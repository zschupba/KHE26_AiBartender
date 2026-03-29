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
        model='llama3.21stBartender',
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
    drinks = detect_drink_mention(text)
    
    storeUserData("standardDrinks", USER_VARIABLES['standardDrinks'] + drinks)
    print("BAC: " + str(calculate_bac(USER_VARIABLES['standardDrinks'])))
    storeUserData("BAC", calculate_bac(USER_VARIABLES['standardDrinks']))

    
    
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
    'standardDrinks': 0,
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
            standardDrinks DEFAULT 0.0,
            bac REAL DEFAULT 0.0,
            timeDrinking 
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
    
    # row: (user_id, nickname, sex, weight, age, favorite_drink, likes, dislikes, avoid, alc_grams_consumed, bac, time_drinking)
    USER_VARIABLES['nickname'] = row[1]
    USER_VARIABLES['sex'] = row[2] or 'male'  # Default to male if NULL
    USER_VARIABLES['weight'] = row[3] or 170  # Default to 170 lbs if NULL
    USER_VARIABLES['age'] = row[4]
    USER_VARIABLES['favoriteDrink'] = row[5]
    USER_VARIABLES['likes'] = row[6]
    USER_VARIABLES['dislikes'] = row[7]
    USER_VARIABLES['avoid'] = row[8]
    USER_VARIABLES['standardDrinks'] = row[9] or 0
    USER_VARIABLES['BAC'] = row[10] or 0.0
    USER_VARIABLES['timeDrinking'] = row[11]


def saveUserData(user_id, db_path='users.db'):
    """Save USER_VARIABLES to database."""
    initDatabase(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_profile 
        SET nickname = ?, sex = ?, weight = ?, age = ?, favoriteDrink = ?,
            likes = ?, dislikes = ?, avoid = ?, standardDrinks = ?, BAC = ?, timeDrinking = ?
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
        USER_VARIABLES['standardDrinks'],
        USER_VARIABLES['BAC'],
        USER_VARIABLES['timeDrinking'],
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
    'beer':         {1},
    'ipa':          {1.5},
    'wine':         {1.25},
    'shot':         {1},
    'whiskey':      {1},
    'bourbon':      {1},
    'vodka':        {1},
    'tequila':      {1.5},
    'rum':          {1},
    'gin':          {1},
    'cocktail':     {1.5},
    'hard seltzer': {1},
    'margarita':    {2},
    'mixed drink':    {1.5},
}

"""
Widmark formula: BAC = (A / (W * r)) * 100 - (0.015 * t)
A = grams of pure alcohol
W = body weight in grams
r = sex-based Widmark factor
t = hours since consumption (with 0.5hr lag)
"""
def calculate_bac(drinks = 0, timeDrinking = 0.5, weight_lbs = 170, sex = 'male'):
    if not weight_lbs:
        return 0.0

    r = WIDMARK_R.get(sex, 0.73)
    weight_g = weight_lbs * 453.592
    now = datetime.utcnow()
    bac = 0.0

    for drink in range(int(drinks)):

        contribution = (0.6 / (weight_g * r)) * 100
        # Subtract metabolism (0.015%/hr) after 30-min absorption lag
        absorbed_hours = max(0, timeDrinking - 0.5)
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
            sanitizedDefaults = str(defaults).replace("{","").replace("}","")
            drinksFloat = float(sanitizedDefaults)
            print("num drinks: " + str(drinksFloat))
            return drinksFloat
            
    return None


#if __name__ == '__main__':
    #prompter.run(debug=True)