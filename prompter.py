# This program prompts the ollama agent, sets the response variables and prints the output to the console

import ollama
import sqlite3
import os
from datetime import datetime 

def getLlamaResponse(prompt: str) :
    # Parse user input for drinks and user information
    parseUserInput(prompt)
    # Calculate BAC and update user profile

    # Determine bartender response based on user input, profile, and conversation context

    response = ollama.chat(
        model='llama3.2Bartender',
        messages = [{'role' : 'user', 'content' : prompt}]
    )
    return response['message']['content']

# quit = False
# while(quit == False):
#     prompt = input("Ask the bartender a question (q for quit): ")
#     print("\n")
#     if(prompt == "q"):
#         quit = True
#     else:
#         response = getLlamaResponse(prompt + str(" answer in <40 words and act like you are a zesty bartender suggesting them to drink more"))
#         print(response)
#         print("\n")
        
# returns how the bartender is going to respond and what image should be displayed
def bartenderProfile():
    print("test1")

# TODO
# Identify what the user wants out of the question
# Is the user wanting to rant, drink a lot, telling them their statistics, etc
# Allow user to choose the base personality if they want to rant, talk deeply, safe drinking, etc

# -Listening, talking, suggesting, mentoring, distracting, drinking, encouragement after purchase,
# Target response due to circumstances/ what user wants/ update the picture
# Build the different personalities/ add mode to find out more about the user

# Parses user input to identify drinks mentioned, user information, and intent
def parseUserInput(text):
    drink = detect_drink_mention(text)
    storeUserData(alcoholGramsConsumed, calculateAlcGrams(drink['abv_pct'], drink['volume_oz']))
    print(calculate_bac(USER_VARIABLES['alcGramsConsumed'], USER_VARIABLES['weight'], USER_VARIABLES['sex']))

    
    
# Store user Data and preferences to make the bartender more personalized
USER_VARIABLES = {
    'nickname': None,   
    'sex': None,
    'weight': None,
    'age': None,
    'favoriteDrink': None,
    'likes': None,
    'dislikes': None,
    'avoid': None,
    'alcGramsConsumed': 0,
    'BAC': 0.0,
    'sessionStart': None
}


def storeUserData(variable, info):
    """Store a single variable in memory."""
    if variable in USER_VARIABLES:
        USER_VARIABLES[variable] = info
    else:
        print(f"Variable {variable} not recognized.")


def initDatabase(db_path='users.db'):
    """Create user_profile table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT,
            sex TEXT,
            weight INTEGER,
            age INTEGER,
            favorite_drink TEXT,
            likes TEXT,
            dislikes TEXT,
            avoid TEXT,
            alc_grams_consumed REAL DEFAULT 0,
            bac REAL DEFAULT 0.0,
            session_start DATETIME
        )
    ''')
    conn.commit()
    conn.close()


def createUserProfile(user_id, db_path='users.db'):
    """Create a new user profile with default values after registration."""
    initDatabase(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_profile (user_id, sex, weight, alc_grams_consumed, bac)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, 'male', 170, 0, 0.0))
    conn.commit()
    conn.close()


def loadUserData(user_id, db_path='users.db'):
    """Load user data from database into USER_VARIABLES. Profile guaranteed to exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_profile WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    # row: (user_id, nickname, sex, weight, age, favorite_drink, likes, dislikes, avoid, alc_grams_consumed, bac, session_start)
    USER_VARIABLES['nickname'] = row[1]
    USER_VARIABLES['sex'] = row[2] or 'male'  # Default to male if NULL
    USER_VARIABLES['weight'] = row[3] or 170  # Default to 170 lbs if NULL
    USER_VARIABLES['age'] = row[4]
    USER_VARIABLES['favoriteDrink'] = row[5]
    USER_VARIABLES['likes'] = row[6]
    USER_VARIABLES['dislikes'] = row[7]
    USER_VARIABLES['avoid'] = row[8]
    USER_VARIABLES['alcGramsConsumed'] = row[9] or 0
    USER_VARIABLES['BAC'] = row[10] or 0.0
    USER_VARIABLES['sessionStart'] = row[11]


def saveUserData(user_id, db_path='users.db'):
    """Save USER_VARIABLES to database."""
    initDatabase(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_profile 
        SET nickname = ?, sex = ?, weight = ?, age = ?, favorite_drink = ?,
            likes = ?, dislikes = ?, avoid = ?, alc_grams_consumed = ?, bac = ?, session_start = ?
        WHERE user_id = ?
    ''', (
        USER_VARIABLES['nickname'],
        USER_VARIABLES['sex'],
        USER_VARIABLES['weight'],
        USER_VARIABLES['age'],
        USER_VARIABLES['favoriteDrink'],
        USER_VARIABLES['likes'],
        USER_VARIABLES['dislikes'],
        USER_VARIABLES['avoid'],
        USER_VARIABLES['alcGramsConsumed'],
        USER_VARIABLES['BAC'],
        USER_VARIABLES['sessionStart'],
        user_id
    ))
    conn.commit()
    conn.close()
# Determin BAC of the user
# Windmark formula for BAC = (A × 5.14 / W × r) - .015 × H
# Automatically assumes everybodies a 170 pound male until the bartender asks
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
    'mixed drink':    {'abv': 13.0, 'oz': 4.0},
}

"""
Widmark formula: BAC = (A / (W * r)) * 100 - (0.015 * t)
A = grams of pure alcohol
W = body weight in grams
r = sex-based Widmark factor
t = hours since consumption (with 0.5hr lag)
"""
def calculate_bac(drinks = 1, weight_lbs = 170, sex = 'male'):
    if not drinks or not weight_lbs:
        return 0.0

    r = WIDMARK_R.get(sex, 0.73)
    weight_g = weight_lbs * 453.592
    now = datetime.utcnow()
    bac = 0.0

    for drink in drinks:
        # grams of alcohol: volume_oz * (abv/100) * mL/oz * g/mL
        
        alcohol_g = calculateAlcGrams(drink['abv_pct'], drink['volume_oz'])
        hours_ago = (now - drink.logged_at).total_seconds() / 3600
        contribution = (alcohol_g / (weight_g * r)) * 100
        # Subtract metabolism (0.015%/hr) after 30-min absorption lag
        absorbed_hours = max(0, hours_ago - 0.5)
        contribution -= 0.015 * absorbed_hours
        bac += max(0, contribution)

    return round(max(0.0, bac), 4)

def calculateAlcGrams(abv_pct, volume_oz):
    return volume_oz * (abv_pct / 100) * 29.5735 * 0.789
    
# Scans user input for mentions of different drinks
def detect_drink_mention(text):
    text_lower = text.lower()
    # Order matters — more specific matches first
    ordered = ['light beer', 'beer', 'ipa', 'hard seltzer', 'old fashioned', 'margarita',
                'bourbon', 'whiskey', 'tequila', 'vodka', 'rum',
               'gin', 'cocktail', 'wine', 'shot', 'mixed drink', 'drink']

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


#if __name__ == '__main__':
    #prompter.run(debug=True)