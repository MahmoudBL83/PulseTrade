from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers import AutoTokenizer
import torch
from auto_gptq import AutoGPTQForCausalLM




# Import the required modules before loading the pickle file
torch.set_default_tensor_type(torch.FloatTensor)  # Set the default tensor type if needed

tokenizer = AutoTokenizer.from_pretrained("AceGPT-7b-chat-GPTQ")
model = AutoModelForCausalLM.from_pretrained("AceGPT-7b-chat-GPTQ",from_tf=True)

#model = AutoGPTQForCausalLM.from_quantized("AceGPT-7b-chat-GPTQ").todevice("cpu")
#tokenizer = AutoTokenizer.from_pretrained("AceGPT-7b-chat-GPTQ", padding_side="right", use_fast=False)

# Load the model from the pickle file
with open("AceGPT-7b-chat-GPTQ/gptq_model-4bit-128g_2.bin", "rb") as f:
    state_dict = torch.load(f, map_location=torch.device('cpu'))

model.load_state_dict(state_dict)

while True:
    prompt = input(">>> ")
    generated_text = model.generate(
        input_ids=tokenizer.encode(prompt, return_tensors="pt"),
        max_length=100,
    )

    print(tokenizer.decode(generated_text[0], skip_special_tokens=True))

