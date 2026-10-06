import os
import requests

API_URL = "https://api-inference.huggingface.co/models/FreedomIntelligence/AceGPT-13B-chat"
headers = {"Authorization": "Bearer " + os.environ.get('HF_TOKEN', '')}

def query(payload):
	response = requests.post(API_URL, headers=headers, json=payload)
	return response.json()


while True:
    prompt = input("enter prompt: ")
    output = query({
        "inputs": prompt
    })
    print(output)