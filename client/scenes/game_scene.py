"""Primary gameplay scene: hex map, UI, phases."""

import pygame
from shared.constants import (
    MessageType, Phase, AgendaType, IdolType,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_DISPLAY_NAMES, FACTION_COLORS,
)
from shared.models import GameStateSnapshot, HexCoord, Idol, WarState
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import UIRenderer, Button
from client.renderer.animation import AnimationManager
from client.input_handler import InputHandler


class GameScene:
    def __init__(self, app):
        self.app = app
        self.hex_renderer = HexRenderer()
        self.ui_renderer = UIRenderer()
        self.animation = AnimationManager()
        self.input_handler = InputHandler()

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

        # Phase-specific state
        self.phase_options: dict = {}
        self.selected_faction: str | None = None
        self.selected_hex: tuple[int, int] | None = None
        self.selected_idol_type: str | None = None
        self.vagrant_action: str | None = None  # "possess" or "place_idol"

        # Agenda state
        self.agenda_hand: list[dict] = []
        self.selected_agenda_index: int = -1

        # Change/ejection state
        self.change_cards: list[str] = []
        self.ejection_pending = False
        self.ejection_faction = ""

        # UI buttons
        self.action_buttons: list[Button] = []
        self.submit_button: Button | None = None
        self.faction_buttons: list[Button] = []
        self.idol_buttons: list[Button] = []

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

        if event.type == pygame.MOUSEMOTION:
            for btn in self.action_buttons + self.faction_buttons + self.idol_buttons:
                btn.update(event.pos)
            if self.submit_button:
                self.submit_button.update(event.pos)

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

            # Hex click
            hex_coord = self.hex_renderer.get_hex_at_screen(
                event.pos[0], event.pos[1], self.input_handler,
                SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
            )
            if hex_coord:
                self._handle_hex_click(hex_coord)

    def _handle_action_button(self, text: str):
        if text == "Possess":
            self.vagrant_action = "possess"
            self._build_faction_buttons()
        elif text == "Place Idol":
            self.vagrant_action = "place_idol"
            self._build_idol_buttons()

    def _handle_faction_select(self, faction_id: str):
        self.selected_faction = faction_id

    def _handle_idol_select(self, idol_type: str):
        self.selected_idol_type = idol_type

    def _handle_hex_click(self, hex_coord: tuple[int, int]):
        if self.vagrant_action == "place_idol" and self.hex_ownership.get(hex_coord) is None:
            self.selected_hex = hex_coord
        else:
            # Click to view faction info
            owner = self.hex_ownership.get(hex_coord)
            if owner:
                self.selected_faction = owner

    def _submit_action(self):
        if self.phase == Phase.VAGRANT_PHASE.value:
            if self.vagrant_action == "possess" and self.selected_faction:
                self.app.network.send(MessageType.SUBMIT_VAGRANT_ACTION, {
                    "action_type": "possess",
                    "target": self.selected_faction,
                })
                self._clear_selection()
            elif (self.vagrant_action == "place_idol" and
                  self.selected_hex and self.selected_idol_type):
                self.app.network.send(MessageType.SUBMIT_VAGRANT_ACTION, {
                    "action_type": "place_idol",
                    "idol_type": self.selected_idol_type,
                    "q": self.selected_hex[0],
                    "r": self.selected_hex[1],
                })
                self._clear_selection()
        elif self.phase == Phase.AGENDA_PHASE.value:
            if self.selected_agenda_index >= 0:
                self.app.network.send(MessageType.SUBMIT_AGENDA_CHOICE, {
                    "agenda_index": self.selected_agenda_index,
                })
                self._clear_selection()

    def _submit_change_choice(self, index: int):
        self.app.network.send(MessageType.SUBMIT_CHANGE_CHOICE, {
            "card_index": index,
        })
        self.change_cards = []

    def _submit_ejection_choice(self, agenda_type: str):
        self.app.network.send(MessageType.SUBMIT_EJECTION_AGENDA, {
            "agenda_type": agenda_type,
        })
        self.ejection_pending = False

    def _clear_selection(self):
        self.vagrant_action = None
        self.selected_faction = None
        self.selected_hex = None
        self.selected_idol_type = None
        self.selected_agenda_index = -1
        self.action_buttons = []
        self.faction_buttons = []
        self.idol_buttons = []
        self.submit_button = None

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
            if "state" in payload:
                self._update_state_from_snapshot(payload["state"])
            events = payload.get("events", [])
            for event in events:
                self._log_event(event)

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
            # Build possess/idol buttons
            y = SCREEN_HEIGHT - 200
            self.action_buttons = [
                Button(pygame.Rect(20, y, 120, 36), "Possess", (60, 80, 130)),
                Button(pygame.Rect(150, y, 120, 36), "Place Idol", (60, 80, 130)),
            ]
            self.submit_button = Button(
                pygame.Rect(SCREEN_WIDTH - 150, SCREEN_HEIGHT - 60, 130, 40),
                "Confirm", (60, 130, 60)
            )

        elif self.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
            hand = self.phase_options.get("hand", [])
            self.agenda_hand = hand
            self.selected_agenda_index = -1
            self.submit_button = Button(
                pygame.Rect(SCREEN_WIDTH - 150, SCREEN_HEIGHT - 60, 130, 40),
                "Confirm", (60, 130, 60)
            )

        elif self.phase == "change_choice":
            self.change_cards = payload_cards if (payload_cards := self.phase_options.get("cards")) else []

        elif self.phase == "ejection_choice":
            self.ejection_pending = True
            self.ejection_faction = self.phase_options.get("faction", "")
            # Build ejection buttons
            y = SCREEN_HEIGHT - 200
            self.action_buttons = []
            for i, at in enumerate(AgendaType):
                btn = Button(
                    pygame.Rect(20 + i * 110, y, 100, 36),
                    at.value.title(), (80, 60, 130)
                )
                self.action_buttons.append(btn)

    def _build_faction_buttons(self):
        available = self.phase_options.get("available_factions", [])
        self.faction_buttons = []
        y = SCREEN_HEIGHT - 160
        for i, fid in enumerate(available):
            color = FACTION_COLORS.get(fid, (100, 100, 100))
            btn = Button(
                pygame.Rect(20 + i * 120, y, 110, 32),
                FACTION_DISPLAY_NAMES.get(fid, fid),
                color=tuple(max(c // 2, 30) for c in color),
                text_color=(255, 255, 255),
            )
            self.faction_buttons.append(btn)

    def _build_idol_buttons(self):
        self.idol_buttons = []
        y = SCREEN_HEIGHT - 160
        for i, it in enumerate(IdolType):
            colors = {
                IdolType.BATTLE: (130, 50, 50),
                IdolType.AFFLUENCE: (130, 120, 30),
                IdolType.SPREAD: (50, 120, 50),
            }
            btn = Button(
                pygame.Rect(20 + i * 120, y, 110, 32),
                it.value.title(), colors.get(it, (80, 80, 80))
            )
            self.idol_buttons.append(btn)

    def _get_card_rects(self) -> list[pygame.Rect]:
        """Calculate card rects for the agenda hand."""
        rects = []
        card_w, card_h = 100, 140
        spacing = 10
        total_w = len(self.agenda_hand) * (card_w + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = SCREEN_HEIGHT - 180
        for i in range(len(self.agenda_hand)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_change_card_rects(self) -> list[pygame.Rect]:
        rects = []
        card_w, card_h = 120, 60
        spacing = 10
        total_w = len(self.change_cards) * (card_w + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = SCREEN_HEIGHT // 2 - card_h // 2
        for i in range(len(self.change_cards)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _log_event(self, event: dict):
        etype = event.get("type", "")
        if etype == "idol_placed":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            self.event_log.append(f"{name} placed {event['idol_type']} idol")
        elif etype == "possessed":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{name} possessed {fname}")
        elif etype == "possess_contested":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"Contested possession of {fname}!")
        elif etype == "agenda_chosen":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} plays {event['agenda']}")
        elif etype == "agenda_random":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} randomly plays {event['agenda']}")
        elif etype == "steal":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} stole {event.get('gold_gained', 0)} gold")
        elif etype == "bond":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} improved relations")
        elif etype == "trade":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} traded for {event.get('gold_gained', 0)} gold")
        elif etype == "expand":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} expanded territory")
        elif etype == "expand_failed":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} couldn't expand, gained gold")
        elif etype == "change":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{fname} upgraded {event.get('modifier', '?')}")
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
                self.event_log.append(
                    f"{wname} won war! (Roll: {event.get('roll_a', '?')}+{event.get('power_a', '?')} vs "
                    f"{event.get('roll_b', '?')}+{event.get('power_b', '?')})")
            else:
                self.event_log.append("War ended in a tie!")
        elif etype == "vp_scored":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            self.event_log.append(f"{name} scored {event.get('vp_gained', 0)} VP (total: {event.get('total_vp', 0)})")
        elif etype == "ejected":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{name} ejected from {fname}")
        elif etype == "presence_gained":
            name = self.spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            self.event_log.append(f"{name} gained presence in {fname}")
        elif etype == "turn_start":
            self.event_log.append(f"--- Turn {event.get('turn', '?')} ---")
        elif etype == "game_over":
            winners = event.get("winners", [])
            names = [self.spirits.get(w, {}).get("name", w[:6]) for w in winners]
            self.event_log.append(f"GAME OVER! Winner(s): {', '.join(names)}")

    def update(self, dt):
        self.animation.update(dt)

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
                })())

        # Parse wars for rendering
        render_wars = []
        for w in self.wars:
            if isinstance(w, dict) and w.get("battleground"):
                bg = w["battleground"]
                render_wars.append(type('War', (), {
                    'battleground': (
                        type('H', (), {'q': bg[0]['q'], 'r': bg[0]['r']})(),
                        type('H', (), {'q': bg[1]['q'], 'r': bg[1]['r']})(),
                    )
                })())

        # Draw hex grid
        highlight = None
        if self.vagrant_action == "place_idol":
            highlight = {h for h, o in self.hex_ownership.items() if o is None}

        self.hex_renderer.draw_hex_grid(
            screen, self.hex_ownership,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            idols=render_idols, wars=render_wars,
            selected_hex=self.selected_hex,
            highlight_hexes=highlight,
        )

        # Draw HUD
        self.ui_renderer.draw_hud(screen, self.phase, self.turn,
                                   self.spirits, self.app.my_spirit_id)

        # Draw faction panel (right side)
        panel_faction = self.selected_faction
        if not panel_faction:
            # Default to possessed faction
            my_spirit = self.spirits.get(self.app.my_spirit_id, {})
            panel_faction = my_spirit.get("possessed_faction")
        if panel_faction and panel_faction in self.factions:
            self.ui_renderer.draw_faction_panel(
                screen, self.factions[panel_faction],
                SCREEN_WIDTH - 240, 50, 230
            )

        # Draw event log (bottom right)
        self.ui_renderer.draw_event_log(
            screen, self.event_log,
            SCREEN_WIDTH - 300, SCREEN_HEIGHT - 200, 290, 190
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

    def _render_vagrant_ui(self, screen):
        # Action buttons
        for btn in self.action_buttons:
            btn.draw(screen, self.font)
        for btn in self.faction_buttons:
            btn.draw(screen, self.font)
        for btn in self.idol_buttons:
            btn.draw(screen, self.font)

        # Selection info
        y = SCREEN_HEIGHT - 110
        if self.vagrant_action == "possess" and self.selected_faction:
            fname = FACTION_DISPLAY_NAMES.get(self.selected_faction, self.selected_faction)
            text = self.font.render(f"Possess: {fname}", True, (200, 200, 220))
            screen.blit(text, (20, y))
        elif self.vagrant_action == "place_idol":
            parts = []
            if self.selected_idol_type:
                parts.append(f"Idol: {self.selected_idol_type}")
            if self.selected_hex:
                parts.append(f"Hex: ({self.selected_hex[0]}, {self.selected_hex[1]})")
            if parts:
                text = self.font.render(" | ".join(parts), True, (200, 200, 220))
                screen.blit(text, (20, y))
            else:
                text = self.small_font.render("Select idol type, then click a neutral hex", True, (140, 140, 160))
                screen.blit(text, (20, y))

        # Submit button
        if self.submit_button:
            can_submit = False
            if self.vagrant_action == "possess" and self.selected_faction:
                can_submit = True
            elif (self.vagrant_action == "place_idol" and
                  self.selected_hex and self.selected_idol_type):
                can_submit = True
            self.submit_button.enabled = can_submit
            self.submit_button.draw(screen, self.font)

    def _render_agenda_ui(self, screen):
        if self.agenda_hand:
            total_w = len(self.agenda_hand) * 110 - 10
            start_x = SCREEN_WIDTH // 2 - total_w // 2
            self.ui_renderer.draw_card_hand(
                screen, self.agenda_hand,
                self.selected_agenda_index,
                start_x, SCREEN_HEIGHT - 180,
            )

        if self.submit_button:
            self.submit_button.enabled = self.selected_agenda_index >= 0
            self.submit_button.draw(screen, self.font)

    def _render_change_ui(self, screen):
        if not self.change_cards:
            return
        # Draw change card options
        title = self.font.render("Choose a Change modifier:", True, (200, 200, 220))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, SCREEN_HEIGHT // 2 - 60))

        rects = self._get_change_card_rects()
        for i, (card, rect) in enumerate(zip(self.change_cards, rects)):
            pygame.draw.rect(screen, (50, 50, 70), rect, border_radius=6)
            pygame.draw.rect(screen, (120, 120, 160), rect, 2, border_radius=6)
            text = self.font.render(card.title(), True, (220, 220, 240))
            screen.blit(text, (rect.centerx - text.get_width() // 2,
                               rect.centery - text.get_height() // 2))

    def _render_ejection_ui(self, screen):
        title = self.font.render("Choose an Agenda card to add to the faction's deck:", True, (200, 200, 220))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, SCREEN_HEIGHT // 2 - 80))

        for btn in self.action_buttons:
            btn.draw(screen, self.font)

        # Handle click on ejection buttons
        # (clicks handled in handle_event via action_buttons)
