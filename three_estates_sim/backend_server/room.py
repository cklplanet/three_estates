import json
import numpy
import datetime
import pickle
import time
import math

from global_methods import *
from utils import *

class Location:
    def __init__(self, name):
        self.name = name
        self.connected = set()     # NAMES of adjacent locations
        self.revealed_cards = []
        self.events = set()        # events (and events corresponding to objects) happening at this location? maybe?
        self.current_lines = [] # format: list of ((subject, object, volume, contents, timestamp, keywords))
        self.current_events = [] # format: list of ((subject, object, act_desp, timestamp, keywords))
        self.personas = dict()
        self.removal_targets = set() # format: (sub, obj, subj_role, target_table)
        self.lockdown_targets = set() # format: (sub, obj, subj_role)
        #TODO?: solve conflicts between for example innkeeper-lockdown and king-lockdown
        self.incoming_arrivals = set() # format: (self, "benefactor"(optional), source_table)
        self.bishop_trigger = False
        self.baron_trigger = set() # set of player_names
        self.spinster_marked = None
        self.timer_expired = False

    def add_connection(self, other_location_name):
        self.connected.add(other_location_name)

    def select_next_actor(self):
        for persona in self.personas:
            pass

    def __repr__(self):
        return f"<Location: {self.name} | Connected: {list(self.connected)} | Contents: {self.contents}>"
    
    def add_table_event(self, event_tuple):
        self.current_events.append(event_tuple)
        print(f"({self.name})" + event_tuple[2])
    
    def add_table_dialogue(self, dialogue_tuple):
        self.current_lines.append(dialogue_tuple)
        print(f"({self.name})" + dialogue_tuple[0] + f"(to {dialogue_tuple[1]}):" + f" ({dialogue_tuple[2]})" + f" {dialogue_tuple[3]}")


class RoomGraph:
    def __init__(self, personas):
        self.locations = dict()
        self.personas = personas
        edges = [
            ("Forest", "Castle"),
            ("Castle", "Village"),
            ("Forest", "Village"),
        ]
        for a, b in edges:
            self.connect(a, b)
        

    def add_location(self, name):
        if name not in self.locations:
            self.locations[name] = Location(name)

    def connect(self, a, b):
        self.add_location(a)
        self.add_location(b)
        self.locations[a].add_connection(b)
        self.locations[b].add_connection(a)

    #def move_object(self, obj, from_loc, to_loc):
        #if to_loc in self.locations[from_loc].connected:
            #self.locations[from_loc].contents.remove(obj)
            #self.locations[to_loc].contents.append(obj)
        #else:
            #raise ValueError(f"{to_loc} not accessible from {from_loc}")

    def __getitem__(self, loc_name):
        return self.locations[loc_name]
    
    def get_nearby_locations(self, loc_name):
        return self.locations[loc_name].connected
    

    def add_event_to_location(self, curr_event, loc_name):
        self.locations[loc_name].events.add(curr_event)

    def remove_event_from_location(self, curr_event, loc_name):
        curr_location_ev_cp = self.locations[loc_name].events.copy()
        for event in curr_location_ev_cp:
            if event == curr_event:
                self.locations[loc_name].events.remove(event)

    def turn_event_from_location_idle(self, curr_event, loc_name):
        curr_location_ev_cp = self.locations[loc_name].events.copy()
        for event in curr_location_ev_cp: 
            if event == curr_event:  
                self.locations[loc_name].events.remove(event)
                new_event = (event[0], None, None, None)
                self.locations[loc_name].events.add(new_event)

    def remove_subject_events_from_location(self, subject, loc_name):
        curr_location_ev_cp = self.locations[loc_name].events.copy()
        for event in curr_location_ev_cp: 
            if event[0] == subject:  
                self.locations[loc_name].events.remove(event)


def path_finder(room, start: str, end: str) -> list:
    """
    Returns the shortest path between two locations in the RoomGraph using BFS.
    :param room: RoomGraph instance
    :param start: starting location (string)
    :param end: destination location (string)
    :return: list of location names from start to end (inclusive)
    """
    if start == end:
        return [start]

    visited = set()
    queue = [(start, [start])]

    while queue:
        current, path = queue.pop(0)
        visited.add(current)

        for neighbor in room.locations[current].connected:
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return []  # No path found
    
