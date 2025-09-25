"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: reflect.py
Description: This defines the "Reflect" module for generative agents. 
"""
import sys
sys.path.append('../../')

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

  if "is idle" in description: 
    return 1

  if event_type == "event" or event_type == "thought": 
    return run_gpt_prompt_event_poignancy(persona, description)[0]
  elif event_type == "chat": 
    return run_gpt_prompt_chat_poignancy(persona, description)[0]



def run_reflect(persona):
  """
  Run the actual reflection. We generate the focal points, retrieve any 
  relevant nodes, and generate thoughts and insights. 

  INPUT: 
    persona: Current Persona object
  Output: 
    None
  """
  # Reflection requires certain focal points. Generate that first. 
  # make focal point MUCH more object-based
  def filter_nonoverlapping_events(chat_dict, existing_events):
        all_existing_ids = {e.description for e in existing_events}
        filtered_events = {}
        for k, vlist in chat_dict.items():
            filtered_vlist = [node for node in vlist if node.description not in all_existing_ids]
            if filtered_vlist:
                filtered_events[k] = filtered_vlist
        return filtered_events
  
  obj = "her" if persona.scratch.gender == "female" else "him"
  subj = "she" if persona.scratch.gender == "female" else "he"
  poss = "her" if persona.scratch.gender == "female" else "his"
  nodes = []
  # nodes here represent EVERY event and chat
  subjects = set()
  for i in (persona.a_mem.seq_event + persona.a_mem.seq_chat):
    subjects.update(i.keywords)
    nodes.append([i.last_accessed, i])

  nodes = sorted(nodes, key=lambda x: x[0]) # resort by LAST ACCESSED
  nodes = [i for created, i in nodes] # get rid of the timestamp apparently
  nodes = nodes[-1*persona.scratch.importance_ele_n:] # the time filter

  for subject in subjects:
    # not yourself
    if subject != persona.scratch.name:
      subject_nodes = [node for node in nodes if subject in node.keywords]
      
      focal_points = [f"How honest or reliable is {subject}'s words? Are there any contradictions in {poss} words? Hidden motives behind {poss} actions? Being unusually quiet?",
                      f"Do you feel if {subject} can be a potential ally, foe, or useful tool (and whether or not it is related to {poss} win conditions synergizing with yours or not)?",
                      f"What is {subject}'s role (or family) and have they revealed and seemingly revealed it {obj}self? If you're still not sure what their role (or family) is, can you make an educated guess?",
                      f"What other people might {subject} have been colluding with? What other person/people might f{subject} have special relationship with outside of the game, and what kind?",
                      f"Based on your knowledge or guess of {subject}'s family or role so far, how close is {subject} to fulfilling {poss} win condition? If you have no clue yet, it's okay to admit."]
      subject_thoughts = [thought for thought in persona.a_mem.seq_thought if subject == thought.o]
      # collect all the thoughts with the subject as, you know, the subject
      subject_thoughts = sorted(subject_thoughts, key=lambda x: x[0]) # resort by LAST ACCESSED
      subject_thoughts = [i for created, i in subject_thoughts] # get rid of the timestamp apparently
      subject_thoughts = subject_thoughts[-5:] # the recency filter
      for focal_point in focal_points:
        retrieved = new_retrieve(persona, [focal_point])
        # TODO: note: new_retrieve retrieves thoughts possibly from older times. might want to change for further iterations
        subject_events = filter_nonoverlapping_events(retrieved, subject_nodes)
        thought_dict = run_gpt_prompt_reflect_on_subject(persona, subject_events, subject_thoughts, focal_point)[0]["summary"]
        thought = thought_dict['summary']
        thought_embedding_pair = (thought, get_embedding(thought))
        created = persona.scratch.curr_time
        expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
        s = persona.scratch.name
        o = subject
        thought_poignancy = generate_poig_score(persona, "thought", thought)
        keywords = set([s,o])
        # format: {focal point: [list of nodes]}
        persona.a_mem.add_thought(created, expiration, s, o, 
                                  thought, keywords, thought_poignancy, 
                                  thought_embedding_pair)
    else: # yah it's me
      my_nodes = [node for node in nodes if persona.scratch.name in node.keywords]
      focal_point = f"Give your own family and role, how close are you, aka {persona.scratch.name} to fulfilling your own win condition? If you have no clue yet, it's okay to admit."
      my_relevant_thoughts = [thought for thought in persona.a_mem.seq_thought if persona.scratch.name in thought.keywords]
      # EVERY thought relevant to me
      retrieved = new_retrieve(persona, [focal_point])
      my_relevant_events = filter_nonoverlapping_events(retrieved, my_nodes)
      thought_dict = run_gpt_prompt_reflect_on_subject(persona, my_relevant_events, my_relevant_thoughts, focal_point)[0]["summary"]
      persona.scratch.win_progress = thought
  
    


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