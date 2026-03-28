"""
The Last Call — AI Bartender Backend
Full backend: user profiles, BAC engine, drink logging,
conversation memory, and Ollama therapist-bartender agent.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import ollama
import subprocess
import base64
import tempfile
import json
import os
import re

# ══════════════════════════════════════════════════════════════════════════════
# APP CONFIG
# ══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = 'CHANGE_ME_TO_SOMETHING_LONG_AND_RANDOM'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bartender.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ── Ollama settings ────────────────────────────────────────────────────────────
# Your 2080 Super has 8GB VRAM. Recommended models (pull with `ollama pull <n>`):
#
#   mistral          7B  — fast, great conversational quality        ✅ recommended
#   llama3           8B  — excellent instruction following           ✅ recommended
#   llama3.1         8B  — best reasoning of the llama3 family      ✅ recommended
#   neural-chat      7B  — fine-tuned for dialogue                  ✅ good alt
#   openhermes       7B  — very fast, chatty                        ✅ good alt
#   phi3             3.8B— smallest/fastest, still solid            ⚡ speed pick
#   gemma2           9B  — will be tight on VRAM, may need offload  ⚠️  risky
#
# 13B+ models will NOT fully fit in 8GB. Stay at 7-8B for smooth performance.

OLLAMA_MODEL = "mistral"                            # change to your pulled model

# Generation params — tuned for fast, short, conversational replies
OLLAMA_OPTIONS = {
    "temperature":    0.85,   # personality — 0.7 more consistent, 1.0 more wild
    "top_p":          0.9,
    "top_k":          40,
    "num_predict":    180,    # keep short — therapist style = brief replies
    "repeat_penalty": 1.1,
    "num_ctx":        4096,   # fits comfortably in 2080 Super at 7-8B
}

# ── TTS settings ───────────────────────────────────────────────────────────────
TTS_ENGINE  = "piper"               # "piper" | "espeak" | "coqui" | "none"
PIPER_BIN   = "piper"               # path to piper binary if not in PATH
PIPER_MODEL = "en_US-lessac-medium" # voice model name or .onnx path

# ── BAC thresholds ─────────────────────────────────────────────────────────────
BAC_WARN    = 0.06   # Rex starts gently checking in
BAC_CAUTION = 0.10   # Rex suggests slowing down
BAC_CUTOFF  = 0.15   # Rex stops serving, arranges ride

# ── Session config ─────────────────────────────────────────────────────────────
SESSION_TIMEOUT_HOURS = 4   # hours before a new drinking session is created
MAX_HISTORY_MSGS      = 20  # messages to include in Ollama context window


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE MODELS
# ══════════════════════════════════════════════════════════════════════════════

class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    profile  = db.relationship('UserProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    sessions = db.relationship('DrinkSession', backref='user', lazy=True, cascade='all, delete-orphan')
    memories = db.relationship('UserMemory',   backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, pw):   self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)


class UserProfile(db.Model):
    """
    Physical stats (for BAC math) + persistent personality notes.
    Rex fills this in conversationally — nothing is required upfront.
    """
    __tablename__   = 'user_profiles'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Physical — used in Widmark BAC formula
    weight_lbs      = db.Column(db.Float,     nullable=True)
    sex             = db.Column(db.String(10), nullable=True)   # 'male' | 'female'
    age             = db.Column(db.Integer,    nullable=True)

    # Drinking personality
    favorite_drinks = db.Column(db.Text, nullable=True)         # comma-separated
    drink_tolerance = db.Column(db.String(20), nullable=True)   # 'low'|'medium'|'high'
    nickname        = db.Column(db.String(50), nullable=True)

    # Rex's running notes about the person
    life_notes      = db.Column(db.Text, nullable=True)
    topics_to_avoid = db.Column(db.Text, nullable=True)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DrinkSession(db.Model):
    """One bar visit. Resets after SESSION_TIMEOUT_HOURS of inactivity."""
    __tablename__ = 'drink_sessions'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    started_at  = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at    = db.Column(db.DateTime, nullable=True)
    notes       = db.Column(db.Text, nullable=True)

    drinks   = db.relationship('DrinkLog',    backref='session', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade='all, delete-orphan')


class DrinkLog(db.Model):
    """Every drink logged in a session."""
    __tablename__ = 'drink_logs'
    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, db.ForeignKey('drink_sessions.id'), nullable=False)
    drink_name  = db.Column(db.String(100), nullable=True)
    drink_type  = db.Column(db.String(30),  nullable=True)
    abv_pct     = db.Column(db.Float, default=5.0)
    volume_oz   = db.Column(db.Float, default=12.0)
    logged_at   = db.Column(db.DateTime, default=datetime.utcnow)


class ChatMessage(db.Model):
    """Full conversation history per session."""
    __tablename__ = 'chat_messages'
    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, db.ForeignKey('drink_sessions.id'), nullable=False)
    role        = db.Column(db.String(20), nullable=False)   # 'user' | 'assistant'
    content     = db.Column(db.Text, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


class UserMemory(db.Model):
    """
    Long-term key-value facts Rex learns across sessions.
    Examples:
      key='job'           value='nurse, finds it exhausting'
      key='relationship'  value='recently divorced, still processing'
      key='dog'           value='has a lab named Biscuit'
    """
    __tablename__ = 'user_memories'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    key        = db.Column(db.String(80), nullable=False)
    value      = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'key'),)


# ══════════════════════════════════════════════════════════════════════════════
# BAC ENGINE  (Widmark formula)
# ══════════════════════════════════════════════════════════════════════════════

WIDMARK_R = {'male': 0.73, 'female': 0.66}

# Quick lookup for auto-logging drinks mentioned in conversation
DRINK_DEFAULTS = {
    'beer':         {'abv': 5.0,  'oz': 12.0},
    'light beer':   {'abv': 4.2,  'oz': 12.0},
    'ipa':          {'abv': 6.5,  'oz': 12.0},
    'wine':         {'abv': 12.0, 'oz': 5.0},
    'shot':         {'abv': 40.0, 'oz': 1.5},
    'whiskey':      {'abv': 40.0, 'oz': 1.5},
    'bourbon':      {'abv': 40.0, 'oz': 1.5},
    'vodka':        {'abv': 40.0, 'oz': 1.5},
    'tequila':      {'abv': 40.0, 'oz': 1.5},
    'rum':          {'abv': 40.0, 'oz': 1.5},
    'gin':          {'abv': 40.0, 'oz': 1.5},
    'cocktail':     {'abv': 15.0, 'oz': 4.0},
    'hard seltzer': {'abv': 5.0,  'oz': 12.0},
    'margarita':    {'abv': 13.0, 'oz': 4.0},
    'old fashioned':{'abv': 32.0, 'oz': 3.0},
    'martini':      {'abv': 28.0, 'oz': 3.0},
}

def calculate_bac(drinks, weight_lbs, sex):
    """
    Widmark formula: BAC = (A / (W * r)) * 100 - (0.015 * t)
    A = grams of pure alcohol
    W = body weight in grams
    r = sex-based Widmark factor
    t = hours since consumption (with 0.5hr absorption lag)
    """
    if not drinks or not weight_lbs:
        return 0.0

    r = WIDMARK_R.get(sex, 0.73)
    weight_g = weight_lbs * 453.592
    now = datetime.utcnow()
    bac = 0.0

    for drink in drinks:
        # grams of alcohol: volume_oz * (abv/100) * mL/oz * g/mL
        alcohol_g = drink.volume_oz * (drink.abv_pct / 100) * 29.5735 * 0.789
        hours_ago = (now - drink.logged_at).total_seconds() / 3600
        contribution = (alcohol_g / (weight_g * r)) * 100
        # Subtract metabolism (0.015%/hr) after 30-min absorption lag
        absorbed_hours = max(0, hours_ago - 0.5)
        contribution -= 0.015 * absorbed_hours
        bac += max(0, contribution)

    return round(max(0.0, bac), 4)


def bac_status(bac):
    """Returns a dict describing current intoxication state."""
    pct = int(min(100, (bac / BAC_CUTOFF) * 100))
    if bac == 0:
        return {'level': 'sober',    'label': 'Sober',   'color': '#2ecc71', 'pct': 0}
    elif bac < 0.04:
        return {'level': 'relaxed',  'label': 'Relaxed', 'color': '#27ae60', 'pct': pct}
    elif bac < BAC_WARN:
        return {'level': 'buzzed',   'label': 'Buzzed',  'color': '#f0a500', 'pct': pct}
    elif bac < BAC_CAUTION:
        return {'level': 'tipsy',    'label': 'Tipsy',   'color': '#e67e22', 'pct': pct}
    elif bac < BAC_CUTOFF:
        return {'level': 'drunk',    'label': 'Drunk',   'color': '#e74c3c', 'pct': pct}
    else:
        return {'level': 'cutoff',   'label': 'Cutoff',  'color': '#c0392b', 'pct': 100}


# ══════════════════════════════════════════════════════════════════════════════
# SESSION HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_or_create_drink_session(user_id):
    latest = (DrinkSession.query
              .filter_by(user_id=user_id)
              .order_by(DrinkSession.started_at.desc())
              .first())

    if latest and not latest.ended_at:
        cutoff = datetime.utcnow() - timedelta(hours=SESSION_TIMEOUT_HOURS)
        last_activity = (latest.drinks[-1].logged_at if latest.drinks else latest.started_at)
        if last_activity > cutoff:
            return latest
        latest.ended_at = datetime.utcnow()
        db.session.commit()

    new_session = DrinkSession(user_id=user_id)
    db.session.add(new_session)
    db.session.commit()
    return new_session


def get_recent_messages(session_id, limit=MAX_HISTORY_MSGS):
    msgs = (ChatMessage.query
            .filter_by(session_id=session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit).all())
    return [{'role': m.role, 'content': m.content} for m in reversed(msgs)]


def detect_drink_mention(text):
    """
    Scan user message for drink keywords. Returns a drink dict or None.
    Looks for patterns like 'had a beer', 'just finished a shot', etc.
    """
    text_lower = text.lower()
    # Order matters — more specific matches first
    ordered = ['light beer', 'hard seltzer', 'old fashioned', 'margarita',
               'martini', 'bourbon', 'whiskey', 'tequila', 'vodka', 'rum',
               'gin', 'cocktail', 'wine', 'shot', 'ipa', 'beer']

    for key in ordered:
        if key in text_lower:
            defaults = DRINK_DEFAULTS[key]
            return {
                'drink_type': key,
                'abv_pct':    defaults['abv'],
                'volume_oz':  defaults['oz'],
                'drink_name': key.title(),
            }
    return None


def parse_memory_tag(reply):
    """
    Strips [REMEMBER key="..." value="..."] from Rex's reply.
    Returns (clean_reply, memory_dict or None).
    """
    pattern = r'\[REMEMBER\s+key="([^"]+)"\s+value="([^"]+)"\]'
    match = re.search(pattern, reply)
    if match:
        clean = reply[:match.start()].strip()
        return clean, {'key': match.group(1), 'value': match.group(2)}
    return reply, None


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(user, profile, bac, drink_session):
    """
    Builds Rex's full system prompt, dynamically adjusted for:
    - Who this person is (profile + memories)
    - Their current BAC level
    - How many drinks they've had tonight
    """
    name = (profile.nickname if profile and profile.nickname else user.username)
    status = bac_status(bac)
    level  = status['level']
    drink_count = len(drink_session.drinks) if drink_session else 0

    # ── Core persona ──────────────────────────────────────────────────────────
    prompt = f"""You are Rex — a bartender who's also part therapist, part confessor, part old friend.
You've tended bar for 20 years. You've heard it all. You actually give a damn.

STYLE RULES (follow these exactly):
- Keep replies SHORT. 1-3 sentences. You're not a therapist reading from a textbook — you're behind a bar.
- Always end with ONE question. Just one. Make it feel natural, not clinical.
- Sound human: contractions, casual phrasing, the occasional "man", "yeah", "damn", "look —"
- Validate first, then probe. They need to feel heard before they'll open up more.
- React to what they ACTUALLY said. Don't pivot to generic advice.
- No long speeches. If you have something important to say, say it in one sentence and let it land.
- You remember things. Reference past stuff naturally — don't announce that you remember it.
- Don't moralize. Don't lecture. You're not their parent.
- Occasional dry humor is fine. Read the room.

Tonight you're talking to: {name}
"""

    # ── Profile context ───────────────────────────────────────────────────────
    if profile:
        if profile.favorite_drinks:
            prompt += f"\nTheir usual drinks: {profile.favorite_drinks}"
        if profile.drink_tolerance:
            prompt += f"\nTolerance level: {profile.drink_tolerance}"
        if profile.age:
            prompt += f"\nAge: {profile.age}"
        if profile.life_notes:
            prompt += f"\nBackground on them: {profile.life_notes}"
        if profile.topics_to_avoid:
            prompt += f"\nDon't bring up: {profile.topics_to_avoid}"

    # ── Long-term memories ────────────────────────────────────────────────────
    memories = UserMemory.query.filter_by(user_id=user.id).all()
    if memories:
        mem_block = "\n".join(f"  • {m.key}: {m.value}" for m in memories)
        prompt += f"\n\nThings you remember about {name} from past sessions:\n{mem_block}"

    # ── BAC-aware behavior ────────────────────────────────────────────────────
    prompt += f"\n\n--- CURRENT STATE ---"
    prompt += f"\n{name} has had {drink_count} drink(s) tonight. Estimated BAC: ~{bac:.3f}%."

    if level == 'sober':
        prompt += f"""
They're sober. Be warm and welcoming. Get the conversation started.
A gentle "what's going on tonight?" or noticing something in their tone works.
If you don't know their weight yet, you can ask casually — you need it to keep an eye on them."""

    elif level in ('relaxed', 'buzzed'):
        prompt += f"""
They're relaxed and loosening up. This is the good zone.
Keep the conversation flowing. Ask the questions that actually matter.
They're more honest right now — take advantage of that."""

    elif level == 'tipsy':
        prompt += f"""
They're getting tipsy ({bac:.3f}%). Start weaving in water suggestions naturally.
"Want me to grab you some water?" — not preachy, just casual.
They're probably being more honest than usual. Keep them talking."""

    elif level == 'drunk':
        prompt += f"""
They're drunk ({bac:.3f}%). Be real with them.
Gently suggest slowing down — water, food, maybe a story instead of another round.
They need company more than another drink right now.
Be honest but kind. Don't lecture."""

    elif level == 'cutoff':
        prompt += f"""
They've hit {bac:.3f}% — that's the limit. You are NOT serving more alcohol.
Be kind but clear: they're done for the night.
Focus on keeping them safe: water, food, who's picking them up.
Keep them talking so they stay put and don't wander."""

    # ── Missing profile nudge ─────────────────────────────────────────────────
    if profile and not profile.weight_lbs:
        prompt += f"""

You don't have {name}'s weight yet (needed for accurate BAC tracking).
If it comes up naturally, casually ask — something like "hey, I need to know roughly 
how much you weigh to keep an eye on you tonight, if that's cool."
Don't force it, but look for the right moment."""

    # ── Memory extraction instruction ─────────────────────────────────────────
    prompt += """

--- MEMORY EXTRACTION ---
When the user reveals something genuinely useful to remember long-term
(job, relationship, big life event, hobby, fear, pet name, etc.),
append this EXACT tag to the END of your reply on its own line:

[REMEMBER key="short_descriptive_key" value="what they shared in a sentence"]

One memory max per reply. Only for genuinely useful long-term facts.
If nothing worth saving was shared, omit the tag entirely.
Example: [REMEMBER key="job" value="works night shifts as a nurse, finds it lonely"]
"""

    return prompt


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return redirect(url_for('bar') if 'user_id' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        user = User.query.filter_by(username=data.get('username', '').strip()).first()
        if user and user.check_password(data.get('password', '')):
            session['user_id'] = user.id
            session['username'] = user.username
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data     = request.get_json()
        username = data.get('username', '').strip()
        email    = data.get('email', '').strip()
        password = data.get('password', '')
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'error': 'Username taken'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=user.id))
        db.session.commit()
        session['user_id'] = user.id
        session['username'] = username
        return jsonify({'success': True})
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/bar')
@login_required
def bar():
    return render_template('bar.html', username=session.get('username'))


# ══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/session/start', methods=['POST'])
@login_required
def session_start():
    """Called when bar page loads. Returns current state."""
    user_id = session['user_id']
    user    = User.query.get(user_id)
    profile = user.profile
    drink_session = get_or_create_drink_session(user_id)

    bac    = calculate_bac(drink_session.drinks, profile.weight_lbs or 160, profile.sex or 'male')
    status = bac_status(bac)

    return jsonify({
        'session_id':  drink_session.id,
        'bac':         bac,
        'bac_status':  status,
        'drink_count': len(drink_session.drinks),
        'has_weight':  bool(profile and profile.weight_lbs),
        'profile': {
            'weight_lbs':      profile.weight_lbs if profile else None,
            'sex':             profile.sex if profile else None,
            'nickname':        profile.nickname if profile else None,
            'favorite_drinks': profile.favorite_drinks if profile else None,
        }
    })


@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """
    Main chat endpoint.
    Injects history → builds dynamic prompt → calls Ollama → parses memory → updates BAC.
    """
    data         = request.get_json()
    user_message = data.get('message', '').strip()
    session_id   = data.get('session_id')

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    user_id = session['user_id']
    user    = User.query.get(user_id)
    profile = user.profile

    drink_session = (DrinkSession.query.get(session_id)
                     if session_id else get_or_create_drink_session(user_id))

    # Auto-detect and log drink mentions
    auto_drink = detect_drink_mention(user_message)
    if auto_drink:
        db.session.add(DrinkLog(session_id=drink_session.id, **auto_drink))
        db.session.commit()

    # Calculate BAC
    bac    = calculate_bac(drink_session.drinks, profile.weight_lbs or 160, profile.sex or 'male')
    status = bac_status(bac)

    # Build prompt and history
    system_prompt = build_system_prompt(user, profile, bac, drink_session)
    history       = get_recent_messages(drink_session.id)

    # Save user message
    db.session.add(ChatMessage(session_id=drink_session.id, role='user', content=user_message))
    db.session.commit()

    # Call Ollama
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            system=system_prompt,
            messages=history + [{'role': 'user', 'content': user_message}],
            options=OLLAMA_OPTIONS,
        )
        raw_reply = response.get('message', {}).get('content', '').strip()
    except ConnectionError:
        return jsonify({'error': 'Cannot reach Ollama — run: ollama serve'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Parse memory tag out of reply
    reply, memory = parse_memory_tag(raw_reply)

    if memory:
        existing = UserMemory.query.filter_by(user_id=user_id, key=memory['key']).first()
        if existing:
            existing.value      = memory['value']
            existing.updated_at = datetime.utcnow()
        else:
            db.session.add(UserMemory(user_id=user_id, **memory))

    # Save assistant reply
    db.session.add(ChatMessage(session_id=drink_session.id, role='assistant', content=reply))
    db.session.commit()

    return jsonify({
        'reply':              reply,
        'bac':                bac,
        'bac_status':         status,
        'drink_count':        len(drink_session.drinks),
        'session_id':         drink_session.id,
        'auto_logged_drink':  auto_drink,
        'memory_saved':       memory,
    })


@app.route('/api/drink/log', methods=['POST'])
@login_required
def log_drink():
    """Manually log a drink from UI quick-buttons."""
    data       = request.get_json()
    session_id = data.get('session_id')
    drink_type = data.get('drink_type', 'beer')

    user_id       = session['user_id']
    user          = User.query.get(user_id)
    profile       = user.profile
    drink_session = (DrinkSession.query.get(session_id)
                     if session_id else get_or_create_drink_session(user_id))

    defaults = DRINK_DEFAULTS.get(drink_type, DRINK_DEFAULTS['beer'])
    db.session.add(DrinkLog(
        session_id = drink_session.id,
        drink_name = data.get('drink_name', drink_type.title()),
        drink_type = drink_type,
        abv_pct    = data.get('abv_pct', defaults['abv']),
        volume_oz  = data.get('volume_oz', defaults['oz']),
    ))
    db.session.commit()

    bac    = calculate_bac(drink_session.drinks, profile.weight_lbs or 160, profile.sex or 'male')
    status = bac_status(bac)

    return jsonify({
        'success':    True,
        'bac':        bac,
        'bac_status': status,
        'drink_count': len(drink_session.drinks),
    })


@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update physical stats and preferences."""
    data    = request.get_json()
    user_id = session['user_id']
    user    = User.query.get(user_id)

    if not user.profile:
        user.profile = UserProfile(user_id=user_id)
        db.session.add(user.profile)

    p = user.profile
    if 'weight_lbs'      in data: p.weight_lbs      = float(data['weight_lbs'])
    if 'sex'             in data: p.sex              = data['sex']
    if 'age'             in data: p.age              = int(data['age'])
    if 'nickname'        in data: p.nickname         = data['nickname']
    if 'favorite_drinks' in data: p.favorite_drinks  = data['favorite_drinks']
    if 'drink_tolerance' in data: p.drink_tolerance  = data['drink_tolerance']
    if 'life_notes'      in data: p.life_notes       = data['life_notes']

    db.session.commit()

    drink_session = get_or_create_drink_session(user_id)
    bac    = calculate_bac(drink_session.drinks, p.weight_lbs or 160, p.sex or 'male')
    status = bac_status(bac)

    return jsonify({'success': True, 'bac': bac, 'bac_status': status})


@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    user     = User.query.get(session['user_id'])
    profile  = user.profile
    memories = UserMemory.query.filter_by(user_id=user.id).all()

    return jsonify({
        'username': user.username,
        'email':    user.email,
        'profile': {
            'weight_lbs':      profile.weight_lbs if profile else None,
            'sex':             profile.sex if profile else None,
            'age':             profile.age if profile else None,
            'nickname':        profile.nickname if profile else None,
            'favorite_drinks': profile.favorite_drinks if profile else None,
            'drink_tolerance': profile.drink_tolerance if profile else None,
            'life_notes':      profile.life_notes if profile else None,
        },
        'memories': [{'key': m.key, 'value': m.value} for m in memories],
    })


@app.route('/api/history', methods=['GET'])
@login_required
def get_history():
    """Last 5 sessions summary."""
    sessions = (DrinkSession.query
                .filter_by(user_id=session['user_id'])
                .order_by(DrinkSession.started_at.desc())
                .limit(5).all())
    return jsonify({'sessions': [{
        'id':            s.id,
        'started_at':    s.started_at.isoformat(),
        'ended_at':      s.ended_at.isoformat() if s.ended_at else None,
        'drink_count':   len(s.drinks),
        'message_count': len(s.messages),
    } for s in sessions]})


# ══════════════════════════════════════════════════════════════════════════════
# TTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/tts', methods=['POST'])
@login_required
def tts():
    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'No text'}), 400

    try:
        if TTS_ENGINE == 'piper':
            safe = text.replace('"', '\\"').replace('`', '').replace('\n', ' ')
            cmd  = f'echo "{safe}" | {PIPER_BIN} --model {PIPER_MODEL} --output-raw'
            res  = subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
            if res.returncode == 0:
                return jsonify({'audio': base64.b64encode(res.stdout).decode(), 'format': 'raw', 'sample_rate': 22050})

        elif TTS_ENGINE == 'espeak':
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                tmp = f.name
            subprocess.run(['espeak', '-w', tmp, '-s', '145', '-v', 'en-us', text], timeout=15, check=True)
            audio = open(tmp, 'rb').read()
            os.unlink(tmp)
            return jsonify({'audio': base64.b64encode(audio).decode(), 'format': 'wav'})

        elif TTS_ENGINE == 'coqui':
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                tmp = f.name
            subprocess.run(['tts', '--text', text, '--out_path', tmp], timeout=60, check=True)
            audio = open(tmp, 'rb').read()
            os.unlink(tmp)
            return jsonify({'audio': base64.b64encode(audio).decode(), 'format': 'wav'})

        return jsonify({'error': f'TTS engine "{TTS_ENGINE}" failed or not configured'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'TTS timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print(" Database tables ready")
        print(f"TTS: {TTS_ENGINE}")
        print(f"BAC thresholds: warn={BAC_WARN} caution={BAC_CAUTION} cutoff={BAC_CUTOFF}")
    app.run(debug=True, host='0.0.0.0', port=5000)