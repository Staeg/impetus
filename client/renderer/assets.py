"""Load and cache agenda card images from graphics/ folder."""

import os
import sys
import pygame

# Module-level caches: agenda name -> pygame.Surface
agenda_images: dict[str, pygame.Surface] = {}        # 48x48 for map animations
agenda_card_images: dict[str, pygame.Surface] = {}    # 70x70 for card faces

AGENDA_NAMES = ["steal", "bond", "trade", "expand", "change"]

_loaded = False


def load_assets():
    """Load all agenda PNGs, apply transparency, and scale to both sizes.

    Call once after pygame.display is initialized.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True

    # Use _MEIPASS when running from a PyInstaller bundle, else resolve from source tree
    if getattr(sys, '_MEIPASS', None):
        base_dir = os.path.join(sys._MEIPASS, "graphics")
    else:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "graphics")
        base_dir = os.path.normpath(base_dir)

    for name in AGENDA_NAMES:
        filename = f"{name.title()}.png"
        path = os.path.join(base_dir, filename)
        if not os.path.exists(path):
            print(f"[assets] WARNING: Missing agenda image: {path}")
            continue

        raw = pygame.image.load(path)
        alpha_img = raw.convert_alpha()

        agenda_images[name] = pygame.transform.smoothscale(alpha_img, (48, 48))
        agenda_card_images[name] = pygame.transform.smoothscale(alpha_img, (70, 70))

    if len(agenda_images) < len(AGENDA_NAMES):
        print(f"[assets] WARNING: Only loaded {len(agenda_images)}/{len(AGENDA_NAMES)} agenda images")
    else:
        print(f"[assets] Loaded {len(agenda_images)} agenda images")
