"""Pre-game lobby: player list, ready state, host controls."""

import pygame
from shared.constants import MessageType, SCREEN_WIDTH, SCREEN_HEIGHT
from client.renderer.ui_renderer import Button, draw_dotted_underline
from client.renderer.popup_manager import (
    PopupManager, HoverRegion, draw_multiline_tooltip_with_regions
)

_BTN_W = 160
_BTN_H = 44
_CX = SCREEN_WIDTH // 2


class LobbyScene:
    _LOBBY_TIP_TOOLTIP = (
        "While hovering you can right-click to freeze the popup window. "
        "When popups are frozen, right-click closes only the newest one."
    )
    _LOBBY_FREEZE_TOOLTIP = (
        "Right-click closes only the newest frozen popup. Keep right-clicking "
        "to close older popups one by one."
    )
    _LOBBY_HOVER_REGIONS = [
        HoverRegion("freeze", _LOBBY_FREEZE_TOOLTIP, sub_regions=[]),
    ]

    def __init__(self, app):
        self.app = app
        self.font = pygame.font.SysFont("consolas", 16)
        self.title_font = pygame.font.SysFont("consolas", 24)
        self.small_font = pygame.font.SysFont("consolas", 14)

        # Layout constants (measured from bottom of screen)
        _BTN_ROW_Y  = SCREEN_HEIGHT - 150   # spectator toggle + ready buttons
        _START_Y    = SCREEN_HEIGHT - 98    # start game button
        _TIP_Y      = SCREEN_HEIGHT - 172   # tooltip tip line
        _VP_ROW_Y   = SCREEN_HEIGHT - 212   # VP to Win row
        _AI_ROW_Y   = SCREEN_HEIGHT - 250   # AI Players row
        # x positions for the ± spinner buttons — far enough from the centred label
        _SPIN_MINUS_X = _CX - 115   # right edge at _CX-87 (≥20 px clear of text)
        _SPIN_PLUS_X  = _CX + 87    # left  edge at _CX+87
        _SPIN_W, _SPIN_H = 28, 28

        # Ready / Unready button (non-spectators only)
        self.ready_button = Button(
            pygame.Rect(_CX + 5, _BTN_ROW_Y, _BTN_W, _BTN_H),
            "Ready", (60, 120, 60)
        )
        # Spectator toggle button (all players)
        self.spectator_button = Button(
            pygame.Rect(_CX - _BTN_W - 5, _BTN_ROW_Y, _BTN_W, _BTN_H),
            "Watch as Spectator", (60, 80, 120)
        )
        # Start Game button (host only)
        self.start_button = Button(
            pygame.Rect(_CX - 100, _START_Y, 200, _BTN_H),
            "Start Game", (60, 120, 60)
        )
        # VP adjustment buttons (host only) — centred label, ± buttons on either side
        self.vp_minus = Button(pygame.Rect(_SPIN_MINUS_X, _VP_ROW_Y, _SPIN_W, _SPIN_H), "-", (80, 80, 100))
        self.vp_plus  = Button(pygame.Rect(_SPIN_PLUS_X,  _VP_ROW_Y, _SPIN_W, _SPIN_H), "+", (80, 80, 100))
        # AI count adjustment buttons (host only)
        self.ai_minus = Button(pygame.Rect(_SPIN_MINUS_X, _AI_ROW_Y, _SPIN_W, _SPIN_H), "-", (80, 80, 100))
        self.ai_plus  = Button(pygame.Rect(_SPIN_PLUS_X,  _AI_ROW_Y, _SPIN_W, _SPIN_H), "+", (80, 80, 100))
        # Store layout y-values for use in render
        self._tip_y    = _TIP_Y
        self._vp_row_y = _VP_ROW_Y
        self._ai_row_y = _AI_ROW_Y

        self.room_code = ""
        self.players = []
        self.spectators = []
        self.my_spirit_id = ""
        self.host_spirit_id = ""
        self.vp_to_win = 100
        self.ai_player_count = 0
        self.all_ready = False
        self.error_message = ""
        self._tip_phrase_rect = pygame.Rect(0, 0, 0, 0)
        self.popup_manager = PopupManager()
        # Hold-to-repeat state for VP ± buttons
        self._vp_held = None        # 'minus' | 'plus' | None
        self._vp_hold_timer = 0.0   # seconds until next repeat fire

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _is_host(self) -> bool:
        return self.my_spirit_id == self.host_spirit_id and bool(self.my_spirit_id)

    def _is_spectator(self) -> bool:
        return any(p.get("spirit_id") == self.my_spirit_id for p in self.spectators)

    def _is_ready(self) -> bool:
        return any(p.get("spirit_id") == self.my_spirit_id and p.get("ready")
                   for p in self.players)

    def _send_vp_change(self, direction: str):
        if direction == 'minus':
            new_vp = max(50, self.vp_to_win - 5)
        else:
            new_vp = min(250, self.vp_to_win + 5)
        if new_vp != self.vp_to_win:
            self.app.network.send(MessageType.SET_LOBBY_OPTIONS, {"vp_to_win": new_vp})

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #

    def handle_event(self, event):
        i_am_spectator = self._is_spectator()
        i_am_host = self._is_host()

        if event.type == pygame.MOUSEMOTION:
            self.ready_button.update(event.pos)
            self.spectator_button.update(event.pos)
            self.start_button.update(event.pos)
            if i_am_host:
                self.vp_minus.update(event.pos)
                self.vp_plus.update(event.pos)
                self.ai_minus.update(event.pos)
                self.ai_plus.update(event.pos)
            if self.popup_manager.has_popups():
                self.popup_manager.update_hover(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not i_am_spectator and self.ready_button.clicked(event.pos):
                self.app.network.send(MessageType.READY)
                return

            if self.spectator_button.clicked(event.pos):
                self.app.network.send(MessageType.TOGGLE_SPECTATOR)
                return

            if i_am_host and self.all_ready and self.start_button.clicked(event.pos):
                self.app.network.send(MessageType.START_GAME)
                return

            if i_am_host:
                if self.vp_minus.clicked(event.pos):
                    self._send_vp_change('minus')
                    self._vp_held = 'minus'
                    self._vp_hold_timer = 0.4
                elif self.vp_plus.clicked(event.pos):
                    self._send_vp_change('plus')
                    self._vp_held = 'plus'
                    self._vp_hold_timer = 0.4
                elif self.ai_minus.clicked(event.pos):
                    new_ai = max(0, self.ai_player_count - 1)
                    self.app.network.send(MessageType.SET_LOBBY_OPTIONS, {"ai_count": new_ai})
                elif self.ai_plus.clicked(event.pos):
                    new_ai = min(5, self.ai_player_count + 1)
                    self.app.network.send(MessageType.SET_LOBBY_OPTIONS, {"ai_count": new_ai})

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._vp_held = None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if self.popup_manager.has_popups():
                self.popup_manager.handle_right_click(
                    event.pos, self.small_font, SCREEN_WIDTH)
            elif self._tip_phrase_rect.collidepoint(event.pos):
                self.popup_manager.pin_tooltip(
                    self._LOBBY_TIP_TOOLTIP,
                    self._LOBBY_HOVER_REGIONS,
                    anchor_x=self._tip_phrase_rect.centerx,
                    anchor_y=self._tip_phrase_rect.bottom,
                    font=self.small_font,
                    max_width=420,
                    surface_w=SCREEN_WIDTH,
                    below=True,
                )

    def handle_network(self, msg_type, payload):
        print(f"[lobby] handle_network: {msg_type.value} keys={list(payload.keys())}")
        if msg_type == MessageType.LOBBY_STATE:
            if "room_code" in payload:
                self.room_code = payload["room_code"]
            if "spirit_id" in payload:
                self.my_spirit_id = payload["spirit_id"]
                self.app.my_spirit_id = payload["spirit_id"]
            if "players" in payload:
                self.players = payload["players"]
                print(f"[lobby] Players updated: {len(self.players)} players")
            if "spectators" in payload:
                self.spectators = payload["spectators"]
            if "host_spirit_id" in payload:
                self.host_spirit_id = payload["host_spirit_id"]
            if "vp_to_win" in payload:
                self.vp_to_win = payload["vp_to_win"]
            if "ai_player_count" in payload:
                self.ai_player_count = payload["ai_player_count"]
            if "all_ready" in payload:
                self.all_ready = payload["all_ready"]
        elif msg_type == MessageType.ERROR:
            self.error_message = payload.get("message", "Unknown error")
            print(f"[lobby] Error: {self.error_message}")
            # If we never successfully joined a room, return to menu
            if not self.room_code:
                self.app.network.disconnect()
                menu = self.app.scenes["menu"]
                menu.error_message = self.error_message
                # Reset lobby for next attempt
                self.players = []
                self.spectators = []
                self.my_spirit_id = ""
                self.error_message = ""
                self.app.set_scene("menu")

    def update(self, dt):
        if self._vp_held and self._is_host():
            self._vp_hold_timer -= dt
            if self._vp_hold_timer <= 0.0:
                self._send_vp_change(self._vp_held)
                self._vp_hold_timer = 0.1

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def render(self, screen: pygame.Surface):
        screen.fill((15, 15, 25))

        title = self.title_font.render("Game Lobby", True, (200, 200, 220))
        screen.blit(title, (_CX - title.get_width() // 2, 40))

        if self.room_code:
            code_text = self.font.render(f"Room Code: {self.room_code}", True, (180, 220, 180))
            screen.blit(code_text, (_CX - code_text.get_width() // 2, 80))

        i_am_spectator = self._is_spectator()
        i_am_host = self._is_host()
        i_am_ready = self._is_ready()

        y = 130

        # ── Player list ──────────────────────────────────────────────────
        header = self.font.render("Players:", True, (160, 160, 180))
        screen.blit(header, (_CX - 100, y))
        y += 28

        for player in self.players:
            name = player.get("name", "???")
            ready = player.get("ready", False)
            connected = player.get("connected", True)
            is_me = player.get("spirit_id") == self.my_spirit_id
            is_host = player.get("spirit_id") == self.host_spirit_id

            status = "READY" if ready else "waiting..."
            if not connected:
                status = "disconnected"

            color = (100, 255, 100) if ready else (200, 200, 200)
            if not connected:
                color = (150, 80, 80)

            prefix = "> " if is_me else "  "
            host_tag = " [host]" if is_host else ""
            text = self.font.render(f"{prefix}{name}{host_tag}  [{status}]", True, color)
            screen.blit(text, (_CX - 100, y))
            y += 26

        # ── AI Players count display ─────────────────────────────────────
        if self.ai_player_count > 0 or i_am_host:
            y += 6
            ai_label = self.font.render(
                f"AI Players: {self.ai_player_count}", True, (180, 180, 160))
            screen.blit(ai_label, (_CX - 100, y))
            y += 26

        # ── Spectator list ───────────────────────────────────────────────
        if self.spectators:
            y += 6
            spec_header = self.font.render("Spectators:", True, (140, 140, 160))
            screen.blit(spec_header, (_CX - 100, y))
            y += 26
            for spec in self.spectators:
                name = spec.get("name", "???")
                connected = spec.get("connected", True)
                is_me = spec.get("spirit_id") == self.my_spirit_id
                color = (150, 180, 200) if connected else (100, 80, 80)
                prefix = "> " if is_me else "  "
                text = self.font.render(f"{prefix}{name}  [watching]", True, color)
                screen.blit(text, (_CX - 100, y))
                y += 26

        # ── Host controls: VP and AI count ───────────────────────────────
        vp_y = self._vp_row_y
        ai_y = self._ai_row_y

        if i_am_host:
            # VP row: [-] centred label [+]
            self.vp_minus.draw(screen, self.font)
            vp_text = self.font.render(f"VP to Win: {self.vp_to_win}", True, (200, 200, 160))
            screen.blit(vp_text, (_CX - vp_text.get_width() // 2, vp_y + 6))
            self.vp_plus.draw(screen, self.font)
            # AI count row
            self.ai_minus.draw(screen, self.font)
            ai_text = self.font.render(f"AI Players: {self.ai_player_count}", True, (200, 200, 160))
            screen.blit(ai_text, (_CX - ai_text.get_width() // 2, ai_y + 6))
            self.ai_plus.draw(screen, self.font)
        else:
            # Non-host: read-only display
            vp_disp = self.small_font.render(f"VP to Win: {self.vp_to_win}", True, (160, 160, 140))
            screen.blit(vp_disp, (_CX - vp_disp.get_width() // 2, vp_y + 8))
            ai_disp = self.small_font.render(f"AI Players: {self.ai_player_count}", True, (160, 160, 140))
            screen.blit(ai_disp, (_CX - ai_disp.get_width() // 2, ai_y + 8))

        # ── Buttons ──────────────────────────────────────────────────────
        if i_am_spectator:
            # Spectator: show "Join as Player" only
            self.spectator_button.text = "Join as Player"
            self.spectator_button.color = (80, 120, 60)
            self.spectator_button.rect.x = _CX - _BTN_W // 2
            self.spectator_button.draw(screen, self.font)
        else:
            # Player: show spectator toggle + ready button
            self.spectator_button.text = "Watch as Spectator"
            self.spectator_button.color = (60, 80, 120)
            self.spectator_button.rect.x = _CX - _BTN_W - 5
            self.spectator_button.draw(screen, self.font)

            self.ready_button.text = "Unready" if i_am_ready else "Ready"
            self.ready_button.color = (120, 60, 60) if i_am_ready else (60, 120, 60)
            self.ready_button.draw(screen, self.font)

        # Start button (host only)
        if i_am_host:
            self.start_button.color = (60, 140, 60) if self.all_ready else (70, 70, 80)
            self.start_button.draw(screen, self.font)

        # ── Tip line ─────────────────────────────────────────────────────
        tip_y = self._tip_y
        prefix_str = "Tip: "
        hover_phrase = "underlined text"
        suffix_str = " has on-hover tooltips!"
        p_surf = self.small_font.render(prefix_str, True, (140, 140, 165))
        h_surf = self.small_font.render(hover_phrase, True, (100, 220, 210))
        s_surf = self.small_font.render(suffix_str, True, (140, 140, 165))
        total_w = p_surf.get_width() + h_surf.get_width() + s_surf.get_width()
        start_x = _CX - total_w // 2
        screen.blit(p_surf, (start_x, tip_y))
        hover_x = start_x + p_surf.get_width()
        screen.blit(h_surf, (hover_x, tip_y))
        self._tip_phrase_rect = pygame.Rect(
            hover_x, tip_y, h_surf.get_width(), h_surf.get_height())
        draw_dotted_underline(
            screen, self._tip_phrase_rect.x, self._tip_phrase_rect.bottom - 1,
            self._tip_phrase_rect.width, color=(100, 220, 210))
        screen.blit(s_surf, (self._tip_phrase_rect.right, tip_y))

        mouse_pos = pygame.mouse.get_pos()
        if not self.popup_manager.has_popups() and self._tip_phrase_rect.collidepoint(mouse_pos):
            draw_multiline_tooltip_with_regions(
                screen, self.small_font, self._LOBBY_TIP_TOOLTIP,
                self._LOBBY_HOVER_REGIONS,
                anchor_x=self._tip_phrase_rect.centerx,
                anchor_y=self._tip_phrase_rect.bottom,
                max_width=420, below=True,
            )
        self.popup_manager.render(screen, self.small_font)

        # ── Hint text ─────────────────────────────────────────────────────
        hint = self.small_font.render(
            "All human players must be ready before the host can start",
            True, (100, 100, 120))
        screen.blit(hint, (_CX - hint.get_width() // 2, SCREEN_HEIGHT - 42))

        if self.error_message:
            err = self.small_font.render(self.error_message, True, (255, 100, 100))
            screen.blit(err, (_CX - err.get_width() // 2, SCREEN_HEIGHT - 22))
