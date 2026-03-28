# This program prompts the ollama agent, sets the response variables and prints the output to the console

import ollama 

def getLlamaResponse(prompt: str) :
    response = ollama.chat(
        model='llama3.2',
        messages = [{'role' : 'user', 'content' : prompt}]
    )
    return response['message']['content']

quit = False
while(quit == False):
    prompt = input("Ask the bartender a question (q for quit): ")
    print("\n")
    if(prompt == "q"):
        quit = True
    else:
        response = getLlamaResponse(prompt + str(" answer in <40 words and act like you are a zesty bartender suggesting them to drink more"))
        print(response)
        print("\n")
        


#if __name__ == '__main__':
    #prompter.run(debug=True)