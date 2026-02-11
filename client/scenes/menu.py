"""Main menu scene: host/join options."""

import pygame
from shared.constants import MessageType, SCREEN_WIDTH, SCREEN_HEIGHT, DEFAULT_PORT
from client.renderer.ui_renderer import Button


def _get_clipboard():
    """Get text from the system clipboard."""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        data = pygame.scrap.get(pygame.SCRAP_TEXT)
        if data:
            return data.decode("utf-8").rstrip("\x00")
    except Exception:
        pass
    return ""


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.font = pygame.font.SysFont("consolas", 16)
        self.title_font = pygame.font.SysFont("consolas", 36)
        self.small_font = pygame.font.SysFont("consolas", 14)

        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2

        self.host_button = Button(
            pygame.Rect(cx - 120, cy - 20, 240, 50),
            "Host Game", (60, 80, 130)
        )
        self.join_button = Button(
            pygame.Rect(cx - 120, cy + 50, 240, 50),
            "Join Game", (60, 80, 130)
        )

        self.entering_name = True
        self.entering_code = False
        self.entering_host_code = False
        self.entering_server = False
        self.player_name = ""
        self.room_code = ""
        self.host_code = ""
        self.server_address = "192.168.178.187:8765"
        self.error_message = ""
        self.name_confirmed = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.host_button.update(event.pos)
            self.join_button.update(event.pos)

        if event.type == pygame.KEYDOWN:
            is_paste = (event.key == pygame.K_v and
                        event.mod & pygame.KMOD_CTRL)

            if self.entering_name:
                if event.key == pygame.K_RETURN and self.player_name.strip():
                    self.entering_name = False
                    self.name_confirmed = True
                elif event.key == pygame.K_BACKSPACE:
                    self.player_name = self.player_name[:-1]
                elif is_paste:
                    text = _get_clipboard()
                    self.player_name = (self.player_name + text)[:16]
                elif event.unicode and event.unicode.isprintable() and len(self.player_name) < 16:
                    self.player_name += event.unicode
                return
            elif self.entering_server:
                if event.key == pygame.K_RETURN:
                    self._apply_server_address()
                    self.entering_server = False
                elif event.key == pygame.K_ESCAPE:
                    self.entering_server = False
                elif event.key == pygame.K_BACKSPACE:
                    self.server_address = self.server_address[:-1]
                elif is_paste:
                    text = _get_clipboard()
                    self.server_address = (self.server_address + text)[:45]
                elif event.unicode and event.unicode.isprintable() and len(self.server_address) < 45:
                    self.server_address += event.unicode
                return
            elif self.entering_host_code:
                if event.key == pygame.K_RETURN and self.host_code.strip():
                    self._host_game()
                elif event.key == pygame.K_ESCAPE:
                    self.entering_host_code = False
                elif event.key == pygame.K_BACKSPACE:
                    self.host_code = self.host_code[:-1]
                elif is_paste:
                    text = _get_clipboard().upper()
                    self.host_code = (self.host_code + text)[:6]
                elif event.unicode and event.unicode.isprintable() and len(self.host_code) < 6:
                    self.host_code += event.unicode.upper()
                return
            elif self.entering_code:
                if event.key == pygame.K_RETURN and self.room_code.strip():
                    self._join_room()
                elif event.key == pygame.K_ESCAPE:
                    self.entering_code = False
                elif event.key == pygame.K_BACKSPACE:
                    self.room_code = self.room_code[:-1]
                elif is_paste:
                    text = _get_clipboard().upper()
                    self.room_code = (self.room_code + text)[:6]
                elif event.unicode and event.unicode.isprintable() and len(self.room_code) < 6:
                    self.room_code += event.unicode.upper()
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.name_confirmed:
                return
            # Check if server address area was clicked
            server_rect = pygame.Rect(SCREEN_WIDTH // 2 - 140, 198, 280, 28)
            if server_rect.collidepoint(event.pos):
                self.entering_server = True
                return
            # Clicking outside server field closes it
            if self.entering_server:
                self._apply_server_address()
                self.entering_server = False
            if self.host_button.clicked(event.pos):
                self.entering_host_code = True
                self.host_code = ""
            elif self.join_button.clicked(event.pos):
                self.entering_code = True
                self.room_code = ""

    def _apply_server_address(self):
        addr = self.server_address.strip()
        if ":" in addr:
            host, _, port_str = addr.rpartition(":")
            try:
                self.app.server_port = int(port_str)
                self.app.server_host = host
            except ValueError:
                self.app.server_host = addr
                self.app.server_port = DEFAULT_PORT
        else:
            self.app.server_host = addr
            self.app.server_port = DEFAULT_PORT

    def _host_game(self):
        self._apply_server_address()
        self.app.connect_to_server()
        self.app.network.send(MessageType.JOIN_GAME, {
            "player_name": self.player_name.strip(),
            "create_room": self.host_code.strip(),
        })
        self.entering_host_code = False
        self.app.set_scene("lobby")

    def _join_room(self):
        self._apply_server_address()
        self.app.connect_to_server()
        self.app.network.send(MessageType.JOIN_GAME, {
            "player_name": self.player_name.strip(),
            "room_code": self.room_code.strip(),
        })
        self.app.set_scene("lobby")

    def update(self, dt):
        pass

    def render(self, screen: pygame.Surface):
        screen.fill((15, 15, 25))

        title = self.title_font.render("IMPETUS", True, (200, 180, 140))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))

        subtitle = self.small_font.render("A game of spirits and factions", True, (120, 120, 140))
        screen.blit(subtitle, (SCREEN_WIDTH // 2 - subtitle.get_width() // 2, 125))

        if self.entering_name:
            prompt = self.font.render("Enter your name:", True, (180, 180, 200))
            screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, 220))

            name_rect = pygame.Rect(SCREEN_WIDTH // 2 - 120, 250, 240, 36)
            pygame.draw.rect(screen, (40, 40, 55), name_rect, border_radius=4)
            pygame.draw.rect(screen, (100, 100, 140), name_rect, 1, border_radius=4)

            name_text = self.font.render(self.player_name, True, (220, 220, 240))
            cursor = self.font.render("|", True, (220, 220, 240))
            screen.blit(name_text, (name_rect.x + 8, name_rect.y + 8))
            screen.blit(cursor, (name_rect.x + 8 + name_text.get_width() - 1, name_rect.y + 8))

            hint = self.small_font.render("Press Enter to confirm", True, (100, 100, 120))
            screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 295))
            return

        if self.entering_host_code:
            prompt = self.font.render("Choose a room code:", True, (180, 180, 200))
            screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, 220))

            code_rect = pygame.Rect(SCREEN_WIDTH // 2 - 80, 250, 160, 36)
            pygame.draw.rect(screen, (40, 40, 55), code_rect, border_radius=4)
            pygame.draw.rect(screen, (100, 100, 140), code_rect, 1, border_radius=4)

            code_text = self.font.render(self.host_code + "|", True, (220, 220, 240))
            screen.blit(code_text, (code_rect.x + 8, code_rect.y + 8))

            hint = self.small_font.render("Press Enter to host, Esc to cancel", True, (100, 100, 120))
            screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 295))
            return

        if self.entering_code:
            prompt = self.font.render("Enter room code:", True, (180, 180, 200))
            screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, 220))

            code_rect = pygame.Rect(SCREEN_WIDTH // 2 - 80, 250, 160, 36)
            pygame.draw.rect(screen, (40, 40, 55), code_rect, border_radius=4)
            pygame.draw.rect(screen, (100, 100, 140), code_rect, 1, border_radius=4)

            code_text = self.font.render(self.room_code + "|", True, (220, 220, 240))
            screen.blit(code_text, (code_rect.x + 8, code_rect.y + 8))

            hint = self.small_font.render("Press Enter to join, Esc to cancel", True, (100, 100, 120))
            screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 295))
            return

        # Show name
        name_text = self.small_font.render(f"Playing as: {self.player_name}", True, (140, 180, 140))
        screen.blit(name_text, (SCREEN_WIDTH // 2 - name_text.get_width() // 2, 170))

        # Server address field
        server_label = self.small_font.render("Server:", True, (130, 130, 150))
        screen.blit(server_label, (SCREEN_WIDTH // 2 - 140, 203))

        server_rect = pygame.Rect(SCREEN_WIDTH // 2 - 80, 198, 220, 28)
        border_color = (140, 140, 180) if self.entering_server else (70, 70, 90)
        pygame.draw.rect(screen, (30, 30, 42), server_rect, border_radius=4)
        pygame.draw.rect(screen, border_color, server_rect, 1, border_radius=4)

        display_addr = self.server_address + ("|" if self.entering_server else "")
        addr_text = self.small_font.render(display_addr, True, (180, 180, 200))
        screen.blit(addr_text, (server_rect.x + 6, server_rect.y + 6))

        self.host_button.draw(screen, self.font)
        self.join_button.draw(screen, self.font)

        if self.error_message:
            err = self.small_font.render(self.error_message, True, (255, 100, 100))
            screen.blit(err, (SCREEN_WIDTH // 2 - err.get_width() // 2, SCREEN_HEIGHT - 60))
