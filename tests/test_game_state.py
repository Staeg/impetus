"""Tests for game state machine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.constants import Phase, AgendaType, IdolType, ChangeModifierTarget
from server.game_state import GameState


def make_game(num_players=3):
    gs = GameState()
    players = [{"spirit_id": f"spirit_{i}", "name": f"Player {i}"} for i in range(num_players)]
    gs.setup_game(players)
    return gs


def clear_affinities(gs):
    """Remove all spirit affinities so contested guidance resolves via normal rules."""
    for spirit in gs.spirits.values():
        spirit.habitat_affinity = ""
        spirit.race_affinity = ""


def neutral_hexes(gs, n=2):
    """Get n guaranteed-neutral hex coordinates from the game state."""
    return list(gs.hex_map.get_neutral_hexes())[:n]


class TestGameStateSetup:
    def test_initial_phase(self):
        gs = make_game()
        assert gs.phase == Phase.VAGRANT_PHASE

    def test_initial_turn(self):
        gs = make_game()
        assert gs.turn == 2

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
                    # due to opening automated turns resolving Trade/Steal)
                    assert other_fid in faction.regard

    def test_habitat_starting_modifiers(self):
        from shared.constants import HABITAT_STARTING_MODIFIERS
        gs = GameState()
        players = [{"spirit_id": f"s{i}", "name": f"P{i}"} for i in range(3)]
        initial_snapshot, _ = gs.setup_game(players)
        for fid, expected in HABITAT_STARTING_MODIFIERS.items():
            faction_state = initial_snapshot.factions[fid]
            for modifier, count in expected.items():
                actual = faction_state.change_modifiers.get(modifier.value, 0)
                assert actual == count, f"{fid} {modifier}: expected {count}, got {actual}"

    def test_automated_turn_wars_erupt(self, monkeypatch):
        # Mountain's habitat gives it Steal ×1; force its automated Turn 1
        # agenda to Steal so a war is declared.
        agenda_calls = {"n": 0}

        def fake_choice(seq):
            if seq and hasattr(seq[0], "agenda_type"):
                agenda_calls["n"] += 1
                if agenda_calls["n"] == 1:
                    for card in seq:
                        if card.agenda_type == AgendaType.STEAL:
                            return card
            return seq[0]

        monkeypatch.setattr("random.choice", fake_choice)

        gs = make_game()
        assert gs.turn == 2
        assert len(gs.wars) > 0
        # Wars erupt and ripen within the same automated turn's war phase.
        assert all(w.is_ripe for w in gs.wars)


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
        # Clear affinities so no spirit has an advantage — normal contest applies
        gs.spirits["spirit_0"].habitat_affinity = ""
        gs.spirits["spirit_0"].race_affinity = ""
        gs.spirits["spirit_1"].habitat_affinity = ""
        gs.spirits["spirit_1"].race_affinity = ""
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
        clear_affinities(gs)
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

    def test_contested_guidance_cooldown(self):
        """Contested guidance blocks the faction for 1 turn, then expires."""
        gs = make_game(2)
        clear_affinities(gs)
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "mountain",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        gs.resolve_current_phase()  # resolve vagrant phase

        # Cooldown is set immediately after the contested guidance resolves.
        # Check this now, before running war phases that might eliminate mountain.
        assert "mountain" in gs.guidance_cooldowns.get("spirit_0", set())
        assert "mountain" in gs.guidance_cooldowns.get("spirit_1", set())
        err = gs.submit_action("spirit_0", {"guide_target": "mountain"})
        assert err is not None  # blocked by cooldown

        # Advance to next vagrant phase. Use a loop rather than a fixed count:
        # the agenda phase can take 2 calls when a guided faction draws Change,
        # and wars from automated setup turns may eliminate factions.
        for _ in range(10):
            if gs.phase == Phase.VAGRANT_PHASE:
                break
            gs.resolve_current_phase()

        # If mountain survived wars, verify it appears as contested-blocked.
        if not gs.factions["mountain"].eliminated:
            opts0 = gs.get_phase_options("spirit_0")
            assert "mountain" not in opts0["available_factions"]
            assert "mountain" in opts0["contested_blocked"]

        # Guide different factions instead, advance a full turn
        gs.pending_actions.clear()
        gs.submit_action("spirit_0", {"guide_target": "mesa"})
        gs.submit_action("spirit_1", {"guide_target": "plains"})
        gs.resolve_current_phase()  # vagrant — clears cooldowns
        assert gs.spirits["spirit_0"].guided_faction == "mesa"

        # Eject to become vagrant again, advance to next vagrant phase.
        # spirit_1 still guides plains, so agenda phase may block for change
        # choices — loop until VAGRANT rather than using a fixed count.
        gs.spirits["spirit_0"].become_vagrant()
        gs.factions["mesa"].guiding_spirit = None
        for _ in range(10):
            if gs.phase == Phase.VAGRANT_PHASE:
                break
            gs.resolve_current_phase()

        # Cooldown expired: mountain available again (if not eliminated by wars)
        if not gs.factions["mountain"].eliminated:
            opts0 = gs.get_phase_options("spirit_0")
            assert "mountain" in opts0["available_factions"]

    def test_submit_no_action_fails(self):
        gs = make_game(2)
        err = gs.submit_action("spirit_0", {})
        assert err is not None

    def test_idol_limit_per_vagrant_stint(self):
        gs = make_game(2)
        clear_affinities(gs)
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
        # (mountain is contested-blocked, so pick a different faction)
        err = gs.submit_action("spirit_0", {
            "guide_target": "mesa",
        })
        assert err is None

    def test_can_place_idol_flag_in_options(self):
        gs = make_game(2)
        options = gs.get_phase_options("spirit_0")
        assert options["can_place_idol"] is True

    def test_habitat_affinity_wins_contest(self):
        """A spirit with habitat affinity guides the faction; others waste their turn."""
        gs = make_game(2)
        clear_affinities(gs)
        gs.spirits["spirit_0"].habitat_affinity = "mountain"  # matches mountain faction
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
        # spirit_0 has habitat affinity → wins
        assert gs.spirits["spirit_0"].is_vagrant is False
        assert gs.spirits["spirit_0"].guided_faction == "mountain"
        assert gs.spirits["spirit_1"].is_vagrant is True
        # No cooldown for either (affinity resolved the contest)
        assert "mountain" not in gs.guidance_cooldowns.get("spirit_0", set())
        assert "mountain" not in gs.guidance_cooldowns.get("spirit_1", set())
        # Loser gets a guide_contested event, winner gets guided event
        guided = [e for e in events if e["type"] == "guided"]
        assert len(guided) == 1 and guided[0]["spirit"] == "spirit_0"
        contested = [e for e in events if e["type"] == "guide_contested"]
        assert len(contested) == 1
        assert contested[0]["spirits"] == ["spirit_1"]
        assert contested[0].get("won_by_affinity") == "spirit_0"

    def test_race_affinity_wins_contest(self):
        """A spirit with race affinity wins when no habitat affinity is present."""
        gs = make_game(2)
        clear_affinities(gs)
        mountain_race = gs.factions["mountain"].race
        gs.spirits["spirit_0"].race_affinity = mountain_race
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
        assert gs.spirits["spirit_0"].guided_faction == "mountain"
        assert gs.spirits["spirit_1"].is_vagrant is True
        assert "mountain" not in gs.guidance_cooldowns.get("spirit_0", set())
        assert "mountain" not in gs.guidance_cooldowns.get("spirit_1", set())

    def test_habitat_beats_race_affinity(self):
        """Habitat affinity beats race affinity when both spirits have different affinities."""
        gs = make_game(2)
        clear_affinities(gs)
        mountain_race = gs.factions["mountain"].race
        gs.spirits["spirit_0"].habitat_affinity = "mountain"  # habitat match
        gs.spirits["spirit_1"].race_affinity = mountain_race   # race match
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "mountain",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        gs.resolve_current_phase()
        # Habitat wins over race
        assert gs.spirits["spirit_0"].guided_faction == "mountain"
        assert gs.spirits["spirit_1"].is_vagrant is True

    def test_tied_habitat_affinities_normal_contest(self):
        """Two spirits with habitat affinity tie — normal contest applies (cooldown set)."""
        gs = make_game(2)
        clear_affinities(gs)
        gs.spirits["spirit_0"].habitat_affinity = "mountain"
        gs.spirits["spirit_1"].habitat_affinity = "mountain"
        h = neutral_hexes(gs)
        gs.submit_action("spirit_0", {
            "guide_target": "mountain",
            "idol_type": "battle", "idol_q": h[0][0], "idol_r": h[0][1],
        })
        gs.submit_action("spirit_1", {
            "guide_target": "mountain",
            "idol_type": "affluence", "idol_q": h[1][0], "idol_r": h[1][1],
        })
        gs.resolve_current_phase()
        # Both fail — normal contest
        assert gs.spirits["spirit_0"].is_vagrant is True
        assert gs.spirits["spirit_1"].is_vagrant is True
        assert "mountain" in gs.guidance_cooldowns.get("spirit_0", set())
        assert "mountain" in gs.guidance_cooldowns.get("spirit_1", set())


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
