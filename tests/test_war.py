"""Tests for war system."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.war import War
from server.faction import Faction
from server.hex_map import HexMap


class TestWar:
    def test_war_creation(self):
        war = War("mountain", "mesa")
        assert war.faction_a == "mountain"
        assert war.faction_b == "mesa"
        assert war.war_id is not None

    def test_war_resolve(self):
        war = War("mountain", "mesa")
        power_a = 3
        power_b = 3
        result = war.resolve(power_a, power_b)
        assert "roll_a" in result
        assert "roll_b" in result
        assert "power_a" in result
        assert "power_b" in result
        assert result["power_a"] == power_a
        assert result["power_b"] == power_b
        assert result.get("forced") is False

    def test_war_to_state(self):
        war = War("mountain", "mesa")
        state = war.to_state()
        assert state.faction_a == "mountain"
        assert state.faction_b == "mesa"
        assert state.war_id == war.war_id

    def test_resolve_uses_provided_power(self):
        """resolve() should use the provided power values, not compute its own."""
        war = War("mountain", "mesa")
        result = war.resolve(10, 20)
        assert result["power_a"] == 10
        assert result["power_b"] == 20
        assert result["total_a"] == result["roll_a"] + 10
        assert result["total_b"] == result["roll_b"] + 20

    def test_resolve_forced_winner(self):
        """resolve_forced returns correct winner/loser with forced=True."""
        war = War("mountain", "mesa")
        result = war.resolve_forced("mountain", guided_faction="mountain")
        assert result["winner"] == "mountain"
        assert result["loser"] == "mesa"
        assert result["forced"] is True
        assert result["guided_faction"] == "mountain"

    def test_resolve_forced_other_faction_wins(self):
        """Spirit can choose the opposing faction to win."""
        war = War("mountain", "mesa")
        result = war.resolve_forced("mesa", guided_faction="mountain")
        assert result["winner"] == "mesa"
        assert result["loser"] == "mountain"
        assert result["forced"] is True
