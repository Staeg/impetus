"""Pre-game lobby: player list, ready state."""

import pygame
from shared.constants import MessageType, SCREEN_WIDTH, SCREEN_HEIGHT
from client.renderer.ui_renderer import Button


class LobbyScene:
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

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.ready_button.update(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.ready_button.clicked(event.pos):
                self.app.network.send(MessageType.READY)

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

        hint = self.small_font.render("All players must be ready to start", True, (100, 100, 120))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 50))

        if self.error_message:
            err = self.small_font.render(self.error_message, True, (255, 100, 100))
            screen.blit(err, (SCREEN_WIDTH // 2 - err.get_width() // 2, SCREEN_HEIGHT - 30))
