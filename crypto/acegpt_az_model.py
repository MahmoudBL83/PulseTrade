import requests

# Dictionary defining roles
role_dict = {
    'AceGPT': ['[INST]', '[/INST]'],  # Role tokens for AceGPT
}

# Dictionary defining start and end tokens
se_tok_dict = {
    'AceGPT': ['', '</s>'],  # Start and end tokens for AceGPT
}

def format_message(query, history, max_src_len, instruct):
    if not history:
        return f"""{instruct}{query} {role_dict["AceGPT"][1]}"""
    else:
        prompt = instruct
        filter_historys = []
        memory_size = len(prompt) + len(query)
        for rev_idx in range(len(history) - 1, -1, -1):
            this_turn_len = len(history[rev_idx][0] + history[rev_idx][1])
            if memory_size + this_turn_len > max_src_len:
                break
            filter_historys.append(history[rev_idx])
            memory_size += this_turn_len
        filter_historys.reverse()
        for i, (old_query, response) in enumerate(filter_historys):
            prompt += f'{old_query} {role_dict["AceGPT"][1]}{response}{se_tok_dict["AceGPT"][1]}{role_dict["AceGPT"][0]} '
        prompt += f'{query} {role_dict["AceGPT"][1]}'
        return prompt

# Constants for token limits and lengths
max_new_tokens = 768
content_len = 2048
max_src_len = content_len - max_new_tokens - 8

# Introduction and instruction message
instruct = """[INST] <<SYS>>\nأنا صديق افتراضي إسمه عز. أنا أدرس بجامعة الملك عبد الله في السعودية. أنا أسكن في جدة وعمري 22 عام. أنا هنا للاستماع إليك وتفهم مشاعرك. أنا أحترم جميع المستخدمين، بغض النظر عن خلفيتهم أو معتقداتهم.\n\nإذا كان السؤال لا معنى له أو لم يكن متماسكا من الناحية الواقعية، سأشرح السبب بدلا من الإجابة على شيء غير صحيح. إذا كنت لا أعرف إجابة سؤال ما، فسأقوم بتجنب مشاركة معلومات خاطئة.\n\nأنا لست مساعد ذكاء اصطناعي. أنا مجرد شخص يحاول أن يكون صديقًا.\n<</SYS>>\n\n"""

# Generate the prompt message
history = [
    ("هل تريد معرفة اسمي", "نعم أريد ذلك"),
    ("اسمي عبد الرحمن", "اسم جميل جداً")
]

prompt = format_message("DO YOU", history, max_src_len, instruct)

# API endpoint for sending the request
api_endpoint = "https://2v8yh9v1w7.execute-api.us-east-1.amazonaws.com/default/aoz"


# Create the payload for the request
payload = {
    "inputs": prompt,
}

print(payload)

# Send the POST request to the API endpoint
response = requests.post(api_endpoint, json=payload)

# Process the response
if response.status_code == 200:
    response_json = response.json()[0]['generated_text'].split("[/INST]")[-1].strip()
    print(response_json)
else:
    print("Request failed with status code:", response.status_code)