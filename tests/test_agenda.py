"""Tests for agenda resolution."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.constants import AgendaType
from server.faction import Faction
from server.hex_map import HexMap
from server.agenda import resolve_agendas


def make_factions():
    factions = {}
    for fid in ["mountain", "mesa", "sand", "plains", "river", "jungle"]:
        f = Faction(fid)
        for other in ["mountain", "mesa", "sand", "plains", "river", "jungle"]:
            if other != fid:
                f.regard[other] = 0
        factions[fid] = f
    return factions


class TestSteal:
    def test_steal_takes_gold(self):
        factions = make_factions()
        hm = HexMap()
        # Give mesa some gold
        factions["mesa"].gold = 5
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.STEAL}, wars, events)
        # Mountain should have gained gold (mesa is neighbor)
        assert factions["mountain"].gold > 0

    def test_steal_reduces_regard(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.STEAL}, wars, events)
        # Regard with neighbors should be negative
        assert factions["mountain"].get_regard("mesa") < 0

    def test_steal_erupts_war(self):
        factions = make_factions()
        hm = HexMap()
        # Set regard to -1 so steal pushes to -2
        factions["mountain"].regard["mesa"] = -1
        factions["mesa"].regard["mountain"] = -1
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.STEAL}, wars, events)
        assert len(wars) > 0

    def test_simultaneous_steal(self):
        factions = make_factions()
        hm = HexMap()
        factions["mountain"].gold = 3
        factions["mesa"].gold = 3
        events = []
        wars = []
        resolve_agendas(factions, hm, {
            "mountain": AgendaType.STEAL,
            "mesa": AgendaType.STEAL,
        }, wars, events)
        # Both should have negative regard with each other
        assert factions["mountain"].get_regard("mesa") <= -2


class TestBond:
    def test_bond_increases_regard(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.BOND}, wars, events)
        assert factions["mountain"].get_regard("mesa") > 0


class TestTrade:
    def test_trade_gives_gold(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.TRADE}, wars, events)
        assert factions["mountain"].gold >= 1

    def test_multiple_traders(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {
            "mountain": AgendaType.TRADE,
            "mesa": AgendaType.TRADE,
        }, wars, events)
        # Each should get base 1 + 1 for the other trader
        assert factions["mountain"].gold >= 2
        assert factions["mesa"].gold >= 2


class TestExpand:
    def test_expand_claims_territory(self):
        factions = make_factions()
        hm = HexMap()
        # Give mountain gold to pay for expansion (cost = number of territories = 1)
        factions["mountain"].gold = 5
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.EXPAND}, wars, events)
        # Should now have 2 territories
        terr = hm.get_faction_territories("mountain")
        assert len(terr) == 2

    def test_expand_no_gold_gives_gold(self):
        factions = make_factions()
        hm = HexMap()
        factions["mountain"].gold = 0
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.EXPAND}, wars, events)
        assert factions["mountain"].gold >= 1
        # Still 1 territory
        terr = hm.get_faction_territories("mountain")
        assert len(terr) == 1


class TestChange:
    def test_change_adds_modifier(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.CHANGE}, wars, events)
        # At least one modifier should have increased
        total = sum(factions["mountain"].change_modifiers.values())
        assert total == 1
