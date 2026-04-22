from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from shared.constants import AgendaType, IdolType, Phase, STARTING_INFLUENCE
from shared.models import AgendaCard, HexCoord
from shared.protocol import SubPhase
from server.game_state import GameState, SpoilsPendingEntry
from server.war import War


HUMAN_SPIRIT_ID = "tutorial_player"
HUMAN_NAME = "Player"


@dataclass
class TutorialBootstrapResult:
    game_state: GameState
    human_spirit_id: str = HUMAN_SPIRIT_ID
    scripted_actions: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    intro_events: list[dict[str, Any]] = field(default_factory=list)


def _make_game(player_count: int = 1, seed: int = 7) -> GameState:
    random.seed(seed)
    gs = GameState()
    players = [{"spirit_id": HUMAN_SPIRIT_ID, "name": HUMAN_NAME}]
    for idx in range(1, player_count):
        players.append({"spirit_id": f"tutorial_ai_{idx}", "name": f"Rival {idx}"})
    gs.setup_game(players, enabled_eras={gs.current_era})
    for faction in gs.factions.values():
        faction.reset_turn_tracking()
        faction.played_agenda_this_turn.clear()
    gs.wars.clear()
    gs.pending_actions.clear()
    gs.drawn_hands.clear()
    gs.change_pending.clear()
    gs.expand_pending.clear()
    gs.expand_chosen.clear()
    gs.ejection_pending.clear()
    gs.spoils_pending.clear()
    gs.auto_spoils_choices.clear()
    gs.winner_choice_pending.clear()
    gs.respawn_pending.clear()
    gs._stored_agenda_choices = {}
    gs._guided_change_factions = []
    gs._guided_change_modifiers = {}
    return gs


def _clear_guidance(gs: GameState) -> None:
    for spirit in gs.spirits.values():
        spirit.become_vagrant()
    for faction in gs.factions.values():
        faction.guiding_spirit = None


def _guide(gs: GameState, spirit_id: str, faction_id: str, influence: int = STARTING_INFLUENCE) -> None:
    spirit = gs.spirits[spirit_id]
    spirit.guide_faction(faction_id)
    spirit.influence = influence
    gs.factions[faction_id].guiding_spirit = spirit_id


def _place_idol(gs: GameState, spirit_id: str, idol_type: IdolType, pos: tuple[int, int]) -> None:
    spirit = gs.spirits[spirit_id]
    idol = spirit.place_idol(idol_type, HexCoord(*pos))
    gs.hex_map.place_idol(idol)


def board_reading_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=1)
    gs.phase = Phase.VAGRANT_PHASE
    gs.turn = 2
    neutral_hex = sorted(gs.hex_map.get_neutral_hexes())[0]
    _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.BATTLE, neutral_hex)
    return TutorialBootstrapResult(game_state=gs)


def vagrant_guidance_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=2)
    _clear_guidance(gs)
    gs.phase = Phase.VAGRANT_PHASE
    gs.turn = 2
    return TutorialBootstrapResult(game_state=gs)


def trade_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=3)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.phase = Phase.AGENDA_PHASE
    gs.turn = 3
    gs.drawn_hands[HUMAN_SPIRIT_ID] = [
        AgendaCard(AgendaType.TRADE),
        AgendaCard(AgendaType.EXPAND),
        AgendaCard(AgendaType.STEAL),
    ]
    return TutorialBootstrapResult(game_state=gs)


def expand_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=4)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.factions["mountain"].gold = 4
    gs.phase = Phase.AGENDA_PHASE
    gs.turn = 3
    gs.drawn_hands[HUMAN_SPIRIT_ID] = [AgendaCard(AgendaType.EXPAND)]
    return TutorialBootstrapResult(game_state=gs)


def failed_expand_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=5)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.factions["mountain"].gold = 0
    gs.phase = Phase.AGENDA_PHASE
    gs.turn = 3
    gs.drawn_hands[HUMAN_SPIRIT_ID] = [AgendaCard(AgendaType.EXPAND)]
    return TutorialBootstrapResult(game_state=gs)


def change_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=6)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.phase = Phase.AGENDA_PHASE
    gs.turn = 3
    gs.drawn_hands[HUMAN_SPIRIT_ID] = [AgendaCard(AgendaType.CHANGE)]
    return TutorialBootstrapResult(game_state=gs)


def steal_war_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=7)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.factions["mesa"].gold = 3
    gs.factions["mountain"].regard["mesa"] = -1
    gs.factions["mesa"].regard["mountain"] = -1
    gs.phase = Phase.AGENDA_PHASE
    gs.turn = 3
    gs.drawn_hands[HUMAN_SPIRIT_ID] = [AgendaCard(AgendaType.STEAL)]
    return TutorialBootstrapResult(game_state=gs)


def war_scoring_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=8)
    _clear_guidance(gs)
    gs.phase = Phase.WAR_PHASE
    gs.turn = 3
    gs.wars.append(War("mountain", "mesa", declared_turn=3))
    gs.factions["mountain"].worship_spirit = HUMAN_SPIRIT_ID
    _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.BATTLE, next(iter(gs.hex_map.get_faction_territories("mountain"))))
    return TutorialBootstrapResult(game_state=gs)


def worship_scoring_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=9)
    _clear_guidance(gs)
    gs.phase = Phase.SCORING
    gs.turn = 4
    gs.factions["mountain"].worship_spirit = HUMAN_SPIRIT_ID
    gs.factions["mountain"].gold_gained_this_turn = 3
    gs.factions["mountain"].territories_gained_this_turn = 1
    gs.factions["mountain"].wars_won_this_turn = 1
    mountain_hex = sorted(gs.hex_map.get_faction_territories("mountain"))[0]
    _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.BATTLE, mountain_hex)
    _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.AFFLUENCE, mountain_hex)
    _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.SPREAD, mountain_hex)
    return TutorialBootstrapResult(game_state=gs)


def contested_guidance_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(player_count=2, seed=10)
    _clear_guidance(gs)
    gs.phase = Phase.VAGRANT_PHASE
    gs.turn = 2
    for spirit in gs.spirits.values():
        spirit.habitat_affinity = ""
        spirit.race_affinity = ""
    rival_id = "tutorial_ai_1"
    neutral_hexes = sorted(gs.hex_map.get_neutral_hexes())
    scripted = {
        Phase.VAGRANT_PHASE.value: {
            rival_id: {
                "guide_target": "mountain",
                "idol_type": IdolType.AFFLUENCE.value,
                "idol_q": neutral_hexes[1][0],
                "idol_r": neutral_hexes[1][1],
            }
        }
    }
    return TutorialBootstrapResult(game_state=gs, scripted_actions=scripted)


def worship_timing_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(player_count=2, seed=11)
    _clear_guidance(gs)
    rival_id = "tutorial_ai_1"
    _guide(gs, rival_id, "mountain", influence=1)
    gs.factions["mountain"].worship_spirit = rival_id
    mountain_hex = next(iter(gs.hex_map.get_faction_territories("mountain")))
    _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.SPREAD, mountain_hex)
    _place_idol(gs, rival_id, IdolType.BATTLE, mountain_hex)
    gs.phase = Phase.VAGRANT_PHASE
    gs.turn = 4
    gs.spirits[rival_id].become_vagrant()
    gs.factions["mountain"].guiding_spirit = None
    return TutorialBootstrapResult(game_state=gs)


def ejection_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=12)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=0)
    gs.phase = Phase.SCORING
    gs.turn = 5
    gs.ejection_pending[HUMAN_SPIRIT_ID] = "mountain"
    return TutorialBootstrapResult(game_state=gs)


def winner_choice_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=13)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=1)
    gs.phase = Phase.WAR_PHASE
    gs.turn = 4
    gs.winner_choice_pending[HUMAN_SPIRIT_ID] = [{
        "war_id": "war-1",
        "faction_a": "mountain",
        "faction_b": "mesa",
        "guided_faction": "mountain",
    }]
    return TutorialBootstrapResult(game_state=gs)


def spoils_choice_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=14)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.phase = Phase.WAR_PHASE
    gs.turn = 4
    gs.spoils_pending[HUMAN_SPIRIT_ID] = [
        SpoilsPendingEntry("mountain", "mesa", [AgendaType.TRADE, AgendaType.CHANGE]),
        SpoilsPendingEntry("mountain", "sand", [AgendaType.EXPAND, AgendaType.STEAL]),
    ]
    return TutorialBootstrapResult(game_state=gs)


def spoils_change_bootstrap() -> TutorialBootstrapResult:
    from shared.constants import CHANGE_DECK

    gs = _make_game(seed=15)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.phase = Phase.WAR_PHASE
    gs.turn = 4
    pending = SpoilsPendingEntry("mountain", "mesa", [AgendaType.CHANGE])
    pending.stage = SubPhase.CHANGE_CHOICE
    pending.change_cards = CHANGE_DECK[:3]
    gs.spoils_pending[HUMAN_SPIRIT_ID] = [pending]
    return TutorialBootstrapResult(game_state=gs)


def spoils_expand_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=16)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=2)
    gs.phase = Phase.WAR_PHASE
    gs.turn = 4
    pending = SpoilsPendingEntry("mountain", "mesa", [AgendaType.EXPAND])
    pending.stage = SubPhase.SPOILS_EXPAND_CHOICE
    pending.expand_hexes = sorted(gs.hex_map.get_faction_territories("mesa"))
    gs.spoils_pending[HUMAN_SPIRIT_ID] = [pending]
    return TutorialBootstrapResult(game_state=gs)


def respawn_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=17)
    _clear_guidance(gs)
    _guide(gs, HUMAN_SPIRIT_ID, "mountain", influence=1)
    gs.phase = Phase.WAR_PHASE
    gs.turn = 4
    for hex_coord, owner in list(gs.hex_map.ownership.items()):
        if owner == "mountain":
            gs.hex_map.ownership[hex_coord] = None
    gs.factions["mountain"].gold = 5
    gs.respawn_pending[HUMAN_SPIRIT_ID] = "mountain"
    return TutorialBootstrapResult(game_state=gs)


def unguided_behavior_bootstrap() -> TutorialBootstrapResult:
    gs = _make_game(seed=18)
    _clear_guidance(gs)
    gs.phase = Phase.AGENDA_PHASE
    gs.turn = 3
    plains_targets = sorted(gs.hex_map.get_reachable_neutral_hexes("plains"))
    if plains_targets:
        _place_idol(gs, HUMAN_SPIRIT_ID, IdolType.SPREAD, plains_targets[0])
    gs.factions["plains"].gold = 5
    return TutorialBootstrapResult(game_state=gs)
