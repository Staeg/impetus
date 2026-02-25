"""Tutorial system: guided overlay for first-time players."""

from __future__ import annotations

import math
import re
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
        self.hide_phase_ui = False
        self.first_time_triggers_enabled = False
        self.fired_triggers: set[str] = set()
        self.popup_step: TutorialStep | None = None
        self.popup_ok_rect: pygame.Rect | None = None
        self._popup_panel_rect: pygame.Rect | None = None
        self.popup_highlights: list[str] = []
        self.highlight_war_arrows: bool = False
        self.exposed_rects: dict[str, pygame.Rect] = {}
        self._continue_rect: pygame.Rect | None = None
        self._return_to_menu_rect: pygame.Rect | None = None
        self.return_to_menu_requested: bool = False
        self._dynamic_text: str | None = None

        # Internal flow flags
        self._step_pending_show = False   # step is waiting for a trigger before shown
        self._expecting_phase_result = False  # guards animations_done for step 12

        # Hover/freeze action gate tracking (step 3)
        self._hover_freeze_done: set[str] = set()

        self._steps = self._build_steps()

    # ------------------------------------------------------------------ #
    # Step definitions  (18 steps: 0–17)
    # ------------------------------------------------------------------ #

    def _build_steps(self) -> list[TutorialStep]:
        return [
            # Step 0: history (hard-blocking)
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
            # Step 1: spirit panel (pending show: animations_done after turn-1; hard-blocking when shown)
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
            # Step 2: event log (hard-blocking)
            TutorialStep(
                title="Event Log",
                text=(
                    "The event log in the bottom-right records everything that happens: "
                    "guidance, agendas, wars, scoring. Scroll it with the mouse wheel "
                    "both vertically and horizontally."
                ),
                button_label="Continue",
                highlights=["event_log"],
            ),
            # Step 3: hover tooltips and right-click freeze (action gate: hover_and_freeze)
            TutorialStep(
                title="Hover Tooltips",
                text=(
                    "Many elements show a tooltip when hovered — try hovering over a Faction "
                    "name, an idol icon, or any panel value.\n\n"
                    "Right-click while hovering to freeze the tooltip in place. "
                    "You can then hover other elements for nested popups.\n"
                    "Right-click again to close the frozen tooltip.\n\n"
                    "Try it: hover something, right-click to freeze it, then right-click "
                    "to unfreeze. Click Continue when done."
                ),
                button_label="Continue",
                action_gate="hover_and_freeze",
            ),
            # Step 4 (was 3): factions (action gate: select_faction; NOT hard-blocking)
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
            # Step 5 (was 4): regard and gold (hard-blocking; highlights faction info panel)
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
            # Step 6 (was 5): tracking changes (action gate: click_delta; NOT hard-blocking)
            TutorialStep(
                title="Tracking Changes",
                text=(
                    "The colored [+2] and [-1] chips next to values show what changed last turn.\n\n"
                    "Click one of those chips now to highlight the event in the log that "
                    "caused the change.\n\n"
                    "If the Faction you selected does not have any of them, select a different one."
                ),
                button_label="Continue",
                action_gate="click_delta",
            ),
            # Step 7 (was 6): guidance and worship (action gate: guidance_select; NOT hard-blocking)
            # Game Confirm is blocked via is_blocking_submit() until Continue is clicked.
            TutorialStep(
                title="Guidance and Worship",
                text=(
                    "Each turn that you start Vagrant (not Guiding a Faction), " 
                    "you choose one Faction to Guide from the list on the left. Guiding a Faction "
                    "for the first time makes them Worship you, which earns Victory Points (VP).\n\n"
                    "Select a new Faction to Guide now."
                ),
                button_label="Continue",
                highlights=["guidance_btns"],
                action_gate="guidance_select",
            ),
            # Step 8 (was 7): idols (shown immediately after step 7 Continue; game_confirm via vagrant submit)
            TutorialStep(
                title="Idols",
                text=(
                    "Alongside Guidance, you may place one Idol on any neutral hex. "
                    "Once in a Faction's territory, they grant VP based on the Idol type:\n"
                    "  Battle — 5 VP per War won\n"
                    "  Affluence — 2 VP per Gold gained\n"
                    "  Spread — 5 VP per Territory claimed\n\n"
                    "These VPs go to whichever Spirit the Faction Worships.\n"
                    "Factions prioritize expanding into hexes with Idols.\n"
                    "Choose an Idol type, click a neutral hex, then click Confirm."
                ),
                button_label=None,  # game_confirm: vagrant submission advances tutorial
            ),
            # Step 9 (was 8): agenda types (pending: agenda_phase_started; hard-blocking)
            TutorialStep(
                title="Agenda Types",
                text=(
                    "Each turn, every Faction plays one Agenda card from their pool:\n"
                    "  Trade — gain gold and regard with other Traders\n"
                    "  Steal — drain gold from neighbors, risking War\n"
                    "  Expand — spend gold to claim a neutral hex\n"
                    "  Change — draw a modifier that permanently boosts an Agenda type\n\n"
                    "Factions play a random Agenda from their pool unless Guided."
                ),
                button_label="Continue",
            ),
            # Step 10 (was 9): modifiers (shown immediately after step 9 Continue; hard-blocking)
            TutorialStep(
                title="Modifiers and Habitats",
                text=(
                    "Each Faction starts with Change modifiers based on their Habitat — "
                    "see the modifier icons on each faction's ribbon section.\n\n"
                    "Modifiers permanently increase the power of a specific Agenda. "
                    "On the left, your Guided Faction's cards show these modifiers with a +."
                ),
                button_label="Continue",
                highlights=["ribbon", "agenda_cards_area"],
            ),
            # Step 11 (was 10): agenda resolution (pending: agenda_phase_started via _refire; game_confirm)
            TutorialStep(
                title="Agenda Resolution",
                text=(
                    "Choose an Agenda card from the list on the left. "
                    "Each card shows what the Faction will do this turn.\n\n"
                    "Click Confirm when you've made your selection."
                ),
                button_label=None,  # game_confirm: player clicks game Confirm
            ),
            # Step 12 (was 11): watch and learn (pending: animations_done after step 11; hard-blocking)
            TutorialStep(
                title="Watch and Learn",
                text=(
                    "That was Turn 2's Agenda phase. Look at what changed in the "
                    "Event Log and Faction panels. You can click delta chips to "
                    "trace changes back to their cause.\n\nClick Continue when you're ready."
                ),
                button_label="Continue",
            ),
            # Step 13 (was 12): influence (pending: agenda_phase_started with draw_count<=3; game_confirm)
            # Shows only once influence has visibly dropped (draw_count < starting 4).
            TutorialStep(
                title="Influence",
                text=(
                    "Your Influence drops by 1 each turn you guide a Faction. "
                    "Higher Influence means more Agenda cards to choose from.\n\n"
                    "When Influence reaches 0, you'll be ejected from the Faction, "
                    "become Vagrant again and Guide a new Faction.\n\n"
                    "Choose an Agenda and click Confirm."
                ),
                button_label=None,  # game_confirm
            ),
            # Step 14 (was 13): final choice (pending: agenda_phase_started with draw_count<=2; game_confirm)
            # Shows only when the player is actually on their last agenda choice before ejection.
            TutorialStep(
                title="Final Choice",
                text=(
                    "This is your last Agenda choice before you're ejected from this Faction. "
                    "After you play an Agenda, your Influence will drop to 0.\n\n"
                    "Choose carefully, then click Confirm."
                ),
                button_label=None,  # game_confirm
            ),
            # Step 15 (was 14): ejection / agenda pool (pending: ejection_phase_started; game_confirm)
            TutorialStep(
                title="Agenda Pool",
                text=(
                    "Your influence has reached 0, so you've been ejected! But you get to "
                    "leave a mark — replace one card in this Faction's Agenda pool.\n\n"
                    "Remove one Agenda type and add another; this permanently shapes which "
                    "Agendas this Faction will play in the future.\n\n"
                    "Select a card to remove and a card to add, then click Confirm."
                ),
                button_label=None,  # game_confirm
            ),
            # Step 16 (was 15): worship recap (hard-blocking)
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
            # Step 17 (was 16): good luck (Finish; hard-blocking)
            TutorialStep(
                title="Good Luck",
                text=(
                    "That's the core of Impetus! From here on, you'll learn by doing — "
                    "some mechanics will be explained the first time they occur.\n\n"
                    "First to 100 VP wins. The AI is quite basic, so this is a chance "
                    "to practice.\n\nGood luck, Spirit."
                ),
                button_label="Finish",
            ),
        ]

    # ------------------------------------------------------------------ #
    # Hard-blocking steps: block all game input when panel is shown
    # ------------------------------------------------------------------ #

    _HARD_BLOCKING_STEPS = frozenset({0, 1, 2, 5, 9, 10, 16, 17})

    def is_hard_blocking(self) -> bool:
        if not self.active or not self._shown:
            return False
        return self.step_idx in self._HARD_BLOCKING_STEPS

    def is_blocking_animations(self) -> bool:
        return self.block_animations

    def is_blocking_phase_ui(self) -> bool:
        return self.block_phase_ui

    def is_blocking_submit(self) -> bool:
        """Return True to prevent the game Confirm button from responding.

        Blocks Confirm during all pre-Idols steps so the player can't skip the
        tutorial intro. Step 7 (Idols) is the first step where Confirm is meaningful.
        """
        return self.active and self._shown and self.step_idx < 8

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
        self.hide_phase_ui = False
        self.first_time_triggers_enabled = False
        self.fired_triggers = set()
        self.popup_step = None
        self.popup_ok_rect = None
        self._popup_panel_rect = None
        self.popup_highlights = []
        self.highlight_war_arrows = False
        self._return_to_menu_rect = None
        self.return_to_menu_requested = False
        self._step_pending_show = False
        self._expecting_phase_result = False
        self._dynamic_text = None
        self._hover_freeze_done = set()

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
            self.hide_phase_ui = False
            return

        # Steps that need an external trigger before showing.
        # Steps 8 and 10 show immediately (not pending) — 8 after step 7 Continue,
        # 10 after step 9 Continue.
        if new_idx in (1, 9, 11, 12, 13, 14, 15):
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
                self.popup_highlights = []
                self.highlight_war_arrows = False
                return True
            if self._popup_panel_rect and self._popup_panel_rect.collidepoint(pos):
                return True
            return False

        # Return to Menu button (step 17 / Finish step only)
        if self._shown and self._return_to_menu_rect and self._return_to_menu_rect.collidepoint(pos):
            self.return_to_menu_requested = True
            self.active = False
            self._shown = False
            return True

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
            # Release animation block; step 1 shows after turn-1 animations complete
            self.block_animations = False
            self._advance_to(1)
        elif idx in (1, 2, 3, 4, 5, 6):
            self._advance_to(idx + 1)
        elif idx == 7:
            # Step 8 (Idols) shows immediately; player can now interact with vagrant UI
            self._advance_to(8)
        elif idx == 9:
            # Step 10 (Modifiers) shows immediately
            self._advance_to(10)
        elif idx == 10:
            # Step 11 shows via _refire of agenda_phase_started; cards already visible
            self._advance_to(11)
        elif idx == 12:
            # Release phase UI block so turn-3 vagrant phase can appear
            self.block_phase_ui = False
            self._advance_to(13)
        elif idx == 16:
            self._advance_to(17)
        elif idx == 17:
            self.active = False
            self._shown = False
            self.hide_phase_ui = False

    # ------------------------------------------------------------------ #
    # Game event / action notifications
    # ------------------------------------------------------------------ #

    def notify_action(self, action_type: str, data: dict):
        if not self.active:
            return
        idx = self.step_idx

        if action_type == "faction_selected":
            if idx == 4 and not self.action_satisfied:
                self.action_satisfied = True

        elif action_type == "delta_clicked":
            if idx == 6 and not self.action_satisfied:
                self.action_satisfied = True

        elif action_type == "guidance_selected":
            if idx == 7 and not self.action_satisfied:
                self.action_satisfied = True

        elif action_type == "tooltip_hovered":
            if idx == 3 and not self.action_satisfied:
                self._hover_freeze_done.add("hovered")
                if self._hover_freeze_done >= {"hovered", "frozen", "unfrozen"}:
                    self.action_satisfied = True

        elif action_type == "tooltip_frozen":
            if idx == 3 and not self.action_satisfied:
                self._hover_freeze_done.add("frozen")
                if self._hover_freeze_done >= {"hovered", "frozen", "unfrozen"}:
                    self.action_satisfied = True

        elif action_type == "tooltip_unfrozen":
            if idx == 3 and not self.action_satisfied:
                self._hover_freeze_done.add("unfrozen")
                if self._hover_freeze_done >= {"hovered", "frozen", "unfrozen"}:
                    self.action_satisfied = True

        elif action_type == "vagrant_submitted":
            # Advance past idols/guidance step to wait for the agenda phase.
            # Handles both the normal path (idx==8, player read Idols step) and
            # the early-submit edge case (idx==7, player clicked Confirm before
            # clicking tutorial Continue — without this guard the tutorial would
            # get stuck at step 7 forever).
            if idx in (7, 8):
                self._advance_to(9)  # pending: agenda_phase_started

        elif action_type == "agenda_submitted":
            if idx == 11:
                self.first_time_triggers_enabled = True
                # Block turn-3 vagrant phase until step 12 (Watch and Learn) Continue
                self.block_phase_ui = True
                self._expecting_phase_result = True
                self._advance_to(12)
            elif idx == 13:
                self._advance_to(14)
            elif idx == 14:
                self._advance_to(15)

        elif action_type == "ejection_submitted":
            if idx == 15:
                self._advance_to(16)

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
            # Step 12: show after turn-2 agenda animations (guarded until PHASE_RESULT arrives)
            elif idx == 12 and self._step_pending_show and not self._expecting_phase_result:
                self._step_pending_show = False
                self._shown = True
                # block_phase_ui is already True (set at agenda_submitted for step 11)

        elif event_type == "agenda_phase_started":
            draw_count = data.get("draw_count", 2)
            if idx == 9 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True
            elif idx == 11 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True
            elif idx == 13 and self._step_pending_show and draw_count <= 3:
                # Show once influence has visibly dropped (starting draw_count is 4)
                self._step_pending_show = False
                self._shown = True
                self._dynamic_text = (
                    f"Your Influence drops by 1 each turn you guide a Faction. "
                    f"Higher Influence means more Agenda cards to choose from.\n\n"
                    f"You're now drawing {draw_count} cards. "
                    f"When Influence reaches 0, you'll be ejected.\n\n"
                    f"Choose an Agenda and click Confirm."
                )
            elif idx == 14 and self._step_pending_show and draw_count <= 2:
                # Show only when the player is truly on their last agenda choice
                self._step_pending_show = False
                self._shown = True

        elif event_type == "ejection_phase_started":
            if idx == 15 and self._step_pending_show:
                self._step_pending_show = False
                self._shown = True

        elif event_type == "vagrant_phase_started":
            # If guidance was contested/lost last turn, the player is Vagrant again and
            # the tutorial is stuck at step 9 pending (agenda_phase_started never fires
            # for a Vagrant player). Revert to step 7 so they know to guide again.
            if idx == 9 and self._step_pending_show:
                self._advance_to(7)

        elif event_type == "war_erupted":
            if (self.first_time_triggers_enabled
                    and "war_erupted" not in self.fired_triggers):
                self.fired_triggers.add("war_erupted")
                self.popup_step = TutorialStep(
                    title="A War Has Erupted!",
                    text=(
                        "Wars erupt when Regard between neighbors drops to -2 or below "
                        "after a Steal agenda. A new War is 'fresh'; it ripens at the end "
                        "of the turn and resolves at the end of the NEXT turn.\n\n"
                        "When a War resolves, both sides roll a die and add their territory "
                        "count. The winner gains gold and draws Spoils (an extra Agenda). "
                        "The loser loses 1 gold. If the winning Faction is Guided, the "
                        "Spirit chooses which Spoils card to play based on its Influence."
                    ),
                    button_label="Ok",
                )
                self._popup_panel_rect = None
                self.popup_highlights = ["ribbon_war", "panel_war"]
                self.highlight_war_arrows = True

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

        elif event_type == "change_drawn":
            influence = data.get("influence", 0)
            card_count = data.get("card_count", 1)
            if (self.first_time_triggers_enabled
                    and influence > 0
                    and "change_drawn_with_influence" not in self.fired_triggers):
                self.fired_triggers.add("change_drawn_with_influence")
                self.popup_step = TutorialStep(
                    title="Change — Influence Helps Here",
                    text=(
                        f"You're drawing {card_count} modifier options because your "
                        f"Influence is {influence}. Higher Influence means more cards "
                        f"to choose from — so you can be selective about which modifier "
                        f"you want.\n\n"
                        "Each modifier permanently boosts one Agenda type for your Guided "
                        "Faction. Stack the same type for compounding effects, or spread "
                        "across types for flexibility."
                    ),
                    button_label="Ok",
                )
                self._popup_panel_rect = None

        elif event_type == "guided_spoils_drawn":
            if (self.first_time_triggers_enabled
                    and "guided_spoils_drawn" not in self.fired_triggers):
                self.fired_triggers.add("guided_spoils_drawn")
                self.popup_step = TutorialStep(
                    title="Your Faction Won a War — Spoils!",
                    text=(
                        "Your Guided Faction won a War and draws Spoils — a bonus Agenda "
                        "card that resolves immediately after the regular agendas this turn.\n\n"
                        "Choose a Spoils card from those drawn. Most cards work normally: "
                        "Trade sends gold back and benefits from others Trading this turn; "
                        "Steal and Change work exactly as normal.\n\n"
                        "Expand is different: it conquers the war's battleground hex rather "
                        "than an adjacent neutral hex. The gold cost is waive. If more than "
                        "one Faction tries to conquer a hex simultaneously, they get [+1] gold "
                        "as consolation."
                    ),
                    button_label="Ok",
                )
                self._popup_panel_rect = None

        elif event_type == "faction_eliminated":
            if (self.first_time_triggers_enabled
                    and "faction_eliminated" not in self.fired_triggers):
                self.fired_triggers.add("faction_eliminated")
                self.popup_step = TutorialStep(
                    title="A Faction Has Been Eliminated!",
                    text=(
                        "A Faction lost all of its territories and has been eliminated!\n\n"
                        "Eliminated Factions no longer play Agendas, accumulate Gold, or "
                        "participate in Wars. Any Spirit guiding them is immediately ejected. "
                        "Their Worship is cleared, and any Wars they were involved in are "
                        "cancelled.\n\n"
                        "Fewer Factions means fewer options for Guidance. However, if you are "
                        "ever in a situation where you have to Guide and can't, you gain 10 VP "
                        "instead."
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
            if self.popup_highlights:
                self._draw_highlights(screen, self.popup_highlights)

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
            if key in ("spirit_panel", "event_log", "faction_info", "agenda_cards_area",
                       "panel_war"):
                rect = self.exposed_rects.get(key)
                if rect:
                    self._draw_glow_rect(screen, rect, color, pulse_alpha)
            elif key == "ribbon":
                rects = [r for k, r in self.exposed_rects.items()
                         if k.startswith("ribbon_") and not k.startswith("ribbon_war_")]
                if rects:
                    union = rects[0].unionall(rects[1:])
                    self._draw_glow_rect(screen, union, color, pulse_alpha)
            elif key == "ribbon_war":
                for rkey, rect in self.exposed_rects.items():
                    if rkey.startswith("ribbon_war_"):
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
        line_h = small_font.get_height() + 2

        btn_h = 26
        btn_w = 84
        btn_gap = 6
        show_button = step.button_label is not None

        body_h = len(body_lines) * line_h
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
        for line in body_lines:
            if y + line_h > clip_bottom:
                break
            self._draw_body_line(screen, line, small_font, px + pad, y)
            y += line_h
        screen.set_clip(old_clip)

        self._continue_rect = None
        self._return_to_menu_rect = None
        if show_button:
            btn_x = px + pw - btn_w - pad
            btn_y = py + ph - btn_h - pad
            can_advance = self._can_advance_now()
            if step.button_label == "Finish":
                btn_color = self._BTN_FINISH
                # Draw "Return to Menu" button to the left of Finish
                btn_w_menu = 110
                menu_btn_x = btn_x - btn_gap - btn_w_menu
                menu_btn_rect = pygame.Rect(menu_btn_x, btn_y, btn_w_menu, btn_h)
                pygame.draw.rect(screen, (60, 60, 100), menu_btn_rect, border_radius=3)
                menu_lbl = small_font.render("Return to Menu", True, (230, 230, 230))
                screen.blit(menu_lbl, (menu_btn_rect.centerx - menu_lbl.get_width() // 2,
                                       menu_btn_rect.centery - menu_lbl.get_height() // 2))
                self._return_to_menu_rect = menu_btn_rect
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

    _DELTA_POSITIVE = re.compile(r'(\[\+\d+\])')
    _DELTA_NEGATIVE = re.compile(r'(\[-\d+\])')
    _DELTA_SPLIT = re.compile(r'(\[[-+]\d+\])')
    _COLOR_POS = (80, 220, 80)
    _COLOR_NEG = (255, 90, 90)

    def _draw_body_line(self, screen: pygame.Surface,
                        line: str, font: pygame.font.Font,
                        x: int, y: int):
        """Draw one text line, colouring [+N] green and [-N] red."""
        parts = self._DELTA_SPLIT.split(line)
        cx = x
        for part in parts:
            if not part:
                continue
            if self._DELTA_POSITIVE.match(part):
                color = self._COLOR_POS
            elif self._DELTA_NEGATIVE.match(part):
                color = self._COLOR_NEG
            else:
                color = self._TEXT_COLOR
            surf = font.render(part, True, color)
            screen.blit(surf, (cx, y))
            cx += surf.get_width()

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
        py = 105  # just below the faction ribbon strip (ribbon ends at y=97)

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
