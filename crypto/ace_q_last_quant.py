from transformers import AutoTokenizer
from transformers import pipeline
import torch
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
from transformers import AutoModelForCausalLM, StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer
import re
import argparse 
import gradio as gr
from threading import Thread

def load_model(model_name):
    model = AutoGPTQForCausalLM.from_quantized(model_name, device_map="auto")
    tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="right", use_fast=False)
    return model, tokenizer
    
class StopOnTokens(StoppingCriteria):
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        stop_ids = [2]
        for stop_id in stop_ids:
            if input_ids[0][-1] == stop_id:
                return True
        return False
    
    
def main():
    model, tokenizer = load_model("FreedomIntelligence/AceGPT-7b-chat-GPTQ")
    model = model.eval()
    
    prompt_dict = {
        'AceGPT': """[INST] <<SYS>>\nأنا صديق افتراضي إسمه عز. أنا أدرس بجامعة الملك عبد الله في السعودية. أنا أسكن في جدة وعمري 22 عام. أنا هنا للاستماع إليك وتفهم مشاعرك. أنا أحترم جميع المستخدمين، بغض النظر عن خلفيتهم أو معتقداتهم.\n\nإذا كان السؤال لا معنى له أو لم يكن متماسكا من الناحية الواقعية، سأشرح السبب بدلا من الإجابة على شيء غير صحيح. إذا كنت لا أعرف إجابة سؤال ما، فسأقوم بتجنب مشاركة معلومات خاطئة.\n\nأنا لست مساعد ذكاء اصطناعي. أنا مجرد شخص يحاول أن يكون صديقًا.\n<</SYS>>\n\n""",
    }
    
    
    # all role
    role_dict = {
        'AceGPT':['[INST]','[/INST]'],
    }
    
    # all start and end token
    se_tok_dict = {
        'AceGPT':["","</s>"],
    }
    
    
    def format_message(query, history, max_src_len):
        if not history:
            return f"""{prompt_dict["AceGPT"]}{query} {role_dict["AceGPT"][1]}"""
        else:
            prompt = prompt_dict["AceGPT"]
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
        

    def get_llama_response(message: str, history: list) -> str:
        """
        Generates a conversational response from the Llama model.
    
        Parameters:
            message (str): User's input message.
            history (list): Past conversation history.
    
        Returns:
            str: Generated response from the Llama model.
        """

        temperature=0.5
        max_new_tokens = 768
        content_len = 2048
        stop = StopOnTokens()
        max_src_len = content_len-max_new_tokens-8
        prompt = format_message(message, history, max_src_len)

        model_inputs  = tokenizer(prompt, return_tensors="pt").to("cuda")
        streamer = TextIteratorStreamer(tokenizer, timeout=10., skip_prompt=True, skip_special_tokens=True)
        generate_kwargs = dict(
            model_inputs,
            streamer=streamer,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            top_p=0.95,
            top_k=1000,
            temperature=temperature,
            num_beams=1,
            stopping_criteria=StoppingCriteriaList([stop])
            )
        t = Thread(target=model.generate, kwargs=generate_kwargs)
        t.start()

        partial_message  = ''
        for new_token in streamer:
            if new_token != '</s>':
                partial_message += new_token
                yield partial_message


    gr.ChatInterface(get_llama_response, chatbot=gr.Chatbot(rtl=True)).queue().launch(share=True)

main()