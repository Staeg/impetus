"""Settings scene: display mode and other preferences."""

from __future__ import annotations
import pygame
from shared.constants import SCREEN_WIDTH, SCREEN_HEIGHT
from client.renderer.ui_renderer import Button
from client.renderer.font_cache import get_font
import client.theme as theme


class SettingsScene:
    _MODE_OPTIONS = [
        ("borderless", "Borderless"),
        ("windowed", "Windowed"),
        ("fullscreen", "Fullscreen"),
    ]

    def __init__(self, app):
        self.app = app
        self.font = get_font(16)
        self.title_font = get_font(36)
        self.small_font = get_font(14)
        self.return_scene: str = "menu"
        self.back_button: Button | None = None
        self.mode_buttons: list[tuple[str, Button]] = []
        self.on_resize(SCREEN_WIDTH, SCREEN_HEIGHT)

    def on_resize(self, width: int, height: int) -> None:
        cx = width // 2
        self.back_button = Button(
            pygame.Rect(cx - 80, height - 100, 160, 44),
            "Back", (70, 70, 90)
        )

        button_w = 220
        button_h = 46
        block_h = 92
        start_y = max(220, height // 2 - (len(self._MODE_OPTIONS) * block_h) // 2)
        self.mode_buttons = []
        for idx, (mode, label) in enumerate(self._MODE_OPTIONS):
            rect = pygame.Rect(cx - button_w // 2, start_y + idx * block_h, button_w, button_h)
            self.mode_buttons.append((mode, Button(rect, label, (60, 60, 80))))

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.back_button.update(event.pos)
            for _, button in self.mode_buttons:
                button.update(event.pos)

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._go_back()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for mode, button in self.mode_buttons:
                if button.clicked(event.pos):
                    self.app.set_display_mode(mode)
                    return
            if self.back_button.clicked(event.pos):
                self._go_back()

    def _go_back(self):
        dest = self.return_scene
        self.return_scene = "menu"
        self.app.set_scene(dest)

    def update(self, dt):
        pass

    def render(self, screen: pygame.Surface):
        screen.fill(theme.BG_MENU)

        title = self.title_font.render("Settings", True, theme.TITLE_TEXT)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))

        subtitle = self.font.render("Display Mode", True, theme.TEXT_HIGHLIGHT)
        screen.blit(subtitle, (SCREEN_WIDTH // 2 - subtitle.get_width() // 2, 180))

        description_map = {
            "borderless": "Native monitor size in a borderless window. Default launch mode.",
            "windowed": "Resizable window that renders at the current window size.",
            "fullscreen": "Exclusive fullscreen mode.",
        }

        for mode, button in self.mode_buttons:
            active = self.app.display_mode == mode
            button.color = (90, 120, 80) if active else (60, 60, 80)
            button.hover_color = (110, 145, 95) if active else (90, 90, 120)
            button.draw(screen, self.font)
            desc = self.small_font.render(description_map[mode], True, theme.TEXT_DIM)
            screen.blit(desc, (SCREEN_WIDTH // 2 - desc.get_width() // 2, button.rect.bottom + 10))

        hint = self.small_font.render("F11 toggles exclusive fullscreen on and off", True, (90, 90, 110))
        last_button = self.mode_buttons[-1][1]
        hint_y = min(SCREEN_HEIGHT - 150, last_button.rect.bottom + 70)
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, hint_y))

        self.back_button.draw(screen, self.font)
