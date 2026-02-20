"""Server-side hex map state: ownership, idol placement, queries."""

import random
from typing import Optional
from shared.hex_utils import (
    generate_hex_grid, hex_neighbors, hexes_are_adjacent,
)
from shared.constants import MAP_SIDE_LENGTH, FACTION_START_HEXES
from shared.models import HexCoord, Idol


class HexMap:
    """Manages the hex grid, territory ownership, and idol placement."""

    def __init__(self, faction_start_hexes=None):
        self.all_hexes: set[tuple[int, int]] = generate_hex_grid(MAP_SIDE_LENGTH)
        # Maps (q, r) -> faction_id or None (neutral)
        self.ownership: dict[tuple[int, int], Optional[str]] = {}
        self.idols: list[Idol] = []
        self._faction_start_hexes = faction_start_hexes or FACTION_START_HEXES
        self._init_ownership()

    def _init_ownership(self):
        for hex_coord in self.all_hexes:
            self.ownership[hex_coord] = None
        for faction_id, (q, r) in self._faction_start_hexes.items():
            self.ownership[(q, r)] = faction_id

    def get_faction_territories(self, faction_id: str) -> set[tuple[int, int]]:
        return {h for h, owner in self.ownership.items() if owner == faction_id}

    def get_neutral_hexes(self) -> set[tuple[int, int]]:
        return {h for h, owner in self.ownership.items() if owner is None}

    def get_reachable_neutral_hexes(self, faction_id: str) -> set[tuple[int, int]]:
        """Neutral hexes adjacent to any territory owned by faction_id."""
        territories = self.get_faction_territories(faction_id)
        reachable = set()
        for (q, r) in territories:
            for nq, nr in hex_neighbors(q, r):
                if (nq, nr) in self.ownership and self.ownership[(nq, nr)] is None:
                    reachable.add((nq, nr))
        return reachable

    def get_border_hex_pairs(self, faction_a: str, faction_b: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """Return pairs of adjacent hexes where one belongs to faction_a and the other to faction_b."""
        terr_a = self.get_faction_territories(faction_a)
        pairs = []
        for (q, r) in terr_a:
            for nq, nr in hex_neighbors(q, r):
                if (nq, nr) in self.ownership and self.ownership[(nq, nr)] == faction_b:
                    pairs.append(((q, r), (nq, nr)))
        return pairs

    def are_factions_neighbors(self, faction_a: str, faction_b: str) -> bool:
        return len(self.get_border_hex_pairs(faction_a, faction_b)) > 0

    def get_live_neighbor_ids(self, faction_id: str, factions: dict) -> list[str]:
        """Return IDs of non-eliminated factions neighboring faction_id."""
        return [
            fid for fid, f in factions.items()
            if fid != faction_id and not f.eliminated
            and self.are_factions_neighbors(faction_id, fid)
        ]

    def claim_hex(self, hex_coord: tuple[int, int], faction_id: str):
        """Set ownership of a hex to a faction."""
        self.ownership[hex_coord] = faction_id

    def place_idol(self, idol: Idol):
        self.idols.append(idol)

    def get_idols_in_territories(self, faction_id: str) -> list[Idol]:
        """Return all idols located in territories owned by faction_id."""
        territories = self.get_faction_territories(faction_id)
        return [idol for idol in self.idols if idol.position.to_tuple() in territories]

    def get_idols_at_hex(self, q: int, r: int) -> list[Idol]:
        return [idol for idol in self.idols if idol.position.q == q and idol.position.r == r]

    def count_spirit_idols_in_faction(self, spirit_id: str, faction_id: str) -> int:
        """Count how many idols a specific spirit has in a faction's territory."""
        territories = self.get_faction_territories(faction_id)
        return sum(1 for idol in self.idols
                   if idol.owner_spirit == spirit_id
                   and idol.position.to_tuple() in territories)

    def get_random_reachable_neutral(self, faction_id: str) -> Optional[tuple[int, int]]:
        """Pick a random reachable neutral hex, preferring those with idols."""
        reachable = self.get_reachable_neutral_hexes(faction_id)
        if not reachable:
            return None
        # Prefer hexes with idols
        with_idols = {h for h in reachable if self.get_idols_at_hex(h[0], h[1])}
        if with_idols:
            return random.choice(list(with_idols))
        return random.choice(list(reachable))

    def get_ownership_dict(self) -> dict[str, Optional[str]]:
        """Serializable ownership map: 'q,r' -> faction_id or None."""
        return {f"{q},{r}": owner for (q, r), owner in self.ownership.items()}
