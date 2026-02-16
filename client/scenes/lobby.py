"""Pre-game lobby: player list, ready state."""

import pygame
from shared.constants import MessageType, SCREEN_WIDTH, SCREEN_HEIGHT
from client.renderer.ui_renderer import Button, draw_dotted_underline
from client.renderer.popup_manager import (
    PopupManager, HoverRegion, draw_multiline_tooltip_with_regions
)


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

        self.ready_button = Button(
            pygame.Rect(SCREEN_WIDTH // 2 - 80, SCREEN_HEIGHT - 100, 160, 44),
            "Ready", (60, 120, 60)
        )

        self.room_code = ""
        self.players = []
        self.my_spirit_id = ""
        self.error_message = ""
        self._tip_phrase_rect = pygame.Rect(0, 0, 0, 0)
        self.popup_manager = PopupManager()

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.ready_button.update(event.pos)
            if self.popup_manager.has_popups():
                self.popup_manager.update_hover(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.ready_button.clicked(event.pos):
                self.app.network.send(MessageType.READY)
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
                self.my_spirit_id = ""
                self.error_message = ""
                self.app.set_scene("menu")

    def update(self, dt):
        pass

    def render(self, screen: pygame.Surface):
        screen.fill((15, 15, 25))

        title = self.title_font.render("Game Lobby", True, (200, 200, 220))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 40))

        if self.room_code:
            code_text = self.font.render(f"Room Code: {self.room_code}", True, (180, 220, 180))
            screen.blit(code_text, (SCREEN_WIDTH // 2 - code_text.get_width() // 2, 80))

        # Player list
        y = 130
        header = self.font.render("Players:", True, (160, 160, 180))
        screen.blit(header, (SCREEN_WIDTH // 2 - 100, y))
        y += 30

        for player in self.players:
            name = player.get("name", "???")
            ready = player.get("ready", False)
            connected = player.get("connected", True)
            is_me = player.get("spirit_id") == self.my_spirit_id

            status = "READY" if ready else "waiting..."
            if not connected:
                status = "disconnected"

            color = (100, 255, 100) if ready else (200, 200, 200)
            if not connected:
                color = (150, 80, 80)
            if is_me:
                name = f"> {name}"

            text = self.font.render(f"{name}  [{status}]", True, color)
            screen.blit(text, (SCREEN_WIDTH // 2 - 100, y))
            y += 26

        # Ready button
        is_ready = any(p.get("spirit_id") == self.my_spirit_id and p.get("ready")
                      for p in self.players)
        self.ready_button.text = "Unready" if is_ready else "Ready"
        self.ready_button.color = (120, 60, 60) if is_ready else (60, 120, 60)
        self.ready_button.draw(screen, self.font)

        # Tip line above the ready button with nested hover tooltips.
        tip_y = self.ready_button.rect.y - 22
        prefix = "Tip: "
        hover_phrase = "underlined text"
        suffix = " has on-hover tooltips!"
        p_surf = self.small_font.render(prefix, True, (140, 140, 165))
        h_surf = self.small_font.render(hover_phrase, True, (100, 220, 210))
        s_surf = self.small_font.render(suffix, True, (140, 140, 165))
        total_w = p_surf.get_width() + h_surf.get_width() + s_surf.get_width()
        start_x = SCREEN_WIDTH // 2 - total_w // 2
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

        hint = self.small_font.render("All players must be ready to start", True, (100, 100, 120))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 50))

        if self.error_message:
            err = self.small_font.render(self.error_message, True, (255, 100, 100))
            screen.blit(err, (SCREEN_WIDTH // 2 - err.get_width() // 2, SCREEN_HEIGHT - 30))
