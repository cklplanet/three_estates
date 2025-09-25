import datetime

# Copy and paste your OpenAI API Key
OPENROUTER_KEY = "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"
# Put your name
key_owner = "<Name>"

maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"

save_file = "/Users/cklplanet/Desktop/work2/three_estates/three_estates_sim/sessions/kancolle1"

collision_block_id = "32125"

# Verbose 
debug = True


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