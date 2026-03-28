# This program prompts the ollama agent, sets the response variables and prints the output to the console

import ollama 

def getLlamaResponse(prompt: str) :
    response = ollama.chat(
        model='llama3.2',
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
def identifyUserIntent(prompt: str):
    # IDK how but i need to determine what the user is asking for and what they want out of the question
    print("test")

# -Listening, talking, suggesting, mentoring, distracting, drinking, encouragement after purchase,
# Target response due to circumstances/ what user wants/ update the picture
# Build the different personalities
# 
# Store user Data and preferences to make the bartender more personalized



#if __name__ == '__main__':
    #prompter.run(debug=True)