"""Primary gameplay scene: hex map, UI, phases."""

import pygame
from shared.constants import (
    MessageType, Phase, AgendaType, IdolType, MAP_SIDE_LENGTH,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES, FACTION_DISPLAY_NAMES, FACTION_COLORS,
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP,
)
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import UIRenderer, Button, build_agenda_tooltip, build_modifier_tooltip, draw_dotted_underline
from client.renderer.animation import AnimationManager, TextAnimation
from client.renderer.assets import load_assets, agenda_card_images
from client.input_handler import InputHandler
from client.scenes.animation_orchestrator import AnimationOrchestrator
from client.scenes.change_tracker import FactionChangeTracker
from client.renderer.popup_manager import (
    PopupManager, HoverRegion, TooltipDescriptor, TooltipRegistry,
    set_ui_rects, _WEIGHT_TEXT, _WEIGHT_NON_TEXT,
)

# Approximate hex map screen bounds (default camera) for centering UI
_HEX_MAP_HALF_W = int(HEX_SIZE * 1.5 * (MAP_SIDE_LENGTH - 1)) + HEX_SIZE
_HEX_MAP_LEFT_X = SCREEN_WIDTH // 2 - _HEX_MAP_HALF_W
_HEX_MAP_RIGHT_X = SCREEN_WIDTH // 2 + _HEX_MAP_HALF_W
_FACTION_PANEL_X = SCREEN_WIDTH - 240

# Centering positions for button columns
_GUIDANCE_CENTER_X = _HEX_MAP_LEFT_X // 2
_IDOL_CENTER_X = (_HEX_MAP_RIGHT_X + _FACTION_PANEL_X) // 2
_BTN_W = 130
_GUIDANCE_BTN_X = _GUIDANCE_CENTER_X - _BTN_W // 2
_IDOL_BTN_X = _IDOL_CENTER_X - _BTN_W // 2

# Title positions (below faction overview strip which ends at Y=97)
_TITLE_Y = 102
_BTN_START_Y = 129

_INFLUENCE_TOOLTIP = (
    "The number of additional Agenda cards a Spirit draws when "
    "choosing for their Guided Faction. Set to 3 when Guidance "
    "begins, it decreases by 1 each turn. The Spirit is ejected "
    "when it reaches 0."
)

_AGENDA_DECK_TOOLTIP = (
    "All possible Agendas a Faction can draw and play. The base "
    "deck contains 1 of each type: Trade, Steal, Expand, "
    "and Change. Extra cards can be added via the Change agenda "
    "or when a Spirit is ejected from Guidance. Spirits with "
    "more Influence draw more options from it."
)

_WAR_TOOLTIP = (
    "If two Factions have -2 Regard or less after one of them plays Steal, "
    "a War is declared. At the end of the turn where it is declared, a War "
    "becomes ripe and two neighboring hexes, one belonging to each Faction, "
    "are chosen as the Battleground. At the end of the next turn, the ripe "
    "War resolves."
)

_WAR_RESOLVES_TOOLTIP = (
    "When a ripe War resolves, both Factions roll a 6-sided die and add the "
    "number of their Territories to the roll. The Faction with the higher "
    "total wins.\n\n"
    "The victorious Faction gains 1 gold and plays a random Agenda card as "
    "Spoils of War. Expand drawn as Spoils will conquer the enemy side of "
    "the Battleground instead of its usual effect. Other Agendas have their "
    "normal effect, including Trade granting gold and Regard with other "
    "Trade cards played this turn.\n\n"
    "If the winning Faction is Guided, the Spirit gets to draw additional "
    "Agendas as Spoils equal to its current Influence before choosing one to "
    "resolve.\n\n"
    "The losing Faction loses 1 gold. In the case of a tie, both Factions "
    "lose 1 gold."
)

_GOLD_TOOLTIP = "Resource used to pay for Expand Agendas. Cannot go below 0."

_TRADE_AGENDA_TOOLTIP = "Trade\n+1 gold, +1 gold for every other Faction playing Trade this turn.\n+1 Regard with each other Faction playing Trade this turn."
_STEAL_AGENDA_TOOLTIP = "Steal\n-1 Regard with and -1 gold to all neighbors. +1 gold for each gold lost. War erupts at -2 Regard."
_EXPAND_AGENDA_TOOLTIP = "Expand\nSpend gold equal to territories to claim a neutral hex. If unavailable or lacking gold, +1 gold instead. Idol hexes prioritized."

_MODIFIER_TOOLTIP = (
    "Permanently improves a specific Agenda when used by the Faction implementing the modifier. "
    "These bonuses stack. Possible modifiers:\n"
    "Trade: +1 gold and +1 Regard per co-trader\n"
    "Steal: +1 gold stolen and -1 regard to affected neighbors\n"
    "Expand: -1 cost on successful Expands, +1 gold on failed Expands"
)

_CONTESTED_TOOLTIP = (
    "If several Spirits attempt to Guide the same Faction on a given turn, "
    "the Guidance fails. This prevents all involved Spirits from Guiding "
    "that Faction for exactly 1 turn.\n\n"
    "Spirits can only place 1 Idol per successful Guidance."
)

_GUIDANCE_HOVER_REGIONS = [
    HoverRegion("Agenda deck", _AGENDA_DECK_TOOLTIP, sub_regions=[
        HoverRegion("Influence", _INFLUENCE_TOOLTIP, sub_regions=[]),
    ]),
    HoverRegion("Influence", _INFLUENCE_TOOLTIP, sub_regions=[]),
    HoverRegion("Gold", _GOLD_TOOLTIP, sub_regions=[]),
    HoverRegion("gold", _GOLD_TOOLTIP, sub_regions=[]),
    HoverRegion("War", _WAR_TOOLTIP, sub_regions=[
        HoverRegion("resolves", _WAR_RESOLVES_TOOLTIP, sub_regions=[]),
    ]),
    HoverRegion("modifier", _MODIFIER_TOOLTIP, sub_regions=[
        HoverRegion("Trade", _TRADE_AGENDA_TOOLTIP, sub_regions=[]),
        HoverRegion("Steal", _STEAL_AGENDA_TOOLTIP, sub_regions=[]),
        HoverRegion("Expand", _EXPAND_AGENDA_TOOLTIP, sub_regions=[]),
    ]),
    HoverRegion("Contested", _CONTESTED_TOOLTIP, sub_regions=[]),
]

_WAR_HOVER_REGIONS = [
    HoverRegion("resolves", _WAR_RESOLVES_TOOLTIP, sub_regions=[]),
]

_CHOICE_CARD_Y = 136
_MULTI_CHOICE_BLOCK_STEP = 220


class GameScene:
    def __init__(self, app):
        self.app = app
        self.hex_renderer = HexRenderer()
        self.ui_renderer = UIRenderer()
        self.animation = AnimationManager()
        self.input_handler = InputHandler()
        self.orchestrator = AnimationOrchestrator(
            self.animation, self.hex_renderer, self.input_handler)
        load_assets()

        self.game_state: dict = {}
        self.phase = ""
        self.turn = 0
        self.factions: dict = {}
        self.spirits: dict = {}
        self.wars: list = []
        self.all_idols: list = []
        self.hex_ownership: dict[tuple[int, int], str | None] = {}
        # Deferred display state: lags behind real state while animations play
        self._display_hex_ownership: dict[tuple[int, int], str | None] | None = None
        self._display_factions: dict | None = None
        self._display_wars: list | None = None
        self.waiting_for: list[str] = []
        self.event_log: list[str] = []
        self.event_log_scroll_offset: int = 0

        # Faction overview tracking
        self.faction_agendas_this_turn: dict[str, str] = {}
        self.faction_spoils_agendas_this_turn: dict[str, list[str]] = {}
        self._pending_ribbon_clear_on_next_agenda: bool = False
        self._pending_agenda_log_info: dict[str, dict] = {}

        # Phase-specific state
        self.phase_options: dict = {}
        self.selected_faction: str | None = None
        self.selected_hex: tuple[int, int] | None = None
        self.selected_idol_type: str | None = None
        self.panel_faction: str | None = None
        self.preview_guidance: str | None = None
        self.preview_idol: tuple | None = None  # (idol_type, q, r)

        # Agenda state
        self.agenda_hand: list[dict] = []
        self.selected_agenda_index: int = -1

        # Change/ejection/spoils state
        self.change_cards: list[str] = []
        self.ejection_pending = False
        self.ejection_faction = ""
        self.selected_ejection_type: str | None = None
        self.spoils_cards: list[list[str]] = []  # list of card lists per war
        self.spoils_opponents: list[str] = []   # opponent per war
        self.spoils_selections: list[int] = []  # selected card index per war (-1 = none)
        self.spoils_change_cards: list[list[str]] = []  # list of card lists per change choice
        self.spoils_change_opponents: list[str] = []
        self.spoils_change_selections: list[int] = []

        # UI buttons
        self.action_buttons: list[Button] = []
        self.submit_button: Button | None = None
        self.faction_buttons: list[Button] = []
        self.idol_buttons: list[Button] = []

        # Title labels (rects + tooltip text)
        self.guidance_title_rect: pygame.Rect | None = None
        self.guidance_title_hovered: bool = False
        self.idol_title_rect: pygame.Rect | None = None
        self.idol_title_hovered: bool = False

        # Idol hover tooltip
        self.hovered_idol = None  # idol object or None
        self.idol_tooltip_spirit_rects: list[tuple[str, pygame.Rect]] = []

        # Agenda hover tooltip state
        self.hovered_card_tooltip: str | None = None
        self.hovered_card_rect: pygame.Rect | None = None
        self.agenda_label_rects: list[tuple[str, str, bool, pygame.Rect]] = []
        self.hovered_agenda_label_fid: str | None = None
        self.hovered_agenda_label_type: str | None = None
        self.hovered_agenda_label_is_spoils: bool = False
        self.hovered_agenda_label_rect: pygame.Rect | None = None
        self.hovered_anim_tooltip: str | None = None
        self.hovered_anim_rect: pygame.Rect | None = None

        # Faction panel / VP hover tooltip state
        self.hovered_panel_guided: bool = False
        self.hovered_panel_worship: bool = False
        self.hovered_panel_war: bool = False
        self.hovered_vp_spirit_id: str | None = None

        # Spirit panel state (which spirit's panel to show, or None)
        self.spirit_panel_spirit_id: str | None = None
        self.hovered_spirit_panel_guidance: bool = False
        self.hovered_spirit_panel_influence: bool = False
        self.hovered_spirit_panel_worship: str | None = None  # faction_id or None
        # Ejection title keyword hover state
        self.ejection_keyword_rects: dict[str, list[pygame.Rect]] = {}
        self.hovered_ejection_keyword: str | None = None

        # Change tracking for faction panel
        self.change_tracker = FactionChangeTracker()
        self.popup_manager = PopupManager()
        self.tooltip_registry = TooltipRegistry()
        self.highlighted_log_index: int | None = None
        self.panel_change_rects: list[tuple[pygame.Rect, int]] = []

        self._font = None
        self._small_font = None

    @property
    def font(self):
        if self._font is None:
            self._font = pygame.font.SysFont("consolas", 16)
        return self._font

    @property
    def small_font(self):
        if self._small_font is None:
            self._small_font = pygame.font.SysFont("consolas", 13)
        return self._small_font

    def _update_state_from_snapshot(self, data: dict):
        """Update local state from a game state snapshot dict."""
        self.turn = data.get("turn", self.turn)
        self.phase = data.get("phase", self.phase)
        self.factions = data.get("factions", self.factions)
        self.spirits = data.get("spirits", self.spirits)

        # Parse wars
        self.wars = []
        for w in data.get("wars", []):
            self.wars.append(w)

        # Parse idols
        self.all_idols = []
        for i in data.get("all_idols", []):
            self.all_idols.append(i)

        # Parse hex ownership
        self.hex_ownership = {}
        for key, owner in data.get("hex_ownership", {}).items():
            parts = key.split(",")
            if len(parts) == 2:
                q, r = int(parts[0]), int(parts[1])
                self.hex_ownership[(q, r)] = owner

    def _snapshot_display_state(self):
        """Capture current state into display fields before updating real state.

        Only snapshots if display state isn't already set (preserves display
        state across multiple PHASE_RESULT messages during animation).
        """
        if self._display_hex_ownership is None:
            self._display_hex_ownership = dict(self.hex_ownership)
        if self._display_factions is None:
            import copy
            self._display_factions = copy.deepcopy(self.factions)
        if self._display_wars is None:
            import copy
            self._display_wars = copy.deepcopy(self.wars)

    def _clear_display_state(self):
        """Clear deferred display state so rendering uses real state."""
        self._display_hex_ownership = None
        self._display_factions = None
        self._display_wars = None

    @property
    def display_hex_ownership(self) -> dict:
        return self._display_hex_ownership if self._display_hex_ownership is not None else self.hex_ownership

    @property
    def display_factions(self) -> dict:
        return self._display_factions if self._display_factions is not None else self.factions

    @property
    def display_wars(self) -> list:
        return self._display_wars if self._display_wars is not None else self.wars

    def handle_event(self, event):
        self.input_handler.handle_camera_event(event)

        if event.type == pygame.MOUSEWHEEL:
            log_rect = pygame.Rect(
                SCREEN_WIDTH - 300, SCREEN_HEIGHT - 200, 290, 190
            )
            mx, my = pygame.mouse.get_pos()
            if log_rect.collidepoint(mx, my):
                visible_count = (190 - 26) // 16
                max_offset = max(0, len(self.event_log) - visible_count)
                self.event_log_scroll_offset += event.y
                self.event_log_scroll_offset = max(0, min(self.event_log_scroll_offset, max_offset))

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.popup_manager.handle_escape()

        if event.type == pygame.MOUSEMOTION:
            for btn in self.action_buttons + self.faction_buttons + self.idol_buttons:
                btn.update(event.pos)
            if self.submit_button:
                self.submit_button.update(event.pos)
            # Title label hover tracking
            if self.guidance_title_rect:
                self.guidance_title_hovered = self.guidance_title_rect.collidepoint(event.pos)
            if self.idol_title_rect:
                self.idol_title_hovered = self.idol_title_rect.collidepoint(event.pos)
            # Idol hover detection on hex map
            self._update_idol_hover(event.pos)
            # Agenda card/label/animation hover detection
            self._update_agenda_hover(event.pos)
            # Faction panel guided/worship hover detection
            self._update_panel_hover(event.pos)
            # Spirit panel hover detection
            self._update_spirit_panel_hover(event.pos)
            # Ejection title keyword hover detection
            self._update_ejection_title_hover(event.pos)
            # Popup keyword hover
            self.popup_manager.update_hover(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check submit button
            if self.submit_button and self.submit_button.clicked(event.pos):
                self._submit_action()
                return

            # Check action buttons
            for btn in self.action_buttons:
                if btn.clicked(event.pos):
                    self._handle_action_button(btn.text)
                    return

            # Check faction buttons
            for btn in self.faction_buttons:
                if btn.clicked(event.pos):
                    self._handle_faction_select(btn.text.lower())
                    return

            # Check idol type buttons
            for btn in self.idol_buttons:
                if btn.clicked(event.pos):
                    self._handle_idol_select(btn.text.lower())
                    return

            # Check agenda card clicks
            if self.agenda_hand:
                for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.agenda_hand))):
                    if rect.collidepoint(event.pos):
                        self.selected_agenda_index = i
                        return

            # Check change card clicks
            if self.change_cards:
                for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.change_cards))):
                    if rect.collidepoint(event.pos):
                        self._submit_card_choice(i, MessageType.SUBMIT_CHANGE_CHOICE, "change_cards")
                        return

            # Check spoils card clicks (multi-war)
            if self.spoils_cards:
                y_offset = _CHOICE_CARD_Y
                for war_idx, cards in enumerate(self.spoils_cards):
                    rects = self._calc_left_choice_card_rects(len(cards), y=y_offset)
                    for i, rect in enumerate(rects):
                        if rect.collidepoint(event.pos):
                            self.spoils_selections[war_idx] = i
                            # If all wars have a selection, submit
                            if all(s >= 0 for s in self.spoils_selections):
                                self.app.network.send(MessageType.SUBMIT_SPOILS_CHOICE,
                                    {"card_indices": list(self.spoils_selections)})
                                self.spoils_cards = []
                                self.spoils_opponents = []
                                self.spoils_selections = []
                            return
                    y_offset += _MULTI_CHOICE_BLOCK_STEP

            # Check spoils change card clicks (multi-choice)
            if self.spoils_change_cards:
                y_offset = _CHOICE_CARD_Y
                for choice_idx, cards in enumerate(self.spoils_change_cards):
                    rects = self._calc_left_choice_card_rects(len(cards), y=y_offset)
                    for i, rect in enumerate(rects):
                        if rect.collidepoint(event.pos):
                            self.spoils_change_selections[choice_idx] = i
                            if all(s >= 0 for s in self.spoils_change_selections):
                                self.app.network.send(MessageType.SUBMIT_SPOILS_CHANGE_CHOICE,
                                    {"card_indices": list(self.spoils_change_selections)})
                                self.spoils_change_cards = []
                                self.spoils_change_opponents = []
                                self.spoils_change_selections = []
                            return
                    y_offset += _MULTI_CHOICE_BLOCK_STEP

            # Check change delta chip clicks (faction panel)
            for rect, log_idx in self.panel_change_rects:
                if rect.collidepoint(event.pos):
                    if self.highlighted_log_index == log_idx:
                        self.highlighted_log_index = None
                    else:
                        self.highlighted_log_index = log_idx
                        # Auto-scroll event log to show highlighted entry
                        visible_count = (190 - 26) // 16
                        total = len(self.event_log)
                        if total > visible_count:
                            # scroll_offset=0 shows last entries; we want log_idx visible
                            offset = total - log_idx - visible_count
                            self.event_log_scroll_offset = max(0, min(offset, total - visible_count))
                    return

            # Idol tooltip: click spirit names to toggle that spirit's panel
            for sid, name_rect in self.idol_tooltip_spirit_rects:
                if name_rect.collidepoint(event.pos):
                    if self.spirit_panel_spirit_id == sid:
                        self.spirit_panel_spirit_id = None
                    else:
                        self.spirit_panel_spirit_id = sid
                    return

            # Spirit panel: click on any name in VP HUD toggles that spirit's panel
            for sid, vp_rect in self.ui_renderer.vp_hover_rects.items():
                if vp_rect.collidepoint(event.pos):
                    if self.spirit_panel_spirit_id == sid:
                        self.spirit_panel_spirit_id = None
                    else:
                        self.spirit_panel_spirit_id = sid
                    return

            # Click on spirit panel itself should not close it
            sp_rect = self.ui_renderer.spirit_panel_rect
            if self.spirit_panel_spirit_id and sp_rect and sp_rect.collidepoint(event.pos):
                return

            # Clicking elsewhere closes the spirit panel
            if self.spirit_panel_spirit_id:
                self.spirit_panel_spirit_id = None

            # Hex click
            hex_coord = self.hex_renderer.get_hex_at_screen(
                event.pos[0], event.pos[1], self.input_handler,
                SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
            )
            if hex_coord:
                self._handle_hex_click(hex_coord)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if self.popup_manager.has_popups():
                self.popup_manager.handle_right_click(
                    event.pos, self.small_font, SCREEN_WIDTH)
            else:
                self._try_pin_hovered_tooltip(event.pos)

    def _handle_action_button(self, text: str):
        if self.ejection_pending:
            self.selected_ejection_type = text.lower()
            return

    def _handle_faction_select(self, faction_id: str):
        self.selected_faction = faction_id
        self.panel_faction = faction_id
        self.spirit_panel_spirit_id = None

    def _handle_idol_select(self, idol_type: str):
        self.selected_idol_type = idol_type

    def _handle_hex_click(self, hex_coord: tuple[int, int]):
        if self.phase == Phase.VAGRANT_PHASE.value and self.hex_ownership.get(hex_coord) is None:
            # Neutral hex during vagrant phase: select for idol placement
            self.selected_hex = hex_coord
        else:
            owner = self.hex_ownership.get(hex_coord)
            if owner:
                self.panel_faction = owner
                self.spirit_panel_spirit_id = None
                # If guidance is available, also set as guide target
                if self.phase == Phase.VAGRANT_PHASE.value and self.faction_buttons:
                    available = set(self.phase_options.get("available_factions", []))
                    blocked = set(self.phase_options.get("worship_blocked", []))
                    if owner in available and owner not in blocked:
                        self.selected_faction = owner

    def _submit_action(self):
        if self.phase == Phase.VAGRANT_PHASE.value:
            payload = {}
            if self.selected_faction:
                payload["guide_target"] = self.selected_faction
            if self.selected_idol_type and self.selected_hex:
                payload["idol_type"] = self.selected_idol_type
                payload["idol_q"] = self.selected_hex[0]
                payload["idol_r"] = self.selected_hex[1]
            if payload:
                # Store previews before clearing
                if self.selected_faction:
                    self.preview_guidance = self.selected_faction
                if self.selected_idol_type and self.selected_hex:
                    self.preview_idol = (self.selected_idol_type,
                                         self.selected_hex[0], self.selected_hex[1])
                self.app.network.send(MessageType.SUBMIT_VAGRANT_ACTION, payload)
                self._clear_selection()
        elif self.phase == Phase.AGENDA_PHASE.value:
            if self.selected_agenda_index >= 0:
                self.app.network.send(MessageType.SUBMIT_AGENDA_CHOICE, {
                    "agenda_index": self.selected_agenda_index,
                })
                self._clear_selection()
        elif self.phase == "ejection_choice":
            if self.selected_ejection_type:
                self.app.network.send(MessageType.SUBMIT_EJECTION_AGENDA, {
                    "agenda_type": self.selected_ejection_type,
                })
                self._clear_selection()
                self.ejection_pending = False

    def _submit_card_choice(self, index: int, msg_type: MessageType, card_attr: str):
        self.app.network.send(msg_type, {"card_index": index})
        setattr(self, card_attr, [])

    def _clear_selection(self):
        self.selected_faction = None
        self.selected_hex = None
        self.selected_idol_type = None
        self.panel_faction = None
        self.selected_agenda_index = -1
        self.selected_ejection_type = None
        self.agenda_hand = []
        self.action_buttons = []
        self.faction_buttons = []
        self.idol_buttons = []
        self.submit_button = None
        self.guidance_title_rect = None
        self.guidance_title_hovered = False
        self.idol_title_rect = None
        self.idol_title_hovered = False
        self.ejection_keyword_rects = {}
        self.hovered_ejection_keyword = None

    def handle_network(self, msg_type, payload):
        if msg_type == MessageType.GAME_START:
            self._update_state_from_snapshot(payload)
            self.change_tracker.snapshot_and_reset(self.factions, self.spirits)
            self.event_log.append("Game started.")

        elif msg_type == MessageType.PHASE_START:
            phase = payload.get("phase", "")
            action = payload.get("options", {}).get("action", "")
            needs_input = action not in ("none", "") or phase in (
                "change_choice", "spoils_choice",
                "spoils_change_choice", "ejection_choice")
            if needs_input and self.orchestrator.has_animations_playing():
                self.orchestrator.deferred_phase_start = payload
            else:
                self.phase = payload.get("phase", self.phase)
                self.turn = payload.get("turn", self.turn)
                self.phase_options = payload.get("options", {})
                self._setup_phase_ui()

        elif msg_type == MessageType.WAITING_FOR:
            self.waiting_for = payload.get("players_remaining", [])

        elif msg_type == MessageType.PHASE_RESULT:
            active_sub_phase = self.phase if self.phase in (
                "change_choice", "spoils_choice", "spoils_change_choice") else None
            # Snapshot display state before updating so animations render old state
            events = payload.get("events", [])
            _ANIM_ORDER = {
                "trade": 0, "steal": 1,
                "expand": 2, "expand_failed": 2, "expand_spoils": 2,
                "change": 3,
            }
            agenda_events = [e for e in events if e.get("type", "") in _ANIM_ORDER
                           and not e.get("is_guided_modifier")]
            if agenda_events and "state" in payload:
                self._snapshot_display_state()
            if "state" in payload:
                self._update_state_from_snapshot(payload["state"])
            # Preserve sub-phases while this player still has cards to choose
            if active_sub_phase == "change_choice" and self.change_cards:
                self.phase = active_sub_phase
            elif active_sub_phase == "spoils_choice" and any(self.spoils_cards):
                self.phase = active_sub_phase
            elif active_sub_phase == "spoils_change_choice" and any(self.spoils_change_cards):
                self.phase = active_sub_phase
            # Log events (consolidate agenda play + resolution into one line)
            self._log_events_batch(events)
            # VP gain animations
            for event in events:
                if event.get("type") == "vp_scored":
                    vp = event.get("vp_gained", 0)
                    sid = event.get("spirit", "")
                    if vp > 0 and sid:
                        vp_pos = self.ui_renderer.vp_positions.get(sid)
                        if vp_pos:
                            self.animation.add_effect_animation(TextAnimation(
                                f"+{vp:.1f} VP", vp_pos[0], vp_pos[1] + 16,
                                (80, 255, 80),
                                delay=0.0, duration=3.0, drift_pixels=40,
                                direction=1, screen_space=True,
                            ))
            # Trigger agenda events immediately, but preserve turn_start segmentation
            # for bootstrap payloads so Turn 1 and Turn 2 do not animate concurrently.
            if agenda_events:
                turn_batched_events: list[list[dict]] = []
                current_turn_batch: list[dict] = []
                saw_turn_markers = False
                for event in events:
                    etype = event.get("type", "")
                    if etype == "turn_start":
                        saw_turn_markers = True
                        if current_turn_batch:
                            turn_batched_events.append(current_turn_batch)
                            current_turn_batch = []
                        continue
                    if (etype in _ANIM_ORDER or etype == "war_erupted") and not event.get("is_guided_modifier"):
                        current_turn_batch.append(event)
                if current_turn_batch:
                    turn_batched_events.append(current_turn_batch)

                if not saw_turn_markers:
                    war_events = [e for e in events if e.get("type") == "war_erupted"]
                    anim_events = agenda_events + war_events
                    self.orchestrator.process_agenda_events(
                        anim_events, self.hex_ownership, self.small_font)
                else:
                    for batch in turn_batched_events:
                        self.orchestrator.process_agenda_events(
                            batch, self.hex_ownership, self.small_font)
            # Clear previews after processing phase results
            self.preview_guidance = None
            self.preview_idol = None

        elif msg_type == MessageType.GAME_OVER:
            # Will be in the events
            self.app.set_scene("results")

        elif msg_type == MessageType.ERROR:
            self.event_log.append(f"Error: {payload.get('message', '?')}")

    def _setup_phase_ui(self):
        """Build UI elements for the current phase."""
        self._clear_selection()
        action = self.phase_options.get("action", "none")

        if self.phase == Phase.VAGRANT_PHASE.value and action == "choose":
            # Build faction buttons (left) and idol buttons (right)
            self._build_faction_buttons()
            if self.phase_options.get("can_place_idol", True):
                self._build_idol_buttons()
            self.submit_button = Button(
                pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
                "Confirm", (60, 130, 60)
            )

        elif self.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
            hand = self.phase_options.get("hand", [])
            self.agenda_hand = hand
            self.selected_agenda_index = -1
            self.submit_button = Button(
                pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
                "Confirm", (60, 130, 60)
            )

        elif self.phase == "change_choice":
            self.change_cards = payload_cards if (payload_cards := self.phase_options.get("cards")) else []

        elif self.phase == "spoils_choice":
            choices = self.phase_options.get("choices", [])
            if choices:
                self.spoils_cards = [c.get("cards", []) for c in choices]
                self.spoils_opponents = [c.get("loser", "") for c in choices]
            else:
                # Backwards compat: single-war format
                cards = self.phase_options.get("cards", [])
                self.spoils_cards = [cards] if cards else []
                self.spoils_opponents = [self.phase_options.get("loser", "")] if cards else []
            self.spoils_selections = [-1] * len(self.spoils_cards)

        elif self.phase == "spoils_change_choice":
            choices = self.phase_options.get("choices", [])
            if choices:
                self.spoils_change_cards = [c.get("cards", []) for c in choices]
                self.spoils_change_opponents = [c.get("loser", "") for c in choices]
            else:
                cards = self.phase_options.get("cards", [])
                self.spoils_change_cards = [cards] if cards else []
                self.spoils_change_opponents = [self.phase_options.get("loser", "")] if cards else []
            self.spoils_change_selections = [-1] * len(self.spoils_change_cards)

        elif self.phase == "ejection_choice":
            self.ejection_pending = True
            self.ejection_faction = self.phase_options.get("faction", "")
            self.selected_ejection_type = None
            # Build ejection buttons
            y = SCREEN_HEIGHT - 200
            self.action_buttons = []
            modifiers = self._get_faction_modifiers(self.ejection_faction)
            for i, at in enumerate(AgendaType):
                tooltip = build_agenda_tooltip(at.value, modifiers)
                btn = Button(
                    pygame.Rect(20 + i * 110, y, 100, 36),
                    at.value.title(), (80, 60, 130),
                    tooltip=tooltip,
                    tooltip_always=True,
                )
                self.action_buttons.append(btn)
            self.submit_button = Button(
                pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
                "Confirm", (60, 130, 60)
            )

    def _count_spirit_idols_in_faction(self, spirit_id: str, faction_id: str) -> int:
        """Count idols owned by a spirit in a faction's territory."""
        count = 0
        for idol in self.all_idols:
            if isinstance(idol, dict):
                if idol.get('owner_spirit') == spirit_id:
                    pos = idol.get('position', {})
                    q, r = pos.get('q'), pos.get('r')
                    if self.hex_ownership.get((q, r)) == faction_id:
                        count += 1
        return count

    def _build_guidance_tooltip(self, faction_id: str, is_blocked: bool,
                                is_contested_blocked: bool = False) -> str:
        """Build tooltip for a Guidance faction button."""
        fdata = self.factions.get(faction_id, {})
        worship_id = fdata.get("worship_spirit") if isinstance(fdata, dict) else None
        lines = []
        if is_contested_blocked:
            lines.append("Contested last turn;")
            lines.append("cannot target this turn.")
        elif is_blocked:
            lines.append("This Faction Worships you;")
            lines.append("you cannot Guide them.")
        elif worship_id:
            name = self.spirits.get(worship_id, {}).get("name", worship_id[:6])
            lines.append(f"Worshipped by: {name}")
            my_id = self.app.my_spirit_id
            my_idols = self._count_spirit_idols_in_faction(my_id, faction_id)
            their_idols = self._count_spirit_idols_in_faction(worship_id, faction_id)
            if my_idols >= their_idols:
                lines.append("Guiding will make you Worshipped")
            else:
                lines.append(f"You need more Idols to become")
                lines.append(f"Worshipped ({my_idols} vs {their_idols})")
        else:
            lines.append("Not Worshipped by any Spirit")
            lines.append("Guiding will make you Worshipped")
        return "\n".join(lines)

    def _build_faction_buttons(self):
        available = [
            fid for fid in self.phase_options.get("available_factions", [])
            if not self.factions.get(fid, {}).get("eliminated", False)
        ]
        blocked = self.phase_options.get("worship_blocked", [])
        contested_blocked = self.phase_options.get("contested_blocked", [])
        self.faction_buttons = []
        all_factions = available + blocked + contested_blocked
        for i, fid in enumerate(all_factions):
            color = FACTION_COLORS.get(fid, (100, 100, 100))
            is_blocked = fid in blocked
            is_contested_blocked = fid in contested_blocked
            tooltip = self._build_guidance_tooltip(fid, is_blocked, is_contested_blocked)
            btn = Button(
                pygame.Rect(_GUIDANCE_BTN_X, _BTN_START_Y + i * 40, _BTN_W, 34),
                FACTION_DISPLAY_NAMES.get(fid, fid),
                color=tuple(max(c // 2, 30) for c in color),
                text_color=(255, 255, 255),
                tooltip=tooltip,
                tooltip_always=True,
            )
            if is_blocked or is_contested_blocked:
                btn.enabled = False
            self.faction_buttons.append(btn)
        # Set up guidance title rect
        title_w = 100
        self.guidance_title_rect = pygame.Rect(
            _GUIDANCE_CENTER_X - title_w // 2, _TITLE_Y, title_w, 22
        )

    def _build_idol_buttons(self):
        idol_tooltips = {
            IdolType.BATTLE: f"{BATTLE_IDOL_VP} VP for each war won\nby the Worshipping Faction",
            IdolType.AFFLUENCE: f"{AFFLUENCE_IDOL_VP} VP for each gold gained\nby the Worshipping Faction",
            IdolType.SPREAD: f"{SPREAD_IDOL_VP} VP for each territory gained\nby the Worshipping Faction",
        }
        self.idol_buttons = []
        for i, it in enumerate(IdolType):
            colors = {
                IdolType.BATTLE: (130, 50, 50),
                IdolType.AFFLUENCE: (130, 120, 30),
                IdolType.SPREAD: (50, 120, 50),
            }
            btn = Button(
                pygame.Rect(_IDOL_BTN_X, _BTN_START_Y + i * 40, _BTN_W, 34),
                it.value.title(), colors.get(it, (80, 80, 80)),
                tooltip=idol_tooltips.get(it),
                tooltip_always=True,
            )
            self.idol_buttons.append(btn)
        # Set up idol title rect
        title_w = 130
        self.idol_title_rect = pygame.Rect(
            _IDOL_CENTER_X - title_w // 2, _TITLE_Y, title_w, 22
        )

    def _calc_card_rects(self, count: int, start_x: int = 20, y: int = 125,
                         centered: bool = False) -> list[pygame.Rect]:
        card_w, card_h = 110, 170
        spacing = 10
        if centered:
            total_w = count * (card_w + spacing) - spacing
            start_x = SCREEN_WIDTH // 2 - total_w // 2
        return [pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h)
                for i in range(count)]

    def _calc_left_choice_card_rects(self, count: int, y: int = 136) -> list[pygame.Rect]:
        """Card rects centered within the left black panel, clamped from x=20."""
        card_w, spacing = 110, 10
        total_w = count * (card_w + spacing) - spacing
        start_x = (_HEX_MAP_LEFT_X - total_w) // 2
        start_x = max(20, start_x)
        return self._calc_card_rects(count, start_x=start_x, y=y, centered=False)

    def _update_idol_hover(self, mouse_pos):
        """Check if mouse is hovering over a placed idol on the hex map."""
        if not self.all_idols:
            self.hovered_idol = None
            self.idol_tooltip_spirit_rects = []
            return
        # Build render idols the same way as render()
        render_idols = []
        for idol_data in self.all_idols:
            if isinstance(idol_data, dict):
                render_idols.append(type('Idol', (), {
                    'type': IdolType(idol_data['type']),
                    'position': type('Pos', (), {
                        'q': idol_data['position']['q'],
                        'r': idol_data['position']['r'],
                    })(),
                    'owner_spirit': idol_data.get('owner_spirit'),
                })())
        if not render_idols:
            self.hovered_idol = None
            self.idol_tooltip_spirit_rects = []
            return
        spirit_index_map = {
            sid: i for i, sid in enumerate(sorted(self.spirits.keys()))
        }
        self.hovered_idol = self.hex_renderer.get_idol_at_screen(
            mouse_pos[0], mouse_pos[1], render_idols,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            spirit_index_map,
        )
        if self.hovered_idol is None:
            self.idol_tooltip_spirit_rects = []

    def _get_faction_modifiers(self, faction_id: str) -> dict:
        """Get the change_modifiers for a given faction."""
        fdata = self.factions.get(faction_id, {})
        if isinstance(fdata, dict):
            return fdata.get("change_modifiers", {})
        return {}

    def _update_agenda_hover(self, mouse_pos):
        """Check if mouse is hovering over agenda cards, faction labels, or animations."""
        self.hovered_card_tooltip = None
        self.hovered_card_rect = None
        self.hovered_agenda_label_fid = None
        self.hovered_agenda_label_type = None
        self.hovered_agenda_label_is_spoils = False
        self.hovered_agenda_label_rect = None
        self.hovered_anim_tooltip = None
        self.hovered_anim_rect = None

        mx, my = mouse_pos

        # Check card pickers (agenda hand, change cards, spoils cards, spoils change cards)
        modifiers = self._get_current_faction_modifiers()

        if self.agenda_hand:
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.agenda_hand))):
                if rect.collidepoint(mx, my):
                    atype = self.agenda_hand[i].get("agenda_type", "")
                    self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers)
                    self.hovered_card_rect = rect
                    return

        if self.change_cards:
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.change_cards))):
                if rect.collidepoint(mx, my):
                    self.hovered_card_tooltip = build_modifier_tooltip(self.change_cards[i])
                    self.hovered_card_rect = rect
                    return

        if self.spoils_cards:
            y_offset = _CHOICE_CARD_Y
            for war_idx, cards in enumerate(self.spoils_cards):
                for i, rect in enumerate(self._calc_left_choice_card_rects(len(cards), y=y_offset)):
                    if rect.collidepoint(mx, my):
                        atype = cards[i]
                        self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers, is_spoils=True)
                        self.hovered_card_rect = rect
                        return
                y_offset += _MULTI_CHOICE_BLOCK_STEP

        if self.spoils_change_cards:
            y_offset = _CHOICE_CARD_Y
            for choice_idx, cards in enumerate(self.spoils_change_cards):
                for i, rect in enumerate(self._calc_left_choice_card_rects(len(cards), y=y_offset)):
                    if rect.collidepoint(mx, my):
                        self.hovered_card_tooltip = build_modifier_tooltip(cards[i])
                        self.hovered_card_rect = rect
                        return
                y_offset += _MULTI_CHOICE_BLOCK_STEP

        # Check faction ribbon agenda labels
        for fid, agenda_type, is_spoils, rect in self.agenda_label_rects:
            if rect.collidepoint(mx, my):
                self.hovered_agenda_label_fid = fid
                self.hovered_agenda_label_type = agenda_type
                self.hovered_agenda_label_is_spoils = is_spoils
                self.hovered_agenda_label_rect = rect
                return

        # Check persistent agenda slide animations
        for anim in self.animation.get_persistent_agenda_animations():
            if not anim.active or not anim.agenda_type:
                continue
            img_w = anim.image.get_width()
            img_h = anim.image.get_height()
            anim_rect = pygame.Rect(int(anim.x), int(anim.y), img_w, img_h)
            if anim_rect.collidepoint(mx, my):
                fid = anim.faction_id
                fmod = self._get_faction_modifiers(fid)
                self.hovered_anim_tooltip = build_agenda_tooltip(
                    anim.agenda_type, fmod, is_spoils=anim.is_spoils)
                self.hovered_anim_rect = anim_rect
                return

    def _update_panel_hover(self, mouse_pos):
        """Check if mouse is hovering over hoverable faction panel labels."""
        mx, my = mouse_pos
        r = self.ui_renderer.panel_guided_rect
        self.hovered_panel_guided = r is not None and r.collidepoint(mx, my)
        r = self.ui_renderer.panel_worship_rect
        self.hovered_panel_worship = r is not None and r.collidepoint(mx, my)
        r = self.ui_renderer.panel_war_rect
        self.hovered_panel_war = r is not None and r.collidepoint(mx, my)

    def _update_vp_hover(self, mouse_pos):
        """Check if mouse is hovering over a player name in the VP HUD."""
        mx, my = mouse_pos
        self.hovered_vp_spirit_id = None
        for sid, rect in self.ui_renderer.vp_hover_rects.items():
            if rect.collidepoint(mx, my):
                self.hovered_vp_spirit_id = sid
                return

    def _update_spirit_panel_hover(self, mouse_pos):
        """Check if mouse is hovering over elements in the spirit panel."""
        mx, my = mouse_pos
        if not self.spirit_panel_spirit_id:
            self.hovered_spirit_panel_guidance = False
            self.hovered_spirit_panel_influence = False
            self.hovered_spirit_panel_worship = None
            return
        r = self.ui_renderer.spirit_panel_guidance_rect
        self.hovered_spirit_panel_guidance = r is not None and r.collidepoint(mx, my)
        r = self.ui_renderer.spirit_panel_influence_rect
        self.hovered_spirit_panel_influence = r is not None and r.collidepoint(mx, my)
        self.hovered_spirit_panel_worship = None
        for fid, rect in self.ui_renderer.spirit_panel_worship_rects.items():
            if rect.collidepoint(mx, my):
                self.hovered_spirit_panel_worship = fid
                return

    def _update_ejection_title_hover(self, mouse_pos):
        """Check if mouse is hovering over keyword spans in ejection title text."""
        self.hovered_ejection_keyword = None
        if self.phase != "ejection_choice":
            return
        mx, my = mouse_pos
        for keyword, rects in self.ejection_keyword_rects.items():
            for rect in rects:
                if rect.collidepoint(mx, my):
                    self.hovered_ejection_keyword = keyword
                    return

    def _try_pin_hovered_tooltip(self, mouse_pos):
        """Pin the currently active tooltip from the registry as a popup."""
        self.tooltip_registry.try_pin(self.popup_manager, self.small_font, SCREEN_WIDTH)

    def _count_idol_vp_for_faction(self, faction_id: str):
        """Count total VP per event type from idols in a faction's territory.

        Returns (battle_vp, spread_vp, affluence_vp) totals.
        """
        battle_count = 0
        spread_count = 0
        affluence_count = 0
        for idol in self.all_idols:
            if isinstance(idol, dict):
                pos = idol.get('position', {})
                q, r = pos.get('q'), pos.get('r')
                if self.hex_ownership.get((q, r)) == faction_id:
                    itype = idol.get('type', '')
                    if itype == IdolType.BATTLE.value:
                        battle_count += 1
                    elif itype == IdolType.SPREAD.value:
                        spread_count += 1
                    elif itype == IdolType.AFFLUENCE.value:
                        affluence_count += 1
        return (
            battle_count * BATTLE_IDOL_VP,
            spread_count * SPREAD_IDOL_VP,
            affluence_count * AFFLUENCE_IDOL_VP,
        )

    _GUIDANCE_GENERIC_TOOLTIP = (
        "A Spirit can Guide a Faction by choosing it during the "
        "Vagrant phase. While Guiding, the Spirit draws from the "
        "Faction's Agenda deck and picks which Agenda the Faction "
        "plays each turn. Guidance lasts until the Spirit's "
        "Influence runs out."
    )

    _UNGUIDED_FACTION_TOOLTIP = (
        "This Faction is not currently Guided by any Spirit. "
        "An unguided Faction draws and plays 1 random Agenda "
        "from its Agenda deck each turn. A Vagrant Spirit can "
        "choose to Guide it during the Vagrant phase."
    )

    def _build_guidance_panel_tooltip(self, spirit_id: str | None) -> str:
        """Build tooltip text for Guided by / VP name hover."""
        if not spirit_id:
            return self._UNGUIDED_FACTION_TOOLTIP
        spirit = self.spirits.get(spirit_id, {})
        influence = spirit.get("influence", 0)
        return (
            "When Guidance begins, the Spirit's Influence is set to 3. "
            "Spirits draw 1 Agenda card + however much Influence they have "
            "from the Guided Faction's Agenda deck, choose 1 of the drawn "
            "Agendas for their Guided Faction to play, then lose 1 Influence. "
            f"This Spirit currently has {influence} remaining Influence and "
            f"will become Vagrant again after that many turns."
        )

    def _build_worship_panel_tooltip(self, faction_id: str) -> str:
        """Build tooltip text for Worshipping hover."""
        worship_id = self.ui_renderer.panel_worship_spirit_id
        battle_vp, spread_vp, affluence_vp = self._count_idol_vp_for_faction(faction_id)

        def _fmt(v):
            return f"{v:g}"

        if worship_id:
            name = self.spirits.get(worship_id, {}).get("name", worship_id[:6])
            return (
                f"At the end of every turn, this Faction will give {name} "
                f"{_fmt(battle_vp)} VPs for each battle it won, "
                f"{_fmt(spread_vp)} VPs for each new Territory it acquired and "
                f"{_fmt(affluence_vp)} VPs for each gold it acquired during that turn."
            )
        else:
            return (
                f"At the end of every turn, this Faction would give "
                f"{_fmt(battle_vp)} VPs for each battle it won, "
                f"{_fmt(spread_vp)} VPs for each new Territory it acquired and "
                f"{_fmt(affluence_vp)} VPs for each gold it acquired during that turn "
                f"to whoever it Worships. The first Spirit to Guide it will become Worshipped."
            )

    def _build_spirit_worship_tooltip(self, faction_id: str, spirit_id: str) -> str:
        """Build tooltip for a faction worshipping a spirit in the spirit panel."""
        battle_vp, spread_vp, affluence_vp = self._count_idol_vp_for_faction(faction_id)
        faction_name = FACTION_DISPLAY_NAMES.get(faction_id, faction_id)

        def _fmt(v):
            return f"{v:g}"

        if spirit_id == self.app.my_spirit_id:
            return (
                f"{faction_name} Worships you. Each turn it gives you "
                f"{_fmt(battle_vp)} VP per battle won, "
                f"{_fmt(spread_vp)} VP per territory gained, and "
                f"{_fmt(affluence_vp)} VP per gold earned."
            )
        else:
            spirit_name = self.spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            return (
                f"{faction_name} Worships {spirit_name}. Each turn it gives them "
                f"{_fmt(battle_vp)} VP per battle won, "
                f"{_fmt(spread_vp)} VP per territory gained, and "
                f"{_fmt(affluence_vp)} VP per gold earned."
            )

    def _log_event(self, event: dict):
        from client.scenes.event_logger import log_event
        etype = log_event(event, self.event_log, self.spirits,
                          self.app.my_spirit_id, self.faction_agendas_this_turn)
        # Record change for faction panel delta display
        self.change_tracker.process_event(
            event, len(self.event_log) - 1, self.factions, self.spirits)
        # Side effects that touch scene state
        if etype == "turn_start":
            self.change_tracker.snapshot_and_reset(self.factions, self.spirits)
            self.highlighted_log_index = None
            self._pending_ribbon_clear_on_next_agenda = True
        elif etype == "guide_contested":
            if self.app.my_spirit_id in event.get("spirits", []):
                self.preview_guidance = None

    @staticmethod
    def _format_faction_list(factions: list[str]) -> str:
        if not factions:
            return ""
        names = [FACTION_DISPLAY_NAMES.get(fid, fid) for fid in factions]
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return f"{', '.join(names[:-1])}, and {names[-1]}"

    def _build_consolidated_agenda_line(self, play_info: dict, resolution_event: dict) -> str:
        faction_id = play_info["faction"]
        fname = FACTION_DISPLAY_NAMES.get(faction_id, faction_id)
        agenda = play_info["agenda"].title()
        verb = "randomly plays" if play_info["source"] == "random" else "plays"
        guided_part = ""
        spirit_id = play_info.get("spirit")
        if spirit_id:
            spirit_name = self.spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            guided_part = f" guided by {spirit_name}"

        etype = resolution_event.get("type", "")
        if etype == "trade":
            gold = resolution_event.get("gold_gained", 0)
            co_traders = resolution_event.get("co_traders", [])
            if co_traders:
                regard = resolution_event.get("regard_gain", 0)
                others = self._format_faction_list(co_traders)
                return f"{fname} {verb} {agenda}{guided_part} for {gold} gold and +{regard} regard with {others}."
            return f"{fname} {verb} {agenda}{guided_part} for {gold} gold."

        if etype == "steal":
            gold = resolution_event.get("gold_gained", 0)
            penalty = resolution_event.get("regard_penalty", 1)
            neighbors = resolution_event.get("neighbors", [])
            if neighbors:
                others = self._format_faction_list(neighbors)
                return f"{fname} {verb} {agenda}{guided_part} for {gold} gold and -{penalty} regard with {others}."
            return f"{fname} {verb} {agenda}{guided_part} for {gold} gold."

        if etype == "expand":
            cost = resolution_event.get("cost", 0)
            return f"{fname} {verb} {agenda}{guided_part} and expands territory for {cost} gold."

        if etype == "expand_failed":
            gained = resolution_event.get("gold_gained", 0)
            return f"{fname} {verb} {agenda}{guided_part} but couldn't expand and gained {gained} gold."

        if etype == "change":
            mod = resolution_event.get("modifier", "?")
            return f"{fname} {verb} {agenda}{guided_part} and upgrades {mod}."

        return f"{fname} {verb} {agenda}{guided_part}."

    def _log_events_batch(self, events: list[dict]):
        resolution_to_agenda = {
            "trade": "trade",
            "steal": "steal",
            "expand": "expand",
            "expand_failed": "expand",
            "change": "change",
        }

        for event in events:
            etype = event.get("type", "")

            if etype in ("agenda_chosen", "agenda_random"):
                if self._pending_ribbon_clear_on_next_agenda:
                    self.faction_agendas_this_turn.clear()
                    self.faction_spoils_agendas_this_turn.clear()
                    self._pending_agenda_log_info.clear()
                    self._pending_ribbon_clear_on_next_agenda = False
                faction_id = event.get("faction", "")
                agenda = event.get("agenda", "")
                if faction_id and agenda:
                    self._pending_agenda_log_info[faction_id] = {
                        "faction": faction_id,
                        "agenda": agenda,
                        "source": "random" if etype == "agenda_random" else "chosen",
                        "spirit": event.get("spirit"),
                    }
                    self.faction_agendas_this_turn[faction_id] = agenda
                continue

            # Guided change choice echo event is an intermediate step; keep it out of log.
            if etype == "change" and event.get("is_guided_modifier"):
                continue

            if event.get("is_spoils"):
                spoils_agenda_type = None
                if etype in ("trade", "steal", "change"):
                    spoils_agenda_type = etype
                elif etype in ("expand", "expand_failed", "expand_spoils"):
                    spoils_agenda_type = "expand"
                if spoils_agenda_type:
                    faction_id = event.get("faction", "")
                    if faction_id:
                        self.faction_spoils_agendas_this_turn.setdefault(faction_id, []).append(
                            spoils_agenda_type)

            faction_id = event.get("faction", "")
            pending = self._pending_agenda_log_info.get(faction_id)
            expected_agenda = resolution_to_agenda.get(etype)
            if pending and expected_agenda and pending.get("agenda") == expected_agenda:
                line = self._build_consolidated_agenda_line(pending, event)
                self.event_log.append(line)
                log_index = len(self.event_log) - 1
                self.change_tracker.process_event(
                    event, log_index, self.factions, self.spirits)
                del self._pending_agenda_log_info[faction_id]
                continue

            self._log_event(event)

    def update(self, dt):
        self.animation.update(dt)
        # Incrementally reveal hexes, gold, and wars as animations become active
        if self._display_hex_ownership is not None:
            self.orchestrator.apply_hex_reveals(self._display_hex_ownership)
        if self._display_factions is not None:
            self.orchestrator.apply_gold_deltas(self._display_factions)
        if self._display_wars is not None:
            self.orchestrator.apply_war_reveals(self._display_wars)
        self.orchestrator.try_show_deferred_phase_ui(self)
        # Clear display state when all animations are done
        if self._display_hex_ownership is not None and not self.orchestrator.has_animations_playing():
            self._clear_display_state()

    def _register_ui_rects_for_tooltips(self):
        """Populate the popup_manager rect registry for tooltip placement scoring."""
        rects: list[tuple[pygame.Rect, int]] = []

        # TEXT rects (high penalty) — areas with important readable info
        # HUD bar
        rects.append((pygame.Rect(0, 0, SCREEN_WIDTH, 40), _WEIGHT_TEXT))
        # Faction overview strip
        rects.append((pygame.Rect(0, 42, SCREEN_WIDTH, 55), _WEIGHT_TEXT))
        # Event log
        rects.append((pygame.Rect(SCREEN_WIDTH - 300, SCREEN_HEIGHT - 200, 290, 190), _WEIGHT_TEXT))
        # Faction panel
        fp = self.ui_renderer.faction_panel_rect
        if fp:
            rects.append((fp, _WEIGHT_TEXT))
        # Spirit panel
        sp = self.ui_renderer.spirit_panel_rect
        if sp:
            rects.append((sp, _WEIGHT_TEXT))
        # Pinned popup rects
        for popup in self.popup_manager._stack:
            rects.append((popup.rect, _WEIGHT_TEXT))

        # NON_TEXT rects (low penalty) — buttons and cards
        for btn in self.action_buttons + self.faction_buttons + self.idol_buttons:
            rects.append((btn.rect, _WEIGHT_NON_TEXT))
        if self.submit_button:
            rects.append((self.submit_button.rect, _WEIGHT_NON_TEXT))
        # Card rects (if cards are showing)
        if self.agenda_hand:
            for cr in self._calc_left_choice_card_rects(len(self.agenda_hand)):
                rects.append((cr, _WEIGHT_NON_TEXT))
        if self.change_cards:
            for cr in self._calc_left_choice_card_rects(len(self.change_cards)):
                rects.append((cr, _WEIGHT_NON_TEXT))
        if self.spoils_cards:
            y_offset = _CHOICE_CARD_Y
            for cards in self.spoils_cards:
                for cr in self._calc_left_choice_card_rects(len(cards), y=y_offset):
                    rects.append((cr, _WEIGHT_NON_TEXT))
                y_offset += _MULTI_CHOICE_BLOCK_STEP
        if self.spoils_change_cards:
            y_offset = _CHOICE_CARD_Y
            for cards in self.spoils_change_cards:
                for cr in self._calc_left_choice_card_rects(len(cards), y=y_offset):
                    rects.append((cr, _WEIGHT_NON_TEXT))
                y_offset += _MULTI_CHOICE_BLOCK_STEP

        set_ui_rects(rects)

    def render(self, screen: pygame.Surface):
        screen.fill((10, 10, 18))

        # Parse idol data for rendering
        render_idols = []
        for idol_data in self.all_idols:
            if isinstance(idol_data, dict):
                render_idols.append(type('Idol', (), {
                    'type': IdolType(idol_data['type']),
                    'position': type('Pos', (), {
                        'q': idol_data['position']['q'],
                        'r': idol_data['position']['r'],
                    })(),
                    'owner_spirit': idol_data.get('owner_spirit'),
                })())

        # Parse wars for rendering (use display state if available)
        render_wars = []
        for w in self.display_wars:
            if isinstance(w, dict):
                war_obj = type('War', (), {
                    'faction_a': w.get('faction_a', ''),
                    'faction_b': w.get('faction_b', ''),
                    'is_ripe': w.get('is_ripe', False),
                    'battleground': None,
                })()
                if w.get("battleground"):
                    bg = w["battleground"]
                    war_obj.battleground = (
                        type('H', (), {'q': bg[0]['q'], 'r': bg[0]['r']})(),
                        type('H', (), {'q': bg[1]['q'], 'r': bg[1]['r']})(),
                    )
                render_wars.append(war_obj)

        # Draw hex grid (use display state if available)
        hex_own = self.display_hex_ownership
        highlight = None
        if self.phase == Phase.VAGRANT_PHASE.value:
            highlight = {h for h, o in hex_own.items() if o is None}

        # Compute preview idol (post-confirm or pre-confirm)
        render_preview_idol = self.preview_idol
        if not render_preview_idol and self.selected_idol_type and self.selected_hex:
            render_preview_idol = (self.selected_idol_type,
                                   self.selected_hex[0], self.selected_hex[1])

        # Build spirit_id -> player_index mapping (sorted for stability)
        spirit_index_map = {
            sid: i for i, sid in enumerate(sorted(self.spirits.keys()))
        }

        self.hex_renderer.draw_hex_grid(
            screen, hex_own,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            idols=render_idols, wars=render_wars,
            selected_hex=self.selected_hex,
            highlight_hexes=highlight,
            spirit_index_map=spirit_index_map,
            preview_idol=render_preview_idol,
        )

        # Draw world-space effect animations (border text + arrows)
        self.orchestrator.render_effect_animations(screen, screen_space_only=False, small_font=self.small_font)

        # Draw HUD
        self.ui_renderer.draw_hud(screen, self.phase, self.turn,
                                   self.spirits, self.app.my_spirit_id)

        # Compute preview guidance dict
        preview_guid_dict = None
        preview_fid = self.preview_guidance or self.selected_faction
        if preview_fid:
            my_name = self.spirits.get(self.app.my_spirit_id, {}).get("name", "?")
            preview_guid_dict = {preview_fid: my_name}

        # Draw faction overview strip (with war indicators, use display state)
        disp_factions = self.display_factions
        animated_agenda_factions = self.animation.get_persistent_agenda_factions()
        self.agenda_label_rects = self.ui_renderer.draw_faction_overview(
            screen, disp_factions, self.faction_agendas_this_turn,
            wars=render_wars,
            faction_spoils_agendas=self.faction_spoils_agendas_this_turn,
            spirits=self.spirits,
            preview_guidance=preview_guid_dict,
            animated_agenda_factions=animated_agenda_factions,
        )

        # Draw persistent agenda slide animations (on top of overview strip)
        self.orchestrator.render_persistent_agenda_animations(screen)

        # Draw screen-space effect animations (gold text overlays)
        self.orchestrator.render_effect_animations(screen, screen_space_only=True, small_font=self.small_font)

        # Draw spirit panel OR faction panel (right side, mutually exclusive)
        self.panel_change_rects = []
        if self.spirit_panel_spirit_id:
            # Spirit panel
            spirit = self.spirits.get(self.spirit_panel_spirit_id, {})
            self.ui_renderer.draw_spirit_panel(
                screen, spirit, self.factions, self.all_idols,
                self.hex_ownership, SCREEN_WIDTH - 240, 102, 230,
                my_spirit_id=self.spirit_panel_spirit_id,
            )
            # Clear faction panel rects
            self.ui_renderer.faction_panel_rect = None
            self.ui_renderer.panel_guided_rect = None
            self.ui_renderer.panel_worship_rect = None
            self.ui_renderer.panel_war_rect = None
        else:
            # Faction panel
            pf = self.panel_faction
            if not pf:
                my_spirit = self.spirits.get(self.app.my_spirit_id, {})
                pf = my_spirit.get("guided_faction")
            real_faction_data = self.factions.get(pf) if pf else None
            if pf and real_faction_data:
                self.ui_renderer.draw_faction_panel(
                    screen, real_faction_data,
                    SCREEN_WIDTH - 240, 102, 230,
                    spirits=self.spirits,
                    preview_guidance=preview_guid_dict,
                    change_tracker=self.change_tracker,
                    panel_faction_id=pf,
                    highlight_log_idx=self.highlighted_log_index,
                    change_rects=self.panel_change_rects,
                    wars=render_wars,
                )
            else:
                self.ui_renderer.faction_panel_rect = None
                self.ui_renderer.panel_guided_rect = None
                self.ui_renderer.panel_worship_rect = None
                self.ui_renderer.panel_war_rect = None
            # Clear spirit panel rects
            self.ui_renderer.spirit_panel_rect = None
            self.ui_renderer.spirit_panel_guidance_rect = None
            self.ui_renderer.spirit_panel_influence_rect = None
            self.ui_renderer.spirit_panel_worship_rects.clear()

        # Draw event log (bottom right)
        self.ui_renderer.draw_event_log(
            screen, self.event_log,
            SCREEN_WIDTH - 300, SCREEN_HEIGHT - 200, 290, 190,
            scroll_offset=self.event_log_scroll_offset,
            highlight_log_idx=self.highlighted_log_index,
        )

        # Draw waiting indicator (suppress while UI is deferred for animations)
        if self.waiting_for and not self.orchestrator.deferred_phase_start:
            self.ui_renderer.draw_waiting_overlay(screen, self.waiting_for, self.spirits)

        # Reset tooltip registry for this frame (before phase-specific UI
        # which may offer tooltips, and before the main tooltip registration block)
        self.tooltip_registry.clear()

        # Phase-specific UI
        if self.phase == Phase.VAGRANT_PHASE.value:
            self._render_vagrant_ui(screen)
        elif self.phase == Phase.AGENDA_PHASE.value:
            self._render_agenda_ui(screen)
        elif self.phase == "change_choice":
            self._render_change_ui(screen)
        elif self.phase == "ejection_choice":
            self._render_ejection_ui(screen)
        elif self.phase == "spoils_choice":
            self._render_spoils_ui(screen)
        elif self.phase == "spoils_change_choice":
            self._render_spoils_change_ui(screen)

        # Register UI rects for tooltip placement scoring
        self._register_ui_rects_for_tooltips()

        # Rebuilt only while idol hover tooltip is actively rendered.
        self.idol_tooltip_spirit_rects = []

        # Agenda hover tooltips
        if self.hovered_card_tooltip and self.hovered_card_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self.hovered_card_tooltip, _GUIDANCE_HOVER_REGIONS,
                self.hovered_card_rect.centerx, self.hovered_card_rect.top,
            ))
        elif self.hovered_agenda_label_fid and self.hovered_agenda_label_rect:
            fmod = self._get_faction_modifiers(self.hovered_agenda_label_fid)
            agenda_str = self.hovered_agenda_label_type or ""
            if agenda_str:
                tooltip = build_agenda_tooltip(
                    agenda_str, fmod, is_spoils=self.hovered_agenda_label_is_spoils)
                self.tooltip_registry.offer(TooltipDescriptor(
                    tooltip, _GUIDANCE_HOVER_REGIONS,
                    self.hovered_agenda_label_rect.centerx,
                    self.hovered_agenda_label_rect.bottom, below=True,
                ))
        elif self.hovered_anim_tooltip and self.hovered_anim_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self.hovered_anim_tooltip, _GUIDANCE_HOVER_REGIONS,
                self.hovered_anim_rect.centerx,
                self.hovered_anim_rect.bottom, below=True,
            ))

        # Idol hover tooltip (custom renderer for clickable spirit names;
        # also offer text to registry for right-click-to-pin)
        if self.hovered_idol:
            if not self.popup_manager.has_popups():
                self._render_idol_tooltip(screen)
            tooltip_text, _ = self._build_idol_tooltip_text(self.hovered_idol)
            mx, my = pygame.mouse.get_pos()
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip_text, _GUIDANCE_HOVER_REGIONS, mx, my,
            ))

        # Faction panel guided/worship hover tooltips
        if self.hovered_panel_guided:
            tooltip = self._build_guidance_panel_tooltip(
                self.ui_renderer.panel_guided_spirit_id)
            r = self.ui_renderer.panel_guided_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))
        elif self.hovered_panel_worship and self.ui_renderer.panel_faction_id:
            tooltip = self._build_worship_panel_tooltip(
                self.ui_renderer.panel_faction_id)
            r = self.ui_renderer.panel_worship_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))
        elif self.hovered_panel_war and self.ui_renderer.panel_war_rect:
            r = self.ui_renderer.panel_war_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                _WAR_TOOLTIP, _WAR_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))

        # Spirit panel hover tooltips
        if self.hovered_spirit_panel_guidance and self.spirit_panel_spirit_id:
            spirit = self.spirits.get(self.spirit_panel_spirit_id, {})
            if spirit.get("guided_faction"):
                tooltip = self._build_guidance_panel_tooltip(self.spirit_panel_spirit_id)
            else:
                tooltip = self._GUIDANCE_GENERIC_TOOLTIP
            r = self.ui_renderer.spirit_panel_guidance_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))
        elif self.hovered_spirit_panel_influence:
            r = self.ui_renderer.spirit_panel_influence_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                _INFLUENCE_TOOLTIP, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))
        elif self.hovered_spirit_panel_worship and self.spirit_panel_spirit_id:
            tooltip = self._build_spirit_worship_tooltip(
                self.hovered_spirit_panel_worship, self.spirit_panel_spirit_id)
            r = self.ui_renderer.spirit_panel_worship_rects[self.hovered_spirit_panel_worship]
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))

        # Render the single active tooltip (suppressed when popups are open)
        self.tooltip_registry.render(screen, self.small_font, self.popup_manager)

        # Pinned popups (drawn on top of everything)
        self.popup_manager.render(screen, self.small_font)

    def _build_idol_tooltip_text(self, idol):
        idol_type = idol.type
        owner_id = idol.owner_spirit
        owner_name = (self.spirits.get(owner_id, {}).get("name", owner_id[:6])
                      if owner_id else "Unknown")
        clickable_spirits: dict[str, str] = {}
        if owner_id:
            clickable_spirits[owner_id] = owner_name
        type_name = idol_type.value.title()

        # Determine territory ownership
        q, r = idol.position.q, idol.position.r
        faction_id = self.hex_ownership.get((q, r))
        faction_name = FACTION_DISPLAY_NAMES.get(faction_id, faction_id) if faction_id else None

        if faction_id:
            # Idol is in a faction's territory
            worship_id = None
            fdata = self.factions.get(faction_id)
            if isinstance(fdata, dict):
                worship_id = fdata.get("worship_spirit")
            worship_name = (self.spirits.get(worship_id, {}).get("name", worship_id[:6])
                            if worship_id else None)
            if worship_id and worship_name:
                clickable_spirits[worship_id] = worship_name
            header = (f"{type_name} Idol placed by {owner_name}, "
                      f"currently in the custody of {faction_name}")
            if idol_type == IdolType.BATTLE:
                if worship_name:
                    vp_line = (f"When {faction_name} wins a War, the Spirit they "
                               f"Worship - {worship_name} - gains {BATTLE_IDOL_VP} VP "
                               f"at the end of the turn.")
                else:
                    vp_line = (f"When {faction_name} wins a War and Worships a Spirit, "
                               f"that Spirit gains {BATTLE_IDOL_VP} VP at the end of the turn.")
            elif idol_type == IdolType.AFFLUENCE:
                if worship_name:
                    vp_line = (f"When {faction_name} gains gold, the Spirit they "
                               f"Worship - {worship_name} - gains {AFFLUENCE_IDOL_VP} VP "
                               f"at the end of the turn.")
                else:
                    vp_line = (f"When {faction_name} gains gold and Worships a Spirit, "
                               f"that Spirit gains {AFFLUENCE_IDOL_VP} VP at the end of the turn.")
            else:  # SPREAD
                if worship_name:
                    vp_line = (f"When {faction_name} gains a Territory, the Spirit they "
                               f"Worship - {worship_name} - gains {SPREAD_IDOL_VP} VP "
                               f"at the end of the turn.")
                else:
                    vp_line = (f"When {faction_name} gains a Territory and Worships a Spirit, "
                               f"that Spirit gains {SPREAD_IDOL_VP} VP at the end of the turn.")
        else:
            # Idol is on neutral ground
            header = (f"{type_name} Idol placed by {owner_name}, "
                      f"currently on neutral grounds")
            if idol_type == IdolType.BATTLE:
                vp_line = (f"After a Faction claims the Territory this Idol is on, "
                           f"it will grant the Spirit they Worship {BATTLE_IDOL_VP} VP "
                           f"for each War the Faction wins.")
            elif idol_type == IdolType.AFFLUENCE:
                vp_line = (f"After a Faction claims the Territory this Idol is on, "
                           f"it will grant the Spirit they Worship {AFFLUENCE_IDOL_VP} VP "
                           f"for each gold the Faction gains.")
            else:  # SPREAD
                vp_line = (f"After a Faction claims the Territory this Idol is on, "
                           f"it will grant the Spirit they Worship {SPREAD_IDOL_VP} VP "
                           f"for each Territory the Faction gains.")

        return f"{header}\n{vp_line}", clickable_spirits

    def _render_idol_tooltip(self, screen):
        tooltip_text, clickable_spirits = self._build_idol_tooltip_text(self.hovered_idol)
        mx, my = pygame.mouse.get_pos()
        max_width = 350
        lines = self._wrap_lines(tooltip_text, self.small_font, max_width)
        line_h = self.small_font.get_linesize()
        rendered_widths = [self.small_font.size(line)[0] for line in lines]
        content_w = max(rendered_widths) if rendered_widths else 0
        tip_w = content_w + 16
        tip_h = len(lines) * line_h + 12
        tip_x = mx - tip_w // 2
        if tip_x < 4:
            tip_x = 4
        if tip_x + tip_w > SCREEN_WIDTH - 4:
            tip_x = SCREEN_WIDTH - 4 - tip_w
        tip_y = my - tip_h - 4
        tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
        pygame.draw.rect(screen, (40, 40, 50), tip_rect, border_radius=4)
        pygame.draw.rect(screen, (150, 150, 100), tip_rect, 1, border_radius=4)

        keyword_names = list(dict.fromkeys(clickable_spirits.values()))
        name_rects = self._render_rich_lines(
            screen, self.small_font, lines, tip_x + 8, tip_y + 6,
            keywords=keyword_names,
            hovered_keyword=None,
            normal_color=(255, 220, 150),
            keyword_color=(140, 220, 255),
            hovered_keyword_color=(140, 220, 255),
        )

        self.idol_tooltip_spirit_rects = []
        for sid, name in clickable_spirits.items():
            for rect in name_rects.get(name, []):
                self.idol_tooltip_spirit_rects.append((sid, rect))

    _GUIDANCE_TITLE_TOOLTIP = (
        "Select a Faction to Guide. If you are not the only Spirit "
        "attempting to Guide that Faction this turn, both of you will "
        "fail and choose again next turn.\n\n"
        "If successful, for the next 3 turns you will choose among "
        "several options whenever that Faction would ordinarily draw a "
        "random Agenda card or Change modifier: 3 additional choices "
        "this turn, 2 additional choices next turn and 1 additional "
        "choice the turn after that. You will be ejected after this "
        "last turn of Guidance, but you will leave behind a lasting "
        "effect: adding an additional Agenda card to its Agenda deck.\n\n"
        "Additionally, every time you begin and end Guidance of a "
        "Faction, you will attempt to become Worshipped by that Faction. "
        "If that Faction is not Worshipping any Spirit, you automatically "
        "succeed. If they are Worshipping another Spirit, you become "
        "their new object of Worship if you have as many or more Idols "
        "in the Faction's Territories as the Spirit they currently Worship.\n\n"
        "You cannot begin Guiding a Faction that Worships you."
    )

    _IDOL_TITLE_TOOLTIP = (
        "Choose a neutral Territory and Idol type to place. When inside "
        "a Faction's Territory, the Spirit Worshipped by that Faction "
        "gains Victory Points at the end of every turn if that Faction "
        "succeeds at winning Wars, gaining gold or expanding their "
        "Territory, depending on which Idols are present.\n\n"
        "Idols in neutral Territory beckon all neighboring Factions: "
        "if they Expand, Territories with Idols in them are prioritized "
        "over ones without Idols."
    )

    def _render_vagrant_ui(self, screen):
        # Draw "Guidance" title
        if self.guidance_title_rect and self.faction_buttons:
            title_surf = self.font.render("Guidance", True, (200, 200, 220))
            tx = self.guidance_title_rect.centerx - title_surf.get_width() // 2
            ty = self.guidance_title_rect.y
            screen.blit(title_surf, (tx, ty))
            draw_dotted_underline(screen, tx, ty + title_surf.get_height(),
                                  title_surf.get_width())

        # Draw "Idol placement" title
        if self.idol_title_rect and self.idol_buttons:
            title_surf = self.font.render("Idol placement", True, (200, 200, 220))
            tx = self.idol_title_rect.centerx - title_surf.get_width() // 2
            ty = self.idol_title_rect.y
            screen.blit(title_surf, (tx, ty))
            draw_dotted_underline(screen, tx, ty + title_surf.get_height(),
                                  title_surf.get_width())

        # Draw faction buttons (left) with selection highlight
        for btn in self.faction_buttons:
            if self.selected_faction and btn.text == FACTION_DISPLAY_NAMES.get(self.selected_faction):
                pygame.draw.rect(screen, (255, 255, 255), btn.rect.inflate(4, 4), 2, border_radius=8)
            btn.draw(screen, self.font)

        # Draw idol buttons (right) with selection highlight
        for btn in self.idol_buttons:
            if self.selected_idol_type and btn.text.lower() == self.selected_idol_type:
                pygame.draw.rect(screen, (255, 255, 255), btn.rect.inflate(4, 4), 2, border_radius=8)
            btn.draw(screen, self.font)

        # Register button tooltips with the tooltip registry
        for btn in self.faction_buttons:
            if btn.tooltip and btn.hovered and (btn.tooltip_always or not btn.enabled):
                self.tooltip_registry.offer(TooltipDescriptor(
                    btn.tooltip, _GUIDANCE_HOVER_REGIONS,
                    btn.rect.centerx, btn.rect.top,
                ))
        for btn in self.idol_buttons:
            if btn.tooltip and btn.hovered and (btn.tooltip_always or not btn.enabled):
                self.tooltip_registry.offer(TooltipDescriptor(
                    btn.tooltip, _GUIDANCE_HOVER_REGIONS,
                    btn.rect.centerx, btn.rect.top,
                ))

        # Title tooltips
        if self.guidance_title_hovered and self.guidance_title_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self._GUIDANCE_TITLE_TOOLTIP, _GUIDANCE_HOVER_REGIONS,
                self.guidance_title_rect.centerx,
                self.guidance_title_rect.bottom, below=True,
            ))
        if self.idol_title_hovered and self.idol_title_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self._IDOL_TITLE_TOOLTIP, _GUIDANCE_HOVER_REGIONS,
                self.idol_title_rect.centerx,
                self.idol_title_rect.bottom, below=True,
            ))

        # Selection info at bottom
        y = SCREEN_HEIGHT - 110
        parts = []
        if self.selected_faction:
            fname = FACTION_DISPLAY_NAMES.get(self.selected_faction, self.selected_faction)
            parts.append(f"Guide: {fname}")
        if self.selected_idol_type:
            parts.append(f"Idol: {self.selected_idol_type}")
        if self.selected_hex:
            parts.append(f"Hex: ({self.selected_hex[0]}, {self.selected_hex[1]})")
        if parts:
            text = self.font.render(" | ".join(parts), True, (200, 200, 220))
            screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, y))

        # Submit button
        if self.submit_button:
            has_guide = bool(self.selected_faction)
            has_idol = bool(self.selected_idol_type and self.selected_hex)
            can_guide = bool(self.phase_options.get("available_factions"))
            can_place_idol = bool(self.idol_buttons) and bool(self.phase_options.get("neutral_hexes"))
            if can_guide and can_place_idol:
                self.submit_button.enabled = has_guide and has_idol
            else:
                self.submit_button.enabled = has_guide or has_idol
            self.submit_button.draw(screen, self.font)

    def _get_current_faction_modifiers(self) -> dict:
        """Get the change_modifiers for the current player's guided faction."""
        my_spirit = self.spirits.get(self.app.my_spirit_id, {})
        fid = my_spirit.get("guided_faction")
        if fid and fid in self.factions:
            return self.factions[fid].get("change_modifiers", {})
        return {}

    def _render_agenda_ui(self, screen):
        if self.agenda_hand:
            my_spirit = self.spirits.get(self.app.my_spirit_id, {})
            faction_id = my_spirit.get("guided_faction", "")
            faction_name = FACTION_DISPLAY_NAMES.get(faction_id, faction_id) if faction_id else "your Faction"
            title = self.font.render(f"Choose an Agenda for {faction_name} to play.", True, (200, 200, 220))
            title_x = max(20, (_HEX_MAP_LEFT_X - title.get_width()) // 2)
            screen.blit(title, (title_x, 106))

            card_rects = self._calc_left_choice_card_rects(len(self.agenda_hand))
            start_x = card_rects[0].x if card_rects else 20
            modifiers = self._get_current_faction_modifiers()
            self.ui_renderer.draw_card_hand(
                screen, self.agenda_hand,
                self.selected_agenda_index,
                start_x, 136,
                modifiers=modifiers,
                card_images=agenda_card_images,
            )

        if self.submit_button:
            self.submit_button.enabled = self.selected_agenda_index >= 0
            self.submit_button.draw(screen, self.font)

    def _render_change_ui(self, screen):
        if not self.change_cards:
            return
        title = self.font.render("Choose a Change modifier:", True, (200, 200, 220))
        title_x = max(20, (_HEX_MAP_LEFT_X - title.get_width()) // 2)
        screen.blit(title, (title_x, 106))

        hand = []
        for card_name in self.change_cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        card_rects = self._calc_left_choice_card_rects(len(hand))
        start_x = card_rects[0].x if card_rects else 20
        start_y = 136
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            card_images=agenda_card_images,
        )

    def _render_ejection_ui(self, screen):
        faction_name = FACTION_DISPLAY_NAMES.get(self.ejection_faction, self.ejection_faction)
        title_text = (
            f"As the last remnants of your Influence leave the {faction_name} faction, "
            f"you nudge their future. Choose an Agenda card to add to {faction_name}'s Agenda deck:"
        )
        keywords = ["Influence", "Agenda deck"]
        text_x = 20
        max_text_width = max(220, _HEX_MAP_LEFT_X - 30)
        lines = self._wrap_lines(title_text, self.font, max_text_width)
        line_h = self.font.get_linesize()
        title_h = len(lines) * line_h
        buttons_top = min((btn.rect.top for btn in self.action_buttons), default=SCREEN_HEIGHT - 200)
        text_y = max(96, buttons_top - title_h - 10)
        self.ejection_keyword_rects = self._render_rich_lines(
            screen, self.font, lines, text_x, text_y,
            keywords=keywords,
            hovered_keyword=self.hovered_ejection_keyword,
            normal_color=(200, 200, 220),
            keyword_color=(100, 220, 210),
            hovered_keyword_color=(140, 255, 245),
        )

        # Highlight selected button
        for btn in self.action_buttons:
            if self.selected_ejection_type and btn.text.lower() == self.selected_ejection_type:
                btn.color = (120, 80, 180)
            else:
                btn.color = (80, 60, 130)
            btn.draw(screen, self.font)

        # Register ejection button tooltips with the registry
        for btn in self.action_buttons:
            if btn.tooltip and btn.hovered and (btn.tooltip_always or not btn.enabled):
                self.tooltip_registry.offer(TooltipDescriptor(
                    btn.tooltip, _GUIDANCE_HOVER_REGIONS,
                    btn.rect.centerx, btn.rect.top,
                ))
        if self.hovered_ejection_keyword:
            tooltip = _INFLUENCE_TOOLTIP if self.hovered_ejection_keyword == "Influence" else _AGENDA_DECK_TOOLTIP
            rects = self.ejection_keyword_rects.get(self.hovered_ejection_keyword, [])
            if rects:
                mx, my = pygame.mouse.get_pos()
                anchor = rects[0]
                for rect in rects:
                    if rect.collidepoint(mx, my):
                        anchor = rect
                        break
                self.tooltip_registry.offer(TooltipDescriptor(
                    tooltip, _GUIDANCE_HOVER_REGIONS,
                    anchor.centerx, anchor.bottom, below=True,
                ))

        # Selection feedback
        if self.selected_ejection_type:
            sel_text = self.font.render(
                f"Selected: {self.selected_ejection_type.title()}", True, (200, 200, 220))
            screen.blit(sel_text, (20, SCREEN_HEIGHT - 110))

        # Confirm button
        if self.submit_button:
            self.submit_button.enabled = self.selected_ejection_type is not None
            self.submit_button.draw(screen, self.font)

    def _wrap_lines(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        """Simple word-wrap utility for inline UI text blocks."""
        lines = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                lines.append("")
                continue
            words = paragraph.split()
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if font.size(candidate)[0] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return lines

    def _render_rich_lines(self, surface: pygame.Surface, font: pygame.font.Font,
                           lines: list[str], x: int, y: int,
                           keywords: list[str], hovered_keyword: str | None,
                           normal_color: tuple[int, int, int],
                           keyword_color: tuple[int, int, int],
                           hovered_keyword_color: tuple[int, int, int]) -> dict[str, list[pygame.Rect]]:
        """Render wrapped lines with keyword underline styling and return keyword rects."""
        keyword_rects: dict[str, list[pygame.Rect]] = {k: [] for k in keywords}
        line_h = font.get_linesize()

        for line_idx, line in enumerate(lines):
            cy = y + line_idx * line_h
            if not keywords:
                surface.blit(font.render(line, True, normal_color), (x, cy))
                continue

            occurrences = []
            for kw in keywords:
                start = 0
                while True:
                    pos = line.find(kw, start)
                    if pos < 0:
                        break
                    occurrences.append((pos, pos + len(kw), kw))
                    start = pos + len(kw)

            if not occurrences:
                surface.blit(font.render(line, True, normal_color), (x, cy))
                continue

            occurrences.sort(key=lambda o: o[0])
            filtered = []
            last_end = 0
            for seg_start, seg_end, kw in occurrences:
                if seg_start >= last_end:
                    filtered.append((seg_start, seg_end, kw))
                    last_end = seg_end

            cursor_x = x
            pos = 0
            for seg_start, seg_end, kw in filtered:
                if seg_start > pos:
                    normal_text = line[pos:seg_start]
                    surf = font.render(normal_text, True, normal_color)
                    surface.blit(surf, (cursor_x, cy))
                    cursor_x += surf.get_width()

                kw_text = line[seg_start:seg_end]
                color = hovered_keyword_color if kw == hovered_keyword else keyword_color
                surf = font.render(kw_text, True, color)
                surface.blit(surf, (cursor_x, cy))
                kw_rect = pygame.Rect(cursor_x, cy, surf.get_width(), line_h)
                keyword_rects[kw].append(kw_rect)

                underline_y = cy + line_h - 2
                ux = cursor_x
                ux_end = cursor_x + surf.get_width()
                while ux < ux_end:
                    dot_end = min(ux + 2, ux_end)
                    pygame.draw.line(surface, color, (ux, underline_y), (dot_end, underline_y), 1)
                    ux += 5

                cursor_x += surf.get_width()
                pos = seg_end

            if pos < len(line):
                tail = line[pos:]
                surf = font.render(tail, True, normal_color)
                surface.blit(surf, (cursor_x, cy))

        return keyword_rects

    def _render_spoils_ui(self, screen):
        if not self.spoils_cards:
            return
        modifiers = self._get_current_faction_modifiers()
        y_offset = 106
        for war_idx, cards in enumerate(self.spoils_cards):
            opponent = self.spoils_opponents[war_idx] if war_idx < len(self.spoils_opponents) else ""
            opponent_name = FACTION_DISPLAY_NAMES.get(opponent, opponent)
            selected = self.spoils_selections[war_idx] if war_idx < len(self.spoils_selections) else -1
            title_text = f"Spoils of War vs {opponent_name} - Choose an agenda:" if opponent_name else "Spoils of War - Choose an agenda:"
            title = self.font.render(title_text, True, (255, 200, 100))
            title_x = max(20, (_HEX_MAP_LEFT_X - title.get_width()) // 2)
            screen.blit(title, (title_x, y_offset))

            hand = [{"agenda_type": card} for card in cards]
            card_rects = self._calc_left_choice_card_rects(len(hand), y=y_offset + 30)
            start_x = card_rects[0].x if card_rects else 20
            start_y = y_offset + 30
            self.ui_renderer.draw_card_hand(
                screen, hand, selected,
                start_x, start_y,
                modifiers=modifiers,
                card_images=agenda_card_images,
                is_spoils=True,
            )
            y_offset += _MULTI_CHOICE_BLOCK_STEP

    def _render_spoils_change_ui(self, screen):
        if not self.spoils_change_cards:
            return
        y_offset = 106
        for choice_idx, cards in enumerate(self.spoils_change_cards):
            opponent = self.spoils_change_opponents[choice_idx] if choice_idx < len(self.spoils_change_opponents) else ""
            opponent_name = FACTION_DISPLAY_NAMES.get(opponent, opponent)
            selected = self.spoils_change_selections[choice_idx] if choice_idx < len(self.spoils_change_selections) else -1
            title_text = f"Spoils of War vs {opponent_name} - Choose a Change modifier:" if opponent_name else "Spoils of War - Choose a Change modifier:"
            title = self.font.render(title_text, True, (255, 200, 100))
            title_x = max(20, (_HEX_MAP_LEFT_X - title.get_width()) // 2)
            screen.blit(title, (title_x, y_offset))

            hand = []
            for card_name in cards:
                desc = self.ui_renderer._build_modifier_description(card_name)
                hand.append({"agenda_type": card_name, "description": desc})
            card_rects = self._calc_left_choice_card_rects(len(hand), y=y_offset + 30)
            start_x = card_rects[0].x if card_rects else 20
            start_y = y_offset + 30
            self.ui_renderer.draw_card_hand(
                screen, hand, selected,
                start_x, start_y,
                card_images=agenda_card_images,
            )
            y_offset += _MULTI_CHOICE_BLOCK_STEP
