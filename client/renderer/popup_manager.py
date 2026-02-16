"""Pinnable popup system with nested hover regions."""

import pygame

# --- Tooltip placement scoring ---
_WEIGHT_NON_TEXT = 1
_WEIGHT_TEXT = 4

# Module-level registry: list of (rect, weight) tuples.
# Populated each frame by game_scene._register_ui_rects_for_tooltips().
_ui_rects: list[tuple[pygame.Rect, int]] = []


def set_ui_rects(rects: list[tuple[pygame.Rect, int]]):
    """Replace the UI rect registry (called once per frame)."""
    global _ui_rects
    _ui_rects = rects


def _compute_best_position(anchor_x: int, anchor_y: int,
                            tip_w: int, tip_h: int,
                            screen_w: int, screen_h: int,
                            prefer_below: bool = False) -> tuple[int, int]:
    """Pick the best tooltip position from 6 candidates scored by UI overlap."""
    margin = 4
    x_center = anchor_x - tip_w // 2
    x_left = anchor_x - tip_w + 20
    x_right = anchor_x - 20
    y_above = anchor_y - tip_h - margin
    y_below = anchor_y + margin

    def clamp(x, y):
        x = max(margin, min(x, screen_w - margin - tip_w))
        y = max(margin, min(y, screen_h - margin - tip_h))
        return (x, y)

    # Generate and deduplicate candidates
    raw = []
    for yv in (y_above, y_below):
        for xv in (x_center, x_left, x_right):
            raw.append(clamp(xv, yv))
    seen = set()
    candidates = []
    for pos in raw:
        if pos not in seen:
            seen.add(pos)
            candidates.append(pos)

    if not _ui_rects or len(candidates) == 1:
        # No UI rects registered or only one option — use prefer_below logic
        if prefer_below:
            return clamp(x_center, y_below)
        return clamp(x_center, y_above)

    def score(pos):
        tip_rect = pygame.Rect(pos[0], pos[1], tip_w, tip_h)
        total = 0
        for ui_rect, weight in _ui_rects:
            overlap = tip_rect.clip(ui_rect)
            total += overlap.w * overlap.h * weight
        # Tiebreaker: prefer the side indicated by prefer_below
        is_below = pos[1] > anchor_y
        if is_below != prefer_below:
            total += 0.5  # tiny nudge
        return total

    return min(candidates, key=score)


class HoverRegion:
    """A keyword in a popup that can show/pin a sub-tooltip."""
    __slots__ = ("keyword", "tooltip_text", "sub_regions")

    def __init__(self, keyword: str, tooltip_text: str,
                 sub_regions: list["HoverRegion"] | None = None):
        self.keyword = keyword
        self.tooltip_text = tooltip_text
        self.sub_regions = sub_regions or []


class PinnedPopup:
    """A pinned popup on screen."""
    __slots__ = ("text", "lines", "rect", "hover_regions",
                 "keyword_rects", "hovered_keyword", "max_width")

    def __init__(self, text: str, lines: list[str], rect: pygame.Rect,
                 hover_regions: list[HoverRegion],
                 keyword_rects: dict[str, list[pygame.Rect]],
                 max_width: int):
        self.text = text
        self.lines = lines
        self.rect = rect
        self.hover_regions = hover_regions
        self.keyword_rects = keyword_rects
        self.hovered_keyword = None
        self.max_width = max_width


def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
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


def _draw_plain_tooltip(surface: pygame.Surface, font: pygame.font.Font,
                        text: str, anchor_x: int, anchor_y: int,
                        max_width: int = 350, below: bool = False):
    """Draw a simple multi-line tooltip box."""
    lines = _wrap_text(text, font, max_width)
    if not lines:
        return
    line_h = font.get_linesize()
    rendered = [font.render(line, True, (255, 220, 150)) for line in lines]
    content_w = max(s.get_width() for s in rendered)
    tip_w = content_w + 16
    tip_h = len(lines) * line_h + 12

    tip_x, tip_y = _compute_best_position(
        anchor_x, anchor_y, tip_w, tip_h,
        surface.get_width(), surface.get_height(),
        prefer_below=below,
    )

    tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
    pygame.draw.rect(surface, (40, 40, 50), tip_rect, border_radius=4)
    pygame.draw.rect(surface, (150, 150, 100), tip_rect, 1, border_radius=4)
    for i, surf in enumerate(rendered):
        surface.blit(surf, (tip_x + 8, tip_y + 6 + i * line_h))


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


def draw_multiline_tooltip_with_regions(surface: pygame.Surface, font: pygame.font.Font,
                                        text: str, hover_regions: list[HoverRegion],
                                        anchor_x: int, anchor_y: int,
                                        max_width: int = 350, below: bool = False):
    """Draw an unpinned tooltip, underlining known nested-hover keywords."""
    lines = _wrap_text(text, font, max_width)
    if not lines:
        return

    line_h = font.get_linesize()
    rendered_widths = [font.size(line)[0] for line in lines]
    content_w = max(rendered_widths) if rendered_widths else 0
    tip_w = content_w + 16
    tip_h = len(lines) * line_h + 12

    tip_x, tip_y = _compute_best_position(
        anchor_x, anchor_y, tip_w, tip_h,
        surface.get_width(), surface.get_height(),
        prefer_below=below,
    )

    tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
    pygame.draw.rect(surface, (40, 40, 50), tip_rect, border_radius=4)
    pygame.draw.rect(surface, (150, 150, 100), tip_rect, 1, border_radius=4)

    keywords = [region.keyword for region in hover_regions]
    text_x = tip_x + 8
    text_y = tip_y + 6
    for line_idx, line in enumerate(lines):
        y = text_y + line_idx * line_h
        _render_rich_line_with_keywords(
            surface, font, line, text_x, y,
            keywords=keywords,
            normal_color=(255, 220, 150),
            keyword_color=(100, 220, 210),
        )


class PopupManager:
    """Manages a stack of pinned popup tooltips with nested hover regions."""

    def __init__(self):
        self._stack: list[PinnedPopup] = []

    def has_popups(self) -> bool:
        return bool(self._stack)

    def close_all(self):
        self._stack.clear()

    def handle_escape(self):
        self._stack.clear()

    def pin_tooltip(self, text: str, hover_regions: list[HoverRegion],
                    anchor_x: int, anchor_y: int,
                    font: pygame.font.Font, max_width: int,
                    surface_w: int, below: bool = False,
                    surface_h: int = 800):
        """Word-wrap text, compute popup rect and keyword rects, push to stack."""
        lines = _wrap_text(text, font, max_width)
        if not lines:
            return
        line_h = font.get_linesize()
        rendered_widths = [font.size(line)[0] for line in lines]
        content_w = max(rendered_widths) if rendered_widths else 0
        tip_w = content_w + 16
        tip_h = len(lines) * line_h + 12

        tip_x, tip_y = _compute_best_position(
            anchor_x, anchor_y, tip_w, tip_h,
            surface_w, surface_h,
            prefer_below=below,
        )

        rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)

        # Compute keyword rects
        keyword_rects: dict[str, list[pygame.Rect]] = {}
        for region in hover_regions:
            kw = region.keyword
            rects = []
            for line_idx, line in enumerate(lines):
                start = 0
                while True:
                    pos = line.find(kw, start)
                    if pos < 0:
                        break
                    prefix_w = font.size(line[:pos])[0]
                    kw_w = font.size(kw)[0]
                    kw_x = tip_x + 8 + prefix_w
                    kw_y = tip_y + 6 + line_idx * line_h
                    rects.append(pygame.Rect(kw_x, kw_y, kw_w, line_h))
                    start = pos + len(kw)
            if rects:
                keyword_rects[kw] = rects

        popup = PinnedPopup(
            text=text, lines=lines, rect=rect,
            hover_regions=hover_regions,
            keyword_rects=keyword_rects,
            max_width=max_width,
        )
        self._stack.append(popup)

    def update_hover(self, mouse_pos: tuple[int, int]):
        """Update hovered_keyword on topmost popup only."""
        if not self._stack:
            return
        popup = self._stack[-1]
        popup.hovered_keyword = None
        mx, my = mouse_pos
        for kw, rects in popup.keyword_rects.items():
            for r in rects:
                if r.collidepoint(mx, my):
                    popup.hovered_keyword = kw
                    return

    def handle_right_click(self, mouse_pos: tuple[int, int],
                           font: pygame.font.Font, surface_w: int):
        """Handle right-click when popups are open."""
        if not self._stack:
            return
        mx, my = mouse_pos
        popup = self._stack[-1]
        # Refresh hover state from click position so right-click behavior
        # does not depend on a prior mouse-move event.
        popup.hovered_keyword = None
        for kw, rects in popup.keyword_rects.items():
            if any(r.collidepoint(mx, my) for r in rects):
                popup.hovered_keyword = kw
                break

        # Check if clicking on a hovered keyword -> pin sub-popup
        if popup.hovered_keyword:
            for region in popup.hover_regions:
                if region.keyword == popup.hovered_keyword:
                    anchor_rect = None
                    for r in popup.keyword_rects.get(region.keyword, []):
                        if r.collidepoint(mx, my):
                            anchor_rect = r
                            break
                    if anchor_rect:
                        self.pin_tooltip(
                            region.tooltip_text, region.sub_regions,
                            anchor_x=anchor_rect.centerx,
                            anchor_y=anchor_rect.bottom,
                            font=font, max_width=popup.max_width,
                            surface_w=surface_w, below=True,
                        )
                    return

        # Non-keyword right-click closes only the newest popup.
        self._stack.pop()

    def render(self, surface: pygame.Surface, font: pygame.font.Font):
        """Draw all pinned popups and transient keyword hover tooltip."""
        normal_color = (255, 220, 150)
        keyword_color = (100, 220, 210)
        keyword_hover_color = (140, 255, 245)

        for popup in self._stack:
            # Background
            pygame.draw.rect(surface, (40, 40, 50), popup.rect, border_radius=4)
            pygame.draw.rect(surface, (150, 150, 100), popup.rect, 1,
                             border_radius=4)

            line_h = font.get_linesize()
            text_x = popup.rect.x + 8
            text_y = popup.rect.y + 6

            # Build keyword lookup for this popup
            keyword_set = {}
            for region in popup.hover_regions:
                keyword_set[region.keyword] = region

            for line_idx, line in enumerate(popup.lines):
                y = text_y + line_idx * line_h
                self._render_rich_line(
                    surface, font, line, text_x, y,
                    keyword_set, popup.hovered_keyword,
                    normal_color, keyword_color, keyword_hover_color,
                )

        # Draw transient hover tooltip for hovered keyword on topmost popup
        if self._stack:
            popup = self._stack[-1]
            if popup.hovered_keyword:
                for region in popup.hover_regions:
                    if region.keyword == popup.hovered_keyword:
                        rects = popup.keyword_rects.get(region.keyword, [])
                        if rects:
                            mx, my = pygame.mouse.get_pos()
                            anchor = rects[0]
                            for r in rects:
                                if r.collidepoint(mx, my):
                                    anchor = r
                                    break
                            # Use keyword-aware rendering for transient sub-tooltips
                            # so nested hover affordances are visible before pinning.
                            draw_multiline_tooltip_with_regions(
                                surface, font, region.tooltip_text, region.sub_regions,
                                anchor_x=anchor.centerx,
                                anchor_y=anchor.bottom,
                                max_width=popup.max_width,
                                below=True,
                            )
                        break

    def _render_rich_line(self, surface, font, line, x, y,
                          keyword_set, hovered_keyword,
                          normal_color, keyword_color, hover_color):
        """Render a line with keyword highlighting and underlines."""
        if not keyword_set:
            surf = font.render(line, True, normal_color)
            surface.blit(surf, (x, y))
            return

        # Find all keyword occurrences, sort by position
        occurrences = []
        for kw in keyword_set:
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

        # Sort by position, remove overlaps
        occurrences.sort(key=lambda o: o[0])
        filtered = []
        last_end = 0
        for seg_start, seg_end, kw in occurrences:
            if seg_start >= last_end:
                filtered.append((seg_start, seg_end, kw))
                last_end = seg_end

        # Render segments
        cursor_x = x
        pos = 0
        line_h = font.get_linesize()
        for seg_start, seg_end, kw in filtered:
            # Normal text before keyword
            if seg_start > pos:
                normal_text = line[pos:seg_start]
                surf = font.render(normal_text, True, normal_color)
                surface.blit(surf, (cursor_x, y))
                cursor_x += surf.get_width()
            # Keyword text
            kw_text = line[seg_start:seg_end]
            is_hovered = (kw == hovered_keyword)
            color = hover_color if is_hovered else keyword_color
            surf = font.render(kw_text, True, color)
            surface.blit(surf, (cursor_x, y))
            # Dotted underline
            underline_y = y + line_h - 2
            ux = cursor_x
            ux_end = cursor_x + surf.get_width()
            while ux < ux_end:
                dot_end = min(ux + 2, ux_end)
                pygame.draw.line(surface, color, (ux, underline_y), (dot_end, underline_y), 1)
                ux += 5
            cursor_x += surf.get_width()
            pos = seg_end

        # Remaining normal text
        if pos < len(line):
            normal_text = line[pos:]
            surf = font.render(normal_text, True, normal_color)
            surface.blit(surf, (cursor_x, y))
