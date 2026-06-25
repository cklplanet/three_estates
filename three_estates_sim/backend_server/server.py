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
import shutil
import uuid
from paths import FRONTEND_SERVER_ROOT


folder_mem_saved = FRONTEND_SERVER_ROOT / "memory"
SESSION_CONTEXT_FILE = "character_context.json"
SESSION_METADATA_FILE = "session_metadata.json"
SESSION_STATE_FILE = "session_state.json"
RUN_LOG_TIME_FORMAT = "%Y%m%d_%H%M%S"
NON_PERSONA_SESSION_DIRS = {"dialogue_logs"}
NEW_SESSION_ALIASES = {"new", "n", "start new", "restart", "fresh"}
CONTINUE_SESSION_ALIASES = {"continue", "c", "resume", "r", "load"}
REUSE_CAST_SAME_ROLES_ALIASES = {"same roles", "same", "reuse roles", "reuse same", "cast roles", "2"}
REUSE_CAST_REROLL_ROLES_ALIASES = {"reroll roles", "reroll", "reassign roles", "reuse reroll", "cast reroll", "3"}


class ThreeEstatesServer:
    def __init__(self):
        self.personas = dict()
        self.room = RoomGraph(self.personas)
        self.personas_loc = dict()
        self.sec_per_step = 12
        self.curr_time = datetime.timedelta(0)
        self.server_sleep = 5
        self.session_id = None
        self.dialogue_log_path = None
        self.debug_log_path = None

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
            print("Please type 'continue', 'new', 'same roles', or 'reroll roles'.")

    def metadata_payload(self):
        return {
            "session_id": self.session_id,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "dialogue_log_path": str(self.dialogue_log_path) if self.dialogue_log_path else None,
            "debug_log_path": str(self.debug_log_path) if self.debug_log_path else None,
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
        self.dialogue_log_path = metadata.get("dialogue_log_path")
        self.debug_log_path = metadata.get("debug_log_path")
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
            "incoming_arrivals": [list(arrival) for arrival in table.incoming_arrivals],
            "bishop_trigger": table.bishop_trigger,
            "spinster_marked": list(table.spinster_marked) if table.spinster_marked else None,
            "timer_expired": table.timer_expired,
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
        table.incoming_arrivals = {tuple(arrival) for arrival in table_state.get("incoming_arrivals", [])}
        table.bishop_trigger = table_state.get("bishop_trigger", False)
        spinster_marked = table_state.get("spinster_marked")
        table.spinster_marked = tuple(spinster_marked) if spinster_marked else None
        table.timer_expired = table_state.get("timer_expired", False)

    def save_checkpoint(self, reason):
        os.makedirs(save_file, exist_ok=True)
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        for persona in self.personas.values():
            persona.save(os.path.join(save_file, persona.scratch.name))
        state = {
            "session_id": self.session_id,
            "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "save_reason": reason,
            "curr_time": self.curr_time.total_seconds(),
            "sec_per_step": self.sec_per_step,
            "tables": {
                table_name: self.serialize_table(table)
                for table_name, table in self.room.locations.items()
            },
        }
        state_path = self.session_state_path()
        tmp_path = f"{state_path}.tmp"
        with open(tmp_path, "w") as outfile:
            json.dump(state, outfile, indent=2)
        os.replace(tmp_path, state_path)
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
        self.session_id = state.get("session_id") or self.session_id or uuid.uuid4().hex[:12]
        self.curr_time = datetime.timedelta(seconds=state.get("curr_time", 0))
        self.sec_per_step = state.get("sec_per_step", self.sec_per_step)
        for table_name, table_state in state.get("tables", {}).items():
            if table_name in self.room.locations:
                self.restore_table(table_name, table_state)
        for persona in self.personas.values():
            persona.scratch.curr_time = self.curr_time
        print(f"Loaded checkpoint from: {self.session_state_path()}")

    def should_start_game_after_generation(self):
        while True:
            choice = input("Characters are generated. Type 'start' to begin this game now, or 'quit' to save the cast and stop here:\n").strip().lower()
            if choice in {"start", "s", "yes", "y", "continue", "c"}:
                return True
            if choice in {"quit", "q", "no", "n", "stop"}:
                return False
            print("Please type 'start' or 'quit'.")

    def add_lock_if_allowed(self, table, benefactor, target_name, role):
        target = table.personas[target_name]
        if target.scratch.role == "Farmer":
            special_circumstance = f"the {role} {benefactor} is trying to lock you at this table and you have to reveal you're the Farmer and immune"
            poss = "her" if target.scratch.gender == "female" else "his"
            act_desp = f"{target_name} reveals {poss} Farmer card"
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
            cast.append({
                "name": scratch.get("name") or filename,
                "first_name": scratch.get("first_name"),
                "last_name": scratch.get("last_name"),
                "gender": scratch.get("gender"),
                "age": scratch.get("age"),
                "innate": scratch.get("innate"),
                "role": scratch.get("role"),
                "group_context": scratch.get("group_context"),
            })
        return cast

    def rebuild_clean_cast(self, cast, roles, reroll_roles=False):
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
            used_roles = set()
            role_assignments = {}
            fallback_roles = list(roles)
            random.shuffle(fallback_roles)
            for character in cast:
                role = character.get("role")
                if role not in roles or role in used_roles:
                    while fallback_roles and fallback_roles[-1] in used_roles:
                        fallback_roles.pop()
                    if not fallback_roles:
                        raise ValueError(f"Could not assign a unique role to {character['name']}")
                    role = fallback_roles.pop()
                used_roles.add(role)
                role_assignments[character["name"]] = role

        self.personas = {}
        self.room = RoomGraph(self.personas)
        self.personas_loc = {}
        for character in cast:
            role = role_assignments[character["name"]]
            persona = Persona(character["name"], self.room, role)
            persona.scratch.name = character["name"]
            persona.scratch.first_name = character.get("first_name")
            persona.scratch.last_name = character.get("last_name")
            persona.scratch.gender = character.get("gender")
            persona.scratch.age = character.get("age")
            persona.scratch.innate = character.get("innate")
            persona.scratch.group_context = character.get("group_context")
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
            self.personas[new_persona.scratch.name] = new_persona

    def initialize_dialogue_log(self, resume_existing=False):
        log_dir = os.path.join(save_file, "dialogue_logs")
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        if not resume_existing or not self.dialogue_log_path:
            timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
            self.dialogue_log_path = os.path.join(log_dir, f"dialogue_{self.session_id}_{timestamp}.log")
        if not resume_existing or not self.debug_log_path:
            timestamp = datetime.datetime.now().strftime(RUN_LOG_TIME_FORMAT)
            self.debug_log_path = os.path.join(log_dir, f"debug_{self.session_id}_{timestamp}.log")
        set_dialogue_log_path(self.dialogue_log_path)
        set_debug_log_path(self.debug_log_path)
        self.save_session_metadata()
        print(f"dialogue log: {self.dialogue_log_path}")
        print(f"debug log: {self.debug_log_path}")



    def server_loop(self):
        """Main loop of the server yaaaaay"""
            # Assume this is your set of all roles in the game
        roles = {
            "King", "Queen", "Spinster", "Bishop", "Priest",
            "Farmer", "Thief", "Innkeeper", "Nun", "Baron"
        }

        try:
            print("save_file: ", save_file)
            session_mode = self.choose_session_mode()
            resume_from_checkpoint = session_mode == "resume"
            generated_new_characters = session_mode == "new"
            reused_existing_characters = session_mode in {"reuse_same_roles", "reuse_reroll_roles"}
            if session_mode in {"resume", "legacy"}:
                print("save file detected, loading")
                self.load_session_metadata()
                self.load_personas_from_session(roles)
                character_group_context = self.load_character_context()
                if character_group_context:
                    for persona in self.personas.values():
                        if not persona.scratch.group_context:
                            persona.scratch.group_context = character_group_context
                if resume_from_checkpoint:
                    self.load_checkpoint()
                self.initialize_dialogue_log(resume_existing=resume_from_checkpoint)
            elif reused_existing_characters:
                context_payload = self.load_character_context_payload()
                character_group_context = context_payload.get("character_group_context", "")
                name_mode = context_payload.get("name_mode", "")
                cast = self.collect_cast_from_existing_session()
                if not cast:
                    raise ValueError(f"No saved characters found in {save_file}")
                self.archive_existing_session()
                os.makedirs(save_file, exist_ok=True)
                self.session_id = uuid.uuid4().hex[:12]
                self.dialogue_log_path = None
                self.debug_log_path = None
                self.save_character_context(character_group_context, name_mode)
                self.rebuild_clean_cast(cast, roles, reroll_roles=(session_mode == "reuse_reroll_roles"))
                self.initialize_dialogue_log()
                self.save_personas_only("clean_character_reuse_complete")
            else:
                self.session_id = uuid.uuid4().hex[:12]
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

            if not resume_from_checkpoint:
                if generated_new_characters:
                    self.save_personas_only("character_generation_complete")
                    if not self.should_start_game_after_generation():
                        print("Character set saved. Exiting before relationship generation or seating/game start.")
                        return
                    relationship_flag = input("Do you want at least some of them to know each other beforehand? yes or no\n")
                    if relationship_flag == "yes":
                        all_pairs = list(itertools.combinations(self.personas.values(), 2))
                        num_relationships = random.randint(3, 6)
                        selected_pairs = random.sample(all_pairs, num_relationships)
                        for p1, p2 in selected_pairs:
                            self.generate_relationship(character_group_context, p1, p2)
                    self.save_personas_only("relationship_generation_complete")
                elif reused_existing_characters:
                    relationship_flag = input("Do you want at least some of them to know each other beforehand? yes or no\n")
                    if relationship_flag == "yes":
                        all_pairs = list(itertools.combinations(self.personas.values(), 2))
                        num_relationships = min(random.randint(3, 6), len(all_pairs))
                        selected_pairs = random.sample(all_pairs, num_relationships)
                        for p1, p2 in selected_pairs:
                            self.generate_relationship(character_group_context, p1, p2)
                    self.save_personas_only("relationship_generation_complete")

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
                self.save_checkpoint("session_start")
            else:
                if debug:
                    debug_log(f"[RESUME] session_id={self.session_id} | t={self.curr_time} | loaded_characters={list(self.personas.keys())}")

            while True:
                print(f"{timedelta_to_natural(self.curr_time)} since the game started")

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
                                if next_loc != "stay":
                                    persona.scratch.movement_cooldown = MOVEMENT_LEAVE_COOLDOWN_STEPS
                                    self.clear_table_locks(table, persona_name)
                                    to_remove.append((persona_name, next_loc))
                                    self.room.locations[next_loc].incoming_arrivals.add((persona_name, None, table_name))
                                else:
                                    persona.scratch.movement_cooldown = MOVEMENT_STAY_COOLDOWN_STEPS

                    if table.removal_targets or to_remove:
                        table.bishop_trigger = True
                    table.removal_targets = set()
                    for name, destination in to_remove:
                        special_circumstance = f"you have decided to leave {table.name} for {destination}; as parting words before you depart,"
                        self.personas[name].speak(table, special_circumstance)
                        event_msg = f"{name} leaves for {destination}."
                        table.add_table_event((name, None, event_msg, self.curr_time, set([name])))
                        self.personas[name].scratch.curr_loc = destination
                        del table.personas[name]

                    for persona_name, persona in table.personas.items():
                        persona.update_knowledge(self.room)
                        result = bid(persona, table)
                        table_bidding_results[persona.name] = result

                    final_table_results = [(name, points) for name, points in sorted(table_bidding_results.items(), key=lambda item: item[1], reverse=True)]
                    if debug:
                        debug_log(f"[BID-RESULT] t={self.curr_time} | table={table.name} | ranking={final_table_results}")

                    if final_table_results:
                        EPS = 1e-6
                        top_score = final_table_results[0][1]
                        top_candidates = [name for name, pts in final_table_results if abs(pts - top_score) <= EPS]

                        winner = random.choice(top_candidates)
                        if debug:
                            debug_log(f"[ACTOR] t={self.curr_time} | table={table.name} | winner={winner} | top_score={top_score} | tied={top_candidates}")

                        table.personas[winner].act(table)

                    for persona_name, persona in table.personas.items():
                        if len(table.personas.keys()) == 2:
                            remaining = set(table.personas.keys()) - {persona_name}
                            if len(remaining) != 1:
                                raise ValueError("Expected exactly one other persona")
                            the_other_name = next(iter(remaining))
                            the_other = table.personas[the_other_name]
                            if the_other.scratch.role == "Baron":
                                if persona.scratch.role in the_other.scratch.cards_slot:
                                    persona.retrieve_card(table, the_other_name)
                        if persona.scratch.role == "Nun":
                            if persona.scratch.ability_active:
                                if persona.scratch.ability_objects[0] in table.personas.keys():
                                    persona.update_knowledge(self.room)
                                    persona.retrieve_card(table, persona.scratch.ability_objects[0])

                    table.bishop_trigger = False

                    if table.spinster_marked:
                        spinster_marked_name, spinster_name = table.spinster_marked
                        spinster_marked = table.personas[spinster_marked_name]
                        act_desp = f"the Spinster {spinster_name} forces {spinster_marked_name} to reveal {spinster_marked.possessive_for()} {spinster_marked.scratch.role} card before departing"
                        reveal_event = (spinster_name, spinster_marked_name, act_desp, self.curr_time, set([spinster_marked_name, spinster_name]))
                        table.add_table_event(reveal_event)
                        spinster_marked.resolve_baron_reaction(table, spinster_marked_name, act_desp, block_ability=False)
                        table.spinster_marked = None

                    for removal_target in table.removal_targets:
                        target_name = removal_target[1]
                        destination = removal_target[3]
                        target_persona = self.personas[target_name]
                        target_persona.scratch.curr_loc = destination
                        self.room.locations[destination].incoming_arrivals.add((target_name, removal_target[0], table_name))
                        if target_name in table.personas:
                            del table.personas[target_name]

                for table_name, table in self.room.locations.items():
                    innkeeper = None
                    queen_followups = []
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
                        else:
                            special_circumstance = f"you're arriving at this table from {source_table}"
                            self.personas[candidate].speak(table, special_circumstance)
                        if benefactor:
                            queen_followups.append((benefactor, candidate))
                    for benefactor, candidate in queen_followups:
                        if benefactor and benefactor in table.personas and table.personas[benefactor].scratch.role == "Queen":
                            if self.add_lock_if_allowed(table, benefactor, candidate, "Queen"):
                                table.personas[benefactor].scratch.ability_objects.append(candidate)
                    if innkeeper:
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

                    table.incoming_arrivals = set()

                self.curr_time += datetime.timedelta(seconds=self.sec_per_step)
                for persona_name, persona in self.personas.items():
                    persona.scratch.curr_time = self.curr_time
                    persona.scratch.movement_cooldown = max(0, persona.scratch.movement_cooldown - 1)
                    persona.scratch.speaking_cooldown = max(0, persona.scratch.speaking_cooldown - 1)

                for table_name, table in self.room.locations.items():
                    table.current_events = []
                    table.current_lines = []
                self.save_checkpoint("timestep_complete")

            results = resolve_endgame(self.room)
            print("Final results:")
            for player_name, won in sorted(results["final_results"].items()):
                outcome = "wins" if won else "loses"
                print(f"- {player_name}: {outcome}")
            if results["flipped_by_spinster"]:
                flipped = ", ".join(results["flipped_by_spinster"])
                print(f"Spinster reversal applied to: {flipped}")
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
