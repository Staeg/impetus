"""Spirit model: influence, possession, idols, VP."""

from typing import Optional
from shared.constants import STARTING_INFLUENCE, IdolType
from shared.models import Idol, SpiritState, HexCoord


class Spirit:
    """Server-side spirit (player) state."""

    def __init__(self, spirit_id: str, name: str):
        self.spirit_id = spirit_id
        self.name = name
        self.influence: int = 0
        self.is_vagrant: bool = True
        self.possessed_faction: Optional[str] = None
        self.idols: list[Idol] = []
        self.victory_points: int = 0

    def possess_faction(self, faction_id: str):
        self.is_vagrant = False
        self.possessed_faction = faction_id
        self.influence = STARTING_INFLUENCE

    def become_vagrant(self):
        self.is_vagrant = True
        self.possessed_faction = None
        self.influence = 0

    def lose_influence(self, amount: int = 1):
        self.influence = max(0, self.influence - amount)

    def place_idol(self, idol_type: IdolType, position: HexCoord) -> Idol:
        idol = Idol(type=idol_type, position=position, owner_spirit=self.spirit_id)
        self.idols.append(idol)
        return idol

    def count_idols_in_hexes(self, hex_set: set[tuple[int, int]]) -> int:
        return sum(1 for idol in self.idols if idol.position.to_tuple() in hex_set)

    def to_state(self) -> SpiritState:
        return SpiritState(
            spirit_id=self.spirit_id,
            name=self.name,
            influence=self.influence,
            is_vagrant=self.is_vagrant,
            possessed_faction=self.possessed_faction,
            idols=list(self.idols),
            victory_points=self.victory_points,
        )
