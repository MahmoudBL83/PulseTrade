from crypto import app, db
import os
from flask import request
import json
import random
import string
import time
from typing import Any
from flask import request, render_template,jsonify
#from g4f import ChatCompletion
import sys
from pathlib import Path
from flask_login import login_required,current_user
#import g4f
from crypto.models import User,Chat
import requests

sys.path.append(str(Path(__file__).parent.parent))

@app.route("/chat/")
def chat_page():
    return render_template("chat2.html",messages = current_user.chats)

@app.route("/llama/",methods=['POST','GET'])
@login_required
def llama_page():
    
    messages = []

    '''for chat in current_user.chats:
        messages.append({"role": chat.role, "content": chat.message})'''
    
    
    messages.append({"role": "system", "content": "You are a virtual friend named azzam"})
    #messages.append({"role": "system", "content": "don't write english write in arabic only"})
    #messages.append({"role": "system", "content": "أنت صديق افتراضي واسمك عزام وأنت سعودي، اكتب باللغة العربية فقط"},)
    messages.append({"role": "user", "content": request.json['message']})
    
    url = "https://swtp771ld3.execute-api.us-east-1.amazonaws.com/default/aoz"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "inputs": [messages],
        "parameters": {
            "max_new_tokens": 256,
            "top_p": 0.9,
            "temperature": 0.6
        }
    }

    data = {
        "inputs": [messages],
        "parameters": {
            "max_new_tokens": 256,
            "top_p":0.9,
            "temperature": 0.7
        }
    }
    

    response = requests.post(url, headers=headers, data=json.dumps(data))

    # Check the response status code
    if response.status_code == 200:
        # Request succeeded
        res = response.json()
        print(res)
        data = res[0]['generation']['content']
        chat1 = Chat(message=request.json['message'],role="user")
        chat2 = Chat(message=data,role="assistant")
        current_user.chats.append(chat1)
        current_user.chats.append(chat2)
        db.session.add(chat1)
        db.session.add(chat2)
        db.session.commit()
        return jsonify(data)

    else:
        # Request failed
        print("Request failed with status code:", response.status_code)
    return jsonify(response.json())


@app.route("/gpt",methods=['POST'])
@login_required
def gpt_Acytoo():
    '''num_tries = 5
    while num_tries > 0:
        response = g4f.ChatCompletion.create(model='gpt-3.5-turbo', provider=g4f.Provider.Acytoo, messages=[{"role": "user", "content": request.args.get('message')}])
        if response is not None:
            return response
        else:
            num_tries -= 1
            time.sleep(3)  # Wait for 3 seconds before trying again

    # If all tries are exhausted and no valid response is generated, return None
    return response'''

    messages = []
    for chat in current_user.chats:
        messages.append({"role": chat.role, "content": chat.message})

    messages.append({"role": "user", "content": request.json['message']})
    
    response = g4f.ChatCompletion.create(
        model="gpt-3.5-turbo",
        provider=g4f.Provider.Ails,
        messages = messages[0:10],
        stream=False,
        active_server=5,
    )

    chat1 = Chat(message=request.json['message'],role="user")
    chat2 = Chat(message=response,role="assistant")
    current_user.chats.append(chat1)
    current_user.chats.append(chat2)
    db.session.add(chat1)
    db.session.add(chat2)
    db.session.commit()

    return jsonify(response)

@app.route("/binggpt/")
def gpt_bing():
    response = g4f.ChatCompletion.create(model='gpt-3.5-turbo', provider=g4f.Provider.Bing, messages=[
        {"role": "user", "content": request.args.get('message')}
    ])

    return response.replace("Bing", "Azzam").replace("بينغ", "عزام").replace("هذا بينغ","أنا عزام")

@app.route("/bardgpt/")
def gpt_bard():
    response = g4f.ChatCompletion.create(model='palm2', provider=g4f.Provider.Bard, messages=[
        {"role": "user", "content": request.args.get('message')}
    ],auth=os.environ.get('GOOGLE_API_KEY', ''))

    return response

@app.route("/llamagpt/")
def gpt_llama():
    response = g4f.ChatCompletion.create(model='llama-13b', provider=g4f.Provider.base_provider, messages=[
        {"role": "user", "content": request.args.get('message')}
    ])

    return response


@app.route("/chat/completions", methods=["POST"])
def chat_completions():
    model = "gpt-3.5-turbo"
    stream = False
    
    messages = []
    for chat in current_user.chats:
        messages.append({"role": chat.role, "content": chat.message})

    messages.append({"role": "user", "content": request.json['message']})
    if len(messages) > 5:
        messages = messages[-5:]
    response = ChatCompletion.create(model=model, stream=stream, messages=messages)

    completion_id = "".join(random.choices(string.ascii_letters + string.digits, k=28))
    completion_timestamp = int(time.time())

    chat1 = Chat(message=request.json['message'],role="user")
    chat2 = Chat(message=response,role="assistant")
    current_user.chats.append(chat1)
    current_user.chats.append(chat2)
    db.session.add(chat1)
    db.session.add(chat2)
    db.session.commit()

    if not stream:
        return jsonify(response)
        return {
            "id": f"chatcmpl-{completion_id}",
            "object": "chat.completion",
            "created": completion_timestamp,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            },
        }
