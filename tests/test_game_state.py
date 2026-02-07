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


class TestGameStateSetup:
    def test_initial_phase(self):
        gs = make_game()
        assert gs.phase == Phase.VAGRANT_PHASE

    def test_initial_turn(self):
        gs = make_game()
        assert gs.turn == 1

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
                    # due to setup turn resolving Bond/Steal)
                    assert other_fid in faction.regard


class TestVagrantPhase:
    def test_needs_input(self):
        gs = make_game(2)
        assert gs.needs_input("spirit_0") is True
        assert gs.needs_input("spirit_1") is True

    def test_submit_possess(self):
        gs = make_game(2)
        err = gs.submit_action("spirit_0", {"action_type": "possess", "target": "mountain"})
        assert err is None

    def test_submit_idol(self):
        gs = make_game(2)
        err = gs.submit_action("spirit_0", {
            "action_type": "place_idol",
            "idol_type": "battle",
            "q": 0, "r": 0,
        })
        assert err is None

    def test_invalid_possess_target(self):
        gs = make_game(2)
        err = gs.submit_action("spirit_0", {"action_type": "possess", "target": "nonexistent"})
        assert err is not None

    def test_resolve_possess(self):
        gs = make_game(2)
        gs.submit_action("spirit_0", {"action_type": "possess", "target": "mountain"})
        gs.submit_action("spirit_1", {"action_type": "possess", "target": "plains"})
        events = gs.resolve_current_phase()
        assert gs.phase == Phase.AGENDA_PHASE
        assert gs.spirits["spirit_0"].possessed_faction == "mountain"
        assert gs.spirits["spirit_0"].influence == 3
        assert gs.factions["mountain"].possessing_spirit == "spirit_0"

    def test_contested_possess(self):
        gs = make_game(2)
        gs.submit_action("spirit_0", {"action_type": "possess", "target": "mountain"})
        gs.submit_action("spirit_1", {"action_type": "possess", "target": "mountain"})
        events = gs.resolve_current_phase()
        assert gs.spirits["spirit_0"].is_vagrant is True
        assert gs.spirits["spirit_1"].is_vagrant is True
        assert gs.factions["mountain"].possessing_spirit is None

    def test_idol_placement(self):
        gs = make_game(2)
        gs.submit_action("spirit_0", {
            "action_type": "place_idol", "idol_type": "battle", "q": 0, "r": 0,
        })
        gs.submit_action("spirit_1", {
            "action_type": "place_idol", "idol_type": "affluence", "q": 2, "r": 0,
        })
        events = gs.resolve_current_phase()
        assert len(gs.hex_map.idols) == 2
        assert len(gs.spirits["spirit_0"].idols) == 1


class TestAgendaPhase:
    def test_agenda_draw(self):
        gs = make_game(2)
        gs.submit_action("spirit_0", {"action_type": "possess", "target": "mountain"})
        gs.submit_action("spirit_1", {"action_type": "possess", "target": "plains"})
        gs.resolve_current_phase()
        assert gs.phase == Phase.AGENDA_PHASE
        # Spirit should be able to draw 1 + 3 = 4 cards (influence starts at 3)
        options = gs.get_phase_options("spirit_0")
        assert options["action"] == "choose_agenda"
        assert len(options["hand"]) == 4

    def test_submit_agenda_choice(self):
        gs = make_game(2)
        gs.submit_action("spirit_0", {"action_type": "possess", "target": "mountain"})
        gs.submit_action("spirit_1", {"action_type": "possess", "target": "plains"})
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
