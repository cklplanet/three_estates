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


def get_other_player_context(table, persona):
    table_information = persona.scratch.curr_loc
    your_role = persona.scratch.role
    your_family = ROLE_DICT[your_role]["family"]
    your_ability = ROLE_DICT[your_role]["ability"]
    your_win_condition = ROLE_DICT[your_role]["win_condition"]
    your_win_progress = persona.scratch.win_progress


def ability_trigger(persona, table):
    # TODO: the peculiar case of the the thief immediately bailing after stealing one's card, encouraged but not strictly regulated
    trigger_message = ""
    if persona.scratch.role in persona.scratch.cards_slot: # Prerequisite: your card is still with you
        if len(table.personas.keys()) == 2: # those that require one-on-one triggers
            if persona.scratch.role == "Nun" or persona.scratch.role == "Thief" or persona.scratch.role == "Priest":
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
                ability_objects = ", ".join(persona.scratch.ability_objects)
                trigger_message = f"Reminder that you're currently holding {ability_objects} hostage and if you leave for another table your lock on {ability_objects} will automatically break.\n"
        elif persona.scratch.role == "Bishop":
            if table.bishop_trigger == True:
                trigger_message = f"Since at least one player has just made their departure, you have the option to stay and trigger your ability.\n"
        elif persona.scratch.role == "Baron":
            if table.baron_trigger:
                ability_objects = " and ".join(list(table.baron_trigger))
                trigger_message = f"Since {ability_objects} has/have just revealed their card, you have the option to stay and trigger your ability.\n"
        elif persona.scratch.role == "Innkeeper":
            if persona.scratch.ability_active == False:
                if persona.scratch.curr_loc == "Village":
                    trigger_message = "Since you're already at the Village, if you want to trigger your ability you must leave and come back again.\n"
                else:
                    trigger_message = "Since you're outside the Village, you have the option to return to the village to trigger your ability.\n"
            else:
                ability_objects = ", ".join(persona.scratch.ability_objects)
                trigger_message = f"Reminder that you're currently holding {ability_objects} hostage and if you leave for another table your lock on {ability_objects} will automatically break.\n"

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
  except: 
    return False