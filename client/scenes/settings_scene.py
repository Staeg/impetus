"""Settings scene: fullscreen toggle and other preferences."""

import pygame
from shared.constants import SCREEN_WIDTH, SCREEN_HEIGHT
from client.renderer.ui_renderer import Button
from client.renderer.font_cache import get_font
import client.theme as theme


class SettingsScene:
    def __init__(self, app):
        self.app = app
        self.font = get_font(16)
        self.title_font = get_font(36)
        self.small_font = get_font(14)
        self.return_scene: str = "menu"  # where Back/Escape navigates to

        cx = SCREEN_WIDTH // 2
        self.back_button = Button(
            pygame.Rect(cx - 80, SCREEN_HEIGHT - 100, 160, 44),
            "Back", (70, 70, 90)
        )

        # Checkbox rect for fullscreen toggle
        self.checkbox_rect = pygame.Rect(cx - 110, SCREEN_HEIGHT // 2 - 16, 22, 22)
        self.label_rect = pygame.Rect(cx - 80, SCREEN_HEIGHT // 2 - 16, 200, 22)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.back_button.update(event.pos)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._go_back()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Clicking checkbox or its label toggles fullscreen
            toggle_rect = pygame.Rect(
                self.checkbox_rect.x, self.checkbox_rect.y,
                self.label_rect.right - self.checkbox_rect.x,
                self.checkbox_rect.height
            )
            if toggle_rect.collidepoint(event.pos):
                self.app.toggle_fullscreen()
            elif self.back_button.clicked(event.pos):
                self._go_back()

    def _go_back(self):
        dest = self.return_scene
        self.return_scene = "menu"  # reset for next time
        self.app.set_scene(dest)

    def update(self, dt):
        pass

    def render(self, screen: pygame.Surface):
        screen.fill(theme.BG_MENU)

        title = self.title_font.render("Settings", True, theme.TITLE_TEXT)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))

        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2

        # Fullscreen checkbox
        cb = self.checkbox_rect
        pygame.draw.rect(screen, theme.BG_INPUT, cb, border_radius=3)
        pygame.draw.rect(screen, theme.BORDER_INPUT, cb, 1, border_radius=3)
        if self.app.fullscreen:
            # Draw X inside checkbox
            margin = 4
            pygame.draw.line(screen, theme.CHECKBOX_FILL,
                             (cb.x + margin, cb.y + margin),
                             (cb.right - margin, cb.bottom - margin), 2)
            pygame.draw.line(screen, theme.CHECKBOX_FILL,
                             (cb.right - margin, cb.y + margin),
                             (cb.x + margin, cb.bottom - margin), 2)

        label = self.font.render("Fullscreen", True, theme.TEXT_HIGHLIGHT)
        screen.blit(label, (cb.right + 10, cb.y + (cb.height - label.get_height()) // 2))

        hint = self.small_font.render("F11 to toggle fullscreen from any screen", True, (90, 90, 110))
        screen.blit(hint, (cx - hint.get_width() // 2, cy + 40))

        self.back_button.draw(screen, self.font)
