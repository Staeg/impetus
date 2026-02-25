"""Settings persistence: load/save settings.json next to the executable (or project root)."""

import os
import sys
import json


def _settings_path() -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        # Two levels up from client/settings.py → project root
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'settings.json')


def load_settings() -> dict:
    path = _settings_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"fullscreen": True}


def save_settings(data: dict) -> None:
    path = _settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
