"""Pure validation helpers for fixed-roster character generation."""


def normalize_character_name_roster(raw_names, cast_size, committed_names=None):
    """Return exactly ``cast_size`` unique names, preserving order.

    Already-created names are authoritative and lead the roster. Model-proposed
    names fill the remaining slots. Deterministic placeholders are used only
    when the model did not provide enough valid unique names.
    """
    if isinstance(raw_names, dict):
        raw_names = raw_names.get("names", [])
    if not isinstance(raw_names, (list, tuple)):
        raw_names = []

    roster = []
    seen = set()

    def add_name(value):
        value = str(value or "").strip()
        identity = value.casefold()
        if not value or identity in seen or len(roster) >= cast_size:
            return
        roster.append(value)
        seen.add(identity)

    for name in committed_names or []:
        add_name(name)
    for name in raw_names:
        if isinstance(name, dict):
            name = name.get("name")
        add_name(name)

    placeholder_index = 1
    while len(roster) < cast_size:
        candidate = f"Character {placeholder_index}"
        placeholder_index += 1
        add_name(candidate)
    return roster
