"""Load and cache agenda card images from graphics/ folder."""

import os
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

    base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "graphics")
    base_dir = os.path.normpath(base_dir)

    for name in AGENDA_NAMES:
        filename = f"{name.title()}.png"
        path = os.path.join(base_dir, filename)
        if not os.path.exists(path):
            continue

        img = pygame.image.load(path).convert()
        img.set_colorkey((255, 255, 255))

        # Convert to SRCALPHA for proper alpha blending
        alpha_img = img.convert_alpha()

        agenda_images[name] = pygame.transform.smoothscale(alpha_img, (48, 48))
        agenda_card_images[name] = pygame.transform.smoothscale(alpha_img, (70, 70))
