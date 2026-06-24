import datetime
from pathlib import Path
from paths import DEFAULT_SESSION_DIR, FRONTEND_SERVER_ROOT

# Copy and paste your OpenAI API Key
OPENROUTER_KEY = "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"
# Put your name
key_owner = "<Name>"

maze_assets_loc = FRONTEND_SERVER_ROOT / "static_dirs" / "assets"
env_matrix = maze_assets_loc / "the_ville" / "matrix"
env_visuals = maze_assets_loc / "the_ville" / "visuals"

fs_storage = FRONTEND_SERVER_ROOT / "storage"
fs_temp_storage = FRONTEND_SERVER_ROOT / "temp_storage"

save_file = DEFAULT_SESSION_DIR

collision_block_id = "32125"

# Verbose 
debug = True

SPEAKING_COOLDOWN_STEPS = 1
DIALOGUE_LOG_PATH = None
DEBUG_LOG_PATH = None


PREFIX = """You are playing a digital version of a turn-based **social deduction game** involving secret roles, public actions, and table-based conversations.

GAME RULES:
- Roles belong to one of three **families**: Nobility, Commoners, Clergy. Each role has a **unique ability** and a **hidden win condition**.
- The game takes place across **three timed locations (tables)**: Castle, Forest, and Village.
- All players must be at one of the three tables at all times. Players may move between tables freely but can only leave a table if its timer is still active—unless affected by certain abilities.
- To activate an ability, a player must **reveal their card** and be holding it. Some abilities require conditions like being alone with another player.
- Only one ability may be activated at a table at a time. Players may voluntarily reveal their role to others at their table at any time.
- **Conversations are always public** at a table.
- When the game ends (all table timers expire), players win if their **individual win condition** is satisfied—*unless reversed by the Spinster’s guess*.
"""


ROLE_DICT = {
    "King": {
        "family": "Nobility",
        "ability": "When sitting at a table, may choose a family. Members of that family cannot leave the table unless the King or an unaffected player leaves. If nobility is chosen, the King may still move freely.",
        "win_condition": "Wins if at most 1 commoner is in the Castle at game end."
    },
    "Queen": {
        "family": "Nobility",
        "ability": "When leaving a table, may choose a player who must follow to the new table and cannot leave until the Queen or another player leaves it.",
        "win_condition": "Wins if sitting in the Castle without the King, or in the Village with the Priest at game end."
    },
    "Spinster": {
        "family": "Commoners",
        "ability": "When leaving the Forest, can choose to point to a player there. After leaving, that player must reveal their role to everyone else in the Forest (not including the Spinster).",
        "win_condition": "If all other players at the Spinster's final table at game end are guessed correctly. In the event of this the win conditions of all other players' at said table are reversed."
    },
    "Bishop": {
        "family": "Clergy",
        "ability": "When a player leaves the table, may guess the family of another player at the table. If correct, that player must leave the table immediately.",
        "win_condition": "Wins if sitting with no nobles at game end."
    },
    "Priest": {
        "family": "Clergy",
        "ability": "If sitting with only one other player, may view that player’s role. The ability fails if the other player does not possess their role card.",
        "win_condition": "Wins if at most 1 person is in the Forest at game end."
    },
    "Farmer": {
        "family": "Commoners",
        "ability": "Is immune to other players’ abilities, except for the Nun’s card-giving and the Spinster’s endgame reversal.",
        "win_condition": "Wins if sitting with at least two clergy members at game end."
    },
    "Thief": {
        "family": "Commoners",
        "ability": "If sitting with only one other player, may swap roles and win conditions with that player. The ability fails if the other player does not have their role card.",
        "win_condition": "Wins if every other player in the Village loses, even if the Thief is in the Village too."
    },
    "Innkeeper": {
        "family": "Commoners",
        "ability": "Upon entering the Villag from elsewhere, may declare the role. If declared, no one can leave the Village until either the Innkeeper leaves or another player enters.",
        "win_condition": "Wins if sitting with at least two nobles at game end."
    },
    "Nun": {
        "family": "Clergy",
        "ability": "If sitting with only one other player, may give away the role card. The recipient becomes immune to other abilities and must return the card if asked.",
        "win_condition": "Wins if at least three commoners win."
    },
    "Baron": {
        "family": "Nobility",
        "ability": "When a player reveals their card at a table with at least two other players, may block that ability and steal the card. The original player keeps their role but loses the ability until they sit with the Baron alone, which must be allowed.",
        "win_condition": "Wins if holding at least three other cards at game end."
    }
}

TIMERS = {"Castle": datetime.timedelta(minutes=12),
          "Forest": datetime.timedelta(minutes=13),
          "Village": datetime.timedelta(minutes=14)}


def prompt_payload(prompt_result, default=None):
    if isinstance(prompt_result, (list, tuple)) and prompt_result:
        payload = prompt_result[0]
    else:
        payload = prompt_result
    if payload is False or payload is None:
        return default
    return payload


def prompt_dict(prompt_result, defaults):
    payload = prompt_payload(prompt_result, {})
    if isinstance(payload, dict):
        merged = dict(defaults)
        merged.update({key: value for key, value in payload.items() if value not in [None, ""]})
        return merged
    return dict(defaults)


def prompt_text(prompt_result, default):
    payload = prompt_payload(prompt_result, default)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return default


def bounded_int(value, default, allowed=None, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if allowed is not None and parsed not in allowed:
        return default
    if minimum is not None and parsed < minimum:
        return default
    if maximum is not None and parsed > maximum:
        return default
    return parsed


def set_dialogue_log_path(path):
    global DIALOGUE_LOG_PATH
    DIALOGUE_LOG_PATH = Path(path)
    DIALOGUE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DIALOGUE_LOG_PATH, "a") as outfile:
        outfile.write(f"# Three Estates table log started at {datetime.datetime.now().isoformat(timespec='seconds')}\n")


def set_debug_log_path(path):
    global DEBUG_LOG_PATH
    DEBUG_LOG_PATH = Path(path)
    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEBUG_LOG_PATH, "a") as outfile:
        outfile.write(f"# Three Estates debug log started at {datetime.datetime.now().isoformat(timespec='seconds')}\n")


def debug_log(message):
    if not debug:
        return
    print(message)
    if DEBUG_LOG_PATH is None:
        return
    with open(DEBUG_LOG_PATH, "a") as outfile:
        outfile.write(message + "\n")


def write_table_event_log(table_name, event_tuple):
    if DIALOGUE_LOG_PATH is None:
        return
    subject, obj, description, timestamp, keywords = event_tuple
    subject = subject or "system"
    obj = obj or "everyone"
    keyword_text = ", ".join(sorted(str(keyword) for keyword in keywords)) if keywords else ""
    with open(DIALOGUE_LOG_PATH, "a") as outfile:
        outfile.write(f"[{timestamp}] EVENT ({table_name}) {subject} -> {obj}: {description}")
        if keyword_text:
            outfile.write(f" | keywords={keyword_text}")
        outfile.write("\n")


def write_dialogue_log(table_name, dialogue_tuple):
    if DIALOGUE_LOG_PATH is None:
        return
    speaker, target, volume, line, timestamp, _keywords = dialogue_tuple
    with open(DIALOGUE_LOG_PATH, "a") as outfile:
        outfile.write(f"[{timestamp}] DIALOGUE ({table_name}) {speaker} -> {target} [{volume}]: {line}\n")


def debug_bid(persona, table, action, bid, reasoning):
    if not debug:
        return
    cooldown = ""
    if action == "speak" and persona.scratch.speaking_cooldown > 0:
        cooldown = f" | speaking_cooldown={persona.scratch.speaking_cooldown}"
    debug_log(
        f"[BID] t={persona.scratch.curr_time} | table={table.name} | "
        f"character={persona.scratch.name} | role={persona.scratch.role} | "
        f"action={action} | bid={bid}{cooldown} | reasoning={reasoning}"
    )


def debug_perception(persona, table_name, self_count, other_count):
    if not debug:
        return
    debug_log(
        f"[PERCEIVE] t={persona.scratch.curr_time} | character={persona.scratch.name} | "
        f"table={table_name} | new_local_items={self_count} | overheard_items={other_count} | "
        f"recent_batches={len(persona.scratch.recent_conversation)}"
    )


def role_family(role):
    return ROLE_DICT[role]["family"]


def family_counts(players):
    counts = {"Nobility": 0, "Commoners": 0, "Clergy": 0}
    for player in players:
        counts[role_family(player.scratch.role)] += 1
    return counts


def final_table_map(room):
    return {
        table_name: dict(table.personas)
        for table_name, table in room.locations.items()
    }


def player_final_locations(final_tables):
    locations = {}
    for table_name, players in final_tables.items():
        for player_name in players:
            locations[player_name] = table_name
    return locations


def evaluate_base_win(player_name, player, final_tables, adjusted_results=None):
    locations = player_final_locations(final_tables)
    table_name = locations[player_name]
    table_players = final_tables[table_name]
    role = player.scratch.role
    families_at_table = family_counts(table_players.values())

    if role == "King":
        castle_commoners = family_counts(final_tables["Castle"].values())["Commoners"]
        return castle_commoners <= 1
    if role == "Queen":
        castle_players = final_tables["Castle"]
        village_players = final_tables["Village"]
        return (
            table_name == "Castle" and not any(p.scratch.role == "King" for p in castle_players.values())
        ) or (
            table_name == "Village" and any(p.scratch.role == "Priest" for p in village_players.values())
        )
    if role == "Spinster":
        guesses = getattr(player.scratch, "endgame_role_guesses", {}) or {}
        other_players = {name: p for name, p in table_players.items() if name != player_name}
        return all(
            guesses.get(name) == other.scratch.role
            for name, other in other_players.items()
        )
    if role == "Bishop":
        return families_at_table["Nobility"] == 0
    if role == "Priest":
        return len(final_tables["Forest"]) <= 1
    if role == "Farmer":
        return families_at_table["Clergy"] >= 2
    if role == "Innkeeper":
        return families_at_table["Nobility"] >= 2
    if role == "Baron":
        return len(set(player.scratch.cards_slot) - {role}) >= 3
    if role == "Nun":
        if adjusted_results is None:
            return False
        return sum(
            1 for name, result in adjusted_results.items()
            if result and role_family(locations_to_player(final_tables)[name].scratch.role) == "Commoners"
        ) >= 3
    if role == "Thief":
        if adjusted_results is None:
            return False
        village_others = [name for name in final_tables["Village"] if name != player_name]
        return all(not adjusted_results.get(name, False) for name in village_others)
    return False


def locations_to_player(final_tables):
    players = {}
    for table_players in final_tables.values():
        players.update(table_players)
    return players


def resolve_endgame(room):
    final_tables = final_table_map(room)
    players = locations_to_player(final_tables)
    base_results = {
        name: evaluate_base_win(name, player, final_tables)
        for name, player in players.items()
    }

    locations = player_final_locations(final_tables)
    flipped_by_spinster = set()
    for spinster_name, spinster in players.items():
        if spinster.scratch.role != "Spinster" or not base_results[spinster_name]:
            continue
        spinster_table = locations[spinster_name]
        flipped_by_spinster.update(
            name for name in final_tables[spinster_table] if name != spinster_name
        )

    adjusted_results = {
        name: (not result if name in flipped_by_spinster else result)
        for name, result in base_results.items()
    }

    for _ in range(max(1, len(players))):
        changed = False
        next_base = dict(base_results)
        for name, player in players.items():
            if player.scratch.role in {"Nun", "Thief"}:
                next_base[name] = evaluate_base_win(name, player, final_tables, adjusted_results)
        next_adjusted = {
            name: (not result if name in flipped_by_spinster else result)
            for name, result in next_base.items()
        }
        if next_base != base_results or next_adjusted != adjusted_results:
            changed = True
        base_results = next_base
        adjusted_results = next_adjusted
        if not changed:
            break

    return {
        "tables": {table_name: list(players_at_table) for table_name, players_at_table in final_tables.items()},
        "base_results": base_results,
        "flipped_by_spinster": sorted(flipped_by_spinster),
        "final_results": adjusted_results,
    }
