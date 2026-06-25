from persona.persona import *
from room import *
from utils import *
from persona.cognitive_modules.plan import *
import datetime
import random
import itertools
from global_methods import *
import os
import json
from paths import FRONTEND_SERVER_ROOT


folder_mem_saved = FRONTEND_SERVER_ROOT / "memory"
SESSION_CONTEXT_FILE = "character_context.json"
RUN_LOG_TIME_FORMAT = "%Y%m%d_%H%M%S"
NON_PERSONA_SESSION_DIRS = {"dialogue_logs"}


class ThreeEstatesServer:
    def __init__(self):
        self.personas = dict()
        self.room = RoomGraph(self.personas)
        self.personas_loc = dict()
        self.sec_per_step = 12
        self.curr_time = datetime.timedelta(0)
        self.server_sleep = 5

    def clear_table_locks(self, table, breaker_name):
        if not table.lockdown_targets:
            return
        previous_benefactors = {(lock[0], lock[2]) for lock in table.lockdown_targets}
        for previous_benefactor, role in previous_benefactors:
            if previous_benefactor in table.personas:
                table.personas[previous_benefactor].scratch.ability_active = False
                table.personas[previous_benefactor].scratch.ability_objects = []
            act_desp = f"{previous_benefactor}'s lockdown ability as {role} is nullified by {breaker_name} leaving or entering"
            nullify_event = (breaker_name, previous_benefactor, act_desp, self.curr_time, set([breaker_name, previous_benefactor]))
            table.add_table_event(nullify_event)
        table.lockdown_targets = set()

    def is_locked_at_table(self, table, persona_name):
        for benefactor, target, _role in table.lockdown_targets:
            if target == persona_name and benefactor != persona_name:
                return True
        return False

    def sync_persona_to_table_history_end(self, persona, table_name):
        table = self.room.locations[table_name]
        persona.scratch.dialogue_cursors[table_name] = len(table.dialogue_history)
        persona.scratch.event_cursors[table_name] = len(table.event_history)

    def add_lock_if_allowed(self, table, benefactor, target_name, role):
        target = table.personas[target_name]
        if target.scratch.role == "Farmer":
            special_circumstance = f"the {role} {benefactor} is trying to lock you at this table and you have to reveal you're the Farmer and immune"
            act_desp = f"{target_name} reveals as Farmer"
            reveal_event = (target_name, None, act_desp, self.curr_time, set([target_name]))
            table.add_table_event(reveal_event)
            target.speak(table, special_circumstance)
            return False
        if target.scratch.nun_protected:
            special_circumstance = f"the {role} {benefactor} is trying to lock you at this table, but the Nun card protects you"
            target.speak(table, special_circumstance)
            return False
        table.lockdown_targets.add((benefactor, target_name, role))
        return True
    
    def generate_relationship(self, character_group_context, p1, p2):
        relationship = prompt_text(
            run_gpt_prompt_generate_relationship(character_group_context, p1, p2),
            f"{p1.scratch.name} and {p2.scratch.name} know each other only casually through the game group."
        )
        #print(f"Generating relationship between {p1.role} and {p2.role}")
        p1.scratch.relationships[p2.scratch.name] = relationship
        p2.scratch.relationships[p1.scratch.name] = relationship

    def generate_character(self, role, character_group_context, existing_character_choices, name_mode):
        fallback_name = f"{role} Player"
        character_dict = prompt_dict(
            run_gpt_prompt_generate_character(character_group_context, existing_character_choices, name_mode),
            {
                "name": fallback_name,
                "first_name": fallback_name,
                "last_name": "",
                "gender": "unknown",
                "age": "30",
                "innate": f"is a cautious contestant generated as a fallback for the {role} role.",
            }
        )
        persona_path = os.path.join(save_file, character_dict['name'])
        new_persona = Persona(character_dict['name'], self.room, role, folder_mem_saved=persona_path)
        new_persona.scratch.name = character_dict['name']
        if name_mode != "single":
            new_persona.scratch.first_name = character_dict['first_name']
            new_persona.scratch.last_name = character_dict['last_name']
        new_persona.scratch.gender = character_dict['gender']
        new_persona.scratch.age = bounded_int(character_dict['age'], 30, minimum=0, maximum=120)
        new_persona.scratch.innate = character_dict['innate']
        new_persona.scratch.group_context = character_group_context
        self.personas[new_persona.scratch.name] = new_persona
        new_persona.save(persona_path)
        return new_persona

    def session_context_path(self):
        return os.path.join(save_file, SESSION_CONTEXT_FILE)

    def save_character_context(self, character_group_context, name_mode):
        os.makedirs(save_file, exist_ok=True)
        context_payload = {
            "character_group_context": character_group_context,
            "name_mode": name_mode,
        }
        with open(self.session_context_path(), "w") as outfile:
            json.dump(context_payload, outfile, indent=2)

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

    def initialize_dialogue_log(self):
        log_dir = os.path.join(save_file, "dialogue_logs")
        timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
        log_path = os.path.join(log_dir, f"dialogue_{timestamp}.log")
        debug_log_path = os.path.join(log_dir, f"debug_{timestamp}.log")
        set_dialogue_log_path(log_path)
        set_debug_log_path(debug_log_path)
        print(f"dialogue log: {log_path}")
        print(f"debug log: {debug_log_path}")



    def server_loop(self):
        """Main loop of the server yaaaaay"""
            # Assume this is your set of all roles in the game
        roles = {
            "King", "Queen", "Spinster", "Bishop", "Priest",
            "Farmer", "Thief", "Innkeeper", "Nun", "Baron"
        }

        print("save_file: ", save_file)
        if os.path.isdir(save_file): #case where it's already saved
            print("save file detected, loading")
            random_pool = list(roles)
            random.shuffle(random_pool)
            for filename in os.listdir(save_file):
                if filename in NON_PERSONA_SESSION_DIRS:
                    continue
                persona_path = os.path.join(save_file, filename)
                if not os.path.isdir(persona_path):
                    continue
                if not random_pool:
                    raise ValueError(f"More persona directories than available roles in {save_file}")
                role = random_pool.pop()
                name = persona_path.split("/")[-1]
                new_persona = Persona(name, self.room, role, folder_mem_saved=persona_path)
                self.personas[new_persona.scratch.name] = new_persona
            character_group_context = self.load_character_context()
            if character_group_context:
                for persona in self.personas.values():
                    if not persona.scratch.group_context:
                        persona.scratch.group_context = character_group_context
        else:
            character_group_context = input("Enter the context in which you generate characters:\n")
            name_mode = input("Do you want singular names or full names with first and last names etc?\n")
            self.save_character_context(character_group_context, name_mode)
            # Step 1: Initialize one persona per role
            personas = dict()
            existing_character_names = []
            for role in roles:
                existing_character_choices = ""
                if existing_character_names:
                    existing_character_choices = ",".join(existing_character_names)
                new_character = self.generate_character(role, character_group_context, existing_character_choices, name_mode)
                existing_character_names.append(new_character.scratch.name)
                personas[role] = new_character

        self.initialize_dialogue_log()

        #game_obj_cleanup = dict()
        relationship_flag = input("Do you want at least some of them to know each other beforehand? yes or no\n")
        if relationship_flag == "yes":
            # Step 2: Create all non-repeating, unique pairs (unordered)
            all_pairs = list(itertools.combinations(self.personas.values(), 2))

            # Step 3: Pick a random number of pairs (e.g., 3 to 6)
            num_relationships = random.randint(3, 6)
            selected_pairs = random.sample(all_pairs, num_relationships)

            # Step 4: Run relationship generation for selected pairs
            for p1, p2 in selected_pairs:
                self.generate_relationship(character_group_context, p1, p2)

        for persona_name, persona in self.personas.items():
            starting_table = random.choice(["Village", "Castle", "Forest"])
            persona.scratch.curr_loc = starting_table
            persona.scratch.dialogue_cursors = {}
            persona.scratch.overheard_dialogue_cursors = {}
            persona.scratch.event_cursors = {}
            persona.scratch.recent_conversation = []
            self.room.locations[starting_table].personas[persona.scratch.name] = persona
            if debug:
                debug_log(
                    f"[LOAD] character={persona.scratch.name} | role={persona.scratch.role} | "
                    f"object_id={id(persona)} | starting_table={starting_table}"
                )
            # DEBUG for player information shit
            #print(f"player information of {persona.scratch.name}:\n")
            #print(persona.get_personal_game_context())


        while (True): 
            print(f"{timedelta_to_natural(self.curr_time)} since the game started")
            
        # Done with this iteration if curr_time exceeds even the village
            if self.curr_time >= TIMERS["Village"]:
                break
            village_timer = TIMERS["Village"] - self.curr_time
            print(f"{timedelta_to_natural(village_timer)} left until the game ends")
            
            for table_name, table in self.room.locations.items():
                if self.curr_time >= TIMERS[table.name]:
                    table.timer_expired = True

                table_bidding_results = dict()
                to_remove = []
                for persona_name, persona in table.personas.items(): 
                    persona.update_knowledge(self.room)
                    retrieved_self, retrieved_others, self_retrieved_lines_related, other_retrieved_lines_related, retrieved_all_tables = persona.scratch.retrieved 

                    if persona.scratch.movement_cooldown <= 0:
                        if table.timer_expired == False:
                            if self.is_locked_at_table(table, persona_name):
                                continue
                            next_loc = decide_on_leaving(persona, table, retrieved_all_tables)
                            if next_loc != "stay": # moving to another location and getting it resolved before the bidding even starts
                                persona.scratch.movement_cooldown = MOVEMENT_LEAVE_COOLDOWN_STEPS
                                self.clear_table_locks(table, persona_name)
                                to_remove.append((persona_name, next_loc))
                                #self.room.locations[next_loc].personas[persona.name] = persona
                                self.room.locations[next_loc].incoming_arrivals.add((persona_name, None, table_name))
                            else:
                                persona.scratch.movement_cooldown = MOVEMENT_STAY_COOLDOWN_STEPS

                # We'll also reset the Bishop trigger only here after bidding for THIS round has completed and to reserve Bishop acting for the NEXT ROUND
                if table.removal_targets or to_remove:
                    table.bishop_trigger = True
                # Also reset removal targets here before the winner can be determined
                table.removal_targets = set()
                # Remove after the iteration to avoid RuntimeError
                for name, destination in to_remove:
                    event_msg = f"{name} leaves for {destination}."
                    table.add_table_event((name, None, event_msg, self.curr_time, set([name])))
                    special_circumstance = f"you have decided to leave {table.name} for {destination}; as parting words before you depart,"
                    self.personas[name].speak(table, special_circumstance)
                    self.personas[name].scratch.curr_loc = destination
                    del table.personas[name]
                # Now that all of the removals are gone we can actually bid
                for persona_name, persona in table.personas.items(): 
                    # UPDATE PERCEPTION AFTER PREVIOUS EVENTS
                    persona.update_knowledge(self.room)

                    result = bid(persona, table)
                    table_bidding_results[persona.name] = result

                final_table_results = [(name, points) for name, points in sorted(table_bidding_results.items(), key=lambda item: item[1], reverse=True)]
                if debug:
                    debug_log(f"[BID-RESULT] t={self.curr_time} | table={table.name} | ranking={final_table_results}")
                
                if final_table_results:  # if there are even people at this table
                    # Tie-break among all with the top score
                    EPS = 1e-6
                    top_score = final_table_results[0][1]
                    top_candidates = [name for name, pts in final_table_results if abs(pts - top_score) <= EPS]

                    winner = random.choice(top_candidates)
                    if debug:
                        debug_log(f"[ACTOR] t={self.curr_time} | table={table.name} | winner={winner} | top_score={top_score} | tied={top_candidates}")

                    table.personas[winner].act(table)

                for persona_name, persona in table.personas.items(): 
                    #other people taking their card back from Baron case
                    if len(table.personas.keys()) == 2:
                        remaining = set(table.personas.keys()) - {persona_name}
                        if len(remaining) != 1:
                            raise ValueError("Expected exactly one other persona")
                        the_other_name = next(iter(remaining))
                        the_other = table.personas[the_other_name]
                        if the_other.scratch.role == "Baron":
                            if persona.scratch.role in the_other.scratch.cards_slot:
                                persona.retrieve_card(table, the_other_name)
                    #NUN taking her card back case
                    if persona.scratch.role == "Nun":
                        if persona.scratch.ability_active:
                            if persona.scratch.ability_objects[0] in table.personas.keys():
                                persona.update_knowledge(self.room)

                                persona.retrieve_card(table, persona.scratch.ability_objects[0])


                

                # reset the baron and bishop triggers here since if he didn't act he "misses his chances" and any spinster baron trigger would be for next round
                table.baron_trigger = set()
                table.bishop_trigger = False

                #any spinster forced reveal. if card with them then trigger baron, otherwise don't bother
                if table.spinster_marked:
                    spinster_marked_name, spinster_name = table.spinster_marked
                    spinster_marked = table.personas[spinster_marked_name]
                    act_desp = f"the Spinster {spinster_name} forces {spinster_marked_name} to reveal as {spinster_marked.scratch.role} before departing"
                    reveal_event = (spinster_name, spinster_marked_name, act_desp, self.curr_time, set([spinster_marked_name, spinster_name]))
                    table.add_table_event(reveal_event)
                    if spinster_marked.scratch.role in spinster_marked.scratch.cards_slot: # baron-capable
                        table.baron_trigger.add(spinster_marked_name)
                    table.spinster_marked = None
                
                #resolve the ability-based forced migration BEFORE the innkeeper comes
                # forced_removal typically only has like two at most i guess
                for removal_target in table.removal_targets: # format: (sub, obj, subj_role, target_table)
                    #last words before getting yetted
                    target_name = removal_target[1]
                    destination = removal_target[3]
                    target_persona = self.personas[target_name]
                    #target_persona.speak(table, removal_reason=(removal_target[0], removal_target[3]))
                    target_persona.scratch.curr_loc = destination
                    self.room.locations[destination].incoming_arrivals.add((target_name, removal_target[0], table_name))
                    if target_name in table.personas:
                        del table.personas[target_name]

            # We then finally allow the incomers across all tables to join in
            for table_name, table in self.room.locations.items():
                innkeeper = None
                queen_followups = []
                # format: (self, "benefactor"(optional), source_table)
                for candidate, benefactor, source_table in table.incoming_arrivals:
                    if table.lockdown_targets:
                        self.clear_table_locks(table, candidate)
                    self.sync_persona_to_table_history_end(self.personas[candidate], table_name)
                    table.personas[candidate] = self.personas[candidate]
                    act_desp = f"{candidate} arrives from {source_table}"
                    arrival_event = (candidate, None, act_desp, self.personas[candidate].scratch.curr_time, set([candidate]))
                    table.add_table_event(arrival_event)
                    if self.personas[candidate].scratch.role == "Innkeeper" and self.personas[candidate].scratch.ability_active:
                        innkeeper = candidate
                        # exclusively let the true, non-bluff innkeeper say the last
                    else:
                        special_circumstance = f"you're arriving at this table from {source_table}"
                        self.personas[candidate].speak(table, special_circumstance)
                    if benefactor:
                        queen_followups.append((benefactor, candidate))
                for benefactor, candidate in queen_followups:
                    if benefactor and benefactor in table.personas and table.personas[benefactor].scratch.role == "Queen":
                        if self.add_lock_if_allowed(table, benefactor, candidate, "Queen"):
                            table.personas[benefactor].scratch.ability_objects.append(candidate)
                if innkeeper: #innkeeper is in this table now
                    innkeeper = self.personas[innkeeper]
                    innkeeper_announcement = "you've just arrived here to lock everyone down and has to announce yourself to be Innkeeper to do so (without even having to show your card even though you DO have your card)"
                    innkeeper.speak(table, special_circumstance=innkeeper_announcement)

                    for other_player_name, other_player in table.personas.items():
                        if other_player_name != innkeeper.scratch.name:
                            if self.add_lock_if_allowed(table, innkeeper.scratch.name, other_player_name, innkeeper.scratch.role):
                                innkeeper.scratch.ability_objects.append(other_player_name)
                    
                    act_desp = f"{innkeeper.scratch.name} self-declares as innkeeper and locks down everyone at the Village"
                    lockdown_event = (innkeeper.scratch.name, None, act_desp, self.curr_time, set([innkeeper.scratch.name] + innkeeper.scratch.ability_objects))
                    table.add_table_event(lockdown_event)
                    
                table.incoming_arrivals = set() # reset to None

            # After this cycle, the world takes one step forward, and the 
            # current time moves by <sec_per_step> amount. 

            self.curr_time += datetime.timedelta(seconds=self.sec_per_step)
            for persona_name, persona in self.personas.items():
                persona.scratch.curr_time = self.curr_time
                persona.scratch.movement_cooldown = max(0, persona.scratch.movement_cooldown - 1)
                persona.scratch.speaking_cooldown = max(0, persona.scratch.speaking_cooldown - 1)

            for table_name, table in self.room.locations.items():
                table.current_events = []  #reset current events and chat
                table.current_lines = []  
        # Sleep so we don't burn our machines. 
        results = resolve_endgame(self.room)
        print("Final results:")
        for player_name, won in sorted(results["final_results"].items()):
            outcome = "wins" if won else "loses"
            print(f"- {player_name}: {outcome}")
        if results["flipped_by_spinster"]:
            flipped = ", ".join(results["flipped_by_spinster"])
            print(f"Spinster reversal applied to: {flipped}")
        time.sleep(self.server_sleep)


if __name__ == '__main__':
  server = ThreeEstatesServer()
  server.server_loop()
