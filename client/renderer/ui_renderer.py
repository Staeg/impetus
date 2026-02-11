"""HUD, cards, faction info panels, phase indicators, event log."""

import pygame
from shared.constants import (
    Phase, AgendaType, IdolType, FACTION_COLORS, FACTION_DISPLAY_NAMES,
    FACTION_NAMES,
)


class Button:
    def __init__(self, rect: pygame.Rect, text: str, color=(80, 80, 120),
                 text_color=(255, 255, 255), hover_color=(100, 100, 150),
                 tooltip: str = None):
        self.rect = rect
        self.text = text
        self.color = color
        self.text_color = text_color
        self.hover_color = hover_color
        self.hovered = False
        self.enabled = True
        self.tooltip = tooltip

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
        """Draw tooltip above the button if disabled and hovered."""
        if not self.tooltip or self.enabled or not self.hovered:
            return
        tip_surf = font.render(self.tooltip, True, (255, 220, 150))
        tip_w = tip_surf.get_width() + 12
        tip_h = tip_surf.get_height() + 8
        tip_x = self.rect.centerx - tip_w // 2
        tip_y = self.rect.top - tip_h - 4
        tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
        pygame.draw.rect(surface, (40, 40, 50), tip_rect, border_radius=4)
        pygame.draw.rect(surface, (150, 150, 100), tip_rect, 1, border_radius=4)
        surface.blit(tip_surf, (tip_x + 6, tip_y + 4))

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

    def _get_font(self, size=16):
        return pygame.font.SysFont("consolas", size)

    @property
    def font(self):
        if self._font is None:
            self._font = self._get_font(16)
        return self._font

    @property
    def small_font(self):
        if self._small_font is None:
            self._small_font = self._get_font(13)
        return self._small_font

    @property
    def title_font(self):
        if self._title_font is None:
            self._title_font = self._get_font(24)
        return self._title_font

    def draw_hud(self, surface: pygame.Surface, phase: str, turn: int,
                 spirits: dict, my_spirit_id: str):
        """Draw the top HUD bar: phase, turn, VP totals."""
        bar_rect = pygame.Rect(0, 0, surface.get_width(), 40)
        pygame.draw.rect(surface, (20, 20, 30), bar_rect)
        pygame.draw.line(surface, (60, 60, 80), (0, 40), (surface.get_width(), 40))

        phase_text = self.font.render(f"Turn {turn} | {phase.replace('_', ' ').title()}", True, (200, 200, 220))
        surface.blit(phase_text, (10, 10))

        # VP display
        x = 300
        for sid, spirit in spirits.items():
            color = (255, 255, 100) if sid == my_spirit_id else (180, 180, 200)
            name = spirit.get("name", sid[:6])
            vp = spirit.get("victory_points", 0)
            faction_id = spirit.get("possessed_faction")

            # Render name
            name_surf = self.small_font.render(name, True, color)
            surface.blit(name_surf, (x, 12))
            x += name_surf.get_width()

            # Render faction tag in faction color
            if faction_id:
                faction_color = FACTION_COLORS.get(faction_id, (150, 150, 150))
                faction_tag = f" [{FACTION_DISPLAY_NAMES.get(faction_id, faction_id)}]"
                tag_surf = self.small_font.render(faction_tag, True, faction_color)
                surface.blit(tag_surf, (x, 12))
                x += tag_surf.get_width()

            # Render VP
            vp_surf = self.small_font.render(f": {vp}VP", True, color)
            surface.blit(vp_surf, (x, 12))
            x += vp_surf.get_width() + 20

    def draw_faction_overview(self, surface: pygame.Surface, factions: dict,
                              faction_agendas: dict[str, str], wars=None,
                              spirits: dict = None,
                              preview_possession: dict = None):
        """Draw a compact overview strip showing all factions' gold, agenda, wars, and presence."""
        spirits = spirits or {}
        strip_y = 42
        strip_h = 42
        sw = surface.get_width()
        cell_w = sw // len(FACTION_NAMES) if FACTION_NAMES else sw

        # Background
        pygame.draw.rect(surface, (15, 15, 22), pygame.Rect(0, strip_y, sw, strip_h))
        pygame.draw.line(surface, (40, 40, 55), (0, strip_y + strip_h),
                         (sw, strip_y + strip_h))

        agenda_colors = {
            "steal": (255, 80, 80),
            "bond": (100, 200, 255),
            "trade": (255, 220, 60),
            "expand": (80, 220, 80),
            "change": (200, 140, 255),
        }

        # Build war lookup: faction_id -> list of (opponent_abbr, is_ripe)
        war_lookup = {}
        if wars:
            for war in wars:
                fa_abbr = FACTION_DISPLAY_NAMES.get(war.faction_a, war.faction_a)
                fb_abbr = FACTION_DISPLAY_NAMES.get(war.faction_b, war.faction_b)
                war_lookup.setdefault(war.faction_a, []).append((fb_abbr, war.is_ripe))
                war_lookup.setdefault(war.faction_b, []).append((fa_abbr, war.is_ripe))

        for i, fid in enumerate(FACTION_NAMES):
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
                abbr = FACTION_DISPLAY_NAMES.get(fid, fid)
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
            abbr = FACTION_DISPLAY_NAMES.get(fid, fid)
            abbr_surf = self.small_font.render(abbr, True, fc)
            surface.blit(abbr_surf, (cx + 6, strip_y + 4))

            # Gold amount
            gold = fd.get("gold", 0) if isinstance(fd, dict) else getattr(fd, "gold", 0)
            gold_text = self.small_font.render(f"{gold}g", True, (255, 220, 60))
            surface.blit(gold_text, (cx + 6 + abbr_surf.get_width() + 6, strip_y + 4))

            # Presence indicator (first row, after gold)
            presence_id = fd.get("presence_spirit") if isinstance(fd, dict) else getattr(fd, "presence_spirit", None)
            possessing_id = fd.get("possessing_spirit") if isinstance(fd, dict) else getattr(fd, "possessing_spirit", None)
            presence_end_x = cx + 6 + abbr_surf.get_width() + 6 + gold_text.get_width()
            if presence_id:
                p_name = spirits.get(presence_id, {}).get("name", presence_id[:6])
                p_surf = self.small_font.render(f" P:{p_name}", True, (100, 200, 180))
                surface.blit(p_surf, (presence_end_x, strip_y + 4))

            # Preview possession indicator (faded, with ? prefix)
            if preview_possession and not possessing_id and fid in preview_possession:
                preview_name = preview_possession[fid]
                pv_surf = self.small_font.render(f" ?{preview_name}", True, (80, 80, 100))
                surface.blit(pv_surf, (presence_end_x + (p_surf.get_width() if presence_id else 0), strip_y + 4))

            # Agenda name (right-aligned)
            agenda_str = faction_agendas.get(fid, "")
            if agenda_str:
                a_label = agenda_str.title()
                a_color = agenda_colors.get(agenda_str, (160, 160, 180))
                a_surf = self.small_font.render(a_label, True, a_color)
                surface.blit(a_surf, (cx + cell_w - a_surf.get_width() - 6, strip_y + 4))

            # War indicators (second row)
            if fid in war_lookup:
                wx = cx + 6
                for opponent_abbr, is_ripe in war_lookup[fid]:
                    war_color = (255, 50, 50) if is_ripe else (180, 60, 60)
                    war_surf = self.small_font.render(f"vs {opponent_abbr}", True, war_color)
                    surface.blit(war_surf, (wx, strip_y + 22))
                    wx += war_surf.get_width() + 6

    def draw_faction_panel(self, surface: pygame.Surface, faction_data: dict,
                           x: int, y: int, width: int = 220, spirits: dict = None,
                           preview_possession: dict = None):
        """Draw faction info panel."""
        if not faction_data:
            return

        fid = faction_data.get("faction_id", "")
        color = tuple(faction_data.get("color", (150, 150, 150)))
        gold = faction_data.get("gold", 0)
        territories = faction_data.get("territories", [])
        regard = faction_data.get("regard", {})
        modifiers = faction_data.get("change_modifiers", {})
        possessing = faction_data.get("possessing_spirit")
        presence = faction_data.get("presence_spirit")

        spirits = spirits or {}
        preview_possession = preview_possession or {}
        possessing_name = spirits.get(possessing, {}).get("name", possessing) if possessing else "none"
        presence_name = spirits.get(presence, {}).get("name", presence) if presence else "none"

        panel_h = 200 + len(regard) * 18
        panel_rect = pygame.Rect(x, y, width, panel_h)
        pygame.draw.rect(surface, (30, 30, 40), panel_rect, border_radius=4)
        pygame.draw.rect(surface, color, panel_rect, 2, border_radius=4)

        dy = y + 8
        name = FACTION_DISPLAY_NAMES.get(fid, fid)
        name_text = self.font.render(name, True, color)
        surface.blit(name_text, (x + 10, dy))
        dy += 24

        if faction_data.get("eliminated", False):
            elim_text = self.font.render("ELIMINATED", True, (200, 60, 60))
            surface.blit(elim_text, (x + 10, dy))
            return

        # Check for preview possession name
        preview_poss_name = preview_possession.get(fid)

        info_lines = [
            ("Gold", f"Gold: {gold}", None),
            ("Territories", f"Territories: {len(territories)}", None),
            ("Possessing", f"Possessing: {possessing_name}",
             f"Possessing: {preview_poss_name}?" if possessing_name == "none" and preview_poss_name else None),
            ("Presence", f"Presence: {presence_name}",
             f"Presence: {preview_poss_name}?" if presence_name == "none" and preview_poss_name else None),
        ]
        for label, line, preview_line in info_lines:
            if preview_line:
                text = self.small_font.render(preview_line, True, (100, 100, 130))
            else:
                text = self.small_font.render(line, True, (180, 180, 200))
            surface.blit(text, (x + 10, dy))
            dy += 18

        if regard:
            dy += 4
            text = self.small_font.render("Regard:", True, (150, 150, 170))
            surface.blit(text, (x + 10, dy))
            dy += 18
            for other_fid, val in regard.items():
                r_color = (100, 255, 100) if val > 0 else (255, 100, 100) if val < 0 else (180, 180, 200)
                other_name = FACTION_DISPLAY_NAMES.get(other_fid, other_fid)
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
                    text = self.small_font.render(f"  {mod}: +{val}", True, (150, 200, 255))
                    surface.blit(text, (x + 10, dy))
                    dy += 18

        # Extra agenda cards
        extra_agendas = faction_data.get("agenda_deck_extra", {})
        if extra_agendas:
            dy += 4
            text = self.small_font.render("Extra Agendas:", True, (150, 150, 170))
            surface.blit(text, (x + 10, dy))
            dy += 18
            for atype, count in extra_agendas.items():
                text = self.small_font.render(f"  {atype}: +{count}", True, (200, 180, 100))
                surface.blit(text, (x + 10, dy))
                dy += 18

    def _build_card_description(self, agenda_type: str, modifiers: dict) -> list[str]:
        """Build detailed description lines for an agenda card based on modifiers."""
        steal_mod = modifiers.get("steal", 0)
        bond_mod = modifiers.get("bond", 0)
        trade_mod = modifiers.get("trade", 0)
        expand_mod = modifiers.get("expand", 0)

        descs = {
            "steal": [
                f"-{1 + steal_mod} regard",
                f"-{1 + steal_mod}g from neighbors",
                "+gold stolen",
                "War at -2 regard",
            ],
            "bond": [
                f"+{1 + bond_mod} regard",
                "with neighbors",
            ],
            "trade": [
                "+1g base",
                f"+{1 + trade_mod}g per trader",
            ],
            "expand": [
                f"Cost: terr-{expand_mod}g",
                "Claim neutral hex",
                f"Fail: +{1 + expand_mod}g",
            ],
            "change": [
                "Draw modifier",
                "card",
            ],
        }
        return descs.get(agenda_type, ["???"])

    def draw_card_hand(self, surface: pygame.Surface, hand: list[dict],
                       selected_index: int, x: int, y: int,
                       modifiers: dict | None = None) -> list[pygame.Rect]:
        """Draw clickable agenda cards. Returns list of card rects."""
        modifiers = modifiers or {}
        rects = []
        card_w, card_h = 110, 170
        spacing = 10
        effect_font = self._get_font(11)

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

            # Detailed description
            desc_lines = self._build_card_description(agenda_type, modifiers)
            for j, line in enumerate(desc_lines):
                desc_text = effect_font.render(line, True, (160, 170, 190))
                surface.blit(desc_text, (cx + card_w // 2 - desc_text.get_width() // 2, y + 38 + j * 15))

        return rects

    def draw_event_log(self, surface: pygame.Surface, events: list[str],
                       x: int, y: int, width: int, height: int,
                       scroll_offset: int = 0):
        """Draw scrollable event log."""
        panel_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(surface, (20, 20, 30), panel_rect, border_radius=4)
        pygame.draw.rect(surface, (60, 60, 80), panel_rect, 1, border_radius=4)

        header = self.small_font.render("Event Log", True, (150, 150, 170))
        surface.blit(header, (x + 8, y + 4))

        visible_count = (height - 26) // 16
        total = len(events)

        # Slice events using scroll_offset (offset scrolls up from bottom)
        if scroll_offset > 0:
            end = total - scroll_offset
            start = max(0, end - visible_count)
            visible_events = events[start:end]
        else:
            visible_events = events[-visible_count:] if total > visible_count else events

        clip_rect = pygame.Rect(x + 4, y + 22, width - 8, height - 26)
        surface.set_clip(clip_rect)

        dy = y + 22
        for event_text in visible_events:
            text = self.small_font.render(event_text, True, (160, 160, 180))
            surface.blit(text, (x + 8, dy))
            dy += 16

        surface.set_clip(None)

        # Scroll indicators
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

    def draw_waiting_overlay(self, surface: pygame.Surface, waiting_for: list[str],
                             spirits: dict):
        """Draw overlay showing who we're waiting for."""
        if not waiting_for:
            return
        names = [spirits.get(sid, {}).get("name", sid[:6]) for sid in waiting_for]
        text = f"Waiting for: {', '.join(names)}"
        text_surf = self.font.render(text, True, (200, 200, 100))
        x = surface.get_width() // 2 - text_surf.get_width() // 2
        surface.blit(text_surf, (x, 92))
