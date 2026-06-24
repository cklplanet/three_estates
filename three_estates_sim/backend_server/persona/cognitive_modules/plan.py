"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: plan.py
Description: This defines the "Plan" module for generative agents. 
"""
import datetime
import math
import random 
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
SPEAK_MULTIPLIER = 2


def bid(persona, table):
  table_size = len(table.personas.keys())
  role = persona.scratch.role
  persona.scratch.current_bidding_scores = dict()
  # Default ability bid is 0 (not usable)
  ability_bid = 0
  # Check conditions for ability being allowed
  # TODO: prompt in other forms of act notifying that they can't use their ability right now.
  if table_size > 1 and role in persona.scratch.cards_slot: # if there isn't any other person at the table don't even bother bidding for the ability
    if (
        (role == "Bishop" and table.bishop_trigger) or
        (role == "Baron" and table.baron_trigger and table_size > 2) or
        (role in {"Priest", "Thief", "Nun"} and table_size == 2) or
        (role == "Innkeeper" and table.name != "Village") or
        (role == "Spinster" and table.name == "Forest") or
        (role in {"King", "Queen"} and table_size > 1)
    ):
        # If conditions are satisfied, allow ability bidding
        ability_bid_dict = prompt_dict(
          run_gpt_prompt_act_bidding_ability(persona, table),
          {"reasoning": "I do not have a clear ability play right now.", "bid": "0"}
        )
        persona.scratch.act_reasoning = ability_bid_dict["reasoning"]
        ability_bid = bounded_int(ability_bid_dict["bid"], 0, allowed={0, 1, 3, 5, 7})
        ability_bid = ABILITY_MULTIPLIER * ability_bid
        persona.scratch.current_bidding_scores['ability'] = ability_bid
        debug_bid(persona, table, "ability", ability_bid, ability_bid_dict["reasoning"])
  reveal_bid_dict = prompt_dict(
    run_gpt_prompt_act_bidding_reveal(persona, table),
    {"reasoning": "I do not need to reveal my card right now.", "bid": "0"}
  )
  persona.scratch.act_reasoning = reveal_bid_dict["reasoning"]
  reveal_bid = bounded_int(reveal_bid_dict["bid"], 0, allowed={0, 1, 2, 3, 5})
  debug_bid(persona, table, "reveal", REVEAL_MULTIPLIER * reveal_bid, reveal_bid_dict["reasoning"])
  if persona.scratch.speaking_cooldown > 0:
    speaking_bid_dict = {
      "reasoning": f"I just spoke and should let others respond for {persona.scratch.speaking_cooldown} more turn(s).",
      "bid": "0"
    }
  else:
    speaking_bid_dict = prompt_dict(
      run_gpt_prompt_act_bidding_speak(persona, table),
      {"reasoning": "I have nothing useful to add out loud right now.", "bid": "0"}
    )
  persona.scratch.act_reasoning = speaking_bid_dict["reasoning"]
  speaking_bid = bounded_int(speaking_bid_dict["bid"], 0, allowed={0, 1, 2, 3, 4})
  #print("reveal bid: ", reveal_bid_dict)
  #print("speaking bid: ", speaking_bid_dict)
  reveal_bid = REVEAL_MULTIPLIER * reveal_bid
  speaking_bid = SPEAK_MULTIPLIER * speaking_bid
  debug_bid(persona, table, "speak", speaking_bid, speaking_bid_dict["reasoning"])
  total_bid_score = ability_bid + reveal_bid + speaking_bid
  persona.scratch.current_bidding_scores['reveal'] = reveal_bid
  persona.scratch.current_bidding_scores['speak'] = speaking_bid
  return total_bid_score


def decide_on_leaving(persona, table, retrieved_all_tables):
  movement_dict = prompt_dict(
    run_gpt_prompt_decide_on_leaving(persona, table, retrieved_all_tables),
    {"reasoning": "I do not have a strong reason to leave right now.", "option": "stay"}
  )
  option = movement_dict["option"]
  if option not in table.connected and option != "stay":
    return "stay"
  return option
