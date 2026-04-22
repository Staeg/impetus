from __future__ import annotations

from typing import Any

from shared.constants import Phase
from shared.protocol import C2S, S2C, SubPhase
from shared.protocol import create_message, parse_message
from server import ai

from client.tutorials.bootstrap import TutorialBootstrapResult


class LocalTutorialTransport:
    def __init__(self, bootstrap_result: TutorialBootstrapResult):
        self.bootstrap_result = bootstrap_result
        self.game_state = bootstrap_result.game_state
        self.human_spirit_id = bootstrap_result.human_spirit_id
        self.scripted_actions = bootstrap_result.scripted_actions
        self._incoming: list[tuple[str, dict[str, Any]]] = []
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._enqueue(S2C.GAME_START, self.game_state.get_snapshot().to_dict())
        if self.bootstrap_result.intro_events:
            self._enqueue_phase_result(self.bootstrap_result.intro_events)
        self._advance_until_input()

    def connect(self, host, port):
        return None

    def disconnect(self):
        self._connected = False

    def stop(self):
        self.disconnect()

    def poll(self):
        if self._incoming:
            return self._incoming.pop(0)
        return None

    def poll_all(self):
        messages = list(self._incoming)
        self._incoming.clear()
        return messages

    def send(self, msg_type: str, payload: dict | None = None):
        if not self._connected:
            return
        payload = payload or {}
        if msg_type == C2S.SUBMIT_VAGRANT_ACTION:
            error = self.game_state.submit_action(self.human_spirit_id, payload)
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            self._apply_scripted_actions(Phase.VAGRANT_PHASE.value)
            self._resolve_vagrant_if_ready()
            return
        if msg_type == C2S.SUBMIT_AGENDA_CHOICE:
            error = self.game_state.submit_action(self.human_spirit_id, payload)
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            self._apply_scripted_actions(Phase.AGENDA_PHASE.value)
            self._resolve_agenda_if_ready()
            return
        if msg_type == C2S.SUBMIT_EXPAND_CHOICE:
            error = self.game_state.submit_expand_choice(self.human_spirit_id, int(payload.get("q", 0)), int(payload.get("r", 0)))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            self._resolve_change_or_agendas()
            return
        if msg_type == C2S.SUBMIT_CHANGE_CHOICE:
            error, events = self.game_state.submit_change_choice(self.human_spirit_id, int(payload.get("card_index", 0)))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            if events:
                self._enqueue_phase_result(events)
            self._resolve_change_or_agendas()
            return
        if msg_type == C2S.SUBMIT_EJECTION_AGENDA:
            error = self.game_state.submit_ejection_choice(
                self.human_spirit_id,
                payload.get("remove_type", ""),
                payload.get("add_type", ""),
            )
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            self._enqueue_phase_result(self.game_state.finalize_sub_choices())
            self._advance_until_input()
            return
        if msg_type == C2S.SUBMIT_WINNER_CHOICE:
            error, events = self.game_state.submit_winner_choice(self.human_spirit_id, payload.get("choices", []))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            if events:
                self._enqueue_phase_result(events)
            self._advance_until_input()
            return
        if msg_type == C2S.SUBMIT_SPOILS_CHOICE:
            error, events = self.game_state.submit_spoils_choice(self.human_spirit_id, payload.get("card_indices", []))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            if events:
                self._enqueue_phase_result(events)
            self._advance_until_input()
            return
        if msg_type == C2S.SUBMIT_SPOILS_CHANGE_CHOICE:
            error, events = self.game_state.submit_spoils_change_choice(self.human_spirit_id, payload.get("card_indices", []))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            if events:
                self._enqueue_phase_result(events)
            self._advance_until_input()
            return
        if msg_type == C2S.SUBMIT_SPOILS_EXPAND_CHOICE:
            error, events = self.game_state.submit_spoils_expand_choice(self.human_spirit_id, payload.get("choices", []))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            if events:
                self._enqueue_phase_result(events)
            self._advance_until_input()
            return
        if msg_type == C2S.SUBMIT_RESPAWN_CHOICE:
            error, events = self.game_state.submit_respawn_choice(self.human_spirit_id, int(payload.get("q", 0)), int(payload.get("r", 0)))
            if error:
                self._enqueue(S2C.ERROR, {"message": error})
                return
            if events:
                self._enqueue_phase_result(events)
            self._advance_until_input()

    def _apply_scripted_actions(self, phase_key: str) -> None:
        for spirit_id, action in self.scripted_actions.get(phase_key, {}).items():
            if self.game_state.needs_input(spirit_id) and spirit_id not in self.game_state.pending_actions:
                self.game_state.submit_action(spirit_id, action)

    def _resolve_vagrant_if_ready(self) -> None:
        if not self.game_state.all_inputs_received():
            return
        self._enqueue_phase_result(self.game_state.resolve_current_phase())
        self._advance_until_input()

    def _resolve_agenda_if_ready(self) -> None:
        if not self.game_state.all_inputs_received():
            return
        change_events = self.game_state.prepare_change_choices()
        if change_events:
            self._enqueue_phase_result(change_events)
        self.game_state.prepare_expand_choices()
        self._resolve_change_or_agendas()

    def _resolve_change_or_agendas(self) -> None:
        for spirit_id, faction_id in list(self.game_state.expand_pending.items()):
            if spirit_id == self.human_spirit_id:
                continue
            allow_enemy = "Special Military Operations" in self.game_state.factions[faction_id].shaping_effects
            reachable = list(self.game_state.hex_map.get_expand_targets(faction_id, allow_enemy=allow_enemy))
            if reachable:
                self.game_state.submit_expand_choice(spirit_id, reachable[0][0], reachable[0][1])
        for spirit_id, cards in list(self.game_state.change_pending.items()):
            if spirit_id == self.human_spirit_id:
                continue
            self.game_state.submit_change_choice(spirit_id, ai.get_ai_change_choice(cards))
        if self.human_spirit_id in self.game_state.expand_pending:
            self._send_expand_prompt()
            return
        if self.human_spirit_id in self.game_state.change_pending:
            self._send_change_prompt()
            return
        self._enqueue_phase_result(self.game_state.resolve_agenda_phase_after_changes())
        self._advance_until_input()

    def _advance_until_input(self) -> None:
        while True:
            if self.game_state.phase == Phase.WAR_PHASE:
                self._auto_resolve_ai_winner_choices()
                if self.human_spirit_id in self.game_state.winner_choice_pending:
                    self._send_phase_start(SubPhase.WINNER_CHOICE, {"choices": self.game_state.winner_choice_pending[self.human_spirit_id]})
                    return
                if self.human_spirit_id in self.game_state.spoils_pending:
                    self._send_spoils_prompt()
                    return
                if self.human_spirit_id in self.game_state.respawn_pending:
                    self._send_respawn_prompt()
                    return
                events = self.game_state.resolve_current_phase()
                if events:
                    self._enqueue_phase_result(events)
                if self.game_state.phase == Phase.GAME_OVER:
                    self._enqueue(S2C.GAME_OVER, self._game_over_payload())
                    return
                continue
            if self.game_state.phase == Phase.SCORING:
                events = self.game_state.resolve_current_phase()
                if events:
                    self._enqueue_phase_result(events)
                if self.human_spirit_id in self.game_state.ejection_pending:
                    self._send_ejection_prompt()
                    return
                if self.game_state.phase == Phase.GAME_OVER:
                    self._enqueue(S2C.GAME_OVER, self._game_over_payload())
                    return
                continue
            if self.game_state.phase == Phase.CLEANUP:
                events = self.game_state.resolve_current_phase()
                if events:
                    self._enqueue_phase_result(events)
                continue
            if self.game_state.phase in (Phase.VAGRANT_PHASE, Phase.AGENDA_PHASE):
                if self.game_state.needs_input(self.human_spirit_id):
                    self._send_main_phase_prompt()
                    return
                self._apply_scripted_actions(self.game_state.phase.value)
                if self.game_state.all_inputs_received():
                    if self.game_state.phase == Phase.VAGRANT_PHASE:
                        self._resolve_vagrant_if_ready()
                    else:
                        self._resolve_agenda_if_ready()
                return
            return

    def _auto_resolve_ai_winner_choices(self) -> None:
        for spirit_id, entries in list(self.game_state.winner_choice_pending.items()):
            if spirit_id == self.human_spirit_id:
                continue
            error, events = self.game_state.submit_winner_choice(spirit_id, ai.get_ai_winner_choice(entries))
            if not error and events:
                self._enqueue_phase_result(events)

    def _send_main_phase_prompt(self) -> None:
        options = self.game_state.get_phase_options(self.human_spirit_id)
        self._send_phase_start(self.game_state.phase.value, options)

    def _send_change_prompt(self) -> None:
        cards = self.game_state.change_pending[self.human_spirit_id]
        self._send_phase_start(SubPhase.CHANGE_CHOICE, {"cards": [card.value for card in cards]})

    def _send_expand_prompt(self) -> None:
        faction_id = self.game_state.expand_pending[self.human_spirit_id]
        allow_enemy = "Special Military Operations" in self.game_state.factions[faction_id].shaping_effects
        hexes = [{"q": q, "r": r} for q, r in sorted(self.game_state.hex_map.get_expand_targets(faction_id, allow_enemy=allow_enemy))]
        self._send_phase_start(SubPhase.EXPAND_CHOICE, {"faction": faction_id, "hexes": hexes})

    def _send_ejection_prompt(self) -> None:
        faction_id = self.game_state.ejection_pending[self.human_spirit_id]
        agenda_pool = [card.agenda_type.value for card in self.game_state.factions[faction_id].agenda_pool]
        self._send_phase_start(SubPhase.EJECTION_CHOICE, {"faction": faction_id, "agenda_pool": agenda_pool})

    def _send_spoils_prompt(self) -> None:
        pending_list = self.game_state.spoils_pending[self.human_spirit_id]
        change_pendings = [p for p in pending_list if p.stage == SubPhase.CHANGE_CHOICE]
        expand_pendings = [p for p in pending_list if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
        if change_pendings:
            self._send_phase_start(SubPhase.SPOILS_CHANGE_CHOICE, {"choices": [{"cards": [card.value for card in p.change_cards], "loser": p.loser} for p in change_pendings]})
            return
        if expand_pendings:
            self._send_phase_start(SubPhase.SPOILS_EXPAND_CHOICE, {"choices": [{"loser": p.loser, "available_hexes": [{"q": q, "r": r} for q, r in p.expand_hexes]} for p in expand_pendings]})
            return
        self._send_phase_start(SubPhase.SPOILS_CHOICE, {"choices": [{"cards": [card.value for card in p.cards], "loser": p.loser} for p in pending_list]})

    def _send_respawn_prompt(self) -> None:
        neutral_hexes = [{"q": q, "r": r} for q, r in sorted(self.game_state.hex_map.get_neutral_hexes())]
        self._send_phase_start(SubPhase.RESPAWN_CHOICE, {"faction": self.game_state.respawn_pending[self.human_spirit_id], "hexes": neutral_hexes})

    def _send_phase_start(self, phase: str, options: dict[str, Any]) -> None:
        self._enqueue(S2C.PHASE_START, {"phase": phase, "turn": self.game_state.turn, "options": options})
        self._enqueue(S2C.WAITING_FOR, {"players_remaining": [self.human_spirit_id]})

    def _enqueue_phase_result(self, events: list[dict[str, Any]]) -> None:
        self._enqueue(S2C.PHASE_RESULT, {
            "phase": self.game_state.phase.value if hasattr(self.game_state.phase, "value") else self.game_state.phase,
            "events": events,
            "state": self.game_state.get_snapshot().to_dict(),
        })

    def _enqueue(self, msg_type: str, payload: dict[str, Any]) -> None:
        self._incoming.append(parse_message(create_message(msg_type, payload)))

    def _game_over_payload(self) -> dict[str, Any]:
        max_vp = max(spirit.victory_points for spirit in self.game_state.spirits.values())
        winners = [sid for sid, spirit in self.game_state.spirits.items() if spirit.victory_points == max_vp]
        return {
            "winners": winners,
            "scores": {sid: spirit.victory_points for sid, spirit in self.game_state.spirits.items()},
        }
