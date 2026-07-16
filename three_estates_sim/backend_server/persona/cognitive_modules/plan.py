"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: plan.py
Description: This defines the "Plan" module for generative agents. 
"""
import datetime
import math
import random 
import re
import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from global_methods import *
from persona.prompt_template.run_gpt_prompt import *
from persona.cognitive_modules.retrieve import *
from utils import *

ABILITY_MULTIPLIER = 1
REVEAL_MULTIPLIER = 1
SPEAK_MULTIPLIER = 1.5


def movement_reasoning_keywords(persona, table, option, reasoning):
  keywords = {persona.scratch.name, table.name, option, "movement", "stay" if option == "stay" else "leave"}
  for table_name in persona.room.locations.keys():
    if table_name.lower() in reasoning.lower() or table_name == option or table_name == table.name:
      keywords.add(table_name)
  for player_name in persona.room.personas.keys():
    if player_name == persona.scratch.name or re.search(rf"(?<!\\w){re.escape(player_name)}(?!\\w)", reasoning, re.IGNORECASE):
      keywords.add(player_name)
  role_words = set(ROLE_DICT.keys()) | {role_data["family"] for role_data in ROLE_DICT.values()}
  for word in role_words:
    if word.lower() in reasoning.lower():
      keywords.add(word)
  return keywords


def remember_movement_reasoning(persona, table, requested_option, final_option, reasoning):
  adjusted = "" if requested_option == final_option else f" I originally considered {requested_option}, but that was not a valid move."
  if final_option == "stay":
    description = f"I decided to stay at {table.name} because {reasoning}.{adjusted}"
    poignancy = 3
  else:
    description = f"I decided to leave {table.name} for {final_option} because {reasoning}.{adjusted}"
    poignancy = 5
  if description in persona.a_mem.embeddings:
    return
  embedding = get_embedding(description)
  expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
  keywords = movement_reasoning_keywords(persona, table, final_option, reasoning)
  persona.a_mem.add_thought(
    persona.scratch.curr_time,
    expiration,
    persona.scratch.name,
    persona.scratch.name,
    description,
    keywords,
    poignancy,
    (description, embedding),
  )


def bid(persona, table, action_context=""):
  table_size = len(table.personas.keys())
  role = persona.scratch.role
  persona.scratch.current_bidding_scores = dict()
  persona.scratch.current_bidding_reasonings = dict()
  # Default ability bid is 0 (not usable)
  ability_bid = 0
  retrieve_bid = 0
  nun_reveal_bid = 0
  retrieval_options = persona.card_retrieval_options(table)
  if retrieval_options:
    retrieve_bid_dict = prompt_dict(
      run_gpt_prompt_act_bidding_retrieve(persona, table, retrieval_options, action_context=action_context),
      {"reasoning": "I will not spend the table's attention retrieving a card right now.", "bid": "0"}
    )
    persona.scratch.current_bidding_reasonings['retrieve'] = retrieve_bid_dict["reasoning"]
    retrieve_bid = bounded_int(retrieve_bid_dict["bid"], 0)
    persona.scratch.current_bidding_scores['retrieve'] = retrieve_bid
    debug_bid(persona, table, "retrieve", retrieve_bid, retrieve_bid_dict["reasoning"])
  # Check conditions for ability being allowed
  if has_own_role_card(persona, role):
    if (
        table_size > 1 and (
          (role == "Innkeeper" and table.name != "Village" and not table.timer_expired) or
          (role == "Bishop" and table.bishop_trigger) or
          (role in {"Priest", "Nun"} and table_size == 2) or
          (role == "Thief" and table_size == 2 and not thief_reverse_swap_locked(table, persona.scratch.name)) or
          (role == "Spinster" and table.name == "Forest" and not table.timer_expired) or
          (role == "King") or
          (role == "Queen" and not table.timer_expired)
        )
    ):
        # If conditions are satisfied, allow ability bidding
        ability_bid_dict = prompt_dict(
          run_gpt_prompt_act_bidding_ability(persona, table, action_context=action_context),
          {"reasoning": "I do not have a clear ability play right now.", "bid": "0"}
        )
        persona.scratch.current_bidding_reasonings['ability'] = ability_bid_dict["reasoning"]
        ability_bid = bounded_int(ability_bid_dict["bid"], 0)
        ability_bid = ABILITY_MULTIPLIER * ability_bid
        persona.scratch.current_bidding_scores['ability'] = ability_bid
        debug_bid(persona, table, "ability", ability_bid, ability_bid_dict["reasoning"])
  if role != "Nun" and has_nun_protection(persona):
    nun_reveal_bid_dict = prompt_dict(
      run_gpt_prompt_act_bidding_nun_reveal(persona, table, action_context=action_context),
      {"reasoning": "I do not need to show the Nun card protecting me right now.", "bid": "0"}
    )
    persona.scratch.current_bidding_reasonings['nun-reveal'] = nun_reveal_bid_dict["reasoning"]
    nun_reveal_bid = bounded_int(nun_reveal_bid_dict["bid"], 0)
    persona.scratch.current_bidding_scores['nun-reveal'] = nun_reveal_bid
    debug_bid(persona, table, "nun-reveal", nun_reveal_bid, nun_reveal_bid_dict["reasoning"])
  if not has_own_role_card(persona, role):
    reveal_bid_dict = {
      "reasoning": f"I cannot reveal my {role} card because I do not currently have it.",
      "bid": "0"
    }
  else:
    reveal_bid_dict = prompt_dict(
      run_gpt_prompt_act_bidding_reveal(persona, table, action_context=action_context),
      {"reasoning": "I do not need to reveal my card right now.", "bid": "0"}
    )
  persona.scratch.current_bidding_reasonings['reveal'] = reveal_bid_dict["reasoning"]
  reveal_bid = bounded_int(reveal_bid_dict["bid"], 0)
  debug_bid(persona, table, "reveal", REVEAL_MULTIPLIER * reveal_bid, reveal_bid_dict["reasoning"])
  if ENABLE_SPEAKING_COOLDOWN and persona.scratch.speaking_cooldown > 0:
    speaking_bid_dict = {
      "reasoning": f"I just spoke and should let others respond for {persona.scratch.speaking_cooldown} more turn(s).",
      "bid": "0"
    }
  else:
    speaking_bid_dict = prompt_dict(
      run_gpt_prompt_act_bidding_speak(persona, table, action_context=action_context),
      {"reasoning": "I have nothing useful to add out loud right now.", "bid": "0"}
    )
  persona.scratch.current_bidding_reasonings['speak'] = speaking_bid_dict["reasoning"]
  speaking_bid = bounded_int(speaking_bid_dict["bid"], 0)
  #print("reveal bid: ", reveal_bid_dict)
  #print("speaking bid: ", speaking_bid_dict)
  reveal_bid = REVEAL_MULTIPLIER * reveal_bid
  speaking_bid = SPEAK_MULTIPLIER * speaking_bid
  debug_bid(persona, table, "speak", speaking_bid, speaking_bid_dict["reasoning"])
  total_bid_score = ability_bid + reveal_bid + speaking_bid + retrieve_bid + nun_reveal_bid
  persona.scratch.current_bidding_scores['reveal'] = reveal_bid
  persona.scratch.current_bidding_scores['speak'] = speaking_bid
  if persona.scratch.current_bidding_scores:
    tie_break_priority = {
      "retrieve": 5,
      "ability": 4,
      "nun-reveal": 3,
      "reveal": 2,
      "speak": 1,
    }
    strongest_action = max(
      persona.scratch.current_bidding_scores,
      key=lambda action: (
        persona.scratch.current_bidding_scores[action],
        tie_break_priority.get(action, -1),
      ),
    )
    persona.scratch.act_reasoning = persona.scratch.current_bidding_reasonings.get(
      strongest_action,
      persona.scratch.act_reasoning,
    )
  return total_bid_score


def decide_on_leaving(persona, table, retrieved_all_tables):
  movement_dict = prompt_dict(
    run_gpt_prompt_decide_on_leaving(persona, table, retrieved_all_tables),
    {
      "reasoning": "I do not have a strong reason to leave right now.",
      "summary": "Stay for now and keep watching the table.",
      "option": "stay"
    }
  )
  requested_option = movement_dict["option"]
  option = requested_option
  if option not in table.connected and option != "stay":
    option = "stay"
  full_reasoning = movement_dict["reasoning"]
  summary = compact_summary_text(movement_dict.get("summary"), full_reasoning)
  persona.scratch.current_movement_reasoning = summary
  persona.scratch.current_movement_destination = option
  debug_movement(persona, table, requested_option, option, full_reasoning, summary)
  remember_movement_reasoning(persona, table, requested_option, option, summary)
  return option
