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
        power_a = len(hm.get_faction_territories("mountain"))
        power_b = len(hm.get_faction_territories("mesa"))
        result = war.resolve(power_a, power_b)
        assert "roll_a" in result
        assert "roll_b" in result
        assert "power_a" in result
        assert "power_b" in result
        assert result["power_a"] == power_a
        assert result["power_b"] == power_b
        # resolve() no longer applies gold — only determines winner
        assert factions["mountain"].gold == 5
        assert factions["mesa"].gold == 5

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

    def test_resolve_uses_provided_power(self):
        """resolve() should use the provided power values, not compute its own."""
        war = War("mountain", "mesa")
        war.is_ripe = True
        war.battleground = ((0, 0), (1, 0))
        # Provide arbitrary power values
        result = war.resolve(10, 20)
        assert result["power_a"] == 10
        assert result["power_b"] == 20
        # No gold side effects (no faction objects involved)
        assert result["total_a"] == result["roll_a"] + 10
        assert result["total_b"] == result["roll_b"] + 20
