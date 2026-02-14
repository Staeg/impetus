"""Tests for scoring system."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.constants import IdolType
from shared.models import Idol, HexCoord
from server.faction import Faction
from server.spirit import Spirit
from server.hex_map import HexMap
from server.scoring import calculate_scoring


class TestScoring:
    def _setup(self):
        hm = HexMap()
        factions = {}
        for fid in ["mountain", "mesa", "sand", "plains", "river", "jungle"]:
            f = Faction(fid)
            for other in ["mountain", "mesa", "sand", "plains", "river", "jungle"]:
                if other != fid:
                    f.regard[other] = 0
            factions[fid] = f
        spirits = {}
        s = Spirit("s1", "Player 1")
        spirits["s1"] = s
        return hm, factions, spirits

    def test_no_worship_no_score(self):
        hm, factions, spirits = self._setup()
        events = calculate_scoring(factions, spirits, hm)
        assert len(events) == 0

    def test_battle_idol_scoring(self):
        hm, factions, spirits = self._setup()
        spirit = spirits["s1"]
        faction = factions["mountain"]
        faction.worship_spirit = "s1"
        faction.wars_won_this_turn = 2

        # Place a battle idol in mountain territory (1, -1)
        idol = Idol(IdolType.BATTLE, HexCoord(1, -1), "s1")
        hm.place_idol(idol)
        spirit.idols.append(idol)

        events = calculate_scoring(factions, spirits, hm)
        # 1 battle idol * 0.5 * 2 wars won = 1.0 VP -> floor = 1
        assert len(events) == 1
        assert events[0]["vp_gained"] == 1

    def test_affluence_idol_scoring(self):
        hm, factions, spirits = self._setup()
        spirit = spirits["s1"]
        faction = factions["mountain"]
        faction.worship_spirit = "s1"
        faction.gold_gained_this_turn = 5

        idol = Idol(IdolType.AFFLUENCE, HexCoord(1, -1), "s1")
        hm.place_idol(idol)
        spirit.idols.append(idol)

        events = calculate_scoring(factions, spirits, hm)
        # 1 affluence idol * 0.2 * 5 gold = 1.0 VP -> floor = 1
        assert len(events) == 1
        assert events[0]["vp_gained"] == 1

    def test_spread_idol_scoring(self):
        hm, factions, spirits = self._setup()
        spirit = spirits["s1"]
        faction = factions["mountain"]
        faction.worship_spirit = "s1"
        faction.territories_gained_this_turn = 2

        idol = Idol(IdolType.SPREAD, HexCoord(1, -1), "s1")
        hm.place_idol(idol)
        spirit.idols.append(idol)

        events = calculate_scoring(factions, spirits, hm)
        # 1 spread idol * 0.5 * 2 territories = 1.0 VP -> floor = 1
        assert len(events) == 1
        assert events[0]["vp_gained"] == 1

    def test_floor_rounding(self):
        hm, factions, spirits = self._setup()
        spirit = spirits["s1"]
        faction = factions["mountain"]
        faction.worship_spirit = "s1"
        faction.wars_won_this_turn = 1

        idol = Idol(IdolType.BATTLE, HexCoord(1, -1), "s1")
        hm.place_idol(idol)
        spirit.idols.append(idol)

        events = calculate_scoring(factions, spirits, hm)
        # 1 battle idol * 0.5 * 1 war = 0.5 -> floor = 0, no VP event
        assert len(events) == 0

    def test_multiple_idols(self):
        hm, factions, spirits = self._setup()
        spirit = spirits["s1"]
        faction = factions["mountain"]
        faction.worship_spirit = "s1"
        faction.wars_won_this_turn = 1

        # Place 2 battle idols
        for pos in [HexCoord(1, -1), HexCoord(1, -1)]:
            idol = Idol(IdolType.BATTLE, pos, "s1")
            hm.place_idol(idol)
            spirit.idols.append(idol)

        events = calculate_scoring(factions, spirits, hm)
        # 2 battle idols * 0.5 * 1 war = 1.0 -> floor = 1
        assert len(events) == 1
        assert events[0]["vp_gained"] == 1
