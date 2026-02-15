"""Primary gameplay scene: hex map, UI, phases."""

import pygame
from shared.constants import (
    MessageType, Phase, AgendaType, IdolType, MAP_SIDE_LENGTH,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES, FACTION_DISPLAY_NAMES, FACTION_COLORS,
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP,
)
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import UIRenderer, Button, draw_multiline_tooltip, build_agenda_tooltip, build_modifier_tooltip
from client.renderer.animation import AnimationManager, TextAnimation
from client.renderer.assets import load_assets, agenda_card_images
from client.input_handler import InputHandler
from client.scenes.animation_orchestrator import AnimationOrchestrator
from client.scenes.change_tracker import FactionChangeTracker

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
        self.spoils_cards: list[str] = []
        self.spoils_change_cards: list[str] = []
        self.spoils_opponent: str = ""

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

        # Agenda hover tooltip state
        self.hovered_card_tooltip: str | None = None
        self.hovered_card_rect: pygame.Rect | None = None
        self.agenda_label_rects: dict[str, pygame.Rect] = {}
        self.hovered_agenda_label_fid: str | None = None
        self.hovered_agenda_label_rect: pygame.Rect | None = None
        self.hovered_anim_tooltip: str | None = None
        self.hovered_anim_rect: pygame.Rect | None = None

        # Faction panel / VP hover tooltip state
        self.hovered_panel_guided: bool = False
        self.hovered_panel_worship: bool = False
        self.hovered_vp_spirit_id: str | None = None

        # Change tracking for faction panel
        self.change_tracker = FactionChangeTracker()
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
            # VP HUD hover detection
            self._update_vp_hover(event.pos)

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
                for i, rect in enumerate(self._calc_card_rects(
                        len(self.agenda_hand), y=SCREEN_HEIGHT - 210, centered=True)):
                    if rect.collidepoint(event.pos):
                        self.selected_agenda_index = i
                        return

            # Check change card clicks
            if self.change_cards:
                for i, rect in enumerate(self._calc_card_rects(len(self.change_cards))):
                    if rect.collidepoint(event.pos):
                        self._submit_card_choice(i, MessageType.SUBMIT_CHANGE_CHOICE, "change_cards")
                        return

            # Check spoils card clicks
            if self.spoils_cards:
                for i, rect in enumerate(self._calc_card_rects(len(self.spoils_cards))):
                    if rect.collidepoint(event.pos):
                        self._submit_card_choice(i, MessageType.SUBMIT_SPOILS_CHOICE, "spoils_cards")
                        return

            # Check spoils change card clicks
            if self.spoils_change_cards:
                for i, rect in enumerate(self._calc_card_rects(len(self.spoils_change_cards))):
                    if rect.collidepoint(event.pos):
                        self._submit_card_choice(i, MessageType.SUBMIT_SPOILS_CHANGE_CHOICE, "spoils_change_cards")
                        return

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

            # Hex click
            hex_coord = self.hex_renderer.get_hex_at_screen(
                event.pos[0], event.pos[1], self.input_handler,
                SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
            )
            if hex_coord:
                self._handle_hex_click(hex_coord)

    def _handle_action_button(self, text: str):
        if self.ejection_pending:
            self.selected_ejection_type = text.lower()
            return

    def _handle_faction_select(self, faction_id: str):
        self.selected_faction = faction_id
        self.panel_faction = faction_id

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

    def handle_network(self, msg_type, payload):
        if msg_type == MessageType.GAME_START:
            self._update_state_from_snapshot(payload)
            self.change_tracker.snapshot_and_reset(self.factions, self.spirits)
            self.event_log.append(f"Game started! Turn {self.turn}")

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
                "trade": 0, "bond": 1, "steal": 2,
                "expand": 3, "expand_failed": 3, "expand_spoils": 3,
                "change": 4,
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
            elif active_sub_phase == "spoils_choice" and self.spoils_cards:
                self.phase = active_sub_phase
            elif active_sub_phase == "spoils_change_choice" and self.spoils_change_cards:
                self.phase = active_sub_phase
            # Log all events in original order
            for event in events:
                self._log_event(event)
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
            # Queue agenda events for animation
            if agenda_events:
                # Split setup events into a separate batch so they play
                # before resolution events (and don't visually overlap).
                setup_events = [e for e in agenda_events if e.get("is_setup")]
                if setup_events:
                    resolution_events = [e for e in agenda_events if not e.get("is_setup")]
                    self.orchestrator.queue.append(setup_events)
                    if resolution_events:
                        for e in resolution_events:
                            e["_setup_turn"] = True
                        self.orchestrator.queue.append(resolution_events)
                else:
                    self.orchestrator.queue.append(agenda_events)
                self.orchestrator.try_process_next_batch(
                    self.hex_ownership, self.small_font)
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
            self.spoils_cards = payload_cards if (payload_cards := self.phase_options.get("cards")) else []
            self.spoils_opponent = self.phase_options.get("loser", "")

        elif self.phase == "spoils_change_choice":
            self.spoils_change_cards = payload_cards if (payload_cards := self.phase_options.get("cards")) else []
            self.spoils_opponent = self.phase_options.get("loser", "")

        elif self.phase == "ejection_choice":
            self.ejection_pending = True
            self.ejection_faction = self.phase_options.get("faction", "")
            self.selected_ejection_type = None
            # Build ejection buttons
            y = SCREEN_HEIGHT - 200
            self.action_buttons = []
            for i, at in enumerate(AgendaType):
                btn = Button(
                    pygame.Rect(20 + i * 110, y, 100, 36),
                    at.value.title(), (80, 60, 130)
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

    def _build_guidance_tooltip(self, faction_id: str, is_blocked: bool) -> str:
        """Build tooltip for a Guidance faction button."""
        fdata = self.factions.get(faction_id, {})
        worship_id = fdata.get("worship_spirit") if isinstance(fdata, dict) else None
        lines = []
        if is_blocked:
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
        self.faction_buttons = []
        all_factions = available + blocked
        for i, fid in enumerate(all_factions):
            color = FACTION_COLORS.get(fid, (100, 100, 100))
            is_blocked = fid in blocked
            tooltip = self._build_guidance_tooltip(fid, is_blocked)
            btn = Button(
                pygame.Rect(_GUIDANCE_BTN_X, _BTN_START_Y + i * 40, _BTN_W, 34),
                FACTION_DISPLAY_NAMES.get(fid, fid),
                color=tuple(max(c // 2, 30) for c in color),
                text_color=(255, 255, 255),
                tooltip=tooltip,
                tooltip_always=True,
            )
            if is_blocked:
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

    def _update_idol_hover(self, mouse_pos):
        """Check if mouse is hovering over a placed idol on the hex map."""
        if not self.all_idols:
            self.hovered_idol = None
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
            return
        spirit_index_map = {
            sid: i for i, sid in enumerate(sorted(self.spirits.keys()))
        }
        self.hovered_idol = self.hex_renderer.get_idol_at_screen(
            mouse_pos[0], mouse_pos[1], render_idols,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            spirit_index_map,
        )

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
        self.hovered_agenda_label_rect = None
        self.hovered_anim_tooltip = None
        self.hovered_anim_rect = None

        mx, my = mouse_pos

        # Check card pickers (agenda hand, change cards, spoils cards, spoils change cards)
        modifiers = self._get_current_faction_modifiers()

        if self.agenda_hand:
            for i, rect in enumerate(self._calc_card_rects(
                    len(self.agenda_hand), y=SCREEN_HEIGHT - 210, centered=True)):
                if rect.collidepoint(mx, my):
                    atype = self.agenda_hand[i].get("agenda_type", "")
                    self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers)
                    self.hovered_card_rect = rect
                    return

        if self.change_cards:
            for i, rect in enumerate(self._calc_card_rects(len(self.change_cards))):
                if rect.collidepoint(mx, my):
                    self.hovered_card_tooltip = build_modifier_tooltip(self.change_cards[i])
                    self.hovered_card_rect = rect
                    return

        if self.spoils_cards:
            for i, rect in enumerate(self._calc_card_rects(len(self.spoils_cards))):
                if rect.collidepoint(mx, my):
                    atype = self.spoils_cards[i]
                    self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers, is_spoils=True)
                    self.hovered_card_rect = rect
                    return

        if self.spoils_change_cards:
            for i, rect in enumerate(self._calc_card_rects(len(self.spoils_change_cards))):
                if rect.collidepoint(mx, my):
                    self.hovered_card_tooltip = build_modifier_tooltip(self.spoils_change_cards[i])
                    self.hovered_card_rect = rect
                    return

        # Check faction ribbon agenda labels
        for fid, rect in self.agenda_label_rects.items():
            if rect.collidepoint(mx, my):
                self.hovered_agenda_label_fid = fid
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
        """Check if mouse is hovering over Guided by / Worshipping in faction panel."""
        mx, my = mouse_pos
        r = self.ui_renderer.panel_guided_rect
        self.hovered_panel_guided = r is not None and r.collidepoint(mx, my)
        r = self.ui_renderer.panel_worship_rect
        self.hovered_panel_worship = r is not None and r.collidepoint(mx, my)

    def _update_vp_hover(self, mouse_pos):
        """Check if mouse is hovering over a player name in the VP HUD."""
        mx, my = mouse_pos
        self.hovered_vp_spirit_id = None
        for sid, rect in self.ui_renderer.vp_hover_rects.items():
            if rect.collidepoint(mx, my):
                self.hovered_vp_spirit_id = sid
                return

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

    def _build_guidance_panel_tooltip(self, spirit_id: str) -> str:
        """Build tooltip text for Guided by / VP name hover."""
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
            self.faction_agendas_this_turn.clear()
            if not self.orchestrator.queue and self.animation.is_all_done():
                self.animation.start_agenda_fadeout()
        elif etype == "guide_contested":
            if self.app.my_spirit_id in event.get("spirits", []):
                self.preview_guidance = None

    def update(self, dt):
        self.animation.update(dt)
        # Incrementally reveal hexes as expand animations become active
        if self._display_hex_ownership is not None:
            self.orchestrator.apply_hex_reveals(self._display_hex_ownership)
        self.orchestrator.try_process_next_batch(self.hex_ownership, self.small_font)
        self.orchestrator.try_show_deferred_phase_ui(self)
        # Clear display state when all animations are done
        if self._display_hex_ownership is not None and not self.orchestrator.has_animations_playing():
            self._clear_display_state()

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
            spirits=self.spirits,
            preview_guidance=preview_guid_dict,
            animated_agenda_factions=animated_agenda_factions,
        )

        # Draw persistent agenda slide animations (on top of overview strip)
        self.orchestrator.render_persistent_agenda_animations(screen)

        # Draw screen-space effect animations (gold text overlays)
        self.orchestrator.render_effect_animations(screen, screen_space_only=True, small_font=self.small_font)

        # Draw faction panel (right side)
        pf = self.panel_faction
        if not pf:
            # Default to guided faction
            my_spirit = self.spirits.get(self.app.my_spirit_id, {})
            pf = my_spirit.get("guided_faction")
        self.panel_change_rects = []
        if pf and pf in disp_factions:
            self.ui_renderer.draw_faction_panel(
                screen, disp_factions[pf],
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
            self.ui_renderer.panel_guided_rect = None
            self.ui_renderer.panel_worship_rect = None

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

        # Agenda hover tooltips
        if self.hovered_card_tooltip and self.hovered_card_rect:
            draw_multiline_tooltip(
                screen, self.small_font, self.hovered_card_tooltip,
                anchor_x=self.hovered_card_rect.centerx,
                anchor_y=self.hovered_card_rect.top,
            )
        elif self.hovered_agenda_label_fid and self.hovered_agenda_label_rect:
            fmod = self._get_faction_modifiers(self.hovered_agenda_label_fid)
            agenda_str = self.faction_agendas_this_turn.get(self.hovered_agenda_label_fid, "")
            if agenda_str:
                tooltip = build_agenda_tooltip(agenda_str, fmod)
                draw_multiline_tooltip(
                    screen, self.small_font, tooltip,
                    anchor_x=self.hovered_agenda_label_rect.centerx,
                    anchor_y=self.hovered_agenda_label_rect.bottom,
                    below=True,
                )
        elif self.hovered_anim_tooltip and self.hovered_anim_rect:
            draw_multiline_tooltip(
                screen, self.small_font, self.hovered_anim_tooltip,
                anchor_x=self.hovered_anim_rect.centerx,
                anchor_y=self.hovered_anim_rect.bottom,
                below=True,
            )

        # Idol hover tooltip (drawn last so it's on top)
        if self.hovered_idol:
            self._render_idol_tooltip(screen)

        # Faction panel guided/worship hover tooltips
        if self.hovered_panel_guided and self.ui_renderer.panel_guided_spirit_id:
            tooltip = self._build_guidance_panel_tooltip(
                self.ui_renderer.panel_guided_spirit_id)
            r = self.ui_renderer.panel_guided_rect
            draw_multiline_tooltip(
                screen, self.small_font, tooltip,
                anchor_x=r.centerx, anchor_y=r.bottom, below=True,
            )
        elif self.hovered_panel_worship and self.ui_renderer.panel_faction_id:
            tooltip = self._build_worship_panel_tooltip(
                self.ui_renderer.panel_faction_id)
            r = self.ui_renderer.panel_worship_rect
            draw_multiline_tooltip(
                screen, self.small_font, tooltip,
                anchor_x=r.centerx, anchor_y=r.bottom, below=True,
            )

        # VP HUD name hover tooltip
        if self.hovered_vp_spirit_id:
            spirit = self.spirits.get(self.hovered_vp_spirit_id, {})
            if spirit.get("guided_faction"):
                tooltip = self._build_guidance_panel_tooltip(
                    self.hovered_vp_spirit_id)
                r = self.ui_renderer.vp_hover_rects[self.hovered_vp_spirit_id]
                draw_multiline_tooltip(
                    screen, self.small_font, tooltip,
                    anchor_x=r.centerx, anchor_y=r.bottom, below=True,
                )

    _IDOL_VP_TEXT = {
        IdolType.BATTLE: f"{BATTLE_IDOL_VP} VP for each war won\nby the Worshipping Faction",
        IdolType.AFFLUENCE: f"{AFFLUENCE_IDOL_VP} VP for each gold gained\nby the Worshipping Faction",
        IdolType.SPREAD: f"{SPREAD_IDOL_VP} VP for each territory gained\nby the Worshipping Faction",
    }

    def _render_idol_tooltip(self, screen):
        idol = self.hovered_idol
        idol_type = idol.type
        owner_id = idol.owner_spirit
        owner_name = self.spirits.get(owner_id, {}).get("name", owner_id[:6]) if owner_id else "Unknown"
        vp_text = self._IDOL_VP_TEXT.get(idol_type, "")
        tooltip_text = f"{idol_type.value.title()} Idol\nPlaced by: {owner_name}\n{vp_text}"
        mx, my = pygame.mouse.get_pos()
        draw_multiline_tooltip(
            screen, self.small_font, tooltip_text,
            anchor_x=mx,
            anchor_y=my,
        )

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
            screen.blit(title_surf, (
                self.guidance_title_rect.centerx - title_surf.get_width() // 2,
                self.guidance_title_rect.y,
            ))

        # Draw "Idol placement" title
        if self.idol_title_rect and self.idol_buttons:
            title_surf = self.font.render("Idol placement", True, (200, 200, 220))
            screen.blit(title_surf, (
                self.idol_title_rect.centerx - title_surf.get_width() // 2,
                self.idol_title_rect.y,
            ))

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

        # Tooltips (drawn last so they appear on top)
        for btn in self.faction_buttons:
            btn.draw_tooltip(screen, self.small_font)
        for btn in self.idol_buttons:
            btn.draw_tooltip(screen, self.small_font)

        # Title tooltips (drawn below title)
        if self.guidance_title_hovered and self.guidance_title_rect:
            draw_multiline_tooltip(
                screen, self.small_font, self._GUIDANCE_TITLE_TOOLTIP,
                anchor_x=self.guidance_title_rect.centerx,
                anchor_y=self.guidance_title_rect.bottom,
                below=True,
            )
        if self.idol_title_hovered and self.idol_title_rect:
            draw_multiline_tooltip(
                screen, self.small_font, self._IDOL_TITLE_TOOLTIP,
                anchor_x=self.idol_title_rect.centerx,
                anchor_y=self.idol_title_rect.bottom,
                below=True,
            )

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
            total_w = len(self.agenda_hand) * 120 - 10
            start_x = SCREEN_WIDTH // 2 - total_w // 2
            modifiers = self._get_current_faction_modifiers()
            self.ui_renderer.draw_card_hand(
                screen, self.agenda_hand,
                self.selected_agenda_index,
                start_x, SCREEN_HEIGHT - 210,
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
        screen.blit(title, (20, 100))

        hand = []
        for card_name in self.change_cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        start_x = 20
        start_y = 125
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            card_images=agenda_card_images,
        )

    def _render_ejection_ui(self, screen):
        faction_name = FACTION_DISPLAY_NAMES.get(self.ejection_faction, self.ejection_faction)
        title = self.font.render(f"As the last remnants of your presence leave the {faction_name} faction, you nudge their future. Choose an Agenda card to add to {faction_name}'s deck:", True, (200, 200, 220))
        screen.blit(title, (20, SCREEN_HEIGHT // 2 - 80))

        # Highlight selected button
        for btn in self.action_buttons:
            if self.selected_ejection_type and btn.text.lower() == self.selected_ejection_type:
                btn.color = (120, 80, 180)
            else:
                btn.color = (80, 60, 130)
            btn.draw(screen, self.font)

        # Selection feedback
        if self.selected_ejection_type:
            sel_text = self.font.render(
                f"Selected: {self.selected_ejection_type.title()}", True, (200, 200, 220))
            screen.blit(sel_text, (20, SCREEN_HEIGHT - 110))

        # Confirm button
        if self.submit_button:
            self.submit_button.enabled = self.selected_ejection_type is not None
            self.submit_button.draw(screen, self.font)

    def _render_spoils_ui(self, screen):
        if not self.spoils_cards:
            return
        opponent_name = FACTION_DISPLAY_NAMES.get(self.spoils_opponent, self.spoils_opponent)
        title_text = f"Spoils of War vs {opponent_name} - Choose an agenda:" if opponent_name else "Spoils of War - Choose an agenda:"
        title = self.font.render(title_text, True, (255, 200, 100))
        screen.blit(title, (20, 100))

        modifiers = self._get_current_faction_modifiers()
        hand = [{"agenda_type": card} for card in self.spoils_cards]
        start_x = 20
        start_y = 125
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            modifiers=modifiers,
            card_images=agenda_card_images,
            is_spoils=True,
        )

    def _render_spoils_change_ui(self, screen):
        if not self.spoils_change_cards:
            return
        opponent_name = FACTION_DISPLAY_NAMES.get(self.spoils_opponent, self.spoils_opponent)
        title_text = f"Spoils of War vs {opponent_name} - Choose a Change modifier:" if opponent_name else "Spoils of War - Choose a Change modifier:"
        title = self.font.render(title_text, True, (255, 200, 100))
        screen.blit(title, (20, 100))

        hand = []
        for card_name in self.spoils_change_cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        start_x = 20
        start_y = 125
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            card_images=agenda_card_images,
        )
