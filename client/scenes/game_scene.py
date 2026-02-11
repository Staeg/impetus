"""Primary gameplay scene: hex map, UI, phases."""

import pygame
from shared.constants import (
    MessageType, Phase, AgendaType, IdolType,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_DISPLAY_NAMES, FACTION_COLORS,
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP,
)
from shared.models import GameStateSnapshot, HexCoord, Idol, WarState
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import UIRenderer, Button
from client.renderer.animation import AnimationManager, AgendaAnimation
from client.renderer.assets import load_assets, agenda_images, agenda_card_images
from client.input_handler import InputHandler
from shared.hex_utils import axial_to_pixel


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
                "spoils_choice", "spoils_change_choice") else None
            if "state" in payload:
                self._update_state_from_snapshot(payload["state"])
            # Preserve spoils sub-phases while this player still has cards to choose
            if active_sub_phase == "spoils_choice" and self.spoils_cards:
                self.phase = active_sub_phase
            elif active_sub_phase == "spoils_change_choice" and self.spoils_change_cards:
                self.phase = active_sub_phase
            events = payload.get("events", [])
            agenda_anim_index = 0
            for event in events:
                self._log_event(event)
                # Spawn floating agenda animations for agenda resolution events
                etype = event.get("type", "")
                agenda_event_map = {
                    "steal": "steal", "bond": "bond", "trade": "trade",
                    "expand": "expand", "expand_failed": "expand",
                    "change": "change", "expand_spoils": "expand",
                }
                if etype in agenda_event_map:
                    img_key = agenda_event_map[etype]
                    img = agenda_images.get(img_key)
                    faction_id = event.get("faction")
                    if img and faction_id:
                        wx, wy = self._get_faction_centroid(faction_id)
                        if wx is not None:
                            anim = AgendaAnimation(
                                img, wx, wy,
                                delay=agenda_anim_index * 0.5,
                            )
                            self.animation.add_agenda_animation(anim)
                            agenda_anim_index += 1
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
                pygame.Rect(SCREEN_WIDTH // 2 - 65, SCREEN_HEIGHT - 60, 130, 40),
                "Confirm", (60, 130, 60)
            )

        elif self.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
            hand = self.phase_options.get("hand", [])
            self.agenda_hand = hand
            self.selected_agenda_index = -1
            self.submit_button = Button(
                pygame.Rect(20, SCREEN_HEIGHT - 60, 130, 40),
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
                pygame.Rect(20, SCREEN_HEIGHT - 60, 130, 40),
                "Confirm", (60, 130, 60)
            )

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
            btn = Button(
                pygame.Rect(10, 120 + i * 40, 130, 34),
                FACTION_DISPLAY_NAMES.get(fid, fid),
                color=tuple(max(c // 2, 30) for c in color),
                text_color=(255, 255, 255),
                tooltip="Your Presence prevents you from Guiding this Faction" if is_blocked else None,
            )
            if is_blocked:
                btn.enabled = False
            self.faction_buttons.append(btn)

    def _build_idol_buttons(self):
        self.idol_buttons = []
        for i, it in enumerate(IdolType):
            colors = {
                IdolType.BATTLE: (130, 50, 50),
                IdolType.AFFLUENCE: (130, 120, 30),
                IdolType.SPREAD: (50, 120, 50),
            }
            btn = Button(
                pygame.Rect(SCREEN_WIDTH - 380, 120 + i * 40, 130, 34),
                it.value.title(), colors.get(it, (80, 80, 80))
            )
            self.idol_buttons.append(btn)

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
        card_w, card_h = 120, 60
        spacing = 10
        total_w = len(self.change_cards) * (card_w + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = SCREEN_HEIGHT // 2 - card_h // 2
        for i in range(len(self.change_cards)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_spoils_card_rects(self) -> list[pygame.Rect]:
        rects = []
        card_w, card_h = 110, 170
        spacing = 10
        total_w = len(self.spoils_cards) * (card_w + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = SCREEN_HEIGHT // 2 - card_h // 2
        for i in range(len(self.spoils_cards)):
            rects.append(pygame.Rect(start_x + i * (card_w + spacing), y, card_w, card_h))
        return rects

    def _get_spoils_change_card_rects(self) -> list[pygame.Rect]:
        rects = []
        card_w, card_h = 120, 60
        spacing = 10
        total_w = len(self.spoils_change_cards) * (card_w + spacing) - spacing
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        y = SCREEN_HEIGHT // 2 - card_h // 2
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

    def _render_agenda_animations(self, screen: pygame.Surface):
        """Draw active agenda animations, converting world coords to screen."""
        for anim in self.animation.get_active_agenda_animations():
            if not anim.active:
                continue
            sx, sy = self.input_handler.world_to_screen(
                anim.world_x, anim.world_y + anim.y_offset,
                SCREEN_WIDTH, SCREEN_HEIGHT,
            )
            img = anim.image.copy()
            img.fill((255, 255, 255, anim.alpha), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(img, (sx - img.get_width() // 2, sy - img.get_height() // 2))

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
            self.event_log.append(f"{fname} improved relations")
        elif etype == "trade":
            fname = FACTION_DISPLAY_NAMES.get(event["faction"], event["faction"])
            prefix = "Spoils: " if event.get("is_spoils") else ""
            self.event_log.append(f"{prefix}{fname} traded for {event.get('gold_gained', 0)} gold")
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
            self.event_log.append(f"{name} gained presence in {fname}")
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

        # Draw agenda animations (above hex grid, below HUD)
        self._render_agenda_animations(screen)

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
        self.ui_renderer.draw_faction_overview(
            screen, self.factions, self.faction_agendas_this_turn,
            wars=render_wars,
            spirits=self.spirits,
            preview_guidance=preview_guid_dict,
        )

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

    def _render_vagrant_ui(self, screen):
        # Draw faction buttons (left) with selection highlight
        for btn in self.faction_buttons:
            # Highlight selected faction with white border
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
        title = self.font.render("Spoils of War - Choose an agenda:", True, (255, 200, 100))
        rects = self._get_spoils_card_rects()
        title_y = rects[0].y - 30 if rects else SCREEN_HEIGHT // 2 - 120
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, title_y))

        modifiers = self._get_current_faction_modifiers()
        hand = [{"agenda_type": card} for card in self.spoils_cards]
        total_w = len(self.spoils_cards) * 120 - 10
        start_x = SCREEN_WIDTH // 2 - total_w // 2
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, rects[0].y if rects else SCREEN_HEIGHT // 2 - 85,
            modifiers=modifiers,
            card_images=agenda_card_images,
        )

    def _render_spoils_change_ui(self, screen):
        if not self.spoils_change_cards:
            return
        title = self.font.render("Spoils of War - Choose a Change modifier:", True, (255, 200, 100))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, SCREEN_HEIGHT // 2 - 60))

        rects = self._get_spoils_change_card_rects()
        for i, (card, rect) in enumerate(zip(self.spoils_change_cards, rects)):
            pygame.draw.rect(screen, (50, 50, 70), rect, border_radius=6)
            pygame.draw.rect(screen, (120, 120, 160), rect, 2, border_radius=6)
            text = self.font.render(card.title(), True, (220, 220, 240))
            screen.blit(text, (rect.centerx - text.get_width() // 2,
                               rect.centery - text.get_height() // 2))
