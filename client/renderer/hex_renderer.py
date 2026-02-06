"""Hex grid drawing, territory coloring, borders, idols."""

import pygame
import math
from shared.hex_utils import axial_to_pixel, hex_vertices
from shared.constants import (
    FACTION_COLORS, NEUTRAL_COLOR, HEX_SIZE, IdolType,
)


IDOL_COLORS = {
    IdolType.BATTLE: (255, 50, 50),
    IdolType.AFFLUENCE: (255, 215, 0),
    IdolType.SPREAD: (50, 200, 50),
}

IDOL_SYMBOLS = {
    IdolType.BATTLE: "B",
    IdolType.AFFLUENCE: "A",
    IdolType.SPREAD: "S",
}


class HexRenderer:
    """Draws the hex grid and its contents."""

    def __init__(self):
        self.hex_size = HEX_SIZE
        self._font = None

    def _get_font(self, size=14):
        if self._font is None:
            self._font = pygame.font.SysFont("consolas", size)
        return self._font

    def draw_hex_grid(self, surface: pygame.Surface, hex_ownership: dict,
                      camera, screen_w: int, screen_h: int,
                      idols: list = None, wars: list = None,
                      selected_hex=None, highlight_hexes=None,
                      spirit_index_map: dict = None):
        """Draw the complete hex map.

        Args:
            hex_ownership: dict of (q,r) -> faction_id or None
            camera: InputHandler with camera state
            idols: list of Idol objects
            wars: list of WarState objects
            selected_hex: (q, r) tuple to highlight
            highlight_hexes: set of (q, r) tuples to highlight (e.g., valid targets)
            spirit_index_map: dict of spirit_id -> player index for idol positioning
        """
        font = self._get_font()

        # Collect battleground hexes for highlighting
        battleground_hexes = set()
        if wars:
            for war in wars:
                if war.battleground:
                    bg = war.battleground
                    battleground_hexes.add((bg[0].q, bg[0].r))
                    battleground_hexes.add((bg[1].q, bg[1].r))

        for (q, r), owner in hex_ownership.items():
            # Get screen coordinates
            wx, wy = axial_to_pixel(q, r, self.hex_size)
            sx, sy = camera.world_to_screen(wx, wy, screen_w, screen_h)

            # Skip off-screen hexes
            margin = self.hex_size * 2 * camera.zoom
            if sx < -margin or sx > screen_w + margin or sy < -margin or sy > screen_h + margin:
                continue

            # Determine color
            if owner and owner in FACTION_COLORS:
                color = FACTION_COLORS[owner]
            else:
                color = NEUTRAL_COLOR

            # Calculate vertices in screen space
            verts = hex_vertices(q, r, self.hex_size)
            screen_verts = [
                camera.world_to_screen(vx, vy, screen_w, screen_h)
                for vx, vy in verts
            ]

            # Draw filled hex
            pygame.draw.polygon(surface, color, screen_verts)

            # Draw border
            border_color = (40, 40, 40)
            if (q, r) == selected_hex:
                border_color = (255, 255, 255)
                pygame.draw.polygon(surface, border_color, screen_verts, 3)
            elif highlight_hexes and (q, r) in highlight_hexes:
                border_color = (200, 200, 255)
                pygame.draw.polygon(surface, border_color, screen_verts, 2)
            elif (q, r) in battleground_hexes:
                border_color = (255, 100, 100)
                pygame.draw.polygon(surface, border_color, screen_verts, 3)
            else:
                pygame.draw.polygon(surface, border_color, screen_verts, 1)

        # Draw idols
        if idols:
            self._draw_idols(surface, idols, camera, screen_w, screen_h,
                             spirit_index_map or {})

    def _draw_idols(self, surface, idols, camera, screen_w, screen_h,
                    spirit_index_map):
        """Draw idol icons on their hexes, offset radially by owner."""
        font = self._get_font(12)
        dist = self.hex_size / 2  # halfway to hex vertex

        for idol in idols:
            wx, wy = axial_to_pixel(idol.position.q, idol.position.r, self.hex_size)
            # Radial offset based on player index
            player_idx = spirit_index_map.get(getattr(idol, 'owner_spirit', None), 0)
            angle = math.radians(-90 + player_idx * 60)
            offset_x = math.cos(angle) * dist
            offset_y = math.sin(angle) * dist
            ix, iy = camera.world_to_screen(wx + offset_x, wy + offset_y,
                                            screen_w, screen_h)
            idol_color = IDOL_COLORS.get(idol.type, (255, 255, 255))
            pygame.draw.circle(surface, idol_color, (ix, iy), max(4, int(5 * camera.zoom)))
            # Draw letter
            symbol = IDOL_SYMBOLS.get(idol.type, "?")
            text = font.render(symbol, True, (0, 0, 0))
            surface.blit(text, (ix - text.get_width() // 2, iy - text.get_height() // 2))

    def get_hex_at_screen(self, sx: int, sy: int, camera, screen_w: int, screen_h: int,
                          valid_hexes: set = None) -> tuple[int, int] | None:
        """Return the hex coordinate at screen position, or None."""
        q, r = camera.screen_to_hex(sx, sy, screen_w, screen_h, self.hex_size)
        if valid_hexes is not None:
            if (q, r) in valid_hexes:
                return (q, r)
            return None
        return (q, r)
