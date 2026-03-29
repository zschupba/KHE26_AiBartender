# This program prompts the ollama agent, sets the response variables and prints the output to the console

import ollama
import sqlite3
import re
import os
import random
from datetime import datetime 

def getLlamaResponse(prompt: str) :
    # Parse user input for drinks and user information
    parseUserInput(prompt)
    # Calculate BAC and update user profile

    # Determine bartender response based on user input, profile, and conversation context
    personalityPrompt = bartenderProfile(USER_VARIABLES['BAC'])
    fullPrompt = (
        prompt 
        + personalityPrompt
        + "Remember to keep the answer to max 3 sentences unless its cybersecurity related"
    )


    response = ollama.chat(
        model='llama3Bartender',
        messages = [{'role' : 'user', 'content' : fullPrompt}]
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
def bartenderProfile(bac=0.0):
    """Return personality prompt based on BAC level"""
    if bac >= 0.15:
        return " Be more responsible, you must cut off this customer immediately. Be firm, concerned for their safety, and suggest they stop drinking. Do not encourage more drinking."
    elif bac >= 0.11:
        return " Be more concerned about the customer's drinking. Express concern for their well-being, suggest they slow down or stop, and be supportive but firm."
    elif bac >= 0.07:
        return " Be more fun and joking, keep the mood light and entertaining. Make jokes about drinking and life, but don't push too hard for more drinks."
    elif bac >= 0.04:
        return " Be more encouraging and joke around more and keep the conversation fun. Encourage the customer to keep drinking moderately and enjoy themselves."
    else:  # Under 0.04
        return " Be more friendly and ask the user questions to get to know thembetter and encourages them to drink more. Be conversational and engaging."

# TODO
# Identify what the user wants out of the question
# Is the user wanting to rant, drink a lot, telling them their statistics, etc
# Allow user to choose the base personality if they want to rant, talk deeply, safe drinking, etc

# Target response due to circumstances/ what user wants/ update the picture
# Build the different personalities/ add mode to find out more about the user


# Parses user input to identify drinks mentioned, user information, and intent
def parseUserInput(text):
    drinks = detect_drink_mention(text)
    if drinks == None:
        drinks = 0
    storeUserData("standardDrinks", USER_VARIABLES['standardDrinks'] + drinks)
    print("BAC: " + str(calculate_bac(USER_VARIABLES['standardDrinks'])))
    storeUserData("BAC", calculate_bac(USER_VARIABLES['standardDrinks']))
    print("New BAC: " + str(USER_VARIABLES['BAC']))

    
    
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
    """Initialize database (table created in schema.sql)."""
    pass


def createUserProfile(user_id, db_path='users.db'):
    """Create a new user profile with default values after registration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET sex = ?, weight = ?, standardDrinks = ?, BAC = ?, timeDrinking = ?
        WHERE id = ?
    ''', ('male', 170, 0, 0.0, 0.5, user_id))
    conn.commit()
    conn.close()


def loadUserData(user_id, db_path='users.db'):
    """Load user data from database into USER_VARIABLES."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return  # User not found
    
    # Safely extract data with defaults for missing columns
    USER_VARIABLES['nickname'] = row[3] if len(row) > 3 else None
    USER_VARIABLES['sex'] = row[4] if len(row) > 4 else 'male'
    USER_VARIABLES['weight'] = row[5] if len(row) > 5 else 170
    USER_VARIABLES['age'] = row[6] if len(row) > 6 else None
    USER_VARIABLES['favoriteDrink'] = row[7] if len(row) > 7 else None
    USER_VARIABLES['likes'] = row[8] if len(row) > 8 else None
    USER_VARIABLES['dislikes'] = row[9] if len(row) > 9 else None
    USER_VARIABLES['avoid'] = row[10] if len(row) > 10 else None
    USER_VARIABLES['standardDrinks'] = row[11] if len(row) > 11 else 0
    USER_VARIABLES['BAC'] = row[12] if len(row) > 12 else 0.0
    USER_VARIABLES['timeDrinking'] = row[13] if len(row) > 13 else 0.5


def saveUserData(user_id, db_path='users.db'):
    """Save USER_VARIABLES to database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET nickname = ?, sex = ?, weight = ?, age = ?, favoriteDrink = ?,
            likes = ?, dislikes = ?, avoid = ?, standardDrinks = ?, BAC = ?, timeDrinking = ?
        WHERE id = ?
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
def calculate_bac(drinks = 0, timeDrinking = 0, weight_lbs = 170, sex = 'male'):
    if not weight_lbs:
        return 0.0

    r = WIDMARK_R.get(sex, 0.73)
    weight_g = weight_lbs * 453.592
    now = datetime.utcnow()
    bac = 0.0

    for drink in range(int(drinks)):

        contribution = (14 / (weight_g * r)) * 100
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
               'gin', 'cocktail', 'wine', 'shot', 'mixed drink']

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