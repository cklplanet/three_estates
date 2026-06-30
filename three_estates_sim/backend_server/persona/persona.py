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


  def resolve_baron_reaction(self, table, revealed_player_name, action_context, block_ability=True):
    if len(table.personas) < 3 or revealed_player_name not in table.personas:
      return False
    revealed_player = table.personas[revealed_player_name]
    if revealed_player.scratch.role == "Farmer" or revealed_player.scratch.nun_protected:
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

      revealed_player.scratch.cards_slot.discard(revealed_player.scratch.role)
      baron.scratch.cards_slot.add(revealed_player.scratch.role)
      special_circumstance = f"you are revealing your Baron card to react to {revealed_player_name}'s action and steal the {revealed_player.scratch.role} card"
      if block_ability:
        special_circumstance += f", blocking {revealed_player_name}'s {revealed_player.scratch.role} ability before it resolves"
      else:
        special_circumstance += " after their reveal has already been made"
      baron.speak(table, special_circumstance)
      if block_ability:
        act_desp = f"{baron_name} reveals {self.role_card_text(baron, 'Baron')}, blocks {revealed_player_name}'s {revealed_player.scratch.role} ability, and steals the {revealed_player.scratch.role} card."
      else:
        act_desp = f"{baron_name} reveals {self.role_card_text(baron, 'Baron')} after {revealed_player_name}'s reveal and steals the {revealed_player.scratch.role} card."
      table.add_table_event((baron_name, revealed_player_name, act_desp, self.scratch.curr_time, set([baron_name, revealed_player_name])))
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

  def speak(self, table, special_circumstance=None):
    self.update_knowledge(self.room)
    default_line = {
      "object": "everyone",
      "volume": "calm",
      "line": "I need a moment to think this through.",
    }
    if special_circumstance:
      speak_dict = prompt_dict(run_gpt_prompt_generate_next_convo_line_special(self, table, special_circumstance), default_line)
    else:
      speak_dict = prompt_dict(run_gpt_prompt_generate_next_convo_line_normal(self, table), default_line)
    if speak_dict["object"] not in table.personas and speak_dict["object"] != "everyone":
      speak_dict["object"] = "everyone"
    if speak_dict["volume"] not in {"whisper", "calm", "loud", "practically screaming"}:
      speak_dict["volume"] = "calm"
    table.add_table_dialogue((self.scratch.name, speak_dict["object"], speak_dict["volume"], speak_dict["line"], self.scratch.curr_time, set([self.scratch.name, speak_dict["object"]])))
    self.scratch.speaking_cooldown = max(self.scratch.speaking_cooldown, SPEAKING_COOLDOWN_STEPS + 1)

  def select_ability_target(self, table):
    possible_targets = list(set(table.personas.keys()) - {self.scratch.name})
    if self.scratch.role == "King":
      fallback = ROLE_DICT[self.scratch.role]["family"]
      family_options = {ROLE_DICT[player.scratch.role]["family"] for player in table.personas.values()}
      target_dict = prompt_dict(run_gpt_prompt_select_ability_target(self, table), {"target": fallback})
      return target_dict["target"] if target_dict["target"] in family_options else fallback
    fallback = possible_targets[0] if possible_targets else self.scratch.name
    target_dict = prompt_dict(run_gpt_prompt_select_ability_target(self, table), {"target": fallback})
    return target_dict["target"] if target_dict["target"] in possible_targets else fallback

  def guess_family_bishop(self, target, table):
    return prompt_dict(
      run_gpt_prompt_guess_family_bishop(self, target, table),
      {"reasoning": "I have to make my best guess from limited evidence.", "guess": "Commoners"}
    )

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
    return result == "yes"

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
    act_desp = f"{self.scratch.name} makes final Spinster role guesses: {guess_text}."
    table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name] + target_names + list(guesses.values()))))
    return guesses

  def select_ability_destination(self, table, retrieved_all_tables, special_circumstance):
    fallback = next(iter(set(retrieved_all_tables.keys()) - {table.name}), table.name)
    destination_dict = prompt_dict(
      run_gpt_prompt_select_ability_destination(self, table, retrieved_all_tables, special_circumstance),
      {"reasoning": "I will choose the safest available table.", "option": fallback}
    )
    option = destination_dict["option"]
    if option == table.name or option not in self.room.locations[table.name].connected:
      return fallback
    return option

  
  def act(self, table):
    _, _, _, _, retrieved_all_tables = self.scratch.retrieved
    act_scores = self.scratch.current_bidding_scores
    act_scores = [(option, points) for option, points in sorted(act_scores.items(), key=lambda item: item[1], reverse=True)]
    final_option = act_scores[0][0]
    obj = "her" if self.scratch.gender == "female" else "him"
    subj = "she" if self.scratch.gender == "female" else "he"
    poss = self.possessive_for()
    action_role = self.scratch.role

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
        ability_attempt_context = f"{self.scratch.name} reveals {self.role_card_text(role='Innkeeper')} and attempts to use {poss} Innkeeper ability by leaving for Village."
        self.speak(table, "you are revealing your Innkeeper card and attempting to use your ability by leaving for Village; say what you want the table to hear before you depart")
        table.add_table_event((self.scratch.name, None, ability_attempt_context, self.scratch.curr_time, set([self.scratch.name])))
        if self.resolve_baron_reaction(table, self.scratch.name, ability_attempt_context, block_ability=True):
          return
        table.removal_targets.add((None, self.scratch.name, action_role, "Village"))
        self.scratch.ability_active = True
        act_desp = f"{self.scratch.name} reveals {self.role_card_text(role='Innkeeper')} and leaves for Village."
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
        target_name = self.select_ability_target(table)

      ability_attempt_context = f"{self.scratch.name} reveals {self.role_card_text(role=action_role)} and attempts to use {poss} {action_role} ability on {target_name}."
      self.speak(table, f"you are revealing your {action_role} card and attempting to use your ability on {target_name}; say what you want the table to hear before the ability resolves")
      table.add_table_event((self.scratch.name, target_name, ability_attempt_context, self.scratch.curr_time, set([self.scratch.name, target_name])))
      if self.resolve_baron_reaction(table, self.scratch.name, ability_attempt_context, block_ability=True):
        return

      if action_role == "King":
        self.scratch.ability_active = True
        for other_player_name, other_player in table.personas.items():
          if other_player_name != self.scratch.name and ROLE_DICT[other_player.scratch.role]["family"] == target_name:
            if other_player.scratch.role == "Farmer":
              special_circumstance = f"the King {self.scratch.name} is trying to use {poss} ability on you and you have to reveal your Farmer card to prove you're immune,"
              act_desp = f"{other_player_name} reveals {self.role_card_text(other_player, 'Farmer')}"
              table.add_table_event((other_player_name, None, act_desp, self.scratch.curr_time, set([other_player_name])))
              other_player.speak(table, special_circumstance)
            elif other_player.scratch.nun_protected:
              special_circumstance = f"the King {self.scratch.name} is trying to lock you at this table, but the Nun card protects you"
              other_player.speak(table, special_circumstance)
            else:
              table.lockdown_targets.add((self.scratch.name, other_player_name, action_role))
              self.scratch.ability_objects.append(other_player_name)
        act_desp = f"{self.scratch.name} reveals {self.role_card_text(role='King')} and uses {poss} ability to lock down all {target_name} at {table.name}"
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

      if target.scratch.role == "Farmer":
        special_circumstance = f"the {action_role} {self.scratch.name} is trying to use {poss} ability on you and you have to reveal your Farmer card to prove you're immune,"
        act_desp = f"{target_name} reveals {self.role_card_text(target, 'Farmer')}"
        table.add_table_event((target_name, None, act_desp, self.scratch.curr_time, set([target_name])))
        target.speak(table, special_circumstance)
        return

      if target.scratch.nun_protected:
        special_circumstance = f"the {action_role} {self.scratch.name} is trying to use {poss} ability on you, but since you have the Nun card's protection and will have to show it to prove you're immune,"
        target.speak(table, special_circumstance)
        return

      if action_role == "Thief":
        if target.scratch.role not in target.scratch.cards_slot:
          special_circumstance = f"the Thief {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
          target.speak(table, special_circumstance)
        else:
          old_role = self.scratch.role
          target_old_role = target.scratch.role
          self.scratch.cards_slot.discard(old_role)
          self.scratch.cards_slot.add(target_old_role)
          self.scratch.role = target_old_role
          target.scratch.cards_slot.discard(target_old_role)
          target.scratch.cards_slot.add(old_role)
          target.scratch.role = old_role
          self.scratch.movement_cooldown = max(self.scratch.movement_cooldown, 1)
          target.scratch.movement_cooldown = max(target.scratch.movement_cooldown, 1)
          act_desp = f"{self.scratch.name} reveals {self.role_card_text(role=old_role)} and forcefully swaps cards with {target_name}. {target_name} is the Thief now while {self.scratch.name} is now {self.scratch.role}"
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))

      elif action_role == "Queen":
        self.scratch.ability_active = True
        self.scratch.ability_objects.append(target_name)
        special_circumstance = f"you, as Queen, have just activated your ability to force {target_name} to follow you"
        next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
        table.removal_targets.add((None, self.scratch.name, action_role, next_loc))
        table.removal_targets.add((self.scratch.name, target_name, action_role, next_loc))
        special_circumstance = f"the Queen has just activated {poss} ability, chose you as the target, and are about to drag you to depart to the {next_loc}, as parting words,"
        target.speak(table, special_circumstance)
        event_msg = f"{self.scratch.name} reveals {self.role_card_text(role='Queen')} and leaves for {next_loc} while dragging {target_name} with {obj} using {poss} ability."
        table.add_table_event((self.scratch.name, target_name, event_msg, self.scratch.curr_time, set([self.scratch.name, target_name])))

      elif action_role == "Spinster":
        special_circumstance = f"you, as Spinster, have just activated your ability"
        next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
        table.removal_targets.add((None, self.scratch.name, action_role, next_loc))
        table.spinster_marked = (target_name, self.scratch.name)
        act_desp = f"{self.scratch.name} reveals {self.role_card_text(role='Spinster')} and leaves for {next_loc}."
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
          special_circumstance = f"you have just been guessed by the Bishop {self.scratch.name} as family {guess}, which is wrong"
          target.speak(table, special_circumstance)
        else:
          next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
          special_circumstance = f"you have just been correctly guessed by the Bishop {self.scratch.name} as family {guess} and now have to leave for {next_loc}"
          table.removal_targets.add((self.scratch.name, target_name, action_role, next_loc))
          target.speak(table, special_circumstance)
          act_desp = f"the Bishop {self.scratch.name} correctly guesses {target_name}'s family as {guess} and the latter has to leave for {next_loc}"
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))

    elif final_option == "reveal":
      if action_role not in self.scratch.cards_slot:
        act_desp = f"{self.scratch.name} tries to reveal {self.role_card_text(role=action_role)}, but cannot prove it because {subj} does not have that role card."
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
        if not self.maybe_stay_silent(table, "they cannot prove their role card right now"):
          self.speak(table, f"you want to reveal your {action_role} card, but you cannot prove it because you do not currently have your role card")
        return
      self.speak(table, f"you are revealing your {action_role} card without using your ability; say what you want the table to hear as/accompanying this reveal")
      act_desp = f"{self.scratch.name} reveals {self.role_card_text(role=action_role)} without using {poss} ability"
      table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
      self.resolve_baron_reaction(table, self.scratch.name, act_desp, block_ability=False)

    else:
      self.speak(table)

  
  def retrieve_card(self, table, object):
    poss = "her" if self.scratch.gender == "female" else "his"
    retrieval_dict = prompt_dict(
      run_gpt_prompt_decide_card_retrieval(self, table, object),
      {"reasoning": "I will wait before demanding the card back.", "result": "no"}
    )
    result = retrieval_dict["result"]
    if result == "yes" and object in table.personas:
      table.personas[object].scratch.cards_slot.discard(self.scratch.role)
      self.scratch.cards_slot.add(self.scratch.role)
      if self.scratch.role == "Nun":
        table.personas[object].scratch.nun_protected = False
        self.scratch.ability_active = False
        self.scratch.ability_objects = []
        act_desp = f"the Nun {self.scratch.name} retrieves Nun card and revokes protection from {object}."
        special_circumstance = f"you are going to retrieve your card from {object} and revoke your protection from {object}"
        self.speak(table, special_circumstance)
        retrieval_event = (self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name]))
        table.add_table_event(retrieval_event)
        
      else:
        act_desp = f"{self.scratch.name} retrieves {poss} card from the Baron {object}."
        special_circumstance = f"you are going to retrieve your card from the Baron {object} since the Baron is alone with you now"
        self.speak(table, special_circumstance)
        retrieval_event = (self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name]))
        table.add_table_event(retrieval_event)



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
    personal_context_msg += f"You are currently at the {table_information}. Your role is {your_role}, which means your family is {your_family}.\nYour ability is: {your_ability}\nYour win condition is: {your_win_condition}\nYour progress to winning: {your_win_progress}\nYour own {your_role} card is currently {own_card_status}. You are currently holding {len(other_cards)} other players' role card(s): {other_cards_text}.\n"
    return personal_context_msg

  
  
