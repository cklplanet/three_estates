from persona.persona import *
from room import *
from utils import *
from persona.cognitive_modules.plan import *
import datetime
import random
import itertools
from global_methods import *
import os


folder_mem_saved = "../frontend_server/memory"


class ThreeEstatesServer:

    # TODO: actually checking game end win

    def __init__(self):
        self.personas = dict()
        self.room = RoomGraph(self.personas)
        self.personas_loc = dict()
        self.sec_per_step = 7
        self.curr_time = datetime.timedelta(0)
        self.server_sleep = 5
    
    def generate_relationship(self, character_group_context, p1, p2):
        relationship = run_gpt_prompt_generate_relationship(character_group_context, p1, p2)[0]
        #print(f"Generating relationship between {p1.role} and {p2.role}")
        p1.scratch.relationships[p2.scratch.name] = relationship
        p2.scratch.relationships[p1.scratch.name] = relationship

    def generate_character(self, role, character_group_context, existing_character_choices, name_mode):
        character_dict = run_gpt_prompt_generate_character(character_group_context, existing_character_choices, name_mode)[0]
        persona_path = os.path.join(save_file, character_dict['name'])
        new_persona = Persona(character_dict['name'], self.room, role, folder_mem_saved=persona_path)
        new_persona.scratch.name = character_dict['name']
        if name_mode != "single":
            new_persona.scratch.first_name = character_dict['first_name']
            new_persona.scratch.last_name = character_dict['last_name']
        new_persona.scratch.gender = character_dict['gender']
        new_persona.scratch.age = int(character_dict['age'])
        new_persona.scratch.innate = character_dict['innate']
        new_persona.scratch.group_context = character_group_context
        self.personas[new_persona.scratch.name] = new_persona
        new_persona.save(persona_path)
        return new_persona



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
                role = random_pool.pop()
                persona_path = os.path.join(save_file, filename)
                if os.path.isdir(persona_path):
                    name = persona_path.split("/")[-1]
                    new_persona = Persona(name, self.room, role, folder_mem_saved=persona_path)
                    self.personas[new_persona.scratch.name] = new_persona
        else:
            character_group_context = input("Enter the context in which you generate characters:\n")
            name_mode = input("Do you want singular names or full names with first and last names etc?\n")
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
            self.room.locations[starting_table].personas[persona.scratch.name] = persona
            # DEBUG for player information shit
            #print(f"player information of {persona.scratch.name}:\n")
            #print(persona.get_personal_game_context())


        while (True): 
            print(f"{timedelta_to_natural(self.curr_time)} since the game started")
            
        # Done with this iteration if curr_time exceeds even the village
            if self.curr_time >= TIMERS["Village"]:
                break
            village_timer = TIMERS["Village"] - self.curr_time
            print(f"{timedelta_to_natural(village_timer - self.curr_time)} left until the game ends")
            
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
                            next_loc = decide_on_leaving(persona, table, retrieved_all_tables)
                            if next_loc != "stay": # moving to another location and getting it resolved before the bidding even starts
                                persona.scratch.movement_cooldown = 7
                                if table.lockdown_targets:
                                #first person to move breaks locks (king, queen, innkeeper)
                                    previous_benefactors = set()
                                    for lock in table.lockdown_targets:
                                        previous_benefactors.add((lock[0], lock[2]))
                                    for previous_benefactor, role in previous_benefactors:
                                        table.personas[previous_benefactor].ability_active = False
                                        table.personas[previous_benefactor].scratch.ability_objects = []
                                        act_desp = f"{previous_benefactor}'s lockdown ability as {role} is nullified by {persona_name} leaving"
                                        nullify_event = (persona_name, previous_benefactor, act_desp, persona.scratch.curr_time, set([persona_name, previous_benefactor]))
                                        table.add_table_event(nullify_event)
                                    table.lockdown_targets = set()
                                to_remove.append((persona_name, next_loc))
                                persona.scratch.curr_loc = next_loc
                                #self.room.locations[next_loc].personas[persona.name] = persona
                                self.room.locations[next_loc].incoming_arrivals.add((persona_name, None, table_name))

                # We'll also reset the Bishop trigger only here after bidding for THIS round has completed and to reserve Bishop acting for the NEXT ROUND
                if table.removal_targets or to_remove:
                    table.bishop_trigger = True
                # Also reset removal targets here before the winner can be determined
                table.removal_targets = set()
                # Remove after the iteration to avoid RuntimeError
                for name, destination in to_remove:
                    event_msg = f"{name} leaves for {destination}."
                    table.add_table_event((name, None, event_msg, self.curr_time, set([name])))
                    special_circumstance = f"you have decided to leave this table for another, as parting words,"
                    self.personas[name].speak(table, special_circumstance)
                    del table.personas[name]
                # Now that all of the removals are gone we can actually bid
                for persona_name, persona in table.personas.items(): 
                    # UPDATE PERCEPTION AFTER PREVIOUS EVENTS
                    persona.update_knowledge(self.room)

                    result = bid(persona, table)
                    table_bidding_results[persona.name] = result

                final_table_results = [(name, points) for name, points in sorted(table_bidding_results.items(), key=lambda item: item[1], reverse=True)]
                print("final table results - --------", final_table_results)
                
                if final_table_results:  # if there are even people at this table
                    # Tie-break among all with the top score
                    EPS = 1e-6
                    top_score = final_table_results[0][1]
                    top_candidates = [name for name, pts in final_table_results if abs(pts - top_score) <= EPS]

                    winner = random.choice(top_candidates)
                    #print(f"tie-break among {top_candidates} at {top_score} → winner: {winner}")

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
                    reveal_event = (spinster_name, spinster_marked_name, act_desp, self.scratch.curr_time, set([spinster_marked_name, spinster_name]))
                    table.add_table_event(reveal_event)
                    if spinster_marked.scratch.role not in spinster_marked.scratch.cards_slot: # baron-capable
                        table.baron_trigger.add(spinster_marked_name)
                    table.spinster_marked = None
                
                #resolve the ability-based forced migration BEFORE the innkeeper comes
                # forced_removal typically only has like two at most i guess
                for removal_target in table.removal_targets: # format: (sub, obj, subj_role, target_table)
                    #last words before getting yetted
                    target_name = removal_target[1]
                    #target_persona = self.personas[target_name]
                    #target_persona.speak(table, removal_reason=(removal_target[0], removal_target[3]))
                    self.room.locations[removal_target[3]].incoming_arrivals.add((target_name, removal_target[0], table_name))
                    del table.personas[target_name]

            # TODO: (MUST FIX) SOMEHOW a person leaving for another table reads info from the destination table?
            # We then finally allow the incomers across all tables to join in
            for table_name, table in self.room.locations.items():
                innkeeper = None
                # format: (self, "benefactor"(optional), source_table)
                for candidate, benefactor, source_table in table.incoming_arrivals:
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
                if innkeeper: #innkeeper is in this table now
                    innkeeper = self.personas[innkeeper]
                    innkeeper_announcement = "you've just arrived here to lock everyone down and has to announce yourself to be Innkeeper to do so (without even having to show your card even though you DO have your card)"
                    innkeeper.speak(table, special_circumstance=innkeeper_announcement)

                    for other_player_name, other_player in table.personas.items():
                        if other_player_name != innkeeper.scratch.name:
                            if other_player.scratch.role == "Farmer": # farmer immunity
                                special_circumstance = f"the Innkeeper {self.scratch.name} is trying to lock down everyone at the table and you have to reveal you're the Farmer that you're immune"
                                act_desp = f"{other_player_name} reveals as Farmer"
                                reveal_event = (other_player_name, None, act_desp, self.scratch.curr_time, set([other_player_name]))
                                table.add_table_event(reveal_event)
                                other_player.speak(table, special_circumstance)
                            else:
                                table.lockdown_targets.add((self.scratch.name, other_player_name, self.scratch.role))
                                innkeeper.scratch.ability_objects.append(other_player_name)
                    
                    act_desp = f"{innkeeper.scratch.name} self-declares as innkeeper and locks down everyone at the Village"
                    lockdown_event = (innkeeper.scratch.name, None, act_desp, self.scratch.curr_time, set([innkeeper.scratch.name] + innkeeper.scratch.ability_objects))
                    table.add_table_event(lockdown_event)
                    
                table.incoming_arrivals = set() # reset to None

            # After this cycle, the world takes one step forward, and the 
            # current time moves by <sec_per_step> amount. 

            self.curr_time += datetime.timedelta(seconds=self.sec_per_step)
            for persona_name, persona in self.personas.items():
                persona.scratch.curr_time = self.curr_time
                persona.scratch.movement_cooldown = max(0, persona.scratch.movement_cooldown - 1)

            for table_name, table in self.room.locations.items():
                table.current_events = []  #reset current events and chat
                table.current_lines = []  
        # Sleep so we don't burn our machines. 
        time.sleep(self.server_sleep)


if __name__ == '__main__':
  server = ThreeEstatesServer()
  server.server_loop()