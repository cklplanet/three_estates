"""
Simplified reflection module.

This fork deliberately avoids RAG-style semantic retrieval and poignancy
thresholds. Agents keep a perfect runtime transcript of what they personally
encountered or overheard, and reflection is triggered only by a count of actual
movement decisions. The only persisted associative-memory nodes are the
reflection thoughts created here.
"""
import datetime
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from global_methods import *
from persona.prompt_template.run_gpt_prompt import *
from persona.prompt_template.gpt_structure import *


def sorted_encountered_nodes(persona):
  return sorted(
    persona.a_mem.seq_event + persona.a_mem.seq_chat,
    key=lambda node: (node.created, node.node_count)
  )


def run_reflect(persona):
  nodes = sorted_encountered_nodes(persona)
  if not nodes:
    return

  room_personas = getattr(getattr(persona, "room", None), "personas", {})
  subjects = set(room_personas.keys())
  for node in nodes:
    subjects.update(keyword for keyword in node.keywords if keyword in room_personas)
    if node.subject:
      subjects.add(node.subject)
    if node.object and node.object in room_personas:
      subjects.add(node.object)

  board_focal_points = [
    "Across the whole board, what can be observed about each player's likely role, family, card status, and public credibility?",
    "Across the whole board, what can be observed about each player's current win condition progress or obstacles?",
    "Across the whole board, what open or hidden alliances, rivalries, bargains, coercion, or relationship patterns are shaping the game?"
  ]
  focal_retrievals = {focal_point: nodes for focal_point in board_focal_points}

  prior_board_thoughts = sorted(
    [thought for thought in persona.a_mem.seq_thought if thought.object == "board"],
    key=lambda thought: thought.created
  )[-5:]
  thought_dict = prompt_dict(
    run_gpt_prompt_reflect_on_board_state(persona, focal_retrievals, prior_board_thoughts),
    {
      "reasoning": "I do not have enough reliable evidence to fully update the board.",
      "summary": "I am still tracking each player's role, win-condition progress, alliances, and rivalries, but the board remains uncertain."
    }
  )
  thought = thought_dict["summary"]
  created = persona.scratch.curr_time
  expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
  keywords = {persona.scratch.name, "board", "roles", "win conditions", "alliances", "rivalries"} | set(subjects)
  for role, role_data in ROLE_DICT.items():
    if role.lower() in thought.lower() or role_data["family"].lower() in thought.lower():
      keywords.add(role)
      keywords.add(role_data["family"])
  persona.a_mem.add_thought(created, expiration, persona.scratch.name, "board",
                            thought, keywords, 9,
                            (thought, None))

  focal_point = f"Given the whole board, my role as {persona.scratch.role}, my card status, and current table state, how close am I, {persona.scratch.name}, to fulfilling my own win condition?"
  my_relevant_thoughts = [
    thought_node for thought_node in persona.a_mem.seq_thought
    if persona.scratch.name in thought_node.keywords or thought_node.object == "board"
  ][-8:]
  thought_dict = prompt_dict(
    run_gpt_prompt_reflect_on_subject(persona, {focal_point: nodes}, my_relevant_thoughts, focal_point),
    {
      "reasoning": "I do not have enough reliable new evidence to update my progress.",
      "summary": "I am still assessing whether my current table helps my win condition."
    }
  )
  persona.scratch.win_progress = thought_dict["summary"]


def reflection_trigger(persona):
  return (
    persona.scratch.movement_reflection_count >= MOVEMENT_REFLECTION_TRIGGER_COUNT
    and bool(persona.a_mem.seq_event or persona.a_mem.seq_chat)
  )


def reset_reflection_counter(persona):
  persona.scratch.movement_reflection_count = 0
  persona.scratch.importance_ele_n = 0
  persona.scratch.importance_trigger_curr = persona.scratch.importance_trigger_max


def reflect(persona):
  if reflection_trigger(persona):
    run_reflect(persona)
    reset_reflection_counter(persona)
