"""Tests for game state machine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.constants import Phase, AgendaType, IdolType
from server.game_state import GameState


def make_game(num_players=3):
    gs = GameState()
    players = [{"spirit_id": f"spirit_{i}", "name": f"Player {i}"} for i in range(num_players)]
    gs.setup_game(players)
    return gs


def neutral_hexes(gs, n=2):
    """Get n guaranteed-neutral hex coordinates from the game state."""
    return list(gs.hex_map.get_neutral_hexes())[:n]


class TestGameStateSetup:
    def test_initial_phase(self):
        gs = make_game()
        assert gs.phase == Phase.VAGRANT_PHASE

    def test_initial_turn(self):
        gs = make_game()
        assert gs.turn == 3

    def test_factions_created(self):
        gs = make_game()
        assert len(gs.factions) == 6

    def test_spirits_created(self):
        gs = make_game(4)
        assert len(gs.spirits) == 4

    def test_all_spirits_vagrant(self):
        gs = make_game()
        for spirit in gs.spirits.values():
            assert spirit.is_vagrant is True

    def test_faction_regard_initialized(self):
        gs = make_game()
        for faction in gs.factions.values():
            for other_fid in gs.factions:
                if other_fid != faction.faction_id:
                    # Regard is initialized for all pairs (may be non-zero
                    # due to opening automated turns resolving Bond/Steal)
                    assert other_fid in faction.regard


class TestVagrantPhase:
    def test_needs_input(self):
        gs = make_game(2)
        assert gs.needs_input("spirit_0") is True
        assert gs.needs_input("spirit_1") is True

    def test_submit_guide(self):
        gs = make_game(2)
        h = neutral_hexes(gs, 1)
        err = gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        assert err is None

    def test_submit_idol(self):
        gs = make_game(2)
        h = neutral_hexes(gs, 1)
        err = gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        assert err is None

    def test_invalid_guide_target(self):
        gs = make_game(2)
        h = neutral_hexes(gs, 1)
        err = gs.submit_action("spirit_0", {
            "guide_target": "nonexistent",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        assert err is not None

    def test_resolve_guide(self):
        gs = make_game(2)
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "plains",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        events = gs.resolve_current_phase()
        assert gs.phase == Phase.AGENDA_PHASE
        assert gs.spirits["spirit_0"].guided_faction == "mountain"
        assert gs.spirits["spirit_0"].influence == 3
        assert gs.factions["mountain"].guiding_spirit == "spirit_0"

    def test_contested_guide(self):
        gs = make_game(2)
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "mountain",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        events = gs.resolve_current_phase()
        assert gs.spirits["spirit_0"].is_vagrant is True
        assert gs.spirits["spirit_1"].is_vagrant is True
        assert gs.factions["mountain"].guiding_spirit is None

    def test_idol_placement(self):
        gs = make_game(2)
        # Use hexes far from faction starts to avoid setup Expand claims
        neutral = list(gs.hex_map.get_neutral_hexes())
        h0, h1 = neutral[0], neutral[1]
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h0[0], "idol_r": h0[1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "plains",
            "idol_type": "affluence", "idol_q": h1[0], "idol_r": h1[1],
        })
        events = gs.resolve_current_phase()
        assert len(gs.hex_map.idols) == 2
        assert len(gs.spirits["spirit_0"].idols) == 1

    def test_submit_combined_guide_and_idol(self):
        gs = make_game(2)
        h = neutral_hexes(gs)
        err = gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle",
            "idol_q": h[0][0], "idol_r": h[0][1],
        })
        assert err is None
        gs.submit_action("spirit_1", {
            "guide_target": "plains",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        events = gs.resolve_current_phase()
        # Both should resolve
        assert gs.spirits["spirit_0"].guided_faction == "mountain"
        assert len(gs.hex_map.idols) == 2
        assert len(gs.spirits["spirit_0"].idols) == 1

    def test_contested_single_event(self):
        gs = make_game(2)
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "mountain",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        events = gs.resolve_current_phase()
        contested = [e for e in events if e["type"] == "guide_contested"]
        assert len(contested) == 1
        assert set(contested[0]["spirits"]) == {"spirit_0", "spirit_1"}
        assert contested[0]["faction"] == "mountain"

    def test_submit_no_action_fails(self):
        gs = make_game(2)
        err = gs.submit_action("spirit_0", {})
        assert err is not None

    def test_idol_limit_per_vagrant_stint(self):
        gs = make_game(2)
        # Both contest same faction so both stay vagrant, but place idols
        neutral = list(gs.hex_map.get_neutral_hexes())
        h0, h1 = neutral[0], neutral[1]
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h0[0], "idol_r": h0[1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "mountain",
            "idol_type": "affluence", "idol_q": h1[0], "idol_r": h1[1],
        })
        gs.resolve_current_phase()

        # Advance back to vagrant phase (resolve remaining phases)
        # Both spirits are still vagrant (contested guide)
        gs.resolve_current_phase()  # agenda (no input needed)
        gs.resolve_current_phase()  # war
        gs.resolve_current_phase()  # scoring
        gs.resolve_current_phase()  # cleanup

        assert gs.phase == Phase.VAGRANT_PHASE
        # spirit_0 should not be able to place another idol
        assert gs.spirits["spirit_0"].has_placed_idol_as_vagrant is True
        options = gs.get_phase_options("spirit_0")
        assert options["can_place_idol"] is False

        # With can_place_idol False, only guide_target is required
        err = gs.submit_action("spirit_0", {
            "guide_target": "mountain",
        })
        assert err is None

    def test_can_place_idol_flag_in_options(self):
        gs = make_game(2)
        options = gs.get_phase_options("spirit_0")
        assert options["can_place_idol"] is True


class TestAgendaPhase:
    def test_agenda_draw(self):
        gs = make_game(2)
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "plains",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        gs.resolve_current_phase()
        assert gs.phase == Phase.AGENDA_PHASE
        # Spirit should be able to draw 1 + 3 = 4 cards (influence starts at 3)
        options = gs.get_phase_options("spirit_0")
        assert options["action"] == "choose_agenda"
        assert len(options["hand"]) == 4

    def test_submit_agenda_choice(self):
        gs = make_game(2)
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "plains",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        gs.resolve_current_phase()

        gs.get_phase_options("spirit_0")
        gs.get_phase_options("spirit_1")
        err = gs.submit_action("spirit_0", {"agenda_index": 0})
        assert err is None


class TestSnapshot:
    def test_snapshot_serialization(self):
        gs = make_game(2)
        snapshot = gs.get_snapshot()
        d = snapshot.to_dict()
        assert "turn" in d
        assert "phase" in d
        assert "factions" in d
        assert "spirits" in d
