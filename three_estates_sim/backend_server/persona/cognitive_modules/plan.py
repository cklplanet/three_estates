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
sys.path.append('../../')

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
  # Default ability bid is 0 (not usable)
  ability_bid = 0
  # Check conditions for ability being allowed
  # TODO: prompt in other forms of act notifying that they can't use their ability right now.
  if table_size > 1: # if there isn't any other person at the table don't even bother bidding for the ability
    if (
        (role == "Bishop" and table.bishop_trigger) or
        (role == "Baron" and table.baron_trigger and table_size > 2) or
        (role in {"Priest", "Thief", "Nun"} and table_size == 2) or
        (role == "Innkeeper" and table.name != "Village") or
        (role not in {"Bishop", "Baron", "Priest", "Thief", "Nun", "Innkeeper"} and table_size > 1)
    ):
        # If conditions are satisfied, allow ability bidding
        ability_bid_dict = run_gpt_prompt_act_bidding_ability(persona, table)[0]
        persona.scratch.act_reasoning = ability_bid_dict["reasoning"]
        ability_bid = ability_bid_dict["bid"]
        ability_bid = ABILITY_MULTIPLIER * int(ability_bid)
        persona.scratch.current_bidding_scores['ability'] = ability_bid
  reveal_bid_dict = run_gpt_prompt_act_bidding_reveal(persona, table)[0]
  persona.scratch.act_reasoning = reveal_bid_dict["reasoning"]
  reveal_bid = reveal_bid_dict["bid"]
  speaking_bid_dict = run_gpt_prompt_act_bidding_speak(persona, table)[0]
  persona.scratch.act_reasoning = speaking_bid_dict["reasoning"]
  speaking_bid = speaking_bid_dict["bid"]
  #print("reveal bid: ", reveal_bid_dict)
  #print("speaking bid: ", speaking_bid_dict)
  reveal_bid = REVEAL_MULTIPLIER * int(reveal_bid)
  speaking_bid = SPEAK_MULTIPLIER * int(speaking_bid)
  total_bid_score = ability_bid + reveal_bid + speaking_bid
  persona.scratch.current_bidding_scores['reveal'] = reveal_bid
  persona.scratch.current_bidding_scores['speak'] = speaking_bid
  return total_bid_score


def decide_on_leaving(persona, table, retrieved_all_tables):
  return run_gpt_prompt_decide_on_leaving(persona, table, retrieved_all_tables)[0]["option"]

