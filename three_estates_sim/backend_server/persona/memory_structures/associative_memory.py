"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: associative_memory.py
Description: Defines the core long-term memory module for generative agents.

Note (May 1, 2023) -- this class is the Memory Stream module in the generative
agents paper. 
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

import json
import datetime
import os
import difflib
import re

from global_methods import *

FUZZY_KEYWORD_MATCH_THRESHOLD = 0.86

KEYWORD_ALIASES = {
  "commoner": {"commoner", "commoners"},
  "commoners": {"commoner", "commoners"},
  "noble": {"noble", "nobles", "nobility"},
  "nobles": {"noble", "nobles", "nobility"},
  "nobility": {"noble", "nobles", "nobility"},
  "clergy": {"clergy", "cleric", "clerics"},
  "cleric": {"clergy", "cleric", "clerics"},
  "clerics": {"clergy", "cleric", "clerics"},
}


def normalize_keyword(keyword):
  key = str(keyword or "").lower().strip()
  key = re.sub(r"\s+", " ", key)
  key = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", key)
  if key.endswith("'s"):
    key = key[:-2]
  if len(key) > 4 and key.endswith("ies"):
    key = key[:-3] + "y"
  elif len(key) > 4 and key.endswith("es") and not key.endswith("ses"):
    key = key[:-2]
  elif len(key) > 3 and key.endswith("s") and not key.endswith("ss"):
    key = key[:-1]
  return key


def keyword_variants(keyword):
  raw = str(keyword or "").lower().strip()
  normalized = normalize_keyword(raw)
  variants = {raw, normalized}
  variants.update(KEYWORD_ALIASES.get(raw, set()))
  variants.update(KEYWORD_ALIASES.get(normalized, set()))
  return {variant for variant in variants if variant}


class ConceptNode: 
  def __init__(self,
               node_id, node_count, type_count, node_type,
               created,
               s, o, table,
               description, embedding_key, poignancy, keywords,
               expiration=None, depth=0, predicate=None, filling=None):
    self.node_id = node_id
    self.node_count = node_count
    self.type_count = type_count
    self.type = node_type # thought / event / chat

    self.created = created
    self.last_accessed = self.created
    self.expiration = expiration
    self.depth = depth

    self.subject = s
    self.predicate = predicate
    self.object = o
    self.table = table

    self.description = description
    self.embedding_key = embedding_key
    self.poignancy = poignancy
    self.keywords = keywords
    self.filling = filling


  def spo_summary(self): 
    return (self.subject, self.predicate, self.object)


class AssociativeMemory: 
  def __init__(self, name, f_saved=False): 
    self.id_to_node = dict()

    self.seq_event = []
    self.seq_thought = []
    self.seq_chat = []
    self.embeddings = dict()

    self.kw_to_event = dict()
    self.kw_to_thought = dict()
    self.kw_to_chat = dict()

    self.kw_strength_event = dict()
    self.kw_strength_thought = dict()

    direct_saved = f_saved
    nested_saved = f"{f_saved}/{name}" if f_saved else False
    if direct_saved and os.path.isfile(f"{direct_saved}/nodes.json"):
      f_saved = direct_saved
    elif nested_saved and os.path.isfile(f"{nested_saved}/nodes.json"):
      f_saved = nested_saved
    else:
      f_saved = False

    if f_saved and os.path.isdir(f_saved):
      self.embeddings = json.load(open(f_saved + "/embeddings.json"))

      nodes_load = json.load(open(f_saved + "/nodes.json"))
      sorted_node_details = sorted(
        nodes_load.values(),
        key=lambda node: (
          node.get("node_count", 0),
          node.get("created", 0) or 0,
        )
      )
      for node_details in sorted_node_details:

        node_count = node_details["node_count"]
        type_count = node_details["type_count"]
        node_type = node_details["type"]
        node_table = node_details.get("table")
        depth = node_details.get("depth", 0)

        created = self.load_elapsed_time(node_details.get("created"))
        expiration = None
        if node_details.get("expiration") is not None:
          expiration = self.load_elapsed_time(node_details["expiration"])

        s = node_details["subject"]
        o = node_details["object"]

        description = node_details["description"]
        embedding_key = node_details["embedding_key"]
        embedding = self.embeddings.get(embedding_key)
        if embedding is None:
          fallback_embedding = next(iter(self.embeddings.values()), [])
          embedding = [0.0] * len(fallback_embedding)
          self.embeddings[embedding_key] = embedding
        embedding_pair = (embedding_key, embedding)
        poignancy = node_details["poignancy"]
        keywords = set(node_details["keywords"])
        if node_type == "event":
          poignancy = heuristic_poignancy_score(name, node_type, description, s, o, keywords)
        
        if node_type == "event": 
          self.add_event(created, s, o, node_table,
                      description, keywords, poignancy, 
                      embedding_pair)
        elif node_type == "chat": 
          self.add_chat(created, s, o, node_table,
                     description, keywords, poignancy, 
                     embedding_pair)
        elif node_type == "thought": 
          self.add_thought(created, expiration, s, o,
                        description, keywords, poignancy, 
                        embedding_pair)

      kw_strength_load = json.load(open(f_saved + "/kw_strength.json"))
      if kw_strength_load["kw_strength_event"]: 
        self.kw_strength_event = kw_strength_load["kw_strength_event"]
      if kw_strength_load["kw_strength_thought"]: 
        self.kw_strength_thought = kw_strength_load["kw_strength_thought"]

    
  def elapsed_time_to_json(self, value):
    if value is None:
      return None
    if isinstance(value, datetime.timedelta):
      return value.total_seconds()
    if isinstance(value, datetime.datetime):
      return value.strftime('%Y-%m-%d %H:%M:%S')
    return value


  def load_elapsed_time(self, value):
    if value is None:
      return datetime.timedelta(0)
    if isinstance(value, (int, float)):
      return datetime.timedelta(seconds=value)
    try:
      return datetime.timedelta(seconds=float(value))
    except (TypeError, ValueError):
      pass
    return datetime.timedelta(0)


  def index_node_keywords(self, keyword_index, keywords, node):
    for keyword in keywords:
      for kw in keyword_variants(keyword):
        if kw in keyword_index:
          keyword_index[kw][0:0] = [node]
        else:
          keyword_index[kw] = [node]


  def matching_keyword_keys(self, keyword_index, keyword):
    keys = set()
    for variant in keyword_variants(keyword):
      if variant in keyword_index:
        keys.add(variant)
      if len(variant) >= 4:
        close_matches = difflib.get_close_matches(
          variant,
          keyword_index.keys(),
          n=8,
          cutoff=FUZZY_KEYWORD_MATCH_THRESHOLD,
        )
        keys.update(close_matches)
    return keys


  def retrieve_from_keyword_index(self, keyword_index, contents):
    ret = []
    for content in contents:
      if not content:
        continue
      for key in self.matching_keyword_keys(keyword_index, content):
        ret += keyword_index[key]

    ret_by_id = {node.node_id: node for node in ret}
    return sorted(
      ret_by_id.values(),
      key=lambda node: (node.created, node.node_count),
      reverse=True
    )


  def embedding_to_json(self, value):
    if hasattr(value, "tolist"):
      return value.tolist()
    return value


  def save(self, out_json): 
    r = dict()
    for count in range(len(self.id_to_node.keys()), 0, -1): 
      node_id = f"node_{str(count)}"
      node = self.id_to_node[node_id]

      r[node_id] = dict()
      r[node_id]["node_count"] = node.node_count
      r[node_id]["type_count"] = node.type_count
      r[node_id]["type"] = node.type
      r[node_id]["depth"] = node.depth
      r[node_id]["table"] = node.table

      r[node_id]["created"] = self.elapsed_time_to_json(node.created)
      r[node_id]["expiration"] = self.elapsed_time_to_json(node.expiration)

      r[node_id]["subject"] = node.subject
      r[node_id]["predicate"] = node.predicate
      r[node_id]["object"] = node.object

      r[node_id]["description"] = node.description
      r[node_id]["embedding_key"] = node.embedding_key
      r[node_id]["poignancy"] = node.poignancy
      r[node_id]["keywords"] = list(node.keywords)
      r[node_id]["filling"] = node.filling

    with open(out_json+"/nodes.json", "w", encoding="utf-8") as outfile:
      json.dump(r, outfile, ensure_ascii=False)

    r = dict()
    r["kw_strength_event"] = self.kw_strength_event
    r["kw_strength_thought"] = self.kw_strength_thought
    with open(out_json+"/kw_strength.json", "w", encoding="utf-8") as outfile:
      json.dump(r, outfile, ensure_ascii=False)

    with open(out_json+"/embeddings.json", "w", encoding="utf-8") as outfile:
      json.dump(
        {key: self.embedding_to_json(value) for key, value in self.embeddings.items()},
        outfile,
        ensure_ascii=False,
      )


  def add_event(self, created, s, o, table,
                      description, keywords, poignancy, 
                      embedding_pair):
    # node_id, node_count, type_count, node_type,
               #created,
               #s, o, 
               #description, embedding_key, poignancy, keywords)
    # Setting up the node ID and counts.
    node_count = len(self.id_to_node.keys()) + 1
    type_count = len(self.seq_event) + 1
    node_type = "event"
    node_id = f"node_{str(node_count)}"

    # Node type specific clean up. 
    if "(" in description: 
      description = (" ".join(description.split()[:3]) 
                     + " " 
                     +  description.split("(")[-1][:-1])

    # Creating the <ConceptNode> object.
    node = ConceptNode(node_id, node_count, type_count, node_type,
                       created,
                       s, o, table,
                       description, embedding_pair[0], 
                       poignancy, keywords)

    # Creating various dictionary cache for fast access. 
    self.seq_event[0:0] = [node]
    self.index_node_keywords(self.kw_to_event, keywords, node)
    self.id_to_node[node_id] = node 

    # I have no clue what this does, needs double check
    # Adding in the kw_strength
    #if f"{p} {o}" != "is idle":  
      #for kw in keywords: 
        #if kw in self.kw_strength_event: 
          #self.kw_strength_event[kw] += 1
        #else: 
          #self.kw_strength_event[kw] = 1

    self.embeddings[embedding_pair[0]] = embedding_pair[1]

    return node


  def add_thought(self, created, expiration, s, o, 
                        description, keywords, poignancy, 
                        embedding_pair):
    # Setting up the node ID and counts.
    node_count = len(self.id_to_node.keys()) + 1
    type_count = len(self.seq_thought) + 1
    node_type = "thought"
    node_id = f"node_{str(node_count)}"
    depth = 1 

    # Creating the <ConceptNode> object.
    node = ConceptNode(node_id, node_count, type_count, node_type,
                       created,
                       s, o, None,
                       description, embedding_pair[0], poignancy, keywords,
                       expiration=expiration, depth=depth)

    # Creating various dictionary cache for fast access. 
    self.seq_thought[0:0] = [node]
    self.index_node_keywords(self.kw_to_thought, keywords, node)
    self.id_to_node[node_id] = node 

    # I have no clue what this does either
    # Adding in the kw_strength
    #if f"{p} {o}" != "is idle":  
      #for kw in keywords: 
        #if kw in self.kw_strength_thought: 
          #self.kw_strength_thought[kw] += 1
        #else: 
          #self.kw_strength_thought[kw] = 1

    self.embeddings[embedding_pair[0]] = embedding_pair[1]

    return node


  def add_chat(self, created, s, o, table,
                     description, keywords, poignancy, 
                     embedding_pair): 
    # Setting up the node ID and counts.
    node_count = len(self.id_to_node.keys()) + 1
    type_count = len(self.seq_chat) + 1
    node_type = "chat"
    node_id = f"node_{str(node_count)}"

    node = ConceptNode(node_id, node_count, type_count, node_type,
                       created,
                       s, o, table,
                       description, embedding_pair[0], 
                       poignancy, keywords)

    # Creating various dictionary cache for fast access. 
    self.seq_chat[0:0] = [node]
    self.index_node_keywords(self.kw_to_chat, keywords, node)
    self.id_to_node[node_id] = node 

    self.embeddings[embedding_pair[0]] = embedding_pair[1]
        
    return node


  def get_summarized_latest_events(self, retention): 
    ret_set = set()
    for e_node in self.seq_event[:retention]: 
      ret_set.add(e_node.spo_summary())
    return ret_set


  def get_str_seq_events(self): 
    ret_str = ""
    for count, event in enumerate(self.seq_event): 
      ret_str += f'{"Event", len(self.seq_event) - count, ": ", event.spo_summary(), " -- ", event.description}\n'
    return ret_str


  def get_str_seq_thoughts(self): 
    ret_str = ""
    for count, event in enumerate(self.seq_thought): 
      ret_str += f'{"Thought", len(self.seq_thought) - count, ": ", event.spo_summary(), " -- ", event.description}'
    return ret_str


  def get_str_seq_chats(self): 
    ret_str = ""
    for count, event in enumerate(self.seq_chat): 
      ret_str += f"with {event.object.content} ({event.description})\n"
      ret_str += f'{event.created.strftime("%B %d, %Y, %H:%M:%S")}\n'
      for row in event.filling: 
        ret_str += f"{row[0]}: {row[1]}\n"
    return ret_str


  def retrieve_relevant_thoughts(self, s_content, o_content): 
    # "relevant" in this sense means containing the same keywords the query does
    return self.retrieve_from_keyword_index(self.kw_to_thought, [s_content, o_content])


  def retrieve_relevant_events(self, s_content, o_content): 
    # "relevant" in this sense means containing the same keywords the query does
    return self.retrieve_from_keyword_index(self.kw_to_event, [s_content, o_content])


  def get_last_chat(self, target_persona_name): 
    matched_nodes = []
    for key in self.matching_keyword_keys(self.kw_to_chat, target_persona_name):
      matched_nodes += self.kw_to_chat[key]
    if not matched_nodes:
      return False
    return sorted(
      {node.node_id: node for node in matched_nodes}.values(),
      key=lambda node: (node.created, node.node_count),
      reverse=True,
    )[0]
