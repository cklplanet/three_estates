# Three Estates

Three Estates is a terminal-driven social-deduction simulator in which LLM-powered characters move between tables, converse, reveal information, use role abilities, form memories, and pursue individual win conditions.

The simulator supports a 10-player base ruleset and a 16-player expanded ruleset. Each agent acts from incomplete information: it knows its own role and history, perceives activity at its current table, and can only overhear remote dialogue when the line is sufficiently loud. Retrieved memories, relationships, current game state, and table-specific timers are assembled into the prompts that drive each decision.

> **Status:** Active experimental project. Running a full game makes many external LLM calls and may incur meaningful API costs.

## Highlights

- **Up to 16 autonomous agents** with individual roles, abilities, families, and win conditions.
- **RAG-assisted memory** using sentence embeddings, associative memory, recency/relevance scoring, and generated reflections.
- **Partial observability** based on seating, movement, dialogue volume, and who was physically present for an event.
- **Autonomous game loop** covering departures, action bidding, arrivals, role reveals, ability resolution, table lockdowns, and endgame scoring.
- **Persistent character continuity** through reusable character profiles, directional relationships, game-specific context, and archived post-game summaries.
- **Resumable execution** with stable game-state checkpoints, phase snapshots, and granular checkpoints throughout character generation.
- **Configurable conversation styles:** strategic, casual-to-strategic, and ultra-casual.
- **Separate model routing** for character generation, game reasoning, dialogue, poignancy scoring, and post-game writing.
- **Structured output and debugging** through full logs, clean dialogue logs, per-table/per-character logs, game summaries, and visual-novel-style epilogues.

## How a Game Works

Characters begin at the Castle, Forest, Village, and—under the expanded ruleset—Wilderness. During each simulated timestep:

1. Agents decide whether to remain at their current table or depart.
2. Eligible actions compete through an internal bidding system.
3. Selected dialogue, reveals, role abilities, and reactions resolve.
4. Characters in transit arrive and perceive eligible dialogue from their destination.
5. Memories and reflections are updated before the next phase.

Each main table has its own deadline. Once a table's timer expires, its occupants are locked in place. The agents must balance conversation, information gathering, deception, movement, and role-specific objectives before the game ends.

## What the Game Is Designed to Explore

Three Estates is not built around two permanent teams or a single shared victory condition. Every character has an independently evaluated objective, and those objectives overlap only partially. The resulting game is meant to produce:

- **Temporary alliances:** characters can coordinate movement, exchange information, protect one another, or help assemble a mutually favorable final table.
- **Cross-family cooperation:** sharing a family does not guarantee compatible objectives, while characters from different families may benefit from working together.
- **Negotiation and bargaining:** a character may trade truthful information, promises, protection, card access, or help with positioning.
- **Deception and betrayal:** soft claims, selective truths, false alliances, and last-minute departures can all be rational when objectives diverge.
- **Information asymmetry:** conversations are local to tables, remote speech is only partially audible, and memories reflect what each character personally perceived.
- **Changing incentives:** stolen or transferred cards, role swaps, timer lockdowns, and revealed information can alter which alliances remain useful.

The role families—Nobility, Clergy, and Commoners—organize abilities and some deductions, but they are not fixed teams. A player wins or loses according to their current individual role at the end of the game.

## Roles, Abilities, and Win Conditions

The 10-player base game contains exactly one of each role. A player's **role**, **family**, and **win condition** are distinct from the physical location of their role card. Losing a card can prevent a reveal or ability without changing who that player currently is; a successful Thief swap is the principal way roles and win conditions themselves change hands.

| Role | Family | Ability | Win condition |
| --- | --- | --- | --- |
| **King** | Nobility | While seated, chooses a family currently represented at the table. Players of that family who were already seated cannot leave until the King or another unaffected player leaves. The King can still depart when locking Nobility, but doing so breaks the lock. | Wins if no more than one Commoner is in the Castle. |
| **Queen** | Nobility | When leaving, may choose another player who must follow to the same destination. That player remains locked there until the Queen or another player leaves. Immunities and stronger locks can prevent the drag. | Wins either in the Castle without a seated King or in the Village with at least one seated Priest. Loose King or Priest cards do not count as those roles being present. |
| **Baron** | Nobility | When another player reveals their own role card at a table of at least three people, may reveal as Baron, block an associated ability, and steal the revealed card. A merely voluntary reveal remains public even if its card is stolen. The Baron gains neither the stolen role nor its ability. | Wins while holding at least three cards other than the Baron's own card, including willingly granted Nun cards. |
| **Bishop** | Clergy | After another player leaves, may guess the family of a remaining player. A correct guess forces that target to leave; an incorrect guess lets the target decide how much, if anything, to reveal in response. | Wins if no Nobles are seated at the Bishop's final table. |
| **Priest** | Clergy | When alone with exactly one other player, may inspect that player's role. The attempt fails if the target no longer possesses their own role card. | Wins if no more than one person is in the Forest. |
| **Nun** | Clergy | When alone with exactly one other player, may give that player the Nun card. Its holder is protected from most hostile abilities until the card is returned, and must return a Nun's own card when that Nun requests it. | Wins if at least three Commoners win. |
| **Spinster** | Commoners | When leaving the Forest, may mark one player remaining there. After the Spinster departs, that player must reveal their role to everyone else still in the Forest. | At game end, guesses every other role at the Spinster's final table. If every guess is correct, the win/loss results of all other players at that table are reversed. |
| **Farmer** | Commoners | Immune to most other role abilities. Exceptions include receiving Nun protection, direct reveals caused by Priest or Spinster, and the Spinster's endgame reversal. The Farmer may reveal the Farmer card when proof of immunity is required. | Wins if seated with at least two Clergy members. |
| **Thief** | Commoners | When alone with exactly one other player, may swap roles and win conditions with that player. A Thief cannot swap with someone who lacks their own role card, cannot target another Thief, and cannot immediately reverse the same one-on-one swap before the table state changes. | Wins if every non-Thief in the Village loses, or if no such player exists. |
| **Innkeeper** | Commoners | Upon entering the Village from another table, may reveal and declare as Innkeeper. If activated, nobody can leave the Village until the Innkeeper leaves or another player enters. Merely starting in or remaining in the Village does not activate it. | Wins if seated with at least two Nobles. |

### Expanded 16-player rules

The expanded mode adds the Wilderness as a fourth table and uses this role distribution:

| Role | Count | Expanded-mode change |
| --- | ---: | --- |
| King, Queen, Spinster, Bishop, Innkeeper | 1 each | Same ability and threshold as the base game |
| Priest | 2 | Same ability and win condition |
| Nun | 2 | Protection can stack; a holder remains protected while retaining at least one granted Nun card. Each Nun wins if at least five Commoners win. |
| Farmer | 3 | Each Farmer requires at least three Clergy members at the final table. |
| Thief | 2 | Thieves remain immune to Thief swaps. |
| Baron | 2 | A Baron may block another eligible Baron and steal that Baron's accumulated trophy cards, but never the other Baron's own Baron card. Each Baron requires at least four trophy cards to win. |

No win condition directly names the Wilderness. Its purpose is to create additional routing, negotiation, and temporary-alliance possibilities before the main tables close.

## Requirements

- Python 3.9 or newer
- An [OpenRouter](https://openrouter.ai/) API key
- Internet access on first run to download the `all-MiniLM-L6-v2` sentence-transformer model
- Access through OpenRouter to the model IDs configured in your environment file

## Quick Start

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/cklplanet/three_estates.git
cd three_estates
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your local configuration:

```bash
cp .env.example .env.local
```

At minimum, edit `.env.local` and provide:

```dotenv
OPENROUTER_KEY=YOUR_API_KEY_HERE
THREE_ESTATES_SESSION_NAME=my_first_game
```

Review the configured model IDs in the same file and replace them when necessary with models available to your OpenRouter account.

Start the simulator from the repository root:

```bash
python3 three_estates_sim/server.py
```

The terminal will guide you through game size, character generation, conversation style, appearance/context options, relationships, and seating. Existing session directories can be continued, reused with the same or rerolled roles, replayed from an exact setup, or archived in favor of a new cast.

## Configuration

The application reads ordinary environment variables first, followed by `.env.local` and `.env`. See [`.env.example`](.env.example) for the complete starter configuration.

Frequently adjusted settings include:

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_KEY` | API key used for LLM requests |
| `THREE_ESTATES_SESSION_NAME` | Session directory name under `three_estates_sim/sessions/` |
| `THREE_ESTATES_SESSION_DIR` | Optional absolute path overriding the session-name directory |
| `THREE_ESTATES_GAME_MODE` | Default ruleset: `10` or `16` |
| `THREE_ESTATES_CHARACTER_MODEL` | Character profile and cast generation |
| `THREE_ESTATES_GAME_MODEL` | Movement, bidding, abilities, and strategic reasoning |
| `THREE_ESTATES_DIALOGUE_MODEL` | Spoken-line, action, and expression generation |
| `THREE_ESTATES_POIGNANCY_MODEL` | LLM-based memory-importance scoring |
| `THREE_ESTATES_EPILOGUE_MODEL` | Post-game summary and epilogue generation |
| `THREE_ESTATES_SECONDS_PER_PHASE` | Simulated time advanced during ordinary strategic phases |
| `THREE_ESTATES_CASUAL_SECONDS_PER_PHASE` | Simulated time advanced during casual phases |
| `THREE_ESTATES_SERVER_SLEEP_SECONDS` | Real-time delay between simulation phases |
| `THREE_ESTATES_USE_LLM_CHAT_POIGNANCY_SCORING` | Enables LLM scoring in strategic play; casual conversation uses it by default |
| `THREE_ESTATES_ALLOW_SPEECH_REASONING` | Allows the dialogue model's default reasoning behavior |

Reducing the real-time sleep value makes games finish faster but may increase the rate at which API requests and filesystem checkpoints occur.

## Sessions and Outputs

By default, a named run is stored under:

```text
three_estates_sim/sessions/<THREE_ESTATES_SESSION_NAME>/
```

A session can contain:

- Character scratch state and associative memory
- `character_context.json`, including reusable context and post-game summaries
- `session_state.json`, the authoritative resume checkpoint
- Immutable phase snapshots
- Full, clean, table-specific, and character-specific dialogue logs
- A generated post-game epilogue

Session directories and `.env.local` are intentionally ignored by Git because they may contain private prompts, generated dialogue, and credentials.

## Project Layout

```text
three_estates_sim/
├── server.py                         # Main entry point
├── backend_server/
│   ├── server.py                     # Simulation orchestration and persistence
│   ├── room.py                       # Tables, movement, and shared world state
│   ├── utils.py                      # Rules, roles, timers, and configuration
│   └── persona/
│       ├── persona.py                # Agent actions and role abilities
│       ├── cognitive_modules/        # Perception, retrieval, planning, reflection
│       ├── memory_structures/        # Scratch and associative memory
│       └── prompt_template/          # Prompt assembly and templates
└── sessions/                         # Local generated state; ignored by Git
```

## Design Notes

- The simulation is intentionally **agent-centric**, not omniscient. Memory records reflect what a character could actually perceive.
- Dialogue generation returns structured speech, expression, and physical-action fields.
- Different model roles can be tuned independently to trade off quality, latency, and cost.
- Post-game summaries are archived for reference without automatically bloating subsequent runtime prompts.
- Character-generation and phase checkpoints are written atomically so interrupted runs can resume without regenerating completed work.

## Acknowledgements

Three Estates was partially adapted from ideas and implementation patterns presented in:

- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)
- [Werewolf Arena: A Case Study in LLM Evaluation via Social Deduction](https://arxiv.org/abs/2407.13943)

Special thanks to **Nathanaël Lambert (EPFL Digital Humanities)** and **André Da Gloria Santiago (EPFL Digital Humanities)** for the original social-deduction game concept on which this project builds.

This repository is an independently developed extension and is not an official EPFL project.
