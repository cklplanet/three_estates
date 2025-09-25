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
sys.path.append('../')

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
    #TODO: actually fix the baron blocking logic
    # PERSONA MEMORY 
    # If there is already memory in folder_mem_saved, we load that. Otherwise,
    # we create new memory instances. 
    # TODO: reimplement the memory function
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
    if special_circumstance:
      speak_dict = run_gpt_prompt_generate_next_convo_line_special(self, table, special_circumstance)[0]
      table.add_table_dialogue((self.scratch.name, speak_dict["object"], speak_dict["volume"], speak_dict["line"], self.scratch.curr_time, set([self.scratch.name, speak_dict["object"]])))
    else:
      speak_dict = run_gpt_prompt_generate_next_convo_line_normal(self, table)[0]
      table.add_table_dialogue((self.scratch.name, speak_dict["object"], speak_dict["volume"], speak_dict["line"], self.scratch.curr_time, set([self.scratch.name, speak_dict["object"]])))

  def select_ability_target(self, table):
    return run_gpt_prompt_select_ability_target(self, table)[0]["target"]

  
  def act(self, table):
    #TODO: defaulting to speak if the total score is 0
    retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = self.scratch.retrieved
    # for now the act function is reserved exclusively for those who either decided or is forced to stay at the table
    act_scores = self.scratch.current_bidding_scores
    act_scores = [(option, points) for option, points in sorted(act_scores.items(), key=lambda item: item[1], reverse=True)]
    final_option = act_scores[0][0]
    obj = "her" if self.scratch.gender == "female" else "him"
    subj = "she" if self.scratch.gender == "female" else "he"
    poss = "her" if self.scratch.gender == "female" else "his"
    if act_scores[0][1] == 0: #case where literally nobody wanted to do anything
      self.scratch.act_reasoning = "neither me nor anyone else has made a special move, business as usual so it's a bit awkward"
      self.speak(table)
    else: # oh you actually want to do something
      if final_option == "ability":
        if len(table.personas.keys()) <= 1:
          # you're instead just speaking randomly because you can't really use your ability
          self.scratch.act_reasoning = "neither me nor anyone else has made a special move, business as usual so it's a bit awkward"
          self.speak(table)
          # you have to have someone other than yourself
        else:
          if self.scratch.role == "Priest" or self.scratch.role == "Thief" or self.scratch.role == "Nun":
            #save the target selection, there is literally only one target
            remaining = set(table.personas.keys()) - {self.scratch.name}
            if len(remaining) != 1:
                raise ValueError("Expected exactly one other persona")
            target_name = next(iter(remaining))
          else:
            target_name = self.select_ability_target(table)

          # Actually effecting the target below

          if self.scratch.role == "King": # already assuming the ability is a go, but #TODO to make sure
            self.scratch.ability_active = True

            for other_player_name, other_player in table.personas.items():
              if other_player_name != self.scratch.name and ROLE_DICT[other_player.scratch.role]["family"] == target_name:
                if other_player.scratch.role == "Farmer": # farmer immunity
                  special_circumstance = f"the King {self.scratch.name} is trying to use {poss} ability on you and you have to reveal you're the Farmer that you're immune,"
                  act_desp = f"{other_player_name} reveals as Farmer"
                  reveal_event = (other_player_name, None, act_desp, self.scratch.curr_time, set([other_player_name]))
                  table.add_table_event(reveal_event)
                  other_player.speak(table, special_circumstance)
                else:
                  table.lockdown_targets.add((self.scratch.name, other_player_name, self.scratch.role))
                  self.scratch.ability_objects.append(other_player_name)
            act_desp = f"{self.scratch.name} reveals as King and uses {obj} ability and locks down all {target_name} at {table.name}"
            lockdown_event = (self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name] + self.scratch.ability_objects))
            table.add_table_event(lockdown_event)
          else:
            target = table.personas[target_name]

            if self.scratch.role == "Nun":
              self.scratch.ability_active = True
              self.scratch.cards_slot.remove("Nun")
              self.scratch.ability_objects.append(other_player_name)
              target.scratch.cards_slot.add("Nun")
              target.scratch.nun_protected = True
              act_desp = f"{self.scratch.name} reveals as Nun and uses {obj} ability and gives {obj} card to protect {target_name}"
              protection_event = (self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name]))
              table.add_table_event(protection_event)
            else:
              # the ability straight up fails if the target is a farmer
              if target.scratch.role == "Farmer":
                special_circumstance = f"the {self.scratch.role} {self.scratch.name} is trying to use {poss} ability on you and you have to reveal you're the Farmer that you're immune,"
                act_desp = f"{target_name} reveals as Farmer"
                reveal_event = (target_name, None, act_desp, self.scratch.curr_time, set([target_name]))
                table.add_table_event(reveal_event)
                target.speak(table, special_circumstance)
              # the ability also straight up fails if the target is nun-protected
              elif target.scratch.nun_protected:
                special_circumstance = f"the {self.scratch.role} {self.scratch.name} is trying to use {poss} ability on you, but since you have the Nun card's protection and will have to show it to prove you're immune,"
                target.speak(table, special_circumstance)
              else:
                if self.scratch.role == "Baron":
                  target.scratch.cards_slot.remove(target.scratch.role)
                  self.scratch.cards_slot.add(target.scratch.role)
                  act_desp = f"{self.scratch.name} reveals as Baron and robs the card of {target_name}"
                  steal_event = (self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name]))
                  table.add_table_event(steal_event)
                  # we are not including the ability objects system to the baron yet
                  
                if self.scratch.role == "Thief":
                  special_circumstance = f"you as the Thief are trying to use your swap ability on {target_name} and have to ask for it out loud,"
                  self.speak(table, special_circumstance)
                  if target.scratch.role not in target.scratch.cards_slot:
                      special_circumstance = f"the Thief {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
                      target.speak(table, special_circumstance)
                  else:
                    self.scratch.cards_slot.remove("Thief")
                    self.scratch.cards_slot.add(target.scratch.role)
                    self.scratch.role = target.scratch.role
                    act_desp = f"{self.scratch.name} reveals as Thief and forcefully swaps cards with {target_name}. {target_name} is the Thief now while {self.scratch.name} is now {self.scratch.role}"
                    target.scratch.cards_slot.remove(target.scratch.role)
                    target.scratch.cards_slot.add("Thief")
                    target.scratch.role = "Thief"
                    steal_event = (self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name]))
                    table.add_table_event(steal_event)
                # Add such that the events are registered in the above properly

                elif self.scratch.role == "Queen":
                  self.scratch.ability_active = True
                  self.scratch.ability_objects.append(target_name)
                  special_circumstance = f"you, as Queen, have just activated your ability to force {target_name} to follow you"
                  next_loc = run_gpt_prompt_select_ability_destination(self, table, retrieved_all_tables, special_circumstance)[0]["option"]
                  table.removal_targets.add((None, self.scratch.name, self.scratch.role, next_loc)) #queen herself leaving
                  special_circumstance = f"you, as Queen, have just activated your ability and are about to depart to the {next_loc} and force {target_name} to follow you, to convey this out loud,"
                  self.speak(table, special_circumstance)
                  table.removal_targets.add((self.scratch.name, target_name, self.scratch.role, next_loc)) #her "victim"
                  special_circumstance = f"the Queen has just activated {poss} ability, chose you as the target, and are about to drag you to depart to the {next_loc}, as parting words,"
                  target.speak(table, special_circumstance)
                  event_msg = f"{self.scratch.name} leaves for {next_loc} while dragging {target_name} with {obj} using {poss} ability as Queen."
                  table.add_table_event((self.scratch.name, target_name, event_msg, self.curr_time, set([self.scratch.name, target_name])))

                elif self.scratch.role == "Spinster":
                  special_circumstance = f"you, as Spinster, have just activated your ability"
                  next_loc = run_gpt_prompt_select_ability_destination(self, table, retrieved_all_tables, special_circumstance)[0]["option"]
                  special_circumstance = f"you, as Spinster, have just activated your ability and are about to depart to the {next_loc} and choose {target_name} to reveal themself, to convey this and as parting words,"
                  self.speak(table, special_circumstance)
                  table.removal_targets.add((None, self.scratch.name, self.scratch.role, next_loc)) #spinster themself leaving
                  table.spinster_marked = (target_name, self.scratch.name)
                  act_desp = f"{self.scratch.name} leaves for {next_loc}."
                  depart_event = (self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name]))
                  table.add_table_event(depart_event)

                elif self.scratch.role == "Priest":
                  special_circumstance = f"you as the Priest are trying to use your ability on {target_name} and have to ask for it out loud,"
                  self.speak(table, special_circumstance)
                  if target.scratch.role not in target.scratch.cards_slot:
                    special_circumstance = f"the Priest {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
                    target.speak(table, special_circumstance)
                  else:
                    special_circumstance = f"the Priest {self.scratch.name} has used {poss} ability on you and now you HAVE to tell your role as {target.scratch.role} to {obj},"
                    target.speak(table, special_circumstance)
                    act_desp = f"the Priest {self.scratch.name} forces {target_name} to reveal as {target.scratch.role}"
                    reveal_event = (self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name]))
                    table.add_table_event(reveal_event)

                elif self.scratch.role == "Bishop":
                  guess = self.guess_family_bishop(target)['guess']
                  special_circumstance = f"you, as Bishop, have just made an internal guess that {target_name}'s family is {guess}, which you now want to annnounce to the target and to the table"
                  self.speak(table, special_circumstance)
                  if guess != ROLE_DICT[target.scratch.role]["family"]:
                    special_circumstance = f"you have just been guessed by the Bishop {self.scratch.name} as family {guess}, which is wrong"
                    target.speak(table, special_circumstance)
                  else:
                    next_loc = run_gpt_prompt_select_ability_destination(self, table, retrieved_all_tables, special_circumstance)[0]["option"]
                    special_circumstance = f"you have just been correctly guessed by the Bishop {self.scratch.name} as family {guess} and now have to leave for {next_loc}"
                    table.removal_targets.add((self.scratch.name, target_name, self.scratch.role))
                    target.speak(table, special_circumstance)
                    act_desp = f"the Bishop {self.scratch.name} correctly guesses {target_name} to reveal as family {guess} and the latter has to leave for {next_loc}"
                    reveal_event = (self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name]))
                    table.add_table_event(reveal_event)
                    
                elif self.scratch.role == "Innkeeper":
                  special_circumstance = f"you, as Innkeeper, have just activated your ability and are about to depart back into the Village, as parting words to this table,"
                  self.speak(table, special_circumstance)
                  table.removal_targets.add((None, self.scratch.name, self.scratch.role, "Village")) #innkeeper themself leaving
                  self.scratch.ability_active = True
                  act_desp = f"{self.scratch.name} leaves for {next_loc}."
                  depart_event = (self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name]))
                  table.add_table_event(depart_event)

      elif final_option == "reveal":
        # cards being present requirement
        act_desp = f"{self.scratch.name} reveals {obj}self to be the {self.scratch.role} without using {poss} ability"
        reveal_event = (self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name]))
        table.add_table_event(reveal_event)
        table.baron_trigger.add(self.scratch.name)
      else: # final_option being vanilla speak
        self.speak(table)

  
  def retrieve_card(self, table, object):
    poss = "her" if self.scratch.gender == "female" else "his"
    result = run_gpt_prompt_decide_card_retrieval(self, table, object)[0]["result"]
    if result == "yes":
      table.personas[object].scratch.cards_slot.remove(self.scratch.role)
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
    personal_context_msg = self.scratch.get_str_iss()
    for relationship_name, relationship in self.scratch.relationships.items():
      personal_context_msg += f"Your relationship with {relationship_name}: {relationship}\n"
    personal_context_msg += f"You are currently at the {table_information}. Your role is {your_role}, which means your family is {your_family}.\nYour ability is: {your_ability}\nYour win condition is: {your_win_condition}\nYour progress to winning: {your_win_progress}\n"
    return personal_context_msg

  
  