"""Hex grid drawing, territory coloring, borders, idols."""

import pygame
import math
from shared.hex_utils import axial_to_pixel, hex_vertices, hex_neighbors
from shared.constants import (
    FACTION_COLORS, NEUTRAL_COLOR, HEX_SIZE, IdolType,
)
from client.renderer.font_cache import get_font


# One shape per spirit index (0-4 unique, 5+ wraps).
_SPIRIT_SHAPES = ["triangle", "circle", "diamond", "star", "square"]

# Scale each shape so all five read the same visual weight at the same radius.
# Circles fill their whole circumcircle; triangles/stars are sparse.
_SHAPE_SCALE = {
    "circle":   0.75,
    "triangle": 1.05,
    "diamond":  1.00,
    "star":     0.80,
    "square":   0.90,
}


def draw_spirit_symbol(surface, cx, cy, screen_radius, spirit_idx,
                       color=(192, 192, 192)):
    """Draw a single spirit symbol at (cx, cy).

    screen_radius drives the size: symbol is drawn at screen_radius/3 * shape_scale.
    Public — importable by ui_renderer and other modules.
    """
    shape = _SPIRIT_SHAPES[spirit_idx % len(_SPIRIT_SHAPES)]
    r = screen_radius / 3 * _SHAPE_SCALE[shape]
    _draw_shape(surface, shape, cx, cy, r, color)


def _draw_shape(surface, shape, cx, cy, r, color):
    """Draw a filled shape centred at (cx, cy) with circumradius r."""
    cx, cy = int(cx), int(cy)
    r = max(r, 1)
    if shape == "circle":
        pygame.draw.circle(surface, color, (cx, cy), int(r))
    elif shape == "triangle":
        pts = [
            (cx,              cy - r),
            (cx - r * 0.866,  cy + r * 0.5),
            (cx + r * 0.866,  cy + r * 0.5),
        ]
        pygame.draw.polygon(surface, color, [(int(x), int(y)) for x, y in pts])
    elif shape == "diamond":
        pts = [
            (cx,             cy - r),
            (cx + r * 0.65,  cy),
            (cx,             cy + r),
            (cx - r * 0.65,  cy),
        ]
        pygame.draw.polygon(surface, color, [(int(x), int(y)) for x, y in pts])
    elif shape == "star":
        pts = []
        inner = r * 0.4
        for i in range(10):
            angle = math.radians(-90 + i * 36)
            ri = r if i % 2 == 0 else inner
            pts.append((int(cx + ri * math.cos(angle)),
                         int(cy + ri * math.sin(angle))))
        pygame.draw.polygon(surface, color, pts)
    elif shape == "square":
        s = int(r * 0.71)  # r/√2: half-side of square inscribed in circumcircle
        pygame.draw.rect(surface, color, (cx - s, cy - s, s * 2, s * 2))

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
            self._font = get_font(size)
        return self._font

    def draw_hex_grid(self, surface: pygame.Surface, hex_ownership: dict,
                      camera, screen_w: int, screen_h: int,
                      idols: list = None, wars: list = None,
                      selected_hex=None, selected_hexes: set = None,
                      highlight_hexes=None,
                      spirit_index_map: dict = None,
                      preview_idol: tuple = None,
                      faction_spirit_index: dict = None,
                      faction_worship: dict = None,
                      highlight_spirit_id: str = None):
        """Draw the complete hex map.

        Args:
            hex_ownership: dict of (q,r) -> faction_id or None
            camera: InputHandler with camera state
            idols: list of Idol objects
            wars: list of WarState objects
            selected_hex: (q, r) tuple to highlight
            highlight_hexes: set of (q, r) tuples to highlight (e.g., valid targets)
            spirit_index_map: dict of spirit_id -> player index for idol positioning
            faction_spirit_index: dict of faction_id -> spirit index for guidance symbols
            faction_worship: dict of faction_id -> spirit index for worship symbols near idols
        """
        font = self._get_font()

        # Overlay surface for semi-transparent hex tints (collected, then blitted once)
        overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)

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

            # Draw guidance symbol (black) at hex centre for guided factions
            if faction_spirit_index and owner:
                sidx = faction_spirit_index.get(owner)
                if sidx is not None:
                    sr = math.dist(screen_verts[0], (sx, sy))
                    draw_spirit_symbol(surface, sx, sy, sr, sidx, (0, 0, 0))

            # Draw border + queue overlay tint
            border_color = (40, 40, 40)
            border_width = 1
            if (q, r) == selected_hex:
                border_color = (255, 255, 255)
                border_width = 4
                pygame.draw.polygon(overlay, (255, 255, 255, 55), screen_verts)
            elif selected_hexes and (q, r) in selected_hexes:
                border_color = (255, 200, 50)
                border_width = 4
                pygame.draw.polygon(overlay, (255, 200, 50, 55), screen_verts)
            elif highlight_hexes and (q, r) in highlight_hexes:
                border_color = (0, 210, 255)
                border_width = 3
                pygame.draw.polygon(overlay, (0, 210, 255, 45), screen_verts)
            pygame.draw.polygon(surface, border_color, screen_verts, border_width)

        # Apply hex tint overlays
        surface.blit(overlay, (0, 0))

        # Draw war arrows
        if wars:
            self._draw_war_arrows(surface, wars, hex_ownership, camera,
                                  screen_w, screen_h)

        # Draw idols
        if idols:
            self._draw_idols(surface, idols, camera, screen_w, screen_h,
                             spirit_index_map or {},
                             hex_ownership=hex_ownership,
                             faction_worship=faction_worship,
                             highlight_spirit_id=highlight_spirit_id)

        # Draw preview idol (semi-transparent)
        if preview_idol:
            self._draw_preview_idol(surface, preview_idol, camera,
                                    screen_w, screen_h)

    def _draw_idols(self, surface, idols, camera, screen_w, screen_h,
                    spirit_index_map, hex_ownership=None, faction_worship=None,
                    highlight_spirit_id=None):
        """Draw idol icons on their hexes, offset radially by owner."""
        font = self._get_font(12)
        dist = self.hex_size / 2  # halfway to hex vertex

        for idol in idols:
            wx, wy = axial_to_pixel(idol.position.q, idol.position.r, self.hex_size)
            # Radial offset based on player index
            owner_spirit = getattr(idol, 'owner_spirit', None)
            player_idx = spirit_index_map.get(owner_spirit, 0)
            angle = math.radians(-90 + player_idx * 60)
            offset_x = math.cos(angle) * dist
            offset_y = math.sin(angle) * dist
            ix, iy = camera.world_to_screen(wx + offset_x, wy + offset_y,
                                            screen_w, screen_h)

            # Draw worship symbol (silver) behind the idol dot
            if hex_ownership is not None and faction_worship:
                owner_fid = hex_ownership.get((idol.position.q, idol.position.r))
                if owner_fid:
                    worship_sidx = faction_worship.get(owner_fid)
                    if worship_sidx is not None:
                        # Use distance from hex centre to idol as proxy for hex screen radius
                        csx, csy = camera.world_to_screen(wx, wy, screen_w, screen_h)
                        sr = math.dist((ix, iy), (csx, csy)) * 2
                        draw_spirit_symbol(surface, ix, iy, sr, worship_sidx,
                                           (192, 192, 192))

            idol_color = IDOL_COLORS.get(idol.type, (255, 255, 255))
            pygame.draw.circle(surface, idol_color, (ix, iy), 5)
            # Black outline ring for idols belonging to the highlighted spirit
            if owner_spirit == highlight_spirit_id:
                pygame.draw.circle(surface, (0, 0, 0), (ix, iy), 7, 2)
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

    def draw_war_glow_arrows(self, surface, wars, hex_ownership, camera,
                             screen_w, screen_h, pulse: float = 1.0):
        """Draw extra-bright, thick war arrows for tutorial highlighting."""
        r = 255
        g = int(80 + 120 * pulse)
        b = 80
        bright = (r, g, b)
        for war in wars:
            if war.is_ripe and war.battleground:
                h1 = (war.battleground[0].q, war.battleground[0].r)
                h2 = (war.battleground[1].q, war.battleground[1].r)
                self._draw_hex_arrow(surface, h1, h2, bright,
                                     camera, screen_w, screen_h,
                                     width=5, head_size=12)
            else:
                pairs = self._get_border_pairs(hex_ownership, war.faction_a, war.faction_b)
                for h1, h2 in pairs:
                    self._draw_hex_arrow(surface, h1, h2, bright,
                                         camera, screen_w, screen_h,
                                         width=3, head_size=8)

    def get_hex_at_screen(self, sx: int, sy: int, camera, screen_w: int, screen_h: int,
                          valid_hexes: set = None) -> tuple[int, int] | None:
        """Return the hex coordinate at screen position, or None."""
        q, r = camera.screen_to_hex(sx, sy, screen_w, screen_h, self.hex_size)
        if valid_hexes is not None:
            if (q, r) in valid_hexes:
                return (q, r)
            return None
        return (q, r)
