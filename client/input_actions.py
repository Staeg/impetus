"""Semantic input actions for the gameplay scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame


@dataclass(frozen=True)
class GameInputAction:
    """A named gameplay action derived from a raw pygame event."""

    kind: str
    event: pygame.event.Event
    payload: Any = None


def map_game_input(event: pygame.event.Event) -> GameInputAction | None:
    """Map a raw pygame event to a semantic gameplay action."""

    if event.type == pygame.MOUSEWHEEL:
        return GameInputAction("scroll_ui", event, {"x": event.x, "y": event.y})
    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
        return GameInputAction("cancel", event)
    if event.type == pygame.MOUSEMOTION:
        return GameInputAction("hover", event, event.pos)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        return GameInputAction("primary_click", event, event.pos)
    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        return GameInputAction("primary_release", event, event.pos)
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
        return GameInputAction("secondary_click", event, event.pos)
    return None
