"""Module-level registry mapping faction IDs to their race for the current game.

Call update_faction_races() whenever a new game state snapshot is received.
faction_full_name() returns 'Habitat Race' (e.g., 'Mountain Goblins').
"""

from shared.constants import FACTION_DISPLAY_NAMES

_faction_races: dict[str, str] = {}


def update_faction_races(races: dict[str, str]) -> None:
    """Update the registry from a {faction_id: race} mapping."""
    global _faction_races
    _faction_races.clear()
    _faction_races.update(races)


def faction_full_name(fid: str) -> str:
    """Return 'Habitat Race' display name, or just habitat name if no race is known."""
    habitat = FACTION_DISPLAY_NAMES.get(fid, fid)
    race = _faction_races.get(fid, "")
    return f"{habitat} {race}" if race else habitat
