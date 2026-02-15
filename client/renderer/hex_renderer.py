"""Hex grid drawing, territory coloring, borders, idols."""

import pygame
import math
from shared.hex_utils import axial_to_pixel, hex_vertices, hex_neighbors
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
                      spirit_index_map: dict = None,
                      preview_idol: tuple = None):
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
            margin = self.hex_size * 2
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

        # Draw war arrows
        if wars:
            self._draw_war_arrows(surface, wars, hex_ownership, camera,
                                  screen_w, screen_h)

        # Draw idols
        if idols:
            self._draw_idols(surface, idols, camera, screen_w, screen_h,
                             spirit_index_map or {})

        # Draw preview idol (semi-transparent)
        if preview_idol:
            self._draw_preview_idol(surface, preview_idol, camera,
                                    screen_w, screen_h)

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
            pygame.draw.circle(surface, idol_color, (ix, iy), 5)
            # Draw letter
            symbol = IDOL_SYMBOLS.get(idol.type, "?")
            text = font.render(symbol, True, (0, 0, 0))
            surface.blit(text, (ix - text.get_width() // 2, iy - text.get_height() // 2))

    def get_idol_at_screen(self, mx, my, idols, camera, screen_w, screen_h,
                           spirit_index_map):
        """Return the idol object at screen position (mx, my), or None."""
        dist = self.hex_size / 2
        hit_radius = 8  # slightly larger than drawn radius (5) for easier targeting
        best = None
        best_dist_sq = hit_radius * hit_radius
        for idol in idols:
            wx, wy = axial_to_pixel(idol.position.q, idol.position.r, self.hex_size)
            player_idx = spirit_index_map.get(getattr(idol, 'owner_spirit', None), 0)
            angle = math.radians(-90 + player_idx * 60)
            offset_x = math.cos(angle) * dist
            offset_y = math.sin(angle) * dist
            ix, iy = camera.world_to_screen(wx + offset_x, wy + offset_y,
                                            screen_w, screen_h)
            dx = mx - ix
            dy = my - iy
            d_sq = dx * dx + dy * dy
            if d_sq < best_dist_sq:
                best_dist_sq = d_sq
                best = idol
        return best

    def _draw_preview_idol(self, surface, preview_idol, camera, screen_w, screen_h):
        """Draw a semi-transparent preview idol at hex center.

        preview_idol: (idol_type_str, q, r) e.g. ("battle", 0, 1)
        """
        idol_type_str, pq, pr = preview_idol
        try:
            idol_type = IdolType(idol_type_str)
        except ValueError:
            return
        wx, wy = axial_to_pixel(pq, pr, self.hex_size)
        sx, sy = camera.world_to_screen(wx, wy, screen_w, screen_h)
        base_color = IDOL_COLORS.get(idol_type, (255, 255, 255))
        # Draw semi-transparent circle
        alpha_surf = pygame.Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(alpha_surf, (*base_color, 100), (10, 10), 8)
        surface.blit(alpha_surf, (sx - 10, sy - 10))
        # Draw letter
        font = self._get_font(12)
        symbol = IDOL_SYMBOLS.get(idol_type, "?")
        text = font.render(symbol, True, (*base_color, 160))
        surface.blit(text, (sx - text.get_width() // 2, sy - text.get_height() // 2))

    def _draw_war_arrows(self, surface, wars, hex_ownership, camera,
                         screen_w, screen_h):
        """Draw bidirectional arrows for all wars."""
        for war in wars:
            if war.is_ripe and war.battleground:
                # Bright red arrow on the battleground border only
                h1 = (war.battleground[0].q, war.battleground[0].r)
                h2 = (war.battleground[1].q, war.battleground[1].r)
                self._draw_hex_arrow(surface, h1, h2, (255, 50, 50),
                                     camera, screen_w, screen_h,
                                     width=3, head_size=8)
            else:
                # Faint red arrows between all neighboring border hexes
                pairs = self._get_border_pairs(hex_ownership,
                                               war.faction_a, war.faction_b)
                for h1, h2 in pairs:
                    self._draw_hex_arrow(surface, h1, h2, (180, 60, 60),
                                         camera, screen_w, screen_h,
                                         width=1, head_size=5)

    def _get_border_pairs(self, hex_ownership, faction_a, faction_b):
        """Find all adjacent hex pairs where one is faction_a and other is faction_b."""
        seen = set()
        pairs = []
        for (q, r), owner in hex_ownership.items():
            if owner == faction_a:
                for nq, nr in hex_neighbors(q, r):
                    if hex_ownership.get((nq, nr)) == faction_b:
                        key = (min((q, r), (nq, nr)), max((q, r), (nq, nr)))
                        if key not in seen:
                            seen.add(key)
                            pairs.append(((q, r), (nq, nr)))
        return pairs

    def _draw_hex_arrow(self, surface, h1, h2, color, camera, screen_w, screen_h,
                        width=2, head_size=6, unidirectional=False):
        """Draw an arrow between two hex centers. Bidirectional unless unidirectional=True."""
        w1x, w1y = axial_to_pixel(h1[0], h1[1], self.hex_size)
        w2x, w2y = axial_to_pixel(h2[0], h2[1], self.hex_size)
        s1 = camera.world_to_screen(w1x, w1y, screen_w, screen_h)
        s2 = camera.world_to_screen(w2x, w2y, screen_w, screen_h)

        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        ux = dx / length
        uy = dy / length

        # Shorten line to middle portion (30% inward from each end)
        p1 = (s1[0] + dx * 0.3, s1[1] + dy * 0.3)
        p2 = (s2[0] - dx * 0.3, s2[1] - dy * 0.3)

        scaled_head = head_size
        scaled_width = width

        pygame.draw.line(surface, color,
                         (int(p1[0]), int(p1[1])),
                         (int(p2[0]), int(p2[1])), scaled_width)

        # Perpendicular vector
        px, py = -uy, ux

        # Arrowhead at p2 (pointing towards h2)
        tip = p2
        left = (tip[0] - ux * scaled_head + px * scaled_head * 0.5,
                tip[1] - uy * scaled_head + py * scaled_head * 0.5)
        right = (tip[0] - ux * scaled_head - px * scaled_head * 0.5,
                 tip[1] - uy * scaled_head - py * scaled_head * 0.5)
        pygame.draw.polygon(surface, color, [tip, left, right])

        # Arrowhead at p1 (pointing towards h1) — skip for unidirectional arrows
        if not unidirectional:
            tip = p1
            left = (tip[0] + ux * scaled_head + px * scaled_head * 0.5,
                    tip[1] + uy * scaled_head + py * scaled_head * 0.5)
            right = (tip[0] + ux * scaled_head - px * scaled_head * 0.5,
                     tip[1] + uy * scaled_head - py * scaled_head * 0.5)
            pygame.draw.polygon(surface, color, [tip, left, right])

    def get_hex_at_screen(self, sx: int, sy: int, camera, screen_w: int, screen_h: int,
                          valid_hexes: set = None) -> tuple[int, int] | None:
        """Return the hex coordinate at screen position, or None."""
        q, r = camera.screen_to_hex(sx, sy, screen_w, screen_h, self.hex_size)
        if valid_hexes is not None:
            if (q, r) in valid_hexes:
                return (q, r)
            return None
        return (q, r)
