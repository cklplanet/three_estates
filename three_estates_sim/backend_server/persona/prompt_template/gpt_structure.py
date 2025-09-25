import json
from openai import OpenAI
import time 
from sentence_transformers import SentenceTransformer
from utils import *

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Initialize OpenRouter-wrapped client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
    default_headers={"HTTP-Referer": "http://localhost:8000"}  # Optional but recommended
)

def temp_sleep(seconds=0.1):
  time.sleep(seconds)

def get_embedding(text):
    if not text.strip():
        text = "this is blank"
    return embedding_model.encode(text, normalize_embeddings=True)

def generate_prompt(curr_input, prompt_lib_file): 
  """
  Takes in the current input (e.g. comment that you want to classifiy) and 
  the path to a prompt file. The prompt file contains the raw str prompt that
  will be used, which contains the following substr: !<INPUT>! -- this 
  function replaces this substr with the actual curr_input to produce the 
  final promopt that will be sent to the GPT3 server. 
  ARGS:
    curr_input: the input we want to feed in (IF THERE ARE MORE THAN ONE
                INPUT, THIS CAN BE A LIST.)
    prompt_lib_file: the path to the promopt file. 
  RETURNS: 
    a str prompt that will be sent to OpenAI's GPT server.  
  """
  if type(curr_input) == type("string"): 
    curr_input = [curr_input]
  curr_input = [str(i) for i in curr_input]

  f = open(prompt_lib_file, "r")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):   
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt: 
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
  return prompt.strip()


def ChatGPT_request(prompt):
    try:
        completion = client.chat.completions.create(
            model="deepseek/deepseek-chat-v3-0324",
            #model="openai/gpt-4.1",
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except Exception:
        print("ChatGPT ERROR")
        return "ChatGPT ERROR"
  

def ChatGPT_safe_generate_response(prompt, 
                                   fail_safe_response="error",
                                   verbose=False): 
  # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt = '"""\n' + prompt + '\n"""\n'
  #prompt += f"Output the response to the prompt above.\n"

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)


  curr_gpt_response = ChatGPT_request(prompt).strip()
  #end_index = curr_gpt_response.rfind('}') + 1
  #curr_gpt_response = curr_gpt_response[:end_index]
  
  if verbose: 
    print (curr_gpt_response)
    print ("~~~~")

  return curr_gpt_response


def ChatGPT_safe_generate_response_full(prompt, 
                                   repeat=3,
                                   func_clean_up=None,
                                   verbose=False): 
  # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt = '"""\n' + prompt + '\n"""\n'
  #prompt += f"Output the response to the prompt above in json. {special_instruction}\n"

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  for i in range(repeat): 

    try: 
      curr_gpt_response = ChatGPT_request(prompt).strip()
      #end_index = curr_gpt_response.rfind('}') + 1
      #curr_gpt_response = curr_gpt_response[:end_index]
      #curr_gpt_response = json.loads(curr_gpt_response)["output"]

      # print ("---ashdfaf")
      # print (curr_gpt_response)
      # print ("000asdfhia")
      
      return func_clean_up(curr_gpt_response)
      
      if verbose: 
        print ("---- repeat count: \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass

  return False