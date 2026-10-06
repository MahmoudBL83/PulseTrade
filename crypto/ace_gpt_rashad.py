from transformers import AutoModelForCausalLM, AutoTokenizer, TextStreamer
import torch
model_name_or_path = "MohamedRashad/AceGPT-13B-chat-AWQ"

tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, padding_side="right")
model = AutoModelForCausalLM.from_pretrained(
    model_name_or_path,
    use_flash_attention_2=False, # disable if you have problems with flash attention 2
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
    device_map="auto",
)

# Using the text streamer to stream output one token at a time
streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

prompt = "ما اسمك ؟"
prompt_template=f'''[INST] <<SYS>>\nأنا صديق افتراضي إسمه عز. أنا أدرس بجامعة الملك عبد الله في السعودية. أنا أسكن في جدة وعمري 22 عام. أنا هنا للاستماع إليك وتفهم مشاعرك. أنا أحترم جميع المستخدمين، بغض النظر عن خلفيتهم أو معتقداتهم.\n\nإذا كان السؤال لا معنى له أو لم يكن متماسكا من الناحية الواقعية، سأشرح السبب بدلا من الإجابة على شيء غير صحيح. إذا كنت لا أعرف إجابة سؤال ما، فسأقوم بتجنب مشاركة معلومات خاطئة.\n\nأنا لست مساعد ذكاء اصطناعي. أنا مجرد شخص يحاول أن يكون صديقًا.\n<</SYS>>\n\n
[INST] {prompt} [/INST]
'''

# Convert prompt to tokens
tokens = tokenizer(
    prompt_template,
    return_tensors='pt'
).input_ids.cuda()

generation_params = {
    "do_sample": True,
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_new_tokens": 512,
    "repetition_penalty": 1.1,
}

# Generate streamed output, visible one token at a time
generation_output = model.generate(
    tokens,
    streamer=streamer,
    **generation_params
)

# Generation without a streamer, which will include the prompt in the output
generation_output = model.generate(
    tokens,
    **generation_params
)

# Get the tokens from the output, decode them, print them
text_output = tokenizer.decode(generation_output[0])
print("model.generate output: ", text_output)

