"""Main menu scene: start local play, tutorials, or join multiplayer."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from shared.constants import SCREEN_WIDTH, SCREEN_HEIGHT, DEFAULT_PORT
from shared.protocol import C2S
from client.renderer.ui_renderer import Button
from client.renderer.font_cache import get_font
import client.theme as theme


def _get_clipboard() -> str:
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


@dataclass
class _Field:
    key: str
    label: str
    max_length: int
    uppercase: bool = False


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.font = get_font(16)
        self.title_font = get_font(36)
        self.small_font = get_font(14)

        self.single_player_button = None
        self.tutorial_button = None
        self.host_button = None
        self.join_button = None
        self.settings_button = None
        self.rejoin_game_button = None
        self.cancel_button = None
        self.continue_button = None
        self.tutorial_basics_button = None
        self.tutorial_advanced_button = None
        self.tutorial_back_button = None

        self.server_address = "localhost:8765"
        self.player_name = ""
        self.room_code = ""
        self.host_code = ""
        self.error_message = ""
        self.show_tutorial_menu = False
        self.active_flow: str | None = None
        self.active_input: str | None = None

        self._fields = {
            "single_player": [
                _Field("player_name", "Player Name", 16),
            ],
            "host_multiplayer": [
                _Field("player_name", "Player Name", 16),
                _Field("server_address", "Server", 45),
                _Field("host_code", "Room Code", 6, uppercase=True),
            ],
            "join_multiplayer": [
                _Field("player_name", "Player Name", 16),
                _Field("server_address", "Server", 45),
                _Field("room_code", "Room Code", 6, uppercase=True),
            ],
        }

        self.on_resize(SCREEN_WIDTH, SCREEN_HEIGHT)

    def on_resize(self, width: int, height: int) -> None:
        cx = width // 2
        cy = height // 2

        self.single_player_button = Button(
            pygame.Rect(cx - 120, cy - 100, 240, 50),
            "Single Player", (50, 110, 70)
        )
        self.tutorial_button = Button(
            pygame.Rect(cx - 120, cy - 30, 240, 50),
            "Tutorial", (60, 80, 110)
        )
        self.host_button = Button(
            pygame.Rect(cx - 120, cy + 40, 240, 50),
            "Host Game", (60, 80, 130)
        )
        self.join_button = Button(
            pygame.Rect(cx - 120, cy + 110, 240, 50),
            "Join Game", (60, 80, 130)
        )
        self.settings_button = Button(
            pygame.Rect(cx - 120, cy + 180, 240, 50),
            "Settings", (60, 60, 80)
        )
        self.rejoin_game_button = Button(
            pygame.Rect(cx - 160, cy + 120, 150, 42),
            "Rejoin", (76, 104, 72)
        )
        self.continue_button = Button(
            pygame.Rect(cx + 10, cy + 120, 150, 42),
            "Continue", (60, 120, 60)
        )
        self.cancel_button = Button(
            pygame.Rect(cx - 75, cy + 176, 150, 40),
            "Back", (60, 60, 80)
        )
        self.tutorial_basics_button = Button(
            pygame.Rect(cx - 120, cy + 20, 240, 50),
            "Basics", (69, 101, 134)
        )
        self.tutorial_advanced_button = Button(
            pygame.Rect(cx - 120, cy + 90, 240, 50),
            "Advanced Mechanics", (84, 94, 124)
        )
        self.tutorial_back_button = Button(
            pygame.Rect(cx - 120, cy + 160, 240, 50),
            "Back", (60, 60, 80)
        )

    def _set_flow(self, flow: str | None) -> None:
        self.active_flow = flow
        self.active_input = None
        self.error_message = ""

        if flow == "single_player":
            self.active_input = "player_name"
        elif flow == "host_multiplayer":
            self.host_code = self.host_code[:6]
            self.active_input = "player_name"
        elif flow == "join_multiplayer":
            self.room_code = self.room_code[:6]
            self.active_input = "player_name"

    def _apply_server_address(self) -> None:
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

    def _current_room_code(self) -> str:
        if self.active_flow == "host_multiplayer":
            return self.host_code.strip().upper()
        if self.active_flow == "join_multiplayer":
            return self.room_code.strip().upper()
        return ""

    def _current_server_parts(self) -> tuple[str, int]:
        self._apply_server_address()
        return self.app.server_host, self.app.server_port

    def _can_submit_flow(self) -> bool:
        if self.active_flow == "single_player":
            return bool(self.player_name.strip())
        if self.active_flow == "host_multiplayer":
            return bool(self.player_name.strip() and self.server_address.strip() and self.host_code.strip())
        if self.active_flow == "join_multiplayer":
            return bool(self.player_name.strip() and self.server_address.strip() and self.room_code.strip())
        return False

    def _can_rejoin_current_selection(self) -> bool:
        if self.active_flow not in {"host_multiplayer", "join_multiplayer"}:
            return False
        host, port = self._current_server_parts()
        room_code = self._current_room_code()
        return self.app.has_saved_multiplayer_rejoin(
            self.player_name.strip(),
            room_code,
            host,
            port,
        )

    def _start_single_player(self) -> None:
        self.error_message = ""
        self.app.start_local_transport()
        self.app.network.send(C2S.JOIN_GAME, {
            "player_name": self.player_name.strip(),
        })
        self.app.network.send(C2S.SET_LOBBY_OPTIONS, {"ai_count": 1})
        self.app.set_scene("lobby")

    def _start_tutorial(self, campaign_id: str) -> None:
        self.show_tutorial_menu = False
        self.player_name = "Player"
        self.app.start_tutorial(campaign_id)

    def _host_game(self) -> None:
        self._apply_server_address()
        self.error_message = ""
        self.app.connect_to_server()
        self.app.network.send(C2S.JOIN_GAME, {
            "player_name": self.player_name.strip(),
            "create_room": self.host_code.strip().upper(),
        })
        self.app.set_scene("lobby")

    def _join_room(self) -> None:
        self._apply_server_address()
        self.error_message = ""
        self.app.connect_to_server()
        self.app.network.send(C2S.JOIN_GAME, {
            "player_name": self.player_name.strip(),
            "room_code": self.room_code.strip().upper(),
        })
        self.app.set_scene("lobby")

    def _submit_flow(self) -> None:
        if not self._can_submit_flow():
            self.error_message = "Fill in all required fields first."
            return
        if self.active_flow == "single_player":
            self._start_single_player()
        elif self.active_flow == "host_multiplayer":
            self._host_game()
        elif self.active_flow == "join_multiplayer":
            self._join_room()

    def _rejoin_current_selection(self) -> None:
        host, port = self._current_server_parts()
        room_code = self._current_room_code()
        self.error_message = ""
        self.app.rejoin_saved_multiplayer_game(
            self.player_name.strip(),
            room_code,
            host,
            port,
        )

    def _field_rect(self, index: int) -> pygame.Rect:
        width = 320
        top = SCREEN_HEIGHT // 2 - 68
        return pygame.Rect(SCREEN_WIDTH // 2 - width // 2, top + index * 58, width, 36)

    def _field_at_pos(self, pos: tuple[int, int]) -> str | None:
        fields = self._fields.get(self.active_flow or "", [])
        for idx, field in enumerate(fields):
            if self._field_rect(idx).collidepoint(pos):
                return field.key
        return None

    def _update_button_hover(self, pos: tuple[int, int]) -> None:
        self.single_player_button.update(pos)
        self.tutorial_button.update(pos)
        self.host_button.update(pos)
        self.join_button.update(pos)
        self.settings_button.update(pos)
        self.rejoin_game_button.update(pos)
        self.continue_button.update(pos)
        self.cancel_button.update(pos)
        self.tutorial_basics_button.update(pos)
        self.tutorial_advanced_button.update(pos)
        self.tutorial_back_button.update(pos)

    def _handle_active_field_input(self, event: pygame.event.Event) -> bool:
        if not self.active_input:
            return False
        field = next((item for item in self._fields.get(self.active_flow or "", []) if item.key == self.active_input), None)
        if not field:
            return False

        current = getattr(self, field.key)
        is_paste = (event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL)

        if event.key == pygame.K_RETURN:
            if self.active_flow in {"host_multiplayer", "join_multiplayer"} and self.active_input != self._fields[self.active_flow][-1].key:
                keys = [item.key for item in self._fields[self.active_flow]]
                next_idx = keys.index(self.active_input) + 1
                self.active_input = keys[next_idx]
            else:
                self._submit_flow()
            return True
        if event.key == pygame.K_ESCAPE:
            self._set_flow(None)
            return True
        if event.key == pygame.K_TAB and self.active_flow:
            keys = [item.key for item in self._fields[self.active_flow]]
            idx = keys.index(self.active_input)
            self.active_input = keys[(idx + 1) % len(keys)]
            return True
        if event.key == pygame.K_BACKSPACE:
            setattr(self, field.key, current[:-1])
            return True
        if is_paste:
            text = _get_clipboard()
            if field.uppercase:
                text = text.upper()
            setattr(self, field.key, (current + text)[:field.max_length])
            return True
        if event.unicode and event.unicode.isprintable() and len(current) < field.max_length:
            value = event.unicode.upper() if field.uppercase else event.unicode
            setattr(self, field.key, current + value)
            return True
        return False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._update_button_hover(event.pos)

        if event.type == pygame.KEYDOWN:
            if self.show_tutorial_menu:
                if event.key == pygame.K_ESCAPE:
                    self.show_tutorial_menu = False
                    return
            elif self.active_flow and self._handle_active_field_input(event):
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.show_tutorial_menu:
                if self.tutorial_basics_button.clicked(event.pos):
                    self._start_tutorial("basics")
                elif self.tutorial_advanced_button.clicked(event.pos):
                    self._start_tutorial("advanced")
                elif self.tutorial_back_button.clicked(event.pos):
                    self.show_tutorial_menu = False
                return

            if self.active_flow:
                clicked_field = self._field_at_pos(event.pos)
                if clicked_field:
                    self.active_input = clicked_field
                    return
                if self.cancel_button.clicked(event.pos):
                    self._set_flow(None)
                    return
                if self._can_rejoin_current_selection() and self.rejoin_game_button.clicked(event.pos):
                    self._rejoin_current_selection()
                    return
                if self.continue_button.clicked(event.pos):
                    self._submit_flow()
                    return
                return

            if self.single_player_button.clicked(event.pos):
                self._set_flow("single_player")
            elif self.tutorial_button.clicked(event.pos):
                self.show_tutorial_menu = True
            elif self.host_button.clicked(event.pos):
                self._set_flow("host_multiplayer")
            elif self.join_button.clicked(event.pos):
                self._set_flow("join_multiplayer")
            elif self.settings_button.clicked(event.pos):
                self.app.set_scene("settings")

    def update(self, dt):
        pass

    def get_persistent_state(self) -> dict:
        return {
            "player_name": self.player_name,
            "server_address": self.server_address,
            "room_code": self.room_code,
            "host_code": self.host_code,
            "active_flow": self.active_flow,
            "active_input": self.active_input,
        }

    def apply_persistent_state(self, state: dict) -> None:
        self.player_name = str(state.get("player_name", self.player_name))
        self.server_address = str(state.get("server_address", self.server_address))
        self.room_code = str(state.get("room_code", self.room_code)).upper()[:6]
        self.host_code = str(state.get("host_code", self.host_code)).upper()[:6]
        self.active_flow = state.get("active_flow")
        self.active_input = state.get("active_input")
        if self.active_flow not in self._fields:
            self.active_flow = None
            self.active_input = None
        elif self.active_input not in {field.key for field in self._fields[self.active_flow]}:
            self.active_input = self._fields[self.active_flow][0].key
        self.show_tutorial_menu = False

    def _render_main_menu(self, screen: pygame.Surface) -> None:
        self.single_player_button.draw(screen, self.font)
        self.tutorial_button.draw(screen, self.font)
        self.host_button.draw(screen, self.font)
        self.join_button.draw(screen, self.font)
        self.settings_button.draw(screen, self.font)

    def _render_tutorial_menu(self, screen: pygame.Surface) -> None:
        heading = self.font.render("Choose a Tutorial", True, theme.TEXT_BRIGHT)
        desc = self.small_font.render(
            "Launches a local scripted lesson as Player without entering the lobby.",
            True,
            theme.TEXT_DIM,
        )
        screen.blit(heading, (SCREEN_WIDTH // 2 - heading.get_width() // 2, SCREEN_HEIGHT // 2 - 70))
        screen.blit(desc, (SCREEN_WIDTH // 2 - desc.get_width() // 2, SCREEN_HEIGHT // 2 - 42))
        self.tutorial_basics_button.draw(screen, self.font)
        self.tutorial_advanced_button.draw(screen, self.font)
        self.tutorial_back_button.draw(screen, self.font)

    def _render_flow(self, screen: pygame.Surface) -> None:
        titles = {
            "single_player": "Start Single Player",
            "host_multiplayer": "Host Multiplayer Game",
            "join_multiplayer": "Join Multiplayer Game",
        }
        subtitles = {
            "single_player": "Choose the name for your local session.",
            "host_multiplayer": "Enter your name, the server to connect to, and the room code to host.",
            "join_multiplayer": "Enter your name, the server, and the room code to join or rejoin.",
        }

        heading = self.font.render(titles[self.active_flow], True, theme.TEXT_BRIGHT)
        desc = self.small_font.render(subtitles[self.active_flow], True, theme.TEXT_DIM)
        screen.blit(heading, (SCREEN_WIDTH // 2 - heading.get_width() // 2, SCREEN_HEIGHT // 2 - 120))
        screen.blit(desc, (SCREEN_WIDTH // 2 - desc.get_width() // 2, SCREEN_HEIGHT // 2 - 94))

        for idx, field in enumerate(self._fields[self.active_flow]):
            rect = self._field_rect(idx)
            label = self.small_font.render(field.label, True, theme.TEXT_NORMAL)
            screen.blit(label, (rect.x, rect.y - 18))
            active = self.active_input == field.key
            border_color = theme.BORDER_INPUT_ACTIVE if active else theme.BORDER_INPUT
            pygame.draw.rect(screen, theme.BG_INPUT, rect, border_radius=4)
            pygame.draw.rect(screen, border_color, rect, 1, border_radius=4)

            value = getattr(self, field.key)
            display = value + ("|" if active else "")
            text = self.font.render(display, True, theme.TEXT_BRIGHT)
            screen.blit(text, (rect.x + 8, rect.y + 8))

        self.continue_button.text = "Continue" if self.active_flow != "join_multiplayer" else "Join"
        self.continue_button.draw(screen, self.font)
        self.cancel_button.draw(screen, self.font)
        if self._can_rejoin_current_selection():
            self.rejoin_game_button.draw(screen, self.font)

        hint = self.small_font.render("Tab switches fields. Enter submits. Esc goes back.", True, theme.TEXT_DIM)
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT // 2 + 230))

    def render(self, screen: pygame.Surface):
        screen.fill(theme.BG_MENU)

        title = self.title_font.render("IMPETUS", True, theme.TITLE_TEXT)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))

        subtitle = self.small_font.render("A game of spirits and factions", True, theme.TEXT_DIM)
        screen.blit(subtitle, (SCREEN_WIDTH // 2 - subtitle.get_width() // 2, 125))

        if self.show_tutorial_menu:
            self._render_tutorial_menu(screen)
        elif self.active_flow:
            self._render_flow(screen)
        else:
            self._render_main_menu(screen)

        if self.error_message:
            err = self.small_font.render(self.error_message, True, theme.TEXT_ERROR)
            screen.blit(err, (SCREEN_WIDTH // 2 - err.get_width() // 2, SCREEN_HEIGHT - 60))
