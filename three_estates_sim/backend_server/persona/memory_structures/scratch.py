"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: scratch.py
Description: Defines the short-term memory module for generative agents.
"""
import datetime
import json
import sys
sys.path.append('../../')

from global_methods import *
from persona.prompt_template.gpt_structure import *
from persona.prompt_template.run_gpt_prompt import *
from utils import *


class Scratch: 
  # for demo purposes now we are NOT bothering to save any of it
  def __init__(self, role, f_saved=False): 
    # PERSONA HYPERPARAMETERS
    # <att_bandwidth>
    self.att_bandwidth = 3
    # <retention>
    self.retention = 20

    # WORLD INFORMATION
    # Perceived world time. 
    self.curr_time = datetime.timedelta(0)
    # Current table of the persona.
    self.curr_loc = None
    
    # THE CORE IDENTITY OF THE PERSONA 
    # Base information about the persona.
    self.name = None
    self.first_name = None
    self.last_name = None
    self.gender = None
    self.age = None
    # L0 permanent core traits.  
    self.innate = None
    # L1 stable traits.

    # New reflection variables
    self.recency_w = 1
    self.relevance_w = 1
    self.importance_w = 1
    self.importance_ele_n = 0
    self.recency_decay = 0.99
    self.importance_trigger_max = 150
    self.importance_trigger_curr = self.importance_trigger_max

    # RELEVANT TO OUR GAME
    self.role = role #"King", "Queen", "Spinster", etc.
    self.current_bidding_scores = dict()
    self.cards_slot = set() # has your own card by default. also "King", "Queen", "Spinster", etc.
    self.recent_conversation = [] # format: [{time(xxx): events([node, node, node])}, ....]
    #self.current_table_conversation = [] #limited to just the current table, for reflection only
    self.win_progress = None
    self.ability_active = False
    self.nun_protected = False # separate flag needed for this to distinguish between baron-steal and this
    self.ability_objects = []
    self.retrieved = None
    self.act_reasoning = None
    self.relationships = dict()
    self.group_context = None
    self.movement_cooldown = 7



    if check_if_file_exists(f_saved):
        # note: for now the loading does NOT include role
        scratch_load = json.load(open(f_saved))

        self.att_bandwidth = scratch_load["att_bandwidth"]
        self.retention = scratch_load["retention"]

        self.curr_time = datetime.timedelta(seconds=scratch_load['curr_time'])
        self.curr_loc = scratch_load["curr_loc"]

        self.name = scratch_load["name"]
        self.first_name = scratch_load["first_name"]
        self.last_name = scratch_load["last_name"]
        self.gender = scratch_load["gender"]
        self.age = scratch_load["age"]
        self.innate = scratch_load["innate"]

        self.recency_w = scratch_load["recency_w"]
        self.relevance_w = scratch_load["relevance_w"]
        self.importance_w = scratch_load["importance_w"]
        self.importance_ele_n = scratch_load["importance_ele_n"]
        self.recency_decay = scratch_load["recency_decay"]
        self.importance_trigger_max = scratch_load["importance_trigger_max"]
        self.importance_trigger_curr = scratch_load["importance_trigger_curr"]

        #self.role = scratch_load["role"]
        self.current_bidding_scores = scratch_load["current_bidding_scores"]
        self.cards_slot = set(scratch_load["cards_slot"])
        self.recent_conversation = scratch_load["recent_conversation"]
        self.win_progress = scratch_load["win_progress"]
        self.ability_active = scratch_load["ability_active"]
        self.nun_protected = scratch_load["nun_protected"]
        self.ability_objects = scratch_load["ability_objects"]
        self.retrieved = scratch_load["retrieved"]
        self.act_reasoning = scratch_load["act_reasoning"]
        self.relationships = scratch_load["relationships"]
        self.group_context = scratch_load["group_context"]


  def save(self, out_json):
    scratch = dict()
    scratch["att_bandwidth"] = self.att_bandwidth
    scratch["retention"] = self.retention
    scratch["curr_time"] = self.curr_time.total_seconds()
    scratch["curr_loc"] = self.curr_loc
    scratch["name"] = self.name
    scratch["first_name"] = self.first_name
    scratch["last_name"] = self.last_name
    scratch["age"] = self.age
    scratch["gender"] = self.gender
    scratch["innate"] = self.innate
    scratch["recency_w"] = self.recency_w
    scratch["relevance_w"] = self.relevance_w
    scratch["importance_w"] = self.importance_w
    scratch["importance_ele_n"] = self.importance_ele_n
    scratch["recency_decay"] = self.recency_decay
    scratch["importance_trigger_max"] = self.importance_trigger_max
    scratch["importance_trigger_curr"] = self.importance_trigger_curr
    #scratch["role"] = self.role
    scratch["current_bidding_scores"] = self.current_bidding_scores
    scratch["cards_slot"] = list(self.cards_slot)
    scratch["recent_conversation"] = self.recent_conversation
    scratch["win_progress"] = self.win_progress
    scratch["ability_active"] = self.ability_active
    scratch["nun_protected"] = self.nun_protected
    scratch["ability_objects"] = self.ability_objects
    scratch["retrieved"] = self.retrieved
    scratch["act_reasoning"] = self.act_reasoning
    scratch["relationships"] = self.relationships
    scratch["group_context"] = self.group_context

    with open(out_json, "w") as outfile:
        json.dump(scratch, outfile, indent=2)


  def get_str_iss(self): 
    """
    ISS stands for "identity stable set." This describes the commonset summary
    of this persona -- basically, the bare minimum description of the persona
    that gets used in almost all prompts that need to call on the persona. 

    INPUT
      None
    OUTPUT
      the identity stable set summary of the persona in a string form.
    EXAMPLE STR OUTPUT
      "Name: Dolores Heitmiller
       Age: 28
       Innate traits: hard-edged, independent, loyal
       Learned traits: Dolores is a painter who wants live quietly and paint 
         while enjoying her everyday life.
       Currently: Dolores is preparing for her first solo show. She mostly 
         works from home.
       Lifestyle: Dolores goes to bed around 11pm, sleeps for 7 hours, eats 
         dinner around 6pm.
       Daily plan requirement: Dolores is planning to stay at home all day and 
         never go out."
    """
    commonset = ""
    commonset += f"Your name: {self.name}\n"
    commonset += f"Your age: {self.age}\n"
    commonset += f"Your gender: {self.gender}\n"
    commonset += f"Context of the wider game group: {self.group_context}"
    commonset += f"Your personality and information: {self.innate}\n"
    #commonset += f"Current Date: {self.curr_time.strftime('%A %B %d')}\n"
    return commonset


  def get_str_name(self): 
    return self.name


  def get_str_firstname(self): 
    return self.first_name


  def get_str_lastname(self): 
    return self.last_name



  def get_str_innate(self): 
    return self.innate


  def act_time_str(self): 
    """
    Returns a string output of the current time. 

    INPUT
      None
    OUTPUT 
      A string output of the current time.
    EXAMPLE STR OUTPUT
      "14:05 P.M."
    """
    return self.act_start_time.strftime("%H:%M %p")


