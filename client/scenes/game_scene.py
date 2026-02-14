"""Primary gameplay scene: hex map, UI, phases."""

import pygame
from shared.constants import (
    MessageType, Phase, AgendaType, IdolType, MAP_SIDE_LENGTH,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES, FACTION_DISPLAY_NAMES, FACTION_COLORS,
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP,
)
from shared.models import GameStateSnapshot, HexCoord, Idol, WarState
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import UIRenderer, Button, draw_multiline_tooltip
from client.renderer.animation import AnimationManager, AgendaAnimation, AgendaSlideAnimation, TextAnimation, ArrowAnimation
from client.renderer.assets import load_assets, agenda_images, agenda_card_images
from client.input_handler import InputHandler
from shared.hex_utils import axial_to_pixel, hex_neighbors

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

# Title positions
_TITLE_Y = 93
_BTN_START_Y = 120


class GameScene:
    def __init__(self, app):
        self.app = app
        self.hex_renderer = HexRenderer()
        self.ui_renderer = UIRenderer()
        self.animation = AnimationManager()
        self.input_handler = InputHandler()
        load_assets()

        self.game_state: dict = {}
        self.phase = ""
        self.turn = 0
        self.factions: dict = {}
        self.spirits: dict = {}
        self.wars: list = []
        self.all_idols: list = []
        self.hex_ownership: dict[tuple[int, int], str | None] = {}
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

        # Animation queue: batches of agenda events processed sequentially
        self._animation_queue: list[list[dict]] = []
        self._animation_fading: bool = False

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
                card_rects = self._get_card_rects()
                for i, rect in enumerate(card_rects):
                    if rect.collidepoint(event.pos):
                        self.selected_agenda_index = i
                        return

            # Check change card clicks
            if self.change_cards:
                card_rects = self._get_change_card_rects()
                for i, rect in enumerate(card_rects):
                    if rect.collidepoint(event.pos):
                        self._submit_change_choice(i)
                        return

            # Check spoils card clicks
            if self.spoils_cards:
                card_rects = self._get_spoils_card_rects()
                for i, rect in enumerate(card_rects):
                    if rect.collidepoint(event.pos):
                        self._submit_spoils_choice(i)
                        return

            # Check spoils change card clicks
            if self.spoils_change_cards:
                card_rects = self._get_spoils_change_card_rects()
                for i, rect in enumerate(card_rects):
                    if rect.collidepoint(event.pos):
                        self._submit_spoils_change_choice(i)
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
            # Click to view faction info (sets panel, not guide target)
            owner = self.hex_ownership.get(hex_coord)
            if owner:
                self.panel_faction = owner

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

    def _submit_change_choice(self, index: int):
        self.app.network.send(MessageType.SUBMIT_CHANGE_CHOICE, {
            "card_index": index,
        })
        self.change_cards = []

    def _submit_spoils_choice(self, index: int):
        self.app.network.send(MessageType.SUBMIT_SPOILS_CHOICE, {
            "card_index": index,
        })
        self.spoils_cards = []

    def _submit_spoils_change_choice(self, index: int):
        self.app.network.send(MessageType.SUBMIT_SPOILS_CHANGE_CHOICE, {
            "card_index": index,
        })
        self.spoils_change_cards = []

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
            self.event_log.append(f"Game started! Turn {self.turn}")

        elif msg_type == MessageType.PHASE_START:
            self.phase = payload.get("phase", self.phase)
            self.turn = payload.get("turn", self.turn)
            self.phase_options = payload.get("options", {})
            self._setup_phase_ui()

        elif msg_type == MessageType.WAITING_FOR:
            self.waiting_for = payload.get("players_remaining", [])

        elif msg_type == MessageType.PHASE_RESULT:
            active_sub_phase = self.phase if self.phase in (
                "change_choice", "spoils_choice", "spoils_change_choice") else None
            if "state" in payload:
                self._update_state_from_snapshot(payload["state"])
            # Preserve sub-phases while this player still has cards to choose
            if active_sub_phase == "change_choice" and self.change_cards:
                self.phase = active_sub_phase
            elif active_sub_phase == "spoils_choice" and self.spoils_cards:
                self.phase = active_sub_phase
            elif active_sub_phase == "spoils_change_choice" and self.spoils_change_cards:
                self.phase = active_sub_phase
            events = payload.get("events", [])
            # Log all events in original order
            for event in events:
                self._log_event(event)
            # Collect agenda events for animation queuing
            _ANIM_ORDER = {
                "trade": 0, "bond": 1, "steal": 2,
                "expand": 3, "expand_failed": 3, "expand_spoils": 3,
                "change": 4, "change_draw": 4,
            }
            agenda_events = [e for e in events if e.get("type", "") in _ANIM_ORDER]
            if agenda_events:
                self._animation_queue.append(agenda_events)
                self._try_process_next_animation_batch()
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

        elif self.phase == "spoils_change_choice":
            self.spoils_change_cards = payload_cards if (payload_cards := self.phase_options.get("cards")) else []

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
        presence_id = fdata.get("presence_spirit") if isinstance(fdata, dict) else None
        lines = []
        if is_blocked:
            lines.append("This Faction Worships you;")
            lines.append("you cannot Guide them.")
        elif presence_id:
            name = self.spirits.get(presence_id, {}).get("name", presence_id[:6])
            lines.append(f"Worshipped by: {name}")
            my_id = self.app.my_spirit_id
            my_idols = self._count_spirit_idols_in_faction(my_id, faction_id)
            their_idols = self._count_spirit_idols_in_faction(presence_id, faction_id)
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
        blocked = self.phase_options.get("presence_blocked", [])
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

    def _get_card_rects(self) -> list[pygame.Rect]:
        """Calculate card rects for the agenda hand."""
        rects = []
        card_w, card_h = 110, 170
        spacing = 10
        total_w = len(self.agenda_hand) * (card_w + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = SCREEN_HEIGHT - 210
        for i in range(len(self.agenda_hand)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_change_card_rects(self) -> list[pygame.Rect]:
        rects = []
        card_w, card_h = 110, 170
        spacing = 10
        start_x = 20
        y = 125
        for i in range(len(self.change_cards)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_spoils_card_rects(self) -> list[pygame.Rect]:
        rects = []
        card_w, card_h = 110, 170
        spacing = 10
        start_x = 20
        y = 125
        for i in range(len(self.spoils_cards)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_spoils_change_card_rects(self) -> list[pygame.Rect]:
        rects = []
        card_w, card_h = 110, 170
        spacing = 10
        start_x = 20
        y = 125
        for i in range(len(self.spoils_change_cards)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_faction_centroid(self, faction_id: str) -> tuple[float | None, float | None]:
        """Get the world-coordinate centroid of a faction's territory."""
        owned = [(q, r) for (q, r), owner in self.hex_ownership.items()
                 if owner == faction_id]
        if not owned:
            return None, None
        avg_q = sum(q for q, r in owned) / len(owned)
        avg_r = sum(r for q, r in owned) / len(owned)
        # Snap to nearest owned hex
        best = min(owned, key=lambda h: (h[0] - avg_q) ** 2 + (h[1] - avg_r) ** 2)
        return axial_to_pixel(best[0], best[1], HEX_SIZE)

    def _get_gold_display_pos(self, faction_id: str) -> tuple[int, int]:
        """Get screen position below the faction's gold text in the overview strip."""
        try:
            idx = FACTION_NAMES.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 97)
        cell_w = SCREEN_WIDTH // len(FACTION_NAMES)
        cx = idx * cell_w
        abbr = FACTION_DISPLAY_NAMES.get(faction_id, faction_id)
        abbr_w = self.small_font.size(abbr)[0]
        gold_x = cx + 6 + abbr_w + 6
        return (gold_x, 97)  # strip_y(42) + strip_h(55)

    def _get_agenda_label_pos(self, faction_id: str, img_width: int, row: int = 0) -> tuple[int, int]:
        """Get the target screen position for an agenda slide animation (right-aligned in strip cell).

        row=0 is the default position; row=1+ stacks below with 24px offset per row.
        """
        try:
            idx = FACTION_NAMES.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 46)
        cell_w = SCREEN_WIDTH // len(FACTION_NAMES)
        cx = idx * cell_w
        target_x = cx + cell_w - img_width - 6  # right edge minus padding minus image width
        target_y = 42 + 4 + row * 24  # strip_y + small padding + row offset
        return target_x, target_y

    def _get_agenda_slide_start(self, faction_id: str, img_width: int, row: int = 0) -> tuple[int, int]:
        """Get the start screen position for an agenda slide animation (below strip)."""
        target_x, _ = self._get_agenda_label_pos(faction_id, img_width, row)
        start_y = 42 + 55 + 20  # strip_y + strip_h + offset below
        return target_x, start_y

    def _get_faction_strip_pos(self, faction_id: str) -> tuple[int, int]:
        """Get position below a faction's name in the overview strip for regard text."""
        try:
            idx = FACTION_NAMES.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 101)
        cell_w = SCREEN_WIDTH // len(FACTION_NAMES)
        cx = idx * cell_w
        return (cx + 6, 97 + 4)  # strip_y(42) + strip_h(55) = 97, plus padding

    def _get_border_midpoints(self, faction_a: str, faction_b: str) -> list[tuple[float, float]]:
        """Get world-space midpoints of all border edges between two factions."""
        pairs = self.hex_renderer._get_border_pairs(self.hex_ownership, faction_a, faction_b)
        midpoints = []
        for h1, h2 in pairs:
            x1, y1 = axial_to_pixel(h1[0], h1[1], HEX_SIZE)
            x2, y2 = axial_to_pixel(h2[0], h2[1], HEX_SIZE)
            midpoints.append(((x1 + x2) / 2, (y1 + y2) / 2))
        return midpoints

    def _create_effect_animations(self, event: dict, faction_id: str, delay: float):
        """Create effect animations for an agenda event."""
        etype = event.get("type", "")

        if etype in ("trade", "trade_spoils_bonus"):
            gold = event.get("gold_gained", 0)
            if gold > 0:
                gx, gy = self._get_gold_display_pos(faction_id)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{gold}g", gx, gy, (255, 220, 60),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))

        elif etype == "bond":
            regard_gain = event.get("regard_gain", 1)
            neighbors = event.get("neighbors", [])
            for nfid in neighbors:
                rx, ry = self._get_faction_strip_pos(nfid)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{regard_gain}", rx, ry, (100, 200, 255),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))

        elif etype == "steal":
            gold = event.get("gold_gained", 0)
            regard_penalty = event.get("regard_penalty", -1)
            neighbors = event.get("neighbors", [])
            # Gold text in screen space
            if gold > 0:
                gx, gy = self._get_gold_display_pos(faction_id)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{gold}g", gx, gy, (255, 220, 60),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))
            # Regard text under target faction names in overview strip
            for nfid in neighbors:
                rx, ry = self._get_faction_strip_pos(nfid)
                self.animation.add_effect_animation(TextAnimation(
                    str(regard_penalty), rx, ry, (255, 80, 80),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))

        elif etype in ("expand", "expand_spoils"):
            target_hex = event.get("hex")
            if target_hex:
                tq, tr = target_hex["q"], target_hex["r"]
                # Find adjacent owned hexes pointing into the new hex
                for nq, nr in hex_neighbors(tq, tr):
                    if self.hex_ownership.get((nq, nr)) == faction_id:
                        self.animation.add_effect_animation(ArrowAnimation(
                            (nq, nr), (tq, tr), (80, 220, 80),
                            delay=delay, duration=3.0,
                        ))

        elif etype == "expand_failed":
            gold = event.get("gold_gained", 0)
            if gold > 0:
                gx, gy = self._get_gold_display_pos(faction_id)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{gold}g", gx, gy, (255, 220, 60),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))

    def _is_animating(self) -> bool:
        """True if any animations are playing or queued."""
        return not self.animation.is_all_done() or bool(self._animation_queue)

    def _try_process_next_animation_batch(self):
        """Process the next queued animation batch when current animations are done."""
        if not self._animation_queue:
            return
        if self._animation_fading:
            # We started a fadeout; wait for it to finish
            if not self.animation.has_active_persistent_agenda_animations():
                self._animation_fading = False
                batch = self._animation_queue.pop(0)
                self._process_animation_batch(batch)
            return
        if not self.animation.is_all_done():
            return
        # All animations done — check if we need to fade old ones first
        # (only non-auto-fadeout animations need explicit fadeout)
        leftover = [a for a in self.animation.get_persistent_agenda_animations()
                    if a.auto_fadeout_after is None]
        if leftover:
            self.animation.start_agenda_fadeout()
            self._animation_fading = True
            return
        # Clear any remaining auto-fadeout animations before starting new batch
        if hasattr(self.animation, "persistent_agenda_animations"):
            for anim in self.animation.persistent_agenda_animations:
                if anim.auto_fadeout_after is not None and not anim.done:
                    anim.done = True
        # Nothing blocking, process immediately
        batch = self._animation_queue.pop(0)
        self._process_animation_batch(batch)

    def _process_animation_batch(self, agenda_events: list[dict]):
        """Create animations for a batch of agenda events."""
        _ANIM_ORDER = {
            "trade": 0, "bond": 1, "steal": 2,
            "expand": 3, "expand_failed": 3, "expand_spoils": 3,
            "change": 4, "change_draw": 4,
        }
        regular_events = [e for e in agenda_events if not e.get("is_spoils")]
        spoils_events = [e for e in agenda_events if e.get("is_spoils")]

        # --- Regular events ---
        regular_events.sort(key=lambda e: (
            0 if e.get("is_setup") else 1,
            _ANIM_ORDER.get(e["type"], 99),
        ))
        agenda_anim_index = 0
        setup_count = sum(1 for e in regular_events if e.get("is_setup"))
        for event in regular_events:
            etype = event["type"]
            if etype in ("change", "change_draw"):
                modifier = event.get("modifier", "")
                img_key = f"change_{modifier}" if f"change_{modifier}" in agenda_images else "change"
            elif etype == "expand_failed":
                img_key = "expand_failed"
            else:
                img_key = {"steal": "steal", "bond": "bond", "trade": "trade",
                           "expand": "expand", "expand_spoils": "expand"}[etype]
            img = agenda_images.get(img_key)
            faction_id = event.get("faction")
            if not img:
                print(f"[anim] No image for '{img_key}' (loaded: {list(agenda_images.keys())})")
            elif not faction_id:
                print(f"[anim] No faction_id in {etype} event")
            else:
                delay = agenda_anim_index * 1.0
                auto_fadeout = None
                if event.get("is_setup"):
                    remaining = setup_count - agenda_anim_index - 1
                    auto_fadeout = remaining * 1.0 + 2.0
                img_w = img.get_width()
                target_x, target_y = self._get_agenda_label_pos(faction_id, img_w)
                start_x, start_y = self._get_agenda_slide_start(faction_id, img_w)
                anim = AgendaSlideAnimation(
                    img, faction_id,
                    target_x, target_y,
                    start_x, start_y,
                    delay=delay,
                    auto_fadeout_after=auto_fadeout,
                )
                self.animation.add_persistent_agenda_animation(anim)
                self._create_effect_animations(event, faction_id, delay)
                agenda_anim_index += 1

        # --- Spoils events (stack below regular agenda icons) ---
        spoils_events.sort(key=lambda e: _ANIM_ORDER.get(e["type"], 99))
        spoils_batch_counts: dict[str, int] = {}
        spoils_anim_index = 0
        for event in spoils_events:
            etype = event["type"]
            if etype in ("change", "change_draw"):
                modifier = event.get("modifier", "")
                img_key = f"change_{modifier}" if f"change_{modifier}" in agenda_images else "change"
            elif etype == "expand_failed":
                img_key = "expand_failed"
            else:
                img_key = {"steal": "steal", "bond": "bond", "trade": "trade",
                           "expand": "expand", "expand_spoils": "expand"}[etype]
            img = agenda_images.get(img_key)
            faction_id = event.get("faction")
            if not img:
                print(f"[anim] No image for '{img_key}' (loaded: {list(agenda_images.keys())})")
            elif not faction_id:
                print(f"[anim] No faction_id in {etype} event")
            else:
                delay = spoils_anim_index * 1.0
                existing_spoils = self.animation.get_spoils_count_for_faction(faction_id)
                batch_local = spoils_batch_counts.get(faction_id, 0)
                row = 1 + existing_spoils + batch_local
                spoils_batch_counts[faction_id] = batch_local + 1
                img_w = img.get_width()
                target_x, target_y = self._get_agenda_label_pos(faction_id, img_w, row)
                start_x, start_y = self._get_agenda_slide_start(faction_id, img_w, row)
                anim = AgendaSlideAnimation(
                    img, faction_id,
                    target_x, target_y,
                    start_x, start_y,
                    delay=delay,
                    is_spoils=True,
                )
                self.animation.add_persistent_agenda_animation(anim)
                self._create_effect_animations(event, faction_id, delay)
                spoils_anim_index += 1

        total_anims = agenda_anim_index + spoils_anim_index
        if total_anims > 0:
            print(f"[anim] Created {total_anims} agenda animations ({agenda_anim_index} regular, {spoils_anim_index} spoils)")

    def _render_persistent_agenda_animations(self, screen: pygame.Surface):
        """Draw active persistent agenda slide animations in screen space."""
        for anim in self.animation.get_persistent_agenda_animations():
            if not anim.active:
                continue
            img = anim.image.copy()
            img.set_alpha(anim.alpha)
            screen.blit(img, (int(anim.x), int(anim.y)))

    def _render_effect_animations(self, screen: pygame.Surface, screen_space_only: bool):
        """Draw active effect animations (text and arrows)."""
        for anim in self.animation.get_active_effect_animations():
            if not anim.active:
                continue
            if screen_space_only and not anim.screen_space:
                continue
            if not screen_space_only and anim.screen_space:
                continue

            if isinstance(anim, TextAnimation):
                alpha = anim.alpha
                if alpha <= 0:
                    continue
                text_surf = self.small_font.render(anim.text, True, anim.color)
                text_surf.set_alpha(alpha)
                if anim.screen_space:
                    sx, sy = anim.x, anim.y + anim.y_offset
                else:
                    sx, sy = self.input_handler.world_to_screen(
                        anim.x, anim.y + anim.y_offset,
                        SCREEN_WIDTH, SCREEN_HEIGHT,
                    )
                screen.blit(text_surf, (int(sx), int(sy)))

            elif isinstance(anim, ArrowAnimation):
                alpha = anim.alpha
                if alpha <= 0:
                    continue
                color = tuple(int(c * alpha / 255) for c in anim.color)
                self.hex_renderer._draw_hex_arrow(
                    screen, anim.from_hex, anim.to_hex, color,
                    self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
                    width=3, head_size=8, unidirectional=True,
                )

    def _log_event(self, event: dict):
        etype = event.get("type", "")
        if etype == "idol_placed":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            self.event_log.append(f"{name} placed {event['idol_type']} idol")
        elif etype == "guided":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{name} is guiding {fname}")
        elif etype == "guide_contested":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            spirit_ids = event.get("spirits", [])
            names = [self.spirits.get(sid, {}).get("name", sid[:6]) for sid in spirit_ids]
            self.event_log.append(f"Contested guidance of {fname}! ({', '.join(names)})")
            # Clear preview if local player was in the contested list
            if self.app.my_spirit_id in spirit_ids:
                self.preview_guidance = None
        elif etype == "agenda_chosen":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} plays {event['agenda']}")
            self.faction_agendas_this_turn[event["faction"]] = event["agenda"]
        elif etype == "agenda_random":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} randomly plays {event['agenda']}")
            self.faction_agendas_this_turn[event["faction"]] = event["agenda"]
        elif etype == "steal":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            prefix = "Spoils: " if event.get("is_spoils") else ""
            self.event_log.append(f"{prefix}{fname} stole {event.get('gold_gained', 0)} gold")
        elif etype == "bond":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            prefix = "Spoils: " if event.get("is_spoils") else ""
            self.event_log.append(f"{prefix}{fname} improved relations")
        elif etype == "trade":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            prefix = "Spoils: " if event.get("is_spoils") else ""
            self.event_log.append(f"{prefix}{fname} traded for {event.get('gold_gained', 0)} gold")
        elif etype == "trade_spoils_bonus":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} gained {event.get('gold_gained', 1)} gold from Spoils Trade")
        elif etype == "expand":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} expanded territory")
        elif etype == "expand_failed":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} couldn't expand, gained gold")
        elif etype == "change":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            prefix = "Spoils: " if event.get("is_spoils") else ""
            self.event_log.append(f"{prefix}{fname} upgraded {event.get('modifier', '?')}")
        elif etype == "change_draw":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            cards = event.get("cards", [])
            self.event_log.append(f"{fname} draws Change: {', '.join(cards)}")
        elif etype == "war_erupted":
            fa = FACTION_DISPLAY_NAMES.get(event["faction_a"], event["faction_a"])
            fb = FACTION_DISPLAY_NAMES.get(event["faction_b"], event["faction_b"])
            self.event_log.append(f"War erupted between {fa} and {fb}!")
        elif etype == "war_ripened":
            fa = FACTION_DISPLAY_NAMES.get(event["faction_a"], event["faction_a"])
            fb = FACTION_DISPLAY_NAMES.get(event["faction_b"], event["faction_b"])
            self.event_log.append(f"War between {fa} and {fb} is ripe!")
        elif etype == "war_resolved":
            winner = event.get("winner")
            if winner:
                wname = FACTION_DISPLAY_NAMES.get(winner, winner)
                loser = event.get("loser", "?")
                lname = FACTION_DISPLAY_NAMES.get(loser, loser)
                self.event_log.append(
                    f"{wname} won war against {lname}! (Roll: {event.get('roll_a', '?')}+{event.get('power_a', '?')} vs "
                    f"{event.get('roll_b', '?')}+{event.get('power_b', '?')})")
            else:
                self.event_log.append("War ended in a tie!")
        elif etype == "spoils_drawn":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"Spoils: {fname} drew {event.get('agenda', '?')}")
        elif etype == "spoils_choice":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            cards = event.get("cards", [])
            self.event_log.append(f"Spoils: {fname} choosing from {', '.join(cards)}")
        elif etype == "expand_spoils":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"Spoils: {fname} conquered enemy territory")
        elif etype == "vp_scored":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            self.event_log.append(f"{name} scored {event.get('vp_gained', 0)} VP (total: {event.get('total_vp', 0)})")
            b_idols = event.get("battle_idols", 0)
            b_wars = event.get("wars_won", 0)
            if b_idols:
                b_vp = b_idols * BATTLE_IDOL_VP * b_wars
                self.event_log.append(f"  Battle: {b_idols} idol x {b_wars} wars = {b_vp:.1f}")
            a_idols = event.get("affluence_idols", 0)
            a_gold = event.get("gold_gained", 0)
            if a_idols:
                a_vp = a_idols * AFFLUENCE_IDOL_VP * a_gold
                self.event_log.append(f"  Affluence: {a_idols} idol x {a_gold} gold = {a_vp:.1f}")
            s_idols = event.get("spread_idols", 0)
            s_terr = event.get("territories_gained", 0)
            if s_idols:
                s_vp = s_idols * SPREAD_IDOL_VP * s_terr
                self.event_log.append(f"  Spread: {s_idols} idol x {s_terr} terr = {s_vp:.1f}")
        elif etype == "ejected":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{name} ejected from {fname}")
        elif etype == "presence_gained":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} now Worships {name}")
        elif etype == "presence_replaced":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            old_name = self.spirits.get(event.get("old_spirit", ""), {}).get("name", event.get("old_spirit", "?")[:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} now Worships {name} (was {old_name})")
        elif etype == "faction_eliminated":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} has been ELIMINATED!")
        elif etype == "war_ended":
            self.event_log.append(f"War ended ({event.get('reason', 'unknown')})")
        elif etype == "setup_start":
            self.event_log.append("--- Setup ---")
        elif etype == "turn_start":
            self.event_log.append(f"--- Turn {event.get('turn', '?')} ---")
            self.faction_agendas_this_turn.clear()
            self.animation.start_agenda_fadeout()
        elif etype == "game_over":
            winners = event.get("winners", [])
            names = [self.spirits.get(w, {}).get("name", w[:6]) for w in winners]
            self.event_log.append(f"GAME OVER! Winner(s): {', '.join(names)}")

    def update(self, dt):
        self.animation.update(dt)
        self._try_process_next_animation_batch()

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

        # Parse wars for rendering
        render_wars = []
        for w in self.wars:
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

        # Draw hex grid
        highlight = None
        if self.phase == Phase.VAGRANT_PHASE.value:
            highlight = {h for h, o in self.hex_ownership.items() if o is None}

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
            screen, self.hex_ownership,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            idols=render_idols, wars=render_wars,
            selected_hex=self.selected_hex,
            highlight_hexes=highlight,
            spirit_index_map=spirit_index_map,
            preview_idol=render_preview_idol,
        )

        # Draw world-space effect animations (border text + arrows)
        self._render_effect_animations(screen, screen_space_only=False)

        # Draw HUD
        self.ui_renderer.draw_hud(screen, self.phase, self.turn,
                                   self.spirits, self.app.my_spirit_id)

        # Compute preview guidance dict
        preview_guid_dict = None
        preview_fid = self.preview_guidance or self.selected_faction
        if preview_fid:
            my_name = self.spirits.get(self.app.my_spirit_id, {}).get("name", "?")
            preview_guid_dict = {preview_fid: my_name}

        # Draw faction overview strip (with war indicators)
        animated_agenda_factions = self.animation.get_persistent_agenda_factions()
        self.ui_renderer.draw_faction_overview(
            screen, self.factions, self.faction_agendas_this_turn,
            wars=render_wars,
            spirits=self.spirits,
            preview_guidance=preview_guid_dict,
            animated_agenda_factions=animated_agenda_factions,
        )

        # Draw persistent agenda slide animations (on top of overview strip)
        self._render_persistent_agenda_animations(screen)

        # Draw screen-space effect animations (gold text overlays)
        self._render_effect_animations(screen, screen_space_only=True)

        # Draw faction panel (right side)
        pf = self.panel_faction
        if not pf:
            # Default to guided faction
            my_spirit = self.spirits.get(self.app.my_spirit_id, {})
            pf = my_spirit.get("guided_faction")
        if pf and pf in self.factions:
            self.ui_renderer.draw_faction_panel(
                screen, self.factions[pf],
                SCREEN_WIDTH - 240, 92, 230,
                spirits=self.spirits,
                preview_guidance=preview_guid_dict,
            )

        # Draw event log (bottom right)
        self.ui_renderer.draw_event_log(
            screen, self.event_log,
            SCREEN_WIDTH - 300, SCREEN_HEIGHT - 200, 290, 190,
            scroll_offset=self.event_log_scroll_offset,
        )

        # Draw waiting indicator
        if self.waiting_for:
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
            if self._is_animating():
                self.submit_button.enabled = False
                self.submit_button.tooltip = "Previous actions are resolving..."
            else:
                has_guide = bool(self.selected_faction)
                has_idol = bool(self.selected_idol_type and self.selected_hex)
                can_guide = bool(self.phase_options.get("available_factions"))
                can_place_idol = bool(self.idol_buttons) and bool(self.phase_options.get("neutral_hexes"))
                if can_guide and can_place_idol:
                    self.submit_button.enabled = has_guide and has_idol
                else:
                    self.submit_button.enabled = has_guide or has_idol
                self.submit_button.tooltip = None
            self.submit_button.draw(screen, self.font)
            self.submit_button.draw_tooltip(screen, self.small_font)

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
            if self._is_animating():
                self.submit_button.enabled = False
                self.submit_button.tooltip = "Previous actions are resolving..."
            else:
                self.submit_button.enabled = self.selected_agenda_index >= 0
                self.submit_button.tooltip = None
            self.submit_button.draw(screen, self.font)
            self.submit_button.draw_tooltip(screen, self.small_font)

    def _render_change_ui(self, screen):
        if not self.change_cards:
            return
        title = self.font.render("Choose a Change modifier:", True, (200, 200, 220))
        screen.blit(title, (20, 100))

        hand = []
        for card_name in self.change_cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        rects = self._get_change_card_rects()
        start_x = rects[0].x if rects else 20
        start_y = rects[0].y if rects else 125
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            card_images=agenda_card_images,
        )

    def _render_ejection_ui(self, screen):
        faction_name = FACTION_DISPLAY_NAMES.get(self.ejection_faction, self.ejection_faction)
        title = self.font.render(f"Choose an Agenda card to add to {faction_name}'s deck:", True, (200, 200, 220))
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
            if self._is_animating():
                self.submit_button.enabled = False
                self.submit_button.tooltip = "Previous actions are resolving..."
            else:
                self.submit_button.enabled = self.selected_ejection_type is not None
                self.submit_button.tooltip = None
            self.submit_button.draw(screen, self.font)
            self.submit_button.draw_tooltip(screen, self.small_font)

    def _render_spoils_ui(self, screen):
        if not self.spoils_cards:
            return
        title = self.font.render("Spoils of War - Choose an agenda:", True, (255, 200, 100))
        screen.blit(title, (20, 100))

        modifiers = self._get_current_faction_modifiers()
        hand = [{"agenda_type": card} for card in self.spoils_cards]
        rects = self._get_spoils_card_rects()
        start_x = rects[0].x if rects else 20
        start_y = rects[0].y if rects else 125
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
        title = self.font.render("Spoils of War - Choose a Change modifier:", True, (255, 200, 100))
        screen.blit(title, (20, 100))

        hand = []
        for card_name in self.spoils_change_cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        rects = self._get_spoils_change_card_rects()
        start_x = rects[0].x if rects else 20
        start_y = rects[0].y if rects else 125
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            card_images=agenda_card_images,
        )
