from __future__ import annotations

from dataclasses import dataclass

import pygame

from client.tutorials.catalog import TUTORIAL_CATALOG
from client.tutorials.types import TutorialCatalogEntry, TutorialScenarioDefinition, TutorialSceneAdapter


@dataclass
class TutorialProgressState:
    campaign_id: str
    scenario_index: int = 0
    step_index: int = 0
    completion_matches: int = 0
    awaiting_acknowledgement: bool = False


class TutorialRuntimeController:
    def __init__(self, app, campaign_id: str, scenario_index: int = 0):
        self.app = app
        self.catalog_entry: TutorialCatalogEntry = TUTORIAL_CATALOG[campaign_id]
        self.progress = TutorialProgressState(campaign_id=campaign_id, scenario_index=scenario_index)
        self.scene: TutorialSceneAdapter | None = None
        self.feedback_message: str | None = None
        self.feedback_timer: float = 0.0
        self.primary_button_rect: pygame.Rect | None = None
        self.secondary_button_rect: pygame.Rect | None = None
        self.chapter_rects: list[tuple[int, pygame.Rect]] = []

    @property
    def scenario(self) -> TutorialScenarioDefinition:
        return self.catalog_entry.entry_scenarios[self.progress.scenario_index]

    @property
    def step(self):
        return self.scenario.steps[self.progress.step_index]

    def attach_scene(self, scene: TutorialSceneAdapter) -> None:
        self.scene = scene
        self.scene.set_tutorial_feedback(self.feedback_message)

    def detach_scene(self) -> None:
        if self.scene:
            self.scene.clear_tutorial_state()
        self.scene = None

    def set_feedback(self, message: str | None, duration: float = 2.5) -> None:
        self.feedback_message = message
        self.feedback_timer = duration if message else 0.0
        if self.scene:
            self.scene.set_tutorial_feedback(message)

    def update(self, dt: float) -> None:
        if self.feedback_timer > 0.0:
            self.feedback_timer = max(0.0, self.feedback_timer - dt)
            if self.feedback_timer == 0.0:
                self.set_feedback(None)

    def can_perform(self, action_kind: str, payload: dict, scene: TutorialSceneAdapter) -> tuple[bool, str | None]:
        step = self.step
        if action_kind not in step.allowed_actions:
            return False, f"Follow the highlighted instruction first: {step.objective_text}"
        if step.input_gate and action_kind not in step.input_gate.allowed_actions:
            return False, f"Follow the highlighted instruction first: {step.objective_text}"
        if step.input_gate and step.input_gate.validator:
            return step.input_gate.validator(action_kind, payload, scene)
        return True, None

    def handle_semantic_event(self, event_type: str, payload: dict) -> None:
        if not self.scene or self.progress.awaiting_acknowledgement:
            return
        rule = self.step.completion_rule
        if rule is None or event_type not in rule.event_types:
            return
        event = {"type": event_type, **payload}
        if rule.predicate and not rule.predicate(event, self.scene):
            return
        self.progress.completion_matches += 1
        if self.progress.completion_matches >= rule.min_matches:
            self.progress.awaiting_acknowledgement = True

    def handle_click(self, pos: tuple[int, int]) -> bool:
        if self.primary_button_rect and self.primary_button_rect.collidepoint(pos):
            self.advance()
            return True
        if self.secondary_button_rect and self.secondary_button_rect.collidepoint(pos):
            if self.progress.campaign_id == "basics" and self.progress.scenario_index == len(self.catalog_entry.entry_scenarios) - 1:
                self.app.start_tutorial("advanced")
            else:
                self.app.exit_tutorial_to_menu()
            return True
        for index, rect in self.chapter_rects:
            if rect.collidepoint(pos):
                self.app.start_tutorial(self.progress.campaign_id, scenario_index=index)
                return True
        return False

    def advance(self) -> None:
        if not self.progress.awaiting_acknowledgement:
            return
        self.progress.awaiting_acknowledgement = False
        self.progress.completion_matches = 0
        if self.progress.step_index + 1 < len(self.scenario.steps):
            self.progress.step_index += 1
            return
        if self.progress.scenario_index + 1 < len(self.catalog_entry.entry_scenarios):
            self.app.start_tutorial(self.progress.campaign_id, scenario_index=self.progress.scenario_index + 1)
            return
        self.app.exit_tutorial_to_menu()

    def render_overlay(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        if screen.get_width() < 32 or screen.get_height() < 32:
            return
        step = self.step
        if self.scene:
            draw_highlights = getattr(self.scene, "draw_tutorial_highlights", None)
            if callable(draw_highlights):
                draw_highlights(screen, step.highlights)
            layout = getattr(self.scene, "get_tutorial_overlay_layout", None)
            overlay_layout = layout() if callable(layout) else {}
        else:
            overlay_layout = {}
        card_rect = overlay_layout.get("message_rect", pygame.Rect(18, 108, 430, 136))
        inner_width = card_rect.w - 28
        objective_lines = self._wrap_lines(small_font, step.objective_text, inner_width)
        help_lines = self._wrap_lines(small_font, step.help_text, inner_width)
        content_height = (
            16
            + font.get_linesize()
            + 10
            + len(objective_lines[:2]) * small_font.get_linesize()
            + 10
            + len(help_lines[:3]) * small_font.get_linesize()
            + 14
        )
        if card_rect.h < content_height:
            card_rect = card_rect.copy()
            card_rect.y -= content_height - card_rect.h
            card_rect.h = content_height
        pygame.draw.rect(screen, (22, 27, 34), card_rect, border_radius=12)
        pygame.draw.rect(screen, (237, 197, 104), card_rect, 2, border_radius=12)
        title = font.render(f"{self.catalog_entry.title}: {self.scenario.title}", True, (245, 236, 214))
        screen.blit(title, (card_rect.x + 14, card_rect.y + 12))
        objective_y = card_rect.y + 42
        self._draw_wrapped(
            screen,
            small_font,
            step.objective_text,
            pygame.Rect(card_rect.x + 14, objective_y, card_rect.w - 28, small_font.get_linesize() * 2 + 2),
        )
        help_y = objective_y + len(objective_lines[:2]) * small_font.get_linesize() + 8
        self._draw_wrapped(
            screen,
            small_font,
            step.help_text,
            pygame.Rect(card_rect.x + 14, help_y, card_rect.w - 28, small_font.get_linesize() * 3 + 2),
            color=(187, 193, 205),
        )

        if self.feedback_message:
            fb_rect = pygame.Rect(card_rect.x, card_rect.bottom + 8, min(430, card_rect.w), 34)
            pygame.draw.rect(screen, (65, 36, 26), fb_rect, border_radius=10)
            fb = small_font.render(self.feedback_message, True, (255, 226, 198))
            screen.blit(fb, (fb_rect.x + 10, fb_rect.y + 8))

        self.primary_button_rect = None
        self.secondary_button_rect = None
        self.chapter_rects = []
        if self.progress.awaiting_acknowledgement:
            primary_label = "Continue" if self.progress.scenario_index + 1 < len(self.catalog_entry.entry_scenarios) else "Finish"
            button_y = card_rect.bottom + 12 + (42 if self.feedback_message else 0)
            self.primary_button_rect = pygame.Rect(card_rect.x, button_y, 156, 40)
            pygame.draw.rect(screen, (70, 120, 80), self.primary_button_rect, border_radius=8)
            self._draw_center(screen, small_font, primary_label, self.primary_button_rect)
            self.secondary_button_rect = pygame.Rect(self.primary_button_rect.right + 10, self.primary_button_rect.y, 170, 40)
            secondary_label = "Advanced Mechanics" if self.progress.campaign_id == "basics" and self.progress.scenario_index == len(self.catalog_entry.entry_scenarios) - 1 else "Return to Menu"
            pygame.draw.rect(screen, (58, 68, 89), self.secondary_button_rect, border_radius=8)
            self._draw_center(screen, small_font, secondary_label, self.secondary_button_rect)

        if self.progress.campaign_id == "advanced":
            chip_y = screen.get_height() - 44
            chip_x = 18
            for index, scenario in enumerate(self.catalog_entry.entry_scenarios):
                rect = pygame.Rect(chip_x, chip_y, max(120, small_font.size(scenario.title)[0] + 20), 28)
                color = (80, 92, 120) if index != self.progress.scenario_index else (132, 109, 54)
                pygame.draw.rect(screen, color, rect, border_radius=8)
                self._draw_center(screen, small_font, scenario.title, rect)
                self.chapter_rects.append((index, rect))
                chip_x = rect.right + 8

    def _draw_center(self, screen: pygame.Surface, font: pygame.font.Font, text: str, rect: pygame.Rect) -> None:
        surf = font.render(text, True, (245, 241, 230))
        screen.blit(surf, surf.get_rect(center=rect.center))

    def _draw_wrapped(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        rect: pygame.Rect,
        color: tuple[int, int, int] = (224, 224, 230),
    ) -> None:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if font.size(test)[0] <= rect.width:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        y = rect.y
        for line in lines[:3]:
            surf = font.render(line, True, color)
            screen.blit(surf, (rect.x, y))
            y += font.get_linesize()

    def _wrap_lines(self, font: pygame.font.Font, text: str, width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if font.size(test)[0] <= width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
