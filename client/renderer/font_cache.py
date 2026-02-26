"""Shared font factory with module-level cache."""

from __future__ import annotations
import sys
import pygame

_cache: dict[tuple[str, int, bool], pygame.font.Font] = {}

# In WASM the game canvas is not CSS-scaled (pygame.SCALED is disabled), so
# fonts appear small on typical browser viewports.  Apply a multiplier so text
# is comfortably readable without any CSS transform tricks.
_WASM_FONT_SCALE = 1.5 if sys.platform == "emscripten" else 1.0


def get_font(size: int, bold: bool = False, name: str = "consolas") -> pygame.font.Font:
    key = (name, size, bold)
    if key not in _cache:
        scaled = round(size * _WASM_FONT_SCALE)
        _cache[key] = pygame.font.SysFont(name, scaled, bold=bold)
    return _cache[key]
