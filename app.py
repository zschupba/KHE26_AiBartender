from flask import Flask, render_template, request, session, redirect, url_for
import time
import sqlite3
import hashlib

app = Flask(__name__)
app.secret_key = "dev_secret_key"  

# Configuration
MAX_ATTEMPTS = 5        # Amount of attempts before lockout
LOCKOUT_DURATION = 300  # Lockout after x number of attempts
AUTH_DELAY = 1          # Time delay after each password attempt

# Database setup
def get_db():
    return sqlite3.connect('users.db')

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Create table if not exists
with get_db() as conn:
    with open('schema.sql', 'r') as f:
        sql = f.read()
    conn.executescript(sql)
    # Add default admin user if not exists
    if not conn.execute('SELECT * FROM users WHERE username = "admin"').fetchone():
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hash_password('123')))
    conn.commit()

@app.route('/', methods=['GET', 'POST'])
def login():
    # Initialize session state
    if 'failures' not in session:
        session['failures'] = 0
    
    # 1) Check Lockout Status
    if 'lockout_until' in session:
        remaining = session['lockout_until'] - time.time()
        if remaining > 0:
            return f"<h1>Locked Out</h1><p>Try again in {int(remaining)} seconds.</p>"
        else:
            session.pop('lockout_until')
            session['failures'] = 0

    error = None
    if request.method == 'POST':
        # 2) Enforce delay
        time.sleep(AUTH_DELAY)
        
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = hash_password(password)

        # 3) Validate Credentials
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, hashed_password)).fetchone()
            if user:
                session['failures'] = 0
                return "<h1>Success!</h1><p>You are logged in.</p><a href='/'>Logout</a>"
        
        # 4) Handle Failure
        session['failures'] += 1
        if session['failures'] >= MAX_ATTEMPTS:
            session['lockout_until'] = time.time() + LOCKOUT_DURATION
            return "Too many failed attempts. Locked for 5 minutes."
        
        error = f"Invalid login. Attempt {session['failures']} of {MAX_ATTEMPTS}."

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            error = "Passwords do not match."
        elif not username or not password:
            error = "Username and password are required."
        else:
            hashed_password = hash_password(password)
            try:
                with get_db() as conn:
                    conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
                    conn.commit()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                error = "Username already exists."
    
    return render_template('register.html', error=error)

if __name__ == '__main__':
    app.run(debug=True)