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
from persona.cognitive_modules.perceive import generate_poig_score as generate_perception_poig_score

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
    self.ensure_own_card_identity()

  def ensure_own_card_identity(self):
    if not self.scratch.name:
      return
    legacy_role_card = self.scratch.role
    canonical = owned_role_card(self)
    if legacy_role_card in self.scratch.cards_slot and canonical not in self.scratch.cards_slot:
      self.scratch.cards_slot.discard(legacy_role_card)
      self.scratch.cards_slot.add(canonical)
    protection_cards = nun_protection_cards(self)
    self.scratch.nun_protection_cards = protection_cards
    self.scratch.nun_protected = bool(protection_cards)

  def has_own_card(self, role=None):
    return has_own_role_card(self, role)

  def protected_by_nun(self):
    self.scratch.nun_protected = has_nun_protection(self)
    return self.scratch.nun_protected

  def reset_movement_cooldown_after_action(self, table, action_name):
    if self.scratch.movement_cooldown != 0:
      self.scratch.movement_cooldown = 0
      debug_log(
        f"[ACTION-COOLDOWN-RESET] t={self.scratch.curr_time} | table={table.name} | "
        f"character={self.scratch.name} | action={action_name} | movement_cooldown=0"
      )
    changed = []
    for other_name, other_persona in table.personas.items():
      if other_persona is self or other_name == self.scratch.name:
        continue
      previous = other_persona.scratch.movement_cooldown
      current = max(
        0,
        previous - NON_SPEAKING_ACTION_MOVEMENT_COOLDOWN_DECREMENT,
      )
      if current == previous:
        continue
      other_persona.scratch.movement_cooldown = current
      changed.append((other_name, previous, current))
    if changed:
      debug_log(
        f"[ACTION-TABLE-COOLDOWN] t={self.scratch.curr_time} | table={table.name} | "
        f"character={self.scratch.name} | action={action_name} | "
        f"decrement={NON_SPEAKING_ACTION_MOVEMENT_COOLDOWN_DECREMENT} | changed={changed}"
      )

  def queen_drag_blocked_by_immunity(self, table, target_name, destination=None):
    if target_name not in table.personas:
      return False
    target = table.personas[target_name]
    destination_text = f" to {destination}" if destination else ""
    if has_nun_protection(target):
      target.show_nun_protection(
        table,
        self.scratch.name,
        "Queen",
        target_name,
        f"drag you{destination_text}",
      )
      if debug:
        debug_log(
          f"[QUEEN-DRAG-BLOCKED] t={self.scratch.curr_time} | table={table.name} | "
          f"queen={self.scratch.name} | target={target_name} | destination={destination} | "
          "reason=nun_protection"
        )
      return True
    if target.scratch.role != "Farmer":
      return False
    act_desp = tr(
      "event.queen.blocked_by_farmer",
      target=target_name,
      queen=self.scratch.name,
      table=display_name("table", table.name),
    )
    table.add_table_event(
      (
        target_name,
        self.scratch.name,
        act_desp,
        self.scratch.curr_time,
        set(table.personas.keys()) | {"Farmer", "Queen"},
      )
    )
    target.speak(
      table,
      (
        f"the Queen {self.scratch.name} has just tried to drag you{destination_text}, "
        "but you are the Farmer and immune to the Queen ability; reveal your Farmer card now, "
        "make clear that the drag fails before movement, and remain at this table"
      ),
      consume_cooldown=False,
    )
    if debug:
      debug_log(
        f"[QUEEN-DRAG-BLOCKED] t={self.scratch.curr_time} | table={table.name} | "
        f"queen={self.scratch.name} | target={target_name} | destination={destination} | "
        "reason=farmer_immunity"
      )
    return True

  def queen_drag_blocked_by_king_lock(self, table, target_name, destination=None):
    if target_name not in table.personas:
      return False
    target = table.personas[target_name]
    king_locks = [
      benefactor
      for benefactor, locked_target, lock_role in table.lockdown_targets
      if lock_role == "King" and locked_target == target_name and benefactor != target_name
    ]
    if not king_locks:
      return False
    family = ROLE_DICT[target.scratch.role]["family"]
    destination_text = f" to {destination}" if destination else ""
    target.speak(
      table,
      (
        f"the Queen {self.scratch.name} is trying to drag you{destination_text}, "
        f"but a King's lockdown is holding your family, {family}, at this table; "
        "react in the moment without revealing your exact role"
      ),
      consume_cooldown=False,
    )
    act_desp = tr(
      "event.queen.blocked_by_king",
      queen=self.scratch.name,
      target=target_name,
      family=display_name("family", family),
      table=display_name("table", table.name),
    )
    table.add_table_event(
      (
        self.scratch.name,
        target_name,
        act_desp,
        self.scratch.curr_time,
        set([self.scratch.name, target_name, "Queen", "King", family]),
      )
    )
    return True

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
    act_desp = tr(
      "event.table.stays_quiet",
      character=self.scratch.name,
      reason=reason,
    )
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
    act_desp = tr(
      "event.nun.protection",
      target=target_name,
      source=source_name,
      role=display_name("role", source_role),
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
      witnesses = set()
      for lock in matching_locks:
        witnesses.update(getattr(table, "lockdown_witnesses", {}).pop(lock, set(table.personas.keys())))
      if not witnesses:
        witnesses = set(table.personas.keys())
      locked_targets = sorted(lock[1] for lock in matching_locks)
      keywords = set([stolen_player_name, baron_name, stolen_role] + locked_targets)
      if stolen_role == "King":
        locked_families = sorted({
          ROLE_DICT[self.room.personas[target].scratch.role]["family"]
          for target in locked_targets
          if target in self.room.personas
        })
        family_text = ", ".join(
          display_name("family", family) for family in locked_families
        ) or tr("event.targeted_family")
        act_desp = tr(
          "event.lock.nullified_by_theft",
          holder=stolen_player_name,
          role=display_name("role", "King"),
          targets=family_text,
          baron=baron_name,
        )
      else:
        targets_text = ", ".join(locked_targets) if locked_targets else tr("event.locked_target")
        act_desp = tr(
          "event.lock.nullified_by_theft",
          holder=stolen_player_name,
          role=display_name("role", stolen_role),
          targets=targets_text,
          baron=baron_name,
        )
      debug_log(f"[LOCKDOWN-NULLIFIED] t={self.scratch.curr_time} | table={table.name} | audience={sorted(witnesses)} | {act_desp}")
      nullify_event = (baron_name, stolen_player_name, act_desp, self.scratch.curr_time, keywords | witnesses, witnesses)
      write_table_event_log(table.name, nullify_event)
      table.add_table_event(nullify_event, log_event=False)

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


  def resolve_baron_reaction(
    self,
    table,
    revealed_player_name,
    action_context,
    block_ability=True,
    bishop_correct_guess=False,
    bishop_target_name=None,
    bishop_guessed_family=None,
  ):
    if len(table.personas) < 3 or revealed_player_name not in table.personas:
      return False
    revealed_player = table.personas[revealed_player_name]
    if revealed_player.scratch.role == "Farmer":
      return False
    if not has_own_role_card(revealed_player):
      return False

    def eligible_baron_candidates(excluded_names=None):
      excluded_names = set(excluded_names or [])
      candidates = []
      for candidate_name, candidate in table.personas.items():
        if candidate_name in excluded_names or candidate_name == revealed_player_name:
          continue
        if candidate.scratch.role != "Baron" or not has_own_role_card(candidate):
          continue
        candidates.append((candidate_name, candidate))
      return candidates

    def baron_reaction_bid(baron_name, baron, target_player, target_action_context, reaction_context, debug_tag, known_baron_trophy_cards=None):
      baron.update_knowledge(self.room)
      decision = prompt_dict(
        run_gpt_prompt_decide_baron_block(
          baron,
          table,
          target_player,
          target_action_context,
          reaction_context,
          known_baron_trophy_cards=known_baron_trophy_cards,
        ),
        {"reasoning": "I will not reveal myself as Baron for this trigger.", "bid": "0"}
      )
      raw_bid = decision.get("bid")
      if raw_bid is None:
        raw_bid = 6 if str(decision.get("result", "no")).strip().lower() == "yes" else 0
      bid = bounded_int(raw_bid, 0)
      if bid >= 6:
        bid = 6
      elif bid >= 3:
        bid = 3
      else:
        bid = 0
      reasoning = decision.get("reasoning", "")
      debug_log(
        f"[{debug_tag}] t={self.scratch.curr_time} | table={table.name} | "
        f"baron={baron_name} | target={target_player.scratch.name} | bid={bid} | "
        f"reasoning={reasoning}"
      )
      return {"baron_name": baron_name, "baron": baron, "bid": bid, "reasoning": reasoning}

    def choose_baron_bidder(bid_records, debug_tag):
      active_bids = [record for record in bid_records if record["bid"] > 0]
      if not active_bids:
        return None
      top_bid = max(record["bid"] for record in active_bids)
      top_records = [record for record in active_bids if record["bid"] == top_bid]
      winner = random.choice(top_records)
      if len(top_records) > 1:
        debug_log(
          f"[{debug_tag}-TIEBREAK] t={self.scratch.curr_time} | table={table.name} | "
          f"bid={top_bid} | candidates={[record['baron_name'] for record in top_records]} | "
          f"winner={winner['baron_name']}"
        )
      return winner

    def resolve_baron_steal(baron_name, baron, target_player, target_action_context, target_is_primary_baron=False, known_baron_trophy_cards=None):
      stolen_role = target_player.scratch.role
      known_baron_trophy_cards = set(known_baron_trophy_cards or [])
      baron.reset_movement_cooldown_after_action(table, "baron-reaction")
      special_circumstance = (
        f"you are revealing your Baron card right now to react to {target_player.scratch.name}'s action "
        f"and steal the {stolen_role} card now. This is happening in this moment; do not imply "
        f"that you already had {target_player.scratch.name}'s {stolen_role} card before this reaction"
      )
      if len(role_pool_for_mode()) == 16 and stolen_role == "Baron":
        special_circumstance = (
          f"you are revealing your Baron card right now to react to the Baron {target_player.scratch.name}. "
          f"In expanded mode you steal {target_player.scratch.name}'s trophy cards only, not {target_player.scratch.name}'s own Baron role card"
        )
      elif block_ability and not target_is_primary_baron:
        special_circumstance += f", blocking {target_player.scratch.name}'s {stolen_role} ability before it resolves"
      else:
        special_circumstance += " after their reveal has already been made"
      if block_ability and stolen_role == "Bishop" and bishop_correct_guess:
        special_circumstance += (
          f". Special case: the Bishop's guess that {bishop_target_name} belongs to the "
          f"{bishop_guessed_family} family is actually correct, but if your Baron block succeeds, "
          f"that correct guess will not exile {bishop_target_name} because the Bishop ability never resolves. "
          "Your reaction may acknowledge or gloat about thwarting a correct guess, but must not claim the guess itself was wrong"
        )
      baron.speak(table, special_circumstance)
      if has_nun_protection(target_player):
        if len(role_pool_for_mode()) == 16 and stolen_role == "Baron":
          attempt_desp = tr(
            "event.baron.attempt_trophies",
            baron=baron_name,
            target=target_player.scratch.name,
          )
          effect_description = f"steal your Baron trophies"
        elif block_ability and not target_is_primary_baron:
          attempt_desp = tr(
            "event.baron.attempt_block_steal",
            baron=baron_name,
            target=target_player.scratch.name,
            role=display_name("role", stolen_role),
          )
          effect_description = (
            f"block your {stolen_role} ability and steal your {stolen_role} card"
          )
        else:
          attempt_desp = tr(
            "event.baron.attempt_steal",
            baron=baron_name,
            target=target_player.scratch.name,
            role=display_name("role", stolen_role),
          )
          effect_description = f"steal your {stolen_role} card after your reveal"
        table.add_table_event((baron_name, target_player.scratch.name, attempt_desp, self.scratch.curr_time, set([baron_name, target_player.scratch.name, "Baron", stolen_role])))
        self.show_nun_protection(table, baron_name, "Baron", target_player.scratch.name, effect_description)
        return set()
      if len(role_pool_for_mode()) == 16 and stolen_role == "Baron":
        stolen_trophies = held_trophy_cards(target_player)
        target_player.scratch.cards_slot.difference_update(stolen_trophies)
        target_player.scratch.nun_protection_cards.difference_update(stolen_trophies)
        target_player.scratch.baron_obfuscated_trophy_cards.difference_update(stolen_trophies)
        target_player.scratch.nun_protected = has_nun_protection(target_player)
        baron.scratch.cards_slot.update(stolen_trophies)
        if target_is_primary_baron:
          baron.scratch.baron_obfuscated_trophy_cards.update(stolen_trophies - known_baron_trophy_cards)
          for visible_card in known_baron_trophy_cards:
            visible_owner = card_owner(visible_card)
            visible_role = card_role(visible_card)
            if visible_owner in self.room.personas and visible_role:
              set_baron_stolen_claim(self.room.personas[visible_owner], visible_role, baron_name)
        known_trophy_text = ", ".join(describe_card(card) for card in sorted(known_baron_trophy_cards)) if known_baron_trophy_cards else ""
        if target_is_primary_baron:
          act_desp = tr(
            "event.baron.countersteal_trophies",
            baron=baron_name,
            target=target_player.scratch.name,
            known=known_trophy_text or tr("event.none_noted"),
          )
        elif block_ability:
          act_desp = tr(
            "event.baron.block_trophies",
            baron=baron_name,
            target=target_player.scratch.name,
          )
        else:
          act_desp = tr(
            "event.baron.steal_trophies",
            baron=baron_name,
            target=target_player.scratch.name,
          )
        stolen_cards = set(stolen_trophies)
      else:
        removed_cards = remove_own_role_card(target_player, stolen_role)
        baron.scratch.cards_slot.update(removed_cards or {card_id(stolen_role, target_player.scratch.name)})
        stolen_cards = set(removed_cards or {card_id(stolen_role, target_player.scratch.name)})
        set_baron_stolen_claim(target_player, stolen_role, baron_name)
        if block_ability:
          act_desp = tr(
            "event.baron.block_steal",
            baron=baron_name,
            target=target_player.scratch.name,
            role=display_name("role", stolen_role),
          )
        else:
          act_desp = tr(
            "event.baron.steal_after_reveal",
            baron=baron_name,
            target=target_player.scratch.name,
            role=display_name("role", stolen_role),
          )
        self.clear_active_locks_after_card_stolen(target_player.scratch.name, stolen_role, baron_name)
      table.add_table_event((baron_name, target_player.scratch.name, act_desp, self.scratch.curr_time, set([baron_name, target_player.scratch.name, "Baron", stolen_role])))
      if stolen_role == "Baron":
        stolen_card_text = ", ".join(describe_card(card) for card in sorted(stolen_cards))
        if stolen_card_text:
          victim_reaction_context = (
            f"the Baron {baron_name} has just successfully stolen your Baron trophy cards from you: "
            f"{stolen_card_text}. Your own Baron role card was not taken. "
            "React immediately as the victim of this steal without claiming that you still hold the stolen trophies"
          )
        else:
          victim_reaction_context = (
            f"the Baron {baron_name} has just resolved a Baron-on-Baron steal against you, but you had no trophy cards "
            "for them to take and your own Baron role card was not taken. React immediately to that outcome"
          )
      else:
        blocked_text = (
          f" Your attempted {stolen_role} ability was also blocked before resolving."
          if block_ability
          else " Your reveal itself remains public even though the physical card was stolen afterward."
        )
        victim_reaction_context = (
          f"the Baron {baron_name} has just successfully stolen your own {stolen_role} role card from you. "
          f"You still have the {stolen_role} role, family, and win condition, but you no longer physically hold your role card."
          f"{blocked_text} React immediately as the victim of this steal"
        )
      target_player.speak(table, victim_reaction_context, consume_cooldown=False)
      return stolen_cards

    primary_context = (
      "This is a primary Baron reaction to another player's reveal or attempted ability. "
      "If multiple Barons react, the highest bid acts first; tied top bids are broken randomly."
    )
    primary_bids = [
      baron_reaction_bid(baron_name, baron, revealed_player, action_context, primary_context, "BARON-REACTION-BID")
      for baron_name, baron in eligible_baron_candidates()
    ]
    primary_winner = choose_baron_bidder(primary_bids, "BARON-REACTION")
    if not primary_winner:
      return False

    primary_baron_name = primary_winner["baron_name"]
    primary_baron = primary_winner["baron"]
    primary_stolen_cards = resolve_baron_steal(primary_baron_name, primary_baron, revealed_player, action_context)
    if has_nun_protection(revealed_player):
      return False

    counter_candidates = eligible_baron_candidates(excluded_names={primary_baron_name, revealed_player_name})
    if len(role_pool_for_mode()) == 16 and counter_candidates and primary_baron_name in table.personas:
      counter_context = (
        f"The Baron {primary_baron_name} has just revealed a Baron card and claimed the reaction first. "
        f"If you counterreact, you do NOT take {primary_baron_name}'s own Baron role card; you steal {primary_baron_name}'s Baron trophy cards. "
        "This can move the original victim's stolen card from the first Baron to you."
      )
      counter_action_context = (
        f"{primary_baron_name} reveals a Baron card to block/steal from {revealed_player_name}. "
        f"Original trigger: {action_context}"
      )
      counter_bids = [
        baron_reaction_bid(
          baron_name,
          baron,
          primary_baron,
          counter_action_context,
          counter_context,
          "BARON-COUNTER-BID",
          known_baron_trophy_cards=primary_stolen_cards,
        )
        for baron_name, baron in counter_candidates
      ]
      counter_winner = choose_baron_bidder(counter_bids, "BARON-COUNTER")
      if counter_winner:
        resolve_baron_steal(
          counter_winner["baron_name"],
          counter_winner["baron"],
          primary_baron,
          counter_action_context,
          target_is_primary_baron=True,
          known_baron_trophy_cards=primary_stolen_cards,
        )
    return True


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
      "expression": "neutral",
      "action": "does nothing",
      "line": "I need a moment to think this through.",
    }
    speak_dict = {**default_line, **(speak_dict or {})}
    if speak_dict["object"] not in table.personas and speak_dict["object"] != "everyone":
      speak_dict["object"] = "everyone"
    if speak_dict["volume"] not in {"whisper", "calm", "loud", "practically screaming"}:
      speak_dict["volume"] = "calm"
    speak_dict["expression"] = normalize_dialogue_expression(speak_dict.get("expression"))
    speak_dict["action"] = normalize_dialogue_action(speak_dict.get("action"))
    speak_dict["line"] = str(speak_dict.get("line") or default_line["line"]).strip() or default_line["line"]
    return speak_dict

  def remember_own_dialogue(self, table, dialogue_tuple):
    s_chat, o_chat, volume, expression, action, line, timestamp_chat, audience, keywords_chat = unpack_dialogue(dialogue_tuple)
    if s_chat != self.scratch.name:
      return
    if audience and self.scratch.name not in audience:
      return
    target_text = o_chat or f"all of {table.name}"
    audience_text = ", ".join(sorted(audience)) if audience else "unknown"
    description = (
      f"{s_chat}, to {target_text}: [{volume}, {expression}] "
      f"{format_dialogue_payload(action, line)} "
      f"[People physically present for this line: {audience_text}]"
    )
    chat_poignancy = generate_perception_poig_score(
      self,
      "chat",
      description,
      s_chat,
      target_text,
      keywords_chat,
    )
    if description in self.a_mem.embeddings:
      line_embedding = self.a_mem.embeddings[description]
    else:
      line_embedding = get_embedding(description)
    node = self.a_mem.add_chat(
      timestamp_chat,
      s_chat,
      target_text,
      table.name,
      description,
      keywords_chat,
      chat_poignancy,
      (description, line_embedding),
    )
    self.scratch.importance_ele_n += 1
    self.scratch.dialogue_cursors[table.name] = len(table.dialogue_history)
    self.scratch.recent_conversation[0:0] = [(self.scratch.curr_time, [node])]
    self.scratch.recent_conversation = self.scratch.recent_conversation[:self.scratch.retention]

  def emit_speech_dict(self, table, speak_dict, consume_cooldown=True):
    speak_dict = self.normalize_speech_dict(table, speak_dict)
    table.add_table_dialogue((
      self.scratch.name,
      speak_dict["object"],
      speak_dict["volume"],
      speak_dict["expression"],
      speak_dict["action"],
      speak_dict["line"],
      self.scratch.curr_time,
      set([self.scratch.name, speak_dict["object"]]),
    ))
    self.remember_own_dialogue(table, table.dialogue_history[-1])
    if consume_cooldown and ENABLE_SPEAKING_COOLDOWN:
      self.scratch.speaking_cooldown = max(self.scratch.speaking_cooldown, 1)
    return speak_dict

  def speak(self, table, special_circumstance=None, consume_cooldown=True):
    self.update_knowledge(self.room)
    default_line = self.normalize_speech_dict(table)
    if special_circumstance:
      speak_dict = prompt_dict(run_gpt_prompt_generate_next_convo_line_special(self, table, special_circumstance), default_line)
    else:
      speak_dict = prompt_dict(run_gpt_prompt_generate_next_convo_line_normal(self, table), default_line)
    return self.emit_speech_dict(table, speak_dict, consume_cooldown=consume_cooldown)

  def broadcast_global_reveal_event(self, origin_table, role, local_description):
    if not self.room:
      return
    remote_description = tr(
      "event.card.global_reveal_heard",
      table=display_name("table", origin_table.name),
      description=local_description,
    )
    keywords = set([self.scratch.name, role, ROLE_DICT[role]["family"], origin_table.name])
    for table_name, table in self.room.locations.items():
      if table_name == origin_table.name:
        continue
      table.add_table_event((self.scratch.name, None, remote_description, self.scratch.curr_time, keywords), log_event=False)

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
      target_reasoning = target_dict.get("reasoning", "")
      self.scratch.current_bidding_reasonings["ability_target"] = target_reasoning
      debug_ability_target(self, table, requested_target, final_target, enriched_ability_reasoning, target_reasoning)
      return final_target
    fallback = possible_targets[0] if possible_targets else self.scratch.name
    target_dict = prompt_dict(run_gpt_prompt_select_ability_target(self, table, enriched_ability_reasoning), {"target": fallback})
    requested_target = target_dict["target"]
    final_target = requested_target if requested_target in possible_targets else fallback
    target_reasoning = target_dict.get("reasoning", "")
    self.scratch.current_bidding_reasonings["ability_target"] = target_reasoning
    debug_ability_target(self, table, requested_target, final_target, enriched_ability_reasoning, target_reasoning)
    return final_target

  def guess_family_bishop(self, target, table):
    ability_reasoning = (self.scratch.current_bidding_reasonings or {}).get("ability", "")
    target_reasoning = (self.scratch.current_bidding_reasonings or {}).get("ability_target", "")
    return prompt_dict(
      run_gpt_prompt_guess_family_bishop(self, target, table, ability_reasoning, target_reasoning),
      {"reasoning": "I have to make my best guess from limited evidence.", "guess": "Commoners"}
    )

  def respond_to_wrong_bishop_guess(self, bishop, guessed_family, table):
    default_response = {
      "reasoning": "I will not give the table a verified reveal just because the Bishop guessed wrong.",
      "response": "no reveal",
      "object": bishop.scratch.name,
      "volume": "calm",
      "expression": "unimpressed",
      "action": "does nothing",
      "line": "Wrong, but I am not handing you proof for free.",
    }
    response_dict = prompt_dict(
      run_gpt_prompt_bishop_wrong_guess_response(self, bishop, guessed_family, table),
      default_response
    )
    response = str(response_dict.get("response", "no reveal")).strip().lower()
    if response not in {"hard reveal", "soft reveal", "no reveal"}:
      response = "no reveal"
    if response == "hard reveal" and not self.has_own_card():
      response = "no reveal"
      response_dict["line"] = "That guess is wrong, but I cannot prove it with a card right now."
    obj = response_dict.get("object", "everyone")
    if obj not in table.personas and obj != "everyone":
      obj = "everyone"
    response_dict["object"] = obj
    response_dict = self.normalize_speech_dict(table, response_dict)
    volume = response_dict["volume"]
    line = response_dict["line"]
    table.add_table_dialogue((
      self.scratch.name,
      obj,
      volume,
      response_dict["expression"],
      response_dict["action"],
      line,
      self.scratch.curr_time,
      set([self.scratch.name, obj]),
    ))
    self.remember_own_dialogue(table, table.dialogue_history[-1])
    if ENABLE_SPEAKING_COOLDOWN:
      self.scratch.speaking_cooldown = max(self.scratch.speaking_cooldown, 1)
    debug_log(
      f"[BISHOP-WRONG-RESPONSE] t={self.scratch.curr_time} | table={table.name} | "
      f"bishop={bishop.scratch.name} | target={self.scratch.name} | guessed_family={guessed_family} | "
      f"response={response} | reasoning={response_dict.get('reasoning', '')}"
    )
    if response == "hard reveal":
      act_desp = tr(
        "event.bishop.wrong_guess_hard_reveal",
        target=self.scratch.name,
        role=display_name("role", self.scratch.role),
        bishop=bishop.scratch.name,
        family=display_name("family", guessed_family),
      )
      table.add_table_event((
        self.scratch.name,
        bishop.scratch.name,
        act_desp,
        self.scratch.curr_time,
        {
          self.scratch.name,
          bishop.scratch.name,
          self.scratch.role,
          "Bishop",
          guessed_family,
        },
      ))
      self.resolve_baron_reaction(table, self.scratch.name, act_desp, block_ability=False)

  def card_retrieval_options(self, table):
    options = []
    nun_holder_names = set()
    if self.scratch.role == "Nun":
      possible_holders = set(self.scratch.ability_objects or []) if self.scratch.ability_active else set()
      possible_holders.update(
        name
        for name, player in table.personas.items()
        if has_nun_protection(player)
      )
      for holder_name in sorted(possible_holders):
        if (
          holder_name in table.personas
          and has_card(table.personas[holder_name].scratch.cards_slot, "Nun", self.scratch.name)
          and has_nun_protection(table.personas[holder_name])
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
        baron_claim = baron_stolen_claim(self, self.scratch.role)
        can_attempt_baron_retrieval = bool(baron_claim) and not has_own_role_card(self)
        if (
          other_name not in nun_holder_names
          and can_attempt_baron_retrieval
        ):
          options.append({
            "target": other_name,
            "kind": "baron",
            "description": (
              f"probe {other_name} in this one-on-one to see whether they might currently hold your {self.scratch.role} card after a Baron theft. "
              "You do not know for certain that they have it; this may fail if they are not the Baron holding that card now."
            )
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
      "event_msg": tr(
        "event.movement.departure",
        character=self.scratch.name,
        destination=display_name("table", destination),
      ),
    }
    if role not in {"Queen", "Spinster"}:
      return [normal_record]
    if not self.has_own_card(role):
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

    self.reset_movement_cooldown_after_action(table, f"{role.lower()}-movement-ability")
    target_name = self.select_ability_target(table, ability_reasoning)
    poss = self.possessive_for()
    obj = "her" if self.scratch.gender == "female" else "him"
    movement_reasoning = self.scratch.current_movement_reasoning or "I had already decided to leave."

    if role == "Queen":
      ability_attempt_context = tr(
        "event.ability.attempt",
        character=self.scratch.name,
        role=display_name("role", "Queen"),
        target=target_name,
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
        self.scratch.movement_cooldown = 0
        return []
      if self.queen_drag_blocked_by_immunity(table, target_name, destination):
        normal_record["farewell"] = False
        return [normal_record]
      if self.queen_drag_blocked_by_king_lock(table, target_name, destination):
        normal_record["farewell"] = False
        normal_record["speech_constraint"] = (
          f"your Queen drag attempt on {target_name} failed because a King's lockdown holds "
          "that target's family at this table; leave alone without implying they are following you"
        )
        return [normal_record]

      self.scratch.ability_active = True
      target = table.personas[target_name]
      target.speak(
        table,
        f"the Queen has just successfully activated {poss} ability after deciding to leave for {destination}, chose you as the target, and is about to drag you there, as parting words: "
        "(For this occasion, the Queen ability has succeeded; do not claim or imply that this current drag was nullified just because an earlier Queen lock or drag was broken)",
        consume_cooldown=False,
      )
      event_msg = tr(
        "event.queen.drag_departure",
        queen=self.scratch.name,
        destination=display_name("table", destination),
        target=target_name,
      )
      table.add_table_event((self.scratch.name, target_name, event_msg, self.scratch.curr_time, set([self.scratch.name, target_name])))
      return [
        {"name": self.scratch.name, "destination": destination, "benefactor": None, "farewell": False, "event_msg": None},
        {"name": target_name, "destination": destination, "benefactor": self.scratch.name, "farewell": False, "event_msg": None},
      ]

    if role == "Spinster":
      ability_attempt_context = tr(
        "event.spinster.mark_departure",
        spinster=self.scratch.name,
        target=target_name,
        origin=display_name("table", "Forest"),
        destination=display_name("table", destination),
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
    if has_nun_protection(target):
      self.show_nun_protection(
        table,
        self.scratch.name,
        "Spinster",
        target_name,
        "force you to reveal your role card"
      )
      act_desp = tr(
        "event.spinster.reveal_blocked_nun",
        target=target_name,
        spinster=self.scratch.name,
      )
      table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([target_name, self.scratch.name, "Nun"])))
      return
    if not has_own_role_card(target):
      special_circumstance = (
        f"the departing Spinster {self.scratch.name} has forced you to reveal your role card, "
        "but you do not currently have your own role card and therefore cannot prove/reveal it"
      )
      target.speak(table, special_circumstance)
      act_desp = tr(
        "event.spinster.reveal_missing_card",
        target=target_name,
        spinster=self.scratch.name,
      )
      table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([target_name, self.scratch.name])))
      return
    if target.scratch.role == "Farmer":
      special_circumstance = (
        f"the departing Spinster {self.scratch.name} has forced you to reveal your Farmer card. "
        "You are normally immune to other players' abilities, but in this oddly useless edge case "
        "the card reveal is also how you prove you are Farmer, so lampshade that the proof still has to happen "
        "and do not describe this as immunity preventing the reveal. "
        "The Baron cannot block the Spinster forcing this reveal, and Farmer protection also prevents Barons from reacting to the Farmer card reveal afterward"
      )
    else:
      special_circumstance = (
        f"the departing Spinster {self.scratch.name} has forced you to reveal "
        f"your {target.scratch.role} card to the table. The Baron cannot block the Spinster forcing this reveal, "
        "but a Baron may still react to the card you reveal afterward"
      )
    target.speak(table, special_circumstance)
    act_desp = tr(
      "event.spinster.forced_reveal",
      target=target_name,
      spinster=self.scratch.name,
      role=display_name("role", target.scratch.role),
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
        "expression": "focused",
        "action": "surveys the table",
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
    expression = normalize_dialogue_expression(guess_dict.get("expression"))
    action = normalize_dialogue_action(guess_dict.get("action"))
    table.add_table_dialogue((
      self.scratch.name,
      "everyone",
      "calm",
      expression,
      action,
      line,
      self.scratch.curr_time,
      set([self.scratch.name] + target_names),
    ))
    self.remember_own_dialogue(table, table.dialogue_history[-1])

    self.scratch.endgame_role_guesses = guesses
    guess_text = ", ".join(
      tr(
        "event.spinster.guess_entry",
        name=name,
        role=display_name("role", role),
      )
      for name, role in guesses.items()
    ) or tr("event.spinster.no_guesses")
    debug_log(
      f"[SPINSTER-ENDGAME-GUESS] t={self.scratch.curr_time} | table={table.name} | "
      f"character={self.scratch.name} | guesses={guesses} | reasoning={guess_dict.get('reasoning')} | line={line}"
    )
    act_desp = tr(
      "event.spinster.final_guesses",
      spinster=self.scratch.name,
      guesses=guess_text,
    )
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
      "retrieve": 5,
      "ability": 4,
      "nun-reveal": 3,
      "reveal": 2,
      "speak": 1,
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

    if final_option != "speak":
      self.reset_movement_cooldown_after_action(table, final_option)

    if final_option == "ability":
      if not self.has_own_card(action_role):
        act_desp = tr(
          "event.ability.missing_card",
          character=self.scratch.name,
          role=display_name("role", action_role),
        )
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
        act_desp = tr(
          "event.movement.departure",
          character=self.scratch.name,
          destination=display_name("table", "Village"),
        )
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

      if action_role == "Bishop":
        target = table.personas[target_name]
        guess_dict = self.guess_family_bishop(target, table)
        guess = guess_dict.get("guess", ROLE_DICT[target.scratch.role]["family"])
        family_options = {role_data["family"] for role_data in ROLE_DICT.values()}
        if guess not in family_options:
          guess = ROLE_DICT[target.scratch.role]["family"]
        debug_log(
          f"[BISHOP-GUESS] t={self.scratch.curr_time} | table={table.name} | "
          f"bishop={self.scratch.name} | target={target_name} | guessed_family={guess} | "
          f"reasoning={guess_dict.get('reasoning', '')}"
        )
        ability_attempt_context = tr(
          "event.bishop.attempt",
          bishop=self.scratch.name,
          role=display_name("role", action_role),
          target=target_name,
          family=display_name("family", guess),
        )
        ability_speech_context = (
          f"you are revealing your Bishop card and attempting to use your ability on {target_name}; "
          f"you have already chosen to guess that {target_name}'s family is {guess}. "
          "Say what you want the table to hear before the ability resolves, and do not imply a different guessed family"
        )
        self.speak(
          table,
          with_optional_speaking_reasoning(
            with_winning_act_reasoning(
              ability_speech_context,
              "ability",
            )
          )
        )
        table.add_table_event((
          self.scratch.name,
          target_name,
          ability_attempt_context,
          self.scratch.curr_time,
          {self.scratch.name, target_name, action_role, guess},
        ))
        if self.resolve_baron_reaction(
          table,
          self.scratch.name,
          ability_attempt_context,
          block_ability=True,
          bishop_correct_guess=(guess == ROLE_DICT[target.scratch.role]["family"]),
          bishop_target_name=target_name,
          bishop_guessed_family=guess,
        ):
          return
        if has_nun_protection(target):
          self.show_nun_protection(
            table,
            self.scratch.name,
            action_role,
            target_name,
            "guess your family and force you to leave if the guess is correct"
          )
          return
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
          act_desp = tr(
            "event.bishop.correct_guess",
            bishop=self.scratch.name,
            target=target_name,
            family=display_name("family", guess),
            destination=display_name("table", next_loc),
          )
          table.add_table_event((
            self.scratch.name,
            target_name,
            act_desp,
            self.scratch.curr_time,
            {self.scratch.name, target_name, "Bishop", guess},
          ))
        return

      ability_attempt_context = tr(
        "event.ability.attempt",
        character=self.scratch.name,
        role=display_name("role", action_role),
        target=(
          display_name("family", target_name)
          if action_role == "King"
          else target_name
        ),
      )
      ability_speech_context = (
        f"you are revealing your {action_role} card and attempting to use your ability on {target_name}; "
        "say what you want the table to hear before the ability resolves"
      )
      if action_role == "King":
        ability_speech_context += (
          ". Important: a King's lock only affects already-seated players of the chosen family at this table right now. "
          "Do not say or imply that this use will trap people currently in transit, later arrivals, or anyone not physically present here"
        )
      resolved_ability_speech_context = with_optional_speaking_reasoning(
        with_winning_act_reasoning(
          ability_speech_context,
          "ability",
        )
      )
      if action_role == "King":
        seated_names = ", ".join(sorted(table.personas)) or "none"
        transit_names = ", ".join(sorted(getattr(self.room, "transit", {}))) or "none"
        resolved_ability_speech_context += (
          f". FINAL AUTHORITATIVE CORRECTION: only these currently seated players can possibly be caught by this activation: {seated_names}. "
          f"These transit players are explicitly not caught, even if they arrive immediately afterward: {transit_names}. "
          "If the earlier bid reasoning counted an excluded player as a victim of this lock, disregard that part and do not repeat it in the line"
        )
      self.speak(
        table,
        resolved_ability_speech_context,
      )
      table.add_table_event((self.scratch.name, target_name, ability_attempt_context, self.scratch.curr_time, set([self.scratch.name, target_name])))
      if action_role != "Spinster" and self.resolve_baron_reaction(table, self.scratch.name, ability_attempt_context, block_ability=True):
        return

      if action_role == "King":
        self.scratch.ability_active = True
        for other_player_name, other_player in table.personas.items():
          if other_player_name != self.scratch.name and ROLE_DICT[other_player.scratch.role]["family"] == target_name:
            if has_nun_protection(other_player):
              self.show_nun_protection(
                table,
                self.scratch.name,
                "King",
                other_player_name,
                "lock you at this table"
              )
            elif other_player.scratch.role == "Farmer":
              special_circumstance = f"the King {self.scratch.name} is trying to use {poss} ability on you and you have to reveal your Farmer card to prove you're immune,"
              act_desp = tr(
                "event.card.reveal",
                character=other_player_name,
                role=display_name("role", "Farmer"),
              )
              table.add_table_event((other_player_name, None, act_desp, self.scratch.curr_time, set([other_player_name])))
              other_player.speak(table, special_circumstance)
            else:
              lock = (self.scratch.name, other_player_name, action_role)
              table.lockdown_targets.add(lock)
              table.lockdown_witnesses[lock] = set(table.personas.keys())
              self.scratch.ability_objects.append(other_player_name)
              self.scratch.ability_locations.add(table.name)
        act_desp = tr(
          "event.king.lock",
          king=self.scratch.name,
          family=display_name("family", target_name),
          table=display_name("table", table.name),
        )
        public_keywords = {self.scratch.name, "King", ROLE_DICT["King"]["family"], target_name, table.name}
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, public_keywords))
        return

      target = table.personas[target_name]

      if action_role == "Nun":
        self.scratch.ability_active = True
        nun_cards = remove_own_role_card(self, "Nun")
        self.scratch.ability_objects.append(target_name)
        granted_cards = nun_cards or {card_id("Nun", self.scratch.name)}
        target.scratch.cards_slot.update(granted_cards)
        target.scratch.nun_protection_cards.update(granted_cards)
        target.scratch.nun_protected = True
        target.speak(
          table,
          (
            f"the Nun {self.scratch.name} has just successfully given you {poss} Nun card. "
            "You now physically hold that Nun card and are protected by it, while keeping your own role, family, and win condition unchanged. "
            "React immediately to accepting this protection without claiming that the Nun card is your own role card"
          ),
          consume_cooldown=False,
        )
        act_desp = tr(
          "event.nun.give_protection",
          nun=self.scratch.name,
          target=target_name,
        )
        table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name, "Nun"])))
        return

      if has_nun_protection(target):
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
        act_desp = tr(
          "event.priest.force_reveal",
          priest=self.scratch.name,
          target=target_name,
          role=display_name("role", "Farmer"),
        )
        table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))
        return

      if target.scratch.role == "Farmer":
        special_circumstance = f"the {action_role} {self.scratch.name} is trying to use {poss} ability on you and you have to reveal your Farmer card to prove you're immune,"
        act_desp = tr(
          "event.card.reveal",
          character=target_name,
          role=display_name("role", "Farmer"),
        )
        table.add_table_event((target_name, None, act_desp, self.scratch.curr_time, set([target_name])))
        target.speak(table, special_circumstance)
        return

      if action_role == "Thief":
        if target.scratch.role == "Thief":
          special_circumstance = f"the Thief {self.scratch.name} is trying to use {poss} ability on you, but Thieves are immune to Thief swaps; answer that failed attempt in the moment"
          target.speak(table, special_circumstance)
          act_desp = tr(
            "event.thief.blocked_by_thief",
            thief=self.scratch.name,
            target=target_name,
          )
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name, "Thief"])))
          return
        if not has_own_role_card(target):
          special_circumstance = f"the Thief {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
          target.speak(table, special_circumstance)
        else:
          old_role = self.scratch.role
          target_old_role = target.scratch.role
          thief_extra_cards = held_non_own_cards(self)
          target_extra_cards = held_non_own_cards(target)
          removed_self_cards = remove_own_role_card(self, old_role)
          removed_target_cards = remove_own_role_card(target, target_old_role)
          self.scratch.cards_slot.update(
            retag_cards_owner(removed_target_cards, self.scratch.name)
            or {card_id(target_old_role, self.scratch.name)}
          )
          if target_old_role == "Baron":
            transferred_obfuscated = set(target.scratch.baron_obfuscated_trophy_cards) & set(target_extra_cards)
            self.scratch.cards_slot.update(target_extra_cards)
            self.scratch.baron_obfuscated_trophy_cards.update(transferred_obfuscated)
            target.scratch.cards_slot.difference_update(target_extra_cards)
            target.scratch.baron_obfuscated_trophy_cards.difference_update(target_extra_cards)
          self.scratch.role = target_old_role
          target.scratch.cards_slot.update(
            retag_cards_owner(removed_self_cards, target.scratch.name)
            or {card_id(old_role, target.scratch.name)}
          )
          if old_role == "Baron":
            transferred_obfuscated = set(self.scratch.baron_obfuscated_trophy_cards) & set(thief_extra_cards)
            target.scratch.cards_slot.update(thief_extra_cards)
            target.scratch.baron_obfuscated_trophy_cards.update(transferred_obfuscated)
            self.scratch.cards_slot.difference_update(thief_extra_cards)
            self.scratch.baron_obfuscated_trophy_cards.difference_update(thief_extra_cards)
          target.scratch.role = old_role
          self.scratch.movement_cooldown = 0
          add_thief_swap_lock(table, self.scratch.name, target_name)
          act_desp = tr(
            "event.thief.swap",
            thief=self.scratch.name,
            old_role=display_name("role", old_role),
            target=target_name,
            thief_new_role=display_name("role", self.scratch.role),
          )
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))
          special_circumstance = (
            f"the Thief {self.scratch.name} has just successfully swapped roles and cards with you. "
            f"You were {target_old_role}, but now you are the Thief, while {self.scratch.name} is now {self.scratch.role}. "
            "React in the moment to this successful forced swap"
          )
          target.speak(table, special_circumstance)

      elif action_role == "Queen":
        special_circumstance = f"you, as Queen, have just activated your ability to force {target_name} to follow you"
        next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
        if self.queen_drag_blocked_by_king_lock(table, target_name, next_loc):
          table.removal_targets.add((None, self.scratch.name, action_role, next_loc))
          event_msg = tr(
            "event.queen.drag_failed_departure",
            queen=self.scratch.name,
            destination=display_name("table", next_loc),
            target=target_name,
          )
          table.add_table_event((self.scratch.name, target_name, event_msg, self.scratch.curr_time, set([self.scratch.name, target_name, "Queen", "King"])))
          return
        self.scratch.ability_active = True
        table.removal_targets.add((None, self.scratch.name, action_role, next_loc))
        table.removal_targets.add((self.scratch.name, target_name, action_role, next_loc))
        special_circumstance = (
          f"the Queen has just successfully activated {poss} ability, chose you as the target, and is about to drag you to depart to the {next_loc}, as parting words: "
          "(For this occasion, the Queen ability has succeeded; do not claim or imply that this current drag was nullified just because an earlier Queen lock or drag was broken)"
        )
        target.speak(table, special_circumstance, consume_cooldown=False)
        event_msg = tr(
          "event.queen.drag_departure",
          queen=self.scratch.name,
          destination=display_name("table", next_loc),
          target=target_name,
        )
        table.add_table_event((self.scratch.name, target_name, event_msg, self.scratch.curr_time, set([self.scratch.name, target_name])))

      elif action_role == "Spinster":
        special_circumstance = f"you, as Spinster, have just activated your ability"
        next_loc = self.select_ability_destination(table, retrieved_all_tables, special_circumstance)
        table.removal_targets.add((None, self.scratch.name, action_role, next_loc, target_name))
        act_desp = tr(
          "event.spinster.mark_departure_resolved",
          spinster=self.scratch.name,
          destination=display_name("table", next_loc),
          target=target_name,
        )
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))

      elif action_role == "Priest":
        if not has_own_role_card(target):
          special_circumstance = f"the Priest {self.scratch.name} is trying to use {poss} ability on you but you don't have your role card with you thus want to use this to prove you're immune,"
          target.speak(table, special_circumstance)
        else:
          special_circumstance = f"the Priest {self.scratch.name} has used {poss} ability on you and now you HAVE to show or state your {target.scratch.role} card to {obj},"
          target.speak(table, special_circumstance)
          act_desp = tr(
            "event.priest.force_reveal",
            priest=self.scratch.name,
            target=target_name,
            role=display_name("role", target.scratch.role),
          )
          table.add_table_event((self.scratch.name, target_name, act_desp, self.scratch.curr_time, set([self.scratch.name, target_name])))

    elif final_option == "reveal":
      if not self.has_own_card(action_role):
        act_desp = tr(
          "event.card.reveal_failed",
          character=self.scratch.name,
          role=display_name("role", action_role),
        )
        table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
        if not self.maybe_stay_silent(table, "they cannot prove their role card right now"):
          self.speak(table, f"you want to reveal your {action_role} card, but you cannot prove it because you do not currently have your role card")
        return
      reveal_speech = self.speak(
        table,
        with_optional_speaking_reasoning(
          with_winning_act_reasoning(
            f"you are revealing your {action_role} card without using your ability; say what you want the table to hear as/accompanying this reveal",
            "reveal",
          )
        )
      )
      if reveal_speech.get("volume") == "practically screaming":
        act_desp = tr(
          "event.card.reveal_global",
          character=self.scratch.name,
          role=display_name("role", action_role),
        )
      else:
        act_desp = tr(
          "event.card.reveal_without_ability",
          character=self.scratch.name,
          role=display_name("role", action_role),
        )
      table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name])))
      if reveal_speech.get("volume") == "practically screaming":
        self.broadcast_global_reveal_event(table, action_role, act_desp)
      self.resolve_baron_reaction(table, self.scratch.name, act_desp, block_ability=False)

    elif final_option == "nun-reveal":
      if not (self.scratch.role != "Nun" and has_nun_protection(self)):
        act_desp = tr(
          "event.nun.show_failed",
          character=self.scratch.name,
        )
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
      act_desp = tr(
        "event.nun.show_protection",
        character=self.scratch.name,
      )
      table.add_table_event((self.scratch.name, None, act_desp, self.scratch.curr_time, set([self.scratch.name, "Nun"])))

    elif final_option == "retrieve":
      retrieval_options = self.card_retrieval_options(table)
      if not retrieval_options:
        act_desp = tr(
          "event.card.retrieval_unavailable",
          character=self.scratch.name,
        )
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
            and has_nun_protection(table.personas[object])
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
    card_owner_name = self.scratch.name
    if kind == "nun":
      attempt_desp = tr(
        "event.card.request_nun_return",
        nun=self.scratch.name,
        holder=object,
      )
      request_circumstance = f"you are demanding your Nun card back from {object} and ending your protection of them"
    else:
      attempt_desp = tr(
        "event.card.request_stolen_return",
        character=self.scratch.name,
        holder=object,
        role=display_name("role", card_name),
      )
      request_circumstance = (
        f"you are trying to find out whether {object} is currently the Baron holding your {card_name} card, "
        "and if so to demand it back because you are alone together"
      )
    if action_reasoning:
      request_circumstance += (
        f". When you won the internal bid for this retrieve action, your reasoning was: {action_reasoning}"
      )

    self.speak(table, request_circumstance)
    table.add_table_event((self.scratch.name, object, attempt_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name])))

    def log_failed_retrieval(reason_key):
      failed_desp = tr(
        "event.card.retrieval_failed",
        character=self.scratch.name,
        holder=object,
        reason=tr(
          reason_key,
          holder=object,
          role=display_name("role", card_name),
        ),
      )
      table.add_table_event((self.scratch.name, object, failed_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name])))

    if object not in table.personas:
      log_failed_retrieval("event.card.failure.holder_left")
      return False
    holder = table.personas[object]
    if kind == "nun":
      missing_holder_circumstance = f"the Nun {self.scratch.name} is demanding the Nun card back from you, but you no longer have it; answer that failed demand in the moment"
      holder_circumstance = f"the Nun {self.scratch.name} is requiring you to return the Nun card now; you have to comply and lose the Nun card protection"
    else:
      missing_holder_circumstance = f"{self.scratch.name} is asking whether you can return {poss} {card_name} card, but you do not have it; answer that failed demand in the moment"
      holder_circumstance = f"{self.scratch.name} is reclaiming {poss} {card_name} card from you now because you are alone together; you have to comply"
    if kind == "nun":
      if not has_card(table.personas[object].scratch.cards_slot, "Nun", self.scratch.name):
        holder.speak(table, missing_holder_circumstance)
        log_failed_retrieval("event.card.failure.no_nun")
        return False
    elif not has_card(table.personas[object].scratch.cards_slot, self.scratch.role, self.scratch.name):
      holder.speak(table, missing_holder_circumstance)
      log_failed_retrieval("event.card.failure.no_role")
      return False

    holder.speak(table, holder_circumstance)

    removed_cards = matching_cards(table.personas[object].scratch.cards_slot, card_name, card_owner_name)
    if not removed_cards and card_name in table.personas[object].scratch.cards_slot:
      removed_cards = {card_name}
    table.personas[object].scratch.cards_slot.difference_update(removed_cards)
    table.personas[object].scratch.baron_obfuscated_trophy_cards.difference_update(removed_cards)
    if kind == "nun":
      table.personas[object].scratch.nun_protection_cards.difference_update(removed_cards)
    self.scratch.cards_slot.update(removed_cards or {card_id(card_name, card_owner_name)})
    self.scratch.baron_obfuscated_trophy_cards.difference_update(removed_cards)
    if kind == "nun":
      table.personas[object].scratch.nun_protected = has_nun_protection(table.personas[object])
      self.scratch.ability_active = False
      self.scratch.ability_objects = [name for name in self.scratch.ability_objects if name != object]
      if table.personas[object].scratch.nun_protected:
        act_desp = tr(
          "event.card.retrieve_nun_still_protected",
          nun=self.scratch.name,
          holder=object,
        )
      else:
        act_desp = tr(
          "event.card.retrieve_nun_revoke",
          nun=self.scratch.name,
          holder=object,
        )
      retrieval_event = (self.scratch.name, object, act_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name]))
      table.add_table_event(retrieval_event)
    else:
      self.scratch.baron_stolen_card_claims.pop(self.scratch.role, None)
      act_desp = tr(
        "event.card.retrieve",
        character=self.scratch.name,
        role=display_name("role", card_name),
        holder=object,
      )
      retrieval_event = (self.scratch.name, object, act_desp, self.scratch.curr_time, set([self.scratch.name, object, card_name]))
      table.add_table_event(retrieval_event)
    return True



  def get_personal_game_context(self):
    table_information = self.scratch.curr_loc
    your_role = self.scratch.role
    your_family = ROLE_DICT[your_role]["family"]
    your_role_label = protocol_display_name("role", your_role)
    your_family_label = protocol_display_name("family", your_family)
    your_ability = ROLE_DICT[your_role]["ability"]
    your_win_condition = ROLE_DICT[your_role]["win_condition"]
    # note: in the win_progress reflection prompt add the baron's progress check
    your_win_progress = self.scratch.win_progress
    held_cards = sorted(self.scratch.cards_slot)
    own_card_status = own_role_card_custody_text(self, self.room)
    other_cards = sorted(held_non_own_cards(self))
    other_cards_text = ", ".join(describe_card_for_persona(self, card) for card in other_cards) if other_cards else "none"
    personal_context_msg = self.scratch.get_str_iss()
    for relationship_name, relationship in self.scratch.relationships.items():
      personal_context_msg += f"Your relationship with {relationship_name}: {relationship}\n"
      game_specific_context = str(
        self.scratch.game_specific_relationship_contexts.get(relationship_name, "") or ""
      ).strip()
      if game_specific_context:
        personal_context_msg += (
          f"Additional relationship context with {relationship_name} for THIS GAME ONLY: "
          f"{game_specific_context}\n"
        )
    self.scratch.nun_protected = has_nun_protection(self)
    nun_protection_status = " You are currently protected by the Nun card.\n" if self.scratch.nun_protected else "\n"
    personal_context_msg += f"You are currently at the {table_information}. Your private assigned role is {your_role_label}, which means your family is {your_family_label}.\nYour ability is: {your_ability}\nYour win condition is: {your_win_condition}\n{own_card_status} You are currently holding {len(other_cards)} other players' role card(s): {other_cards_text}.{nun_protection_status}"
    if your_role == "Baron":
      trophy_cards = sorted(held_trophy_cards(self))
      trophy_text = ", ".join(describe_card_for_persona(self, card) for card in trophy_cards) if trophy_cards else "none"
      required_trophies = baron_trophy_requirement()
      remaining_trophies = max(0, required_trophies - len(trophy_cards))
      personal_context_msg += (
        f"BARON TROPHY STATUS: Your own Baron card is NOT a trophy and NEVER counts toward your win condition. "
        f"Only other players' cards you are holding count. You currently have {len(trophy_cards)} trophy card(s): {trophy_text}. "
        f"You need {remaining_trophies} more trophy card(s) to reach the required {required_trophies}.\n"
      )
    personal_context_msg += (
      f"TIME ELAPSED SINCE THE GAME STARTED: "
      f"{timedelta_to_natural(self.scratch.curr_time)}.\n"
    )
    return personal_context_msg

  
  
