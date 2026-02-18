"""Tests for agenda resolution."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.constants import AgendaType, AGENDA_RESOLUTION_ORDER
from shared.models import AgendaCard
from server.faction import Faction
from server.hex_map import HexMap
from server.spirit import Spirit
from server.agenda import resolve_agendas, resolve_spoils, finalize_all_spoils


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


class TestResolutionOrder:
    def test_order_is_trade_first(self):
        assert AGENDA_RESOLUTION_ORDER == [
            AgendaType.TRADE,
            AgendaType.STEAL,
            AgendaType.EXPAND,
            AgendaType.CHANGE,
        ]

    def test_steal_resolves_before_expand_cost_check(self):
        factions = make_factions()
        hm = HexMap()
        wars = []
        events = []

        # Mountain can afford Expand only before Mesa steals from it.
        factions["mountain"].gold = 1
        factions["mesa"].gold = 0

        resolve_agendas(factions, hm, {
            "mountain": AgendaType.EXPAND,
            "mesa": AgendaType.STEAL,
        }, wars, events)

        types = [e["type"] for e in events]
        assert "steal" in types
        assert "expand_failed" in types
        assert types.index("steal") < types.index("expand_failed")


class TestEventFields:
    def test_steal_event_has_neighbors_and_penalty(self):
        factions = make_factions()
        hm = HexMap()
        factions["mesa"].gold = 5
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.STEAL}, wars, events)
        steal_events = [e for e in events if e["type"] == "steal"]
        assert len(steal_events) == 1
        ev = steal_events[0]
        assert "regard_penalty" in ev
        assert ev["regard_penalty"] == 1
        assert "neighbors" in ev
        assert isinstance(ev["neighbors"], list)
        assert len(ev["neighbors"]) > 0

class TestTradeRegard:
    def test_co_traders_gain_regard(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {
            "mountain": AgendaType.TRADE,
            "mesa": AgendaType.TRADE,
        }, wars, events)
        # Both process: mountain gives +1 to mesa and mesa gives +1 to mountain
        # Total: +2 each way
        assert factions["mountain"].get_regard("mesa") == 2
        assert factions["mesa"].get_regard("mountain") == 2

    def test_trade_modifier_affects_regard(self):
        factions = make_factions()
        hm = HexMap()
        # Give mountain a trade modifier
        factions["mountain"].change_modifiers["trade"] = 1
        events = []
        wars = []
        resolve_agendas(factions, hm, {
            "mountain": AgendaType.TRADE,
            "mesa": AgendaType.TRADE,
        }, wars, events)
        # Mountain processing: regard_gain = 1+1 = 2, bilateral → both get +2
        # Mesa processing: regard_gain = 1+0 = 1, bilateral → both get +1
        # Total: mountain→mesa = +3, mesa→mountain = +3
        assert factions["mountain"].get_regard("mesa") == 3
        assert factions["mesa"].get_regard("mountain") == 3

    def test_solo_trade_no_regard(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {"mountain": AgendaType.TRADE}, wars, events)
        # No co-traders, no regard changes
        assert factions["mountain"].get_regard("mesa") == 0

    def test_trade_event_has_co_traders(self):
        factions = make_factions()
        hm = HexMap()
        events = []
        wars = []
        resolve_agendas(factions, hm, {
            "mountain": AgendaType.TRADE,
            "mesa": AgendaType.TRADE,
        }, wars, events)
        trade_events = [e for e in events if e["type"] == "trade"]
        assert len(trade_events) == 2
        for ev in trade_events:
            assert "co_traders" in ev
            assert "regard_gain" in ev


class TestSpoilsChoices:
    def test_guided_zero_influence_single_draw_has_no_spoils_choice(self):
        factions = make_factions()
        hm = HexMap()
        wars = []
        events = []

        spirit = Spirit("spirit_0", "Player 0")
        spirit.guide_faction("mountain")
        spirit.influence = 0
        factions["mountain"].guiding_spirit = spirit.spirit_id

        # Force a single possible spoils card.
        factions["mountain"].agenda_pool = [AgendaCard(AgendaType.TRADE)]

        war_results = [{
            "winner": "mountain",
            "loser": "mesa",
            "battleground": None,
        }]

        pending, auto_choices = resolve_spoils(
            factions, hm, war_results, wars, events,
            normal_trade_factions=[], spirits={spirit.spirit_id: spirit},
        )

        assert pending == {}
        assert not any(e["type"] == "spoils_choice" for e in events)
        assert any(
            e["type"] == "spoils_drawn" and e["faction"] == "mountain"
            for e in events
        )
        # Auto choice should have been collected
        assert len(auto_choices) == 1
        assert auto_choices[0]["winner"] == "mountain"


class TestDeckPool:
    def test_draw_agenda_cards_does_not_deplete_deck(self):
        """Drawing cards from the pool should not remove them."""
        factions = make_factions()
        faction = factions["mountain"]
        original_size = len(faction.agenda_pool)
        hand = faction.draw_agenda_cards(3)
        assert len(hand) == 3
        assert len(faction.agenda_pool) == original_size

    def test_draw_random_agenda_does_not_deplete_deck(self):
        factions = make_factions()
        faction = factions["mountain"]
        original_size = len(faction.agenda_pool)
        card = faction.draw_random_agenda()
        assert card is not None
        assert len(faction.agenda_pool) == original_size

    def test_draw_agenda_cards_allows_duplicates(self):
        """With a pool of 1 card, drawing 3 should give 3 copies."""
        factions = make_factions()
        faction = factions["mountain"]
        faction.agenda_pool = [AgendaCard(AgendaType.TRADE)]
        hand = faction.draw_agenda_cards(3)
        assert len(hand) == 3
        assert all(c.agenda_type == AgendaType.TRADE for c in hand)

    def test_cleanup_deck_clears_played(self):
        factions = make_factions()
        faction = factions["mountain"]
        faction.played_agenda_this_turn.append(AgendaCard(AgendaType.STEAL))
        original_size = len(faction.agenda_pool)
        faction.cleanup_deck()
        assert len(faction.played_agenda_this_turn) == 0
        # Pool should not grow from cleanup
        assert len(faction.agenda_pool) == original_size

    def test_replace_agenda_card_keeps_pool_size(self):
        """Ejection replaces one card, so pool size stays the same."""
        factions = make_factions()
        faction = factions["mountain"]
        original_size = len(faction.agenda_pool)
        faction.replace_agenda_card(AgendaType.STEAL, AgendaType.TRADE)
        assert len(faction.agenda_pool) == original_size
        # One Steal was removed and one Trade was added
        types = [c.agenda_type for c in faction.agenda_pool]
        assert AgendaType.STEAL not in types
        assert types.count(AgendaType.TRADE) == 2


class TestContestedSpoilsExpand:
    def test_contested_spoils_expand_neither_gets_hex(self):
        """If two factions target the same hex via spoils expand, neither gets it."""
        factions = make_factions()
        hm = HexMap()
        wars = []
        events = []

        # Find a hex owned by mesa
        mesa_hexes = list(hm.get_faction_territories("mesa"))
        target_hex = mesa_hexes[0]
        bg = [{"q": target_hex[0], "r": target_hex[1]}]

        all_spoils = [
            {
                "winner": "mountain",
                "loser": "mesa",
                "agenda_type": AgendaType.EXPAND,
                "battleground": bg,
            },
            {
                "winner": "sand",
                "loser": "mesa",
                "agenda_type": AgendaType.EXPAND,
                "battleground": bg,
            },
        ]

        finalize_all_spoils(factions, hm, wars, events, all_spoils,
                           normal_trade_factions=[])

        # Neither should have claimed mesa's hex
        assert hm.ownership.get(target_hex) == "mesa"
        # Both should get expand_failed events
        failed = [e for e in events if e["type"] == "expand_failed"]
        assert len(failed) == 2
        assert all(e.get("contested") for e in failed)


class TestMultipleSpoilsPerFaction:
    def test_double_trade_spoils(self):
        """Faction wins 2 wars, both spoils are Trade — gold doubles."""
        factions = make_factions()
        hm = HexMap()
        wars = []
        events = []

        factions["mountain"].gold = 0

        all_spoils = [
            {"winner": "mountain", "loser": "mesa",
             "agenda_type": AgendaType.TRADE, "battleground": None},
            {"winner": "mountain", "loser": "sand",
             "agenda_type": AgendaType.TRADE, "battleground": None},
        ]

        finalize_all_spoils(factions, hm, wars, events, all_spoils,
                           normal_trade_factions=[])

        # Single trade with no co-traders = base 1 gold. Two instances = 2 gold.
        assert factions["mountain"].gold == 2
        trade_events = [e for e in events if e["type"] == "trade"]
        assert len(trade_events) == 1
        assert trade_events[0]["gold_gained"] == 2

    def test_double_expand_spoils_different_hexes(self):
        """Faction wins 2 wars, both spoils Expand to different hexes — both claimed."""
        factions = make_factions()
        hm = HexMap()
        wars = []
        events = []

        # Find two different hexes owned by different losers
        mesa_hexes = list(hm.get_faction_territories("mesa"))
        sand_hexes = list(hm.get_faction_territories("sand"))
        target1 = mesa_hexes[0]
        target2 = sand_hexes[0]

        bg1 = [{"q": target1[0], "r": target1[1]}]
        bg2 = [{"q": target2[0], "r": target2[1]}]

        all_spoils = [
            {"winner": "mountain", "loser": "mesa",
             "agenda_type": AgendaType.EXPAND, "battleground": bg1},
            {"winner": "mountain", "loser": "sand",
             "agenda_type": AgendaType.EXPAND, "battleground": bg2},
        ]

        finalize_all_spoils(factions, hm, wars, events, all_spoils,
                           normal_trade_factions=[])

        # Both hexes should now be owned by mountain
        assert hm.ownership.get(target1) == "mountain"
        assert hm.ownership.get(target2) == "mountain"
        expand_events = [e for e in events if e["type"] == "expand_spoils"]
        assert len(expand_events) == 2

    def test_mixed_agenda_types_both_resolve(self):
        """Faction wins 2 wars with different spoils types — both resolve (regression: dict overwrite)."""
        factions = make_factions()
        hm = HexMap()
        wars = []
        events = []

        factions["mountain"].gold = 0
        factions["mesa"].gold = 5

        all_spoils = [
            {"winner": "mountain", "loser": "mesa",
             "agenda_type": AgendaType.TRADE, "battleground": None},
            {"winner": "mountain", "loser": "sand",
             "agenda_type": AgendaType.STEAL, "battleground": None},
        ]

        finalize_all_spoils(factions, hm, wars, events, all_spoils,
                           normal_trade_factions=[])

        # Both types should have resolved
        trade_events = [e for e in events if e["type"] == "trade"]
        steal_events = [e for e in events if e["type"] == "steal"]
        assert len(trade_events) == 1
        assert len(steal_events) == 1
        # Mountain should have gold from both trade and steal
        assert factions["mountain"].gold > 0
