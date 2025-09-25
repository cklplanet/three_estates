"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: run_gpt_prompt.py
Description: Defines all run gpt prompt functions. These functions directly
interface with the safe_generate_response function.
"""
import re
import datetime
import sys
import ast

sys.path.append('../../')

from global_methods import *
from persona.prompt_template.gpt_structure import *
# from persona.prompt_template.print_prompt import *

def json_cleanup(output):
  start = output.find('{')
  end = output.rfind('}') + 1   # +1 to include the last }

  if start == -1 or end == -1:
      raise ValueError("No JSON object found in output")

  json_str = output[start:end]
  output = json.loads(json_str)
  return output

def run_gpt_prompt_generate_character(character_group_context, existing_character_choices, name_mode, test_input=None, verbose=False): 

  if not existing_character_choices:
    existing_character_choices = "This is the first generation in the group"
  else:
    existing_character_choices = "You have to come up with another character other than the ones already present in the group: " + existing_character_choices
  data = {
    "character_group_context": character_group_context,
    "existing_character_choices":existing_character_choices
  }
  if name_mode != "single":
    prompt_template = "persona/prompt_template/templates/generate_persona.txt"
  else:
    prompt_template = "persona/prompt_template/templates/generate_persona_single_name.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  #print(output) #debug
  
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_generate_relationship(character_group_context, persona1, persona2, test_input=None, verbose=False): 
  character_1_information = persona1.scratch.get_str_iss()
  character_2_information = persona2.scratch.get_str_iss()
  data = {
    "character_1_information": character_1_information,
    "character_2_information": character_2_information,
    "character_group_context": character_group_context
  }

  prompt_template = "persona/prompt_template/templates/generate_relationship.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  output = output.strip()
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_generate_next_convo_line_normal(persona, table, test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table)

  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data['personal_context_msg'],
    "current_table_context": data['current_table_context'],
    "ability_msg": data['ability_msg'],
    "recent_conversation": data['recent_conversation'],
    "current_table_events": data['current_table_events'],
    "current_table_additional_context": data['current_table_additional_context'],
    "stay_at_table_reason": data['stay_at_table_reason'],
    "total_time_left": data['total_time_left'],
  }

  speech_reason = persona.scratch.act_reasoning

  data_sub["speech_reason"] = speech_reason

  prompt_template = "persona/prompt_template/templates/generate_next_convo_line_normal.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  print(output)
  
  if output != False: 
    return output, [output, prompt, data]



def run_gpt_prompt_generate_next_convo_line_special(persona, table, special_circumstance, test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table)
  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data['personal_context_msg'],
    "current_table_context": data['current_table_context'],
    "ability_msg": data['ability_msg'],
    "recent_conversation": data['recent_conversation'],
    "current_table_events": data['current_table_events'],
    "current_table_additional_context": data['current_table_additional_context'],
    "stay_at_table_reason": data['stay_at_table_reason'],
    "total_time_left": data['total_time_left'],
  }

  data_sub["special_circumstance"] = special_circumstance

  prompt_template = "persona/prompt_template/templates/generate_next_convo_line_special.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  print(output)
  
  if output != False: 
    return output, [output, prompt, data]



def run_gpt_prompt_chat_poignancy(persona, chat, test_input=None, verbose=False): 
  personal_game_context = persona.get_personal_game_context()
  data = {"PREFIX": PREFIX,
          "personal_game_context":personal_game_context,
          "current_line":chat}

  prompt_template = "persona/prompt_template/templates/poignancy_chat.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=int)
  #print("chat poignancy output: --->>>", output)
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_event_poignancy(persona, event_description, test_input=None, verbose=False): 
  personal_game_context = persona.get_personal_game_context()
  data = {"PREFIX": PREFIX,
          "personal_game_context":personal_game_context,
          "event_desp":event_description}

  prompt_template = "persona/prompt_template/templates/poignancy_event.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=int)
  #print("event poignancy output: --->>>", output)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_thought_poignancy(persona, thought_description, test_input=None, verbose=False): 
  personal_game_context = persona.get_personal_game_context()
  data = {"PREFIX": PREFIX,
          "personal_game_context":personal_game_context,
          "thought_desp":thought_description}

  prompt_template = "persona/prompt_template/templates/poignancy_thought.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  


def run_gpt_prompt_act_bidding_ability(persona, table, test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_speaking.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_act_bidding_reveal(persona, table, test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_reveal.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def get_bidding_common_data(persona, table):
  retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = persona.scratch.retrieved
  current_table_context = ""
  dict = retrieved_all_tables[persona.scratch.curr_loc]
  new_line = f"Players currently seated at your table, the {persona.scratch.curr_loc}:\n"      
  current_table_context += new_line
  for other_player, other_player_dict in dict.items():
    current_table_context += f"\t{other_player}\n"
    current_table_context += f"\tRelevant events:\n"
    for event in other_player_dict["events"]:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
      new_line = f"\t\t({time_ago} ago)"+ event.description + f" at the {event.table} table\n"
      current_table_context += new_line
    current_table_context += f"\tRelevant thoughts:\n"
    for thought in other_player_dict["thoughts"]:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - thought.created)
      new_line = "\t\t"+ f"I came to the conclusion {time_ago} ago: " + thought.description + "\n"
      current_table_context += new_line
  personal_context_msg = persona.get_personal_game_context()
  if persona.scratch.curr_time == datetime.timedelta(0):
    personal_context_msg += "\nThe game has only JUST started and barely anyone has said or done anything yet.\n"
  ability_msg = ability_trigger(persona, table)
  #retrieved_lines_related: {line_content: list of event nodes, line_2_content: list of event nodes, etc.}
  current_table_additional_context = "This also reminds you that:\n"
  for line, line_event_list in self_retrieved_lines_related.items():
    for event in line_event_list:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
      if event.type == "chat":
        current_table_additional_context += (f"\t({time_ago} ago)" + event.description + "\n")
      else:
        current_table_additional_context += (f"\t({time_ago} ago)"+ event.description + f" at the {event.table} table\n")

  other_table_additional_context = ""
  if other_retrieved_lines_related:
    other_table_additional_context = "Suddenly you also hear loud commotion from other tables:"
    for line_with_table_info, event_list in other_retrieved_lines_related.items():
      other_table_additional_context += line_with_table_info
      other_table_additional_context += "\nThis also reminds you that:\n"
      for event in event_list:
        time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
        if event.type == "chat":
          other_table_additional_context += (f"\t({time_ago} ago)" + event.description + "\n")
        else:
          other_table_additional_context += (f"\t({time_ago} ago)"+ event.description + f" at the {event.table} table\n")

  total_time_left = timedelta_to_natural(TIMERS["Village"] - persona.scratch.curr_time)

  recent_conversation = ""
  for timestamp_dict in persona.scratch.recent_conversation:
    timestamp, timestamp_events = timestamp_dict
    for event in timestamp_events:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
      new_line = f"({time_ago} ago)"+ event.description + f" at the {event.table} table\n"
      recent_conversation += new_line
      
  lockdown_matches = [t for t in table.lockdown_targets if t[1] == persona.scratch.name]
  if not lockdown_matches: # not under influence of abilities rn
    stay_at_table_reason = "you're staying at the table with no rush of going anywhere now"
  else:
    captor_roles = [t[2] for t in lockdown_matches]
    captor_roles = "'s and ".join(captor_roles)
    stay_at_table_reason = f"you're forced to stay due to {captor_roles}'s abilities"
  current_table_events = ""
  if retrieved_self:
    current_table_events = "And right now the latest activities at the table are:\n"
    for event_desc in retrieved_self.keys():
      current_table_events += event_desc

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": personal_context_msg,
    "current_table_context": current_table_context,
    "ability_msg": ability_msg,
    "recent_conversation": recent_conversation,
    "current_table_events": current_table_events,
    "current_table_additional_context": current_table_additional_context,
    "other_table_additional_context": other_table_additional_context,
    "stay_at_table_reason": stay_at_table_reason,
    "total_time_left": total_time_left,
  }

  return data
  


def run_gpt_prompt_act_bidding_speak(persona, table, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_speaking.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  


def run_gpt_prompt_decide_on_leaving(persona, table, retrieved_all_tables, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  external_table_context = ""
  for table_name, dict in retrieved_all_tables.items():
    new_line = f"Players currently seated at the {table_name} table:"      
    if persona.scratch.curr_loc == table_name:
      new_line += ", which is your table"
      new_line += ":\n"
    external_table_context += new_line
    for other_player, other_player_dict in dict.items():
      external_table_context += f"\t{other_player}\n"
      external_table_context += f"\tRelevant events:\n"
      for event in other_player_dict["events"]:
        time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
        new_line = "\t\t"+ event.description + f" at the {event.table} table at {time_ago}\n"
        external_table_context += new_line
      external_table_context += f"\tRelevant thoughts:\n"
      for thought in other_player_dict["thoughts"]:
        new_line = "\t\t"+ f"I thought back at {thought.created}: " + thought.description + "\n"
        external_table_context += new_line
  personal_context_msg = persona.get_personal_game_context()
  ability_msg = ability_trigger(persona, table)

  table_time_left = timedelta_to_natural(TIMERS[persona.scratch.curr_loc] - persona.scratch.curr_time)
  total_time_left = timedelta_to_natural(TIMERS["Village"] - persona.scratch.curr_time)

  current_table = persona.scratch.curr_loc
  other_options = set(retrieved_all_tables.keys()) - {current_table}
  other_options = " or ".join(list(other_options))
  options = " | ".join(list(other_options))

  recent_conversation = ""
  for timestamp_dict in persona.scratch.recent_conversation:
    timestamp, timestamp_events = timestamp_dict
    for event in timestamp_events:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
      new_line = f"({time_ago} ago)"+ event.description + f" at the {event.table} table\n"
      recent_conversation += new_line

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": personal_context_msg,
    "external_table_context": external_table_context,
    "ability_msg": ability_msg,
    "recent_conversation": recent_conversation,
    "current_table": current_table,
    "other_options": other_options,
    "table_time_left": table_time_left,
    "total_time_left": total_time_left,
    "options": options
  }

  prompt_template = "persona/prompt_template/templates/decide_on_moving.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_select_ability_target(persona, table, test_input=None, verbose=False): 
  # this function is only even relevant to queen, spinster, bishop, and king
  data = get_bidding_common_data(persona, table)
  ability_target_info = ""
  
  if persona.scratch.role == "King":
    family_options = set()
    for player_name, player in table.personas.items():
      family_options.add(ROLE_DICT[player.scratch.role]["family"])
    ability_target_info += "as King, you can select one of the families present at the table as target:\n"
    family_options = ", ".join(list(family_options))
    ability_target_info += family_options
  elif persona.scratch.role == "Baron":
    ability_target_info += f"as Baron, you can select one of the players present at the table as target:\n"
    target_options = ", ".join(list(table.baron_trigger))
  elif persona.scratch.role == "Spinster" or persona.scratch.role == "Queen" or persona.scratch.role == "Bishop":
    ability_target_info += f"as {persona.scratch.role}, you can select one of the players present at the table as target:\n"
    target_options = ", ".join(list(set(table.personas.keys()) - {persona.scratch.name}))
    ability_target_info += target_options

  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "ability_target_info": ability_target_info
  }
  prompt_template = "persona/prompt_template/templates/select_ability_target.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]



def run_gpt_prompt_select_ability_destination(persona, table, retrieved_all_tables, special_circumstance
, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  external_table_context = ""
  for table_name, dict in retrieved_all_tables.items():
    new_line = f"Players currently seated at the {table_name} table:"      
    if persona.scratch.curr_loc == table_name:
      new_line += ", which is your table"
      new_line += ":\n"
    external_table_context += new_line
    for other_player, other_player_dict in dict.items():
      external_table_context += f"\t{other_player}\n"
      external_table_context += f"\tRelevant events:\n"
      for event in other_player_dict["events"]:
        time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
        new_line = "\t\t"+ event.description + f" at the {event.table} table at {time_ago}\n"
        external_table_context += new_line
      external_table_context += f"\tRelevant thoughts:\n"
      for thought in other_player_dict["thoughts"]:
        new_line = "\t\t"+ f"I thought back at {thought.created}: " + thought.description + "\n"
        external_table_context += new_line
  personal_context_msg = persona.get_personal_game_context()
  ability_msg = ability_trigger(persona, table)

  table_time_left = timedelta_to_natural(TIMERS[persona.scratch.curr_loc] - persona.scratch.curr_time)
  total_time_left = timedelta_to_natural(TIMERS["Village"] - persona.scratch.curr_time)

  special_circumstance = special_circumstance
  current_table = persona.scratch.curr_loc
  other_options = set(retrieved_all_tables.keys()) - {current_table}
  other_options = " or ".join(list(other_options))
  options = " | ".join(list(other_options))
  
  recent_conversation = ""
  for timestamp_dict in persona.scratch.recent_conversation:
    timestamp, timestamp_events = timestamp_dict
    for event in timestamp_events:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
      new_line = f"({time_ago} ago)"+ event.description + f" at the {event.table} table\n"
      recent_conversation += new_line

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": personal_context_msg,
    "external_table_context": external_table_context,
    "ability_msg": ability_msg,
    "special_circumstance": special_circumstance,
    "recent_conversation": recent_conversation,
    "other_options": other_options,
    "table_time_left": table_time_left,
    "total_time_left": total_time_left,
    "options": options
  }

  prompt_template = "persona/prompt_template/templates/select_ability_destination.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_decide_card_retrieval(persona, table, object, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  data = get_bidding_common_data(persona, table)
  stay_at_table_reason = ""
  if persona.scratch.role == "Nun":
    stay_at_table_reason = f"you're the Nun and your card and ability is currently possessed by and protecting {object}"
  else: # Baron case
    stay_at_table_reason = f"your card is in the Baron {object}'s hands and now due to there being only two people at the table you can ask for it back"
  data["stay_at_table_reason"] = stay_at_table_reason
  prompt_template = "persona/prompt_template/templates/decide_card_retrieval.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_reflect_on_subject(persona, subject_events, subject_thoughts, focal_point, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  data = dict()
  subject_event_details = ""
  for event in subject_events[focal_point]:
    time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
    if event.type == "chat":
      subject_event_details += (f"({time_ago} ago)" + event.description + "\n")
    else:
      subject_event_details += (f"({time_ago} ago)" + event.description + f" at the {event.table} table\n")
    # embedding_key should have every information you need already
  subject_thought_details = ""
  for thought in subject_thoughts:
    time_ago = timedelta_to_natural(persona.scratch.curr_time - thought.created)
    subject_thought_details += (f"You concluded {time_ago} ago that: " + thought.description + "\n")

  data = {"subject_thought_details":subject_thought_details,
       "subject_event_details":subject_event_details,
       "question":focal_point}
  prompt_template = "persona/prompt_template/templates/reflect_person_personality.txt"
  f = open(prompt_template, "r")
  prompt = f.read()
  f.close()
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
