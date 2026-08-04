import datetime
import hashlib
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from paths import DEFAULT_SESSION_DIR, FRONTEND_SERVER_ROOT, PROJECT_ROOT, SESSIONS_ROOT
from localization import available_locales, display_name, protocol_display_name, tr

def read_local_env_value(key):
    for env_path in (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"):
        if not env_path.is_file():
            continue
        with open(env_path) as infile:
            for raw_line in infile:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                env_key, env_value = line.split("=", 1)
                if env_key.strip() == key:
                    return env_value.strip().strip('"').strip("'")
    return None


def read_int_config(key, default):
    raw_value = os.getenv(key) or read_local_env_value(key)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        print(tr("terminal.invalid_integer", key=key, value=repr(raw_value), default=default))
        return default


def read_bool_config(key, default):
    raw_value = os.getenv(key) or read_local_env_value(key)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "y", "on"}


OPENROUTER_KEY = os.getenv("OPENROUTER_KEY") or read_local_env_value("OPENROUTER_KEY") or "YOUR_API_KEY_HERE"
CHARACTER_GENERATION_LLM_MODEL = os.getenv("THREE_ESTATES_CHARACTER_MODEL") or read_local_env_value("THREE_ESTATES_CHARACTER_MODEL") or "openai/gpt-5.5"
GAME_LOOP_LLM_MODEL = os.getenv("THREE_ESTATES_GAME_MODEL") or read_local_env_value("THREE_ESTATES_GAME_MODEL") or "openai/gpt-5.5"
DIALOGUE_GENERATION_LLM_MODEL = os.getenv("THREE_ESTATES_DIALOGUE_MODEL") or read_local_env_value("THREE_ESTATES_DIALOGUE_MODEL") or "openai/gpt-5.5"
SPINSTER_GUESS_LLM_MODEL = os.getenv("THREE_ESTATES_SPINSTER_GUESS_MODEL") or read_local_env_value("THREE_ESTATES_SPINSTER_GUESS_MODEL") or DIALOGUE_GENERATION_LLM_MODEL
EPILOGUE_GENERATION_LLM_MODEL = os.getenv("THREE_ESTATES_EPILOGUE_MODEL") or read_local_env_value("THREE_ESTATES_EPILOGUE_MODEL") or "openai/gpt-5.5"
POIGNANCY_SCORING_LLM_MODEL = os.getenv("THREE_ESTATES_POIGNANCY_MODEL") or read_local_env_value("THREE_ESTATES_POIGNANCY_MODEL") or "openai/gpt-5.5"
FALLBACK_LLM_MODEL = os.getenv("THREE_ESTATES_FALLBACK_MODEL") or read_local_env_value("THREE_ESTATES_FALLBACK_MODEL") or "openai/gpt-5.5"
# Put your name
key_owner = "<Name>"

maze_assets_loc = FRONTEND_SERVER_ROOT / "static_dirs" / "assets"
env_matrix = maze_assets_loc / "the_ville" / "matrix"
env_visuals = maze_assets_loc / "the_ville" / "visuals"

fs_storage = FRONTEND_SERVER_ROOT / "storage"
fs_temp_storage = FRONTEND_SERVER_ROOT / "temp_storage"

SESSION_NAME = os.getenv("THREE_ESTATES_SESSION_NAME") or read_local_env_value("THREE_ESTATES_SESSION_NAME")
SESSION_DIR = os.getenv("THREE_ESTATES_SESSION_DIR") or read_local_env_value("THREE_ESTATES_SESSION_DIR")
if SESSION_DIR:
    save_file = Path(SESSION_DIR).expanduser()
elif SESSION_NAME:
    save_file = SESSIONS_ROOT / SESSION_NAME
else:
    save_file = DEFAULT_SESSION_DIR

collision_block_id = "32125"

# Verbose 
debug = True

MOVEMENT_LEAVE_COOLDOWN_STEPS = read_int_config("THREE_ESTATES_MOVEMENT_LEAVE_COOLDOWN_STEPS", 4)
MOVEMENT_STAY_COOLDOWN_STEPS = read_int_config("THREE_ESTATES_MOVEMENT_STAY_COOLDOWN_STEPS", 2)
STARTING_MOVEMENT_COOLDOWN_STEPS = read_int_config("THREE_ESTATES_STARTING_MOVEMENT_COOLDOWN_STEPS", MOVEMENT_LEAVE_COOLDOWN_STEPS)
STARTING_MOVEMENT_COOLDOWN_RADIUS = max(0, read_int_config("THREE_ESTATES_STARTING_MOVEMENT_COOLDOWN_RADIUS", 2))
NON_SPEAKING_ACTION_MOVEMENT_COOLDOWN_DECREMENT = max(
    0,
    read_int_config("THREE_ESTATES_NON_SPEAKING_ACTION_COOLDOWN_DECREMENT", 1),
)
ENABLE_SPEAKING_COOLDOWN = read_bool_config("THREE_ESTATES_ENABLE_SPEAKING_COOLDOWN", False)
ALLOW_SPEECH_REASONING = read_bool_config("THREE_ESTATES_ALLOW_SPEECH_REASONING", True)
USE_LLM_STRATEGIC_CHAT_POIGNANCY_SCORING = read_bool_config(
    "THREE_ESTATES_USE_LLM_CHAT_POIGNANCY_SCORING",
    False,
)
SPEAKING_COOLDOWN_STEPS = read_int_config("THREE_ESTATES_SPEAKING_COOLDOWN_STEPS", 1)
SCRATCH_IMPORTANCE_TRIGGER_MAX = read_int_config("THREE_ESTATES_IMPORTANCE_TRIGGER_MAX", 150)
SCRATCH_RETENTION_BATCHES = read_int_config("THREE_ESTATES_RETENTION_BATCHES", 15)
SCRATCH_ATTENTION_BANDWIDTH = read_int_config("THREE_ESTATES_ATTENTION_BANDWIDTH", 3)
MIN_ACTION_BID_SCORE = read_int_config("THREE_ESTATES_MIN_ACTION_BID_SCORE", 2)
RETRIEVED_SELF_EVENT_CAP = read_int_config("THREE_ESTATES_RETRIEVED_SELF_EVENT_CAP", 10)
RETRIEVED_SELF_THOUGHT_CAP = read_int_config("THREE_ESTATES_RETRIEVED_SELF_THOUGHT_CAP", 8)
RETRIEVED_TABLE_EVENT_CAP = read_int_config("THREE_ESTATES_RETRIEVED_TABLE_EVENT_CAP", 8)
RETRIEVED_TABLE_THOUGHT_CAP = read_int_config("THREE_ESTATES_RETRIEVED_TABLE_THOUGHT_CAP", 6)
RETRIEVED_OTHER_TABLE_EVENT_CAP = read_int_config("THREE_ESTATES_RETRIEVED_OTHER_TABLE_EVENT_CAP", 3)
RETRIEVED_OTHER_TABLE_THOUGHT_CAP = read_int_config("THREE_ESTATES_RETRIEVED_OTHER_TABLE_THOUGHT_CAP", 2)
RETRIEVED_CURRENT_TABLE_EVENT_TOTAL_CAP = read_int_config("THREE_ESTATES_RETRIEVED_CURRENT_TABLE_EVENT_TOTAL_CAP", RETRIEVED_TABLE_EVENT_CAP)
RETRIEVED_CURRENT_TABLE_THOUGHT_TOTAL_CAP = read_int_config("THREE_ESTATES_RETRIEVED_CURRENT_TABLE_THOUGHT_TOTAL_CAP", RETRIEVED_TABLE_THOUGHT_CAP)
RETRIEVED_FOREIGN_TABLE_EVENT_TOTAL_CAP = read_int_config("THREE_ESTATES_RETRIEVED_FOREIGN_TABLE_EVENT_TOTAL_CAP", RETRIEVED_OTHER_TABLE_EVENT_CAP)
RETRIEVED_FOREIGN_TABLE_THOUGHT_TOTAL_CAP = read_int_config("THREE_ESTATES_RETRIEVED_FOREIGN_TABLE_THOUGHT_TOTAL_CAP", RETRIEVED_OTHER_TABLE_THOUGHT_CAP)
TRANSIT_PERSON_MEMORY_CAP = max(0, read_int_config("THREE_ESTATES_TRANSIT_PERSON_MEMORY_CAP", 2))
NORMAL_TIMER_URGENCY_PHASES = read_int_config("THREE_ESTATES_NORMAL_TIMER_URGENCY_PHASES", 2)
ENDGAME_TIMER_URGENCY_PHASES = read_int_config("THREE_ESTATES_ENDGAME_TIMER_URGENCY_PHASES", 1)
SIM_SECONDS_PER_STEP = read_int_config(
    "THREE_ESTATES_SECONDS_PER_PHASE",
    read_int_config("THREE_ESTATES_SECONDS_PER_STEP", 10)
)
CASUAL_SECONDS_PER_PHASE = max(
    1,
    read_int_config("THREE_ESTATES_CASUAL_SECONDS_PER_PHASE", SIM_SECONDS_PER_STEP),
)
ENDGAME_SECONDS_PER_PHASE = read_int_config("THREE_ESTATES_ENDGAME_SECONDS_PER_PHASE", 2.5 * SIM_SECONDS_PER_STEP)
PHASE_SNAPSHOT_RETENTION = max(1, read_int_config("THREE_ESTATES_PHASE_SNAPSHOT_RETENTION", 2))
DIALOGUE_LOG_PATH = None
CLEAN_DIALOGUE_LOG_PATH = None
DEBUG_LOG_PATH = None
TABLE_LOG_DIR = None
CHARACTER_LOG_DIR = None
CHARACTER_LOG_NAMES = set()
CHARACTER_LOG_FILENAMES = {}
GAME_MODE = "10"

TIMER_CONFIGS = {
    "10": {
        "Castle": datetime.timedelta(minutes=read_int_config("THREE_ESTATES_10_CASTLE_TIMER_MINUTES", 6)),
        "Forest": datetime.timedelta(minutes=read_int_config("THREE_ESTATES_10_FOREST_TIMER_MINUTES", 7)),
        "Village": datetime.timedelta(minutes=read_int_config("THREE_ESTATES_10_VILLAGE_TIMER_MINUTES", 8)),
    },
    "16": {
        "Castle": datetime.timedelta(minutes=read_int_config("THREE_ESTATES_16_CASTLE_TIMER_MINUTES", 8)),
        "Forest": datetime.timedelta(minutes=read_int_config("THREE_ESTATES_16_FOREST_TIMER_MINUTES", 9)),
        "Village": datetime.timedelta(minutes=read_int_config("THREE_ESTATES_16_VILLAGE_TIMER_MINUTES", 10)),
    },
}

ROLE_POOLS = {
    "10": [
        "King", "Queen", "Spinster", "Bishop", "Priest",
        "Farmer", "Thief", "Innkeeper", "Nun", "Baron",
    ],
    "16": [
        "King", "Queen", "Spinster", "Bishop", "Innkeeper",
        "Priest", "Priest", "Nun", "Nun",
        "Farmer", "Farmer", "Farmer", "Thief", "Thief",
        "Baron", "Baron",
    ],
}


class FatalLLMError(RuntimeError):
    """Raised when an LLM call or required LLM output parse fails."""


class DynamicPrefix:
    def __str__(self):
        return build_prefix()

    def __format__(self, _format_spec):
        return build_prefix()


PREFIX = DynamicPrefix()


ROLE_DICT = {
    "King": {
        "family": "Nobility",
        "ability": "When sitting at a table, may choose a family. ALREADY PRESENT members of that family cannot leave the table (overriding even Queen drag attempts) unless the King or an unaffected player leaves. If nobility is chosen, the King may still move freely (BUT will still break the lock if he chooses to depart).",
        "win_condition": "Wins if at most 1 commoner is in the Castle at game end."
    },
    "Queen": {
        "family": "Nobility",
        "ability": "When leaving a table, may choose a player who must follow to the new table and cannot leave until the Queen or another player leaves it.",
        "win_condition": "Wins if sitting in the Castle without any seated player whose current role is King, or in the Village with at least one seated player whose current role is Priest at game end. Loose King/Priest cards held by other roles do not count as those players being present."
    },
    "Spinster": {
        "family": "Commoners",
        "ability": "When leaving the Forest (NOT immune to Forest timer lockdown), can choose to point to a player there; immune to Baron's block and steal while doing so due to being no longer present. After leaving, that player must reveal their role to everyone else in the Forest (not including the Spinster).",
        "win_condition": "Wins if all other players' roles at the Spinster's final table at game end are guessed correctly. If there is no other player at that table, the Spinster trivially wins without making any guesses. When the Spinster wins, the win/loss results of all other players at that table are reversed."
    },
    "Bishop": {
        "family": "Clergy",
        "ability": "IMMEDIATELY (as in, within seconds of) whenever a player leaves the table, may guess the family of another player at the table. If correct, that player must leave the table immediately.",
        "win_condition": "Wins if sitting with no nobles at game end."
    },
    "Priest": {
        "family": "Clergy",
        "ability": "If sitting with only one other player, may view that player’s role. The ability fails if the other player does not possess their role card.",
        "win_condition": "Wins if at most 1 person is in the Forest at game end."
    },
    "Farmer": {
        "family": "Commoners",
        "ability": "Immune to most abilities from any other role (yes INCLUDING Baron steal etc), except the following three cases: Nun card-giving, directly forced reveal from Spinster and Priest, and Spinster endgame reversal. May need to reveal the Farmer card to prove immunity.",
        "win_condition": "Wins if sitting with at least 2 clergy member(s) at game end."
    },
    "Thief": {
        "family": "Commoners",
        "ability": "If sitting with only one other player, may swap roles and win conditions with that player (and, in case of the target being Baron, receive all the Baron's stolen cards too); does not lose any Nun protection in this case. The ability fails if the other player does not have their role card, and Thieves are immune to Thief swaps. The same two players cannot immediately reverse a Thief swap while the table state remains the same one-on-one pair; any table-state change, such as either party leaving or anyone arriving, clears that reverse-swap lock.",
        "win_condition": "Wins if every player in the Village who isn't a Thief loses/doesn't exist."
    },
    "Innkeeper": {
        "family": "Commoners",
        "ability": "Upon entering the Village from elsewhere (and ONLY upon entry, NOT including if the Innkeeper has already been in the Village beforehand), may reveal the Innkeeper card and declare the role. If revealed and declared, no one can leave the Village until either the Innkeeper leaves or another player enters.",
        "win_condition": "Wins if sitting with at least two nobles at game end."
    },
    "Nun": {
        "family": "Clergy",
        "ability": "If sitting with only one other player, may give away the role card. The recipient becomes immune to other abilities while holding at least one willingly granted Nun card and must return a Nun's own card if that Nun asks.",
        "win_condition": "Wins if at least 3 Commoners win."
    },
    "Baron": {
        "family": "Nobility",
        "ability": "When a player reveals their own role card at a table with at least two other players, may reveal the Baron card to block that ability and steal the revealed card. If it was only a voluntary reveal, the reveal itself still stands but the Baron may still steal the card. The Baron does NOT get the abilities or protection effects of stolen cards. The original player keeps their role and win condition but loses use/reveal of the card until valid retrieval.",
        "win_condition": "Wins if holding at least 3 cards other than the Baron's own card at game end, counting willingly granted Nun cards."
    }
}


def role_count_summary(mode=None):
    counts = role_counts_for_mode(mode)
    return ", ".join(f"{role} x{counts[role]}" for role in ROLE_DICT.keys() if counts.get(role, 0))


def role_family_glossary():
    role_entries = [
        protocol_display_name("role", role)
        for role in ROLE_DICT
    ]
    families = dict.fromkeys(
        role_data["family"] for role_data in ROLE_DICT.values()
    )
    family_entries = [
        protocol_display_name("family", family)
        for family in families
    ]
    return "; ".join(role_entries + family_entries)


def localize_rulebook_terms(text):
    rendered = str(text)
    for role in sorted(ROLE_DICT, key=len, reverse=True):
        localized = protocol_display_name("role", role)
        if localized != role:
            rendered = re.sub(
                rf"(?<![A-Za-z]){re.escape(role)}(?![A-Za-z])",
                localized,
                rendered,
            )
    families = dict.fromkeys(
        role_data["family"] for role_data in ROLE_DICT.values()
    )
    for family in sorted(families, key=len, reverse=True):
        localized = protocol_display_name("family", family)
        if localized != family:
            rendered = re.sub(
                rf"(?<![A-Za-z]){re.escape(family)}(?![A-Za-z])",
                localized,
                rendered,
            )
    return rendered


def mode_label(mode=None):
    mode = str(mode or GAME_MODE)
    return "expanded 16-player mode" if mode == "16" else "base 10-player mode"


def update_role_dict_for_mode(mode=None):
    mode = str(mode or GAME_MODE)
    farmer_clergy = 3 if mode == "16" else 2
    nun_commoners = 5 if mode == "16" else 3
    baron_trophies = 4 if mode == "16" else 3
    nun_stack_note = (
        " In this mode there are two Nuns; Nun protection can stack, and a target remains protected while holding at least one willingly granted Nun card."
        if mode == "16" else ""
    )
    baron_vs_baron_note = (
        " In this mode there are two Barons; a Baron can block another non-Nun-protected Baron's reveal/ability and steal that Baron's trophy cards, but NOT that Baron's own Baron role card."
        if mode == "16" else ""
    )

    ROLE_DICT["Farmer"]["win_condition"] = f"Wins if sitting with at least {farmer_clergy} clergy member(s) at game end."
    ROLE_DICT["Thief"]["ability"] = (
        "If sitting with only one other player, may swap roles and win conditions with that player "
        "(and, in case of the target being Baron, receive all the Baron's stolen cards too); does not lose any Nun protection in this case. "
        "The ability fails if the other player does not have their role card, and Thieves are immune to Thief swaps. "
        "The same two players cannot immediately reverse a Thief swap while the table state remains the same one-on-one pair; "
        "any table-state change, such as either party leaving or anyone arriving, clears that reverse-swap lock."
    )
    ROLE_DICT["Nun"]["ability"] = (
        "If sitting with only one other player, may give away the role card. "
        "The recipient becomes immune to other abilities while holding at least one willingly granted Nun card and must return a Nun's own card if that Nun asks."
        + nun_stack_note
    )
    ROLE_DICT["Nun"]["win_condition"] = f"Wins if at least {nun_commoners} Commoners win."
    ROLE_DICT["Baron"]["ability"] = (
        "When a player reveals their own role card at a table with at least two other players, may reveal the Baron card to block that ability and steal the revealed card. "
        "If it was only a voluntary reveal, the reveal itself still stands but the Baron may still steal the card. "
        "The Baron does NOT get the abilities or protection effects of stolen cards, but can still be protected by a consciously granted Nun card. "
        "The original player keeps their role and win condition but loses use/reveal of the card until valid retrieval."
        + baron_vs_baron_note
    )
    ROLE_DICT["Baron"]["win_condition"] = f"Wins if holding at least {baron_trophies} cards other than the Baron's own card at game end, counting willingly granted Nun cards."


def build_prefix(mode=None):
    mode = str(mode or GAME_MODE)
    update_role_dict_for_mode(mode)
    table_names = table_names_for_mode(mode)
    table_line = f"This mode uses these tables: {', '.join(table_names)}."
    if mode == "16":
        table_line += " Wilderness is connected to Castle, Forest, and Village; no role win condition directly names Wilderness, and it closes when the last of Castle/Forest/Village closes."
    role_lines = []
    for role, role_data in ROLE_DICT.items():
        count = role_counts_for_mode(mode).get(role, 0)
        if not count:
            continue
        count_text = f"{count} instance" + ("" if count == 1 else "s")
        role_lines.append(
            f"- {role} ({count_text}), {role_data['family']}: {role_data['ability']} Win: {role_data['win_condition']}"
        )
    retrieval_lines = [
        "- If the Baron stole your own role card, you keep your role and win condition but cannot use/reveal that card. You can reclaim it when and only when sitting alone with the Baron who stole it; the Baron must comply.",
        "- If the Nun gave you the Nun card, you are protected while holding it, cannot pass it onward, and must return that Nun's own card when that Nun asks.",
    ]
    if mode == "16":
        retrieval_lines.append(
            "- Baron-vs-Baron trophy theft does not create a Baron role-card retrieval claim, because the target Baron's own role card was not stolen."
        )
    rulebook = (
        "You are playing a digital version of a turn-based **social deduction game** involving secret roles, public actions, and table-based conversations.\n\n"
        "GAME RULES:\n"
        f"- Active ruleset: {mode_label(mode)}.\n"
        "- Roles belong to one of three **families**: Nobility, Commoners, Clergy. Each player has exactly one hidden assigned role and one own role card.\n"
        f"- Exact role pool for this game: {role_count_summary(mode)}.\n"
        f"- {table_line}\n"
        "- All players must be at some table at all times unless in transit. Players may move between connected tables freely only while the source table's timer is still active. Once a table's timer lockdown resolves, it is FINAL: nobody seated there can leave by normal movement or by any voluntary, forced, or reaction-based role ability. Queen drags, Spinster departures, Bishop exiles, Innkeeper departure bids, and every other effect that would move someone out all fail against an expired table. Players may still enter an expired table.\n"
        "- To activate an ability, a player must reveal their own role card and be holding it. Some abilities require conditions like being alone with another player.\n"
        "- A role card's physical location is NOT the location of its role, family, or player. Except when a Thief ability successfully swaps roles, every player keeps their current role, family, and win condition even when their card is held by someone else. Table composition and location-based win conditions count seated players by their current roles, NEVER loose cards: for example, a Baron holding a King card is still only a Baron, and does not make the King present at that table.\n"
        "- Only one ability may be activated at a table at a time. Players may voluntarily reveal their role to others at their table at any time.\n"
        "- Conversations are always public at a table.\n"
        "- When the game ends, players win if their individual win condition is satisfied, unless reversed by the Spinster's guess.\n"
        "- Another player character's status, title, species, class, job, faction, or social role in their original source material is only flavor/context. It does NOT prove or imply their hidden game role or family here.\n\n"
        "ROLE RULEBOOK FOR THIS MODE ONLY:\n"
        + "\n".join(role_lines)
        + "\n\nCARD RETRIEVAL RULES:\n"
        + "\n".join(retrieval_lines)
        + "\n\nADDITIONAL NOTES:\n"
        "- Nun card protection takes the highest precedence, even over Farmer immunity. Even an ability-granted, non-stolen Nun card does NOT protect the Baron from having to return a stolen card when required to.\n"
    )
    localized_rulebook = localize_rulebook_terms(rulebook)
    if localized_rulebook == rulebook:
        return rulebook
    return (
        "LOCALIZED ROLE/FAMILY GLOSSARY "
        "(canonical English protocol IDs are retained in parentheses):\n"
        f"{role_family_glossary()}\n\n"
        f"{localized_rulebook}"
    )


def thief_swap_pair(player_a, player_b):
    return frozenset([player_a, player_b])


def thief_reverse_swap_locked(table, thief_name):
    if len(getattr(table, "personas", {})) != 2:
        return False
    if thief_name not in table.personas:
        return False
    if table.personas[thief_name].scratch.role != "Thief":
        return False
    other_names = [name for name in table.personas if name != thief_name]
    if not other_names:
        return False
    return thief_swap_pair(thief_name, other_names[0]) in getattr(table, "thief_swap_locks", set())


def add_thief_swap_lock(table, player_a, player_b):
    if not hasattr(table, "thief_swap_locks"):
        table.thief_swap_locks = set()
    table.thief_swap_locks.add(thief_swap_pair(player_a, player_b))


def clear_thief_swap_locks_for_table_change(table, trigger_name=None):
    if not hasattr(table, "thief_swap_locks"):
        table.thief_swap_locks = set()
        return []
    if not table.thief_swap_locks:
        return []
    if trigger_name is None:
        cleared = list(table.thief_swap_locks)
        table.thief_swap_locks = set()
        return cleared
    cleared = [pair for pair in table.thief_swap_locks if trigger_name in pair]
    if cleared:
        table.thief_swap_locks.difference_update(cleared)
    return cleared


TIMERS = {}


def set_game_mode(mode):
    global GAME_MODE
    mode = str(mode or "10").strip()
    if mode not in ROLE_POOLS:
        mode = "10"
    GAME_MODE = mode
    TIMERS.clear()
    TIMERS.update(TIMER_CONFIGS[mode])
    if mode == "16":
        TIMERS["Wilderness"] = max(TIMER_CONFIGS[mode].values())
    update_role_dict_for_mode(mode)


def role_pool_for_mode(mode=None):
    return list(ROLE_POOLS.get(str(mode or GAME_MODE), ROLE_POOLS["10"]))


def role_counts_for_mode(mode=None):
    return Counter(role_pool_for_mode(mode))


def table_names_for_mode(mode=None):
    return list((TIMER_CONFIGS["16"] if str(mode or GAME_MODE) == "16" else TIMER_CONFIGS["10"]).keys()) + (
        ["Wilderness"] if str(mode or GAME_MODE) == "16" else []
    )


def regular_timed_table_names():
    return [table for table in TIMERS if table != "Wilderness"]


set_game_mode(read_local_env_value("THREE_ESTATES_GAME_MODE") or os.getenv("THREE_ESTATES_GAME_MODE") or "10")


def card_id(role, owner_name=None):
    return f"{role}:{owner_name}" if owner_name else role


def retag_card_owner(card, owner_name):
    return card_id(card_role(card), owner_name)


def retag_cards_owner(cards, owner_name):
    return {retag_card_owner(card, owner_name) for card in set(cards or [])}


def card_role(card):
    return str(card).split(":", 1)[0]


def card_owner(card):
    parts = str(card).split(":", 1)
    return parts[1] if len(parts) == 2 else None


def owned_role_card(persona, role=None):
    role = role or persona.scratch.role
    return card_id(role, persona.scratch.name)


def card_matches(card, role, owner_name=None):
    if card == role and owner_name is None:
        return True
    if card_role(card) != role:
        return False
    return owner_name is None or card_owner(card) == owner_name


def matching_cards(cards, role, owner_name=None):
    return {card for card in set(cards or []) if card_matches(card, role, owner_name)}


def has_card(cards, role, owner_name=None):
    return bool(matching_cards(cards, role, owner_name))


def has_own_role_card(persona, role=None):
    role = role or persona.scratch.role
    return has_card(persona.scratch.cards_slot, role, persona.scratch.name) or role in persona.scratch.cards_slot


def remove_own_role_card(persona, role=None):
    role = role or persona.scratch.role
    removed = matching_cards(persona.scratch.cards_slot, role, persona.scratch.name)
    if not removed and role in persona.scratch.cards_slot:
        removed = {role}
    persona.scratch.cards_slot.difference_update(removed)
    return removed


def add_owned_card(persona, role, owner_name):
    persona.scratch.cards_slot.add(card_id(role, owner_name))


def held_non_own_cards(persona):
    own = owned_role_card(persona)
    return {
        card for card in set(persona.scratch.cards_slot)
        if card != own and not (card == persona.scratch.role and not card_owner(card))
    }


def held_trophy_cards(persona):
    return held_non_own_cards(persona)


def nun_protection_cards(persona):
    tracked_cards = set(getattr(persona.scratch, "nun_protection_cards", set()) or set())
    tracked_cards = {
        card for card in tracked_cards
        if card in set(persona.scratch.cards_slot or [])
        and card_matches(card, "Nun")
    }
    if tracked_cards:
        return tracked_cards
    if not getattr(persona.scratch, "nun_protected", False):
        return set()
    # Legacy saves only had the boolean plus cards_slot. Treat non-own Nun cards
    # as granted protection only when no explicit protection-card set exists yet.
    return {
        card for card in matching_cards(persona.scratch.cards_slot, "Nun")
        if not card_matches(card, "Nun", persona.scratch.name)
        and not (card == "Nun" and persona.scratch.role == "Nun")
    }


def has_nun_protection(persona):
    return bool(getattr(persona.scratch, "nun_protected", False) and nun_protection_cards(persona))


def describe_card(card):
    role = card_role(card)
    owner = card_owner(card)
    if owner:
        return f"{owner}'s {role} card"
    return f"{role} card"


def describe_card_for_persona(persona, card):
    obfuscated_cards = set(getattr(persona.scratch, "baron_obfuscated_trophy_cards", set()) or set())
    if card in obfuscated_cards and card in set(getattr(persona.scratch, "cards_slot", set()) or set()):
        role = card_role(card)
        role_text = f" ({role})" if role else ""
        return f"an unidentified trophy card{role_text} taken from another Baron's pile"
    return describe_card(card)


def iter_known_personas(room=None, fallback_persona=None):
    seen = {}
    if room is not None:
        for persona in getattr(room, "personas", {}).values():
            if persona is not None:
                seen[persona.scratch.name] = persona
        for table in getattr(room, "locations", {}).values():
            for persona in getattr(table, "personas", {}).values():
                if persona is not None:
                    seen[persona.scratch.name] = persona
    if fallback_persona is not None:
        seen[fallback_persona.scratch.name] = fallback_persona
    return seen


def find_role_card_holder(room, role, owner_name, fallback_persona=None):
    target_card = card_id(role, owner_name)
    legacy_match = None
    for holder_name, holder in iter_known_personas(room, fallback_persona).items():
        cards = set(getattr(holder.scratch, "cards_slot", set()) or set())
        if target_card in cards:
            return holder_name, holder, target_card
        if role in cards and legacy_match is None:
            legacy_match = (holder_name, holder, role)
    if legacy_match:
        return legacy_match
    return None, None, target_card


def role_card_custody_reason(owner_persona, holder_persona, held_card):
    if holder_persona is None:
        return "missing or unknown"
    owner_name = owner_persona.scratch.name
    holder_name = holder_persona.scratch.name
    if holder_name == owner_name:
        return "in your own hand"
    if held_card in nun_protection_cards(holder_persona):
        return f"given by you to {holder_name} as Nun protection"
    if holder_persona.scratch.role == "Baron":
        return f"stolen by the Baron {holder_name}"
    return f"held by {holder_name} for an unclear or legacy reason"


def baron_stolen_claim(persona, role=None):
    role = role or persona.scratch.role
    claims = getattr(persona.scratch, "baron_stolen_card_claims", {}) or {}
    raw_claim = claims.get(role)
    if not raw_claim:
        return None
    if isinstance(raw_claim, dict):
        return {
            "initial_baron": raw_claim.get("initial_baron") or raw_claim.get("baron") or raw_claim.get("holder"),
        }
    return {
        "initial_baron": str(raw_claim),
    }


def set_baron_stolen_claim(persona, role, baron_name):
    persona.scratch.baron_stolen_card_claims[role] = {
        "initial_baron": baron_name,
    }


def own_role_card_custody(persona, room=None):
    role = persona.scratch.role
    owner_name = persona.scratch.name
    holder_name, holder, held_card = find_role_card_holder(room, role, owner_name, persona)
    return {
        "role": role,
        "owner": owner_name,
        "holder": holder_name,
        "holder_persona": holder,
        "card": held_card,
        "in_own_hand": holder_name == owner_name,
        "reason": role_card_custody_reason(persona, holder, held_card),
    }


def own_role_card_custody_text(persona, room=None):
    custody = own_role_card_custody(persona, room)
    role = custody["role"]
    holder = custody["holder"]
    if custody["in_own_hand"]:
        return f"Your own {role} card is currently in your hands."
    claim = baron_stolen_claim(persona, role)
    known_baron = claim.get("initial_baron") if claim else None
    holder_persona = custody.get("holder_persona")
    if not holder_persona and holder:
        holder_persona = iter_known_personas(room, persona).get(holder)
    if (
        holder_persona is not None
        and custody["card"] in nun_protection_cards(holder_persona)
    ):
        return (
            f"Your own {role} card is currently held by {holder} because you willingly gave it to them as Nun protection. "
            f"It was not stolen, even if {holder}'s assigned role is Baron. You still have the {role} role and win condition, "
            f"but you cannot reveal or use your own {role} card until you retrieve it from {holder}."
        )
    if known_baron or (holder_persona is not None and holder_persona.scratch.role == "Baron"):
        known_baron = known_baron or holder
        return (
            f"Your own {role} card was last known to have been stolen by the Baron {known_baron}. "
            "Its exact current holder is not guaranteed by the system and may have changed through later swaps, steals, or retrievals. "
            "rely on your memories, public events, current observations, and failed/successful retrieval attempts. "
            f"You still have the {role} role and win condition, but you cannot reveal or use your own {role} card unless it is actually returned or retrieved."
        )
    if holder:
        return (
            f"Your own {role} card is currently held by {holder}; reason: {custody['reason']}. "
            f"You still have the {role} role and win condition, but you cannot reveal or use your own "
            f"{role} card unless it is returned or retrieved."
        )
    return (
        f"Your own {role} card is not found in any known card slot; treat it as unavailable. "
        f"You still have the {role} role and win condition, but you cannot reveal or use your own "
        f"{role} card unless it is recovered."
    )


def game_end_time():
    return max(TIMERS.values())


def farmer_clergy_requirement():
    return 3 if GAME_MODE == "16" else 2


def nun_commoner_win_requirement():
    return 5 if GAME_MODE == "16" else 3


def baron_trophy_requirement():
    return 4 if GAME_MODE == "16" else 3


def role_family_terms():
    terms = {
        "nobility", "noble", "nobles",
        "commoner", "commoners",
        "clergy", "cleric", "clerics",
    }
    for role in ROLE_DICT.keys():
        role_lower = role.lower()
        terms.add(role_lower)
        if role_lower.endswith("y"):
            terms.add(f"{role_lower[:-1]}ies")
        elif role_lower.endswith("f"):
            terms.add(f"{role_lower[:-1]}ves")
        else:
            terms.add(f"{role_lower}s")
    terms.update({"thieves"})
    families = {role_data["family"] for role_data in ROLE_DICT.values()}
    for locale in available_locales():
        for role in ROLE_DICT:
            terms.add(display_name("role", role, locale=locale).casefold())
            terms.add(display_name("role_card", role, locale=locale).casefold())
        for family in families:
            terms.add(display_name("family", family, locale=locale).casefold())
    return terms


_CJK_PATTERN = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)
_HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def contains_cjk(text):
    return bool(_CJK_PATTERN.search(str(text or "")))


def compact_cjk_spacing(text):
    """Ignore identity-only Japanese name spaces during natural-text matching."""
    return re.sub(r"\s+", "", str(text or "").casefold())


def contains_localized_term(haystack, term):
    """Match Latin terms by word boundaries and CJK terms by compact text."""
    term = str(term or "").strip().casefold()
    if not term:
        return False
    haystack = str(haystack or "").casefold()
    if contains_cjk(term):
        compact_term = compact_cjk_spacing(term)
        compact_haystack = compact_cjk_spacing(haystack)
        if len(compact_term) == 1 and _HAN_PATTERN.fullmatch(compact_term):
            return re.search(
                rf"(?<![\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])"
                rf"{re.escape(compact_term)}"
                rf"(?![\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])",
                compact_haystack,
            ) is not None
        return compact_term in compact_haystack
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", haystack) is not None


def matches_localized_event_template(text, key):
    """Match rendered event text against any installed locale's template."""
    text = str(text or "").strip()
    for locale in available_locales():
        template = tr(key, locale=locale).strip()
        pattern = re.escape(template)
        pattern = re.sub(r"\\\{[^{}]+\\\}", r".+?", pattern)
        if re.fullmatch(pattern, text, flags=re.DOTALL):
            return True
    return False


def casual_conversation_transition_time():
    regular_table_timers = [
        timer
        for table_name, timer in TIMERS.items()
        if table_name != "Wilderness"
    ]
    if not regular_table_timers:
        return datetime.timedelta(0)
    return min(regular_table_timers) * 3 / 4


def casual_conversation_active(persona_or_room):
    room = getattr(persona_or_room, "room", persona_or_room)
    mode = getattr(room, "conversation_mode", "strategic")
    if mode == "ultra_casual":
        return True
    if mode != "casual":
        return False
    scratch = getattr(persona_or_room, "scratch", None)
    curr_time = getattr(scratch, "curr_time", None)
    if curr_time is not None:
        return curr_time < casual_conversation_transition_time()
    return not any(
        table.timer_expired
        for table_name, table in getattr(room, "locations", {}).items()
        if table_name != "Wilderness"
    )


def conversation_posture_prompt(persona):
    room = getattr(persona, "room", None)
    mode = getattr(room, "conversation_mode", "strategic")
    if casual_conversation_active(persona):
        posture_heading = (
            "CONVERSATIONAL POSTURE — ULTRA CASUAL, ENTIRE GAME:\n"
            if mode == "ultra_casual"
            else "CONVERSATIONAL POSTURE — CASUAL, EARLY GAME:\n"
        )
        return (
            posture_heading
            + "Treat the social-deduction game as the reason everyone is gathered, not as the only worthwhile subject or an objective that must dominate every turn. "
            "Ordinary social impulses are real goals: continue an interesting topic, joke, tease, argue, gossip, complain, tell a story, ask something personal, sit in an awkward silence, or react to someone's personality. "
            "A good conversational continuation can deserve as much urgency as a tactical remark. Do not append a role accusation or game question to an otherwise casual line merely to make it useful. "
            "Casual does not mean friendly or frivolous; remain fully in character. Immediate threats, direct questions, formal game events, forced reactions, and genuinely urgent mechanical opportunities still override this posture."
        )
    if mode == "casual":
        return (
            "CONVERSATIONAL POSTURE — STRATEGIC, LATE IN THE FIRST TABLE TIMER:\n"
            "Three quarters of the earliest-expiring table timer has elapsed, so the game and its consequences may now take priority, though established interpersonal threads can still color what you say and do."
        )
    return (
        "CONVERSATIONAL POSTURE — STRATEGIC:\n"
        "Treat the social-deduction game and your character's win condition as central objectives, while still speaking naturally and allowing personality or interpersonal reactions to matter."
    )


def heuristic_poignancy_score(persona, event_type, description, subject=None, obj=None, keywords=None):
    """Deterministic game-aware memory importance score from 1 to 10."""
    if isinstance(persona, str):
        persona_name = persona
    else:
        persona_name = getattr(getattr(persona, "scratch", None), "name", None)
    keywords = set(keywords or [])
    text = str(description or "")
    text_without_audience = text.split("[People physically present", 1)[0]
    lower = text_without_audience.lower()
    subject_text = str(subject or "")
    object_text = str(obj or "")

    if event_type == "chat":
        return deterministic_chat_poignancy_score(
            persona,
            description,
            subject,
            obj,
            keywords=keywords,
        )

    if "is idle" in lower or matches_localized_event_template(
        text_without_audience,
        "event.table.stays_quiet",
    ):
        return 1
    if (
        subject_text.lower() == "system"
        and (
            "the table falls quiet" in lower
            or "no action bid was strong enough" in lower
            or "everyone is still waiting for space to speak" in lower
            or matches_localized_event_template(
                text_without_audience,
                "event.table.no_action",
            )
        )
    ):
        return 1

    high_proof_patterns = [
        r"\breveals?\b.*\bcard\b",
        r"\battempts? to use\b",
        r"\buses?\b.*\bability\b",
        r"\bforces?\b.*\breveal\b",
        r"\bblocks?\b",
        r"\bsteals?\b",
        r"\blocks? down\b",
        r"\bforcefully swaps?\b",
        r"\bretrieves?\b.*\bcard\b",
        r"\bgives?\b.*\bcard\b",
    ]
    movement_patterns = [
        r"\bleaves for\b",
        r"\barrives from\b",
    ]
    is_movement = (
        any(re.search(pattern, lower) for pattern in movement_patterns)
        or matches_localized_event_template(text_without_audience, "event.movement.departure")
        or matches_localized_event_template(text_without_audience, "event.movement.arrival")
    )
    canonical_role_keywords = {
        role.casefold() for role in ROLE_DICT
    } | {
        role_data["family"].casefold() for role_data in ROLE_DICT.values()
    }
    keyword_tokens = {
        str(keyword).casefold()
        for keyword in (keywords | event_role_keywords_from_text(text_without_audience))
    }
    has_proof_or_ability = (
        any(re.search(pattern, lower) for pattern in high_proof_patterns)
        or bool(keyword_tokens & canonical_role_keywords)
    )

    if is_movement and not has_proof_or_ability:
        return 1

    if persona_name:
        direct_participants = {subject_text, object_text}
        directly_named = contains_localized_term(lower, persona_name)
        directly_involved = persona_name in direct_participants
        if event_type != "chat" and persona_name in keywords:
            directly_involved = True
        if directly_involved or directly_named:
            return 10

    if has_proof_or_ability:
        return 7

    roles_and_families = role_family_terms()
    role_pattern = "|".join(re.escape(term.lower()) for term in sorted(roles_and_families, key=len, reverse=True))
    unproven_reveal = (
        event_type == "chat"
        and (
            (re.search(r"\bclaim(?:s|ed|ing)?\b", lower) and re.search(role_pattern, lower))
            or (re.search(r"\breveal(?:s|ed|ing)?\b", lower) and "card" not in lower)
            or re.search(rf"\b(i am|i'm|im|my family is|my role is|am of the)\b[^.\n]*\b({role_pattern})\b", lower)
        )
    )
    if unproven_reveal:
        return 4

    if "practically screaming" in lower:
        return 5
    if event_type == "event":
        return 3
    if event_type == "thought":
        return 3
    return 2


def deterministic_chat_poignancy_score(
    persona,
    description,
    subject=None,
    obj=None,
    keywords=None,
):
    """Cheap deterministic importance score for dialogue memories."""
    if isinstance(persona, str):
        persona_name = persona
        all_names = {persona_name}
    else:
        scratch = getattr(persona, "scratch", None)
        persona_name = getattr(scratch, "name", "") or ""
        room = getattr(persona, "room", None)
        all_names = set(getattr(room, "personas", {}).keys()) if room else {persona_name}
        all_names.add(persona_name)

    text = str(description or "")
    text = text.split("[People physically present", 1)[0]
    text = re.sub(r"\baudience=\[[^\]]*\]", "", text)
    body = text
    match = re.search(r"\((?:whisper|calm|loud|practically screaming)(?:,[^)]*)?\)\s*(.*)", body, flags=re.IGNORECASE | re.DOTALL)
    if match:
        body = match.group(1)
    elif ": " in body:
        body = body.rsplit(": ", 1)[-1]

    body_lower = body.lower()
    subject_text = str(subject or "")
    object_text = str(obj or "")

    roles_and_families = role_family_terms()
    canonical_role_keywords = {
        role.casefold() for role in ROLE_DICT
    } | {
        role_data["family"].casefold() for role_data in ROLE_DICT.values()
    }
    keyword_tokens = {str(keyword).casefold() for keyword in (keywords or set())}

    def name_aliases(name):
        name = str(name or "").strip()
        aliases = {name}
        if contains_cjk(name):
            aliases.add(compact_cjk_spacing(name))
            return {alias for alias in aliases if alias}
        parts = re.split(r"\s+", name)
        aliases.update(part for part in parts if len(part) >= 3)
        return {alias for alias in aliases if alias}

    has_role_or_family = (
        bool(keyword_tokens & canonical_role_keywords)
        or any(contains_localized_term(body_lower, term) for term in roles_and_families)
    )
    own_name_mentioned = bool(persona_name) and (
        any(contains_localized_term(body_lower, alias) for alias in name_aliases(persona_name))
        or object_text == persona_name
    )

    other_names_mentioned = False
    for name in all_names:
        if not name or name == persona_name:
            continue
        if any(contains_localized_term(body_lower, alias) for alias in name_aliases(name)):
            other_names_mentioned = True
            break

    if casual_conversation_active(persona):
        if own_name_mentioned and has_role_or_family:
            return 5
        if own_name_mentioned:
            return 4
        if other_names_mentioned and has_role_or_family:
            return 4
        if other_names_mentioned:
            return 3
        if has_role_or_family:
            return 3
        return 2

    if own_name_mentioned and has_role_or_family:
        return 9
    if other_names_mentioned and has_role_or_family:
        return 8
    if has_role_or_family:
        return 5
    if own_name_mentioned:
        return 4
    if other_names_mentioned:
        return 3
    return 2


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


def compact_summary_text(value, fallback=""):
    # Keep whitespace normalization, but do not truncate generated reasoning.
    # Length policy is handled by the language-aware prompts.
    return " ".join(str(value or fallback or "").split())


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


def set_dialogue_log_path(path, log_dir=None, character_names=None):
    global DIALOGUE_LOG_PATH
    DIALOGUE_LOG_PATH = Path(path)
    DIALOGUE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DIALOGUE_LOG_PATH, "a", encoding="utf-8") as outfile:
        outfile.write(
            tr(
                "log.table_started",
                timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
            )
            + "\n"
        )
    if log_dir:
        set_advanced_log_dirs(Path(log_dir), character_names=character_names)


def set_clean_dialogue_log_path(path):
    global CLEAN_DIALOGUE_LOG_PATH
    CLEAN_DIALOGUE_LOG_PATH = Path(path)
    CLEAN_DIALOGUE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLEAN_DIALOGUE_LOG_PATH.touch(exist_ok=True)


def set_debug_log_path(path):
    global DEBUG_LOG_PATH
    DEBUG_LOG_PATH = Path(path)
    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEBUG_LOG_PATH, "a") as outfile:
        outfile.write(f"# Three Estates debug log started at {datetime.datetime.now().isoformat(timespec='seconds')}\n")


def set_advanced_log_dirs(log_dir, character_names=None):
    global TABLE_LOG_DIR, CHARACTER_LOG_DIR
    TABLE_LOG_DIR = Path(log_dir) / "tables"
    CHARACTER_LOG_DIR = Path(log_dir) / "characters"
    TABLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    configure_character_logs(character_names or [])


def safe_log_filename(name):
    normalized = unicodedata.normalize("NFC", str(name))
    return re.sub(r"[^\w.-]+", "_", normalized).strip("_.-") or "unknown"


def configure_character_logs(character_names):
    global CHARACTER_LOG_NAMES, CHARACTER_LOG_FILENAMES
    CHARACTER_LOG_NAMES = {
        str(name) for name in character_names if str(name).strip()
    }
    CHARACTER_LOG_FILENAMES = {}
    used_filenames = {}
    for name in sorted(CHARACTER_LOG_NAMES):
        filename = safe_log_filename(name)
        if filename in used_filenames and used_filenames[filename] != name:
            suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
            filename = f"{filename}_{suffix}"
        used_filenames[filename] = name
        CHARACTER_LOG_FILENAMES[name] = filename


def character_log_path(character):
    filename = CHARACTER_LOG_FILENAMES.get(str(character))
    if CHARACTER_LOG_DIR is None or filename is None:
        return None
    return CHARACTER_LOG_DIR / f"{filename}.log"


def append_table_specific_log(table_name, line):
    if TABLE_LOG_DIR is None:
        return
    with open(TABLE_LOG_DIR / f"{safe_log_filename(table_name)}.log", "a") as outfile:
        outfile.write(line + "\n")


def append_all_table_specific_logs(line, exclude_table=None):
    if TABLE_LOG_DIR is None:
        return
    for table_log in sorted(TABLE_LOG_DIR.glob("*.log")):
        if exclude_table and table_log.stem == safe_log_filename(exclude_table):
            continue
        with open(table_log, "a") as outfile:
            outfile.write(line + "\n")


def append_character_specific_log(characters, line):
    if CHARACTER_LOG_DIR is None:
        return
    targets = CHARACTER_LOG_NAMES & {
        str(character) for character in characters if character
    }
    for character in sorted(targets):
        with open(character_log_path(character), "a", encoding="utf-8") as outfile:
            outfile.write(line + "\n")


def append_all_character_specific_logs(line, exclude_characters=None):
    if CHARACTER_LOG_DIR is None:
        return
    exclude_names = {str(character) for character in (exclude_characters or [])}
    for character in sorted(CHARACTER_LOG_NAMES):
        if character in exclude_names:
            continue
        with open(character_log_path(character), "a", encoding="utf-8") as outfile:
            outfile.write(line + "\n")


def debug_log(message):
    if not debug:
        return
    print(message)
    if DEBUG_LOG_PATH is None:
        return
    with open(DEBUG_LOG_PATH, "a") as outfile:
        outfile.write(message + "\n")


def write_table_event_log(table_name, event_tuple):
    if DIALOGUE_LOG_PATH is None and CLEAN_DIALOGUE_LOG_PATH is None:
        return
    if len(event_tuple) == 6:
        subject, obj, description, timestamp, keywords, audience = event_tuple
        audience = set(audience or [])
    else:
        subject, obj, description, timestamp, keywords = event_tuple
        audience = None
    subject = subject or "system"
    obj = obj or "everyone"
    subject_label = display_name("event_actor", subject)
    if obj in {"Nobility", "Commoners", "Clergy"}:
        obj_label = display_name("family", obj)
    else:
        obj_label = display_name("dialogue_target", obj)
    keyword_text = ", ".join(sorted(str(keyword) for keyword in keywords)) if keywords else ""
    table_label = display_name("table", table_name)
    event_label = tr("log.event")
    if DIALOGUE_LOG_PATH is not None:
        with open(DIALOGUE_LOG_PATH, "a", encoding="utf-8") as outfile:
            outfile.write(f"[{timestamp}] {event_label} ({table_label}) {subject_label} -> {obj_label}: {description}")
            if keyword_text:
                outfile.write(f" | keywords={keyword_text}")
            outfile.write("\n")
    advanced_line = f"[{timestamp}] {event_label} ({table_label}) {subject_label} -> {obj_label}: {description}"
    if keyword_text:
        advanced_line += f" | keywords={keyword_text}"
    append_table_specific_log(table_name, advanced_line)
    character_log_targets = set(audience) if audience is not None else set(keywords or []) | {subject, obj}
    if subject and f"departing Spinster {subject}" in description:
        character_log_targets.discard(subject)
    append_character_specific_log(character_log_targets, advanced_line)
    if CLEAN_DIALOGUE_LOG_PATH is not None:
        with open(CLEAN_DIALOGUE_LOG_PATH, "a", encoding="utf-8") as outfile:
            outfile.write(f"[{timestamp}] {event_label} ({table_label}): {description}\n")


def normalize_dialogue_expression(expression):
    words = str(expression or "neutral").strip().split()
    return " ".join(words[:3]) or "neutral"


def compact_profile_field(value, max_characters):
    value = " ".join(str(value or "").strip().split()).rstrip(".")
    if len(value) <= max_characters:
        return value
    shortened = value[:max_characters].rstrip()
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    return shortened.rstrip(" ,.;:")


def visual_character_label(persona):
    name = str(getattr(getattr(persona, "scratch", None), "name", None) or getattr(persona, "name", "Unknown"))
    appearance = compact_profile_field(
        getattr(getattr(persona, "scratch", None), "innate_appearance", ""),
        80,
    )
    if not appearance:
        return name
    clothing = compact_profile_field(
        getattr(getattr(persona, "scratch", None), "clothing", ""),
        70,
    )
    label = tr("prompt.visual_appearance", name=name, appearance=appearance)
    if clothing:
        label += tr("prompt.visual_clothing", clothing=clothing)
    return label


def visual_character_label_by_name(room, name):
    persona = getattr(room, "personas", {}).get(name)
    return visual_character_label(persona) if persona is not None else str(name)


def normalize_dialogue_action(action):
    action = str(action or "does nothing").strip().rstrip(".")
    if not action:
        return "does nothing"
    if len(action) > 70:
        shortened = action[:70].rstrip()
        if " " in shortened:
            shortened = shortened.rsplit(" ", 1)[0]
        action = shortened.rstrip(".") or "does nothing"
    return action


def unpack_dialogue_fields(dialogue_tuple):
    if len(dialogue_tuple) == 9:
        speaker, target, volume, expression, action, line, timestamp, audience, keywords = dialogue_tuple
    elif len(dialogue_tuple) == 8:
        speaker, target, volume, expression, action, line, timestamp, keywords = dialogue_tuple
        audience = []
    elif len(dialogue_tuple) == 7:
        speaker, target, volume, line, timestamp, audience, keywords = dialogue_tuple
        expression, action = "neutral", "does nothing"
    elif len(dialogue_tuple) == 6:
        speaker, target, volume, line, timestamp, keywords = dialogue_tuple
        expression, action, audience = "neutral", "does nothing", []
    else:
        raise ValueError(f"Unsupported dialogue record with {len(dialogue_tuple)} fields")
    return (
        speaker,
        target,
        volume,
        normalize_dialogue_expression(expression),
        normalize_dialogue_action(action),
        line,
        timestamp,
        set(audience or []),
        set(keywords or []),
    )


def format_dialogue_payload(action, line):
    return f"({normalize_dialogue_action(action)}) {line}"


_CANONICAL_CARD_ROLES = (
    "Innkeeper",
    "Spinster",
    "Bishop",
    "Priest",
    "Farmer",
    "Baron",
    "Thief",
    "Queen",
    "King",
    "Nun",
)


def localize_transcript_natural_text(text):
    """Localize leaked canonical card names only at transcript render time."""
    rendered = str(text)
    for role in _CANONICAL_CARD_ROLES:
        rendered = re.sub(
            rf"(?<![A-Za-z])\s*{re.escape(role)}\s*(?:card|カード|卡牌|卡|牌)",
            display_name("role_card", role),
            rendered,
            flags=re.IGNORECASE,
        )
    return rendered


def format_transcript_dialogue_payload(action, line):
    action = localize_transcript_natural_text(normalize_dialogue_action(action))
    line = localize_transcript_natural_text(line)
    return f"({action}) {line}"


def write_dialogue_log(table_name, dialogue_tuple):
    if DIALOGUE_LOG_PATH is None and CLEAN_DIALOGUE_LOG_PATH is None:
        return
    speaker, target, volume, expression, action, line, timestamp, audience, _keywords = unpack_dialogue_fields(dialogue_tuple)
    audience_text = ", ".join(sorted(str(player) for player in audience)) if audience else tr("log.unknown")
    rendered_line = format_transcript_dialogue_payload(action, line)
    table_label = display_name("table", table_name)
    volume_label = display_name("volume", volume)
    target_label = display_name("dialogue_target", target)
    dialogue_label = tr("log.dialogue")
    audience_label = tr("log.audience")
    if DIALOGUE_LOG_PATH is not None:
        with open(DIALOGUE_LOG_PATH, "a", encoding="utf-8") as outfile:
            outfile.write(f"[{timestamp}] {dialogue_label} ({table_label}) {speaker} -> {target_label} [{volume_label}, {expression}]: {rendered_line} | {audience_label}=[{audience_text}]\n")
    advanced_line = f"[{timestamp}] {dialogue_label} ({table_label}) {speaker} -> {target_label} [{volume_label}, {expression}]: {rendered_line} | {audience_label}=[{audience_text}]"
    append_table_specific_log(table_name, advanced_line)
    append_character_specific_log(set(audience or []) | {speaker, target}, advanced_line)
    if volume == "practically screaming":
        overheard_rendered_line = localize_transcript_natural_text(line)
        overheard_line = (
            f"[{timestamp}] {dialogue_label} ({tr('log.overheard_from', table=table_label)}) {speaker} -> {target_label} "
            f"[{volume_label}]: {overheard_rendered_line} | {audience_label}=[{audience_text}]"
        )
        append_all_table_specific_logs(overheard_line, exclude_table=table_name)
        append_all_character_specific_logs(overheard_line, exclude_characters=set(audience or []) | {speaker, target})
    if CLEAN_DIALOGUE_LOG_PATH is not None:
        with open(CLEAN_DIALOGUE_LOG_PATH, "a", encoding="utf-8") as outfile:
            outfile.write(f"[{timestamp}] {dialogue_label} ({table_label}) {speaker} -> {target_label} [{volume_label}, {expression}]: {rendered_line} | {audience_label}=[{audience_text}]\n")


def debug_bid(persona, table, action, bid, reasoning):
    if not debug:
        return
    cooldown = ""
    if ENABLE_SPEAKING_COOLDOWN and action == "speak" and persona.scratch.speaking_cooldown > 0:
        cooldown = f" | speaking_cooldown={persona.scratch.speaking_cooldown}"
    debug_log(
        f"[BID] t={persona.scratch.curr_time} | table={table.name} | "
        f"character={persona.scratch.name} | role={persona.scratch.role} | "
        f"action={action} | bid={bid}{cooldown} | reasoning={reasoning}"
    )


def debug_movement(persona, table, requested_option, final_option, reasoning, summary=None):
    if not debug:
        return
    adjusted = ""
    if requested_option != final_option:
        adjusted = f" | adjusted_from={requested_option}"
    summary_text = f" | summary={summary}" if summary else ""
    debug_log(
        f"[MOVE-DECISION] t={persona.scratch.curr_time} | table={table.name} | "
        f"character={persona.scratch.name} | role={persona.scratch.role} | "
        f"option={final_option}{adjusted} | movement_cooldown={persona.scratch.movement_cooldown}{summary_text} | "
        f"reasoning={reasoning}"
    )


def debug_ability_target(persona, table, requested_target, final_target, ability_reasoning="", target_reasoning=""):
    if not debug:
        return
    adjusted = ""
    if requested_target != final_target:
        adjusted = f" | adjusted_from={requested_target}"
    reasoning_text = f" | ability_reasoning={ability_reasoning}" if ability_reasoning else ""
    target_reasoning_text = f" | target_reasoning={target_reasoning}" if target_reasoning else ""
    debug_log(
        f"[ABILITY-TARGET] t={persona.scratch.curr_time} | table={table.name} | "
        f"character={persona.scratch.name} | role={persona.scratch.role} | "
        f"target={final_target}{adjusted}{reasoning_text}{target_reasoning_text}"
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


def role_keywords_from_text(text):
    lower = str(text or "").lower()
    keywords = set()
    for role, role_data in ROLE_DICT.items():
        role_terms = {role.casefold()}
        for locale in available_locales():
            role_terms.add(display_name("role", role, locale=locale).casefold())
            role_terms.add(display_name("role_card", role, locale=locale).casefold())
        if any(contains_localized_term(lower, term) for term in role_terms):
            keywords.add(role)
            keywords.add(role_data["family"])
    for family in {"Nobility", "Commoners", "Clergy"}:
        family_terms = {family.casefold(), family.rstrip("s").casefold()}
        family_terms.update(
            display_name("family", family, locale=locale).casefold()
            for locale in available_locales()
        )
        if any(contains_localized_term(lower, term) for term in family_terms):
            keywords.add(family)
    return keywords


def event_role_keywords_from_text(text):
    lower = str(text or "").lower()
    keywords = set()
    for role, role_data in ROLE_DICT.items():
        role_lower = role.lower()
        role_patterns = [
            rf"\b{re.escape(role_lower)}\s+card\b",
            rf"\breveals?\s+(?:his|her|their|the)?\s*{re.escape(role_lower)}\b",
            rf"\brevealed\s+as\s+(?:the\s+)?{re.escape(role_lower)}\b",
            rf"\bclaims?\s+(?:to\s+be\s+)?(?:the\s+)?{re.escape(role_lower)}\b",
            rf"\bis\s+(?:now\s+)?(?:the\s+)?{re.escape(role_lower)}\b",
        ]
        if any(re.search(pattern, lower) for pattern in role_patterns):
            keywords.add(role)
            keywords.add(role_data["family"])
        localized_role_terms = set()
        for locale in available_locales():
            localized_role_terms.add(display_name("role", role, locale=locale).casefold())
            localized_role_terms.add(display_name("role_card", role, locale=locale).casefold())
        if any(
            contains_localized_term(lower, term)
            for term in localized_role_terms
        ):
            keywords.add(role)
            keywords.add(role_data["family"])
    for family in {"Nobility", "Commoners", "Clergy"}:
        family_lower = family.lower()
        family_singular = family_lower.rstrip("s")
        family_patterns = [
            rf"\bfamily\s+(?:as|is|of)\s+(?:the\s+)?{re.escape(family_lower)}\b",
            rf"\b{re.escape(family_lower)}\s+family\b",
            rf"\ball\s+(?:present\s+)?{re.escape(family_lower)}\b",
            rf"\bthe\s+{re.escape(family_lower)}\b",
            rf"\b{re.escape(family_singular)}\s+claim\b",
        ]
        if any(re.search(pattern, lower) for pattern in family_patterns):
            keywords.add(family)
        localized_family_terms = {
            display_name("family", family, locale=locale).casefold()
            for locale in available_locales()
        }
        if any(
            contains_localized_term(lower, term)
            for term in localized_family_terms
        ):
            keywords.add(family)
    return keywords


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
        return families_at_table["Clergy"] >= farmer_clergy_requirement()
    if role == "Innkeeper":
        return families_at_table["Nobility"] >= 2
    if role == "Baron":
        return len(held_trophy_cards(player)) >= baron_trophy_requirement()
    if role == "Nun":
        if adjusted_results is None:
            return False
        return sum(
            1 for name, result in adjusted_results.items()
            if result and role_family(locations_to_player(final_tables)[name].scratch.role) == "Commoners"
        ) >= nun_commoner_win_requirement()
    if role == "Thief":
        if adjusted_results is None:
            return False
        village_non_thieves = [
            name
            for name, village_player in final_tables["Village"].items()
            if village_player.scratch.role != "Thief"
        ]
        return all(not adjusted_results.get(name, False) for name in village_non_thieves)
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
