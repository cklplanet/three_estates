"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: perceive.py
Description: This defines the "Perceive" module for generative agents. 
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from operator import itemgetter
from global_methods import *
from persona.prompt_template.gpt_structure import *
from persona.prompt_template.run_gpt_prompt import *

def unpack_dialogue(utterance):
  if len(utterance) == 6:
    s_chat, o_chat, volume, line, timestamp_chat, keywords_chat = utterance
    audience = set()
  else:
    s_chat, o_chat, volume, line, timestamp_chat, audience, keywords_chat = utterance
    audience = set(audience)
  return s_chat, o_chat, volume, line, timestamp_chat, audience, keywords_chat


def generate_poig_score(persona, event_type, description, subject=None, obj=None, keywords=None):
  if event_type == "chat":
    chat_poignancy = prompt_payload(
      run_gpt_prompt_chat_poignancy(persona, description),
      heuristic_poignancy_score(persona, event_type, description, subject, obj, keywords)
    )
    return bounded_int(chat_poignancy, 2, minimum=1, maximum=10)
  return bounded_int(
    heuristic_poignancy_score(persona, event_type, description, subject, obj, keywords),
    1,
    minimum=1,
    maximum=10
  )

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
  current_table = room.locations[persona.scratch.curr_loc]
  local_event_cursor = persona.scratch.event_cursors.get(persona.scratch.curr_loc, 0)
  local_events = current_table.event_history[local_event_cursor:]
  persona.scratch.event_cursors[persona.scratch.curr_loc] = len(current_table.event_history)

  for event in local_events:
    s, o, description, timestamp, keywords = event
    event_poignancy = generate_poig_score(persona, "event", description, s, o, keywords)
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
  local_cursor = persona.scratch.dialogue_cursors.get(persona.scratch.curr_loc, 0)
  local_dialogue = current_table.dialogue_history[local_cursor:]
  persona.scratch.dialogue_cursors[persona.scratch.curr_loc] = len(current_table.dialogue_history)

  for utterance in local_dialogue:
    s_chat, o_chat, volume, line, timestamp_chat, audience, keywords_chat = unpack_dialogue(utterance)
    if audience and persona.scratch.name not in audience:
      continue
    if not o_chat:
      o_chat = f"all of {persona.scratch.curr_loc}"
    audience_text = ", ".join(sorted(audience)) if audience else "unknown"
    line = f"{s_chat}, to {o_chat}: ({volume}) {line} [People physically present for this line: {audience_text}]"
    chat_poignancy = generate_poig_score(persona, "chat", line, s_chat, o_chat, keywords_chat)
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
    other_location = room.locations[other_table]
    overheard_cursor = persona.scratch.overheard_dialogue_cursors.get(other_table, 0)
    overheard_dialogue = other_location.dialogue_history[overheard_cursor:]
    persona.scratch.overheard_dialogue_cursors[other_table] = len(other_location.dialogue_history)
    for utterance in overheard_dialogue:
      s_chat, o_chat, volume, line, timestamp_chat, audience, keywords_chat = unpack_dialogue(utterance)
      if volume == "practically screaming":
        audience_text = ", ".join(sorted(audience)) if audience else "unknown"
        line = f"{s_chat}: ({volume}, overheard from the {other_table}; people physically present there: {audience_text}) {line}"
        chat_poignancy = generate_poig_score(persona, "chat", line, s_chat, o_chat, keywords_chat)
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
  if timestamp_events:
    persona.scratch.recent_conversation[0:0] = [(persona.scratch.curr_time, timestamp_events)]
    persona.scratch.recent_conversation = persona.scratch.recent_conversation[:persona.scratch.retention]
  debug_perception(persona, persona.scratch.curr_loc, len(self_table_ret_events), len(other_table_ret_events))

  # We put the reflect step here
  persona.reflect()

  return self_table_ret_events, other_table_ret_events
