"""HUD, cards, faction info panels, phase indicators, event log."""

from __future__ import annotations
import math
import pygame
from shared.constants import (
    Phase, AgendaType, IdolType, FACTION_COLORS, FACTION_DISPLAY_NAMES,
    FACTION_NAMES,
)
from client.faction_names import faction_full_name
from client.renderer.assets import agenda_ribbon_icons
from client.renderer.hex_renderer import draw_spirit_symbol
from client.renderer.font_cache import get_font
import client.theme as theme


def _wrap_text(text: str, font: "pygame.font.Font", max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
        current_line = words[0]
        for word in words[1:]:
            test_line = current_line + ' ' + word
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
    return lines


def draw_dotted_underline(surface: "pygame.Surface", x: int, y: int, width: int,
                          color: tuple = (120, 120, 140), dot_len: int = 2, gap_len: int = 3):
    """Draw a faint dotted underline."""
    cx = x
    end_x = x + width
    while cx < end_x:
        seg_end = min(cx + dot_len, end_x)
        pygame.draw.line(surface, color, (cx, y), (seg_end, y), 1)
        cx += dot_len + gap_len


def _render_rich_line_with_keywords(surface, font, line, x, y,
                                    keywords: list[str],
                                    normal_color, keyword_color):
    """Render a line with keyword highlighting and dotted underlines."""
    if not keywords:
        surf = font.render(line, True, normal_color)
        surface.blit(surf, (x, y))
        return

    # Find all keyword occurrences, then keep non-overlapping occurrences.
    occurrences = []
    for kw in keywords:
        start = 0
        while True:
            pos = line.find(kw, start)
            if pos < 0:
                break
            occurrences.append((pos, pos + len(kw), kw))
            start = pos + len(kw)

    if not occurrences:
        surf = font.render(line, True, normal_color)
        surface.blit(surf, (x, y))
        return

    occurrences.sort(key=lambda o: o[0])
    filtered = []
    last_end = 0
    for seg_start, seg_end, kw in occurrences:
        if seg_start >= last_end:
            filtered.append((seg_start, seg_end, kw))
            last_end = seg_end

    cursor_x = x
    pos = 0
    line_h = font.get_linesize()
    for seg_start, seg_end, _ in filtered:
        if seg_start > pos:
            normal_text = line[pos:seg_start]
            surf = font.render(normal_text, True, normal_color)
            surface.blit(surf, (cursor_x, y))
            cursor_x += surf.get_width()

        kw_text = line[seg_start:seg_end]
        surf = font.render(kw_text, True, keyword_color)
        surface.blit(surf, (cursor_x, y))

        underline_y = y + line_h - 2
        ux = cursor_x
        ux_end = cursor_x + surf.get_width()
        while ux < ux_end:
            dot_end = min(ux + 2, ux_end)
            pygame.draw.line(surface, keyword_color, (ux, underline_y), (dot_end, underline_y), 1)
            ux += 5

        cursor_x += surf.get_width()
        pos = seg_end

    if pos < len(line):
        normal_text = line[pos:]
        surf = font.render(normal_text, True, normal_color)
        surface.blit(surf, (cursor_x, y))


def render_rich_lines(surface: "pygame.Surface", font: "pygame.font.Font",
                      lines: list[str], x: int, y: int,
                      keywords: list[str], hovered_keyword: str | None,
                      normal_color: tuple, keyword_color: tuple,
                      hovered_keyword_color: tuple) -> "dict[str, list[pygame.Rect]]":
    """Render wrapped lines with keyword underline styling; return keyword rects."""
    keyword_rects: dict[str, list[pygame.Rect]] = {k: [] for k in keywords}
    line_h = font.get_linesize()

    for line_idx, line in enumerate(lines):
        cy = y + line_idx * line_h
        if not keywords:
            surface.blit(font.render(line, True, normal_color), (x, cy))
            continue

        occurrences = []
        for kw in keywords:
            start = 0
            while True:
                pos = line.find(kw, start)
                if pos < 0:
                    break
                occurrences.append((pos, pos + len(kw), kw))
                start = pos + len(kw)

        if not occurrences:
            surface.blit(font.render(line, True, normal_color), (x, cy))
            continue

        occurrences.sort(key=lambda o: o[0])
        filtered = []
        last_end = 0
        for seg_start, seg_end, kw in occurrences:
            if seg_start >= last_end:
                filtered.append((seg_start, seg_end, kw))
                last_end = seg_end

        cursor_x = x
        pos = 0
        for seg_start, seg_end, kw in filtered:
            if seg_start > pos:
                normal_text = line[pos:seg_start]
                surf = font.render(normal_text, True, normal_color)
                surface.blit(surf, (cursor_x, cy))
                cursor_x += surf.get_width()

            kw_text = line[seg_start:seg_end]
            color = hovered_keyword_color if kw == hovered_keyword else keyword_color
            surf = font.render(kw_text, True, color)
            surface.blit(surf, (cursor_x, cy))
            kw_rect = pygame.Rect(cursor_x, cy, surf.get_width(), line_h)
            keyword_rects[kw].append(kw_rect)

            underline_y = cy + line_h - 2
            ux = cursor_x
            ux_end = cursor_x + surf.get_width()
            while ux < ux_end:
                dot_end = min(ux + 2, ux_end)
                pygame.draw.line(surface, color, (ux, underline_y), (dot_end, underline_y), 1)
                ux += 5

            cursor_x += surf.get_width()
            pos = seg_end

        if pos < len(line):
            tail = line[pos:]
            surf = font.render(tail, True, normal_color)
            surface.blit(surf, (cursor_x, cy))

    return keyword_rects


def draw_multiline_tooltip(surface: "pygame.Surface", font: "pygame.font.Font",
                           text: str, anchor_x: int, anchor_y: int,
                           max_width: int = 350, below: bool = False):
    """Draw a multi-line tooltip box at the given anchor position.

    anchor_x/anchor_y: the center-x and top (if below) or bottom (if above) of the tooltip.
    """
    lines = _wrap_text(text, font, max_width)
    if not lines:
        return
    line_h = font.get_linesize()
    rendered = [font.render(line, True, theme.TEXT_TOOLTIP) for line in lines]
    content_w = max(s.get_width() for s in rendered)
    tip_w = content_w + 16
    tip_h = len(lines) * line_h + 12

    from client.renderer.popup_manager import _compute_best_position
    tip_x, tip_y = _compute_best_position(
        anchor_x, anchor_y, tip_w, tip_h,
        surface.get_width(), surface.get_height(),
        prefer_below=below,
    )

    tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
    pygame.draw.rect(surface, theme.BG_TOOLTIP, tip_rect, border_radius=4)
    pygame.draw.rect(surface, theme.BORDER_TOOLTIP, tip_rect, 1, border_radius=4)
    for i, surf in enumerate(rendered):
        surface.blit(surf, (tip_x + 8, tip_y + 6 + i * line_h))


def build_agenda_tooltip(agenda_type: str, modifiers: dict,
                         is_spoils: bool = False) -> str:
    """Build full rules-text tooltip for an agenda type with modifiers applied."""
    steal_mod = modifiers.get("steal", 0)
    trade_mod = modifiers.get("trade", 0)
    expand_mod = modifiers.get("expand", 0)

    if is_spoils and agenda_type == "expand":
        return "Spoils Expand\nConquer the hex on the loser's side of the Battleground (free)."

    tooltips = {
        "trade": f"Trade\n+1 gold, +{1 + trade_mod} gold for every other Faction playing Trade this turn.\n+{1 + trade_mod} Regard with each other Faction playing Trade this turn.",
        "steal": f"Steal\n-{1 + steal_mod} Regard with and -{1 + steal_mod} gold to all neighbors. +1 gold for each gold lost. War erupts at -2 Regard.",
        "expand": f"Expand\nSpend gold equal to territories{' -' + str(expand_mod) if expand_mod else ''} to claim a neutral hex. If unavailable or lacking gold, +{1 + expand_mod} gold instead. Idol hexes prioritized.",
        "change": "Change\nDraw a modifier card. If guided, draw extra cards equal to Influence and choose 1.",
    }
    return tooltips.get(agenda_type, agenda_type.title())


def build_modifier_tooltip(modifier_type: str) -> str:
    """Build full rules-text tooltip for a Change modifier card."""
    tooltips = {
        "trade": "Trade modifier\nPermanently increases gold and Regard gained per co-trader by 1.",
        "steal": "Steal modifier\nPermanently increases gold stolen and Regard penalty by 1 per neighbor.",
        "expand": "Expand modifier\nPermanently decreases expand cost by 1 gold and increases fail bonus by 1 gold.",
    }
    return tooltips.get(modifier_type, modifier_type.title())


class Button:
    def __init__(self, rect: pygame.Rect, text: str, color=(80, 80, 120),
                 text_color=(255, 255, 255), hover_color=(100, 100, 150),
                 tooltip: str = None, tooltip_always: bool = False):
        self.rect = rect
        self.text = text
        self.color = color
        self.text_color = text_color
        self.hover_color = hover_color
        self.hovered = False
        self.enabled = True
        self.tooltip = tooltip
        self.tooltip_always = tooltip_always

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        color = self.hover_color if self.hovered else self.color
        if not self.enabled:
            color = (60, 60, 60)
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, (200, 200, 200), self.rect, 1, border_radius=6)
        text_surf = font.render(self.text, True, self.text_color if self.enabled else (120, 120, 120))
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def draw_tooltip(self, surface: pygame.Surface, font: pygame.font.Font):
        """Draw tooltip near the button when hovered."""
        if not self.tooltip or not self.hovered:
            return
        if not self.tooltip_always and self.enabled:
            return
        draw_multiline_tooltip(
            surface, font, self.tooltip,
            anchor_x=self.rect.centerx,
            anchor_y=self.rect.top,
        )

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def clicked(self, mouse_pos) -> bool:
        return self.enabled and self.rect.collidepoint(mouse_pos)


class UIRenderer:
    """Draws all HUD and UI elements."""

    def __init__(self):
        self._font = None
        self._small_font = None
        self._title_font = None
        self.vp_positions: dict[str, tuple[int, int]] = {}  # spirit_id -> (x, y)
        self.vp_hover_rects: dict[str, pygame.Rect] = {}  # spirit_id -> rect
        self.panel_guided_rect: pygame.Rect | None = None
        self.panel_guided_spirit_id: str | None = None
        self.panel_worship_rect: pygame.Rect | None = None
        self.panel_worship_spirit_id: str | None = None
        self.panel_war_rect: pygame.Rect | None = None
        self.panel_faction_id: str | None = None
        self.faction_panel_rect: pygame.Rect | None = None
        self.event_log_expand_rect: pygame.Rect | None = None

    def _get_font(self, size=16):
        return get_font(size)

    @property
    def font(self):
        if self._font is None:
            self._font = get_font(16)
        return self._font

    @property
    def small_font(self):
        if self._small_font is None:
            self._small_font = get_font(13)
        return self._small_font

    @property
    def title_font(self):
        if self._title_font is None:
            self._title_font = get_font(24)
        return self._title_font

    def draw_hud(self, surface: pygame.Surface, phase: str, turn: int,
                 spirits: dict, my_spirit_id: str):
        """Draw the top HUD bar: phase, turn, VP totals."""
        bar_rect = pygame.Rect(0, 0, surface.get_width(), 40)
        pygame.draw.rect(surface, theme.BG_HUD, bar_rect)
        pygame.draw.line(surface, theme.BORDER_PANEL, (0, 40), (surface.get_width(), 40))

        phase_text = self.font.render(f"Turn {turn} | {phase.replace('_', ' ').title()}", True, theme.TEXT_HIGHLIGHT)
        surface.blit(phase_text, (10, 10))

        # Build spirit index map for sigil lookup (sorted for stability)
        spirit_index_map = {sid: i for i, sid in enumerate(sorted(spirits.keys()))}

        # VP display
        x = 300
        self.vp_hover_rects.clear()
        for sid, spirit in spirits.items():
            color = theme.TEXT_SPIRIT_NAME if sid == my_spirit_id else theme.TEXT_NORMAL
            name = spirit.get("name", sid[:6])
            vp = spirit.get("victory_points", 0)
            faction_id = spirit.get("guided_faction")

            # Render name
            entry_start_x = x
            name_surf = self.small_font.render(name, True, color)
            surface.blit(name_surf, (x, 12))
            x += name_surf.get_width()

            # Render identity symbol (always, vagrant or guiding) — silver
            sigil_r = 14
            sigil_cx = x + 4 + sigil_r
            draw_spirit_symbol(surface, sigil_cx, 20, sigil_r * 2,
                               spirit_index_map.get(sid, 0))
            x += sigil_r * 2 + 10  # left-pad(4) + diameter + right-pad(4)

            # Render VP
            self.vp_positions[sid] = (x, 12)
            vp_surf = self.small_font.render(f": {vp}VP", True, color)
            surface.blit(vp_surf, (x, 12))
            x += vp_surf.get_width()

            # Store hover rect covering name+sigil+VP (for click detection)
            self.vp_hover_rects[sid] = pygame.Rect(entry_start_x, 4, x - entry_start_x, 28)
            x += 20

    def draw_faction_overview(self, surface: pygame.Surface, factions: dict,
                              faction_agendas: dict[str, str], wars=None,
                              faction_spoils_agendas: dict[str, list[str]] = None,
                              spirits: dict = None,
                              preview_guidance: dict = None,
                              animated_agenda_factions: set = None,
                              faction_order: list = None):
        """Draw a compact overview strip showing all factions' gold, agenda, wars, and worship.

        Returns (agenda_label_entries, pool_icon_rects, ribbon_war_rects, ribbon_worship_rects):
        - agenda_label_entries: list of (faction_id, agenda_type, is_spoils, rect)
        - pool_icon_rects: dict of faction_id -> pygame.Rect covering the pool icons row
        - ribbon_war_rects: dict of faction_id -> pygame.Rect covering the war indicator group
        - ribbon_worship_rects: dict of faction_id -> pygame.Rect covering the worship sigil
        """
        spirits = spirits or {}
        faction_spoils_agendas = faction_spoils_agendas or {}
        animated_agenda_factions = animated_agenda_factions or set()
        faction_order = faction_order or FACTION_NAMES
        agenda_label_entries: list[tuple[str, str, bool, pygame.Rect]] = []
        pool_icon_rects: dict[str, pygame.Rect] = {}
        ribbon_war_rects: dict[str, pygame.Rect] = {}
        ribbon_worship_rects: dict[str, pygame.Rect] = {}
        spirit_index_map = {sid: i for i, sid in enumerate(sorted(spirits.keys()))}
        strip_y = 42
        strip_h = 55
        sw = surface.get_width()
        cell_w = sw // len(faction_order) if faction_order else sw

        # Background
        pygame.draw.rect(surface, theme.BG_OVERVIEW, pygame.Rect(0, strip_y, sw, strip_h))
        pygame.draw.line(surface, theme.BG_INPUT, (0, strip_y + strip_h),
                         (sw, strip_y + strip_h))

        agenda_colors = {
            "steal": (255, 80, 80),
            "trade": (255, 220, 60),
            "expand": (80, 220, 80),
            "change": (200, 140, 255),
        }

        # Build war lookup: faction_id -> list of (opponent_faction_id, is_ripe)
        war_lookup = {}
        if wars:
            for war in wars:
                war_lookup.setdefault(war.faction_a, []).append((war.faction_b, war.is_ripe))
                war_lookup.setdefault(war.faction_b, []).append((war.faction_a, war.is_ripe))

        for i, fid in enumerate(faction_order):
            fd = factions.get(fid)
            if not fd:
                continue
            cx = i * cell_w
            fc = tuple(FACTION_COLORS.get(fid, (150, 150, 150)))
            is_eliminated = fd.get("eliminated", False) if isinstance(fd, dict) else getattr(fd, "eliminated", False)

            if is_eliminated:
                # Greyed-out eliminated faction
                pygame.draw.rect(surface, (40, 40, 40), pygame.Rect(cx, strip_y, 3, strip_h))
                pygame.draw.rect(surface, (20, 20, 20), pygame.Rect(cx + 3, strip_y, cell_w - 3, strip_h))
                abbr = faction_full_name(fid)
                abbr_surf = self.small_font.render(abbr, True, (80, 80, 80))
                surface.blit(abbr_surf, (cx + 6, strip_y + 4))
                elim_surf = self.small_font.render("ELIMINATED", True, (120, 60, 60))
                surface.blit(elim_surf, (cx + 6, strip_y + 22))
                continue

            # Color accent bar
            pygame.draw.rect(surface, fc, pygame.Rect(cx, strip_y, 3, strip_h))

            # Darkened background
            bg = tuple(max(c // 5, 8) for c in fc)
            pygame.draw.rect(surface, bg, pygame.Rect(cx + 3, strip_y, cell_w - 3, strip_h))

            # Faction name
            abbr = faction_full_name(fid)
            abbr_surf = self.small_font.render(abbr, True, fc)
            surface.blit(abbr_surf, (cx + 6, strip_y + 4))

            # Gold amount
            gold = fd.get("gold", 0) if isinstance(fd, dict) else getattr(fd, "gold", 0)
            gold_text = self.small_font.render(f"{gold}g", True, (255, 220, 60))
            surface.blit(gold_text, (cx + 6 + abbr_surf.get_width() + 6, strip_y + 4))

            worship_id = fd.get("worship_spirit") if isinstance(fd, dict) else getattr(fd, "worship_spirit", None)
            guiding_id = fd.get("guiding_spirit") if isinstance(fd, dict) else getattr(fd, "guiding_spirit", None)

            # Preview guidance indicator (faded, with ? prefix) — first row, after gold
            if preview_guidance and not guiding_id and fid in preview_guidance:
                preview_name = preview_guidance[fid]
                pv_surf = self.small_font.render(f" ?{preview_name}", True, (80, 80, 100))
                preview_x = cx + 6 + abbr_surf.get_width() + 6 + gold_text.get_width()
                surface.blit(pv_surf, (preview_x, strip_y + 4))

            # Agenda name (right-aligned) - skip if animated
            if fid not in animated_agenda_factions:
                agenda_entries: list[tuple[str, bool]] = []
                agenda_str = faction_agendas.get(fid, "")
                if agenda_str:
                    agenda_entries.append((agenda_str, False))
                for spoils_agenda in faction_spoils_agendas.get(fid, []):
                    if spoils_agenda:
                        agenda_entries.append((spoils_agenda, True))

                for row_idx, (agenda_type, is_spoils) in enumerate(agenda_entries):
                    a_label = agenda_type.title()
                    a_color = agenda_colors.get(agenda_type, (160, 160, 180))
                    a_surf = self.small_font.render(a_label, True, a_color)
                    a_pos = (cx + cell_w - a_surf.get_width() - 6, strip_y + 4 + row_idx * 16)
                    surface.blit(a_surf, a_pos)
                    rect = pygame.Rect(a_pos[0], a_pos[1], a_surf.get_width(), a_surf.get_height())
                    agenda_label_entries.append((fid, agenda_type, is_spoils, rect))
                    draw_dotted_underline(surface, a_pos[0], a_pos[1] + a_surf.get_height(),
                                          a_surf.get_width())

            # Agenda pool icons: 2×2 grid filling space below faction name
            pool_types = fd.get("agenda_pool", []) if isinstance(fd, dict) else []
            icon_size = 15   # px per icon (square)
            icon_gap = 3     # px gap between icons
            grid_start_x = cx + 6
            grid_start_y = strip_y + 18
            grid_total_w = 2 * icon_size + icon_gap
            grid_total_h = 2 * icon_size + icon_gap
            if len(pool_types) == 4:
                # Fixed 2×2 positions: [0]=top-left, [1]=top-right, [2]=bottom-left, [3]=bottom-right
                positions = [
                    (grid_start_x,                         grid_start_y),
                    (grid_start_x + icon_size + icon_gap,  grid_start_y),
                    (grid_start_x,                         grid_start_y + icon_size + icon_gap),
                    (grid_start_x + icon_size + icon_gap,  grid_start_y + icon_size + icon_gap),
                ]
                change_mods = fd.get("change_modifiers", {}) if isinstance(fd, dict) else {}
                plus_font = self._get_font(8)
                for (px, py), at_str in zip(positions, pool_types):
                    img = agenda_ribbon_icons.get(at_str)
                    if img:
                        surface.blit(img, (px, py))
                    else:
                        # Fallback: colored square if image not loaded
                        icon_color = agenda_colors.get(at_str, (160, 160, 180))
                        pygame.draw.rect(surface, icon_color,
                                         pygame.Rect(px, py, icon_size, icon_size), border_radius=2)
                    mod_count = change_mods.get(at_str, 0)
                    if mod_count > 0:
                        display = min(mod_count, 6)
                        line1 = "+" * min(display, 3)
                        line2 = "+" * max(0, display - 3)
                        surf1 = plus_font.render(line1, True, (255, 255, 255))
                        surface.blit(surf1, (px + 1, py + 1))
                        if line2:
                            surf2 = plus_font.render(line2, True, (255, 255, 255))
                            surface.blit(surf2, (px + 1, py + 1 + surf1.get_height()))
                pool_icon_rects[fid] = pygame.Rect(
                    grid_start_x, grid_start_y, grid_total_w, grid_total_h)

            # War indicators: centered in the faction cell (away from the pool)
            sy = grid_start_y + grid_total_h // 2  # center y aligned with pool grid

            # Worship sigil: silver spirit symbol right of pool, left of wars
            if worship_id:
                worship_sidx = spirit_index_map.get(worship_id, 0)
                sigil_cx = grid_start_x + grid_total_w + 10
                draw_spirit_symbol(surface, sigil_cx, sy, 24,
                                   worship_sidx, (192, 192, 192))
                ribbon_worship_rects[fid] = pygame.Rect(sigil_cx - 12, sy - 12, 24, 24)

            if fid in war_lookup:
                opponents = war_lookup[fid]
                # Total width: 14px for swords + 14px per opponent hex
                total_war_w = 14 + len(opponents) * 14
                # Center the group horizontally in the faction cell
                wars_x_start = cx + cell_w // 2 - total_war_w // 2
                wx = wars_x_start
                any_ripe = any(ripe for _, ripe in opponents)
                sword_color = (255, 50, 50) if any_ripe else (180, 60, 60)
                # Draw crossed swords icon (two diagonal lines)
                pygame.draw.line(surface, sword_color, (wx, sy - 5), (wx + 10, sy + 5), 2)
                pygame.draw.line(surface, sword_color, (wx + 10, sy - 5), (wx, sy + 5), 2)
                wx += 14
                # Draw tiny hex for each enemy faction
                for opponent_fid, is_ripe in opponents:
                    enemy_color = tuple(FACTION_COLORS.get(opponent_fid, (150, 150, 150)))
                    hx, hy = wx + 5, sy  # center of tiny hex
                    r = 5  # radius of tiny hex
                    # Flat-top hexagon points
                    points = []
                    for k in range(6):
                        angle = math.pi / 3 * k
                        points.append((hx + r * math.cos(angle), hy + r * math.sin(angle)))
                    pygame.draw.polygon(surface, enemy_color, points)
                    if is_ripe:
                        pygame.draw.polygon(surface, (255, 255, 255), points, 1)
                    wx += 14
                # Store hoverable rect covering just the war indicator area
                ribbon_war_rects[fid] = pygame.Rect(wars_x_start, sy - 8, total_war_w, 16)

        return agenda_label_entries, pool_icon_rects, ribbon_war_rects, ribbon_worship_rects

    def _render_strikethrough(self, surface, font, text_str, color, pos):
        """Render text with a strikethrough line."""
        dim_color = tuple(max(c // 2, 40) for c in color)
        text_surf = font.render(text_str, True, dim_color)
        surface.blit(text_surf, pos)
        # Draw horizontal line through vertical center
        line_y = pos[1] + text_surf.get_height() // 2
        pygame.draw.line(surface, dim_color,
                         (pos[0], line_y),
                         (pos[0] + text_surf.get_width(), line_y), 1)
        return text_surf.get_width()

    def _render_delta_chip(self, surface, font, delta, label, log_index,
                           pos, highlight_log_idx, change_rects):
        """Render a +X or -Y delta chip. Returns chip width."""
        if delta > 0:
            chip_text = f"+{delta}"
            chip_color = theme.DELTA_POS
        else:
            chip_text = f"{delta}"
            chip_color = theme.DELTA_NEG

        is_highlighted = highlight_log_idx is not None and log_index == highlight_log_idx
        text_surf = font.render(chip_text, True, chip_color)
        chip_w = text_surf.get_width() + 6
        chip_h = text_surf.get_height() + 2
        chip_rect = pygame.Rect(pos[0], pos[1], chip_w, chip_h)

        if is_highlighted:
            pygame.draw.rect(surface, (80, 80, 40), chip_rect, border_radius=3)
        pygame.draw.rect(surface, chip_color, chip_rect, 1, border_radius=3)
        surface.blit(text_surf, (pos[0] + 3, pos[1] + 1))

        if change_rects is not None:
            change_rects.append((chip_rect, log_index))

        return chip_w

    def _sum_numeric_deltas(self, changes) -> int:
        """Sum numeric deltas from change entries, ignoring non-numeric entries."""
        total = 0
        for ch in changes:
            if isinstance(ch.delta, (int, float)):
                total += int(ch.delta)
        return total

    def draw_faction_panel(self, surface: pygame.Surface, faction_data: dict,
                           x: int, y: int, width: int = 220, spirits: dict = None,
                           preview_guidance: dict = None,
                           change_tracker=None, panel_faction_id: str = None,
                           highlight_log_idx: int = None,
                           change_rects: list = None,
                           wars: list = None,
                           all_factions: dict = None,
                           faction_order: list = None,
                           scroll_offset: int = 0,
                           max_height: int = None):
        """Draw faction info panel."""
        if not faction_data:
            return

        fid = faction_data.get("faction_id", "")
        color = tuple(faction_data.get("color", (150, 150, 150)))
        gold = faction_data.get("gold", 0)
        territories = faction_data.get("territories", [])
        regard = faction_data.get("regard", {})
        if all_factions:
            regard = {
                other_fid: val
                for other_fid, val in regard.items()
                if not all_factions.get(other_fid, {}).get("eliminated", False)
            }
        if faction_order:
            regard = dict(sorted(regard.items(),
                                 key=lambda kv: faction_order.index(kv[0]) if kv[0] in faction_order else 999))
        modifiers = faction_data.get("change_modifiers", {})
        guiding = faction_data.get("guiding_spirit")
        worship = faction_data.get("worship_spirit")

        spirits = spirits or {}
        preview_guidance = preview_guidance or {}
        guiding_name = spirits.get(guiding, {}).get("name", guiding) if guiding else "none"
        worship_name = spirits.get(worship, {}).get("name", worship) if worship else "none"

        # Build war opponents for this faction
        war_opponents = []  # list of (opponent_name, is_ripe)
        if wars:
            for w in wars:
                fa = getattr(w, 'faction_a', None) or (w.get('faction_a') if isinstance(w, dict) else None)
                fb = getattr(w, 'faction_b', None) or (w.get('faction_b') if isinstance(w, dict) else None)
                ripe = getattr(w, 'is_ripe', None)
                if ripe is None and isinstance(w, dict):
                    ripe = w.get('is_ripe', False)
                if fa == fid:
                    war_opponents.append((faction_full_name(fb), ripe, fb))
                elif fb == fid:
                    war_opponents.append((faction_full_name(fa), ripe, fa))

        # Calculate dynamic panel height based on content
        panel_h = 8 + 24  # top padding + name header
        if faction_data.get("eliminated", False):
            panel_h += 24  # "ELIMINATED" text
        else:
            panel_h += 18 * 4  # gold + territories + guided + worship
            if regard:
                panel_h += 4 + 18 + len(regard) * 18  # gap + header + entries
            active_modifiers = sum(1 for v in modifiers.values() if v > 0)
            if active_modifiers:
                panel_h += 4 + 18 + active_modifiers * 18
            pool_types = faction_data.get("agenda_pool", [])
            pool_counts = {}
            for pt in pool_types:
                pool_counts[pt] = pool_counts.get(pt, 0) + 1
            pool_differs = set(pool_counts.keys()) != {"steal", "trade", "expand", "change"} or any(v != 1 for v in pool_counts.values())
            if pool_differs:
                pool_entries = len(pool_counts)
                panel_h += 4 + 18 + pool_entries * 18
            if war_opponents:
                panel_h += 4 + 18 + len(war_opponents) * 18
        panel_h += 8  # bottom padding
        self._faction_panel_content_h = panel_h
        if max_height:
            display_h = min(panel_h, max_height)
        else:
            display_h = min(panel_h, surface.get_height() - y - 4)
        panel_rect = pygame.Rect(x, y, width, display_h)
        self.faction_panel_rect = panel_rect
        pygame.draw.rect(surface, theme.BG_PANEL, panel_rect, border_radius=4)
        pygame.draw.rect(surface, color, panel_rect, 2, border_radius=4)

        old_clip = surface.get_clip()
        surface.set_clip(panel_rect)

        dy = y + 8 - scroll_offset
        name = faction_full_name(fid)
        name_text = self.font.render(name, True, color)
        surface.blit(name_text, (x + 10, dy))
        dy += 24

        if faction_data.get("eliminated", False):
            elim_text = self.font.render("ELIMINATED", True, (200, 60, 60))
            surface.blit(elim_text, (x + 10, dy))
            surface.set_clip(old_clip)
            return

        # Check for preview guidance name
        preview_guid_name = preview_guidance.get(fid)

        # Helper: get field changes from tracker
        def _field_changes(field_name, target=None):
            if change_tracker and panel_faction_id:
                return change_tracker.get_field_changes(panel_faction_id, field_name, target)
            return []

        # --- Gold ---
        gold_changes = _field_changes("gold")
        if gold_changes:
            gold_delta_total = self._sum_numeric_deltas(gold_changes)
            old_gold = gold - gold_delta_total
            label_surf = self.small_font.render("Gold: ", True, theme.TEXT_NORMAL)
            surface.blit(label_surf, (x + 10, dy))
            cx = x + 10 + label_surf.get_width()
            cx += self._render_strikethrough(
                surface, self.small_font, str(old_gold), theme.TEXT_NORMAL, (cx, dy))
            cx += 4
            for ch in gold_changes:
                cx += self._render_delta_chip(
                    surface, self.small_font, ch.delta, ch.label, ch.log_index,
                    (cx, dy), highlight_log_idx, change_rects)
                cx += 3
            new_surf = self.small_font.render(str(gold), True, (180, 220, 255))
            surface.blit(new_surf, (cx, dy))
        else:
            text = self.small_font.render(f"Gold: {gold}", True, theme.TEXT_NORMAL)
            surface.blit(text, (x + 10, dy))
        dy += 18

        # --- Territories ---
        terr_changes = _field_changes("territories")
        if terr_changes:
            terr_now = len(territories)
            terr_delta_total = self._sum_numeric_deltas(terr_changes)
            old_terr = terr_now - terr_delta_total
            label_surf = self.small_font.render("Territories: ", True, theme.TEXT_NORMAL)
            surface.blit(label_surf, (x + 10, dy))
            cx = x + 10 + label_surf.get_width()
            cx += self._render_strikethrough(
                surface, self.small_font, str(old_terr), theme.TEXT_NORMAL, (cx, dy))
            cx += 4
            for ch in terr_changes:
                cx += self._render_delta_chip(
                    surface, self.small_font, ch.delta, ch.label, ch.log_index,
                    (cx, dy), highlight_log_idx, change_rects)
                cx += 3
            new_surf = self.small_font.render(str(terr_now), True, (180, 220, 255))
            surface.blit(new_surf, (cx, dy))
        else:
            text = self.small_font.render(f"Territories: {len(territories)}", True, theme.TEXT_NORMAL)
            surface.blit(text, (x + 10, dy))
        dy += 18

        # --- Guided by ---
        guide_changes = _field_changes("guiding_spirit")
        guided_line_y = dy
        guided_text_w = 0
        if guide_changes:
            ch = guide_changes[-1]  # latest change
            label_surf = self.small_font.render("Guided by: ", True, theme.TEXT_NORMAL)
            surface.blit(label_surf, (x + 10, dy))
            cx = x + 10 + label_surf.get_width()
            cx += self._render_strikethrough(
                surface, self.small_font, ch.old_value or "none", theme.TEXT_NORMAL, (cx, dy))
            cx += 4
            new_surf = self.small_font.render(ch.new_value or "none", True, (180, 220, 255))
            surface.blit(new_surf, (cx, dy))
            guided_text_w = cx + new_surf.get_width() - (x + 10)
        elif preview_guid_name and guiding_name == "none":
            text = self.small_font.render(f"Guided by: {preview_guid_name}?", True, (100, 100, 130))
            surface.blit(text, (x + 10, dy))
            guided_text_w = text.get_width()
        else:
            text = self.small_font.render(f"Guided by: {guiding_name}", True, theme.TEXT_NORMAL)
            surface.blit(text, (x + 10, dy))
            guided_text_w = text.get_width()
        self.panel_guided_rect = pygame.Rect(x + 10, guided_line_y, guided_text_w, 16)
        self.panel_guided_spirit_id = guiding
        # Dotted underline to indicate hoverable text
        draw_dotted_underline(surface, x + 10, guided_line_y + 14, guided_text_w)
        dy += 18

        # --- Worshipping ---
        worship_changes = _field_changes("worship_spirit")
        worship_line_y = dy
        worship_text_w = 0
        if worship_changes:
            ch = worship_changes[-1]
            label_surf = self.small_font.render("Worshipping: ", True, theme.TEXT_NORMAL)
            surface.blit(label_surf, (x + 10, dy))
            cx = x + 10 + label_surf.get_width()
            cx += self._render_strikethrough(
                surface, self.small_font, ch.old_value or "none", theme.TEXT_NORMAL, (cx, dy))
            cx += 4
            new_surf = self.small_font.render(ch.new_value or "none", True, (180, 220, 255))
            surface.blit(new_surf, (cx, dy))
            worship_text_w = cx + new_surf.get_width() - (x + 10)
        elif preview_guid_name and worship_name == "none":
            text = self.small_font.render(f"Worshipping: {preview_guid_name}?", True, (100, 100, 130))
            surface.blit(text, (x + 10, dy))
            worship_text_w = text.get_width()
        else:
            text = self.small_font.render(f"Worshipping: {worship_name}", True, theme.TEXT_NORMAL)
            surface.blit(text, (x + 10, dy))
            worship_text_w = text.get_width()
        self.panel_worship_rect = pygame.Rect(x + 10, worship_line_y, worship_text_w, 16)
        self.panel_worship_spirit_id = worship
        self.panel_faction_id = fid
        # Dotted underline to indicate hoverable text
        draw_dotted_underline(surface, x + 10, worship_line_y + 14, worship_text_w)
        dy += 18

        if regard:
            dy += 4
            text = self.small_font.render("Regard:", True, (150, 150, 170))
            surface.blit(text, (x + 10, dy))
            dy += 18
            for other_fid, val in regard.items():
                regard_changes = _field_changes("regard", target=other_fid)
                other_name = faction_full_name(other_fid)
                if regard_changes:
                    regard_delta_total = self._sum_numeric_deltas(regard_changes)
                    old_regard = val - regard_delta_total
                    r_old_color = (100, 255, 100) if old_regard > 0 else (255, 100, 100) if old_regard < 0 else theme.TEXT_NORMAL
                    r_new_color = (100, 255, 100) if val > 0 else (255, 100, 100) if val < 0 else theme.TEXT_NORMAL
                    label_surf = self.small_font.render(f"  {other_name}: ", True, theme.TEXT_NORMAL)
                    surface.blit(label_surf, (x + 10, dy))
                    cx = x + 10 + label_surf.get_width()
                    cx += self._render_strikethrough(
                        surface, self.small_font, f"{old_regard:+d}", r_old_color, (cx, dy))
                    cx += 4
                    for ch in regard_changes:
                        cx += self._render_delta_chip(
                            surface, self.small_font, ch.delta, ch.label, ch.log_index,
                            (cx, dy), highlight_log_idx, change_rects)
                        cx += 3
                    new_surf = self.small_font.render(f"{val:+d}", True, r_new_color)
                    surface.blit(new_surf, (cx, dy))
                else:
                    r_color = (100, 255, 100) if val > 0 else (255, 100, 100) if val < 0 else theme.TEXT_NORMAL
                    text = self.small_font.render(f"  {other_name}: {val:+d}", True, r_color)
                    surface.blit(text, (x + 10, dy))
                dy += 18

        if any(v > 0 for v in modifiers.values()):
            dy += 4
            text = self.small_font.render("Modifiers:", True, (150, 150, 170))
            surface.blit(text, (x + 10, dy))
            dy += 18
            for mod, val in modifiers.items():
                if val > 0:
                    mod_changes = _field_changes("modifier", target=mod)
                    if mod_changes:
                        ch = mod_changes[-1]
                        mod_surf = self.small_font.render(f"  {mod}: +{val}", True, (150, 200, 255))
                        surface.blit(mod_surf, (x + 10, dy))
                        # Highlight glow for new modifier
                        glow_rect = pygame.Rect(x + 8, dy - 1, mod_surf.get_width() + 4, mod_surf.get_height() + 2)
                        pygame.draw.rect(surface, (100, 160, 255), glow_rect, 1, border_radius=3)
                        if change_rects is not None:
                            change_rects.append((glow_rect, ch.log_index))
                    else:
                        text = self.small_font.render(f"  {mod}: +{val}", True, (150, 200, 255))
                        surface.blit(text, (x + 10, dy))
                    dy += 18

        # Agenda pool (show when it differs from the standard 1-of-each baseline)
        pool_types = faction_data.get("agenda_pool", [])
        pool_counts: dict[str, int] = {}
        for pt in pool_types:
            pool_counts[pt] = pool_counts.get(pt, 0) + 1
        pool_differs = set(pool_counts.keys()) != {"steal", "trade", "expand", "change"} or any(v != 1 for v in pool_counts.values())
        if pool_differs:
            dy += 4
            text = self.small_font.render("Agenda Pool:", True, (150, 150, 170))
            surface.blit(text, (x + 10, dy))
            dy += 18
            agenda_colors_map = {
                "steal": (255, 100, 100),
                "trade": (255, 220, 100),
                "expand": (100, 220, 100),
                "change": (200, 150, 255),
            }
            for atype in ["steal", "trade", "expand", "change"]:
                count = pool_counts.get(atype, 0)
                if count == 0:
                    color = (120, 60, 60)
                    label = f"  {atype}: none"
                elif count == 1:
                    color = agenda_colors_map.get(atype, (200, 180, 100))
                    label = f"  {atype}"
                else:
                    color = agenda_colors_map.get(atype, (200, 180, 100))
                    label = f"  {atype} \u00d7{count}"
                if count != 1:
                    text = self.small_font.render(label, True, color)
                    surface.blit(text, (x + 10, dy))
                    dy += 18

        # Wars
        if war_opponents:
            dy += 4
            text = self.small_font.render("At War with:", True, (150, 150, 170))
            surface.blit(text, (x + 10, dy))
            self.panel_war_rect = pygame.Rect(x + 10, dy, text.get_width(), 16)
            draw_dotted_underline(surface, x + 10, dy + 14, text.get_width())
            dy += 18
            for opp_name, is_ripe, opp_fid in war_opponents:
                suffix = " (ripe)" if is_ripe else " (new)"
                war_color = tuple(FACTION_COLORS.get(opp_fid, (150, 150, 150)))
                text = self.small_font.render(f"  {opp_name}{suffix}", True, war_color)
                surface.blit(text, (x + 10, dy))
                dy += 18
        else:
            self.panel_war_rect = None

        surface.set_clip(old_clip)

        # Draw scroll arrows if content exceeds displayed area
        if panel_h > display_h:
            indicator_x = x + width - 14
            if scroll_offset > 0:
                arrow_up = self.small_font.render("\u25b2", True, (150, 150, 180))
                surface.blit(arrow_up, (indicator_x, y + 4))
            if scroll_offset < panel_h - display_h:
                arrow_down = self.small_font.render("\u25bc", True, (150, 150, 180))
                surface.blit(arrow_down, (indicator_x, y + display_h - 18))

    def draw_spirit_panel(self, surface: "pygame.Surface", spirit_data: dict,
                          factions: dict, all_idols: list, hex_ownership: dict,
                          x: int, y: int, width: int = 230,
                          my_spirit_id: str = "",
                          circle_fills: "list[float] | None" = None,
                          spirit_index_map: dict = None,
                          max_height: int = None) -> dict:
        """Draw spirit info panel showing guidance, influence, worship, and idol counts.

        Returns a dict with keys "panel", "guidance", "influence", "worship" containing
        the pygame.Rect for each hoverable region (for use by the caller).
        """
        if not spirit_data:
            return {}

        spirit_id = spirit_data.get("spirit_id", my_spirit_id)
        name = spirit_data.get("name", spirit_id[:6])
        influence = spirit_data.get("influence", 0)
        guided_faction = spirit_data.get("guided_faction")
        is_vagrant = spirit_data.get("is_vagrant", True)
        vp = spirit_data.get("victory_points", 0)
        habitat_affinity = spirit_data.get("habitat_affinity", "")
        race_affinity = spirit_data.get("race_affinity", "")

        # Find factions worshipping this spirit
        worshipping_factions = []
        for fid, fdata in factions.items():
            if fdata.get("worship_spirit") == spirit_id and not fdata.get("eliminated"):
                worshipping_factions.append((fid, fdata))

        # Calculate panel height
        panel_h = 108  # header + guidance + influence + affinity
        if worshipping_factions:
            panel_h += 22 + len(worshipping_factions) * 36  # section header + per-faction
        else:
            panel_h += 22 + 18  # section header + "None"

        display_h = min(panel_h, max_height) if max_height else panel_h
        panel_rect = pygame.Rect(x, y, width, display_h)
        pygame.draw.rect(surface, theme.BG_PANEL, panel_rect, border_radius=4)
        pygame.draw.rect(surface, (192, 192, 192), panel_rect, 2, border_radius=4)

        old_clip = surface.get_clip()
        surface.set_clip(panel_rect)

        dy = y + 8

        # Header: Spirit name
        name_surf = self.font.render(name, True, (255, 255, 100))
        surface.blit(name_surf, (x + 10, dy))
        # VP to the right
        vp_surf = self.small_font.render(f"{vp} VP", True, theme.TEXT_HIGHLIGHT)
        surface.blit(vp_surf, (x + width - 10 - vp_surf.get_width(), dy + 2))
        # Identity symbol in header (always, vagrant or guiding) — silver
        if spirit_index_map is not None:
            sidx = spirit_index_map.get(spirit_id, 0)
            sigil_sr = 24
            sigil_cx = x + width - 10 - vp_surf.get_width() - sigil_sr - 8
            sigil_cy = dy + 12   # vertically centred in the 24 px header zone
            draw_spirit_symbol(surface, sigil_cx, sigil_cy, sigil_sr, sidx)
        dy += 24

        # Guidance line
        guidance_line_y = dy
        if guided_faction:
            faction_color = tuple(FACTION_COLORS.get(guided_faction, (150, 150, 150)))
            faction_name = faction_full_name(guided_faction)
            label_surf = self.small_font.render("Guiding: ", True, theme.TEXT_NORMAL)
            surface.blit(label_surf, (x + 10, dy))
            value_surf = self.small_font.render(faction_name, True, faction_color)
            surface.blit(value_surf, (x + 10 + label_surf.get_width(), dy))
            guidance_text_w = label_surf.get_width() + value_surf.get_width()
        else:
            label_surf = self.small_font.render("Vagrant", True, (140, 140, 160))
            surface.blit(label_surf, (x + 10, dy))
            guidance_text_w = label_surf.get_width()
        guidance_rect = pygame.Rect(x + 10, guidance_line_y, guidance_text_w, 16)
        draw_dotted_underline(surface, x + 10, guidance_line_y + 14, guidance_text_w)
        dy += 18

        # Influence circles
        influence_line_y = dy
        inf_label = self.small_font.render("Influence ", True, theme.TEXT_NORMAL)
        surface.blit(inf_label, (x + 10, dy))
        circle_r = 7
        cx_start = x + 10 + inf_label.get_width()
        for idx in range(3):
            cx = cx_start + idx * (circle_r * 2 + 3) + circle_r
            cy = dy + circle_r
            if circle_fills is not None:
                fill = circle_fills[idx]
            else:
                fill = 1.0 if idx < influence else 0.0
            if fill > 0.01:
                tmp = pygame.Surface((circle_r * 2, circle_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(tmp, (180, 180, 220, int(fill * 255)),
                                   (circle_r, circle_r), circle_r)
                surface.blit(tmp, (cx - circle_r, cy - circle_r))
            pygame.draw.circle(surface, (120, 120, 160), (cx, cy), circle_r, 1)
        circles_w = 3 * (circle_r * 2 + 3)
        total_w = inf_label.get_width() + circles_w
        influence_rect = pygame.Rect(x + 10, influence_line_y, total_w, circle_r * 2)
        draw_dotted_underline(surface, x + 10, influence_line_y + circle_r * 2 + 2, total_w)
        dy += circle_r * 2 + 6

        # Affinity row
        affinity_rect = None
        if habitat_affinity or race_affinity:
            aff_label = self.small_font.render("Affinity: ", True, (150, 150, 170))
            surface.blit(aff_label, (x + 10, dy))
            draw_dotted_underline(surface, x + 10, dy + 14, aff_label.get_width() - 1)
            affinity_rect = pygame.Rect(x + 10, dy, aff_label.get_width(), 16)
            ax = x + 10 + aff_label.get_width()
            hab_color = tuple(FACTION_COLORS.get(habitat_affinity, theme.TEXT_NORMAL))
            if habitat_affinity:
                hab_name = FACTION_DISPLAY_NAMES.get(habitat_affinity, habitat_affinity)
                hab_surf = self.small_font.render(hab_name, True, hab_color)
                surface.blit(hab_surf, (ax, dy))
                ax += hab_surf.get_width()
            if habitat_affinity and race_affinity:
                sep_surf = self.small_font.render(" / ", True, (120, 120, 140))
                surface.blit(sep_surf, (ax, dy))
                ax += sep_surf.get_width()
            if race_affinity:
                # Color the race with the color of whichever faction has that race
                race_faction_id = next(
                    (fid for fid, fd in factions.items()
                     if (fd.get("race") if isinstance(fd, dict) else getattr(fd, "race", "")) == race_affinity),
                    None
                )
                race_color = tuple(FACTION_COLORS.get(race_faction_id, theme.TEXT_NORMAL)) if race_faction_id else hab_color
                race_surf = self.small_font.render(race_affinity, True, race_color)
                surface.blit(race_surf, (ax, dy))
            dy += 18

        # Worshipped by section
        worship_rects: dict[str, pygame.Rect] = {}
        section_surf = self.small_font.render("Worshipped by:", True, (150, 150, 170))
        surface.blit(section_surf, (x + 10, dy))
        dy += 18

        if worshipping_factions:
            for fid, fdata in worshipping_factions:
                faction_color = tuple(FACTION_COLORS.get(fid, (150, 150, 150)))
                faction_name = faction_full_name(fid)
                fname_surf = self.small_font.render(faction_name, True, faction_color)
                surface.blit(fname_surf, (x + 14, dy))
                fname_w = fname_surf.get_width()
                worship_rects[fid] = pygame.Rect(x + 14, dy, fname_w, 16)
                draw_dotted_underline(surface, x + 14, dy + 14, fname_w)
                dy += 18

                # Count idols of each type owned by this spirit in this faction's territory
                battle_c = spread_c = affluence_c = 0
                for idol in all_idols:
                    if isinstance(idol, dict):
                        owner = idol.get('owner_spirit', '')
                        if owner != spirit_id:
                            continue
                        pos = idol.get('position', {})
                        q, r = pos.get('q'), pos.get('r')
                        if hex_ownership.get((q, r)) == fid:
                            itype = idol.get('type', '')
                            if itype == IdolType.BATTLE.value:
                                battle_c += 1
                            elif itype == IdolType.SPREAD.value:
                                spread_c += 1
                            elif itype == IdolType.AFFLUENCE.value:
                                affluence_c += 1
                idol_parts = []
                if battle_c:
                    idol_parts.append(f"Battle: {battle_c}")
                if spread_c:
                    idol_parts.append(f"Spread: {spread_c}")
                if affluence_c:
                    idol_parts.append(f"Affluence: {affluence_c}")
                idol_text = ", ".join(idol_parts) if idol_parts else "no idols"
                idol_surf = self.small_font.render(f"  {idol_text}", True, (140, 140, 160))
                surface.blit(idol_surf, (x + 14, dy))
                dy += 18
        else:
            none_surf = self.small_font.render("  None", True, (140, 140, 160))
            surface.blit(none_surf, (x + 10, dy))
            dy += 18

        surface.set_clip(old_clip)

        # Draw scroll arrow if content overflows
        if panel_h > display_h:
            indicator_x = x + width - 14
            arrow_down = self.small_font.render("\u25bc", True, (150, 150, 180))
            surface.blit(arrow_down, (indicator_x, y + display_h - 18))

        return {"panel": panel_rect, "guidance": guidance_rect, "influence": influence_rect,
                "worship": worship_rects, "affinity": affinity_rect}

    def _build_card_description(self, agenda_type: str, modifiers: dict,
                                is_spoils: bool = False,
                                territories: int = 0) -> list[str]:
        """Build detailed description lines for an agenda card based on modifiers."""
        steal_mod = modifiers.get("steal", 0)
        trade_mod = modifiers.get("trade", 0)
        expand_mod = modifiers.get("expand", 0)

        if is_spoils and agenda_type == "expand":
            return [
                "Conquer enemy",
                "Battleground hex",
                "(free)",
            ]

        expand_cost = max(0, territories - expand_mod)
        descs = {
            "steal": [
                f"-{1 + steal_mod} neighbor regard,",
                f"-{1 + steal_mod} neighbor gold",
                "+gold stolen",
            ],
            "trade": [
                "+1g base",
                f"+{1 + trade_mod}g per trader",
                f"+{1 + trade_mod} regard/trader",
            ],
            "expand": [
                f"Cost: {expand_cost}g",
                "Claim neutral hex",
                f"Fail: +{1 + expand_mod}g",
            ],
            "change": [
                "Draw modifier card",
                "which upgrades",
                "other Agendas",
            ],
        }
        return descs.get(agenda_type, ["???"])

    def _build_modifier_description(self, modifier_type: str) -> list[str]:
        """Build description lines for a Change modifier card."""
        descs = {
            "trade": [
                "+1g & +1 Regard",
                "per co-trader",
            ],
            "steal": [
                "+1g stolen &",
                "-1 Regard per",
                "neighbor",
            ],
            "expand": [
                "-1g expand cost",
                "+1g fail bonus",
            ],
        }
        return descs.get(modifier_type, ["???"])

    def draw_card_hand(self, surface: pygame.Surface, hand: list[dict],
                       selected_index: int, x: int, y: int,
                       modifiers: dict | None = None,
                       card_images: dict | None = None,
                       is_spoils: bool = False,
                       show_preview_plus: bool = False,
                       vertical: bool = False,
                       territories: int = 0) -> list[pygame.Rect]:
        """Draw clickable agenda cards. Returns list of card rects.

        Each card dict should have "agenda_type". May optionally have
        "description" (list[str]) to override auto-generated descriptions.
        When vertical=True, cards stack vertically instead of horizontally.
        """
        modifiers = modifiers or {}
        card_images = card_images or {}
        rects = []
        effect_font = self._get_font(11)

        if vertical:
            card_w, card_h = 110, 145
            spacing = 5
            for i, card in enumerate(hand):
                cx = x
                cy = y + i * (card_h + spacing)
                rect = pygame.Rect(cx, cy, card_w, card_h)
                rects.append(rect)

                bg_color = (60, 80, 120) if i == selected_index else (40, 40, 55)
                border_color = (200, 200, 255) if i == selected_index else (80, 80, 100)

                pygame.draw.rect(surface, bg_color, rect, border_radius=6)
                pygame.draw.rect(surface, border_color, rect, 2, border_radius=6)

                agenda_type = card.get("agenda_type", "?")
                name_text = self.font.render(agenda_type.title(), True, (220, 220, 240))
                surface.blit(name_text, (cx + card_w // 2 - name_text.get_width() // 2, cy + 8))

                img = card_images.get(agenda_type)
                desc_y = cy + 30
                if img:
                    img_scaled = pygame.transform.scale(img, (70, img.get_height() * 70 // max(img.get_width(), 1)))
                    img_x = cx + card_w // 2 - img_scaled.get_width() // 2
                    img_y = cy + 26
                    surface.blit(img_scaled, (img_x, img_y))
                    desc_y = img_y + img_scaled.get_height() + 4
                    mod_count = modifiers.get(agenda_type, 0)
                    if mod_count > 0 or show_preview_plus:
                        plus_size = max(9, img_scaled.get_height() // 3)
                        plus_font = self._get_font(plus_size)
                        plus_x = cx + 3
                        for k in range(mod_count):
                            plus_surf = plus_font.render("+", True, (255, 255, 255))
                            surface.blit(plus_surf, (plus_x, img_y + 2 + k * (plus_size + 2)))
                        if show_preview_plus:
                            faded_surf = plus_font.render("+", True, (255, 255, 255))
                            faded_surf.set_alpha(70)
                            surface.blit(faded_surf, (plus_x, img_y + 2 + mod_count * (plus_size + 2)))

                desc_lines = card.get("description") or self._build_card_description(
                    agenda_type, modifiers, is_spoils=is_spoils, territories=territories)
                for j, line in enumerate(desc_lines):
                    desc_text = effect_font.render(line, True, (160, 170, 190))
                    surface.blit(desc_text, (cx + card_w // 2 - desc_text.get_width() // 2, desc_y + j * 13))
        else:
            card_w, card_h = 110, 170
            spacing = 10
            for i, card in enumerate(hand):
                cx = x + i * (card_w + spacing)
                rect = pygame.Rect(cx, y, card_w, card_h)
                rects.append(rect)

                bg_color = (60, 80, 120) if i == selected_index else (40, 40, 55)
                border_color = (200, 200, 255) if i == selected_index else (80, 80, 100)

                pygame.draw.rect(surface, bg_color, rect, border_radius=6)
                pygame.draw.rect(surface, border_color, rect, 2, border_radius=6)

                agenda_type = card.get("agenda_type", "?")
                name_text = self.font.render(agenda_type.title(), True, (220, 220, 240))
                surface.blit(name_text, (cx + card_w // 2 - name_text.get_width() // 2, y + 10))

                # Card image (if available)
                img = card_images.get(agenda_type)
                desc_y = y + 38
                if img:
                    img_x = cx + card_w // 2 - img.get_width() // 2
                    img_y = y + 30
                    surface.blit(img, (img_x, img_y))
                    desc_y = y + 30 + img.get_height() + 4
                    mod_count = modifiers.get(agenda_type, 0)
                    if mod_count > 0 or show_preview_plus:
                        plus_size = max(10, img.get_height() // 3)
                        plus_font = self._get_font(plus_size)
                        plus_x = cx + 3  # left margin of card, clear of the centered image
                        for k in range(mod_count):
                            plus_surf = plus_font.render("+", True, (255, 255, 255))
                            surface.blit(plus_surf, (plus_x, img_y + 2 + k * (plus_size + 2)))
                        if show_preview_plus:
                            faded_surf = plus_font.render("+", True, (255, 255, 255))
                            faded_surf.set_alpha(70)
                            surface.blit(faded_surf, (plus_x, img_y + 2 + mod_count * (plus_size + 2)))

                # Detailed description (custom or auto-generated)
                desc_lines = card.get("description") or self._build_card_description(
                    agenda_type, modifiers, is_spoils=is_spoils, territories=territories)
                for j, line in enumerate(desc_lines):
                    desc_text = effect_font.render(line, True, (160, 170, 190))
                    surface.blit(desc_text, (cx + card_w // 2 - desc_text.get_width() // 2, desc_y + j * 15))

        return rects

    def draw_event_log(self, surface: pygame.Surface, events: list[str],
                       x: int, y: int, width: int, height: int,
                       scroll_offset: int = 0,
                       highlight_log_idx: int = None,
                       h_scroll_offset: int = 0,
                       enlarged: bool = False):
        """Draw scrollable event log."""
        panel_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(surface, (20, 20, 30), panel_rect, border_radius=4)
        pygame.draw.rect(surface, (60, 60, 80), panel_rect, 1, border_radius=4)

        header = self.small_font.render("Event Log", True, (150, 150, 170))
        surface.blit(header, (x + 8, y + 4))

        # Expand/collapse toggle button
        toggle_label = "\u25bc" if enlarged else "\u25b2"
        toggle_surf = self.small_font.render(toggle_label, True, (120, 120, 160))
        toggle_x = x + width - toggle_surf.get_width() - 8
        toggle_y = y + 4
        self.event_log_expand_rect = pygame.Rect(toggle_x - 2, toggle_y - 2,
                                                  toggle_surf.get_width() + 4,
                                                  toggle_surf.get_height() + 4)
        pygame.draw.rect(surface, (40, 40, 55), self.event_log_expand_rect, border_radius=2)
        surface.blit(toggle_surf, (toggle_x, toggle_y))

        visible_count = (height - 26) // 16
        total = len(events)

        # Slice events using scroll_offset (offset scrolls up from bottom)
        if scroll_offset > 0:
            end = total - scroll_offset
            start = max(0, end - visible_count)
        else:
            start = max(0, total - visible_count)
            end = total
        visible_events = events[start:end]

        # Clamp horizontal scroll to the width of the longest visible line
        available_width = width - 16
        max_text_width = max((self.small_font.size(t)[0] for t in visible_events), default=0)
        max_h_offset = max(0, max_text_width - available_width)
        h_scroll_offset = min(h_scroll_offset, max_h_offset)

        clip_rect = pygame.Rect(x + 4, y + 22, width - 8, height - 26)
        surface.set_clip(clip_rect)

        dy = y + 22
        for i, event_text in enumerate(visible_events):
            abs_index = start + i
            # Highlight background if this entry matches the highlighted log index
            if highlight_log_idx is not None and abs_index == highlight_log_idx:
                hl_rect = pygame.Rect(x + 4, dy, width - 8, 16)
                pygame.draw.rect(surface, (80, 75, 20), hl_rect)
                text = self.small_font.render(event_text, True, (255, 240, 150))
            else:
                text = self.small_font.render(event_text, True, (160, 160, 180))
            surface.blit(text, (x + 8 - h_scroll_offset, dy))
            dy += 16

        surface.set_clip(None)

        # Vertical scroll indicators (right edge)
        if total > visible_count:
            indicator_x = x + width - 14
            if scroll_offset < total - visible_count:
                # Can scroll up (older events)
                arrow_up = self.small_font.render("\u25b2", True, (120, 120, 150))
                surface.blit(arrow_up, (indicator_x, y + 22))
            if scroll_offset > 0:
                # Can scroll down (newer events)
                arrow_down = self.small_font.render("\u25bc", True, (120, 120, 150))
                surface.blit(arrow_down, (indicator_x, y + height - 18))

        # Horizontal scroll indicators (bottom edge)
        if max_h_offset > 0:
            if h_scroll_offset > 0:
                arrow_left = self.small_font.render("\u25c4", True, (120, 120, 150))
                surface.blit(arrow_left, (x + 4, y + height - 18))
            if h_scroll_offset < max_h_offset:
                arrow_right = self.small_font.render("\u25ba", True, (120, 120, 150))
                surface.blit(arrow_right, (x + width - 26, y + height - 18))

    def draw_waiting_overlay(self, surface: pygame.Surface, waiting_for: list[str],
                             spirits: dict, x: int = None, y: int = None):
        """Draw overlay showing who we're waiting for."""
        if not waiting_for:
            return
        names = [spirits.get(sid, {}).get("name", sid[:6]) for sid in waiting_for]
        text = f"Waiting for: {', '.join(names)}"
        text_surf = self.font.render(text, True, (200, 200, 100))
        if x is None:
            x = surface.get_width() // 2 - text_surf.get_width() // 2
        if y is None:
            y = 102
        surface.blit(text_surf, (x, y))
