"""Tutorial system: guided overlay for first-time players."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import pygame


@dataclass
class TutorialStep:
    title: str
    text: str
    button_label: str | None  # "Continue", "Finish", or None (game_confirm — no button)
    highlights: list[str] = field(default_factory=list)
    action_gate: str | None = None  # "select_faction" | "click_delta" | "guidance_select"


class TutorialManager:
    # Tutorial panel position / size (safe zone: x=313–965, y=565–740)
    _PX = 313
    _PY = 565
    _PW = 652
    _PH_MAX = 175

    # Colors
    _BG_COLOR = (20, 20, 35, 230)
    _BORDER_COLOR = (200, 180, 100)
    _TITLE_COLOR = (220, 190, 110)
    _TEXT_COLOR = (200, 200, 220)
    _BTN_ENABLED = (60, 130, 60)
    _BTN_DISABLED = (60, 60, 65)
    _BTN_FINISH = (130, 60, 60)

    def __init__(self):
        self.active = False
        self.step_idx = -1
        self._shown = False
        self.action_satisfied = False
        self.block_animations = False
        self.block_phase_ui = False
        self.first_time_triggers_enabled = False
        self.fired_triggers: set[str] = set()
        self.popup_step: TutorialStep | None = None
        self.popup_ok_rect: pygame.Rect | None = None
        self._popup_panel_rect: pygame.Rect | None = None
        self.exposed_rects: dict[str, pygame.Rect] = {}
        self._continue_rect: pygame.Rect | None = None
        self._dynamic_text: str | None = None

        # Internal flow flags
        self._step_pending_show = False   # step is waiting for a trigger before shown
        self._expecting_phase_result = False  # guards animations_done for step 10

        self._steps = self._build_steps()

    # ------------------------------------------------------------------ #
    # Step definitions  (16 steps: 0–15)
    # ------------------------------------------------------------------ #

    def _build_steps(self) -> list[TutorialStep]:
        return [
            # Step 0: history (blocking)
            TutorialStep(
                title="Turn 1: History of the World",
                text=(
                    "Before any Spirit can act, the first turn plays out automatically — "
                    "factions expand, trade, and establish the shape of the world. "
                    "Think of it as ancient history.\n\n"
                    "Watch how the world forms, then we'll talk about how you fit in."
                ),
                button_label="Continue",
            ),
            # Step 1: spirit panel (pending show: animations_done after turn-1)
            TutorialStep(
                title="Your Spirit",
                text=(
                    "The panel in the right column is your Spirit panel. It shows your name, "
                    "current Influence, which Faction you're guiding, and the Factions that "
                    "Worship you — earning you VP each turn."
                ),
                button_label="Continue",
                highlights=["spirit_panel"],
            ),
            # Step 2: event log
            TutorialStep(
                title="Event Log",
                text=(
                    "The event log in the bottom-right records everything that happens: "
                    "guidance, agendas, wars, scoring. Scroll it with the mouse wheel.\n\n"
                    "Later, clicking colored delta chips [+2] in faction panels will "
                    "highlight the event that caused them."
                ),
                button_label="Continue",
                highlights=["event_log"],
            ),
            # Step 3: factions (action gate: select_faction)
            TutorialStep(
                title="Factions",
                text=(
                    "Six Factions compete for territory on the map. Click any Faction's "
                    "section on the ribbon above, their hexes on the map, or their name "
                    "on the guidance list to the left to open their info panel.\n\n"
                    "Try it now — select any Faction."
                ),
                button_label="Continue",
                highlights=["ribbon", "guidance_btns"],
                action_gate="select_faction",
            ),
            # Step 4: regard and gold (highlight faction info panel)
            TutorialStep(
                title="Regard and Gold",
                text=(
                    "This Faction's panel shows their Gold (funding for Expand actions) "
                    "and Regard — how warmly they view each neighboring Faction.\n\n"
                    "Regard of -2 or lower with a neighbor triggers a War. "
                    "Gold cannot go below 0."
                ),
                button_label="Continue",
                highlights=["faction_info"],
            ),
            # Step 5: tracking changes (action gate: click_delta)
            TutorialStep(
                title="Tracking Changes",
                text=(
                    "The colored [+2] and [-1] chips next to values show what changed last turn.\n\n"
                    "Click one of those chips now to highlight the event in the log that "
                    "caused the change."
                ),
                button_label="Continue",
                action_gate="click_delta",
            ),
            # Step 6: guidance and worship (action gate: guidance_select)
            TutorialStep(
                title="Guidance and Worship",
                text=(
                    "Each turn you choose one Faction to Guide from the list on the left. "
                    "Guiding makes that Faction Worship you, which earns VP.\n\n"
                    "A Faction that Worships you cannot be Guided by you again — another Spirit "
                    "must usurp their Worship first (by having at least as many Idols in that "
                    "Faction's territory).\n\nSelect a Faction to Guide now."
                ),
                button_label="Continue",
                highlights=["guidance_btns"],
                action_gate="guidance_select",
            ),
            # Step 7: agenda types (pending show: agenda_phase_started)
            TutorialStep(
                title="Agenda Types",
                text=(
                    "Each turn, every Faction plays one Agenda card from their pool:\n"
                    "  Trade — gain gold and regard with other Traders\n"
                    "  Steal — drain gold from neighbors, risking War\n"
                    "  Expand — spend gold to claim a neutral hex\n"
                    "  Change — draw a modifier that permanently boosts an Agenda type\n\n"
                    "Factions are not controlled directly; their AI picks the best card "
                    "from their pool."
                ),
                button_label="Continue",
            ),
            # Step 8: modifiers (shown immediately after step 7 Continue)
            TutorialStep(
                title="Modifiers and Habitats",
                text=(
                    "Each Faction starts with Change modifiers based on their Habitat — "
                    "see the modifier icons on each faction's ribbon section.\n\n"
                    "Modifiers permanently increase the power of a specific Agenda. "
                    "On the left, your Guided Faction's cards show these modifiers applied."
                ),
                button_label="Continue",
            ),
            # Step 9: agenda resolution (pending show: agenda_phase_started refire; game_confirm)
            TutorialStep(
                title="Agenda Resolution",
                text=(
                    "Choose an Agenda card from the list on the left. "
                    "Each card shows what the Faction will do this turn.\n\n"
                    "Click Confirm when you've made your selection."
                ),
                button_label=None,  # game_confirm: player clicks game Confirm
            ),
            # Step 10: watch and learn (pending show: animations_done after agenda phase)
            TutorialStep(
                title="Watch and Learn",
                text=(
                    "That was Turn 2's Agenda phase. Look at what changed in the "
                    "Event Log and Faction panels. You can click delta chips to "
                    "trace changes back to their cause.\n\nClick Continue when you're ready."
                ),
                button_label="Continue",
            ),
            # Step 11: influence (pending show: agenda_phase_started turn 3; game_confirm)
            TutorialStep(
                title="Influence",
                text=(
                    "Your Influence drops by 1 each turn you guide a Faction. "
                    "Higher Influence means more Agenda cards to choose from.\n\n"
                    "When Influence reaches 0, you'll be ejected from the Faction.\n\n"
                    "Choose an Agenda and click Confirm."
                ),
                button_label=None,  # game_confirm
            ),
            # Step 12: final choice (pending show: agenda_phase_started turn 4; game_confirm)
            TutorialStep(
                title="Final Choice",
                text=(
                    "This is your last Agenda choice before you're ejected from this Faction. "
                    "After you play an Agenda, your Influence will drop to 0.\n\n"
                    "Choose carefully, then click Confirm."
                ),
                button_label=None,  # game_confirm
            ),
            # Step 13: ejection / agenda pool (pending show: ejection_phase_started; game_confirm)
            TutorialStep(
                title="Agenda Pool",
                text=(
                    "You've been ejected! But you get to leave a mark — replace one card "
                    "in this Faction's Agenda pool.\n\n"
                    "Remove one Agenda type and add another; this permanently shapes what "
                    "Agendas this Faction can draw in the future.\n\n"
                    "Select a card to remove and a card to add, then click Confirm."
                ),
                button_label=None,  # game_confirm
            ),
            # Step 14: worship recap (blocking)
            TutorialStep(
                title="Worship Recap",
                text=(
                    "Remember: a Faction that Worships you cannot be Guided by you. "
                    "But it still earns you VP.\n\n"
                    "To usurp Worship, another Spirit must guide that Faction AND have "
                    "at least as many Idols in its territory. Until then, you keep "
                    "earning from their Worship."
                ),
                button_label="Continue",
            ),
            # Step 15: good luck (Finish)
            TutorialStep(
                title="Good Luck",
                text=(
                    "That's the core of Impetus! From here on, you'll learn by doing — "
                    "some mechanics (Wars, contested Guidance) will be explained the "
                    "first time they occur.\n\n"
                    "First to 100 VP wins. The AI is quite basic, so this is a chance "
                    "to practice.\n\nGood luck, Spirit."
                ),
                button_label="Finish",
            ),
        ]

    # ------------------------------------------------------------------ #
    # Hard-blocking steps: block all game input when panel is shown
    # ------------------------------------------------------------------ #

    _HARD_BLOCKING_STEPS = frozenset({0, 1, 2, 4, 7, 8, 10, 14, 15})

    def is_hard_blocking(self) -> bool:
        if not self.active or not self._shown:
            return False
        return self.step_idx in self._HARD_BLOCKING_STEPS

    def is_blocking_animations(self) -> bool:
        return self.block_animations

    def is_blocking_phase_ui(self) -> bool:
        return self.block_phase_ui

    # ------------------------------------------------------------------ #
    # Activation
    # ------------------------------------------------------------------ #

    def activate(self):
        self.active = True
        self.step_idx = 0
        self._shown = True
        self.action_satisfied = False
        self.block_animations = True   # step 0 blocks animations until Continue
        self.block_phase_ui = False
        self.first_time_triggers_enabled = False
        self.fired_triggers = set()
        self.popup_step = None
        self.popup_ok_rect = None
        self._popup_panel_rect = None
        self._step_pending_show = False
        self._expecting_phase_result = False
        self._dynamic_text = None

    # ------------------------------------------------------------------ #
    # State transitions
    # ------------------------------------------------------------------ #

    def _advance_to(self, new_idx: int):
        self.step_idx = new_idx
        self.action_satisfied = False
        self._dynamic_text = None

        if new_idx >= len(self._steps):
            self.active = False
            self._shown = False
            self._step_pending_show = False
            return

        # Steps that need an external trigger before showing
        if new_idx in (1, 7, 9, 10, 11, 12, 13):
            self._shown = False
            self._step_pending_show = True
        else:
            self._shown = True
            self._step_pending_show = False

    # ------------------------------------------------------------------ #
    # Input handling
    # ------------------------------------------------------------------ #

    def handle_click(self, pos) -> bool:
        if not self.active:
            return False

        # Popup Ok button (first-time triggers)
        if self.popup_step is not None:
            if self.popup_ok_rect and self.popup_ok_rect.collidepoint(pos):
                self.popup_step = None
                self.popup_ok_rect = None
                self._popup_panel_rect = None
                return True
            if self._popup_panel_rect and self._popup_panel_rect.collidepoint(pos):
                return True
            return False

        # Main Continue / Finish button
        if self._shown and self._continue_rect and self._continue_rect.collidepoint(pos):
            step = self._steps[self.step_idx]
            if step.button_label in ("Continue", "Finish"):
                if self._can_advance_now():
                    self._on_continue_clicked()
            return True

        # Hard-blocking: swallow all other clicks
        if self.is_hard_blocking():
            return True

        return False

    def _can_advance_now(self) -> bool:
        step = self._steps[self.step_idx]
        if step.action_gate is not None:
            return self.action_satisfied
        return True

    def _on_continue_clicked(self):
        idx = self.step_idx
        if idx == 0:
            # Release animation block; step 1 shows after animations complete
            self.block_animations = False
            self._advance_to(1)
        elif idx in (1, 2, 3, 4, 5):
            self._advance_to(idx + 1)
        elif idx == 6:
            # Step 7 is pending; shows when agenda_phase_started fires
            self._advance_to(7)
        elif idx == 7:
            self._advance_to(8)
        elif idx == 8:
            # Step 9 is pending; shows when agenda_phase_started fires (via refire)
            self._advance_to(9)
        elif idx == 10:
            # Release phase UI block; turn 3 vagrant phase can now appear
            self.block_phase_ui = False
            self._advance_to(11)
        elif idx == 14:
            self._advance_to(15)
        elif idx == 15:
            self.active = False
            self._shown = False

    # ------------------------------------------------------------------ #
    # Game event / action notifications
    # ------------------------------------------------------------------ #

    def notify_action(self, action_type: str, data: dict):
        if not self.active:
            return
        idx = self.step_idx

        if action_type == "faction_selected":
            if idx == 3 and not self.action_satisfied:
                self.action_satisfied = True

        elif action_type == "delta_clicked":
            if idx == 5 and not self.action_satisfied:
                self.action_satisfied = True

        elif action_type == "guidance_selected":
            if idx == 6 and not self.action_satisfied:
                self.action_satisfied = True

        elif action_type == "agenda_submitted":
            if idx == 9:
                self.first_time_triggers_enabled = True
                # Block next vagrant phase until step 10 Continue
                self.block_phase_ui = True
                self._expecting_phase_result = True
                self._advance_to(10)
            elif idx == 11:
                self._advance_to(12)
            elif idx == 12:
                self._advance_to(13)

        elif action_type == "ejection_submitted":
            if idx == 13:
                self._advance_to(14)

    def notify_game_event(self, event_type: str, data: dict):
        if not self.active:
            return
        idx = self.step_idx

        if event_type == "phase_result_received":
            self._expecting_phase_result = False

        elif event_type == "animations_done":
            # Step 1: show after turn-1 animations
            if idx == 1 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True
            # Step 10: show after turn-2 agenda animations (guarded by _expecting)
            elif idx == 10 and self._step_pending_show and not self._expecting_phase_result:
                self._step_pending_show = False
                self._shown = True
                # block_phase_ui is already True (set at agenda_submitted)

        elif event_type == "agenda_phase_started":
            draw_count = data.get("draw_count", 2)
            if idx == 7 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True
            elif idx == 9 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True
            elif idx == 11 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True
                self._dynamic_text = (
                    f"Your Influence drops by 1 each turn you guide a Faction. "
                    f"Higher Influence means more Agenda cards to choose from.\n\n"
                    f"You're now drawing {draw_count} cards. "
                    f"When Influence reaches 0, you'll be ejected.\n\n"
                    f"Choose an Agenda and click Confirm."
                )
            elif idx == 12 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True

        elif event_type == "ejection_phase_started":
            if idx == 13 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True

        elif event_type == "war_erupted":
            if (self.first_time_triggers_enabled
                    and "war_erupted" not in self.fired_triggers):
                self.fired_triggers.add("war_erupted")
                self.popup_step = TutorialStep(
                    title="A War Has Erupted!",
                    text=(
                        "A War has erupted between two Factions!\n\n"
                        "Wars erupt when Regard between neighbors drops to -2 or below "
                        "after a Steal agenda. A new War is 'green'; it ripens at the end "
                        "of the turn and resolves at the end of the NEXT turn.\n\n"
                        "When a War resolves, both sides roll a die and add their territory "
                        "count. The winner gains gold and draws Spoils (an extra Agenda). "
                        "The loser loses 1 gold. If the winning Faction is Guided, the "
                        "Spirit chooses which Spoils card to play."
                    ),
                    button_label="Ok",
                )
                self._popup_panel_rect = None

        elif event_type == "guide_contested":
            if (self.first_time_triggers_enabled
                    and "guide_contested" not in self.fired_triggers):
                self.fired_triggers.add("guide_contested")
                self.popup_step = TutorialStep(
                    title="Guidance Contested!",
                    text=(
                        "Two Spirits tried to Guide the same Faction and nobody won!\n\n"
                        "When Spirits contest the same Faction, the Affinity system resolves it: "
                        "a Spirit with the matching Habitat Affinity wins outright. A matching "
                        "Race Affinity wins if no one has Habitat. If neither Spirit holds a "
                        "relevant Affinity, Guidance is Contested — both are blocked from "
                        "targeting that Faction for one full turn.\n\n"
                        "Check your Spirit panel to see your Affinity."
                    ),
                    button_label="Ok",
                )
                self._popup_panel_rect = None

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def render(self, screen: pygame.Surface,
               font: pygame.font.Font,
               small_font: pygame.font.Font):
        if not self.active:
            return

        if self._shown and 0 <= self.step_idx < len(self._steps):
            step = self._steps[self.step_idx]
            self._draw_highlights(screen, step.highlights)

        if self.popup_step is not None:
            self._draw_popup(screen, self.popup_step, font, small_font)

        if self._shown and 0 <= self.step_idx < len(self._steps):
            step = self._steps[self.step_idx]
            text = self._dynamic_text if self._dynamic_text is not None else step.text
            self._draw_panel(screen, step, text, font, small_font)

    # ------------------------------------------------------------------ #
    # Highlight glows
    # ------------------------------------------------------------------ #

    def _draw_highlights(self, screen: pygame.Surface, highlights: list[str]):
        pulse_alpha = int(150 + 80 * math.sin(time.monotonic() * 3.0))
        color = (200, 180, 100)
        for key in highlights:
            if key in ("spirit_panel", "event_log", "faction_info"):
                rect = self.exposed_rects.get(key)
                if rect:
                    self._draw_glow_rect(screen, rect, color, pulse_alpha)
            elif key == "ribbon":
                for rkey, rect in self.exposed_rects.items():
                    if rkey.startswith("ribbon_"):
                        self._draw_glow_rect(screen, rect, color, pulse_alpha)
            elif key == "guidance_btns":
                for rkey, rect in self.exposed_rects.items():
                    if rkey.startswith("guidance_btn_"):
                        self._draw_glow_rect(screen, rect, color, pulse_alpha)

    def _draw_glow_rect(self, screen: pygame.Surface,
                        rect: pygame.Rect, color: tuple, alpha: int):
        surf = pygame.Surface((rect.w + 4, rect.h + 4), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*color, alpha),
                         pygame.Rect(0, 0, rect.w + 4, rect.h + 4), 2)
        screen.blit(surf, (rect.x - 2, rect.y - 2))

    # ------------------------------------------------------------------ #
    # Panel drawing
    # ------------------------------------------------------------------ #

    def _draw_panel(self, screen: pygame.Surface, step: TutorialStep,
                    text: str, font: pygame.font.Font,
                    small_font: pygame.font.Font):
        px, py, pw = self._PX, self._PY, self._PW
        pad = 10
        inner_w = pw - pad * 2

        title_surf = font.render(step.title, True, self._TITLE_COLOR)
        body_lines = self._wrap_text(text, small_font, inner_w)
        body_surfs = [small_font.render(ln, True, self._TEXT_COLOR) for ln in body_lines]

        btn_h = 26
        btn_w = 84
        btn_gap = 6
        show_button = step.button_label is not None

        body_h = sum(s.get_height() + 2 for s in body_surfs)
        content_h = title_surf.get_height() + 4 + body_h
        if show_button:
            content_h += btn_gap + btn_h
        ph = min(content_h + pad * 2, self._PH_MAX)

        overlay = pygame.Surface((pw, ph), pygame.SRCALPHA)
        overlay.fill(self._BG_COLOR)
        screen.blit(overlay, (px, py))
        pygame.draw.rect(screen, self._BORDER_COLOR,
                         pygame.Rect(px, py, pw, ph), 1)

        y = py + pad
        screen.blit(title_surf, (px + pad, y))
        y += title_surf.get_height() + 4

        clip_bottom = py + ph - (btn_h + btn_gap + pad if show_button else pad)
        old_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(px + pad, py + pad, pw - pad * 2, ph - pad * 2))
        for surf in body_surfs:
            if y + surf.get_height() > clip_bottom:
                break
            screen.blit(surf, (px + pad, y))
            y += surf.get_height() + 2
        screen.set_clip(old_clip)

        self._continue_rect = None
        if show_button:
            btn_x = px + pw - btn_w - pad
            btn_y = py + ph - btn_h - pad
            can_advance = self._can_advance_now()
            if step.button_label == "Finish":
                btn_color = self._BTN_FINISH
            elif can_advance:
                btn_color = self._BTN_ENABLED
            else:
                btn_color = self._BTN_DISABLED
            btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
            pygame.draw.rect(screen, btn_color, btn_rect, border_radius=3)
            lbl = small_font.render(step.button_label, True, (230, 230, 230))
            screen.blit(lbl, (btn_rect.centerx - lbl.get_width() // 2,
                               btn_rect.centery - lbl.get_height() // 2))
            self._continue_rect = btn_rect

    # ------------------------------------------------------------------ #
    # Popup drawing (first-time triggers)
    # ------------------------------------------------------------------ #

    def _draw_popup(self, screen: pygame.Surface, step: TutorialStep,
                    font: pygame.font.Font, small_font: pygame.font.Font):
        from shared.constants import SCREEN_WIDTH, SCREEN_HEIGHT
        pw = 530
        pad = 12
        inner_w = pw - pad * 2

        title_surf = font.render(step.title, True, self._TITLE_COLOR)
        body_lines = self._wrap_text(step.text, small_font, inner_w)
        body_surfs = [small_font.render(ln, True, self._TEXT_COLOR) for ln in body_lines]

        btn_h = 26
        btn_w = 56
        btn_gap = 8

        content_h = (title_surf.get_height() + 4
                     + sum(s.get_height() + 2 for s in body_surfs)
                     + btn_gap + btn_h)
        ph = content_h + pad * 2
        px = SCREEN_WIDTH // 2 - pw // 2
        py = SCREEN_HEIGHT // 2 - ph // 2

        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 80))
        screen.blit(dim, (0, 0))

        overlay = pygame.Surface((pw, ph), pygame.SRCALPHA)
        overlay.fill(self._BG_COLOR)
        screen.blit(overlay, (px, py))
        pygame.draw.rect(screen, self._BORDER_COLOR,
                         pygame.Rect(px, py, pw, ph), 1)
        self._popup_panel_rect = pygame.Rect(px, py, pw, ph)

        y = py + pad
        screen.blit(title_surf, (px + pad, y))
        y += title_surf.get_height() + 4

        for surf in body_surfs:
            screen.blit(surf, (px + pad, y))
            y += surf.get_height() + 2

        btn_x = px + pw - btn_w - pad
        btn_y = py + ph - btn_h - pad
        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        pygame.draw.rect(screen, self._BTN_ENABLED, btn_rect, border_radius=3)
        lbl = small_font.render("Ok", True, (230, 230, 230))
        screen.blit(lbl, (btn_rect.centerx - lbl.get_width() // 2,
                           btn_rect.centery - lbl.get_height() // 2))
        self.popup_ok_rect = btn_rect

    # ------------------------------------------------------------------ #
    # Text wrapping
    # ------------------------------------------------------------------ #

    def _wrap_text(self, text: str, font: pygame.font.Font, max_w: int) -> list[str]:
        result = []
        for para in text.split("\n"):
            if not para.strip():
                result.append("")
                continue
            words = para.split(" ")
            line = ""
            for word in words:
                candidate = (line + " " + word).strip()
                if font.size(candidate)[0] <= max_w:
                    line = candidate
                else:
                    if line:
                        result.append(line)
                    line = word
            if line:
                result.append(line)
        return result
