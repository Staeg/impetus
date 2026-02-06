"""Tests for war system."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.war import War
from server.faction import Faction
from server.hex_map import HexMap


def make_factions():
    factions = {}
    for fid in ["mountain", "mesa", "sand", "plains", "river", "jungle"]:
        f = Faction(fid)
        for other in ["mountain", "mesa", "sand", "plains", "river", "jungle"]:
            if other != fid:
                f.regard[other] = 0
        factions[fid] = f
    return factions


class TestWar:
    def test_war_creation(self):
        war = War("mountain", "mesa")
        assert war.faction_a == "mountain"
        assert war.faction_b == "mesa"
        assert war.is_ripe is False
        assert war.battleground is None

    def test_war_ripen(self):
        hm = HexMap()
        war = War("mountain", "mesa")
        result = war.ripen(hm)
        assert result is True
        assert war.is_ripe is True
        assert war.battleground is not None

    def test_war_resolve(self):
        hm = HexMap()
        factions = make_factions()
        factions["mountain"].gold = 5
        factions["mesa"].gold = 5
        war = War("mountain", "mesa")
        war.ripen(hm)
        result = war.resolve(factions, hm)
        assert "roll_a" in result
        assert "roll_b" in result
        assert "power_a" in result
        assert "power_b" in result
        # One faction should have lost gold (or both in tie)
        total_gold = factions["mountain"].gold + factions["mesa"].gold
        assert total_gold <= 10  # At most what they started with

    def test_war_to_state(self):
        hm = HexMap()
        war = War("mountain", "mesa")
        war.ripen(hm)
        state = war.to_state()
        assert state.faction_a == "mountain"
        assert state.faction_b == "mesa"
        assert state.is_ripe is True
        assert state.battleground is not None

    def test_war_no_border(self):
        """Test war ripening when factions aren't neighbors (opposite sides of map)."""
        hm = HexMap()
        # Mountain (1,-1) and plains (-1,1) are on opposite sides, not adjacent
        war = War("mountain", "plains")
        result = war.ripen(hm)
        assert result is False  # They are not neighbors
