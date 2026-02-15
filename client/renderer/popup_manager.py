"""Pinnable popup system with nested hover regions."""

import pygame


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

    tip_x = anchor_x - tip_w // 2
    screen_w = surface.get_width()
    if tip_x < 4:
        tip_x = 4
    if tip_x + tip_w > screen_w - 4:
        tip_x = screen_w - 4 - tip_w

    if below:
        tip_y = anchor_y + 4
    else:
        tip_y = anchor_y - tip_h - 4

    tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
    pygame.draw.rect(surface, (40, 40, 50), tip_rect, border_radius=4)
    pygame.draw.rect(surface, (150, 150, 100), tip_rect, 1, border_radius=4)
    for i, surf in enumerate(rendered):
        surface.blit(surf, (tip_x + 8, tip_y + 6 + i * line_h))


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
                    surface_w: int, below: bool = False):
        """Word-wrap text, compute popup rect and keyword rects, push to stack."""
        lines = _wrap_text(text, font, max_width)
        if not lines:
            return
        line_h = font.get_linesize()
        rendered_widths = [font.size(line)[0] for line in lines]
        content_w = max(rendered_widths) if rendered_widths else 0
        tip_w = content_w + 16
        tip_h = len(lines) * line_h + 12

        tip_x = anchor_x - tip_w // 2
        if tip_x < 4:
            tip_x = 4
        if tip_x + tip_w > surface_w - 4:
            tip_x = surface_w - 4 - tip_w

        if below:
            tip_y = anchor_y + 4
        else:
            tip_y = anchor_y - tip_h - 4

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

        # Check if click inside any popup -> absorb
        for p in reversed(self._stack):
            if p.rect.collidepoint(mx, my):
                return

        # Click outside all popups -> close all
        self.close_all()

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
                            _draw_plain_tooltip(
                                surface, font, region.tooltip_text,
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
            # Underline
            underline_y = y + line_h - 2
            pygame.draw.line(surface, color,
                             (cursor_x, underline_y),
                             (cursor_x + surf.get_width(), underline_y), 1)
            cursor_x += surf.get_width()
            pos = seg_end

        # Remaining normal text
        if pos < len(line):
            normal_text = line[pos:]
            surf = font.render(normal_text, True, normal_color)
            surface.blit(surf, (cursor_x, y))
