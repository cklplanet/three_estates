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
from localization import (
  localized_prompt_data,
  localized_prompt_path,
  prompt_language_instruction,
  validate_localized_natural_language_fields,
)
from persona.prompt_template.gpt_structure import *
# from persona.prompt_template.print_prompt import *


def read_prompt_template(prompt_template):
  with open(localized_prompt_path(prompt_template), "r", encoding="utf-8") as f:
    prompt = f.read()
  language_instruction = prompt_language_instruction()
  if language_instruction:
    return f"{language_instruction}\n\n{prompt}"
  return prompt


def json_cleanup(output):
  start = output.find('{')
  end = output.rfind('}') + 1   # +1 to include the last }

  if start == -1 or end == -1:
      raise ValueError("No JSON object found in output")

  json_str = output[start:end]
  try:
    return json.loads(json_str)
  except json.JSONDecodeError:
    parsed = ast.literal_eval(json_str)
    if not isinstance(parsed, dict):
      raise ValueError("Parsed LLM output is not a dictionary")
    return parsed


def localized_dialogue_json_cleanup(output):
  return validate_localized_natural_language_fields(json_cleanup(output))


def text_cleanup(output):
  return output.strip()


def game_summary_epilogue_cleanup(output):
  summary_start = "<game_summary>"
  summary_end = "</game_summary>"
  epilogue_start = "<vn_epilogue>"
  epilogue_end = "</vn_epilogue>"
  if not all(marker in output for marker in (summary_start, summary_end, epilogue_start, epilogue_end)):
    raise ValueError("Combined game-summary/epilogue response is missing a required section marker")
  summary = output.split(summary_start, 1)[1].split(summary_end, 1)[0].strip()
  epilogue = output.split(epilogue_start, 1)[1].split(epilogue_end, 1)[0].strip()
  if not summary or not epilogue:
    raise ValueError("Combined game-summary/epilogue response contains an empty section")
  return {"game_summary": summary, "vn_epilogue": epilogue}


def latest_table_line_reminder(persona, table):
  for utterance in reversed(getattr(table, "dialogue_history", [])):
    speaker, target, volume, expression, action, line, _timestamp, audience, _keywords = unpack_dialogue_fields(utterance)
    if audience and persona.scratch.name not in audience:
      continue
    target = target or "everyone"
    return (
      f"{speaker} -> {target} [{volume}, {expression}]: "
      f"{format_dialogue_payload(action, line)}"
    )
  return "none yet"


def movement_duration_hint(persona=None):
  endgame_mode = bool(persona and getattr(persona.room, "endgame_mode", False))
  if endgame_mode:
    return (
      f"Endgame timing note: two tables are locked, so every departure, bidding, and arrival phase now advances "
      f"the timer by {ENDGAME_SECONDS_PER_PHASE} seconds each. Physically moving to another table therefore takes "
      f"about {2 * ENDGAME_SECONDS_PER_PHASE} seconds across the departure and bidding phases before arrival resolves. "
      "However, even if the game has less time remaining than that -- including less than one second -- a confirmed "
      "departure still reaches its chosen destination through the final-arrival flush before results are calculated. "
      "You WILL be seated at the destination for endgame resolution and cannot lose merely by being caught in transit."
    )
  return (
    f"Physically moving from one table to another takes {2 * SIM_SECONDS_PER_STEP} seconds total (but the game timer having less than that left, even less than one second, STILL counts as you being able to make it to your final destination table 'in time'. You WILL have a table in the end if this happens, so don't worry about being 'caught in transit'). \n"
    f"If you stay here then you implicitly commit to staying for at least around {2 * MOVEMENT_STAY_COOLDOWN_STEPS * SIM_SECONDS_PER_STEP} more seconds; and if you move then you implicitly commit to staying at your destination for at least around {2 * MOVEMENT_LEAVE_COOLDOWN_STEPS * SIM_SECONDS_PER_STEP} seconds."
  )


def format_table_lockdown_status(table, persona_name=None, indent=""):
  king_locks_targeting_persona = []
  king_locks_maintained_by_persona = {}
  visible_locks = []
  def king_target_family(target):
    target_persona = getattr(table, "personas", {}).get(target)
    if not target_persona:
      return "unknown family"
    return ROLE_DICT.get(target_persona.scratch.role, {}).get("family", "unknown family")
  for benefactor, target, role in table.lockdown_targets:
    if role == "King":
      target_family = king_target_family(target)
      if persona_name and target == persona_name:
        king_locks_targeting_persona.append((benefactor, target, role, target_family))
      elif persona_name and benefactor == persona_name:
        king_locks_maintained_by_persona.setdefault((benefactor, role), set()).add(target_family)
      elif persona_name is None:
        king_locks_maintained_by_persona.setdefault((benefactor, role), set()).add(target_family)
      continue
    if persona_name is None or persona_name in {benefactor, target}:
      visible_locks.append((benefactor, target, role))

  if king_locks_targeting_persona:
    lines = [f"{indent}Player-imposed lockdowns involving you or maintained by you:\n"]
    for benefactor, _target, role, target_family in sorted(king_locks_targeting_persona, key=lambda item: (str(item[0]), str(item[2]), str(item[3]))):
      lines.append(
        f"{indent}- {benefactor}'s {role} ability currently prevents the {target_family} family, including you, from leaving this table. "
        "Other affected players, if any, are not listed here.\n"
      )
    return "".join(lines)

  if king_locks_maintained_by_persona:
    lines = [f"{indent}Player-imposed lockdowns involving you or maintained by you:\n"]
    for (benefactor, role), families in sorted(king_locks_maintained_by_persona.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
      family_text = ", ".join(sorted(families))
      if persona_name and benefactor == persona_name:
        lines.append(
          f"{indent}- Your {role} ability is maintaining a snapshot lockdown against one or more originally present {family_text} player(s) at this table. "
          "The affected players are not listed here. Do not assume every currently seated member of that family is locked; same-family players who arrived after your declaration were not caught by it.\n"
        )
      else:
        lines.append(
          f"{indent}- {benefactor}'s {role} ability is maintaining a snapshot lockdown against one or more originally present {family_text} player(s) at this table. "
          "The affected players are not listed here. Do not assume every currently seated member of that family is locked; same-family players who arrived after the declaration were not caught by it.\n"
        )

  if not visible_locks and not king_locks_maintained_by_persona:
    if persona_name and persona_name in getattr(table, "personas", {}):
      return (
        f"{indent}AUTHORITATIVE CURRENT PLAYER-IMPOSED LOCKDOWN STATUS FOR YOU: NONE. "
        "No active King, Queen, or Innkeeper lock currently prevents you from leaving this table. "
        "Any memory or prior reasoning saying you are trapped by an older player-imposed lock is outdated and must not be treated as current. "
        "You are free to leave subject only to the table timer and normal movement rules.\n"
      )
    return f"{indent}Player-imposed lockdowns involving you or maintained by you at this table: none.\n"
  if visible_locks and not king_locks_maintained_by_persona:
    lines = [f"{indent}Player-imposed lockdowns involving you or maintained by you:\n"]
  for benefactor, target, role in sorted(visible_locks, key=lambda item: (str(item[2]), str(item[0]), str(item[1]))):
    if benefactor == target:
      self_note = " The lock-holder is free to move under this lock."
    elif persona_name and target == persona_name:
      self_note = " This lock currently applies to you."
    elif persona_name and benefactor == persona_name:
      self_note = " You are maintaining this lock."
    else:
      self_note = ""
    lines.append(
      f"{indent}- {benefactor}'s {role} ability is keeping {target} from leaving this table.{self_note}\n"
    )
  return "".join(lines)


def format_transit_status(room, curr_time, indent=""):
  if not getattr(room, "transit", None):
    return f"{indent}Players currently in transit between tables: none.\n"
  lines = [f"{indent}Players currently in transit between tables; they have left their source table but have not arrived yet:\n"]
  for name, data in sorted(room.transit.items()):
    since = data.get("since", curr_time)
    if hasattr(since, "total_seconds"):
      time_ago = timedelta_to_natural(curr_time - since)
    else:
      time_ago = "some time"
    benefactor = data.get("benefactor")
    forced = f" due to {benefactor}'s ability" if benefactor else ""
    lines.append(
      f"{indent}- {name}: from {data.get('source')} toward {data.get('destination')}{forced}; departed {time_ago} ago.\n"
    )
  return "".join(lines)


def format_transit_memory_context(persona, claim_node=None, indent=""):
  if TRANSIT_PERSON_MEMORY_CAP <= 0 or not getattr(persona.room, "transit", None):
    return ""

  lines = []
  for transit_name in sorted(persona.room.transit):
    candidates = set()
    candidates.update(persona.a_mem.retrieve_relevant_events(transit_name, None))
    candidates.update(persona.a_mem.retrieve_relevant_events(None, transit_name))
    candidates.update(persona.a_mem.retrieve_relevant_thoughts(transit_name, None))
    candidates.update(persona.a_mem.retrieve_relevant_thoughts(None, transit_name))
    candidates = [
      node for node in candidates
      if node.type in {"event", "thought"}
      and node.created is not None
      and node.created < persona.scratch.curr_time
    ]
    candidates = sorted(
      candidates,
      key=lambda node: (
        getattr(node, "poignancy", 0),
        node.created,
        getattr(node, "last_accessed", node.created) or node.created,
        getattr(node, "node_count", 0),
      ),
      reverse=True,
    )

    memory_lines = []
    for node in candidates:
      if claim_node is not None and not claim_node(node):
        continue
      time_ago = timedelta_to_natural(persona.scratch.curr_time - node.created)
      if node.type == "thought":
        memory_lines.append(
          f"{indent}\t- Past private thought from {time_ago} ago, not necessarily current: {node.description}\n"
        )
      else:
        table_text = f" at the {node.table} table" if node.table else ""
        memory_lines.append(
          f"{indent}\t- Past event memory from {time_ago} ago, not necessarily current: {node.description}{table_text}\n"
        )
      if len(memory_lines) >= TRANSIT_PERSON_MEMORY_CAP:
        break
    if memory_lines:
      lines.append(
        f"{indent}Your own limited event/thought memories about transit player {transit_name} "
        f"(up to {TRANSIT_PERSON_MEMORY_CAP}; these are history, not live transit actions):\n"
      )
      lines.extend(memory_lines)
  return "".join(lines)


def format_authoritative_occupancy_snapshot(room):
  lines = ["AUTHORITATIVE PHYSICAL OCCUPANCY NOW:\n"]
  for table_name, table in room.locations.items():
    seated_names = sorted(table.personas)
    seated_count = len(seated_names)
    if seated_names:
      player_word = "player" if seated_count == 1 else "players"
      seated_labels = [
        visual_character_label(table.personas[name])
        for name in seated_names
      ]
      lines.append(
        f"- {table_name}: {seated_count} seated {player_word} -- {'; '.join(seated_labels)}\n"
      )
    else:
      lines.append(f"- {table_name}: 0 seated players -- no seated players\n")
  transit_names = sorted(getattr(room, "transit", {}).keys())
  transit_text = ", ".join(transit_names) if transit_names else "none"
  lines.extend([
    f"- Transit (not seated at any table): {transit_text}\n",
    "This snapshot is the mechanically authoritative current board state. "
    "A table is empty only when its count is exactly 0 and it explicitly says 'no seated players.' "
    "Never remove, relocate, or discount a listed player based on remembered dialogue, past events, suspected movement, "
    "or your interpretation of where they should be. Historical memories cannot override this snapshot.\n",
  ])
  return "".join(lines)


def format_endgame_board_context(persona, retrieved_all_tables, format_memory_line, claim_node):
  if not getattr(persona.room, "endgame_mode", False):
    return ""
  lines = [
    "ENDGAME BOARD AWARENESS: two tables are locked, so you are now tracking the final-table shape across the board. "
    "This is membership and your relevant memories only, not live dialogue from those tables.\n"
  ]
  for table_name, table_dict in retrieved_all_tables.items():
    if table_name == persona.scratch.curr_loc:
      continue
    table_status = table_leave_timer_status(table_name, persona.scratch.curr_time)
    lines.append(f"- {table_name} ({table_status})\n")
    if not table_dict:
      lines.append("\tNo players currently seated there.\n")
      continue
    for player_name, player_dict in table_dict.items():
      lines.append(f"\t{visual_character_label_by_name(persona.room, player_name)}\n")
      event_lines = []
      for event in player_dict.get("events", []):
        if claim_node(event):
          event_lines.append(format_memory_line(event, "\t\t"))
      if event_lines:
        lines.append("\t\tRelevant past events:\n")
        lines.extend(event_lines)
      thought_lines = []
      for thought in player_dict.get("thoughts", []):
        if claim_node(thought):
          thought_lines.append(format_memory_line(thought, "\t\t"))
      if thought_lines:
        lines.append("\t\tRelevant past thoughts:\n")
        lines.extend(thought_lines)
  return "".join(lines)


def build_stay_at_table_reason(persona, table, extra_reasons=None):
  base = persona.scratch.current_movement_reasoning
  if base:
    reasons = [f"your intent for being at this table is: {base}"]
  else:
    reasons = ["you're staying at the table with no rush of going anywhere now"]

  lockdown_matches = [t for t in table.lockdown_targets if t[1] == persona.scratch.name]
  if lockdown_matches:
    captors = ", ".join(f"{benefactor}'s {role}" for benefactor, _target, role in lockdown_matches)
    reasons.append(f"you are currently forced to stay by {captors}")
  else:
    reasons.append(
      "authoritative current correction: no active player-imposed lockdown affects you at this table; "
      "if the stored intent above says an older King, Queen, or Innkeeper lock still traps you, that part is outdated"
    )

  for reason in extra_reasons or []:
    if reason:
      reasons.append(reason)
  return "; and ".join(reasons)


def run_gpt_prompt_generate_character_names(character_group_context, cast_size, existing_names=None, test_input=None, verbose=False):
  existing_names = list(existing_names or [])
  data = {
    "character_group_context": character_group_context,
    "cast_size": cast_size,
    "existing_names": json.dumps(existing_names, ensure_ascii=False),
  }
  prompt_template = "persona/prompt_template/templates/generate_character_names.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  def character_names_cleanup(output):
    parsed = json_cleanup(output)
    names = parsed.get("names")
    if not isinstance(names, list) or len(names) != cast_size:
      raise ValueError(
        f"Character roster must contain exactly {cast_size} names"
      )
    cleaned_names = [str(name or "").strip() for name in names]
    if any(not name for name in cleaned_names):
      raise ValueError("Character roster contains an empty name")
    if len({name.casefold() for name in cleaned_names}) != cast_size:
      raise ValueError("Character roster names must be unique")
    if cleaned_names[:len(existing_names)] != existing_names:
      raise ValueError(
        "Character roster did not preserve already committed names in order"
      )
    return {"names": cleaned_names}

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=character_names_cleanup,
    model=CHARACTER_GENERATION_LLM_MODEL,
  )
  if output != False:
    return output, [output, prompt, data]


def run_gpt_prompt_generate_character(character_group_context, fixed_name, full_roster, test_input=None, verbose=False):
  data = {
    "character_group_context": character_group_context,
    "fixed_name": fixed_name,
    "full_roster": json.dumps(list(full_roster), ensure_ascii=False),
  }
  prompt_template = "persona/prompt_template/templates/generate_persona.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup, model=CHARACTER_GENERATION_LLM_MODEL)
  #print(output) #debug
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_generate_innate_appearance(persona, character_group_context, test_input=None, verbose=False):
  data = {
    "character_group_context": character_group_context,
    "name": persona.scratch.name,
    "gender": persona.scratch.gender,
    #"age": persona.scratch.age,
    "innate": persona.scratch.innate,
  }
  prompt = read_prompt_template("persona/prompt_template/templates/generate_innate_appearance.txt")
  final_prompt = prompt.format(**localized_prompt_data(data))
  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=json_cleanup,
    model=CHARACTER_GENERATION_LLM_MODEL,
  )
  if output != False:
    return output, [output, prompt, data]


def run_gpt_prompt_generate_clothing(persona, character_group_context, test_input=None, verbose=False):
  if isinstance(persona, dict):
    profile = persona
  else:
    profile = {
      "name": persona.scratch.name,
      "gender": persona.scratch.gender,
      "age": persona.scratch.age,
      "innate": persona.scratch.innate,
      "innate_appearance": persona.scratch.innate_appearance,
    }
  data = {
    "character_group_context": character_group_context,
    "name": profile.get("name", "Unknown"),
    "gender": profile.get("gender", "unknown"),
    "age": profile.get("age", "unknown"),
    "innate": profile.get("innate", ""),
    "innate_appearance": profile.get("innate_appearance", ""),
  }
  prompt = read_prompt_template("persona/prompt_template/templates/generate_clothing.txt")
  final_prompt = prompt.format(**localized_prompt_data(data))
  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=json_cleanup,
    model=CHARACTER_GENERATION_LLM_MODEL,
  )
  if output != False:
    return output, [output, prompt, data]


def run_gpt_prompt_assign_immersion_roles(character_group_context, character_profiles, role_pool_text, role_rulebook, test_input=None, verbose=False):
  data = {
    "character_group_context": character_group_context,
    "character_profiles": character_profiles,
    "role_pool_text": role_pool_text,
    "role_rulebook": role_rulebook,
  }

  prompt_template = "persona/prompt_template/templates/assign_immersion_roles.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup, model=CHARACTER_GENERATION_LLM_MODEL)
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
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=text_cleanup, model=CHARACTER_GENERATION_LLM_MODEL)
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_select_relationship_pairs(character_group_context, cast_information, min_pairs, max_pairs, test_input=None, verbose=False):
  data = {
    "character_group_context": character_group_context,
    "cast_information": cast_information,
    "min_pairs": min_pairs,
    "max_pairs": max_pairs,
  }

  prompt_template = "persona/prompt_template/templates/select_relationship_pairs.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup, model=CHARACTER_GENERATION_LLM_MODEL)
  if output != False:
    return output, [output, prompt, data]


def run_gpt_prompt_generate_vn_epilogue(
  epilogue_context,
  line_count_instruction="Write 50 to 60 actual scene entries; blank separator lines and wrapper tags do not count.",
  test_input=None,
  verbose=False,
):
  data = {
    "PREFIX": PREFIX,
    "epilogue_context": epilogue_context,
    "line_count_instruction": line_count_instruction,
  }
  prompt_template = "persona/prompt_template/templates/generate_vn_epilogue.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=text_cleanup, model=EPILOGUE_GENERATION_LLM_MODEL)
  if output != False:
    return output, [output, prompt, data]


def run_gpt_prompt_generate_game_summary_and_vn_epilogue(
  epilogue_context,
  line_count_instruction="Write 50 to 60 actual scene entries; blank separator lines and wrapper tags do not count.",
  test_input=None,
  verbose=False,
):
  data = {
    "PREFIX": PREFIX,
    "epilogue_context": epilogue_context,
    "line_count_instruction": line_count_instruction,
  }
  prompt_template = "persona/prompt_template/templates/generate_game_summary_and_vn_epilogue.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=game_summary_epilogue_cleanup,
    model=EPILOGUE_GENERATION_LLM_MODEL,
  )
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
    "latest_table_line_reminder": data['latest_table_line_reminder'],
    "current_table_events": data['current_table_events'],
    "current_table_additional_context": data['current_table_additional_context'],
    "stay_at_table_reason": data['stay_at_table_reason'],
    "table_time_left": data['table_time_left'],
    "all_table_time_left": data['all_table_time_left'],
    "total_time_left": data['total_time_left'],
    "conversation_posture": data['conversation_posture'],
  }

  speech_reason = persona.scratch.act_reasoning

  data_sub["speech_reason"] = speech_reason

  prompt_template = "persona/prompt_template/templates/generate_next_convo_line_normal.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=localized_dialogue_json_cleanup,
    model=DIALOGUE_GENERATION_LLM_MODEL,
    reasoning_effort=None if ALLOW_SPEECH_REASONING else "none",
  )
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
    "latest_table_line_reminder": data['latest_table_line_reminder'],
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
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=localized_dialogue_json_cleanup,
    model=DIALOGUE_GENERATION_LLM_MODEL,
    reasoning_effort=None if ALLOW_SPEECH_REASONING else "none",
  )
  #print(output)
  
  if output != False: 
    return output, [output, prompt, data]



def run_gpt_prompt_chat_poignancy(persona, chat, test_input=None, verbose=False): 
  personal_game_context = persona.get_personal_game_context()
  data = {"PREFIX": PREFIX,
          "personal_game_context":personal_game_context,
          "current_line":chat}

  prompt_template = (
    "persona/prompt_template/templates/poignancy_chat_casual.txt"
    if casual_conversation_active(persona)
    else "persona/prompt_template/templates/poignancy_chat.txt"
  )
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=int,
    model=POIGNANCY_SCORING_LLM_MODEL,
    reasoning_effort="none",
  )
  #print("chat poignancy output: --->>>", output)
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_event_poignancy(persona, event_description, test_input=None, verbose=False): 
  personal_game_context = persona.get_personal_game_context()
  data = {"PREFIX": PREFIX,
          "personal_game_context":personal_game_context,
          "event_desp":event_description}

  prompt_template = "persona/prompt_template/templates/poignancy_event.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=int,
    model=POIGNANCY_SCORING_LLM_MODEL,
    reasoning_effort="none",
  )
  #print("event poignancy output: --->>>", output)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_thought_poignancy(persona, thought_description, test_input=None, verbose=False): 
  personal_game_context = persona.get_personal_game_context()
  data = {"PREFIX": PREFIX,
          "personal_game_context":personal_game_context,
          "thought_desp":thought_description}

  prompt_template = "persona/prompt_template/templates/poignancy_thought.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=json_cleanup,
    model=POIGNANCY_SCORING_LLM_MODEL,
    reasoning_effort="none",
  )
  
  if output != False: 
    return output, [output, prompt, data]
  


def run_gpt_prompt_act_bidding_ability(persona, table, action_context="", test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table, action_context=action_context)
  if persona.scratch.role == "Innkeeper":
    data["ability_bid_action_clarification"] = (
      "For Innkeeper specifically, bidding for your ability here means bidding to leave your current table for the Village, "
      "no matter where you currently are outside the Village. You are NOT required to reveal your role or card at the departure table (unless you choose to verbally, non-bindingly do so at the departure table); "
      "the real Innkeeper reveal/declaration, if you choose to make it, happens only after you arrive at the Village."
    )
  elif persona.scratch.role == "King":
    data["ability_bid_action_clarification"] = (
      "For King specifically, your ability is a snapshot of players physically seated at your current table right now. "
      "It can only lock already-present members of the chosen family. It does NOT trap people currently in transit, people you expect to arrive later, or people at other tables; later arrivals are unaffected and may leave normally unless you use the ability again after they are seated. "
      "If you already have a King lockdown active, do not infer that every currently seated member of the locked family is affected; only the original hidden targets from the moment of declaration are locked, and later arrivals of that family may still be free. "
      "Bid for this only if locking currently seated people is useful on its own."
    )
  else:
    data["ability_bid_action_clarification"] = (
      "For this prompt in particular, you want to for now decide that, if simply talking alone can't help you achieve your goals, "
      "how urgently you want to use your ability (and in the process reveal your role at everyone at your current table) to the conversation in particular. "
      "For the chance to reveal your card and role next you will place a bid. Highest bidder speaks or acts first."
    )
  if persona.scratch.role in {"Queen", "Spinster"}:
    data["ability_bid_action_clarification"] += f" Timing note for this movement-based ability: {movement_duration_hint(persona)}"

  prompt_template = "persona/prompt_template/templates/reaction_bidding_ability.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_act_bidding_reveal(persona, table, action_context="", test_input=None, verbose=False): 
  data = get_bidding_common_data(persona, table, action_context=action_context)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_reveal.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_act_bidding_nun_reveal(persona, table, action_context="", test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table, action_context=action_context)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_nun_reveal.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)

  if output != False:
    return output, [output, prompt, data]


def run_gpt_prompt_act_bidding_unified(persona, table, action_options, action_context="", test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table, action_context=action_context)
  if persona.scratch.role == "Innkeeper":
    data["ability_bid_action_clarification"] = (
      "For Innkeeper specifically, choosing ability here means choosing to leave your current table for the Village, "
      "no matter where you currently are outside the Village. You are NOT required to reveal your role or card at the departure table; "
      "the real Innkeeper reveal/declaration, if you choose to make it, happens only after you arrive at the Village."
    )
  elif persona.scratch.role == "King":
    seated_names = ", ".join(sorted(table.personas)) or "none"
    transit_names = ", ".join(sorted(getattr(persona.room, "transit", {}))) or "none"
    data["ability_bid_action_clarification"] = (
      "For King specifically, your ability is a snapshot of players physically seated at your current table right now. "
      "It can only lock already-present members of the chosen family. It does NOT trap people currently in transit, people you expect to arrive later, or people at other tables. "
      f"AUTHORITATIVE CURRENT SEATED SNAPSHOT ELIGIBLE FOR THIS ACTIVATION: {seated_names}. "
      f"EXPLICITLY INELIGIBLE BECAUSE THEY ARE IN TRANSIT, EVEN IF THEY ARRIVE IMMEDIATELY AFTER THIS ACTION: {transit_names}. "
      "Score the ability only for what locking the already-seated snapshot accomplishes by itself. A plan whose benefit depends on catching an in-transit or later-arriving player with this activation is mechanically invalid."
    )
  elif persona.scratch.role in {"Queen", "Spinster"}:
    data["ability_bid_action_clarification"] = f"Timing note for this movement-based ability: {movement_duration_hint(persona)}"

  action_rules = {
    "none": "Do not take the table's attention right now.",
    "speak": (
      "Only talk, ask, answer, bluff, soft-claim, accuse, joke, negotiate, promise, agree, refuse, or pressure without hard proof. "
      "Speaking may ask for or promise a future card return, but it cannot physically hand over, return, retrieve, steal, or otherwise transfer a card. "
      "A spoken request is not the formal card-retrieval action; formal retrieval begins only when a system EVENT says either "
      "`the Nun REQUESTER asks HOLDER to return the Nun card and end the protection.` or "
      "`REQUESTER asks HOLDER whether they can return POSSESSIVE ROLE card after a Baron theft.` "
      "Only 'practically screaming', not merely 'loud', can be heard by other tables or people in transit. "
      "When it comes naturally, vary the exact topic from your own most recent spoken line; you may switch topics or extend the previous topic to keep the conversation alive."
    ),
    "reveal": (
      "Reveal your own actual role card without using your ability. This is neither a Nun-protection reveal nor an ability attempt. "
      "If the eventual reveal line is 'practically screaming', the reveal is visible to all tables, but only Barons physically at this table can react."
    ),
    "nun-reveal": "Show a Nun card protecting you without revealing your actual private role card.",
    "ability": (
      "Reveal your own role card and try to use your role ability. "
      f"Additional role-specific ability note: {data['ability_bid_action_clarification']}"
    ),
    "retrieve": "Spend attention trying one of the currently valid formal card-retrieval pathways.",
  }
  option_lines = []
  for option in action_options:
    score_text = " | ".join(str(score) for score in option["scores"])
    action = option["action"]
    action_rule = action_rules.get(action, "Choose this currently available action.")
    option_lines.append(
      f"- {action}: {action_rule} Score guidance: {option['description']} Allowed bid scores: {score_text}."
    )
  data["action_options"] = "\n".join(option_lines) or "- none: take no action. Allowed bid scores: 0."

  prompt_template = "persona/prompt_template/templates/reaction_bidding_unified.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)

  if output != False:
    return output, [output, prompt, data]


def get_bidding_common_data(persona, table, action_context=""):
  retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = persona.scratch.retrieved
  seen_context_descriptions = set()
  seen_node_ids = set()

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

  def claim_node(node):
    node_id = getattr(node, "node_id", None)
    if not node_id:
      return claim_context(getattr(node, "description", ""))
    if node_id in seen_node_ids:
      return False
    seen_node_ids.add(node_id)
    return True

  def format_memory_line(node, indent="", include_chat_table=False):
    time_ago = timedelta_to_natural(persona.scratch.curr_time - node.created)
    if node.type == "chat":
      table_text = f" at the {node.table} table" if include_chat_table else ""
      return f"{indent}(past memory from {time_ago} ago; not necessarily the current board state) {node.description}{table_text}\n"
    if node.type == "thought":
      return f"{indent}Past private thought from {time_ago} ago, not necessarily the current board state: {node.description}\n"
    return f"{indent}(past memory from {time_ago} ago; not necessarily the current board state) {node.description} at the {node.table} table\n"

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
  new_line = (
    f"CURRENT PHYSICAL SEATING at your table, the {persona.scratch.curr_loc} "
    "(this is the live seating list and overrides old memories):\n"
  )
  current_table_context += new_line
  current_table_context += format_table_lockdown_status(table, persona.scratch.name)
  current_table_context += format_transit_status(persona.room, persona.scratch.curr_time)
  for other_player, other_player_dict in dict.items():
    current_table_context += f"\t{visual_character_label_by_name(persona.room, other_player)}\n"
    current_table_context += f"\tRelevant past events about this player (memory only; not necessarily current board state):\n"
    for event in other_player_dict["events"]:
      if claim_node(event):
        current_table_context += format_memory_line(event, "\t\t")
    current_table_context += f"\tRelevant past thoughts about this player (memory only; not necessarily current board state):\n"
    for thought in other_player_dict["thoughts"]:
      if claim_node(thought):
        current_table_context += format_memory_line(thought, "\t\t")
  current_table_context += format_transit_memory_context(persona, claim_node)
  current_table_context += format_endgame_board_context(persona, retrieved_all_tables, format_memory_line, claim_node)
  personal_context_msg = persona.get_personal_game_context()
  if persona.scratch.curr_time == datetime.timedelta(0):
    personal_context_msg += "\nThe game has only JUST started and barely anyone has said or done anything yet.\n"
  ability_msg = ability_trigger(persona, table)
  #retrieved_lines_related: {line_content: list of event nodes, line_2_content: list of event nodes, etc.}
  current_table_additional_lines = []
  for line, line_event_list in self_retrieved_lines_related.items():
    for event in line_event_list:
      if claim_node(event):
        current_table_additional_lines.append(format_memory_line(event, "\t"))
  current_table_additional_context = ""
  if current_table_additional_lines:
    current_table_additional_context = "At this moment, the conversation also reminds you of these past memories; treat them as history, not necessarily the current board state:\n"
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
        if claim_node(event):
          reminder_lines.append(format_memory_line(event, "\t"))
      if reminder_lines:
        other_table_additional_lines.append("This also reminds you of past memories, not necessarily current board state:\n")
        other_table_additional_lines.extend(reminder_lines)
    if other_table_additional_lines:
      other_table_additional_context = "Suddenly you also hear loud commotion from other tables:\n"
      other_table_additional_context += "".join(other_table_additional_lines)

  table_time_left = table_leave_timer_status(persona.scratch.curr_loc, persona.scratch.curr_time)
  all_table_time_left = "\n".join(
    f"- {table_leave_timer_status(table_name, persona.scratch.curr_time)}"
    for table_name in TIMERS.keys()
  )
  total_time_left = timedelta_to_natural(game_end_time() - persona.scratch.curr_time)
      
  stay_at_table_reason = build_stay_at_table_reason(persona, table)
  last_act_reasoning = f"your strongest bidding reasoning moments ago was: {persona.scratch.act_reasoning} (Do reevaluate whether this still applies and DO update based on the actual most recent line spoken at the table, for example if you actually answered an earlier question by others, or if you've asked something multiple times in a row then whether you should shut up and wait for an answer)" if persona.scratch.act_reasoning else "you haven't really thought about doing anything yet"
  ability_bid_action_clarification = (
    "For this prompt in particular, you want to for now decide that, if simply talking alone can't help you achieve your goals, "
    "how urgently you want to use your ability (and in the process reveal your role at everyone at your current table) to the conversation in particular. "
    "For the chance to reveal your card and role next you will place a bid. Highest bidder speaks or acts first."
  )

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": personal_context_msg,
    "current_table_context": current_table_context,
    "action_context": f"Immediate action context:\n{action_context}\n" if action_context else "",
    "ability_msg": ability_msg,
    "recent_conversation": recent_conversation,
    "latest_table_line_reminder": latest_table_line_reminder(persona, table),
    "current_table_events": current_table_events,
    "current_table_additional_context": current_table_additional_context,
    "other_table_additional_context": other_table_additional_context,
    "stay_at_table_reason": stay_at_table_reason,
    "last_act_reasoning": last_act_reasoning,
    "ability_bid_action_clarification": ability_bid_action_clarification,
    "table_time_left": table_time_left,
    "all_table_time_left": all_table_time_left,
    "total_time_left": total_time_left,
    "conversation_posture": conversation_posture_prompt(persona),
  }

  return data
  


def run_gpt_prompt_act_bidding_speak(persona, table, action_context="", test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table, action_context=action_context)

  prompt_template = "persona/prompt_template/templates/reaction_bidding_speaking.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  
def run_gpt_prompt_act_bidding_retrieve(persona, table, retrieval_options, action_context="", test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table, action_context=action_context)
  option_lines = ""
  for option in retrieval_options:
    option_lines += f"- {option['description']}\n"
  data["retrieval_options"] = option_lines or "- No valid retrieval option.\n"

  prompt_template = "persona/prompt_template/templates/reaction_bidding_retrieve.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]
  

def run_gpt_prompt_decide_on_leaving(persona, table, retrieved_all_tables, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  _retrieved_self, _retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, _all_tables = persona.scratch.retrieved
  external_table_context = ""
  seen_context_descriptions = set()
  seen_node_ids = set()
  movement_semantic_reminder_cap = 4

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

  def claim_node(node):
    node_id = getattr(node, "node_id", None)
    description = getattr(node, "description", "")
    if not claim_context(description):
      return False
    if node_id in seen_node_ids:
      return False
    if node_id is not None:
      seen_node_ids.add(node_id)
    return True

  def format_movement_memory_line(node):
    time_ago = timedelta_to_natural(persona.scratch.curr_time - node.created)
    if node.type == "thought":
      return f"\t(past private thought from {time_ago} ago; not necessarily current) {node.description}\n"
    return f"\t(past memory from {time_ago} ago; not necessarily current) {node.description} at the {node.table} table\n"

  for table_name, dict in retrieved_all_tables.items():
    table_timer_left = table_leave_timer_status(table_name, persona.scratch.curr_time)
    new_line = f"Players currently seated at the {table_name} table ({table_timer_left}):"
    if persona.scratch.curr_loc == table_name:
      new_line += ", which is your table"
      new_line += ":\n"
    external_table_context += new_line
    external_table_context += format_table_lockdown_status(persona.room.locations[table_name], persona.scratch.name, "\t")
    for other_player, other_player_dict in dict.items():
      external_table_context += f"\t{visual_character_label_by_name(persona.room, other_player)}\n"
      external_table_context += f"\tRelevant past events about this player (memory only; not necessarily current board state):\n"
      for event in other_player_dict["events"]:
        if not claim_node(event):
          continue
        time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
        new_line = "\t\t"+ f"(past memory from {time_ago} ago; not necessarily current) " + event.description + f" at the {event.table} table\n"
        external_table_context += new_line
      external_table_context += f"\tRelevant past thoughts about this player (memory only; not necessarily current board state):\n"
      for thought in other_player_dict["thoughts"]:
        if not claim_node(thought):
          continue
        time_ago = timedelta_to_natural(persona.scratch.curr_time - thought.created)
        new_line = "\t\t"+ f"(past private thought from {time_ago} ago; not necessarily current) " + thought.description + "\n"
        external_table_context += new_line
  external_table_context += format_transit_status(persona.room, persona.scratch.curr_time)
  external_table_context += format_transit_memory_context(persona, claim_node)
  personal_context_msg = persona.get_personal_game_context()
  ability_msg = ability_trigger(persona, table)

  table_time_left = table_leave_timer_status(persona.scratch.curr_loc, persona.scratch.curr_time)
  all_table_time_left = "\n".join(
    f"- {table_leave_timer_status(table_name, persona.scratch.curr_time)}"
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
      if not claim_context(event.description):
        continue
      time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
      new_line = f"({time_ago} ago)"+ event.description + f" at the {event.table} table\n"
      recent_conversation += new_line
  if not recent_conversation:
    recent_conversation = "No dialogue or table events have been perceived yet.\n"

  movement_semantic_reminder_lines = []
  for related_dict in [self_retrieved_lines_related, other_retrieved_lines_related]:
    for _line, event_list in related_dict.items():
      for event in event_list:
        if len(movement_semantic_reminder_lines) >= movement_semantic_reminder_cap:
          break
        if claim_node(event):
          movement_semantic_reminder_lines.append(format_movement_memory_line(event))
      if len(movement_semantic_reminder_lines) >= movement_semantic_reminder_cap:
        break
    if len(movement_semantic_reminder_lines) >= movement_semantic_reminder_cap:
      break

  movement_semantic_reminders = ""
  if movement_semantic_reminder_lines:
    movement_semantic_reminders = (
      "Recent lines also semantically remind you of these older memories; use them only if they matter for where to move next:\n"
      + "".join(movement_semantic_reminder_lines)
    )

  data = {
    "PREFIX": PREFIX,
    "personal_context_msg": personal_context_msg,
    "external_table_context": external_table_context,
    "ability_msg": ability_msg,
    "recent_conversation": recent_conversation,
    "movement_semantic_reminders": movement_semantic_reminders,
    "authoritative_occupancy_snapshot": format_authoritative_occupancy_snapshot(persona.room),
    "current_table": current_table,
    "other_options": other_options,
    "movement_duration_hint": movement_duration_hint(persona),
    "table_time_left": table_time_left,
    "all_table_time_left": all_table_time_left,
    "total_time_left": total_time_left,
    "conversation_posture": conversation_posture_prompt(persona),
    "options": options
  }

  prompt_template = "persona/prompt_template/templates/decide_on_moving.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

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
    seated_names = ", ".join(sorted(table.personas)) or "none"
    transit_names = ", ".join(sorted(getattr(persona.room, "transit", {}))) or "none"
    ability_target_info += (
      "as King, you can select one of the families physically present at the table right now as target. "
      "This activation takes one immutable snapshot and only affects already-seated players of that family; it does not wait for players in transit or later arrivals. "
      f"AUTHORITATIVE ELIGIBLE SEATED SNAPSHOT: {seated_names}. "
      f"EXPLICITLY EXCLUDED FROM THIS ACTIVATION BECAUSE THEY ARE IN TRANSIT: {transit_names}. "
      "Even if an excluded player lands here immediately after this action, they remain free and are not retroactively added to the lock. "
      "Do not claim that choosing a family now will bind, trap, test, or otherwise affect any excluded transit player. Available family choices:\n"
    )
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
      "Use this as optional context for target selection, but correct any part that conflicts with the authoritative current target rules above. "
      "In particular, for King, discard any claim that this activation will catch someone currently in transit or arriving later.\n"
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
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_guess_family_bishop(persona, target, table, ability_reasoning="", target_reasoning="", test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  families = sorted({role_data["family"] for role_data in ROLE_DICT.values()})
  ability_target_info = (
    f"as Bishop, you are guessing {target.scratch.name}'s family. "
    f"Choose exactly one of these families: {', '.join(families)}"
  )
  prior_reasoning_parts = []
  if ability_reasoning:
    prior_reasoning_parts.append(f"When you bid to use your Bishop ability, your reasoning was: {ability_reasoning}")
  if target_reasoning:
    prior_reasoning_parts.append(f"When you selected {target.scratch.name} as your target, your reasoning was: {target_reasoning}")
  prior_reasoning_msg = (
    "Prior reasoning you should keep consistent with unless new evidence clearly changes your mind:\n"
    + "\n".join(f"- {part}" for part in prior_reasoning_parts)
    if prior_reasoning_parts
    else ""
  )

  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "ability_target_info": ability_target_info,
    "prior_reasoning_msg": prior_reasoning_msg,
  }
  prompt_template = "persona/prompt_template/templates/guess_family_bishop.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    if "guess" not in output and "target" in output:
      output["guess"] = output["target"]
    return output, [output, prompt, data_sub]


def run_gpt_prompt_bishop_wrong_guess_response(persona, bishop, guessed_family, table, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  actual_family = ROLE_DICT[persona.scratch.role]["family"]
  card_status = (
    f"you have your {persona.scratch.role} card and can hard reveal it"
    if has_own_role_card(persona)
    else f"you do not currently have your {persona.scratch.role} card, so hard reveal is not available"
  )
  hard_reveal_option = (
    '- "hard reveal": reveal your actual role card to prove the Bishop was wrong.'
    if has_own_role_card(persona)
    else f'- "hard reveal": (not available right now because you do not have your {persona.scratch.role} role card)'
  )
  data_sub = {
    "PREFIX": PREFIX,
    "personal_context_msg": data["personal_context_msg"],
    "current_table_context": data["current_table_context"],
    "recent_conversation": data["recent_conversation"],
    "current_table_events": data["current_table_events"],
    "current_table_additional_context": data["current_table_additional_context"],
    "other_table_additional_context": data["other_table_additional_context"],
    "bishop_name": bishop.scratch.name,
    "guessed_family": guessed_family,
    "actual_role": persona.scratch.role,
    "actual_family": actual_family,
    "card_status": card_status,
    "hard_reveal_option": hard_reveal_option,
  }
  prompt_template = "persona/prompt_template/templates/bishop_wrong_guess_response.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=localized_dialogue_json_cleanup,
    model=DIALOGUE_GENERATION_LLM_MODEL,
    reasoning_effort=None if ALLOW_SPEECH_REASONING else "none",
  )
  if output != False:
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
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(
    final_prompt,
    func_clean_up=localized_dialogue_json_cleanup,
    model=SPINSTER_GUESS_LLM_MODEL,
  )
  if output != False:
    return output, [output, prompt, data_sub]


def run_gpt_prompt_decide_baron_block(persona, table, revealed_player, action_context, reaction_context="", known_baron_trophy_cards=None, test_input=None, verbose=False):
  data = get_bidding_common_data(persona, table)
  current_trophies = held_trophy_cards(persona)
  known_baron_trophy_cards = set(known_baron_trophy_cards or [])
  blind_baron_trophy_target = len(role_pool_for_mode()) == 16 and revealed_player.scratch.role == "Baron"
  if blind_baron_trophy_target:
    potential_gain = set(known_baron_trophy_cards)
    baron_steal_rule = (
      "Because the revealed player is another Baron in expanded 16-player mode, your Baron reaction can steal that Baron's trophy cards, "
      "but it cannot steal that Baron's own Baron role card. No Baron role-card retrieval claim is created by this. "
      "This prompt does not reveal that Baron's preexisting trophy pile, if any; rely only on cards you saw enter that pile or can infer from your memories."
    )
  else:
    potential_gain = {card_id(revealed_player.scratch.role, revealed_player.scratch.name)}
    baron_steal_rule = (
      "Your Baron reaction can steal the revealed player's own role card. The target keeps their role and win condition but loses use/reveal of that card until valid retrieval."
    )
  new_trophies = current_trophies | potential_gain
  current_trophy_text = ", ".join(describe_card_for_persona(persona, card) for card in sorted(current_trophies)) if current_trophies else "none"
  if blind_baron_trophy_target:
    known_gain_text = ", ".join(describe_card(card) for card in sorted(known_baron_trophy_cards)) if known_baron_trophy_cards else "none"
    minimum_trophies = len(new_trophies)
    baron_trophy_status = (
      f"Your own Baron card is NOT a trophy and does NOT count toward your Baron win condition. "
      f"Only other players' cards you are holding count as trophies. "
      f"You currently have {len(current_trophies)} trophy card(s): {current_trophy_text}. "
      f"You can clearly identify these trophy card(s) in the other Baron's possession from this immediate steal/countersteal chain: {known_gain_text}. "
      f"Any other preexisting trophy cards that Baron may or may not hold are not revealed by this prompt; you may reason from your remembered public events, but do not treat the system as giving you a private inventory view. "
      f"If this succeeds, you would have at least {minimum_trophies} known trophy card(s), plus any hidden trophy cards that Baron actually had. "
      f"Your required trophy count is {baron_trophy_requirement()}."
    )
  else:
    potential_gain_text = ", ".join(describe_card(card) for card in sorted(potential_gain)) if potential_gain else "none"
    baron_trophy_status = (
      f"Your own Baron card is NOT a trophy and does NOT count toward your Baron win condition. "
      f"Only other players' cards you are holding count as trophies. "
      f"You currently have {len(current_trophies)} trophy card(s): {current_trophy_text}. "
      f"This reaction could add {len(potential_gain - current_trophies)} new trophy card(s): {potential_gain_text}. "
      f"If it succeeds, you would have {len(new_trophies)} trophy card(s) toward the required {baron_trophy_requirement()}."
    )
  if not reaction_context:
    reaction_context = (
      "This is a primary Baron reaction to another player's reveal or attempted ability. "
      "If more than one Baron wants to react, the highest Baron reaction bid acts first; tied top bids are broken randomly."
    )
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
    "reaction_context": reaction_context,
    "baron_steal_rule": baron_steal_rule,
    "baron_trophy_status": baron_trophy_status,
  }
  prompt_template = "persona/prompt_template/templates/decide_baron_block.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

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
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

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
    if table.name == "Village":
      ability_description = (
        "As a special Bishop-exile edge case, when you are forced to leave the Village you may reveal your Spinster card, "
        "point to one player still in the Village, and force that player to reveal their role card to the Village after you leave."
      )
    else:
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
    "movement_duration_hint": movement_duration_hint(persona),
    "role": role,
    "destination": destination,
    "movement_reasoning": movement_reasoning or "I did not have a detailed movement reason recorded.",
    "ability_description": ability_description,
    "target_options": target_options,
  }
  prompt_template = "persona/prompt_template/templates/decide_movement_ability_use.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data_sub))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data_sub]



def run_gpt_prompt_select_ability_destination(persona, table, retrieved_all_tables, special_circumstance
, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  external_table_context = ""
  seen_node_ids = set()

  def claim_node(node):
    node_id = getattr(node, "node_id", None)
    if not node_id:
      return True
    if node_id in seen_node_ids:
      return False
    seen_node_ids.add(node_id)
    return True

  for table_name, dict in retrieved_all_tables.items():
    new_line = f"Players currently seated at the {table_name} table:"      
    if persona.scratch.curr_loc == table_name:
      new_line += ", which is your table"
      new_line += ":\n"
    external_table_context += new_line
    external_table_context += format_table_lockdown_status(persona.room.locations[table_name], persona.scratch.name, "\t")
    for other_player, other_player_dict in dict.items():
      external_table_context += f"\t{visual_character_label_by_name(persona.room, other_player)}\n"
      external_table_context += f"\tRelevant past events about this player (memory only; not necessarily current board state):\n"
      for event in other_player_dict["events"]:
        if not claim_node(event):
          continue
        time_ago = timedelta_to_natural(persona.scratch.curr_time - event.created)
        new_line = "\t\t"+ f"(past memory from {time_ago} ago; not necessarily current) " + event.description + f" at the {event.table} table\n"
        external_table_context += new_line
      external_table_context += f"\tRelevant past thoughts about this player (memory only; not necessarily current board state):\n"
      for thought in other_player_dict["thoughts"]:
        if not claim_node(thought):
          continue
        time_ago = timedelta_to_natural(persona.scratch.curr_time - thought.created)
        new_line = "\t\t"+ f"(past private thought from {time_ago} ago; not necessarily current) " + thought.description + "\n"
        external_table_context += new_line
  external_table_context += format_transit_status(persona.room, persona.scratch.curr_time)
  external_table_context += format_transit_memory_context(persona, claim_node)
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

  table_time_left = table_leave_timer_status(persona.scratch.curr_loc, persona.scratch.curr_time)
  all_table_time_left = "\n".join(
    f"- {table_leave_timer_status(table_name, persona.scratch.curr_time)}"
    for table_name in retrieved_all_tables.keys()
  )
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
    "authoritative_occupancy_snapshot": format_authoritative_occupancy_snapshot(persona.room),
    "ability_msg": ability_msg,
    "special_circumstance": special_circumstance,
    "ability_departure_reasoning": ability_departure_reasoning_msg,
    "recent_conversation": recent_conversation,
    "other_options": other_options,
    "table_time_left": table_time_left,
    "all_table_time_left": all_table_time_left,
    "total_time_left": total_time_left,
    "options": options
  }

  prompt_template = "persona/prompt_template/templates/select_ability_destination.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  
  if output != False: 
    return output, [output, prompt, data]


def run_gpt_prompt_decide_card_retrieval(persona, table, object, test_input=None, verbose=False): 
  #retrieved_all_tables format: {table_name: {persona_name: {"events": list of event nodes, "thoughts": list of event nodes}}}
  data = get_bidding_common_data(persona, table)
  if (
      persona.scratch.role == "Nun"
      and (
        object in (persona.scratch.ability_objects or [])
        or (
          object in table.personas
          and has_card(table.personas[object].scratch.cards_slot, "Nun", persona.scratch.name)
          and has_nun_protection(table.personas[object])
        )
      )
  ):
    extra_reason = f"you're the Nun and your card and ability is currently possessed by and protecting {object}"
  else: # Baron case
    extra_reason = (
      f"your own role card was stolen through a Baron theft and is still unavailable; because you are alone with {object}, "
      "you can test whether this person is currently the Baron holder of that card and demand it back if so"
    )
  data["stay_at_table_reason"] = build_stay_at_table_reason(persona, table, [extra_reason])
  prompt_template = "persona/prompt_template/templates/decide_card_retrieval.txt"
  prompt = read_prompt_template(prompt_template)
  final_prompt = prompt.format(**localized_prompt_data(data))

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
  final_prompt = prompt.format(**localized_prompt_data(data))

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
  final_prompt = prompt.format(**localized_prompt_data(data))

  output = ChatGPT_safe_generate_response_full(final_prompt, func_clean_up=json_cleanup)
  if output != False:
    return output, [output, prompt, data]
