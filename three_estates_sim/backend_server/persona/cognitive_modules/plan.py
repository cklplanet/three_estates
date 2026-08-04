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

  def can_bid_ability():
    if not has_own_role_card(persona, role):
      return False
    # Innkeeper's bid is a departure for the Village, not a targeted table
    # ability, so it remains valid even when the Innkeeper is alone.
    if table_size <= 1 and role != "Innkeeper":
      return False
    return (
      (role == "Innkeeper" and table.name != "Village" and not table.timer_expired) or
      (role == "Bishop" and table.bishop_trigger and not table.timer_expired) or
      (role in {"Priest", "Nun"} and table_size == 2) or
      (role == "Thief" and table_size == 2 and not thief_reverse_swap_locked(table, persona.scratch.name)) or
      (role == "Spinster" and table.name == "Forest" and not table.timer_expired) or
      (role == "King") or
      (role == "Queen" and not table.timer_expired)
    )

  def normalize_choice(action, raw_bid, available_options):
    allowed = available_options.get(action)
    if allowed is None:
      return "none", 0
    raw_value = bounded_int(raw_bid, 0)
    return action, max((score for score in allowed if score <= raw_value), default=0)

  retrieval_options = persona.card_retrieval_options(table)
  action_options = [{
    "action": "none",
    "scores": [0],
    "description": "take no action and let the table continue without you seizing attention."
  }]
  if retrieval_options:
    retrieval_descriptions = " ".join(option["description"] for option in retrieval_options)
    action_options.append({
      "action": "retrieve",
      "scores": [0, 3, 8],
      "description": (
        "try a currently valid card retrieval pathway. Score meanings: "
        "0 = not at all; for Baron-theft retrieval, you do not think the card could plausibly be in this person's hands; "
        "for Nun retrieval, you do not want the Nun card back right now. "
        "3 = uncertain probe; Thief swaps, Baron steals/countersteals, movement, or imperfect memory make it useful to check, "
        "or getting the Nun card back could be useful but is not urgent. "
        "8 = urgent retrieval; you are desperate to retrieve your card now, this person was literally the Baron who stole it and nothing suggests it moved elsewhere, "
        "or your memories/observations indicate this person is currently where your card ended up. "
        f"Available retrieval details: {retrieval_descriptions}"
      ),
    })
  if can_bid_ability():
    action_options.append({
      "action": "ability",
      "scores": [0, 2, 4, 5, 7],
      "description": (
        "reveal your role card and attempt to use your role ability under the current valid conditions. Score meanings: "
        "0 = no intention of using your ability right now; the condition is not met, or it would be a waste. "
        "2 = mildly but concretely considering using it, maybe to pressure others or set up a situation. "
        "4 = there is a tactical opportunity where using it could advance your position or disrupt another's. "
        "5 = you need to use it soon to gain leverage, expose someone, or block progress. "
        "7 = using it right now would directly contribute to your win condition, or protect you or an ally from immediate threat."
      ),
    })
  if role != "Nun" and has_nun_protection(persona):
    action_options.append({
      "action": "nun-reveal",
      "scores": [0, 3, 4, 6],
      "description": (
        "voluntarily show the Nun card protecting you without revealing your actual private role card. Score meanings: "
        "0 = do not show the Nun card right now. "
        "3 = you might show it if the table needs a small reminder, but it is not important. "
        "4 = showing Nun protection could meaningfully change how others treat or target you. "
        "6 = you urgently need to prove you are protected by the Nun card right now."
      ),
    })
  if has_own_role_card(persona, role):
    action_options.append({
      "action": "reveal",
      "scores": [0, 1, 3, 5, 6],
      "description": (
        "reveal your own actual role card without using your ability. This does not include showing a Nun card. Score meanings: "
        "0 = do not reveal; no benefit, it may backfire, or you already revealed to this same table with no new arrivals. "
        "1 = slightly open to revealing if prompted or if it builds light trust, but normal conversation is better for now. "
        "3 = proving your role could shift how people treat or believe you, especially to bluff or signal alignment. "
        "5 = enough suspicion or pressure exists that revealing would change the table dynamic or help activate an ability chain. "
        "6 = urgent reveal to disprove a false claim, comply when it benefits you, or publicly pivot perception to directly help your win condition; delay is dangerous."
      ),
    })
  if not ENABLE_SPEAKING_COOLDOWN or persona.scratch.speaking_cooldown <= 0:
    if casual_conversation_active(persona):
      speaking_score_meanings = (
        "0 = listen, allow someone else to answer, or let a silence stand, especially if you just spoke. "
        "1 = a minor aside or low-stakes thought. "
        "2 = a worthwhile continuation of an interesting topic, joke, disagreement, personal question, or interpersonal thread. "
        "3 = a strong in-character desire to tease, argue, gossip, complain, tell a story, ask something personal, or redirect the room away from the game. "
        "4 = you were directly addressed, are emotionally invested, or have an especially character-revealing response that you strongly want heard now."
      )
    else:
      speaking_score_meanings = (
        "0 = lay low, observe, or you have better things to do than merely speaking; this is especially appropriate if the last spoken line was yours, and even more so if you just asked a question and should give others a chance to answer. "
        "1 = you have general thoughts to share, maybe even just chat or keep the table moving. "
        "2 = you have something critical and specific to contribute, including fishing for information or non-card-backed reveals. "
        "3 = urgent need to speak next for information, deflection, or your/others' win conditions. "
        "4 = merely speaking or responding is absolutely preferable to hard reveal or ability use, especially if addressed and needing to answer truthfully, lie, overpower rhetorically, or throw in a pointed comment."
      )
    action_options.append({
      "action": "speak",
      "scores": [0, 1, 2, 3, 4],
      "description": (
        "only speak, ask, answer, accuse, soft-claim, bluff, joke, or pressure without hard proof or ability use. Score meanings: "
        "Only voices at 'practically screaming' volume, not merely 'loud', can reach other tables or people in transit; consider that broadcast value when it is strategically necessary or emotionally overwhelming, but use it sparingly. "
        + speaking_score_meanings
      ),
    })

  available_scores = {option["action"]: option["scores"] for option in action_options}
  bid_dict = prompt_dict(
    run_gpt_prompt_act_bidding_unified(persona, table, action_options, action_context=action_context),
    {"reasoning": "I do not have a strong enough reason to seize attention right now.", "action": "none", "bid": "0"}
  )
  action = str(bid_dict.get("action", "none")).strip().lower()
  action, bid_score = normalize_choice(action, bid_dict.get("bid", 0), available_scores)
  if action == "speak":
    bid_score = SPEAK_MULTIPLIER * bid_score
  elif action == "ability":
    bid_score = ABILITY_MULTIPLIER * bid_score
  elif action == "reveal":
    bid_score = REVEAL_MULTIPLIER * bid_score
  reasoning = bid_dict.get("reasoning", "")
  persona.scratch.current_bidding_reasonings[action] = reasoning
  persona.scratch.current_bidding_scores[action] = bid_score
  persona.scratch.act_reasoning = reasoning or persona.scratch.act_reasoning
  debug_bid(persona, table, action, bid_score, reasoning)
  return bid_score


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
