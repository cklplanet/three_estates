from persona.persona import *
from room import *
from utils import *
from persona.cognitive_modules.plan import *
from persona.cognitive_modules.perceive import unpack_dialogue, generate_poig_score
from persona.prompt_template.run_gpt_prompt import (
    run_gpt_prompt_assign_immersion_roles,
    run_gpt_prompt_generate_vn_epilogue,
    run_gpt_prompt_select_relationship_pairs,
)
from persona.prompt_template.gpt_structure import get_embedding
import datetime
import random
import itertools
from global_methods import *
import os
import json
import shutil
import uuid
from collections import Counter
from paths import FRONTEND_SERVER_ROOT


folder_mem_saved = FRONTEND_SERVER_ROOT / "memory"
SESSION_CONTEXT_FILE = "character_context.json"
SESSION_METADATA_FILE = "session_metadata.json"
SESSION_STATE_FILE = "session_state.json"
RUN_LOG_TIME_FORMAT = "%Y%m%d_%H%M%S"
PHASE_CHECKPOINT_DIRS = {
    "departure_phase_complete": "last_departure_phase",
    "bidding_phase_complete": "last_bidding_phase",
    "arrival_phase_complete": "last_arrival_phase",
    "timestep_complete": "last_timestep_complete",
}
PHASE_SNAPSHOT_ROOT = "phase_snapshots"
TABLE_ACTIVITY_MOVEMENT_COOLDOWN_DECREMENT = 0.5
NON_PERSONA_SESSION_DIRS = {"dialogue_logs", PHASE_SNAPSHOT_ROOT}
NEW_SESSION_ALIASES = {"new", "n", "start new", "restart", "fresh"}
CONTINUE_SESSION_ALIASES = {"continue", "c", "resume", "r", "load"}
REUSE_CAST_SAME_ROLES_ALIASES = {"same roles", "same", "reuse roles", "reuse same", "cast roles", "2"}
REUSE_CAST_REROLL_ROLES_ALIASES = {"reroll roles", "reroll", "reassign roles", "reuse reroll", "cast reroll", "3"}
REUSE_EXACT_SETUP_ALIASES = {"exact setup", "exact", "same setup", "same tables", "reuse exact", "4"}
CHARACTER_GENERATION_NORMAL_ALIASES = {"normal", "n", "role first", "role-first", "standard", "1"}
CHARACTER_GENERATION_IMMERSION_ALIASES = {"immersion", "immersive", "temperament", "fit", "character first", "character-first", "2"}


class ThreeEstatesServer:
    def __init__(self):
        self.personas = dict()
        self.room = RoomGraph(self.personas)
        self.personas_loc = dict()
        self.sec_per_step = SIM_SECONDS_PER_STEP
        self.curr_time = datetime.timedelta(0)
        self.server_sleep = SERVER_SLEEP_SECONDS
        self.session_id = None
        self.dialogue_log_path = None
        self.clean_dialogue_log_path = None
        self.debug_log_path = None
        self.next_phase = "departure"
        self.endgame_mode = False
        self.room.endgame_mode = False
        self.game_mode = GAME_MODE
        self.exact_setup_movement_cooldowns = {}
        self.exact_setup_starting_tables = {}
        self.exceptional_departure_timestamps = set()

    def configure_game_mode(self, mode):
        mode = str(mode or "10").strip()
        if mode not in ROLE_POOLS:
            mode = "10"
        set_game_mode(mode)
        self.game_mode = mode
        self.room = RoomGraph(self.personas)
        self.room.endgame_mode = self.endgame_mode

    def sync_endgame_mode(self):
        locked_count = sum(
            1
            for table_name, table in self.room.locations.items()
            if table_name != "Wilderness" and table.timer_expired
        )
        should_enter = locked_count >= 2
        if should_enter and not self.endgame_mode:
            self.endgame_mode = True
            self.room.endgame_mode = True
            if debug:
                debug_log(
                    f"[ENDGAME-MODE] t={self.curr_time} | locked_tables={locked_count} | "
                    f"seconds_per_bidding_phase={ENDGAME_SECONDS_PER_PHASE}"
                )
        else:
            self.room.endgame_mode = self.endgame_mode

    def randomized_starting_movement_cooldown(self):
        low = max(0, STARTING_MOVEMENT_COOLDOWN_STEPS - STARTING_MOVEMENT_COOLDOWN_RADIUS)
        high = max(0, STARTING_MOVEMENT_COOLDOWN_STEPS + STARTING_MOVEMENT_COOLDOWN_RADIUS)
        return random.randint(low, high)

    def seed_exact_setup_movement_cooldowns(self, cast):
        if self.exact_setup_movement_cooldowns:
            return
        self.exact_setup_movement_cooldowns = {
            character["name"]: self.randomized_starting_movement_cooldown()
            for character in cast
            if character.get("name")
        }

    def seed_exact_setup_starting_tables(self, cast):
        valid_tables = set(TIMERS.keys())
        for character in cast:
            name = character.get("name")
            if not name or name in self.exact_setup_starting_tables:
                continue
            starting_table = character.get("starting_table")
            if starting_table in valid_tables:
                self.exact_setup_starting_tables[name] = starting_table

    def exact_setup_table_for(self, persona):
        table = self.exact_setup_starting_tables.get(persona.scratch.name)
        if table in TIMERS:
            return table
        if persona.scratch.curr_loc in TIMERS:
            return persona.scratch.curr_loc
        return None

    def arrival_speaking_context(self, persona, table_name, source_table, benefactor=None, base_context=None):
        parts = [base_context or f"you are arriving at this table from {source_table}"]
        table = self.room.locations.get(table_name)
        if table:
            present_names = sorted(table.personas.keys())
            present_text = ", ".join(present_names) if present_names else "no one"
            parts.append(
                f"The people physically present at {table_name} right now are: {present_text}. "
            )
        inbound_names = sorted(
            name for name, transit_data in self.room.transit.items()
            if transit_data.get("destination") == table_name and name != persona.scratch.name
        )
        inbound_text = ", ".join(inbound_names) if inbound_names else "no one"
        parts.append(
            f"The people still in transit toward {table_name}, not yet seated, are: {inbound_text}. "
        )
        if benefactor:
            parts.append(f"You were brought here by {benefactor}'s ability rather than by your own free movement choice.")
        if persona.scratch.arrival_overheard_context:
            heard_lines = "\n".join(f"- {line}" for line in persona.scratch.arrival_overheard_context)
            parts.append(
                "While approaching this table, you just overheard these line(s); treat them as immediate fresh context:\n"
                f"{heard_lines}"
            )
        movement_reasoning = persona.scratch.current_movement_reasoning
        movement_destination = persona.scratch.current_movement_destination
        if movement_reasoning and not benefactor and movement_destination == table_name:
            destination_note = f" toward {movement_destination}"
            parts.append(
                f"When you decided to move{destination_note}, your reasoning was: {movement_reasoning}"
            )
        ability_reasoning = (persona.scratch.current_bidding_reasonings or {}).get("ability")
        if ability_reasoning:
            parts.append(f"When you bid to use your ability, your reasoning was: {ability_reasoning}")
        return " ".join(parts)

    def clear_table_locks(self, table, breaker_name, trigger):
        if not table.lockdown_targets:
            return
        remaining_locks = set()
        cleared_locks = set()
        cleared_lock_families = {}
        for benefactor, target, role in table.lockdown_targets:
            should_clear = False
            if trigger == "enter":
                should_clear = role == "Innkeeper"
            elif trigger == "leave":
                if role == "Innkeeper":
                    should_clear = breaker_name == benefactor
                elif role == "Queen":
                    should_clear = breaker_name == benefactor or breaker_name != target
                elif role == "King":
                    breaker_is_locked_by_this_king = breaker_name == target and breaker_name != benefactor
                    should_clear = breaker_name == benefactor or not breaker_is_locked_by_this_king

            if should_clear:
                cleared_locks.add((benefactor, target, role))
                if role == "King" and target in self.personas:
                    cleared_lock_families.setdefault((benefactor, role), set()).add(ROLE_DICT[self.personas[target].scratch.role]["family"])
            else:
                remaining_locks.add((benefactor, target, role))

        if not cleared_locks:
            return

        table.lockdown_targets = remaining_locks
        previous_benefactors = {(lock[0], lock[2]) for lock in cleared_locks}
        for previous_benefactor, role in previous_benefactors:
            if previous_benefactor in self.personas:
                self.refresh_lock_holder_state(previous_benefactor, role)
            family_note = ""
            if role == "King":
                family_text = ", ".join(sorted(cleared_lock_families.get((previous_benefactor, role), {"the targeted family"})))
                family_note = f" against {family_text}"
            act_desp = f"{previous_benefactor}'s lockdown ability as {role}{family_note} is nullified by {breaker_name} {trigger}ing"
            matching_locks = {
                lock for lock in cleared_locks
                if lock[0] == previous_benefactor and lock[2] == role
            }
            witnesses = set()
            for lock in matching_locks:
                witnesses.update(getattr(table, "lockdown_witnesses", {}).pop(lock, set(table.personas.keys())))
            if not witnesses:
                witnesses = set(table.personas.keys())
            nullify_event = (
                breaker_name,
                previous_benefactor,
                act_desp,
                self.curr_time,
                set([breaker_name, previous_benefactor]) | witnesses,
                witnesses,
            )
            debug_log(f"[LOCKDOWN-NULLIFIED] t={self.curr_time} | table={table.name} | audience={sorted(witnesses)} | {act_desp}")
            write_table_event_log(table.name, nullify_event)
            table.add_table_event(nullify_event, log_event=False)

    def active_lock_targets_and_locations(self, benefactor_name, role):
        targets = []
        locations = set()
        for table_name, table in self.room.locations.items():
            table_targets = [
                target
                for benefactor, target, lock_role in table.lockdown_targets
                if benefactor == benefactor_name and lock_role == role
            ]
            if table_targets:
                locations.add(table_name)
                targets.extend(table_targets)
        return targets, locations

    def refresh_lock_holder_state(self, benefactor_name, role):
        if benefactor_name not in self.personas:
            return
        targets, locations = self.active_lock_targets_and_locations(benefactor_name, role)
        self.personas[benefactor_name].scratch.ability_objects = targets
        self.personas[benefactor_name].scratch.ability_locations = locations
        self.personas[benefactor_name].scratch.ability_active = bool(targets)

    def is_locked_at_table(self, table, persona_name):
        for benefactor, target, _role in table.lockdown_targets:
            if target == persona_name and benefactor != persona_name:
                return True
        return False

    def sync_persona_times(self):
        for persona in self.personas.values():
            persona.scratch.curr_time = self.curr_time

    def refresh_audible_dialogue_limits(self):
        self.room.audible_dialogue_limits = {
            table_name: len(table.dialogue_history)
            for table_name, table in self.room.locations.items()
        }

    def advance_phase_time(self, phase_name):
        phase_seconds = self.sec_per_step
        if self.endgame_mode:
            phase_seconds = ENDGAME_SECONDS_PER_PHASE
        self.curr_time += datetime.timedelta(seconds=phase_seconds)
        self.sync_persona_times()
        self.refresh_audible_dialogue_limits()
        if debug:
            debug_log(
                f"[PHASE-TIME] phase={phase_name} | advanced_by={phase_seconds}s | "
                f"endgame_mode={self.endgame_mode} | t={self.curr_time}"
            )

    def enter_transit(self, name, source_table, destination, benefactor=None):
        self.personas[name].scratch.curr_loc = destination
        self.personas[name].scratch.speaking_cooldown = 0
        self.room.locations[destination].incoming_arrivals.add((name, benefactor, source_table))
        self.room.transit[name] = {
            "source": source_table,
            "destination": destination,
            "benefactor": benefactor,
            "since": self.curr_time,
            "dialogue_cursors": {
                table_name: len(table.dialogue_history)
                for table_name, table in self.room.locations.items()
            }
        }

    def clear_thief_swap_locks(self, table, reason, trigger_name=None):
        cleared = clear_thief_swap_locks_for_table_change(table, trigger_name=trigger_name)
        if cleared and debug:
            trigger_text = f" | trigger={trigger_name}" if trigger_name else ""
            debug_log(
                f"[THIEF-SWAP-LOCK-BROKEN] t={self.curr_time} | table={table.name} | "
                f"reason={reason}{trigger_text} | cleared_pairs={[sorted(pair) for pair in cleared]}"
            )
        return cleared

    def resolve_departure_record(self, table, table_name, departure):
        name = departure["name"]
        destination = departure["destination"]
        benefactor = departure.get("benefactor")
        if name not in table.personas:
            return False
        self.clear_table_locks(table, name, "leave")
        self.clear_thief_swap_locks(table, "departure", trigger_name=name)
        if departure.get("farewell", True):
            special_circumstance = f"you have decided to leave {table.name} for {destination};"
            movement_reasoning = self.personas[name].scratch.current_movement_reasoning
            movement_destination = self.personas[name].scratch.current_movement_destination
            if movement_reasoning and movement_destination == destination and not benefactor:
                special_circumstance += f" your movement reasoning was: {movement_reasoning}."
                special_circumstance += (
                    " This departure itself has not resolved any role ability unless an explicit event already did; "
                    "do not claim you have swapped roles, stolen cards, locked anyone, revealed a card, or used an ability "
                    "as part of this move unless that mechanical action has already been logged."
                )
            if departure.get("speech_constraint"):
                special_circumstance += f" {departure['speech_constraint']}."
            special_circumstance += " As parting words before you depart, "
            self.personas[name].speak(table, special_circumstance, consume_cooldown=False)
        event_msg = departure.get("event_msg")
        if event_msg:
            table.add_table_event((name, None, event_msg, self.curr_time, set([name])))
        self.enter_transit(name, table_name, destination, benefactor)
        del table.personas[name]
        spinster_reveal_target = departure.get("spinster_reveal_target")
        if spinster_reveal_target:
            self.personas[name].resolve_spinster_forced_reveal(table, spinster_reveal_target)
        return True

    def process_removal_targets(self, table, table_name, only_roles=None):
        removal_targets = list(table.removal_targets)
        random.shuffle(removal_targets)
        for removal_target in removal_targets:
            action_role = removal_target[2]
            if only_roles is not None and action_role not in only_roles:
                continue
            if removal_target not in table.removal_targets:
                continue
            table.removal_targets.remove(removal_target)
            target_name = removal_target[1]
            destination = removal_target[3]
            if target_name not in table.personas:
                continue
            target_persona = self.personas[target_name]
            self.clear_table_locks(table, target_name, "leave")
            self.clear_thief_swap_locks(table, "departure", trigger_name=target_name)
            bishop_exile_result = {}
            if action_role == "Bishop":
                bishop_exile_result = self.resolve_bishop_exile_movement_ability(table, table_name, target_persona, destination, removal_target[0])
                destination = bishop_exile_result.get("destination", destination)
            self.enter_transit(target_name, table_name, destination, removal_target[0])
            if target_name in table.personas:
                del table.personas[target_name]
            bishop_spinster_reveal_target = bishop_exile_result.get("spinster_reveal_target")
            if bishop_spinster_reveal_target and target_persona.scratch.role == "Spinster":
                target_persona.resolve_spinster_forced_reveal(table, bishop_spinster_reveal_target)
            if len(removal_target) > 4 and target_persona.scratch.role == "Spinster":
                target_persona.resolve_spinster_forced_reveal(table, removal_target[4])

    def resolve_bishop_exile_movement_ability(self, table, table_name, exiled_persona, destination, bishop_name):
        role = exiled_persona.scratch.role
        if role not in {"Queen", "Spinster"}:
            return {}
        if not exiled_persona.has_own_card(role):
            return {}
        if len(table.personas) <= 1:
            return {}
        if role == "Spinster" and table.name != "Forest":
            return {}

        prior_movement_reasoning = exiled_persona.scratch.current_movement_reasoning or ""
        prior_act_reasoning = exiled_persona.scratch.act_reasoning or ""
        prior_context = ""
        if prior_movement_reasoning:
            prior_context += (
                f" Before this forced departure, your latest recorded move/destination reasoning was: "
                f"{prior_movement_reasoning}"
            )
        if prior_act_reasoning:
            prior_context += (
                f" Your latest strongest action-bid impulse before this was: {prior_act_reasoning}"
            )
        force_context = (
            f"You are being forced to leave {table.name} for {destination} because Bishop {bishop_name} "
            "correctly guessed your family. Even though the departure is forced, your movement-triggered "
            "ability may still be attached to the moment of leaving if revealing your card is worth it."
            f"{prior_context}"
        )
        should_use, ability_reasoning = exiled_persona.decide_movement_ability_use(
            table,
            destination,
            movement_reasoning_override=force_context,
        )
        if not should_use:
            return {}

        target_name = exiled_persona.select_ability_target(table, ability_reasoning)
        if target_name not in table.personas or target_name == exiled_persona.scratch.name:
            return {}
        poss = exiled_persona.possessive_for()
        obj = "her" if exiled_persona.scratch.gender == "female" else "him"

        if role == "Queen":
            ability_attempt_context = (
                f"{exiled_persona.scratch.name} reveals {exiled_persona.role_card_text(role='Queen')} and attempts to use "
                f"{poss} Queen ability on {target_name} while being exiled by Bishop {bishop_name}."
            )
            exiled_persona.speak(
                table,
                f"Bishop {bishop_name} is forcing you to leave for {destination}; now you are revealing your Queen card "
                f"and trying to make {target_name} follow you. Your ability-use reasoning was: {ability_reasoning}",
                consume_cooldown=False,
            )
            table.add_table_event((exiled_persona.scratch.name, target_name, ability_attempt_context, self.curr_time, set([exiled_persona.scratch.name, target_name, bishop_name])))
            if exiled_persona.resolve_baron_reaction(table, exiled_persona.scratch.name, ability_attempt_context, block_ability=True):
                exiled_persona.update_knowledge(self.room)
                _, _, _, _, retrieved_all_tables = exiled_persona.scratch.retrieved
                blocked_context = (
                    f"Bishop {bishop_name} is still forcing you to leave {table.name}, but your Queen ability was just blocked "
                    f"and your Queen card may no longer be in your hand. Choose your exile destination again under this new context."
                )
                new_destination = exiled_persona.select_ability_destination(table, retrieved_all_tables, blocked_context)
                exiled_persona.speak(
                    table,
                    f"your Queen ability was blocked while you were being exiled by Bishop {bishop_name}; "
                    f"you must still leave, and you have now chosen to go to {new_destination}",
                    consume_cooldown=False,
                )
                return {"destination": new_destination}
            if exiled_persona.queen_drag_blocked_by_king_lock(table, target_name, destination):
                return {}
            exiled_persona.scratch.ability_active = True
            table.personas[target_name].speak(
                table,
                f"the exiled Queen {exiled_persona.scratch.name} has just successfully activated {poss} ability, chose you as the target, and is dragging you to {destination}, as parting words: "
                "(For this occasion, the Queen ability has succeeded; do not claim or imply that this current drag was nullified just because an earlier Queen lock or drag was broken)",
                consume_cooldown=False,
            )
            event_msg = (
                f"{exiled_persona.scratch.name} reveals {exiled_persona.role_card_text(role='Queen')} while being exiled "
                f"and drags {target_name} to {destination} with {obj} using {poss} ability."
            )
            table.add_table_event((exiled_persona.scratch.name, target_name, event_msg, self.curr_time, set([exiled_persona.scratch.name, target_name, bishop_name])))
            self.clear_table_locks(table, target_name, "leave")
            self.clear_thief_swap_locks(table, "departure", trigger_name=target_name)
            self.enter_transit(target_name, table_name, destination, exiled_persona.scratch.name)
            if target_name in table.personas:
                del table.personas[target_name]
            return {}

        if role == "Spinster":
            ability_attempt_context = (
                f"{exiled_persona.scratch.name} reveals {exiled_persona.role_card_text(role='Spinster')} and attempts to use "
                f"{poss} Spinster ability on {target_name} while being exiled by Bishop {bishop_name} to {destination}."
            )
            exiled_persona.speak(
                table,
                f"Bishop {bishop_name} is forcing you to leave for {destination}; now you are revealing your Spinster card "
                f"and marking {target_name}. Your ability-use reasoning was: {ability_reasoning}",
                consume_cooldown=False,
            )
            table.add_table_event((exiled_persona.scratch.name, target_name, ability_attempt_context, self.curr_time, set([exiled_persona.scratch.name, target_name, bishop_name])))
            return {"spinster_reveal_target": target_name}

        return {}

    def expire_table_timer_if_needed(self, table):
        if table.timer_expired or self.curr_time <= TIMERS[table.name]:
            return
        table.timer_expired = True
        act_desp = f"The {table.name} timer expires; {table.name} is now locked down, and players there can no longer leave by normal movement."
        timer_event = ("system", None, act_desp, self.curr_time, set([table.name] + list(table.personas.keys())))
        table.add_table_event(timer_event)
        self.sync_endgame_mode()

    def reset_urgent_table_movement_cooldowns(self, table):
        if table.timer_expired:
            return
        time_left = TIMERS[table.name] - self.curr_time
        urgency_seconds = (
            ENDGAME_TIMER_URGENCY_PHASES * ENDGAME_SECONDS_PER_PHASE
            if self.endgame_mode
            else NORMAL_TIMER_URGENCY_PHASES * self.sec_per_step
        )
        urgency_window = datetime.timedelta(seconds=urgency_seconds)
        if datetime.timedelta(0) <= time_left <= urgency_window:
            reset_names = []
            for persona in table.personas.values():
                if persona.scratch.movement_cooldown > 0:
                    persona.scratch.movement_cooldown = 0
                    reset_names.append(persona.scratch.name)
            if reset_names and debug:
                debug_log(
                    f"[TIMER-URGENCY] t={self.curr_time} | table={table.name} | "
                    f"time_left={time_left} | reset_movement_cooldowns={reset_names}"
                )

    def decrement_table_movement_cooldowns(self, table, reason, trigger_name=None):
        changed = []
        for persona in table.personas.values():
            if persona.scratch.movement_cooldown > 0:
                persona.scratch.movement_cooldown = max(
                    0,
                    persona.scratch.movement_cooldown - TABLE_ACTIVITY_MOVEMENT_COOLDOWN_DECREMENT,
                )
                changed.append((persona.scratch.name, persona.scratch.movement_cooldown))
        if changed and debug:
            trigger_text = f" | trigger={trigger_name}" if trigger_name else ""
            debug_log(
                f"[TABLE-COOLDOWN] t={self.curr_time} | table={table.name} | "
                f"reason={reason}{trigger_text} | decremented={changed}"
            )

    def run_movement_phase_for_table(self, table_name, table):
        self.expire_table_timer_if_needed(table)
        self.reset_urgent_table_movement_cooldowns(table)
        departed = False
        departure_count = 0
        persona_order = list(table.personas.keys())
        for persona_name in persona_order:
            if persona_name not in table.personas:
                continue
            persona = table.personas[persona_name]
            persona.update_knowledge(self.room)
            retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = persona.scratch.retrieved

            if persona.scratch.movement_cooldown > 0:
                continue
            if table.timer_expired:
                continue
            if self.is_locked_at_table(table, persona_name):
                continue
            next_loc = decide_on_leaving(persona, table, retrieved_all_tables)
            if next_loc == "stay":
                persona.scratch.movement_cooldown = MOVEMENT_STAY_COOLDOWN_STEPS
                continue
            persona.scratch.movement_cooldown = MOVEMENT_LEAVE_COOLDOWN_STEPS
            departures = persona.movement_departure_records(table, next_loc)
            if departures:
                table.bishop_trigger = True
            selected_departures = {}
            departure_order = []
            for departure in departures:
                departure_name = departure["name"]
                if departure_name not in selected_departures:
                    departure_order.append(departure_name)
                    selected_departures[departure_name] = departure
                elif departure.get("benefactor") is not None:
                    selected_departures[departure_name] = departure
            random.shuffle(departure_order)
            for departure_name in departure_order:
                if self.resolve_departure_record(table, table_name, selected_departures[departure_name]):
                    departed = True
                    departure_count += 1
                    if departure_count >= 2:
                        self.decrement_table_movement_cooldowns(
                            table,
                            "departure_pressure_after_second_departure",
                            trigger_name=departure_name,
                        )
        return departed

    def exceptional_departure_phase_seconds(self):
        return ENDGAME_SECONDS_PER_PHASE if self.endgame_mode else self.sec_per_step

    def table_has_exceptional_departure_window(self, table):
        if table.timer_expired:
            return False
        time_left = TIMERS[table.name] - self.curr_time
        phase_window = datetime.timedelta(seconds=self.exceptional_departure_phase_seconds())
        return datetime.timedelta(0) <= time_left < phase_window

    def run_exceptional_departures_if_needed(self, phase_name):
        if phase_name == "departure":
            return False
        timestamp_key = self.curr_time.total_seconds()
        if timestamp_key in self.exceptional_departure_timestamps:
            return False
        eligible_tables = [
            (table_name, table)
            for table_name, table in self.room.locations.items()
            if self.table_has_exceptional_departure_window(table)
        ]
        if not eligible_tables:
            return False
        self.exceptional_departure_timestamps.add(timestamp_key)
        if debug:
            debug_log(
                f"[EXCEPTIONAL-DEPARTURE-PHASE] t={self.curr_time} | phase={phase_name} | "
                f"eligible_tables={[table_name for table_name, _table in eligible_tables]} | "
                f"phase_window={self.exceptional_departure_phase_seconds()}s"
            )
        any_departures = False
        for table_name, table in eligible_tables:
            if debug:
                debug_log(
                    f"[EXCEPTIONAL-DEPARTURE-WINDOW] t={self.curr_time} | table={table.name} | "
                    f"phase={phase_name} | time_left={TIMERS[table.name] - self.curr_time} | "
                    f"phase_window={self.exceptional_departure_phase_seconds()}s"
                )
            any_departures = self.run_movement_phase_for_table(table_name, table) or any_departures
        if any_departures:
            self.save_checkpoint(f"exceptional_departure_before_{phase_name}")
        return any_departures

    def has_pending_arrivals(self):
        return bool(self.room.transit) or any(
            table.incoming_arrivals
            for table in self.room.locations.values()
        )

    def flush_pending_arrivals_before_game_end(self):
        if not self.has_pending_arrivals():
            return False
        if debug:
            debug_log(
                f"[FINAL-ARRIVAL-FLUSH] t={self.curr_time} | "
                f"transit={sorted(self.room.transit.keys())} | "
                f"incoming={{"
                + ", ".join(
                    f"{table_name}: {sorted(arrival[0] for arrival in table.incoming_arrivals)}"
                    for table_name, table in self.room.locations.items()
                    if table.incoming_arrivals
                )
                + "}"
            )
        any_arrival_activity = False
        for table_name, table in self.room.locations.items():
            any_arrival_activity = self.run_arrival_phase_for_table(table_name, table) or any_arrival_activity
        self.save_checkpoint("final_arrival_flush")
        return any_arrival_activity

    def run_bidding_phase_for_table(self, table_name, table):
        table_bidding_results = dict()
        for persona_name, persona in list(table.personas.items()):
            persona.update_knowledge(self.room)
            result = bid(persona, table)
            table_bidding_results[persona.name] = result

        final_table_results = [(name, points) for name, points in sorted(table_bidding_results.items(), key=lambda item: item[1], reverse=True)]
        if debug:
            debug_log(f"[BID-RESULT] t={self.curr_time} | table={table.name} | ranking={final_table_results}")

        if final_table_results:
            EPS = 1e-6
            top_score = final_table_results[0][1]
            if top_score < MIN_ACTION_BID_SCORE:
                if len(table.personas) <= 1:
                    if debug:
                        debug_log(
                            f"[LOW-BID-SOLO-NOOP] t={self.curr_time} | table={table.name} | "
                            f"top_score={top_score} | threshold={MIN_ACTION_BID_SCORE} | "
                            f"ranking={final_table_results}"
                        )
                    table.bishop_trigger = False
                    self.process_removal_targets(table, table_name)
                    return
                eligible_speakers = [
                    name for name, persona in table.personas.items()
                    if not ENABLE_SPEAKING_COOLDOWN or persona.scratch.speaking_cooldown <= 0
                ]
                if eligible_speakers:
                    winner = random.choice(eligible_speakers)
                    table.personas[winner].scratch.act_reasoning = (
                        "no action bid was strong enough, so they fill the table's silence with ordinary conversation"
                    )
                    if debug:
                        debug_log(
                            f"[LOW-BID-RANDOM-SPEAKER] t={self.curr_time} | table={table.name} | "
                            f"winner={winner} | eligible={eligible_speakers} | top_score={top_score} | "
                            f"threshold={MIN_ACTION_BID_SCORE} | ranking={final_table_results}"
                        )
                    table.personas[winner].speak(table)
                    table.bishop_trigger = False
                    self.process_removal_targets(table, table_name)
                    return
                if debug:
                    debug_log(
                        f"[LOW-BID-NOOP] t={self.curr_time} | table={table.name} | "
                        f"top_score={top_score} | threshold={MIN_ACTION_BID_SCORE} | "
                        f"ranking={final_table_results}"
                    )
                act_desp = "The table falls quiet; no action bid is strong enough for anyone to act."
                table.add_table_event(("system", None, act_desp, self.curr_time, set(table.personas.keys())))
            else:
                top_candidates = [name for name, pts in final_table_results if abs(pts - top_score) <= EPS]
                winner = random.choice(top_candidates)
                if debug:
                    debug_log(f"[ACTOR] t={self.curr_time} | table={table.name} | winner={winner} | top_score={top_score} | tied={top_candidates}")
                table.personas[winner].act(table)
                self.process_removal_targets(table, table_name, only_roles={"Spinster"})

        table.bishop_trigger = False
        self.process_removal_targets(table, table_name)

    def top_bidded_action(self, persona):
        action_tie_break_priority = {
            "retrieve": 5,
            "ability": 4,
            "nun-reveal": 3,
            "reveal": 2,
            "speak": 1,
        }
        if not persona.scratch.current_bidding_scores:
            return None, 0
        return max(
            persona.scratch.current_bidding_scores.items(),
            key=lambda item: (item[1], action_tie_break_priority.get(item[0], -2)),
        )

    def run_arrival_solo_action(self, table_name, table, arriving_persona, source_table, benefactor=None, base_context=None):
        if arriving_persona.scratch.name not in table.personas:
            return False
        arrival_context = self.arrival_speaking_context(
            arriving_persona,
            table.name,
            source_table,
            benefactor=benefactor,
            base_context=base_context,
        )
        arriving_persona.update_knowledge(self.room)
        total_score = bid(arriving_persona, table, action_context=arrival_context)
        top_action, top_score = self.top_bidded_action(arriving_persona)
        if debug:
            debug_log(
                f"[ARRIVAL-SOLO-BID] t={self.curr_time} | table={table.name} | "
                f"character={arriving_persona.scratch.name} | total_score={total_score} | "
                f"top_action={top_action} | top_score={top_score} | scores={arriving_persona.scratch.current_bidding_scores}"
            )

        if not top_action or top_score < MIN_ACTION_BID_SCORE:
            arriving_persona.scratch.act_reasoning = (
                "no immediate arrival action bid was strong enough to force the table's attention"
            )
            if debug:
                debug_log(
                    f"[ARRIVAL-SOLO-NOOP] t={self.curr_time} | table={table.name} | "
                    f"character={arriving_persona.scratch.name} | top_action={top_action} | "
                    f"top_score={top_score} | threshold={MIN_ACTION_BID_SCORE}"
                )
            arriving_persona.scratch.arrival_overheard_context = []
            return False

        if top_action == "speak":
            speak_reasoning = (arriving_persona.scratch.current_bidding_reasonings or {}).get("speak")
            if speak_reasoning:
                arrival_context += (
                    f" When you won the internal bid to speak on arrival, your reasoning was: {speak_reasoning}"
                )
            arriving_persona.speak(table, arrival_context, consume_cooldown=False)
            arriving_persona.scratch.arrival_overheard_context = []
            return True

        arriving_persona.act(table)
        self.process_removal_targets(table, table_name, only_roles={"Spinster"})
        self.process_removal_targets(table, table_name)
        arriving_persona.scratch.arrival_overheard_context = []
        return True

    def perceive_transit_screams_on_landfall(self, persona):
        transit_data = self.room.transit.get(persona.scratch.name)
        if not transit_data:
            return
        destination_table = transit_data.get("destination")
        cursor_map = transit_data.get("dialogue_cursors", {})
        perceived = []
        for other_table_name, other_table in self.room.locations.items():
            cursor = cursor_map.get(other_table_name, len(other_table.dialogue_history))
            audible_limit = self.room.audible_dialogue_limits.get(other_table_name, len(other_table.dialogue_history))
            audible_limit = min(audible_limit, len(other_table.dialogue_history))
            for utterance in other_table.dialogue_history[cursor:audible_limit]:
                s_chat, o_chat, volume, line, timestamp_chat, audience, keywords_chat = unpack_dialogue(utterance)
                audible_from_destination = (
                    other_table_name == destination_table
                    and volume in {"loud", "practically screaming"}
                )
                audible_from_elsewhere = volume == "practically screaming"
                if not (audible_from_destination or audible_from_elsewhere):
                    continue
                audience_text = ", ".join(sorted(audience)) if audience else "unknown"
                source_note = (
                    f"destination table {other_table_name}"
                    if other_table_name == destination_table
                    else f"the {other_table_name}"
                )
                description = (
                    f"{s_chat}: ({volume}, overheard while in transit from {source_note}; "
                    f"people physically present there: {audience_text}) {line}"
                )
                persona.scratch.arrival_overheard_context.append(
                    f"{s_chat} at {other_table_name} said {volume}: {line}"
                )
                poignancy = generate_poig_score(persona, "chat", description, s_chat, o_chat, keywords_chat)
                embedding = persona.a_mem.embeddings.get(description) or get_embedding(description)
                node = persona.a_mem.add_chat(
                    timestamp_chat,
                    s_chat,
                    o_chat,
                    "Transit",
                    description,
                    set(keywords_chat or []) | {s_chat, o_chat, other_table_name, "Transit"},
                    poignancy,
                    (description, embedding),
                )
                perceived.append(node)
                persona.scratch.importance_ele_n += 1
            persona.scratch.overheard_dialogue_cursors[other_table_name] = audible_limit
        if perceived:
            persona.scratch.recent_conversation[0:0] = [(persona.scratch.curr_time, perceived)]
            persona.scratch.recent_conversation = persona.scratch.recent_conversation[:persona.scratch.retention]
            debug_perception(persona, "Transit", 0, len(perceived))

    def run_arrival_phase_for_table(self, table_name, table):
        incoming_arrivals = list(table.incoming_arrivals)
        had_arrival_activity = False
        pending_innkeeper_declarations = []
        pending_queen_follow_locks = []

        def resolve_pending_queen_follow_locks():
            nonlocal had_arrival_activity
            still_pending = []
            for dragged_name, queen_name in pending_queen_follow_locks:
                if dragged_name not in table.personas:
                    continue
                if queen_name not in table.personas:
                    still_pending.append((dragged_name, queen_name))
                    continue
                if table.personas[queen_name].scratch.role != "Queen":
                    continue
                had_arrival_activity = True
                self.add_lock_if_allowed(table, queen_name, dragged_name, "Queen")
            pending_queen_follow_locks[:] = still_pending

        random.shuffle(incoming_arrivals)
        for candidate, benefactor, source_table in incoming_arrivals:
            if table.lockdown_targets:
                self.clear_table_locks(table, candidate, "enter")
            arriving_persona = self.personas[candidate]
            self.perceive_transit_screams_on_landfall(arriving_persona)
            self.sync_persona_to_table_history_end(arriving_persona, table_name)
            arriving_persona.scratch.speaking_cooldown = 0
            table.personas[candidate] = arriving_persona
            self.room.transit.pop(candidate, None)
            self.clear_thief_swap_locks(table, "arrival", trigger_name=None)
            act_desp = f"{candidate} arrives from {source_table}"
            arrival_event = (candidate, None, act_desp, self.personas[candidate].scratch.curr_time, set([candidate]))
            table.add_table_event(arrival_event)
            self.decrement_table_movement_cooldowns(
                table,
                "arrival_pressure",
                trigger_name=candidate,
            )

            if benefactor and benefactor in table.personas and table.personas[benefactor].scratch.role == "Queen":
                had_arrival_activity = True
                self.add_lock_if_allowed(table, benefactor, candidate, "Queen")
            elif benefactor and benefactor in self.personas and self.personas[benefactor].scratch.role == "Queen":
                pending_queen_follow_locks.append((candidate, benefactor))
            resolve_pending_queen_follow_locks()

            innkeeper_declaration = False
            innkeeper_declaration_reasoning = ""
            if (
                table.name == "Village"
                and arriving_persona.scratch.role == "Innkeeper"
                and arriving_persona.has_own_card("Innkeeper")
            ):
                if arriving_persona.scratch.ability_active and debug:
                    debug_log(
                        f"[INNKEEPER-DECLARE-PRECOMMIT] t={self.curr_time} | table={table.name} | "
                        f"character={candidate} | source_table={source_table} | "
                        "fresh_confirmation_required=True"
                    )
                innkeeper_declaration, innkeeper_declaration_reasoning = arriving_persona.decide_innkeeper_declaration(table, source_table)
            if (
                table.name == "Village"
                and arriving_persona.scratch.role == "Innkeeper"
                and arriving_persona.has_own_card("Innkeeper")
                and innkeeper_declaration
            ):
                arriving_persona.scratch.ability_active = True
                pending_innkeeper_declarations.append((candidate, source_table, benefactor))
            else:
                base_context = None
                if innkeeper_declaration_reasoning:
                    arriving_persona.scratch.ability_active = False
                    base_context = (
                        f"you are arriving at this table from {source_table}. "
                        "You have just explicitly decided NOT to reveal your Innkeeper card or declare the Village locked on this arrival. "
                        f"Your Innkeeper declaration reasoning was: {innkeeper_declaration_reasoning}. "
                        "Do not say or imply that you reveal as Innkeeper, declare as Innkeeper, shut the Village, or lock anyone here."
                    )
                had_arrival_activity = self.run_arrival_solo_action(
                    table_name,
                    table,
                    arriving_persona,
                    source_table,
                    benefactor=benefactor,
                    base_context=base_context,
                ) or had_arrival_activity

        for innkeeper_name, source_table, benefactor in pending_innkeeper_declarations:
            if innkeeper_name not in table.personas:
                continue
            innkeeper = table.personas[innkeeper_name]
            if innkeeper.scratch.role != "Innkeeper" or not innkeeper.has_own_card("Innkeeper"):
                debug_log(
                    f"[INNKEEPER-DECLARE-SKIP] t={self.curr_time} | table={table.name} | "
                    f"character={innkeeper_name} | role={innkeeper.scratch.role} | "
                    f"cards={sorted(innkeeper.scratch.cards_slot)}"
                )
                continue
            had_arrival_activity = True
            debug_log(
                f"[INNKEEPER-DECLARE-RESOLVE] t={self.curr_time} | table={table.name} | "
                f"character={innkeeper_name} | source_table={source_table}"
            )
            innkeeper_announcement = self.arrival_speaking_context(
                innkeeper,
                table.name,
                source_table,
                benefactor=benefactor,
                base_context="all arrivals for this phase have now seated; you are revealing your Innkeeper card to declare yourself as Innkeeper and lock down the Village",
            )
            innkeeper.speak(table, special_circumstance=innkeeper_announcement, consume_cooldown=False)

            ability_attempt_context = (
                f"{innkeeper.scratch.name} reveals {innkeeper.role_card_text(role='Innkeeper')} and attempts to declare "
                "themself as Innkeeper to lock down everyone at the Village."
            )
            table.add_table_event((innkeeper.scratch.name, None, ability_attempt_context, self.curr_time, set([innkeeper.scratch.name])))
            if innkeeper.resolve_baron_reaction(table, innkeeper.scratch.name, ability_attempt_context, block_ability=True):
                continue

            for other_player_name, other_player in list(table.personas.items()):
                if other_player_name != innkeeper.scratch.name:
                    self.add_lock_if_allowed(table, innkeeper.scratch.name, other_player_name, innkeeper.scratch.role)

            act_desp = f"{innkeeper.scratch.name} reveals {innkeeper.role_card_text(role='Innkeeper')}, declares themself as Innkeeper, and locks down everyone at the Village"
            lockdown_event = (innkeeper.scratch.name, None, act_desp, self.curr_time, set([innkeeper.scratch.name] + innkeeper.scratch.ability_objects))
            table.add_table_event(lockdown_event)

        table.incoming_arrivals = set()
        return had_arrival_activity

    def run_spinster_endgame_guess_round(self):
        for table in self.room.locations.values():
            for persona in list(table.personas.values()):
                if persona.scratch.role != "Spinster":
                    continue
                required_targets = {name for name in table.personas if name != persona.scratch.name}
                existing_guesses = set((persona.scratch.endgame_role_guesses or {}).keys())
                if required_targets and required_targets.issubset(existing_guesses):
                    continue
                persona.make_spinster_endgame_guesses(table)
        self.save_checkpoint("spinster_endgame_guess_complete")

    def pre_spinster_results(self):
        final_tables = final_table_map(self.room)
        players = locations_to_player(final_tables)
        results = {}
        for name, player in players.items():
            if player.scratch.role == "Spinster":
                continue
            results[name] = evaluate_base_win(name, player, final_tables)

        adjusted_results = dict(results)
        for _ in range(max(1, len(players))):
            changed = False
            next_results = dict(results)
            for name, player in players.items():
                if player.scratch.role in {"Nun", "Thief"}:
                    next_results[name] = evaluate_base_win(name, player, final_tables, adjusted_results)
            if next_results != results:
                changed = True
            results = next_results
            adjusted_results = dict(results)
            if not changed:
                break
        return results

    def append_results_to_dialogue_log(self, title, results, pending_roles=None, flipped_by_spinster=None):
        log_paths = [path for path in [self.dialogue_log_path, self.clean_dialogue_log_path] if path]
        if not log_paths:
            return
        pending_roles = set(pending_roles or [])
        flipped_by_spinster = flipped_by_spinster or []
        for log_path in log_paths:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as outfile:
                outfile.write(f"\n[{self.curr_time}] {title}\n")
                for name, persona in sorted(self.personas.items()):
                    if persona.scratch.role in pending_roles:
                        outcome = "pending"
                    else:
                        outcome = "wins" if results.get(name, False) else "loses"
                    outfile.write(f"- {name} ({persona.scratch.role}): {outcome}\n")
                if flipped_by_spinster:
                    outfile.write(f"Spinster reversal applied to: {', '.join(flipped_by_spinster)}\n")
                outfile.write("\n")

    def sync_persona_to_table_history_end(self, persona, table_name):
        table = self.room.locations[table_name]
        persona.scratch.dialogue_cursors[table_name] = len(table.dialogue_history)
        persona.scratch.event_cursors[table_name] = len(table.event_history)

    def session_state_path(self):
        return os.path.join(save_file, SESSION_STATE_FILE)

    def session_metadata_path(self):
        return os.path.join(save_file, SESSION_METADATA_FILE)

    def is_persona_dir(self, dirname):
        if dirname in NON_PERSONA_SESSION_DIRS:
            return False
        persona_path = os.path.join(save_file, dirname)
        if not os.path.isdir(persona_path):
            return False
        return (
            os.path.isfile(os.path.join(persona_path, "scratch.json"))
            or os.path.isdir(os.path.join(persona_path, "associative_memory"))
        )

    def has_existing_session_data(self):
        if not os.path.isdir(save_file):
            return False
        if os.path.isfile(self.session_state_path()):
            return True
        return any(self.is_persona_dir(filename) for filename in os.listdir(save_file))

    def archive_existing_session(self):
        if not os.path.exists(save_file):
            return None
        timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
        archive_path = f"{save_file}_archived_{timestamp}"
        counter = 1
        while os.path.exists(archive_path):
            archive_path = f"{save_file}_archived_{timestamp}_{counter}"
            counter += 1
        shutil.move(save_file, archive_path)
        print(f"Archived previous session to: {archive_path}")
        return archive_path

    def choose_session_mode(self):
        if not self.has_existing_session_data():
            os.makedirs(save_file, exist_ok=True)
            return "new"
        has_checkpoint = os.path.isfile(self.session_state_path())
        checkpoint_note = "saved game state" if has_checkpoint else "saved character memories only"
        while True:
            choice = input(
                f"Existing session data found in {save_file} ({checkpoint_note}). "
                "Choose one:\n"
                "- 'continue' to load the saved run\n"
                "- 'new' to archive everything and generate a fully new cast\n"
                "- 'same roles' to reuse these characters and roles, but wipe game state/memory/logs\n"
                "- 'reroll roles' to reuse these characters with reassigned roles, wiping game state/memory/logs\n"
                "- 'exact setup' to reuse these characters, roles, and starting tables, wiping game state/memory/logs\n"
            ).strip().lower()
            if choice in CONTINUE_SESSION_ALIASES:
                return "resume" if has_checkpoint else "legacy"
            if choice in NEW_SESSION_ALIASES:
                self.archive_existing_session()
                os.makedirs(save_file, exist_ok=True)
                return "new"
            if choice in REUSE_CAST_SAME_ROLES_ALIASES:
                return "reuse_same_roles"
            if choice in REUSE_CAST_REROLL_ROLES_ALIASES:
                return "reuse_reroll_roles"
            if choice in REUSE_EXACT_SETUP_ALIASES:
                return "reuse_exact_setup"
            print("Please type 'continue', 'new', 'same roles', 'reroll roles', or 'exact setup'.")

    def metadata_payload(self):
        return {
            "session_id": self.session_id,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "dialogue_log_path": str(self.dialogue_log_path) if self.dialogue_log_path else None,
            "clean_dialogue_log_path": str(self.clean_dialogue_log_path) if self.clean_dialogue_log_path else None,
            "debug_log_path": str(self.debug_log_path) if self.debug_log_path else None,
            "game_mode": self.game_mode,
            "exact_setup_movement_cooldowns": self.exact_setup_movement_cooldowns,
            "exact_setup_starting_tables": self.exact_setup_starting_tables,
        }

    def save_session_metadata(self):
        os.makedirs(save_file, exist_ok=True)
        metadata_path = self.session_metadata_path()
        existing = {}
        if os.path.isfile(metadata_path):
            with open(metadata_path) as infile:
                existing = json.load(infile)
        payload = {
            "created_at": existing.get("created_at", datetime.datetime.now().isoformat(timespec="seconds")),
            **self.metadata_payload(),
        }
        with open(metadata_path, "w") as outfile:
            json.dump(payload, outfile, indent=2)

    def load_session_metadata(self):
        metadata_path = self.session_metadata_path()
        if not os.path.isfile(metadata_path):
            self.session_id = uuid.uuid4().hex[:12]
            return {}
        with open(metadata_path) as infile:
            metadata = json.load(infile)
        self.session_id = metadata.get("session_id") or uuid.uuid4().hex[:12]
        self.configure_game_mode(metadata.get("game_mode", self.game_mode))
        self.dialogue_log_path = metadata.get("dialogue_log_path")
        self.clean_dialogue_log_path = metadata.get("clean_dialogue_log_path")
        self.debug_log_path = metadata.get("debug_log_path")
        self.exact_setup_movement_cooldowns = {
            name: int(value)
            for name, value in metadata.get("exact_setup_movement_cooldowns", {}).items()
            if isinstance(value, int) or str(value).isdigit()
        }
        self.exact_setup_starting_tables = {
            name: table
            for name, table in metadata.get("exact_setup_starting_tables", {}).items()
            if table in TIMERS
        }
        return metadata

    def serialize_record(self, record):
        values = []
        for value in record:
            if isinstance(value, datetime.timedelta):
                values.append(value.total_seconds())
            elif isinstance(value, set):
                values.append(sorted(value))
            else:
                values.append(value)
        return values

    def deserialize_event_record(self, record):
        if len(record) == 6:
            subject, obj, description, timestamp, keywords, audience = record
            return (subject, obj, description, datetime.timedelta(seconds=timestamp), set(keywords), set(audience))
        subject, obj, description, timestamp, keywords = record
        return (subject, obj, description, datetime.timedelta(seconds=timestamp), set(keywords))

    def deserialize_dialogue_record(self, record):
        if len(record) == 6:
            speaker, target, volume, line, timestamp, keywords = record
            audience = []
        else:
            speaker, target, volume, line, timestamp, audience, keywords = record
        return (speaker, target, volume, line, datetime.timedelta(seconds=timestamp), set(audience), set(keywords))

    def serialize_table(self, table):
        return {
            "personas": list(table.personas.keys()),
            "current_lines": [self.serialize_record(record) for record in table.current_lines],
            "dialogue_history": [self.serialize_record(record) for record in table.dialogue_history],
            "current_events": [self.serialize_record(record) for record in table.current_events],
            "event_history": [self.serialize_record(record) for record in table.event_history],
            "removal_targets": [list(target) for target in table.removal_targets],
            "lockdown_targets": [list(target) for target in table.lockdown_targets],
            "lockdown_witnesses": [
                {"lock": list(lock), "witnesses": sorted(witnesses)}
                for lock, witnesses in getattr(table, "lockdown_witnesses", {}).items()
            ],
            "thief_swap_locks": [sorted(list(pair)) for pair in getattr(table, "thief_swap_locks", set())],
            "incoming_arrivals": [list(arrival) for arrival in table.incoming_arrivals],
            "bishop_trigger": table.bishop_trigger,
            "spinster_marked": list(table.spinster_marked) if table.spinster_marked else None,
            "timer_expired": table.timer_expired,
        }

    def serialize_transit(self):
        return {
            name: {
                **data,
                "since": data["since"].total_seconds() if isinstance(data.get("since"), datetime.timedelta) else data.get("since", 0),
            }
            for name, data in self.room.transit.items()
        }

    def restore_table(self, table_name, table_state):
        table = self.room.locations[table_name]
        table.personas = {
            persona_name: self.personas[persona_name]
            for persona_name in table_state.get("personas", [])
            if persona_name in self.personas
        }
        table.current_lines = [self.deserialize_dialogue_record(record) for record in table_state.get("current_lines", [])]
        table.dialogue_history = [self.deserialize_dialogue_record(record) for record in table_state.get("dialogue_history", [])]
        table.current_events = [self.deserialize_event_record(record) for record in table_state.get("current_events", [])]
        table.event_history = [self.deserialize_event_record(record) for record in table_state.get("event_history", [])]
        table.removal_targets = {tuple(target) for target in table_state.get("removal_targets", [])}
        table.lockdown_targets = {tuple(target) for target in table_state.get("lockdown_targets", [])}
        table.lockdown_witnesses = {
            tuple(entry.get("lock", [])): set(entry.get("witnesses", []))
            for entry in table_state.get("lockdown_witnesses", [])
            if isinstance(entry, dict) and len(entry.get("lock", [])) == 3
        }
        table.thief_swap_locks = {
            frozenset(pair)
            for pair in table_state.get("thief_swap_locks", [])
            if isinstance(pair, list) and len(pair) == 2
        }
        if len(table.personas) != 2:
            table.thief_swap_locks = set()
        table.incoming_arrivals = {tuple(arrival) for arrival in table_state.get("incoming_arrivals", [])}
        table.bishop_trigger = table_state.get("bishop_trigger", False)
        spinster_marked = table_state.get("spinster_marked")
        table.spinster_marked = tuple(spinster_marked) if spinster_marked else None
        table.timer_expired = table_state.get("timer_expired", False)

    def restore_transit(self, transit_state):
        self.room.transit = {}
        for name, data in (transit_state or {}).items():
            self.room.transit[name] = {
                "source": data.get("source"),
                "destination": data.get("destination"),
                "benefactor": data.get("benefactor"),
                "since": datetime.timedelta(seconds=data.get("since", 0)),
                "dialogue_cursors": data.get("dialogue_cursors", {}),
            }

    def save_checkpoint(self, reason):
        def write_state_file(path, payload):
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w") as outfile:
                json.dump(payload, outfile, indent=2)
            os.replace(tmp_path, path)

        def save_phase_snapshot(snapshot_dir, payload):
            tmp_dir = f"{snapshot_dir}.tmp"
            if os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
            os.makedirs(tmp_dir, exist_ok=True)
            write_state_file(os.path.join(tmp_dir, SESSION_STATE_FILE), payload)
            for snapshot_persona in self.personas.values():
                snapshot_persona.save(os.path.join(tmp_dir, snapshot_persona.scratch.name))
            if os.path.isdir(snapshot_dir):
                shutil.rmtree(snapshot_dir)
            os.replace(tmp_dir, snapshot_dir)

        os.makedirs(save_file, exist_ok=True)
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        for persona in self.personas.values():
            persona.save(os.path.join(save_file, persona.scratch.name))
        state = {
            "session_id": self.session_id,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "save_reason": reason,
            "game_mode": self.game_mode,
            "curr_time": self.curr_time.total_seconds(),
            "sec_per_step": self.sec_per_step,
            "next_phase": self.next_phase,
            "endgame_mode": self.endgame_mode,
            "exceptional_departure_timestamps": sorted(self.exceptional_departure_timestamps),
            "tables": {
                table_name: self.serialize_table(table)
                for table_name, table in self.room.locations.items()
            },
            "transit": self.serialize_transit(),
            "audible_dialogue_limits": self.room.audible_dialogue_limits,
        }
        state_path = self.session_state_path()
        write_state_file(state_path, state)
        phase_checkpoint_dir = PHASE_CHECKPOINT_DIRS.get(reason)
        if phase_checkpoint_dir:
            snapshot_root = os.path.join(save_file, PHASE_SNAPSHOT_ROOT)
            os.makedirs(snapshot_root, exist_ok=True)
            save_phase_snapshot(os.path.join(snapshot_root, phase_checkpoint_dir), state)
        self.save_session_metadata()
        print(f"Saved game checkpoint ({reason}) to: {state_path}")

    def save_personas_only(self, reason):
        os.makedirs(save_file, exist_ok=True)
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        for persona in self.personas.values():
            persona.save(os.path.join(save_file, persona.scratch.name))
        self.save_session_metadata()
        print(f"Saved character memories ({reason}) to: {save_file}")

    def load_checkpoint(self):
        with open(self.session_state_path()) as infile:
            state = json.load(infile)
        if state.get("game_mode") and state.get("game_mode") != self.game_mode:
            self.configure_game_mode(state.get("game_mode"))
        self.session_id = state.get("session_id") or self.session_id or uuid.uuid4().hex[:12]
        self.curr_time = datetime.timedelta(seconds=state.get("curr_time", 0))
        self.sec_per_step = state.get("sec_per_step", self.sec_per_step)
        self.next_phase = state.get("next_phase", "departure")
        self.endgame_mode = state.get("endgame_mode", False)
        self.room.endgame_mode = self.endgame_mode
        self.exceptional_departure_timestamps = {
            float(timestamp)
            for timestamp in state.get("exceptional_departure_timestamps", [])
        }
        for table_name, table_state in state.get("tables", {}).items():
            if table_name in self.room.locations:
                self.restore_table(table_name, table_state)
        self.restore_transit(state.get("transit", {}))
        restored_limits = state.get("audible_dialogue_limits")
        if restored_limits is None:
            self.refresh_audible_dialogue_limits()
        else:
            self.room.audible_dialogue_limits = {
                table_name: int(restored_limits.get(table_name, len(table.dialogue_history)))
                for table_name, table in self.room.locations.items()
            }
        for persona in self.personas.values():
            persona.scratch.curr_time = self.curr_time
            persona.rebuild_recent_conversation_from_memory()
        self.sync_endgame_mode()
        print(f"Loaded checkpoint from: {self.session_state_path()}")

    def should_start_game_after_generation(self):
        while True:
            choice = input("Characters and their starting relationships are generated. Type 'start' to begin this game now, or 'quit' to save the prepared cast and stop here:\n").strip().lower()
            if choice in {"start", "s", "yes", "y", "continue", "c"}:
                return True
            if choice in {"quit", "q", "no", "n", "stop"}:
                return False
            print("Please type 'start' or 'quit'.")

    def choose_game_mode_for_new_cast(self):
        env_mode = os.getenv("THREE_ESTATES_GAME_MODE") or read_local_env_value("THREE_ESTATES_GAME_MODE")
        if env_mode in {"10", "16"}:
            self.configure_game_mode(env_mode)
            return
        while True:
            choice = input("Choose game size/ruleset: type '10' for base mode or '16' for expanded mode:\n").strip()
            if choice in {"10", "16"}:
                self.configure_game_mode(choice)
                return
            print("Please type '10' or '16'.")

    def choose_character_generation_mode(self):
        env_mode = (
            os.getenv("THREE_ESTATES_CHARACTER_GENERATION_MODE")
            or read_local_env_value("THREE_ESTATES_CHARACTER_GENERATION_MODE")
            or ""
        ).strip().lower()
        if env_mode in CHARACTER_GENERATION_IMMERSION_ALIASES:
            return "immersion"
        if env_mode in CHARACTER_GENERATION_NORMAL_ALIASES:
            return "normal"
        while True:
            choice = input(
                "Choose character generation role assignment: type 'normal' to generate one character per shuffled role, "
                "or 'immersion' to generate the cast first and assign roles by temperament:\n"
            ).strip().lower()
            if choice in CHARACTER_GENERATION_IMMERSION_ALIASES:
                return "immersion"
            if choice in CHARACTER_GENERATION_NORMAL_ALIASES:
                return "normal"
            print("Please type 'normal' or 'immersion'.")

    def role_pool_text(self, roles):
        counts = Counter(roles)
        return "\n".join(f"- {role}: {counts[role]}" for role in ROLE_DICT if counts.get(role, 0))

    def character_profiles_text(self, character_profiles):
        lines = []
        for character in character_profiles:
            name = character.get("name", "Unnamed")
            gender = character.get("gender", "unknown")
            age = character.get("age", "unknown")
            innate = character.get("innate", "")
            lines.append(f"- {name} | gender={gender} | age={age} | temperament/background={innate}")
        return "\n".join(lines)

    def validate_immersion_role_assignments(self, character_profiles, roles, raw_assignment):
        if isinstance(raw_assignment, dict) and isinstance(raw_assignment.get("assignments"), dict):
            raw_assignment = raw_assignment["assignments"]
        if not isinstance(raw_assignment, dict):
            raw_assignment = {}

        remaining_counts = Counter(roles)
        assignments = {}
        for character in character_profiles:
            name = character["name"]
            requested_role = raw_assignment.get(name)
            if remaining_counts.get(requested_role, 0) > 0:
                assignments[name] = requested_role
                remaining_counts[requested_role] -= 1

        remaining_roles = []
        for role, count in remaining_counts.items():
            remaining_roles.extend([role] * count)
        random.shuffle(remaining_roles)
        for character in character_profiles:
            name = character["name"]
            if name not in assignments:
                assignments[name] = remaining_roles.pop()
        return assignments

    def assign_roles_by_immersion(self, character_group_context, character_profiles, roles):
        raw_assignment = prompt_dict(
            run_gpt_prompt_assign_immersion_roles(
                character_group_context,
                self.character_profiles_text(character_profiles),
                self.role_pool_text(roles),
                build_prefix(self.game_mode),
            ),
            {},
        )
        return self.validate_immersion_role_assignments(character_profiles, roles, raw_assignment)

    def generate_immersion_cast(self, roles, character_group_context):
        character_profiles = []
        existing_character_names = []
        for index in range(len(roles)):
            existing_character_choices = ""
            if existing_character_names:
                existing_character_choices = ",".join(existing_character_names)
            character_dict = self.generate_character_profile(
                character_group_context,
                existing_character_choices,
                f"Character {index + 1}",
            )
            character_profiles.append(character_dict)
            existing_character_names.append(character_dict["name"])

        role_assignments = self.assign_roles_by_immersion(character_group_context, character_profiles, roles)
        for character_dict in character_profiles:
            role = role_assignments[character_dict["name"]]
            self.create_persona_from_character_profile(character_dict, role, character_group_context)
            if debug:
                debug_log(
                    f"[IMMERSION-ROLE] character={character_dict['name']} | role={role} | "
                    f"innate={character_dict.get('innate', '')}"
                )
        return role_assignments

    def add_lock_if_allowed(self, table, benefactor, target_name, role):
        target = table.personas[target_name]
        if has_nun_protection(target):
            target.show_nun_protection(
                table,
                benefactor,
                role,
                target_name,
                "lock you at this table"
            )
            return False
        if target.scratch.role == "Farmer":
            special_circumstance = f"the {role} {benefactor} is trying to lock you at this table and you have to reveal you're the Farmer and immune"
            poss = "her" if target.scratch.gender == "female" else "his"
            act_desp = f"{target_name} reveals {poss} Farmer card"
            reveal_event = (target_name, None, act_desp, self.curr_time, set([target_name]))
            table.add_table_event(reveal_event)
            target.speak(table, special_circumstance)
            return False
        table.lockdown_targets.add((benefactor, target_name, role))
        table.lockdown_witnesses[(benefactor, target_name, role)] = set(table.personas.keys())
        self.refresh_lock_holder_state(benefactor, role)
        return True
    
    def generate_relationship(self, character_group_context, p1, p2):
        relationship = prompt_text(
            run_gpt_prompt_generate_relationship(character_group_context, p1, p2),
            f"{p1.scratch.name} and {p2.scratch.name} know each other only casually through the game group."
        )
        #print(f"Generating relationship between {p1.role} and {p2.role}")
        p1.scratch.relationships[p2.scratch.name] = relationship
        p2.scratch.relationships[p1.scratch.name] = relationship

    def relationship_pair_count_bounds(self):
        cast_size = len(self.personas)
        if cast_size <= 1:
            return 0, 0
        max_possible = cast_size * (cast_size - 1) // 2
        if cast_size >= 16:
            return min(5, max_possible), min(10, max_possible)
        return min(3, max_possible), min(6, max_possible)

    def cast_information_for_relationship_selection(self):
        lines = []
        for persona in sorted(self.personas.values(), key=lambda p: p.scratch.name):
            lines.append(
                f"- {persona.scratch.name}: "
                f"age={persona.scratch.age}; gender={persona.scratch.gender}; "
                f"profile={persona.scratch.innate}"
            )
        return "\n".join(lines)

    def fallback_relationship_pairs(self, min_pairs, max_pairs):
        all_pairs = list(itertools.combinations(self.personas.values(), 2))
        if not all_pairs:
            return []
        target_count = random.randint(min_pairs, max_pairs) if max_pairs >= min_pairs else min_pairs
        return random.sample(all_pairs, min(target_count, len(all_pairs)))

    def select_relationship_pairs(self, character_group_context):
        min_pairs, max_pairs = self.relationship_pair_count_bounds()
        if max_pairs <= 0:
            return []
        personas_by_name = {persona.scratch.name: persona for persona in self.personas.values()}
        fallback = self.fallback_relationship_pairs(min_pairs, max_pairs)
        selection = prompt_dict(
            run_gpt_prompt_select_relationship_pairs(
                character_group_context,
                self.cast_information_for_relationship_selection(),
                min_pairs,
                max_pairs,
            ),
            {"pairs": []},
        )
        selected = []
        seen = set()
        for raw_pair in selection.get("pairs", []):
            if not isinstance(raw_pair, dict):
                continue
            name_1 = raw_pair.get("character_1")
            name_2 = raw_pair.get("character_2")
            if name_1 not in personas_by_name or name_2 not in personas_by_name or name_1 == name_2:
                continue
            key = tuple(sorted([name_1, name_2]))
            if key in seen:
                continue
            seen.add(key)
            selected.append((personas_by_name[name_1], personas_by_name[name_2]))
            if len(selected) >= max_pairs:
                break
        if len(selected) < min_pairs:
            for p1, p2 in fallback:
                key = tuple(sorted([p1.scratch.name, p2.scratch.name]))
                if key in seen:
                    continue
                seen.add(key)
                selected.append((p1, p2))
                if len(selected) >= min_pairs:
                    break
        return selected

    def generate_selected_relationships(self, character_group_context):
        selected_pairs = self.select_relationship_pairs(character_group_context)
        if debug:
            debug_log(
                f"[RELATIONSHIP-PAIRS] selected="
                f"{[(p1.scratch.name, p2.scratch.name) for p1, p2 in selected_pairs]}"
            )
        for p1, p2 in selected_pairs:
            self.generate_relationship(character_group_context, p1, p2)

    def generate_character_profile(self, character_group_context, existing_character_choices, fallback_name):
        return prompt_dict(
            run_gpt_prompt_generate_character(character_group_context, existing_character_choices),
            {
                "name": fallback_name,
                "gender": "unknown",
                "age": "30",
                "innate": "is a cautious contestant generated as a fallback for the simulation.",
            }
        )

    def create_persona_from_character_profile(self, character_dict, role, character_group_context):
        persona_path = os.path.join(save_file, character_dict['name'])
        new_persona = Persona(character_dict['name'], self.room, role, folder_mem_saved=persona_path)
        new_persona.scratch.name = character_dict['name']
        new_persona.ensure_own_card_identity()
        new_persona.scratch.gender = character_dict['gender']
        new_persona.scratch.age = bounded_int(character_dict['age'], 30, minimum=0)
        new_persona.scratch.innate = character_dict['innate']
        new_persona.scratch.group_context = character_group_context
        self.personas[new_persona.scratch.name] = new_persona
        new_persona.save(persona_path)
        return new_persona

    def generate_character(self, role, character_group_context, existing_character_choices, role_label=None):
        role_label = role_label or role
        fallback_name = f"{role_label} Player"
        character_dict = self.generate_character_profile(
            character_group_context,
            existing_character_choices,
            fallback_name,
        )
        return self.create_persona_from_character_profile(character_dict, role, character_group_context)

    def session_context_path(self):
        return os.path.join(save_file, SESSION_CONTEXT_FILE)

    def save_character_context(
        self,
        character_group_context,
        character_generation_mode="normal",
        relationship_generation_complete=False,
    ):
        os.makedirs(save_file, exist_ok=True)
        context_payload = {
            "character_group_context": character_group_context,
            "game_mode": self.game_mode,
            "character_generation_mode": character_generation_mode,
            "relationship_generation_complete": bool(relationship_generation_complete),
        }
        with open(self.session_context_path(), "w") as outfile:
            json.dump(context_payload, outfile, indent=2)

    def mark_relationship_generation_complete(self):
        context_payload = self.load_character_context_payload()
        self.save_character_context(
            context_payload.get("character_group_context", self.load_character_context()),
            context_payload.get("character_generation_mode", "normal"),
            relationship_generation_complete=True,
        )

    def load_character_context(self):
        context_path = self.session_context_path()
        if os.path.isfile(context_path):
            with open(context_path) as infile:
                context_payload = json.load(infile)
            return context_payload.get("character_group_context", "")

        for persona in self.personas.values():
            if persona.scratch.group_context:
                return persona.scratch.group_context

        return ""

    def load_character_context_payload(self):
        context_path = self.session_context_path()
        if os.path.isfile(context_path):
            with open(context_path) as infile:
                return json.load(infile)
        return {}

    def collect_cast_from_existing_session(self):
        cast = []
        for filename in os.listdir(save_file):
            if not self.is_persona_dir(filename):
                continue
            scratch_path = os.path.join(save_file, filename, "scratch.json")
            if not os.path.isfile(scratch_path):
                continue
            with open(scratch_path) as infile:
                scratch = json.load(infile)
            name = scratch.get("name") or filename
            cast.append({
                "name": name,
                "gender": scratch.get("gender"),
                "age": scratch.get("age"),
                "innate": scratch.get("innate"),
                "role": scratch.get("role"),
                "starting_table": self.exact_setup_starting_tables.get(name) or scratch.get("curr_loc"),
                "group_context": scratch.get("group_context"),
            })
        return cast

    def rebuild_clean_cast(self, cast, roles, reroll_roles=False, preserve_tables=False):
        roles = list(roles)
        if len(cast) > len(roles):
            raise ValueError(f"More saved characters than available roles in {save_file}")
        if reroll_roles:
            previous_roles = {character["name"]: character.get("role") for character in cast}
            role_assignments = None
            for _attempt in range(100):
                role_pool = random.sample(list(roles), len(cast))
                candidate = {
                    character["name"]: role
                    for character, role in zip(cast, role_pool)
                }
                if all(candidate[name] != previous_roles.get(name) for name in candidate):
                    role_assignments = candidate
                    break
            if role_assignments is None:
                role_pool = random.sample(list(roles), len(cast))
                role_assignments = {
                    character["name"]: role
                    for character, role in zip(cast, role_pool)
                }
        else:
            remaining_counts = Counter(roles)
            role_assignments = {}
            fallback_roles = list(roles)
            random.shuffle(fallback_roles)
            for character in cast:
                role = character.get("role")
                if remaining_counts.get(role, 0) <= 0:
                    while fallback_roles and remaining_counts.get(fallback_roles[-1], 0) <= 0:
                        fallback_roles.pop()
                    if not fallback_roles:
                        raise ValueError(f"Could not assign a role to {character['name']}")
                    role = fallback_roles.pop()
                remaining_counts[role] -= 1
                role_assignments[character["name"]] = role

        self.personas = {}
        self.room = RoomGraph(self.personas)
        self.personas_loc = {}
        for character in cast:
            role = role_assignments[character["name"]]
            persona = Persona(character["name"], self.room, role)
            persona.scratch.name = character["name"]
            persona.ensure_own_card_identity()
            persona.scratch.gender = character.get("gender")
            persona.scratch.age = character.get("age")
            persona.scratch.innate = character.get("innate")
            persona.scratch.group_context = character.get("group_context")
            if preserve_tables and character.get("starting_table") in TIMERS:
                persona.scratch.curr_loc = character.get("starting_table")
            self.personas[persona.scratch.name] = persona
            persona.save(os.path.join(save_file, persona.scratch.name))

    def load_personas_from_session(self, roles):
        random_pool = list(roles)
        random.shuffle(random_pool)
        for filename in os.listdir(save_file):
            if not self.is_persona_dir(filename):
                continue
            persona_path = os.path.join(save_file, filename)
            if not random_pool:
                raise ValueError(f"More persona directories than available roles in {save_file}")
            role = random_pool.pop()
            new_persona = Persona(filename, self.room, role, folder_mem_saved=persona_path)
            new_persona.ensure_own_card_identity()
            self.personas[new_persona.scratch.name] = new_persona

    def initialize_dialogue_log(self, resume_existing=False):
        log_dir = os.path.join(save_file, "dialogue_logs")
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        if not resume_existing or not self.dialogue_log_path:
            timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
            self.dialogue_log_path = os.path.join(log_dir, f"dialogue_{self.session_id}_{timestamp}.log")
        if not resume_existing or not self.clean_dialogue_log_path:
            timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
            self.clean_dialogue_log_path = os.path.join(log_dir, f"dialogue_clean_{self.session_id}_{timestamp}.log")
        if not resume_existing or not self.debug_log_path:
            timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
            self.debug_log_path = os.path.join(log_dir, f"debug_{self.session_id}_{timestamp}.log")
        set_dialogue_log_path(self.dialogue_log_path, log_dir=log_dir)
        set_clean_dialogue_log_path(self.clean_dialogue_log_path)
        set_debug_log_path(self.debug_log_path)
        self.save_session_metadata()
        print(f"dialogue log: {self.dialogue_log_path}")
        print(f"clean dialogue log: {self.clean_dialogue_log_path}")
        print(f"debug log: {self.debug_log_path}")

    def epilogue_path(self):
        log_dir = os.path.join(save_file, "dialogue_logs")
        os.makedirs(log_dir, exist_ok=True)
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        return os.path.join(log_dir, f"epilogue_{self.session_id}.txt")

    def recent_log_excerpt(self, max_lines=None):
        log_path = self.clean_dialogue_log_path or self.dialogue_log_path
        if not log_path or not os.path.isfile(log_path):
            return "No dialogue log excerpt is available."
        with open(log_path) as infile:
            lines = infile.readlines()
        if max_lines is None:
            max_lines = len(lines)
        return "".join(lines[-max_lines:]).strip()

    def build_epilogue_context(self, results):
        table_lines = []
        for table_name, table in self.room.locations.items():
            table_lines.append(f"{table_name}:")
            for name, persona in sorted(table.personas.items()):
                outcome = "won" if results["final_results"].get(name) else "lost"
                base_outcome = "won" if results["base_results"].get(name) else "lost"
                held_cards = ", ".join(sorted(persona.scratch.cards_slot)) or "no cards"
                guesses = ""
                if persona.scratch.role == "Spinster":
                    guesses = f"; Spinster guesses: {persona.scratch.endgame_role_guesses}"
                table_lines.append(
                    f"- {name}: role={persona.scratch.role}, family={role_family(persona.scratch.role)}, "
                    f"final_result={outcome}, base_result={base_outcome}, held_cards={held_cards}{guesses}"
                )
        character_lines = []
        for name, persona in sorted(self.personas.items()):
            last_move_thought = persona.scratch.current_movement_reasoning or "No recent move/stay reasoning recorded."
            last_move_destination = persona.scratch.current_movement_destination or persona.scratch.curr_loc
            last_act_reasoning = persona.scratch.act_reasoning or "No recent action-bid reasoning recorded."
            character_lines.append(
                f"{name}: {persona.scratch.get_str_iss()}\n"
                f"Last recorded move/stay intent: {last_move_thought} "
                f"(destination/status: {last_move_destination})\n"
                f"Last recorded strongest action-bid impulse: {last_act_reasoning}"
            )
        flipped = ", ".join(results["flipped_by_spinster"]) if results["flipped_by_spinster"] else "none"
        return (
            f"Session id: {self.session_id}\n"
            f"Final time: {self.curr_time}\n"
            f"Spinster reversal flipped: {flipped}\n\n"
            "Final table state, roles, cards, and results:\n"
            + "\n".join(table_lines)
            + "\n\nCharacter/personality notes:\n"
            + "\n".join(character_lines)
            + "\n\nRecent dialogue and event log excerpt:\n"
            + self.recent_log_excerpt(max_lines=None)
        )

    def generate_and_save_vn_epilogue(self, results):
        epilogue_path = self.epilogue_path()
        if os.path.isfile(epilogue_path):
            with open(epilogue_path) as infile:
                epilogue = infile.read().strip()
            print("\nPost-game VN epilogue:")
            print(epilogue)
            print(f"\nepilogue log: {epilogue_path}")
            return epilogue

        epilogue_context = self.build_epilogue_context(results)
        line_count_instruction = (
            "Write about 80 total lines."
            if str(self.game_mode) == "16"
            else "Write 50 to 60 total lines."
        )
        epilogue = prompt_text(
            run_gpt_prompt_generate_vn_epilogue(epilogue_context, line_count_instruction=line_count_instruction),
            "*The room settles after the final bell, everyone too tired and too awake to leave just yet.*"
        )
        with open(epilogue_path, "w") as outfile:
            outfile.write(epilogue.strip() + "\n")
        if self.clean_dialogue_log_path:
            with open(self.clean_dialogue_log_path, "a") as outfile:
                outfile.write(f"\n[{self.curr_time}] POST-GAME VN EPILOGUE\n")
                outfile.write(epilogue.strip() + "\n")
        print("\nPost-game VN epilogue:")
        print(epilogue)
        print(f"\nepilogue log: {epilogue_path}")
        return epilogue



    def server_loop(self):
        """Main loop of the server yaaaaay"""
        roles = role_pool_for_mode(self.game_mode)

        try:
            print("save_file: ", save_file)
            session_mode = self.choose_session_mode()
            resume_from_checkpoint = session_mode == "resume"
            generated_new_characters = session_mode == "new"
            pending_generated_cast = session_mode == "legacy"
            reused_existing_characters = session_mode in {"reuse_same_roles", "reuse_reroll_roles", "reuse_exact_setup"}
            reuse_exact_setup = session_mode == "reuse_exact_setup"
            if session_mode in {"resume", "legacy"}:
                print("save file detected, loading")
                self.load_session_metadata()
                roles = role_pool_for_mode(self.game_mode)
                self.load_personas_from_session(roles)
                character_group_context = self.load_character_context()
                if session_mode == "legacy":
                    context_payload = self.load_character_context_payload()
                    pending_generated_cast = not bool(
                        context_payload.get("relationship_generation_complete", False)
                    )
                if character_group_context:
                    for persona in self.personas.values():
                        if not persona.scratch.group_context:
                            persona.scratch.group_context = character_group_context
                if resume_from_checkpoint:
                    self.load_checkpoint()
                self.initialize_dialogue_log(resume_existing=resume_from_checkpoint)
                if resume_from_checkpoint and debug:
                    for persona in self.personas.values():
                        debug_log(
                            f"[RECENT-RESTORE] t={self.curr_time} | character={persona.scratch.name} | "
                            f"recent_batches={len(persona.scratch.recent_conversation)}"
                        )
            elif reused_existing_characters:
                self.load_session_metadata()
                context_payload = self.load_character_context_payload()
                context_mode = context_payload.get("game_mode")
                if context_mode:
                    self.configure_game_mode(context_mode)
                roles = role_pool_for_mode(self.game_mode)
                character_group_context = context_payload.get("character_group_context", "")
                cast = self.collect_cast_from_existing_session()
                if not cast:
                    raise ValueError(f"No saved characters found in {save_file}")
                if reuse_exact_setup:
                    self.seed_exact_setup_starting_tables(cast)
                    self.seed_exact_setup_movement_cooldowns(cast)
                    for character in cast:
                        preserved_table = self.exact_setup_starting_tables.get(character.get("name"))
                        if preserved_table in TIMERS:
                            character["starting_table"] = preserved_table
                self.archive_existing_session()
                os.makedirs(save_file, exist_ok=True)
                self.session_id = uuid.uuid4().hex[:12]
                self.dialogue_log_path = None
                self.clean_dialogue_log_path = None
                self.debug_log_path = None
                self.save_character_context(
                    character_group_context,
                    context_payload.get("character_generation_mode", "normal"),
                )
                self.rebuild_clean_cast(
                    cast,
                    roles,
                    reroll_roles=(session_mode == "reuse_reroll_roles"),
                    preserve_tables=reuse_exact_setup,
                )
                self.initialize_dialogue_log()
                self.save_personas_only("clean_character_reuse_complete")
            else:
                self.session_id = uuid.uuid4().hex[:12]
                self.choose_game_mode_for_new_cast()
                roles = role_pool_for_mode(self.game_mode)
                character_group_context = input("Enter the context in which you generate characters:\n")
                character_generation_mode = self.choose_character_generation_mode()
                self.save_character_context(character_group_context, character_generation_mode)
                if character_generation_mode == "immersion":
                    self.generate_immersion_cast(roles, character_group_context)
                else:
                    existing_character_names = []
                    role_totals = role_counts_for_mode(self.game_mode)
                    role_seen = Counter()
                    character_generation_roles = list(roles)
                    random.shuffle(character_generation_roles)
                    for role in character_generation_roles:
                        role_seen[role] += 1
                        role_label = f"{role} {role_seen[role]}" if role_totals[role] > 1 else role
                        existing_character_choices = ""
                        if existing_character_names:
                            existing_character_choices = ",".join(existing_character_names)
                        new_character = self.generate_character(role, character_group_context, existing_character_choices, role_label=role_label)
                        existing_character_names.append(new_character.scratch.name)
                self.initialize_dialogue_log()

            if not resume_from_checkpoint:
                if generated_new_characters or pending_generated_cast:
                    self.save_personas_only("character_generation_complete")
                    relationship_flag = input("Do you want at least some of them to know each other beforehand? yes or no\n")
                    if relationship_flag == "yes":
                        self.generate_selected_relationships(character_group_context)
                    self.save_personas_only("relationship_generation_complete")
                    self.mark_relationship_generation_complete()
                    if not self.should_start_game_after_generation():
                        print("Prepared character set and relationships saved. Exiting before seating/game start.")
                        return
                elif reused_existing_characters:
                    relationship_flag = input("Do you want at least some of them to know each other beforehand? yes or no\n")
                    if relationship_flag == "yes":
                        self.generate_selected_relationships(character_group_context)
                    self.save_personas_only("relationship_generation_complete")
                    self.mark_relationship_generation_complete()

                for persona_name, persona in self.personas.items():
                    exact_starting_table = self.exact_setup_table_for(persona) if reuse_exact_setup else None
                    starting_table = exact_starting_table or random.choice(list(TIMERS.keys()))
                    persona.scratch.curr_loc = starting_table
                    if reuse_exact_setup and persona.scratch.name in self.exact_setup_movement_cooldowns:
                        persona.scratch.movement_cooldown = self.exact_setup_movement_cooldowns[persona.scratch.name]
                    else:
                        persona.scratch.movement_cooldown = self.randomized_starting_movement_cooldown()
                    self.exact_setup_movement_cooldowns[persona.scratch.name] = persona.scratch.movement_cooldown
                    self.exact_setup_starting_tables[persona.scratch.name] = starting_table
                    persona.scratch.dialogue_cursors = {}
                    persona.scratch.overheard_dialogue_cursors = {}
                    persona.scratch.event_cursors = {}
                    persona.scratch.recent_conversation = []
                    self.room.locations[starting_table].personas[persona.scratch.name] = persona
                    if debug:
                        debug_log(
                            f"[LOAD] character={persona.scratch.name} | role={persona.scratch.role} | "
                            f"object_id={id(persona)} | starting_table={starting_table} | "
                            f"starting_movement_cooldown={persona.scratch.movement_cooldown}"
                        )
                self.refresh_audible_dialogue_limits()
                self.save_checkpoint("session_start")
            else:
                if debug:
                    debug_log(f"[RESUME] session_id={self.session_id} | t={self.curr_time} | loaded_characters={list(self.personas.keys())}")

            while True:
                print(f"{timedelta_to_natural(self.curr_time)} since the game started")
                for table in self.room.locations.values():
                    self.expire_table_timer_if_needed(table)
                self.sync_endgame_mode()
                self.run_exceptional_departures_if_needed(self.next_phase)

                if self.next_phase == "departure" and self.curr_time > game_end_time():
                    self.flush_pending_arrivals_before_game_end()
                    break
                game_timer = game_end_time() - self.curr_time
                print(f"{timedelta_to_natural(game_timer)} left until the game ends")

                if self.next_phase == "departure":
                    any_departures = False
                    for table_name, table in self.room.locations.items():
                        any_departures = self.run_movement_phase_for_table(table_name, table) or any_departures
                    if any_departures:
                        self.advance_phase_time("departure")
                    self.next_phase = "bidding"
                    self.save_checkpoint("departure_phase_complete")
                    continue

                if self.next_phase == "bidding":
                    for table_name, table in self.room.locations.items():
                        self.expire_table_timer_if_needed(table)
                        self.run_bidding_phase_for_table(table_name, table)
                    self.advance_phase_time("bidding")
                    self.next_phase = "arrival"
                    self.save_checkpoint("bidding_phase_complete")
                    continue

                if self.next_phase == "arrival":
                    any_arrival_activity = False
                    for table_name, table in self.room.locations.items():
                        any_arrival_activity = self.run_arrival_phase_for_table(table_name, table) or any_arrival_activity
                    if any_arrival_activity:
                        self.advance_phase_time("arrival")
                    self.next_phase = "cleanup"
                    self.save_checkpoint("arrival_phase_complete")
                    continue

                if self.next_phase == "cleanup":
                    for persona in self.personas.values():
                        persona.scratch.movement_cooldown = max(0, persona.scratch.movement_cooldown - 1)
                        if ENABLE_SPEAKING_COOLDOWN:
                            persona.scratch.speaking_cooldown = max(0, persona.scratch.speaking_cooldown - 1)

                    for table_name, table in self.room.locations.items():
                        table.current_events = []
                        table.current_lines = []
                    self.next_phase = "departure"
                    self.save_checkpoint("timestep_complete")
                    continue

                self.next_phase = "departure"
                self.save_checkpoint("unknown_phase_reset")

            self.flush_pending_arrivals_before_game_end()
            self.append_results_to_dialogue_log(
                "PRE-SPINSTER NET RESULTS",
                self.pre_spinster_results(),
                pending_roles={"Spinster"}
            )
            self.run_spinster_endgame_guess_round()
            results = resolve_endgame(self.room)
            print("Final results:")
            for player_name, won in sorted(results["final_results"].items()):
                outcome = "wins" if won else "loses"
                role = self.personas[player_name].scratch.role
                print(f"- {player_name} ({role}): {outcome}")
            if results["flipped_by_spinster"]:
                flipped = ", ".join(results["flipped_by_spinster"])
                print(f"Spinster reversal applied to: {flipped}")
            self.append_results_to_dialogue_log(
                "FINAL RESULTS",
                results["final_results"],
                flipped_by_spinster=results["flipped_by_spinster"]
            )
            self.generate_and_save_vn_epilogue(results)
            self.save_checkpoint("game_end")
            time.sleep(self.server_sleep)
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received. Stopping without saving a mid-timestep state.")
            if os.path.isfile(self.session_state_path()):
                print(f"Resume will use the latest stable checkpoint: {self.session_state_path()}")
            else:
                print("No stable checkpoint exists yet, so there is no game state to resume from.")
            return
        except FatalLLMError as exc:
            print(f"\nFatal LLM error: {exc}")
            print("Stopping simulation immediately without saving a mid-timestep state.")
            if os.path.isfile(self.session_state_path()):
                print(f"Resume will use the latest stable checkpoint: {self.session_state_path()}")
            else:
                print("No stable checkpoint exists yet, so there is no game state to resume from.")
            raise SystemExit(1)


if __name__ == '__main__':
  server = ThreeEstatesServer()
  server.server_loop()
