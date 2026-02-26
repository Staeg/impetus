"""War system: eruption tracking, ripening, resolution."""

import random
import uuid
from shared.models import HexCoord, WarState


class War:
    """A war between two factions."""

    def __init__(self, faction_a: str, faction_b: str):
        self.war_id = str(uuid.uuid4())[:8]
        self.faction_a = faction_a
        self.faction_b = faction_b
        self.is_ripe = False
        self.battleground: Optional[tuple[tuple[int, int], tuple[int, int]]] = None

    def ripen(self, hex_map) -> bool:
        """Make this war ripe and select a battleground. Returns True if successful."""
        border_pairs = hex_map.get_border_hex_pairs(self.faction_a, self.faction_b)
        if not border_pairs:
            return False
        self.battleground = random.choice(border_pairs)
        self.is_ripe = True
        return True

    def ripen_with_battleground(self, battleground: tuple) -> None:
        """Ripen this war using an already-chosen battleground pair."""
        self.battleground = battleground
        self.is_ripe = True

    def resolve(self, power_a: int, power_b: int) -> dict:
        """Resolve this war using pre-computed power values.

        Returns a result dict with outcome details. Does NOT apply gold
        changes — the caller is responsible for applying gold simultaneously.
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
            "battleground": None,
        }

        if self.battleground:
            result["battleground"] = [
                {"q": self.battleground[0][0], "r": self.battleground[0][1]},
                {"q": self.battleground[1][0], "r": self.battleground[1][1]},
            ]

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

    def to_state(self) -> WarState:
        bg = None
        if self.battleground:
            bg = (HexCoord(*self.battleground[0]), HexCoord(*self.battleground[1]))
        return WarState(
            war_id=self.war_id,
            faction_a=self.faction_a,
            faction_b=self.faction_b,
            is_ripe=self.is_ripe,
            battleground=bg,
        )
