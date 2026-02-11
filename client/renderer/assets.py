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

    # Create expand_failed composite: expand image with red X overlay
    if "expand" in agenda_images:
        expand_fail = agenda_images["expand"].copy()
        size = expand_fail.get_width()
        margin = 6
        pygame.draw.line(expand_fail, (220, 30, 30), (margin, margin), (size - margin, size - margin), 4)
        pygame.draw.line(expand_fail, (220, 30, 30), (size - margin, margin), (margin, size - margin), 4)
        agenda_images["expand_failed"] = expand_fail

    # Create change_{modifier} composites: change icon + smaller modifier icon to the right
    if "change" in agenda_images:
        change_base = agenda_images["change"]
        for mod_name in ["trade", "bond", "steal", "expand"]:
            if mod_name in agenda_images:
                small_size = 24
                gap = 4
                total_w = 48 + gap + small_size
                composite = pygame.Surface((total_w, 48), pygame.SRCALPHA)
                composite.blit(change_base, (0, 0))
                small_icon = pygame.transform.smoothscale(agenda_images[mod_name], (small_size, small_size))
                composite.blit(small_icon, (48 + gap, (48 - small_size) // 2))
                agenda_images[f"change_{mod_name}"] = composite

    if len(agenda_images) < len(AGENDA_NAMES):
        print(f"[assets] WARNING: Only loaded {len(agenda_images)}/{len(AGENDA_NAMES)} agenda images")
    else:
        print(f"[assets] Loaded {len(agenda_images)} agenda images (+ composites)")
