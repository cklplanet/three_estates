"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: reflect.py
Description: This defines the "Reflect" module for generative agents. 
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

import datetime
import random

from numpy import dot
from numpy.linalg import norm

from global_methods import *
from persona.prompt_template.run_gpt_prompt import *
from persona.prompt_template.gpt_structure import *
from persona.cognitive_modules.retrieve import *


def generate_poig_score(persona, event_type, description): 
  if debug: print ("GNS FUNCTION: <generate_poig_score>")

  return bounded_int(
    heuristic_poignancy_score(persona, event_type, description),
    1,
    minimum=1,
    maximum=10
  )



def run_reflect(persona):
  """
  Run reflection. Retrieve across board-wide and per-person role-status
  focal questions, then create one board thought.

  INPUT: 
    persona: Current Persona object
  Output: 
    None
  """
  room_personas = getattr(getattr(persona, "room", None), "personas", {})
  nodes = []
  subjects = set()
  for i in (persona.a_mem.seq_event + persona.a_mem.seq_chat):
    subjects.update(keyword for keyword in i.keywords if keyword in room_personas or keyword == persona.scratch.name)
    nodes.append([i.last_accessed, i])
  subjects.update(room_personas.keys())

  nodes = sorted(nodes, key=lambda x: x[0])
  nodes = [i for created, i in nodes]
  nodes = nodes[-1*persona.scratch.importance_ele_n:]

  if not subjects:
    return

  board_focal_points = [
    "Across the whole game, what can be observed about each other player's confirmed, claimed, or suspected hidden game role, family, and card status?",
    "Which role or family claims are card-backed, which are verbal only, and which are merely guesses or contradictions?",
    "What alliances, rivalries, bargains, coercion, protection promises, threats, or trust patterns can be inferred without discussing win-condition progress?"
  ]
  subject_focal_points = {}
  for subject in sorted(subjects):
    if subject == persona.scratch.name:
      continue
    subject_focal_points[subject] = [
      f"What is {subject}'s confirmed, claimed, or suspected hidden game role and family, separating card-backed proof from verbal claims?",
      f"What is known or suspected about whether {subject} still has their own role card or any other cards?",
      f"What alliances, rivalries, bargains, coercion, protection promises, threats, or trust patterns involve {subject}?"
    ]

  focal_points = list(board_focal_points)
  for questions in subject_focal_points.values():
    focal_points.extend(questions)

  retrieved = new_retrieve(persona, focal_points, 10)
  focal_retrievals = {
    focal_point: retrieved.get(focal_point, [])
    for focal_point in focal_points
  }
  prior_board_thoughts = sorted(
    [thought for thought in persona.a_mem.seq_thought if thought.object == "board"],
    key=lambda thought: thought.last_accessed
  )[-5:]
  thought_dict = prompt_dict(
    run_gpt_prompt_reflect_on_board_state(persona, focal_retrievals, prior_board_thoughts),
    {
      "reasoning": "I do not have enough reliable evidence to fully update the board.",
      "summary": "I am still tracking other players' confirmed, claimed, and suspected roles, families, card status, alliances, and rivalries, but the board remains uncertain."
    }
  )
  thought = thought_dict["summary"]
  thought_embedding_pair = (thought, get_embedding(thought))
  created = persona.scratch.curr_time
  expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
  keywords = {persona.scratch.name, "board", "roles", "role claims", "card status", "alliances", "rivalries"} | set(subjects)
  for role, role_data in ROLE_DICT.items():
    if role.lower() in thought.lower() or role_data["family"].lower() in thought.lower():
      keywords.add(role)
      keywords.add(role_data["family"])
  persona.a_mem.add_thought(created, expiration, persona.scratch.name, "board",
                            thought, keywords, 9,
                            thought_embedding_pair)
  
    


def reflection_trigger(persona): 
  """
  Given the current persona, determine whether the persona should run a 
  reflection. 
  
  Our current implementation checks for whether the sum of the new importance
  measure has reached the set (hyper-parameter) threshold.

  INPUT: 
    persona: Current Persona object
  Output: 
    True if we are running a new reflection. 
    False otherwise. 
  """
  #print (persona.scratch.name, "persona.scratch.importance_trigger_curr::", persona.scratch.importance_trigger_curr)
  #print (persona.scratch.importance_trigger_max)

  if (persona.scratch.importance_trigger_curr <= 0 and 
      [] != persona.a_mem.seq_event + persona.a_mem.seq_thought + persona.a_mem.seq_chat): 
    return True 
  return False


def reset_reflection_counter(persona): 
  """
  We reset the counters used for the reflection trigger. 

  INPUT: 
    persona: Current Persona object
  Output: 
    None
  """
  persona_imt_max = persona.scratch.importance_trigger_max
  persona.scratch.importance_trigger_curr = persona_imt_max
  persona.scratch.importance_ele_n = 0


def reflect(persona):
  """
  The main reflection module for the persona. We first check if the trigger 
  conditions are met, and if so, run the reflection and reset any of the 
  relevant counters. 

  INPUT: 
    persona: Current Persona object
  Output: 
    None
  """
  if reflection_trigger(persona): 
    run_reflect(persona)
    reset_reflection_counter(persona)



  # the below was the OG's reflection on convos. since here convos and actions are functionally
  # no longer different we don't even have that anymore
