"""War system: eruption tracking and resolution."""

import random
import uuid
from shared.models import WarState


class War:
    """A war between two factions. In Era 1, wars resolve on the same turn they erupt."""

    def __init__(self, faction_a: str, faction_b: str):
        self.war_id = str(uuid.uuid4())[:8]
        self.faction_a = faction_a
        self.faction_b = faction_b

    def resolve(self, power_a: int, power_b: int) -> dict:
        """Resolve this war using a die roll + territory count.

        Returns a result dict. Does NOT apply gold changes (none in Era 1).
        """
        roll_a = random.randint(1, 6)
        roll_b = random.randint(1, 6)

        total_a = roll_a + power_a
        total_b = roll_b + power_b

        result = {
            "war_id": self.war_id,
            "faction_a": self.faction_a,
            "faction_b": self.faction_b,
            "roll_a": roll_a,
            "roll_b": roll_b,
            "power_a": power_a,
            "power_b": power_b,
            "total_a": total_a,
            "total_b": total_b,
            "forced": False,
        }

        if total_a > total_b:
            result["winner"] = self.faction_a
            result["loser"] = self.faction_b
        elif total_b > total_a:
            result["winner"] = self.faction_b
            result["loser"] = self.faction_a
        else:
            result["winner"] = None
            result["loser"] = None

        return result

    def resolve_forced(self, winner: str, guided_faction: str) -> dict:
        """Resolve this war with a spirit-chosen winner (one-guided case).

        guided_faction is the faction the deciding spirit guides.
        Returns a result dict with forced=True.
        """
        loser = self.faction_b if winner == self.faction_a else self.faction_a
        return {
            "war_id": self.war_id,
            "faction_a": self.faction_a,
            "faction_b": self.faction_b,
            "winner": winner,
            "loser": loser,
            "guided_faction": guided_faction,
            "forced": True,
        }

    def to_state(self) -> WarState:
        return WarState(
            war_id=self.war_id,
            faction_a=self.faction_a,
            faction_b=self.faction_b,
        )
