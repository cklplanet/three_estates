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
import json

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from global_methods import *
from paths import resolve_backend_file
from persona.prompt_template.gpt_structure import *
# from persona.prompt_template.print_prompt import *


def read_prompt_template(prompt_template):
  with open(resolve_backend_file(prompt_template), "r") as f:
    return f.read()


def json_cleanup(output):
  start = output.find('{')
  end = output.rfind('}') + 1   # +1 to include the last }

  if start == -1 or end == -1:
      raise ValueError("No JSON object found in output")

  json_str = output[start:end]
  output = json.loads(json_str)
  return output


def text_cleanup(output):
  return output.strip()


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
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup, model=CHARACTER_GENERATION_LLM_MODEL)
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
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=text_cleanup, model=CHARACTER_GENERATION_LLM_MODEL)
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_generate_vn_epilogue(epilogue_context, test_input=None, verbose=False):
  data = {
    "PREFIX": PREFIX,
    "epilogue_context": epilogue_context
  }
  prompt_template = "persona/prompt_template/templates/generate_vn_epilogue.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=text_cleanup, model=EPILOGUE_GENERATION_LLM_MODEL)
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
    "table_time_left": data['table_time_left'],
    "all_table_time_left": data['all_table_time_left'],
    "total_time_left": data['total_time_left'],
  }

  speech_reason = persona.scratch.act_reasoning

  data_sub["speech_reason"] = speech_reason

  prompt_template = "persona/prompt_template/templates/generate_next_convo_line_normal.txt"
  prompt = read_prompt_template(prompt_template)
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
    "table_time_left": data['table_time_left'],
    "all_table_time_left": data['all_table_time_left'],
    "total_time_left": data['total_time_left'],
  }

  data_sub["special_circumstance"] = special_circumstance

  prompt_template = "persona/prompt_template/templates/generate_next_convo_line_special.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  #print(output)
  
  if output != False: 
    return output, [output, prompt, data]

def run_gpt_prompt_act_bidding_ability(persona, table, test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_ability.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_act_bidding_reveal(persona, table, test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_reveal.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def get_bidding_common_data(persona, table):
  retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = persona.scratch.retrieved
  seen_context_descriptions = set()

  def context_key(description):
    return " ".join(str(description or "").split())

  def claim_context(description, aliases=None):
    keys = [context_key(description)]
    if aliases:
      keys.extend(context_key(alias) for alias in aliases)
    keys = [key for key in keys if key]
    if not keys or any(key in seen_context_descriptions for key in keys):
      return False
    seen_context_descriptions.update(keys)
    return True

  def format_memory_line(node, indent="", include_chat_table=False):
    time_ago = timedelta_to_natural(persona.scratch.curr_time - node.created)
    if node.type == "chat":
      table_text = f" at the {node.table} table" if include_chat_table else ""
      return f"{indent}({time_ago} ago){node.description}{table_text}\n"
    if node.type == "thought":
      return f"{indent}I came to the conclusion {time_ago} ago: {node.description}\n"
    return f"{indent}({time_ago} ago){node.description} at the {node.table} table\n"

  recent_conversation = ""
  for timestamp_dict in persona.scratch.recent_conversation:
    timestamp, timestamp_events = timestamp_dict
    for event in timestamp_events:
      if not claim_context(event.description):
        continue
      recent_conversation += format_memory_line(event, include_chat_table=True)
  if not recent_conversation:
    recent_conversation = "No dialogue or table events have been perceived yet.\n"

  current_table_events_lines = []
  for event_desc in retrieved_self.keys():
    if claim_context(event_desc):
      current_table_events_lines.append(event_desc)
  current_table_events = ""
  if current_table_events_lines:
    current_table_events = "And right now the latest activities at the table are:\n"
    for event_desc in current_table_events_lines:
      current_table_events += event_desc.rstrip() + "\n"

  current_table_context = ""
  dict = retrieved_all_tables[persona.scratch.curr_loc]
  new_line = f"Players currently seated at your table, the {persona.scratch.curr_loc}:\n"      
  current_table_context += new_line
  for other_player, other_player_dict in dict.items():
    current_table_context += f"\t{other_player}\n"
    current_table_context += f"\tRelevant events:\n"
    for event in other_player_dict["events"]:
      if claim_context(event.description):
        current_table_context += format_memory_line(event, "\t\t")
    current_table_context += f"\tRelevant thoughts:\n"
    for thought in other_player_dict["thoughts"]:
      if claim_context(thought.description):
        current_table_context += format_memory_line(thought, "\t\t")
  personal_context_msg = persona.get_personal_game_context()
  if persona.scratch.curr_time == datetime.timedelta(0):
    personal_context_msg += "\nThe game has only JUST started and barely anyone has said or done anything yet.\n"
  ability_msg = ability_trigger(persona, table)
  #retrieved_lines_related: {line_content: list of event nodes, line_2_content: list of event nodes, etc.}
  current_table_additional_lines = []
  for line, line_event_list in self_retrieved_lines_related.items():
    for event in line_event_list:
      if claim_context(event.description):
        current_table_additional_lines.append(format_memory_line(event, "\t"))
  current_table_additional_context = ""
  if current_table_additional_lines:
    current_table_additional_context = "At this moment, the conversation also just happens to remind you that:\n"
    current_table_additional_context += "".join(current_table_additional_lines)

  other_table_additional_context = ""
  if other_retrieved_lines_related:
    other_table_additional_lines = []
    for line_with_table_info, event_list in other_retrieved_lines_related.items():
      raw_line = line_with_table_info.split(") ", 1)[1] if line_with_table_info.startswith("(From table ") and ") " in line_with_table_info else line_with_table_info
      if claim_context(line_with_table_info, aliases=[raw_line]):
        other_table_additional_lines.append(line_with_table_info.rstrip() + "\n")
      reminder_lines = []
      for event in event_list:
        if claim_context(event.description):
          reminder_lines.append(format_memory_line(event, "\t"))
      if reminder_lines:
        other_table_additional_lines.append("This also reminds you that:\n")
        other_table_additional_lines.extend(reminder_lines)
    if other_table_additional_lines:
      other_table_additional_context = "Suddenly you also hear loud commotion from other tables:\n"
      other_table_additional_context += "".join(other_table_additional_lines)

  table_time_left = timedelta_to_natural(TIMERS[persona.scratch.curr_loc] - persona.scratch.curr_time)
  all_table_time_left = "\n".join(
    f"- {table_name}: {timedelta_to_natural(TIMERS[table_name] - persona.scratch.curr_time)} until players there can no longer leave"
    for table_name in TIMERS.keys()
  )
  total_time_left = timedelta_to_natural(game_end_time() - persona.scratch.curr_time)
      
  lockdown_matches = [t for t in table.lockdown_targets if t[1] == persona.scratch.name]
  if not lockdown_matches: # not under influence of abilities rn
    stay_at_table_reason = "you're staying at the table with no rush of going anywhere now"
  else:
    captor_roles = [t[2] for t in lockdown_matches]
    captor_roles = "'s and ".join(captor_roles)
    stay_at_table_reason = f"you're forced to stay due to {captor_roles}'s abilities"

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
    "table_time_left": table_time_left,
    "all_table_time_left": all_table_time_left,
    "total_time_left": total_time_left,
  }

  return data
  


def run_gpt_prompt_act_bidding_speak(persona, table, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_speaking.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  


def run_gpt_prompt_decide_on_leaving(persona, table, retrieved_all_tables, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  external_table_context = ""
  for table_name, dict in retrieved_all_tables.items():
    table_timer_left = timedelta_to_natural(TIMERS[table_name] - persona.scratch.curr_time)
    new_line = f"Players currently seated at the {table_name} table ({table_timer_left} until players there can no longer leave):"
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
  all_table_time_left = "\n".join(
    f"- {table_name}: {timedelta_to_natural(TIMERS[table_name] - persona.scratch.curr_time)} until players there can no longer leave"
    for table_name in retrieved_all_tables.keys()
  )
  total_time_left = timedelta_to_natural(game_end_time() - persona.scratch.curr_time)

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
  if not recent_conversation:
    recent_conversation = "No dialogue or table events have been perceived yet.\n"

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": personal_context_msg,
    "external_table_context": external_table_context,
    "ability_msg": ability_msg,
    "recent_conversation": recent_conversation,
    "current_table": current_table,
    "other_options": other_options,
    "table_time_left": table_time_left,
    "all_table_time_left": all_table_time_left,
    "total_time_left": total_time_left,
    "options": options
  }

  prompt_template = "persona/prompt_template/templates/decide_on_moving.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_select_ability_target(persona, table, ability_reasoning="", test_input=None, verbose=False): 
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
  elif persona.scratch.role == "Spinster" or persona.scratch.role == "Queen" or persona.scratch.role == "Bishop":
    ability_target_info += f"as {persona.scratch.role}, you can select one of the players present at the table as target:\n"
    target_options = ", ".join(list(set(table.personas.keys()) - {persona.scratch.name}))
    ability_target_info += target_options
  ability_reasoning_msg = ""
  if ability_reasoning:
    ability_reasoning_msg = (
      "When deciding to use this ability, your reasoning was:\n"
      f"{ability_reasoning}\n"
      "Use this as optional context for target selection.\n"
    )
  if persona.scratch.role == "Spinster":
    ability_reasoning_msg += (
      "Important Spinster rule: your forced reveal only works if the target still has their own role card. "
      "If your memories strongly indicate someone no longer has their own card, consider that when choosing a target; "
      "if you do not know, you may still designate them and the failure will only become clear after you leave.\n"
    )

  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "ability_target_info": ability_target_info,
    "ability_reasoning": ability_reasoning_msg,
  }
  prompt_template = "persona/prompt_template/templates/select_ability_target.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_guess_family_bishop(persona, target, table, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  families = sorted({role_data["family"] for role_data in ROLE_DICT.values()})
  ability_target_info = (
    f"as Bishop, you are guessing {target.scratch.name}'s family. "
    f"Choose exactly one of these families: {', '.join(families)}"
  )

  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "ability_target_info": ability_target_info
  }
  prompt_template = "persona/prompt_template/templates/guess_family_bishop.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    if "guess" not in output and "target" in output:
      output["guess"] = output["target"]
    return output, [output, prompt, data_sub]


def run_gpt_prompt_spinster_endgame_guess(persona, table, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  targets = [name for name in table.personas if name != persona.scratch.name]
  target_list = "\n".join(f"- {name}" for name in targets) or "- No other players at your table."
  role_options = " | ".join(ROLE_DICT.keys())
  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "current_table_events": data["current_table_events"],
    "current_table_additional_context": data["current_table_additional_context"],
    "other_table_additional_context": data["other_table_additional_context"],
    "target_list": target_list,
    "role_options": role_options,
  }
  prompt_template = "persona/prompt_template/templates/spinster_endgame_guess.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data_sub]


def run_gpt_prompt_decide_baron_block(persona, table, revealed_player, action_context, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "current_table_events": data["current_table_events"],
    "current_table_additional_context": data["current_table_additional_context"],
    "other_table_additional_context": data["other_table_additional_context"],
    "stay_at_table_reason": data["stay_at_table_reason"],
    "table_time_left": data["table_time_left"],
    "total_time_left": data["total_time_left"],
    "revealed_player_name": revealed_player.scratch.name,
    "revealed_player_role": revealed_player.scratch.role,
    "action_context": action_context,
  }
  prompt_template = "persona/prompt_template/templates/decide_baron_block.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data_sub]


def run_gpt_prompt_decide_innkeeper_declaration(persona, table, source_table, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  movement_reasoning = persona.scratch.current_movement_reasoning or ""
  movement_reasoning_msg = ""
  if movement_reasoning and persona.scratch.current_movement_destination == "Village":
    movement_reasoning_msg = (
      "When you independently decided to move to the Village, your reasoning was:\n"
      f"{movement_reasoning}\n"
      "Use this as optional context, but decide the Innkeeper declaration based on the current board.\n"
    )
  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "current_table_events": data["current_table_events"],
    "current_table_additional_context": data["current_table_additional_context"],
    "other_table_additional_context": data["other_table_additional_context"],
    "table_time_left": data["table_time_left"],
    "total_time_left": data["total_time_left"],
    "source_table": source_table,
    "movement_reasoning": movement_reasoning_msg,
  }
  prompt_template = "persona/prompt_template/templates/decide_innkeeper_declaration.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data_sub]


def run_gpt_prompt_decide_movement_ability_use(persona, table, destination, movement_reasoning, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  role = persona.scratch.role
  if role == "Queen":
    ability_description = (
      "As Queen, when you leave a table you may reveal your Queen card, choose one player, "
      "and force that player to follow you to the new table."
    )
  elif role == "Spinster":
    ability_description = (
      "As Spinster, when you leave the Forest you may reveal your Spinster card, point to one player still in the Forest, "
      "and force that player to reveal their role card to the Forest after you leave."
    )
  else:
    ability_description = "This role does not have a movement-triggered ability."
  target_options = ", ".join(list(set(table.personas.keys()) - {persona.scratch.name}))
  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "current_table_events": data["current_table_events"],
    "current_table_additional_context": data["current_table_additional_context"],
    "other_table_additional_context": data["other_table_additional_context"],
    "table_time_left": data["table_time_left"],
    "total_time_left": data["total_time_left"],
    "role": role,
    "destination": destination,
    "movement_reasoning": movement_reasoning or "I did not have a detailed movement reason recorded.",
    "ability_description": ability_description,
    "target_options": target_options,
  }
  prompt_template = "persona/prompt_template/templates/decide_movement_ability_use.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data_sub)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data_sub]



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
  ability_departure_reasoning = (persona.scratch.current_bidding_reasonings or {}).get("ability", "")
  ability_departure_reasoning_msg = ""
  if ability_departure_reasoning:
    ability_departure_reasoning_msg = (
      "When you decided to bid for this ability, your reasoning was:\n"
      f"{ability_departure_reasoning}\n"
      "Use this as optional context for why you are leaving, but update your destination choice based on the current board.\n"
    )

  table_time_left = timedelta_to_natural(TIMERS[persona.scratch.curr_loc] - persona.scratch.curr_time)
  total_time_left = timedelta_to_natural(game_end_time() - persona.scratch.curr_time)

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
    "ability_departure_reasoning": ability_departure_reasoning_msg,
    "recent_conversation": recent_conversation,
    "other_options": other_options,
    "table_time_left": table_time_left,
    "total_time_left": total_time_left,
    "options": options
  }

  prompt_template = "persona/prompt_template/templates/select_ability_destination.txt"
  prompt = read_prompt_template(prompt_template)
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
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_reflect_on_subject(persona, subject_events, subject_thoughts, focal_point, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  data = dict()
  subject_event_details = ""
  for event in subject_events.get(focal_point, []):
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

  data = {"PREFIX": PREFIX,
       "subject_thought_details":subject_thought_details,
       "subject_event_details":subject_event_details,
       "question":focal_point}
  prompt_template = "persona/prompt_template/templates/reflect_person_personality.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_reflect_on_board_state(persona, focal_retrievals, prior_board_thoughts, test_input=None, verbose=False):
  focal_retrieval_details = ""
  for focal_point, nodes in focal_retrievals.items():
    focal_retrieval_details += f"\nQuestion: {focal_point}\n"
    if not nodes:
      focal_retrieval_details += "- No retrieved evidence.\n"
      continue
    for node in nodes:
      time_ago = timedelta_to_natural(persona.scratch.curr_time - node.created)
      table_text = f" at the {node.table} table" if node.table else ""
      focal_retrieval_details += f"- ({time_ago} ago) [{node.type}] {node.description}{table_text}\n"

  prior_thought_details = ""
  for thought in prior_board_thoughts:
    time_ago = timedelta_to_natural(persona.scratch.curr_time - thought.created)
    prior_thought_details += f"- ({time_ago} ago) {thought.description}\n"
  if not prior_thought_details:
    prior_thought_details = "No prior board-state thoughts.\n"

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": persona.get_personal_game_context(),
    "prior_thought_details": prior_thought_details,
    "focal_retrieval_details": focal_retrieval_details,
  }
  prompt_template = "persona/prompt_template/templates/reflect_board_state.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**data)

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data]
