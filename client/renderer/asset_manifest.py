"""Stable manifest keys for client-rendered assets."""

from __future__ import annotations

import os
import sys


AGENDA_GRAPHIC_KEYS = {
    "steal": "Steal.png",
    "trade": "Trade.png",
    "expand": "Expand.png",
    "change": "Change.png",
    "battle_idol": "Battle.png",
    "affluence_idol": "Affluence.png",
    "sprawl_idol": "Sprawl.png",
}


def graphics_root() -> str:
    """Resolve the graphics root for source and PyInstaller builds."""

    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "graphics")
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "graphics")
    )


def resolve_graphic_path(asset_key: str) -> str:
    """Resolve a stable manifest key to an on-disk graphics path."""

    try:
        filename = AGENDA_GRAPHIC_KEYS[asset_key]
    except KeyError as exc:
        raise KeyError(f"Unknown graphics asset key: {asset_key}") from exc
    return os.path.join(graphics_root(), filename)


def validate_graphics_manifest() -> list[str]:
    """Return any missing manifest-backed asset paths."""

    missing: list[str] = []
    for asset_key in AGENDA_GRAPHIC_KEYS:
        path = resolve_graphic_path(asset_key)
        if not os.path.exists(path):
            missing.append(path)
    return missing
