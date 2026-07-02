"""
Direct-keyword-only retrieval for the simple memory fork.

Event and chat history is supplied to prompts through the agent's perfect
runtime transcript (`scratch.recent_conversation`). The only long-term
associative memory in this fork is reflection thoughts, and those are recalled
by exact keyword index lookup.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))


def retrieve(persona, room, self_table_perceived, other_tables_perceived):
    retrieved_self = {}
    retrieved_others = {}
    self_retrieved_lines_related = {}
    other_retrieved_lines_related = {}

    for event in self_table_perceived:
        retrieved_self[event.description] = {
            "curr_event": event,
            "events": [],
            "thoughts": list(persona.a_mem.retrieve_relevant_thoughts(event.subject, event.object)),
        }

    for event in other_tables_perceived:
        retrieved_others[event.description] = {
            "curr_event": event,
            "events": [],
            "thoughts": list(persona.a_mem.retrieve_relevant_thoughts(event.subject, event.object)),
        }

    retrieved_all_tables = {}
    for table_name, table in room.locations.items():
        retrieved_all_tables[table_name] = {}
        for persona_name in table.personas:
            relevant_thoughts = set()
            relevant_thoughts.update(persona.a_mem.retrieve_relevant_thoughts(persona_name, None))
            relevant_thoughts.update(persona.a_mem.retrieve_relevant_thoughts(None, persona_name))
            retrieved_all_tables[table_name][persona_name] = {
                "events": [],
                "thoughts": list(relevant_thoughts),
            }

    return (
        retrieved_self,
        retrieved_others,
        self_retrieved_lines_related,
        other_retrieved_lines_related,
        retrieved_all_tables,
    )
