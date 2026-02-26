"""End-of-game scoreboard."""

from __future__ import annotations
import pygame
from shared.constants import SCREEN_WIDTH, SCREEN_HEIGHT


class ResultsScene:
    def __init__(self, app):
        self.app = app
        self.font = pygame.font.SysFont("consolas", 16)
        self.bold_font = pygame.font.SysFont("consolas", 16, bold=True)
        self.title_font = pygame.font.SysFont("consolas", 32)
        self.small_font = pygame.font.SysFont("consolas", 14)
        self.win_font = pygame.font.SysFont("consolas", 28, bold=True)
        self.scores: dict = {}
        self.winners: list[str] = []
        self.spirits: dict = {}

    def set_results(self, winners: list[str], scores: dict, spirits: dict):
        self.winners = winners
        self.scores = scores
        self.spirits = spirits

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.set_scene("menu")

    def handle_network(self, msg_type, payload):
        pass

    def update(self, dt):
        pass

    def render(self, screen: pygame.Surface):
        # Show the actual final board state instead of a blank scoreboard scene.
        game_scene = self.app.scenes.get("game")
        if game_scene:
            game_scene.render(screen)
        else:
            screen.fill((15, 15, 25))

        # Right-side scoreboard overlay with winner names bolded.
        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        panel_w = 260
        panel_h = 42 + len(sorted_scores) * 24 + 12
        panel_x = SCREEN_WIDTH - panel_w - 16
        panel_y = 52
        panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        overlay.fill((20, 20, 30, 210))
        screen.blit(overlay, (panel_x, panel_y))
        pygame.draw.rect(screen, (130, 130, 170), panel, 1, border_radius=4)

        header = self.font.render("Final Scores", True, (220, 220, 240))
        screen.blit(header, (panel_x + 10, panel_y + 10))

        y = panel_y + 34
        for spirit_id, vp in sorted_scores:
            spirit = self.spirits.get(spirit_id, {})
            name = spirit.get("name", spirit_id[:8])
            is_winner = spirit_id in self.winners
            row_font = self.bold_font if is_winner else self.font
            color = (255, 220, 130) if is_winner else (190, 190, 210)
            text = row_font.render(f"{name}: {vp} VP", True, color)
            screen.blit(text, (panel_x + 10, y))
            y += 24

        winner_name = ""
        if self.winners:
            winner_id = self.winners[0]
            winner_name = self.spirits.get(winner_id, {}).get("name", winner_id[:8])
        if winner_name:
            win_text = self.win_font.render(f"{winner_name} wins!", True, (255, 220, 120))
            screen.blit(win_text, (20, SCREEN_HEIGHT - win_text.get_height() - 20))

        hint = self.small_font.render("Press Escape to return to menu", True, (120, 120, 145))
        screen.blit(hint, (SCREEN_WIDTH - hint.get_width() - 16, SCREEN_HEIGHT - 24))
