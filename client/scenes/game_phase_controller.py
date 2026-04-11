"""Phase-specific UI setup and submission helpers for GameScene."""

from __future__ import annotations

import pygame
from types import SimpleNamespace

from shared.constants import AgendaType, Phase, SCREEN_HEIGHT
from shared.protocol import C2S, SubPhase
from client.renderer.ui_renderer import Button, build_agenda_tooltip


class GamePhaseController:
    """Owns phase/sub-phase specific UI setup and submit behavior."""

    def __init__(self, scene):
        self.scene = scene

    def submit_current_phase(self) -> None:
        scene = self.scene
        if scene.phase == Phase.VAGRANT_PHASE.value:
            can_swell = scene.phase_options.get("can_swell", False)
            payload = {}
            if can_swell:
                payload["swell"] = True
            if scene.selected_faction:
                payload["guide_target"] = scene.selected_faction
            if scene.selected_idol_type and scene.selected_hex:
                payload["idol_type"] = scene.selected_idol_type
                payload["idol_q"] = scene.selected_hex[0]
                payload["idol_r"] = scene.selected_hex[1]
            if payload:
                if scene.selected_faction:
                    scene.preview_guidance = scene.selected_faction
                if scene.selected_idol_type and scene.selected_hex:
                    scene.preview_idol = (
                        scene.selected_idol_type,
                        scene.selected_hex[0],
                        scene.selected_hex[1],
                    )
                scene.app.network.send(C2S.SUBMIT_VAGRANT_ACTION, payload)
                scene._clear_selection()
                scene.has_submitted = True
                if scene.tutorial:
                    scene.tutorial.notify_action("vagrant_submitted", {})
            return

        if scene.phase == Phase.AGENDA_PHASE.value:
            if scene.selected_agenda_index >= 0:
                scene.app.network.send(C2S.SUBMIT_AGENDA_CHOICE, {
                    "agenda_index": scene.selected_agenda_index,
                })
                scene._clear_selection()
                scene.has_submitted = True
                if scene.tutorial:
                    scene.tutorial.notify_action("agenda_submitted", {})
            return

        if scene.phase == SubPhase.EJECTION_CHOICE:
            if (
                scene.selected_ejection_remove_type
                and scene.selected_ejection_add_type
                and scene.selected_ejection_remove_type != scene.selected_ejection_add_type
            ):
                scene.app.network.send(C2S.SUBMIT_EJECTION_AGENDA, {
                    "remove_type": scene.selected_ejection_remove_type,
                    "add_type": scene.selected_ejection_add_type,
                })
                scene._clear_selection()
                scene.ejection_pending = False
                scene.has_submitted = True
                if scene.tutorial:
                    scene.tutorial.notify_action("ejection_submitted", {})
            return

        if scene.phase == SubPhase.SPOILS_CHOICE:
            if all(e.selected >= 0 for e in scene.spoils_entries):
                scene.app.network.send(
                    C2S.SUBMIT_SPOILS_CHOICE,
                    {"card_indices": [e.selected for e in scene.spoils_entries]},
                )
                scene.spoils_entries = []
                scene.has_submitted = True
            return

        if scene.phase == SubPhase.SPOILS_CHANGE_CHOICE:
            if all(e.selected >= 0 for e in scene.spoils_change_entries):
                scene.app.network.send(
                    C2S.SUBMIT_SPOILS_CHANGE_CHOICE,
                    {"card_indices": [e.selected for e in scene.spoils_change_entries]},
                )
                scene.spoils_change_entries = []
                scene.has_submitted = True
            return

        if scene.phase == SubPhase.EXPAND_CHOICE:
            if scene.selected_hex:
                q, r = scene.selected_hex
                scene.app.network.send(C2S.SUBMIT_EXPAND_CHOICE, {"q": q, "r": r})
                scene.expand_choice_hexes = set()
                scene.expand_choice_faction = ""
                scene.selected_hex = None
                scene.has_submitted = True
            return

        if scene.phase == SubPhase.RESPAWN_CHOICE:
            if scene.selected_hex:
                q, r = scene.selected_hex
                scene.app.network.send(C2S.SUBMIT_RESPAWN_CHOICE, {"q": q, "r": r})
                scene.respawn_choice_hexes = set()
                scene.respawn_choice_faction = ""
                scene.selected_hex = None
                scene.has_submitted = True
            return

        if scene.phase == SubPhase.WINNER_CHOICE:
            if len(scene.winner_selections) >= len(scene.winner_choice_wars):
                scene._do_submit_winner_choice()
            return

        if scene.phase == SubPhase.SPOILS_EXPAND_CHOICE:
            if all(s is not None for s in scene.spoils_expand_selections):
                scene._do_submit_spoils_expand_choice()
            return

        if scene.phase == SubPhase.BATTLEGROUND_CHOICE:
            if len(scene.battleground_selections) >= len(scene.battleground_choice_entries):
                scene.app.network.send(
                    C2S.SUBMIT_BATTLEGROUND_CHOICE,
                    {"choices": [
                        {"pair_index": scene.battleground_selections[e["war_id"]]}
                        for e in scene.battleground_choice_entries
                    ]},
                )
                scene.has_submitted = True
            return

        if scene.phase == SubPhase.WAR_SUPPORT_CHOICE:
            if len(scene.war_support_selections) >= len(scene.war_support_entries):
                scene.app.network.send(
                    C2S.SUBMIT_WAR_SUPPORT_CHOICE,
                    {"choices": [
                        {"target": scene.war_support_selections[e["war_id"]]}
                        for e in scene.war_support_entries
                    ]},
                )
                scene.has_submitted = True

    def setup_phase_ui(self) -> None:
        scene = self.scene
        scene._clear_selection()
        scene.has_submitted = False
        action = scene.phase_options.get("action", "none")

        if scene.tutorial:
            if scene.phase == Phase.VAGRANT_PHASE.value and action == "choose":
                scene.tutorial.notify_game_event("vagrant_phase_started", {"turn": scene.turn})
            elif scene.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
                hand = scene.phase_options.get("hand", [])
                scene.tutorial.notify_game_event(
                    "agenda_phase_started",
                    {"turn": scene.turn, "draw_count": len(hand)},
                )
            elif scene.phase == SubPhase.EJECTION_CHOICE:
                scene.tutorial.notify_game_event("ejection_phase_started", {"turn": scene.turn})

        sub_phase_setup = {
            SubPhase.RESTRAIN_CHOICE: self._setup_restrain_choice_ui,
            SubPhase.SHAPING_CHOICE: self._setup_shaping_choice_ui,
            SubPhase.ADAPTATION_CHOICE: self._setup_adaptation_choice_ui,
            SubPhase.CHANGE_CHOICE: self._setup_change_choice_ui,
            SubPhase.SPOILS_CHOICE: self._setup_spoils_choice_ui,
            SubPhase.SPOILS_CHANGE_CHOICE: self._setup_spoils_change_choice_ui,
            SubPhase.SPOILS_EXPAND_CHOICE: self._setup_spoils_expand_choice_ui,
            SubPhase.WINNER_CHOICE: self._setup_winner_choice_ui,
            SubPhase.EJECTION_CHOICE: self._setup_ejection_choice_ui,
            SubPhase.EXPAND_CHOICE: self._setup_expand_choice_ui,
            SubPhase.RESPAWN_CHOICE: self._setup_respawn_choice_ui,
            SubPhase.BATTLEGROUND_CHOICE: self._setup_battleground_choice_ui,
            SubPhase.WAR_SUPPORT_CHOICE: self._setup_war_support_choice_ui,
        }
        if scene.phase in sub_phase_setup:
            sub_phase_setup[scene.phase]()
            return

        scene._setup_main_phase_ui(action)

    def _setup_change_choice_ui(self) -> None:
        scene = self.scene
        scene.change_cards = scene.phase_options.get("cards") or []
        if scene.tutorial:
            my_spirit = scene.spirits.get(scene.app.my_spirit_id, {})
            influence = my_spirit.get("influence", 0)
            scene.tutorial.notify_game_event(
                "change_drawn",
                {"influence": influence, "card_count": len(scene.change_cards)},
            )

    def _setup_restrain_choice_ui(self) -> None:
        scene = self.scene
        scene.change_cards = scene.phase_options.get("cards") or []
        scene.submit_button = None

    def _setup_shaping_choice_ui(self) -> None:
        scene = self.scene
        scene.change_cards = scene.phase_options.get("cards") or []
        scene.submit_button = None

    def _setup_adaptation_choice_ui(self) -> None:
        scene = self.scene
        scene.change_cards = scene.phase_options.get("cards") or []
        scene.submit_button = None

    def _setup_spoils_choice_ui(self) -> None:
        scene = self.scene
        if scene.tutorial:
            scene.tutorial.notify_game_event("guided_spoils_drawn", {})
        choices = scene.phase_options.get("choices", [])
        if choices:
            scene.spoils_entries = [
                SimpleNamespace(cards=c.get("cards", []), loser=c.get("loser", ""), selected=-1)
                for c in choices
            ]
        else:
            cards = scene.phase_options.get("cards", [])
            loser = scene.phase_options.get("loser", "")
            scene.spoils_entries = [SimpleNamespace(cards=cards, loser=loser, selected=-1)] if cards else []
        scene.spoils_display_index = 0
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_spoils_change_choice_ui(self) -> None:
        scene = self.scene
        choices = scene.phase_options.get("choices", [])
        if choices:
            scene.spoils_change_entries = [
                SimpleNamespace(cards=c.get("cards", []), loser=c.get("loser", ""), selected=-1)
                for c in choices
            ]
        else:
            cards = scene.phase_options.get("cards", [])
            loser = scene.phase_options.get("loser", "")
            scene.spoils_change_entries = [SimpleNamespace(cards=cards, loser=loser, selected=-1)] if cards else []
        scene.spoils_display_index = 0
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_ejection_choice_ui(self) -> None:
        scene = self.scene
        scene.ejection_pending = True
        scene.ejection_faction = scene.phase_options.get("faction", "")
        scene.ejection_pool = scene.phase_options.get("agenda_pool", [])
        scene.selected_ejection_remove_type = None
        scene.selected_ejection_add_type = None
        modifiers = scene._get_faction_modifiers(scene.ejection_faction)
        btn_x, btn_w, btn_h, btn_gap = 20, 157, 36, 6
        y_remove = 300
        scene.remove_buttons = []
        seen_types: list[str] = []
        for at_str in scene.ejection_pool:
            if at_str not in seen_types:
                seen_types.append(at_str)
        for i, at_str in enumerate(seen_types):
            tooltip = build_agenda_tooltip(at_str, modifiers)
            btn = Button(
                pygame.Rect(btn_x, y_remove + i * (btn_h + btn_gap), btn_w, btn_h),
                at_str.title(),
                (110, 50, 50),
                tooltip=tooltip,
                tooltip_always=True,
            )
            scene.remove_buttons.append(btn)
        n_remove = len(seen_types)
        y_add = y_remove + n_remove * (btn_h + btn_gap) + 28
        scene.action_buttons = []
        for i, at in enumerate(AgendaType):
            tooltip = build_agenda_tooltip(at.value, modifiers)
            btn = Button(
                pygame.Rect(btn_x, y_add + i * (btn_h + btn_gap), btn_w, btn_h),
                at.value.title(),
                (80, 60, 130),
                tooltip=tooltip,
                tooltip_always=True,
            )
            scene.action_buttons.append(btn)
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_expand_choice_ui(self) -> None:
        scene = self.scene
        hexes = scene.phase_options.get("hexes", [])
        scene.expand_choice_hexes = {(h["q"], h["r"]) for h in hexes}
        scene.expand_choice_faction = scene.phase_options.get("faction", "")
        scene.selected_hex = None
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_respawn_choice_ui(self) -> None:
        scene = self.scene
        hexes = scene.phase_options.get("hexes", [])
        scene.respawn_choice_hexes = {(h["q"], h["r"]) for h in hexes}
        scene.respawn_choice_faction = scene.phase_options.get("faction", "")
        scene.selected_hex = None
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_winner_choice_ui(self) -> None:
        scene = self.scene
        wars = scene.phase_options.get("choices", [])
        scene.winner_choice_wars = wars
        scene.winner_selections = {}
        scene.winner_choice_buttons = []
        btn_y = 200
        for wc in wars:
            fa = wc["faction_a"]
            fb = wc["faction_b"]
            rect_a = pygame.Rect(40, btn_y, 180, 44)
            rect_b = pygame.Rect(240, btn_y, 180, 44)
            scene.winner_choice_buttons.append({"war_id": wc["war_id"], "faction": fa, "rect": rect_a})
            scene.winner_choice_buttons.append({"war_id": wc["war_id"], "faction": fb, "rect": rect_b})
            btn_y += 60
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_spoils_expand_choice_ui(self) -> None:
        scene = self.scene
        choices = scene.phase_options.get("choices", [])
        scene.spoils_expand_choices = choices
        scene.spoils_expand_display_index = 0
        scene.spoils_expand_selections = [None] * len(choices)
        scene._refresh_spoils_expand_hex_set()
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_battleground_choice_ui(self) -> None:
        scene = self.scene
        scene.battleground_choice_entries = scene.phase_options.get("choices", [])
        scene.battleground_choice_index = 0
        scene.battleground_choice_buttons = []
        scene.battleground_selections = {}
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))

    def _setup_war_support_choice_ui(self) -> None:
        scene = self.scene
        scene.war_support_entries = scene.phase_options.get("choices", [])
        scene.war_support_buttons = []
        scene.war_support_selections = {}
        scene.submit_button = Button(pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48), "Confirm", (60, 130, 60))
