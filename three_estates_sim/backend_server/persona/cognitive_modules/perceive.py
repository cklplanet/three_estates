"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: perceive.py
Description: This defines the "Perceive" module for generative agents. 
"""
import sys
sys.path.append('../../')

from operator import itemgetter
from global_methods import *
from persona.prompt_template.gpt_structure import *
from persona.prompt_template.run_gpt_prompt import *

def generate_poig_score(persona, event_type, description): 
  
  if event_type == "event" or event_type == "thought": 
    return run_gpt_prompt_event_poignancy(persona, description)[0]
  elif event_type == "chat": 
    return run_gpt_prompt_chat_poignancy(persona, description)[0]

def perceive(persona, room): 
  """
  Perceives events around the persona and saves it to the memory, both events 
  and spaces. 

  We first perceive the events nearby the persona, as determined by its 
  <vision_r>. If there are a lot of events happening within that radius, we 
  take the <att_bandwidth> of the closest events. Finally, we check whether
  any of them are new, as determined by <retention>. If they are new, then we
  save those and return the <ConceptNode> instances for those events. 

  INPUT: 
    persona: An instance of <Persona> that represents the current persona. 
    room: An instance of <Room> that represents the current room in which the 
          persona is acting in. 
  OUTPUT: 
    ret_events: a list of <ConceptNode> that are perceived and new. 
  """
  # PERCEIVE SPACE
  # We get the nearby tables (strings) given our current table
  other_tables = set(list(room.locations.keys())) - {persona.scratch.curr_loc}
  # PERCEIVE EVENTS. 
  # We will perceive events that take place in the same arena as the
  # persona's current arena.
  # We do not perceive the same event twice (this can happen if an object is
  # extended across multiple locations).

  self_table_ret_events = []
  for event in room.locations[persona.scratch.curr_loc].current_events:
    s, o, description, timestamp, keywords = event
    event_poignancy = generate_poig_score(persona, "event", description)
    desc_embedding_in = description
    if desc_embedding_in in persona.a_mem.embeddings: 
      event_embedding = persona.a_mem.embeddings[desc_embedding_in]
    else: 
      event_embedding = get_embedding(desc_embedding_in)
    event_embedding_pair = (desc_embedding_in, event_embedding)
    self_table_ret_events += [persona.a_mem.add_event(timestamp, s, o, persona.scratch.curr_loc,
                        description, keywords, event_poignancy, 
                        event_embedding_pair)]
    persona.scratch.importance_ele_n += 1
    persona.scratch.importance_trigger_curr -= event_poignancy
    # note: for now only local table events themselves count down the trigger?
  # current_event = (subject, object, act_desp, timestamp, keywords)
  for utterance in room.locations[persona.scratch.curr_loc].current_lines:
    s_chat, o_chat, volume, line, timestamp_chat, keywords_chat = utterance
    if not o_chat:
      o_chat = f"all of {persona.scratch.curr_loc}"
    line = f"{s_chat}, to {o_chat}: ({volume}) {line}"
    chat_poignancy = generate_poig_score(persona, "chat", line)
    line_embedding_in = line
    if line_embedding_in in persona.a_mem.embeddings: 
      line_embedding = persona.a_mem.embeddings[line_embedding_in]
    else: 
      line_embedding = get_embedding(line_embedding_in)
    chat_embedding_pair = (line_embedding_in, line_embedding)
    self_table_ret_events += [persona.a_mem.add_chat(timestamp_chat, s_chat, o_chat, persona.scratch.curr_loc,
                        line, keywords_chat, chat_poignancy, 
                        chat_embedding_pair)]
    persona.scratch.importance_ele_n += 1
  # format: (subject, object, volume, contents, timestamp, keywords)

  other_table_ret_events = []
  # should I tiebreak in case both tables end up screaming?
  for other_table in other_tables:
    # TODO: deduplicate each perception step
    # as in rewrite how self/other_table ret events even work
    # and actually USE the associative memory (or not?)
    for utterance in room.locations[other_table].current_lines:
      s_chat, o_chat, volume, line, timestamp_chat, keywords_chat = utterance
      if volume == "practically screaming":
        line = f"{s_chat}: ({volume}) {line}"
        chat_poignancy = generate_poig_score(persona, "chat", line)
        line_embedding_in = line
        if line_embedding_in in persona.a_mem.embeddings: 
          line_embedding = persona.a_mem.embeddings[line_embedding_in]
        else: 
          line_embedding = get_embedding(line_embedding_in)
        chat_embedding_pair = (line_embedding_in, line_embedding)
        other_table_ret_events  += [persona.a_mem.add_chat(timestamp_chat, s_chat, o_chat, persona.scratch.curr_loc,
                            line, keywords_chat, chat_poignancy, 
                            chat_embedding_pair)]
        persona.scratch.importance_ele_n += 1
  
  timestamp_events = (self_table_ret_events + other_table_ret_events)
  persona.scratch.recent_conversation[0:0] = [(persona.scratch.curr_time, timestamp_events)]
  persona.scratch.recent_conversation = persona.scratch.recent_conversation[:persona.scratch.retention]

  # We put the reflect step here
  persona.reflect()

  return self_table_ret_events, other_table_ret_events

