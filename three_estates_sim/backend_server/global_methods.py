from utils import *

def timedelta_to_natural(delta):
    total_seconds = int(delta.total_seconds())
    negative = total_seconds < 0
    total_seconds = abs(total_seconds)

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    result = ' and '.join(parts) if len(parts) <= 2 else ', '.join(parts[:-1]) + f", and {parts[-1]}"
    return f"-{result}" if negative else result


def table_leave_timer_status(table_name, curr_time):
    delta = TIMERS[table_name] - curr_time
    wilderness_note = ""
    if table_name == "Wilderness":
        wilderness_note = (
            " Wilderness has no independent role-timer; this countdown follows the last regular table "
            "to close, and players there can leave normally until that shared final closure."
        )
    if delta < datetime.timedelta(0):
        if table_name == "Wilderness":
            return (
                "Wilderness is FINAL-LOCKED because the last regular table has closed. Nobody seated at Wilderness can leave "
                "by normal movement or by any voluntary or forced ability; timer closure overrides Queen drags, Bishop exiles, "
                "Spinster departures, and every other departure effect. Players may still enter Wilderness."
            )
        return (
            f"{table_name} timer has expired and its timer lockdown is FINAL. Nobody seated at {table_name} can leave "
            "by normal movement or by any voluntary or forced ability; timer closure overrides Queen drags, Bishop exiles, "
            "Spinster departures, and every other departure effect. Players may still enter that table."
        )
    if delta == datetime.timedelta(0):
        if table_name == "Wilderness":
            return (
                "Wilderness has less than 1 second left before the last regular table closes; Wilderness will close "
                "with that final regular table. Players may still leave only before the next timer check resolves the lockdown; "
                "after that check, the lockdown is final and no voluntary or forced ability can move anyone out."
            )
        return (
            f"{table_name} has less than 1 second left and is about to close down NOW; "
            "players there may still leave only before the next timer check resolves the lockdown. After that check, "
            "the lockdown is final and no voluntary or forced ability can move anyone out."
        )
    return (
        f"{timedelta_to_natural(delta)} remaining before {table_name} enters FINAL timer lockdown, after which nobody seated there "
        f"can leave by normal movement or any voluntary or forced ability; players may still enter.{wilderness_note}"
    )


def get_other_player_context(table, persona):
    table_information = persona.scratch.curr_loc
    your_role = persona.scratch.role
    your_family = ROLE_DICT[your_role]["family"]
    your_ability = ROLE_DICT[your_role]["ability"]
    your_win_condition = ROLE_DICT[your_role]["win_condition"]
    your_win_progress = persona.scratch.win_progress


def ability_trigger(persona, table):
    trigger_message = ""
    role = persona.scratch.role
    table_size = len(table.personas.keys())

    def king_locked_family_text():
        families = set()
        for benefactor, target_name, lock_role in table.lockdown_targets:
            if benefactor != persona.scratch.name or lock_role != "King":
                continue
            if target_name in table.personas:
                families.add(ROLE_DICT[table.personas[target_name].scratch.role]["family"])
        if not families:
            return "the targeted family or families at this table"
        return ", ".join(sorted(families))

    if not has_own_role_card(persona, role):
        return f"Your {role} ability is not currently available because you do not have your {role} card.\n"

    if table.timer_expired and role in {"Queen", "Spinster", "Bishop", "Innkeeper"}:
        return (
            f"Your {role} ability cannot cause anyone to leave this table because its timer lockdown has expired and is FINAL. "
            "No voluntary or forced role ability can move a seated player out after timer closure, although players may still enter.\n"
        )

    if has_own_role_card(persona): # Prerequisite: your card is still with you
        if len(table.personas.keys()) == 2: # those that require one-on-one triggers
            if persona.scratch.role in {"Nun", "Priest"}:
                trigger_message = "Since you're alone with another player now, you have the option to stay and trigger your ability.\n"
            elif persona.scratch.role == "Thief" and not thief_reverse_swap_locked(table, persona.scratch.name):
                trigger_message = "Since you're alone with another player now, you have the option to stay and trigger your ability.\n"
        if persona.scratch.role == "Spinster":
            if persona.scratch.curr_loc == "Forest":
                trigger_message = "Since you're currently at the Forest, you can trigger your ability - but ONLY by leaving for another table.\n"
        elif persona.scratch.role == "Queen":
            if persona.scratch.ability_active == False:
                trigger_message = "Reminder that you can activate your ability but you will HAVE to leaving for another table for now.\n"
            else:
                ability_objects = ", ".join(persona.scratch.ability_objects)
                trigger_message = f"Reminder that you're currently holding {ability_objects} hostage and if you leave for another table your lock on {ability_objects} will automatically break.\n"
        elif persona.scratch.role == "King":
            if persona.scratch.ability_active == True:
                locked_families = king_locked_family_text()
                trigger_message = f"Reminder that your King lockdown is currently holding {locked_families} hostage, and if you leave for another table your lock on {locked_families} will automatically break.\n"
        elif persona.scratch.role == "Bishop":
            if table.bishop_trigger == True:
                trigger_message = f"Since at least one player has just made their departure, you have the option to stay and trigger your ability.\n"
        elif persona.scratch.role == "Innkeeper":
            if persona.scratch.ability_active == False:
                if persona.scratch.curr_loc == "Village":
                    trigger_message = "Since you're already at the Village, if you want to trigger your ability you must leave and come back again.\n"
                elif table_size <= 1:
                    trigger_message = (
                        "The condition for your Innkeeper ability bid is not currently met: you are alone at this table, "
                        "so there is no table audience for a departure ability bid. You may still choose to move to the Village through normal movement, "
                        "and if you enter the Village with your Innkeeper card you will decide there whether to reveal and declare.\n"
                    )
                else:
                    trigger_message = "Since you're outside the Village, you have the option to return to the village, reveal your Innkeeper card, and trigger your ability.\n"
            else:
                ability_objects = ", ".join(persona.scratch.ability_objects)
                trigger_message = f"Reminder that you're currently holding {ability_objects} hostage and if you leave for another table your lock on {ability_objects} will automatically break.\n"

    if not trigger_message:
        if role in {"Nun", "Thief", "Priest"}:
            if role == "Thief" and thief_reverse_swap_locked(table, persona.scratch.name):
                trigger_message = "The condition for your Thief ability is not currently met: this exact two-player swap cannot be immediately reversed until the table state changes, such as either of you leaving or someone else arriving.\n"
            else:
                trigger_message = f"The condition for your {role} ability is not currently met: it only works when you are sitting with exactly one other player.\n"
        elif role == "Spinster":
            if persona.scratch.curr_loc != "Forest":
                trigger_message = "The condition for your Spinster ability is not currently met: it only works when you leave the Forest.\n"
            elif table.timer_expired:
                trigger_message = "The condition for your Spinster ability is not currently met: the Forest timer lockdown is final, so no ability can move you out to trigger it.\n"
            elif table_size <= 1:
                trigger_message = "The condition for your Spinster ability is not currently met: there is no other player in the Forest to mark.\n"
        elif role == "Queen":
            if table.timer_expired:
                trigger_message = "The condition for your Queen ability is not currently met: your table timer lockdown is final, so no ability can move you or a target out.\n"
            elif table_size <= 1:
                trigger_message = "The condition for your Queen ability is not currently met: there is no other player here to make follow you.\n"
        elif role == "Bishop":
            trigger_message = "The condition for your Bishop ability is not currently met: nobody has just left your table recently enough for you to react to.\n"
        elif role == "King":
            if table_size <= 1:
                trigger_message = "The condition for your King ability is not currently useful: there are no other players here to lock down.\n"
        elif role == "Baron":
            trigger_message = "Your Baron ability is not a normal voluntary action right now; it can only trigger as a reaction when another player at your table shows a card while there are at least two other players at the table.\n"
        elif role == "Farmer":
            trigger_message = "Your Farmer ability is passive protection, so there is no voluntary ability to trigger right now.\n"

    return trigger_message


def check_if_file_exists(curr_file): 
  """
  Checks if a file exists
  ARGS:
    curr_file: path to the current csv file. 
  RETURNS: 
    True if the file exists
    False if the file does not exist
  """
  try: 
    with open(curr_file) as f_analysis_file: pass
    print("yes the file exists")
    return True
  except OSError:
    return False
