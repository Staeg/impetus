"""End-of-game scoreboard."""

import pygame
from shared.constants import SCREEN_WIDTH, SCREEN_HEIGHT


class ResultsScene:
    def __init__(self, app):
        self.app = app
        self.font = pygame.font.SysFont("consolas", 16)
        self.title_font = pygame.font.SysFont("consolas", 32)
        self.small_font = pygame.font.SysFont("consolas", 14)
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
        screen.fill((15, 15, 25))

        title = self.title_font.render("Game Over", True, (200, 180, 140))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 60))

        # Winner(s)
        winner_names = []
        for w in self.winners:
            spirit = self.spirits.get(w, {})
            winner_names.append(spirit.get("name", w[:8]))

        if winner_names:
            winner_text = f"Winner{'s' if len(winner_names) > 1 else ''}: {', '.join(winner_names)}"
            text = self.font.render(winner_text, True, (255, 215, 100))
            screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 120))

        # Scoreboard
        y = 180
        header = self.font.render("Final Scores:", True, (180, 180, 200))
        screen.blit(header, (SCREEN_WIDTH // 2 - 100, y))
        y += 35

        sorted_scores = sorted(self.scores.items(), key=lambda x: x[1], reverse=True)
        for spirit_id, vp in sorted_scores:
            spirit = self.spirits.get(spirit_id, {})
            name = spirit.get("name", spirit_id[:8])
            is_winner = spirit_id in self.winners
            color = (255, 215, 100) if is_winner else (180, 180, 200)
            text = self.font.render(f"{name}: {vp} VP", True, color)
            screen.blit(text, (SCREEN_WIDTH // 2 - 80, y))
            y += 28

        # Return hint
        hint = self.small_font.render("Press Escape to return to menu", True, (100, 100, 120))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT - 60))
