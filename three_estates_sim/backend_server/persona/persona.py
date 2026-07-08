"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: persona.py
Description: Defines the Persona class that powers the agents in Reverie. 

Note (May 1, 2023) -- this is effectively GenerativeAgent class. Persona was
the term we used internally back in 2022, taking from our Social Simulacra 
paper.
"""
import math
import sys
import datetime
import random
import os
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from global_methods import *

from persona.memory_structures.associative_memory import *
from persona.memory_structures.scratch import *

from persona.cognitive_modules.perceive import *
from persona.cognitive_modules.retrieve import *
from persona.cognitive_modules.plan import *
from persona.cognitive_modules.reflect import *

class Persona: 
  def __init__(self, name, room, role, folder_mem_saved=False):
    # PERSONA BASE STATE 
    # <name> is the full name of the persona. This is a unique identifier for
    # the persona within Reverie. 
    self.name = name
    self.room = room
    # PERSONA MEMORY 
    # If there is already memory in folder_mem_saved, we load that. Otherwise,
    # we create new memory instances. 
    # <s_mem> is the persona's associative memory. 
    f_a_mem_saved = f"{folder_mem_saved}/associative_memory"
    self.a_mem = AssociativeMemory(self.name, f_saved=f_a_mem_saved)
    # <scratch> is the persona's scratch (short term memory) space. 
    scratch_saved = f"{folder_mem_saved}/scratch.json"
    self.scratch = Scratch(role, f_saved=scratch_saved)


  def save(self, save_folder): 
    """
    Save persona's current state (i.e., memory). 

    INPUT: 
      save_folder: The folder where we wil be saving our persona's state. 
    OUTPUT: 
      None
    """

    
    # Associative memory contains a csv with the following rows: 
    # [event.type, event.created, event.expiration, s, p, o]
    # e.g., event,2022-10-23 00:00:00,,Isabella Rodriguez,is,idle
    f_a_mem = f"{save_folder}/associative_memory"
    os.makedirs(f_a_mem, exist_ok=True)
    self.a_mem.save(f_a_mem)

    # Scratch contains non-permanent data associated with the persona. When 
    # it is saved, it takes a json form. When we load it, we move the values
    # to Python variables. 
    f_scratch = f"{save_folder}/scratch.json"
    self.scratch.save(f_scratch)


  def rebuild_recent_conversation_from_memory(self):
    nodes = [
      node for node in (self.a_mem.seq_event + self.a_mem.seq_chat)
      if node.created is not None and (self.scratch.curr_time <= datetime.timedelta(0) or node.created <= self.scratch.curr_time)
    ]
    nodes = sorted(nodes, key=lambda node: (node.created, node.node_count), reverse=True)

    batches = []
    for node in nodes:
      if not batches or batches[-1][0] != node.created:
        if len(batches) >= self.scratch.retention:
          break
        batches.append((node.created, []))
      batches[-1][1].append(node)

    self.scratch.recent_conversation = [
      (timestamp, list(reversed(batch_nodes)))
      for timestamp, batch_nodes in batches
    ]


  def maybe_stay_silent(self, table, reason):
    if not ENABLE_SPEAKING_COOLDOWN:
      return False
    if self.scratch.speaking_cooldown <= 0:
      return False
    act_desp = f"{self.scratch.name} stays quiet for now: {reason}"
    table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
    return True


  def possessive_for(self, persona=None):
    persona = persona or self
    return "her" if persona.scratch.gender == "female" else "his"


  def role_card_text(self, persona=None, role=None):
    persona = persona or self
    role = role or persona.scratch.role
    return f"{self.possessive_for(persona)} {role} card"


  def show_nun_protection(self, table, source_name, source_role, target_name, effect_description):
    target = table.personas[target_name]
    special_circumstance = (
      f"the {source_role} {source_name} is trying to {effect_description}, "
      "but the Nun card protects you. Show the Nun card to prove the protection, "
      "without revealing your actual private role card"
    )
    target.speak(table, special_circumstance)
    act_desp = (
      f"{target_name} reveals the Nun card protecting {target.possessive_for()} and is protected from "
      f"{source_name}'s {source_role} effect"
    )
    table.add_table_event((target_name, source_name, act_desp, self.scratch.curr_time, set([target_name, source_name, "Nun"])))


  def clear_active_locks_after_card_stolen(self, stolen_player_name, stolen_role, baron_name):
    if stolen_role not in {"King", "Queen", "Innkeeper"}:
      return
    stolen_player = self.room.personas.get(stolen_player_name)
    if not stolen_player:
      return
    cleared_any = False
    for table in self.room.locations.values():
      matching_locks = {
        lock for lock in table.lockdown_targets
        if lock[0] == stolen_player_name and lock[2] == stolen_role
      }
      if not matching_locks:
        continue
      table.lockdown_targets -= matching_locks
      cleared_any = True
      locked_targets = sorted(lock[1] for lock in matching_locks)
      keywords = set([stolen_player_name, baron_name, stolen_role] + locked_targets)
      if stolen_role == "King":
        locked_families = sorted({
          ROLE_DICT[self.room.personas[target].scratch.role]["family"]
          for target in locked_targets
          if target in self.room.personas
        })
        family_text = ", ".join(locked_families) if locked_families else "the targeted family"
        act_desp = (
          f"{stolen_player_name}'s lockdown ability as King against {family_text} is nullified "
          f"because {baron_name} stole {stolen_player.possessive_for()} King card."
        )
      else:
        targets_text = ", ".join(locked_targets) if locked_targets else "the locked target"
        act_desp = (
          f"{stolen_player_name}'s lockdown ability as {stolen_role} on {targets_text} is nullified "
          f"because {baron_name} stole {stolen_player.possessive_for()} {stolen_role} card."
        )
      table.add_table_event((baron_name, stolen_player_name, act_desp, self.scratch.curr_time, keywords))

    if cleared_any:
      remaining_targets = []
      remaining_locations = set()
      for table_name, table in self.room.locations.items():
        for benefactor, target, role in table.lockdown_targets:
          if benefactor == stolen_player_name and role == stolen_role:
            remaining_targets.append(target)
            remaining_locations.add(table_name)
      stolen_player.scratch.ability_objects = remaining_targets
      stolen_player.scratch.ability_locations = remaining_locations
      stolen_player.scratch.ability_active = bool(remaining_targets)


  def resolve_baron_reaction(self, table, revealed_player_name, action_context, block_ability=True):
    if len(table.personas) < 3 or revealed_player_name not in table.personas:
      return False
    revealed_player = table.personas[revealed_player_name]
    if (
      revealed_player.scratch.role == "Farmer"
      or (revealed_player.scratch.nun_protected and "Nun" in revealed_player.scratch.cards_slot)
    ):
      return False
    if revealed_player.scratch.role not in revealed_player.scratch.cards_slot:
      return False

    for baron_name, baron in table.personas.items():
      if baron_name == revealed_player_name:
        continue
      if baron.scratch.role != "Baron" or "Baron" not in baron.scratch.cards_slot:
        continue

      baron.update_knowledge(self.room)
      decision = prompt_dict(
        run_gpt_prompt_decide_baron_block(baron, table, revealed_player, action_context),
        {"reasoning": "I will not reveal myself as Baron for this trigger.", "result": "no"}
      )
      result = str(decision["result"]).strip().lower()
      reasoning = decision["reasoning"]
      debug_log(
        f"[BARON-REACTION] t={self.scratch.curr_time} | table={table.name} | "
        f"baron={baron_name} | target={revealed_player_name} | result={result} | "
        f"reasoning={reasoning}"
      )
      if result != "yes":
        continue

      stolen_role = revealed_player.scratch.role
      special_circumstance = (
        f"you are revealing your Baron card right now to react to {revealed_player_name}'s action "
        f"and steal the {stolen_role} card now. This is happening in this moment; do not imply "
        f"that you already had {revealed_player_name}'s {stolen_role} card before this reaction"
      )
      if block_ability:
        special_circumstance += f", blocking {revealed_player_name}'s {stolen_role} ability before it resolves"
      else:
        special_circumstance += " after their reveal has already been made"
      baron.speak(table, special_circumstance)
      revealed_player.scratch.cards_slot.discard(stolen_role)
      baron.scratch.cards_slot.add(stolen_role)
      if block_ability:
        act_desp = f"{baron_name} reveals {self.role_card_text(baron, 'Baron')}, blocks {revealed_player_name}'s {stolen_role} ability, and steals the {stolen_role} card."
      else:
        act_desp = f"{baron_name} reveals {self.role_card_text(baron, 'Baron')} after {revealed_player_name}'s reveal and steals the {stolen_role} card."
      table.add_table_event((baron_name, revealed_player_name, act_desp, self.scratch.curr_time, set([baron_name, revealed_player_name])))
      self.clear_active_locks_after_card_stolen(revealed_player_name, stolen_role, baron_name)
      return True
    return False


  def perceive(self, room):
    """
    This function takes the current room, and returns events that are 
    happening around the persona. Importantly, perceive is guided by 
    two key hyper-parameter for the  persona: 1) att_bandwidth, and 
    2) retention. 

    First, <att_bandwidth> determines the number of nearby events that the 
    persona can perceive. Say there are 10 events that are within the vision
    radius for the persona -- perceiving all 10 might be too much. So, the 
    persona perceives the closest att_bandwidth number of events in case there
    are too many events. 

    Second, the persona does not want to perceive and think about the same 
    event at each time step. That's where <retention> comes in -- there is 
    temporal order to what the persona remembers. So if the persona's memory
    contains the current surrounding events that happened within the most 
    recent retention, there is no need to perceive that again. xx

    INPUT: 
      room: Current <room> instance of the world. 
    OUTPUT: 
      a list of <ConceptNode> that are perceived and new. 
        See associative_memory.py -- but to get you a sense of what it 
        receives as its input: "s, p, o, desc, persona.scratch.curr_time"
    """
    return perceive(self, room)


  def retrieve(self, room, self_table_perceived, other_tables_perceived):
    """
    This function takes the events that are perceived by the persona as input
    and returns a set of related events and thoughts that the persona would 
    need to consider as context when planning. 

    INPUT: 
      perceive: a list of <ConceptNode> that are perceived and new.  
    OUTPUT: 
      retrieved: dictionary of dictionary. The first layer specifies an event,
                 while the latter layer specifies the "curr_event", "events", 
                 and "thoughts" that are relevant.
    """
    return retrieve(self, room, self_table_perceived, other_tables_perceived)


  def reflect(self):
    """
    Reviews the persona's memory and create new thoughts based on it. 

    INPUT: 
      None
    OUTPUT: 
      None
    """
    reflect(self)

  def update_knowledge(self, room):
    self_table_perceived, other_tables_perceived = self.perceive(self.room)
    retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = self.retrieve(room, self_table_perceived, other_tables_perceived)
    self.scratch.retrieved = (retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables)

  def normalize_speech_dict(self, table, speak_dict=None):
    default_line = {
      "reasoning": "I need to say something brief and relevant.",
      "object": "everyone",
      "volume": "calm",
      "line": "I need a moment to think this through.",
    }
    speak_dict = {**default_line, **(speak_dict or {})}
    if speak_dict["object"] not in table.personas and speak_dict["object"] != "everyone":
      speak_dict["object"] = "everyone"
    if speak_dict["volume"] not in {"whisper", "calm", "loud", "practically screaming"}:
      speak_dict["volume"] = "calm"
    speak_dict["line"] = str(speak_dict.get("line") or default_line["line"]).strip() or default_line["line"]
    return speak_dict

  def emit_speech_dict(self, table, speak_dict, consume_cooldown=True):
    speak_dict = self.normalize_speech_dict(table, speak_dict)
    table.add_table_dialogue((self.scratch.name, speak_dict["object"], speak_dict["volume"], speak_dict["line"], self.scratch.curr_time, set([self.scratch.name, speak_dict["object"]])))
    if consume_cooldown and ENABLE_SPEAKING_COOLDOWN:
      self.scratch.speaking_cooldown = max(self.scratch.speaking_cooldown, SPEAKING_COOLDOWN_STEPS + 1)
    return speak_dict

  def speak(self, table, special_circumstance=None, consume_cooldown=True):
    self.update_knowledge(self.room)
    default_line = self.normalize_speech_dict(table)
    if special_circumstance:
      speak_dict = prompt_dict(run_gpt_prompt_generate_next_convo_line_special(self, table, special_circumstance), default_line)
    else:
      speak_dict = prompt_dict(run_gpt_prompt_generate_next_convo_line_normal(self, table), default_line)
    return self.emit_speech_dict(table, speak_dict, consume_cooldown=consume_cooldown)

  def select_ability_target(self, table, ability_reasoning=""):
    movement_reasoning = self.scratch.current_movement_reasoning
    movement_destination = self.scratch.current_movement_destination
    enriched_ability_reasoning = ability_reasoning or ""
    if self.scratch.role in {"Queen", "Spinster"} and movement_reasoning:
      destination_note = f" toward {movement_destination}" if movement_destination else ""
      movement_context = (
        f"When choosing this ability target, also consider that your current movement/departure reasoning{destination_note} was: "
        f"{movement_reasoning}"
      )
      enriched_ability_reasoning = (
        f"{enriched_ability_reasoning}\n{movement_context}"
        if enriched_ability_reasoning
        else movement_context
      )
    possible_targets = list(set(table.personas.keys()) - {self.scratch.name})
    if self.scratch.role == "King":
      fallback = ROLE_DICT[self.scratch.role]["family"]
      family_options = {ROLE_DICT[player.scratch.role]["family"] for player in table.personas.values()}
      target_dict = prompt_dict(run_gpt_prompt_select_ability_target(self, table, enriched_ability_reasoning), {"target": fallback})
      requested_target = target_dict["target"]
      final_target = requested_target if requested_target in family_options else fallback
      debug_ability_target(self, table, requested_target, final_target, enriched_ability_reasoning)
      return final_target
    fallback = possible_targets[0] if possible_targets else self.scratch.name
    target_dict = prompt_dict(run_gpt_prompt_select_ability_target(self, table, enriched_ability_reasoning), {"target": fallback})
    requested_target = target_dict["target"]
    final_target = requested_target if requested_target in possible_targets else fallback
    debug_ability_target(self, table, requested_target, final_target, enriched_ability_reasoning)
    return final_target

  def guess_family_bishop(self, target, table):
    return prompt_dict(
      run_gpt_prompt_guess_family_bishop(self, target, table),
      {"reasoning": "I have to make my best guess from limited evidence.", "guess": "Commoners"}
    )

  def respond_to_wrong_bishop_guess(self, bishop, guessed_family, table):
    default_response = {
      "reasoning": "I will not give the table a verified reveal just because the Bishop guessed wrong.",
      "response": "no reveal",
      "object": bishop.scratch.name,
      "volume": "calm",
      "line": "Wrong, but I am not handing you proof for free.",
    }
    response_dict = prompt_dict(
      run_gpt_prompt_bishop_wrong_guess_response(self, bishop, guessed_family, table),
      default_response
    )
    response = str(response_dict.get("response", "no reveal")).strip().lower()
    if response not in {"hard reveal", "soft reveal", "no reveal"}:
      response = "no reveal"
    if response == "hard reveal" and self.scratch.role not in self.scratch.cards_slot:
      response = "no reveal"
      response_dict["line"] = "That guess is wrong, but I cannot prove it with a card right now."
    obj = response_dict.get("object", "everyone")
    if obj not in table.personas and obj != "everyone":
      obj = "everyone"
    volume = response_dict.get("volume", "calm")
    if volume not in {"whisper", "calm", "loud", "practically screaming"}:
      volume = "calm"
    line = response_dict.get("line", "That guess is wrong.")
    table.add_table_dialogue((self.scratch.name, obj, volume, line, self.scratch.curr_time, set([self.scratch.name, obj])))
    if ENABLE_SPEAKING_COOLDOWN:
      self.scratch.speaking_cooldown = max(self.scratch.speaking_cooldown, SPEAKING_COOLDOWN_STEPS + 1)
    debug_log(
      f"[BISHOP-WRONG-RESPONSE] t={self.scratch.curr_time} | table={table.name} | "
      f"bishop={bishop.scratch.name} | target={self.scratch.name} | guessed_family={guessed_family} | "
      f"response={response} | reasoning={response_dict.get('reasoning', '')}"
    )
    if response == "hard reveal":
      act_desp = (
        f"{self.scratch.name} reveals {self.role_card_text()} to prove "
        f"the Bishop {bishop.scratch.name}'s guess of {guessed_family} was wrong"
      )
      table.add_table_event((self.scratch.name, bishop.scratch.name, act_desp, self.scratch.curr_time, set([self.scratch.name, bishop.scratch.name])))
      self.resolve_baron_reaction(table, self.scratch.name, act_desp, block_ability=False)

  def card_retrieval_options(self, table):
    options = []
    nun_holder_names = set()
    if self.scratch.role == "Nun":
      possible_holders = set(self.scratch.ability_objects or []) if self.scratch.ability_active else set()
      possible_holders.update(
        name
        for name, player in table.personas.items()
        if player.scratch.nun_protected and "Nun" in player.scratch.cards_slot
      )
      for holder_name in sorted(possible_holders):
        if (
          holder_name in table.personas
          and "Nun" in table.personas[holder_name].scratch.cards_slot
          and table.personas[holder_name].scratch.nun_protected
        ):
          nun_holder_names.add(holder_name)
          options.append({
            "target": holder_name,
            "kind": "nun",
            "description": f"retrieve your Nun card from {holder_name} and revoke their protection"
          })
    if len(table.personas) == 2:
      remaining = set(table.personas.keys()) - {self.scratch.name}
      if len(remaining) == 1:
        other_name = next(iter(remaining))
        other = table.personas[other_name]
        if (
          other_name not in nun_holder_names
          and other.scratch.role == "Baron"
          and self.scratch.role in other.scratch.cards_slot
        ):
          options.append({
            "target": other_name,
            "kind": "baron",
            "description": f"retrieve your {self.scratch.role} card from {other_name}"
          })
    return options

  def decide_innkeeper_declaration(self, table, source_table):
    self.update_knowledge(self.room)
    decision = prompt_dict(
      run_gpt_prompt_decide_innkeeper_declaration(self, table, source_table),
      {"reasoning": "I will not reveal myself as Innkeeper on this entry.", "result": "no"}
    )
    result = str(decision["result"]).strip().lower()
    debug_log(
      f"[INNKEEPER-DECLARE] t={self.scratch.curr_time} | table={table.name} | "
      f"character={self.scratch.name} | source_table={source_table} | "
      f"result={result} | reasoning={decision['reasoning']}"
    )
    return result == "yes", decision["reasoning"]

  def decide_movement_ability_use(self, table, destination, movement_reasoning_override=None):
    movement_reasoning = movement_reasoning_override
    if movement_reasoning is None:
      movement_reasoning = self.scratch.current_movement_reasoning or ""
    decision = prompt_dict(
      run_gpt_prompt_decide_movement_ability_use(self, table, destination, movement_reasoning),
      {"reasoning": "I will leave without revealing my movement-triggered ability right now.", "result": "no"}
    )
    result = str(decision["result"]).strip().lower()
    debug_log(
      f"[MOVEMENT-ABILITY] t={self.scratch.curr_time} | table={table.name} | "
      f"character={self.scratch.name} | role={self.scratch.role} | destination={destination} | "
      f"result={result} | movement_reasoning={movement_reasoning} | ability_reasoning={decision['reasoning']}"
    )
    return result == "yes", decision["reasoning"]

  def movement_departure_records(self, table, destination):
    role = self.scratch.role
    normal_record = {
      "name": self.scratch.name,
      "destination": destination,
      "benefactor": None,
      "farewell": True,
      "event_msg": f"{self.scratch.name} leaves for {destination}.",
    }
    if role not in {"Queen", "Spinster"}:
      return [normal_record]
    if role not in self.scratch.cards_slot:
      return [normal_record]
    if role == "Spinster" and table.name != "Forest":
      return [normal_record]
    if len(table.personas) <= 1:
      return [normal_record]

    should_use, ability_reasoning = self.decide_movement_ability_use(table, destination)
    if not should_use:
      normal_record["speech_constraint"] = (
        f"you explicitly chose not to reveal/use your {role} ability for this departure; "
        "do not say or imply that anyone is forced to follow you"
      )
      return [normal_record]

    target_name = self.select_ability_target(table, ability_reasoning)
    poss = self.possessive_for()
    obj = "her" if self.scratch.gender == "female" else "him"
    movement_reasoning = self.scratch.current_movement_reasoning or "I had already decided to leave."

    if role == "Queen":
      ability_attempt_context = (
        f"{self.scratch.name} reveals {self.role_card_text(role='Queen')} and attempts to use {poss} Queen ability "
        f"on {target_name}."
      )
      self.speak(
        table,
        f"you had already decided to leave for {destination} because {movement_reasoning}; "
        f"now you are revealing your Queen card and trying to make {target_name} follow you. "
        f"Your ability-use reasoning was: {ability_reasoning}",
        consume_cooldown=False,
      )
      table.add_table_event((self.scratch.name, target_name, ability_attempt_context, self.scratch.curr_time, set([self.scratch.name, target_name])))
      if self.resolve_baron_reaction(table, self.scratch.name, ability_attempt_context, block_ability=True):
        normal_record["farewell"] = False
        return [normal_record]

      self.scratch.ability_active = True
      target = table.personas[target_name]
      target.speak(
        table,
        f"the Queen has just activated {poss} ability after deciding to leave for {destination}, chose you as the target, and is about to drag you there, as parting words,",
        consume_cooldown=False,
      )
      event_msg = (
        f"{self.scratch.name} reveals {self.role_card_text(role='Queen')} and leaves for {destination} "
        f"while dragging {target_name} with {obj} using {poss} ability."
      )
      table.add_table_event((self.scratch.name, target_name, event_msg, self.scratch.curr_time, set([self.scratch.name, target_name])))
      return [
        {"name": self.scratch.name, "destination": destination, "benefactor": None, "farewell": False, "event_msg": None},
        {"name": target_name, "destination": destination, "benefactor": self.scratch.name, "farewell": False, "event_msg": None},
      ]

    if role == "Spinster":
      ability_attempt_context = (
        f"{self.scratch.name} reveals {self.role_card_text(role='Spinster')} and attempts to use {poss} Spinster ability "
        f"on {target_name} while leaving the Forest for {destination}."
      )
      self.speak(
        table,
        f"you had already decided to leave the Forest for {destination} because {movement_reasoning}; "
        f"now you are revealing your Spinster card and marking {target_name}. "
        f"Your ability-use reasoning was: {ability_reasoning}",
        consume_cooldown=False,
      )
      table.add_table_event((self.scratch.name, target_name, ability_attempt_context, self.scratch.curr_time, set([self.scratch.name, target_name])))

      return [
        {
          "name": self.scratch.name,
          "destination": destination,
          "benefactor": None,
          "farewell": False,
          "event_msg": None,
          "spinster_reveal_target": target_name,
        }
      ]

    return [normal_record]

  def resolve_spinster_forced_reveal(self, table, target_name):
    if target_name not in table.personas:
      return
    target = table.personas[target_name]
    if target.scratch.nun_protected and "Nun" in target.scratch.cards_slot:
      self.show_nun_protection(
        table,
        self.scratch.name,
        "Spinster",
        target_name,
        "force you to reveal your role card"
      )
      act_desp = (
        f"{target_name} is forced by the departing Spinster {self.scratch.name} to reveal a role card, "
        "but reveals the Nun card protecting them instead, so the forced reveal fails"
      )
      table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([target_name, self.scratch.name, "Nun"])))
      return
    if target.scratch.role not in target.scratch.cards_slot:
      special_circumstance = (
        f"the departing Spinster {self.scratch.name} has forced you to reveal your role card, "
        "but you do not currently have your own role card and therefore cannot prove/reveal it"
      )
      target.speak(table, special_circumstance)
      act_desp = (
        f"{target_name} is forced by the departing Spinster {self.scratch.name} to reveal a role card, "
        "but cannot produce their own role card, so the forced reveal fails"
      )
      table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([target_name, self.scratch.name])))
      return
    if target.scratch.role == "Farmer":
      special_circumstance = (
        f"the departing Spinster {self.scratch.name} has forced you to reveal your Farmer card. "
        "You are normally immune to other players' abilities, but in this oddly useless edge case "
        "the card reveal is also how you prove you are Farmer, so lampshade that the proof still has to happen "
        "and do not describe this as immunity preventing the reveal. "
        "The Baron cannot block the Spinster forcing this reveal, but a Baron may still react to the card you reveal afterward"
      )
    else:
      special_circumstance = (
        f"the departing Spinster {self.scratch.name} has forced you to reveal "
        f"your {target.scratch.role} card to the table. The Baron cannot block the Spinster forcing this reveal, "
        "but a Baron may still react to the card you reveal afterward"
      )
    target.speak(table, special_circumstance)
    act_desp = (
      f"{target_name} is forced by the departing Spinster {self.scratch.name} "
      f"to reveal {target.possessive_for()} {target.scratch.role} card"
    )
    table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([target_name, self.scratch.name])))
    target.resolve_baron_reaction(table, target_name, act_desp, block_ability=False)

  def make_spinster_endgame_guesses(self, table):
    self.update_knowledge(self.room)
    target_names = [name for name in table.personas if name != self.scratch.name]
    fallback_guesses = {
      name: self.scratch.endgame_role_guesses.get(name, "King")
      for name in target_names
    }
    guess_dict = prompt_dict(
      run_gpt_prompt_spinster_endgame_guess(self, table),
      {
        "reasoning": "I must make my final guesses from incomplete evidence.",
        "line": "The timers are gone; now my guesses decide whether this table's endings turn inside out.",
        "guesses": fallback_guesses
      }
    )
    raw_guesses = guess_dict.get("guesses", {})
    if not isinstance(raw_guesses, dict):
      raw_guesses = {}
    normalized_guesses = {str(name).strip().lower(): role for name, role in raw_guesses.items()}
    valid_roles = set(ROLE_DICT.keys())
    guesses = {}
    for name in target_names:
      guess = raw_guesses.get(name, normalized_guesses.get(name.lower(), fallback_guesses.get(name, "King")))
      guesses[name] = guess if guess in valid_roles else "King"

    line = str(guess_dict.get("line") or "The timers are gone; now my guesses decide whether this table's endings turn inside out.").strip()
    if not line:
      line = "The timers are gone; now my guesses decide whether this table's endings turn inside out."
    table.add_table_dialogue((self.scratch.name, "everyone", "calm", line, self.scratch.curr_time, set([self.scratch.name] + target_names)))

    self.scratch.endgame_role_guesses = guesses
    guess_text = ", ".join(f"{name} as {role}" for name, role in guesses.items()) or "no other players"
    debug_log(
      f"[SPINSTER-ENDGAME-GUESS] t={self.scratch.curr_time} | table={table.name} | "
      f"character={self.scratch.name} | guesses={guesses} | reasoning={guess_dict.get('reasoning')} | line={line}"
    )
    act_desp = f"{self.scratch.name} makes final Spinster role guesses: {guess_text}."
    table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name] + target_names + list(guesses.values()))))
    return guesses

  def select_ability_destination(self, table, retrieved_all_tables, special_circumstance):
    fallback = next(iter(set(retrieved_all_tables.keys()) - {table.name}), table.name)
    destination_dict = prompt_dict(
      run_gpt_prompt_select_ability_destination(self, table, retrieved_all_tables, special_circumstance),
      {
        "reasoning": "I will choose the safest available table.",
        "summary": "Move to the safest available table for this ability resolution.",
        "option": fallback
      }
    )
    requested_option = destination_dict["option"]
    option = requested_option
    if option == table.name or option not in self.room.locations[table.name].connected:
      option = fallback
    full_reasoning = destination_dict["reasoning"]
    summary = compact_summary_text(destination_dict.get("summary"), full_reasoning)
    self.scratch.current_movement_reasoning = summary
    self.scratch.current_movement_destination = option
    if self.scratch.role in {"Queen", "Spinster"}:
      ability_reasoning = (self.scratch.current_bidding_reasonings or {}).get("ability")
      reasoning = full_reasoning
      compact_reasoning = summary
      if ability_reasoning:
        reasoning = (
          f"I chose to use my {self.scratch.role} ability because {ability_reasoning} "
          f"For the destination, {reasoning}"
        )
        compact_reasoning = compact_summary_text(
          f"{summary}",
          summary
        )
      debug_movement(self, table, requested_option, option, reasoning, compact_reasoning)
      remember_movement_reasoning(self, table, requested_option, option, compact_reasoning)
    return option

  
  def act(self, table):
    _, _, _, _, retrieved_all_tables = self.scratch.retrieved
    act_scores = self.scratch.current_bidding_scores
    action_tie_break_priority = {
      "retrieve": 4,
      "speak": 3,
      "ability": 2,
      "nun-reveal": 1,
      "reveal": -1,
    }
    act_scores = [
      (option, points)
      for option, points in sorted(
        act_scores.items(),
        key=lambda item: (item[1], action_tie_break_priority.get(item[0], -2)),
        reverse=True,
      )
    ]
    final_option = act_scores[0][0]
    obj = "her" if self.scratch.gender == "female" else "him"
    subj = "she" if self.scratch.gender == "female" else "he"
    poss = self.possessive_for()
    action_role = self.scratch.role

    def with_winning_act_reasoning(special_circumstance, action_kind):
      act_reasoning = (self.scratch.current_bidding_reasonings or {}).get(action_kind)
      if not act_reasoning:
        return special_circumstance
      return (
        f"{special_circumstance}. When you won the internal bid for this {action_kind} action, "
        f"your reasoning was: {act_reasoning}"
      )

    def with_optional_speaking_reasoning(special_circumstance):
      speak_reasoning = (self.scratch.current_bidding_reasonings or {}).get("speak")
      if not speak_reasoning:
        return special_circumstance
      return (
        f"{special_circumstance}. Optional context for the line, if useful but not required: "
        f"when considering whether to otherwise simply speak without revealing or ability use, you were thinking: {speak_reasoning}"
      )

    if act_scores[0][1] == 0:
      self.scratch.act_reasoning = "neither me nor anyone else has made a special move, business as usual so it's a bit awkward"
      if not self.maybe_stay_silent(table, "they recently spoke and no action won the table's attention"):
        self.speak(table)
      return

    if final_option == "ability":
      if action_role not in self.scratch.cards_slot:
        act_desp = f"{self.scratch.name} reaches for {self.role_card_text(role=action_role)}, but cannot use the ability because {subj} does not have it."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
        if not self.maybe_stay_silent(table, "they cannot prove their role card right now"):
          self.speak(table, f"you cannot use your {action_role} ability because you do not currently have your role card")
        return

      if action_role == "Innkeeper":
        if table.name == "Village":
          self.scratch.act_reasoning = "I am already in the Village, so I need to leave and re-enter before using the Innkeeper ability."
          if not self.maybe_stay_silent(table, "they cannot activate the Innkeeper ability while already in the Village"):
            self.speak(table)
          return
        self.speak(
          table,
          with_optional_speaking_reasoning(
            with_winning_act_reasoning(
              "you have decided to leave for the Village, where you may reveal your Innkeeper card and declare on arrival; say what you want this table to hear before you depart. You are not revealing or proving your Innkeeper card at this departure table",
              "ability",
            )
          ),
          consume_cooldown=False,
        )
        table.removal_targets.add((None, self.scratch.name, action_role, "Village"))
        self.scratch.ability_active = True
        act_desp = f"{self.scratch.name} leaves for Village."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
        return

      if len(table.personas.keys()) <= 1:
        self.scratch.act_reasoning = "neither me nor anyone else has made a special move, business as usual so it's a bit awkward"
        if not self.maybe_stay_silent(table, "there is no valid ability target"):
          self.speak(table)
        return

      if action_role in {"Priest", "Thief", "Nun"}:
        remaining = set(table.personas.keys()) - {self.scratch.name}
        if len(remaining) != 1:
          raise ValueError("Expected exactly one other persona")
        target_name = next(iter(remaining))
      else:
        target_name = self.select_ability_target(table, (self.scratch.current_bidding_reasonings or {}).get("ability", ""))

      if action_role == "Thief" and thief_reverse_swap_locked(table, self.scratch.name):
        self.scratch.act_reasoning = (
          "I cannot immediately reverse this exact Thief swap while the same two of us remain alone; "
          "the table state must change first."
        )
        if not self.maybe_stay_silent(table, "the reverse Thief swap is currently locked"):
          self.speak(
            table,
            "you considered using your Thief ability, but this exact two-player swap cannot be immediately reversed until the table state changes; speak instead if you want to acknowledge the stalemate",
          )
        return

      ability_attempt_context = f"{self.scratch.name} reveals {self.role_card_text(role=action_role)} and attempts to use {poss} {action_role} ability on {target_name}."
      self.speak(
        table,
        with_optional_speaking_reasoning(
          with_winning_act_reasoning(
            f"you are revealing your {action_role} card and attempting to use your ability on {target_name}; say what you want the table to hear before the ability resolves",
            "ability",
          )
        )
      )
      table.add_table_event((self.scratch.name, target_name, ability_attempt_context, self.scratch.curr_time, set([self.scratch.name, target_name])))
      if action_role != "Spinster" and self.resolve_baron_reaction(table, self.scratch.name, ability_attempt_context, block_ability=True):
        return

      if action_role == "King":
        self.scratch.ability_active = True
        for other_player_name, other_player in table.personas.items():
          if other_player_name != self.scratch.name and ROLE_DICT[other_player.scratch.role]["family"] == target_name:
            if other_player.scratch.nun_protected and "Nun" in other_player.scratch.cards_slot:
              self.show_nun_protection(
                table,
                self.scratch.name,
                "King",
                other_player_name,
                "lock you at this table"
              )
            elif other_player.scratch.role == "Farmer":
              special_circumstance = f"the King {self.scratch.name} is trying to use {poss} ability on you and you have to reveal your Farmer card to prove you're immune,"
              act_desp = f"{other_player_name} reveals {self.role_card_text(other_player, 'Farmer')}"
              table.add_table_event((other_player_name, None, act_desp, self.scratch.curr_time, set([other_player_name])))
              other_player.speak(table, special_circumstance)
            else:
              table.lockdown_targets.add((self.scratch.name, other_player_name, action_role))
              self.scratch.ability_objects.append(other_player_name)
              self.scratch.ability_locations.add(table.name)
        act_desp = f"{self.scratch.name} reveals {self.role_card_text(role='King')} and uses {poss} ability to lock down all present {target_name} at {table.name}"
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name] + self.scratch.ability_objects)))
        return

      target = table.personas[target_name]

      if action_role == "Nun":
        self.scratch.ability_active = True
        self.scratch.cards_slot.discard("Nun")
        self.scratch.ability_objects.append(target_name)
        target.scratch.cards_slot.add("Nun")
        target.scratch.nun_protected = True
        act_desp = f"{self.scratch.name} reveals {self.role_card_text(role='Nun')} and uses {poss} ability by giving {poss} card to protect {target_name}"
        table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))
        return

      if target.scratch.nun_protected and "Nun" in target.scratch.cards_slot:
        self.show_nun_protection(
          table,
          self.scratch.name,
          action_role,
          target_name,
          "use an ability on you"
        )
        return

      if target.scratch.role == "Farmer" and action_role == "Priest":
        special_circumstance = (
          f"the Priest {self.scratch.name} is using {poss} ability on you and technically forces you to reveal your Farmer card. "
          "You are normally immune to other players' abilities, but the only way to prove that you are Farmer is to reveal the Farmer card, "
          "so lampshade the awkward paradox and do not describe this as immunity preventing the reveal"
        )
        target.speak(table, special_circumstance)
        act_desp = f"the Priest {self.scratch.name} forces {target_name} to reveal {self.role_card_text(target, 'Farmer')}"
        table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))
        return

      if target.scratch.role == "Farmer":
        special_circumstance = f"the {action_role} {self.scratch.name} is trying to use {poss} ability on you and you have to reveal your Farmer card to prove you're immune,"
        act_desp = f"{target_name} reveals {self.role_card_text(target, 'Farmer')}"
        table.add_table_event((target_name, None, act_desp, self.scratch.curr_time, set([target_name])))
        target.speak(table, special_circumstance)
        return

      if action_role == "Thief":
        if target.scratch.role not in target.scratch.cards_slot:
          special_circumstance = f"the Thief {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
          target.speak(table, special_circumstance)
        else:
          old_role = self.scratch.role
          target_old_role = target.scratch.role
          thief_extra_cards = set(self.scratch.cards_slot) - {old_role}
          target_extra_cards = set(target.scratch.cards_slot) - {target_old_role}
          self.scratch.cards_slot.discard(old_role)
          self.scratch.cards_slot.add(target_old_role)
          if target_old_role == "Baron":
            self.scratch.cards_slot.update(target_extra_cards)
            target.scratch.cards_slot.difference_update(target_extra_cards)
          self.scratch.role = target_old_role
          target.scratch.cards_slot.discard(target_old_role)
          target.scratch.cards_slot.add(old_role)
          if old_role == "Baron":
            target.scratch.cards_slot.update(thief_extra_cards)
            self.scratch.cards_slot.difference_update(thief_extra_cards)
          target.scratch.role = old_role
          self.scratch.movement_cooldown = 0
          add_thief_swap_lock(table, self.scratch.name, target_name)
          act_desp = f"{self.scratch.name} reveals {self.role_card_text(role=old_role)} and forcefully swaps cards with {target_name}. {target_name} is the Thief now while {self.scratch.name} is now {self.scratch.role}"
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))
          special_circumstance = (
            f"the Thief {self.scratch.name} has just successfully swapped roles and cards with you. "
            f"You were {target_old_role}, but now you are the Thief, while {self.scratch.name} is now {self.scratch.role}. "
            "React in the moment to this successful forced swap"
          )
          target.speak(table, special_circumstance)

      elif action_role == "Queen":
        self.scratch.ability_active = True
        special_circumstance = f"you, as Queen, have just activated your ability to force {target_name} to follow you"
        next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
        table.removal_targets.add((None, self.scratch.name, action_role, next_loc))
        table.removal_targets.add((self.scratch.name, target_name, action_role, next_loc))
        special_circumstance = f"the Queen has just activated {poss} ability, chose you as the target, and are about to drag you to depart to the {next_loc}, as parting words,"
        target.speak(table, special_circumstance, consume_cooldown=False)
        event_msg = f"{self.scratch.name} reveals {self.role_card_text(role='Queen')} and leaves for {next_loc} while dragging {target_name} with {obj} using {poss} ability."
        table.add_table_event((self.scratch.name, target_name, event_msg, self.scratch.curr_time, set([self.scratch.name, target_name])))

      elif action_role == "Spinster":
        special_circumstance = f"you, as Spinster, have just activated your ability"
        next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
        table.removal_targets.add((None, self.scratch.name, action_role, next_loc, target_name))
        act_desp = f"{self.scratch.name} leaves for {next_loc} after marking {target_name} with {poss} Spinster ability."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))

      elif action_role == "Priest":
        if target.scratch.role not in target.scratch.cards_slot:
          special_circumstance = f"the Priest {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
          target.speak(table, special_circumstance)
        else:
          special_circumstance = f"the Priest {self.scratch.name} has used {poss} ability on you and now you HAVE to show or state your {target.scratch.role} card to {obj},"
          target.speak(table, special_circumstance)
          act_desp = f"the Priest {self.scratch.name} forces {target_name} to reveal {self.role_card_text(target, target.scratch.role)}"
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))

      elif action_role == "Bishop":
        guess = self.guess_family_bishop(target, table)["guess"]
        special_circumstance = f"you, as Bishop, have just made an internal guess that {target_name}'s family is {guess}, which you now want to annnounce to the target and to the table"
        if guess != ROLE_DICT[target.scratch.role]["family"]:
          target.respond_to_wrong_bishop_guess(self, guess, table)
        else:
          target_choice_context = (
            f"the Bishop {self.scratch.name} correctly guessed your family as {guess}; "
            "you, the target of the Bishop ability, must choose which other table to leave for"
          )
          next_loc = target.select_ability_destination(table, retrieved_all_tables, target_choice_context)
          special_circumstance = f"you have just been correctly guessed by the Bishop {self.scratch.name} as family {guess} and now have to leave for {next_loc}"
          table.removal_targets.add((self.scratch.name, target_name, action_role, next_loc))
          target.speak(table, special_circumstance, consume_cooldown=False)
          act_desp = f"the Bishop {self.scratch.name} correctly guesses {target_name}'s family as {guess} and the latter has to leave for {next_loc}"
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))

    elif final_option == "reveal":
      if action_role not in self.scratch.cards_slot:
        act_desp = f"{self.scratch.name} tries to reveal {self.role_card_text(role=action_role)}, but cannot prove it because {subj} does not have that role card."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
        if not self.maybe_stay_silent(table, "they cannot prove their role card right now"):
          self.speak(table, f"you want to reveal your {action_role} card, but you cannot prove it because you do not currently have your role card")
        return
      self.speak(
        table,
        with_optional_speaking_reasoning(
          with_winning_act_reasoning(
            f"you are revealing your {action_role} card without using your ability; say what you want the table to hear as/accompanying this reveal",
            "reveal",
          )
        )
      )
      act_desp = f"{self.scratch.name} reveals {self.role_card_text(role=action_role)} without using {poss} ability"
      table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
      self.resolve_baron_reaction(table, self.scratch.name, act_desp, block_ability=False)

    elif final_option == "nun-reveal":
      if not (self.scratch.role != "Nun" and self.scratch.nun_protected and "Nun" in self.scratch.cards_slot):
        act_desp = f"{self.scratch.name} tries to show the Nun card protecting {obj}, but cannot produce it."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name, "Nun"])))
        return
      self.speak(
        table,
        with_optional_speaking_reasoning(
          with_winning_act_reasoning(
            "you are showing the Nun card currently protecting you. This proves you are protected by the Nun card, but it does NOT reveal or prove your actual private role card",
            "nun-reveal",
          )
        )
      )
      act_desp = f"{self.scratch.name} reveals the Nun card protecting {obj}, without revealing {poss} actual role card"
      table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name, "Nun"])))

    elif final_option == "retrieve":
      retrieval_options = self.card_retrieval_options(table)
      if not retrieval_options:
        act_desp = f"{self.scratch.name} considers retrieving a card, but no valid retrieval condition is currently met."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
        return
      target_name = retrieval_options[0]["target"]
      retrieval_reasoning = (self.scratch.current_bidding_reasonings or {}).get("retrieve", "")
      self.retrieve_card(table, target_name, ask=False, kind=retrieval_options[0]["kind"], action_reasoning=retrieval_reasoning)

    else:
      self.speak(table)

  
  def retrieve_card(self, table, object, ask=True, kind=None, action_reasoning=""):
    poss = "her" if self.scratch.gender == "female" else "his"
    if kind is None:
      kind = "nun" if (
        self.scratch.role == "Nun"
        and (
          object in (self.scratch.ability_objects or [])
          or (
            object in table.personas
            and table.personas[object].scratch.nun_protected
            and "Nun" in table.personas[object].scratch.cards_slot
          )
        )
      ) else "baron"
    if ask:
      retrieval_dict = prompt_dict(
        run_gpt_prompt_decide_card_retrieval(self, table, object),
        {"reasoning": "I will wait before demanding the card back.", "result": "no"}
      )
      result = str(retrieval_dict["result"]).strip().lower()
      if result != "yes":
        return False

    card_name = "Nun" if kind == "nun" else self.scratch.role
    if kind == "nun":
      attempt_desp = f"the Nun {self.scratch.name} asks {object} to return the Nun card and end the protection."
      request_circumstance = f"you are demanding your Nun card back from {object} and ending your protection of them"
    else:
      attempt_desp = f"{self.scratch.name} asks {object} to return {poss} {card_name} card."
      request_circumstance = f"you are demanding your {card_name} card back from {object} because you are alone together and they are holding your card"
    if action_reasoning:
      request_circumstance += (
        f". When you won the internal bid for this retrieve action, your reasoning was: {action_reasoning}"
      )

    self.speak(table, request_circumstance)
    table.add_table_event((self.scratch.name, object, attempt_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name])))

    def log_failed_retrieval(reason):
      failed_desp = f"{self.scratch.name}'s card retrieval from {object} fails: {reason}"
      table.add_table_event((self.scratch.name, object, failed_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name])))

    if object not in table.personas:
      log_failed_retrieval(f"{object} is no longer at the table.")
      return False
    holder = table.personas[object]
    if kind == "nun":
      missing_holder_circumstance = f"the Nun {self.scratch.name} is demanding the Nun card back from you, but you no longer have it; answer that failed demand in the moment"
      holder_circumstance = f"the Nun {self.scratch.name} is requiring you to return the Nun card now; you have to comply and lose the Nun card protection"
    else:
      missing_holder_circumstance = f"{self.scratch.name} is demanding {poss} {card_name} card back from you, but you no longer have it; answer that failed demand in the moment"
      holder_circumstance = f"{self.scratch.name} is reclaiming {poss} {card_name} card from you now because you are alone together; you have to comply"
    if kind == "nun":
      if "Nun" not in table.personas[object].scratch.cards_slot:
        holder.speak(table, missing_holder_circumstance)
        log_failed_retrieval(f"{object} no longer has the Nun card.")
        return False
    elif self.scratch.role not in table.personas[object].scratch.cards_slot:
      holder.speak(table, missing_holder_circumstance)
      log_failed_retrieval(f"{object} no longer has the {self.scratch.role} card.")
      return False

    holder.speak(table, holder_circumstance)

    table.personas[object].scratch.cards_slot.discard(card_name)
    self.scratch.cards_slot.add(card_name)
    if kind == "nun":
      table.personas[object].scratch.nun_protected = False
      self.scratch.ability_active = False
      self.scratch.ability_objects = []
      act_desp = f"the Nun {self.scratch.name} retrieves the Nun card from {object} and revokes protection from {object}."
      retrieval_event = (self.scratch.name, object, act_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name]))
      table.add_table_event(retrieval_event)
    else:
      act_desp = f"{self.scratch.name} retrieves {poss} {card_name} card from {object}."
      retrieval_event = (self.scratch.name, object, act_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name]))
      table.add_table_event(retrieval_event)
    return True



  def get_personal_game_context(self):
    table_information = self.scratch.curr_loc
    your_role = self.scratch.role
    your_family = ROLE_DICT[your_role]["family"]
    your_ability = ROLE_DICT[your_role]["ability"]
    your_win_condition = ROLE_DICT[your_role]["win_condition"]
    # note: in the win_progress reflection prompt add the baron's progress check
    your_win_progress = self.scratch.win_progress
    held_cards = sorted(self.scratch.cards_slot)
    own_card_status = "in your hands" if your_role in self.scratch.cards_slot else "not in your hands"
    other_cards = sorted(set(self.scratch.cards_slot) - {your_role})
    other_cards_text = ", ".join(other_cards) if other_cards else "none"
    personal_context_msg = self.scratch.get_str_iss()
    for relationship_name, relationship in self.scratch.relationships.items():
      personal_context_msg += f"Your relationship with {relationship_name}: {relationship}\n"
    nun_protection_status = " You are currently protected by the Nun card.\n" if self.scratch.nun_protected else "\n"
    personal_context_msg += f"You are currently at the {table_information}. Your private assigned role is {your_role}, which means your family is {your_family}.\nYour ability is: {your_ability}\nYour win condition is: {your_win_condition}\nYour own {your_role} card is currently {own_card_status}. You are currently holding {len(other_cards)} other players' role card(s): {other_cards_text}.{nun_protection_status}"
    return personal_context_msg

  
  
