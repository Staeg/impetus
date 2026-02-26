"""Shared font factory with module-level cache."""

import pygame

_cache: dict[tuple[str, int, bool], pygame.font.Font] = {}


def get_font(size: int, bold: bool = False, name: str = "consolas") -> pygame.font.Font:
    key = (name, size, bold)
    if key not in _cache:
        _cache[key] = pygame.font.SysFont(name, size, bold=bold)
    return _cache[key]
