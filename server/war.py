"""War system: eruption tracking and resolution."""

import random
import uuid
from shared.models import WarState, HexCoord


class War:
    """A war between two factions. In Era 1, wars resolve on the same turn they erupt."""

    def __init__(self, faction_a: str, faction_b: str,
                 declared_turn: int = 0, resolve_turn: int = 0):
        self.war_id = str(uuid.uuid4())[:8]
        self.faction_a = faction_a
        self.faction_b = faction_b
        self.declared_turn = declared_turn
        self.resolve_turn = resolve_turn
        self.battleground_a: tuple[int, int] | None = None
        self.battleground_b: tuple[int, int] | None = None
        self.is_staged = False

    def stage(self, battleground_a: tuple[int, int], battleground_b: tuple[int, int], resolve_turn: int):
        self.battleground_a = battleground_a
        self.battleground_b = battleground_b
        self.resolve_turn = resolve_turn
        self.is_staged = True

    def resolve(self, power_a: int, power_b: int,
                bonus_dice_a: int = 0, bonus_dice_b: int = 0) -> dict:
        """Resolve this war using die rolls plus territory count.

        Returns a result dict. Does NOT apply gold changes (none in Era 1).
        """
        base_roll_a = random.randint(1, 6)
        base_roll_b = random.randint(1, 6)
        support_rolls_a = [random.randint(1, 6) for _ in range(max(0, bonus_dice_a))]
        support_rolls_b = [random.randint(1, 6) for _ in range(max(0, bonus_dice_b))]

        roll_a = base_roll_a + sum(support_rolls_a)
        roll_b = base_roll_b + sum(support_rolls_b)

        total_a = roll_a + power_a
        total_b = roll_b + power_b

        result = {
            "war_id": self.war_id,
            "faction_a": self.faction_a,
            "faction_b": self.faction_b,
            "declared_turn": self.declared_turn,
            "resolve_turn": self.resolve_turn,
            "battleground_a": {"q": self.battleground_a[0], "r": self.battleground_a[1]} if self.battleground_a else None,
            "battleground_b": {"q": self.battleground_b[0], "r": self.battleground_b[1]} if self.battleground_b else None,
            "is_staged": self.is_staged,
            "roll_a": roll_a,
            "roll_b": roll_b,
            "base_roll_a": base_roll_a,
            "base_roll_b": base_roll_b,
            "support_rolls_a": support_rolls_a,
            "support_rolls_b": support_rolls_b,
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
            "declared_turn": self.declared_turn,
            "resolve_turn": self.resolve_turn,
            "battleground_a": {"q": self.battleground_a[0], "r": self.battleground_a[1]} if self.battleground_a else None,
            "battleground_b": {"q": self.battleground_b[0], "r": self.battleground_b[1]} if self.battleground_b else None,
            "is_staged": self.is_staged,
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
            battleground_a=HexCoord(*self.battleground_a) if self.battleground_a else None,
            battleground_b=HexCoord(*self.battleground_b) if self.battleground_b else None,
            resolve_turn=self.resolve_turn,
            declared_turn=self.declared_turn,
            is_staged=self.is_staged,
        )
