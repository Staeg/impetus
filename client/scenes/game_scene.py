"""Primary gameplay scene: hex map, UI, phases."""

import math
import time
from typing import Any
import pygame
from dataclasses import dataclass
from shared.constants import (
    MessageType, Phase, SubPhase, AgendaType, IdolType, MAP_SIDE_LENGTH,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES, FACTION_COLORS,
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP,
)
from shared.hex_utils import axial_to_pixel
from client.faction_names import faction_full_name, update_faction_races
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import (
    UIRenderer, Button, build_agenda_tooltip, build_modifier_tooltip,
    draw_dotted_underline, _wrap_text, render_rich_lines,
)
from client.renderer.font_cache import get_font
import client.theme as theme
from client.renderer.animation import AnimationManager, TextAnimation, IdolBeamAnimation
from client.renderer.assets import load_assets, agenda_card_images
from client.input_handler import InputHandler
from client.scenes.animation_orchestrator import AnimationOrchestrator
from client.scenes.change_tracker import FactionChangeTracker
from client.tutorial import TutorialManager
from client.renderer.popup_manager import (
    PopupManager, HoverRegion, TooltipDescriptor, TooltipRegistry,
    set_ui_rects, _WEIGHT_TEXT, _WEIGHT_NON_TEXT,
)

# Approximate hex map screen bounds (default camera) for centering UI
# Pointy-top: rightmost vertex = sqrt(3)*HEX_SIZE*(MAP_SIDE_LENGTH-1+0.5)
_HEX_MAP_HALF_W = int(math.sqrt(3) * HEX_SIZE * (MAP_SIDE_LENGTH - 0.5))
_HEX_MAP_LEFT_X = SCREEN_WIDTH // 2 - _HEX_MAP_HALF_W
_HEX_MAP_RIGHT_X = SCREEN_WIDTH // 2 + _HEX_MAP_HALF_W

# Right column layout: starts just past map right edge
_FACTION_PANEL_X = _HEX_MAP_RIGHT_X + 14
_PANEL_W = SCREEN_WIDTH - _FACTION_PANEL_X - 2

# Panel heights for the stacked right column (y=102 to y=796 = 694px usable)
_FACTION_PANEL_MAX_H = 300    # scrollable faction/spirit panel (top)
_SPIRIT_PANEL_MAX_H = 195     # persistent self-spirit panel (middle)
_EVENT_LOG_H = 191            # event log (bottom); 694-300-4-195-4=191
_EVENT_LOG_H_ENLARGED = 400   # event log when expanded

# Centering positions for button column (left side only)
_GUIDANCE_CENTER_X = _HEX_MAP_LEFT_X // 2
_BTN_W = 157
_BTN_H = 37
_BTN_STEP_Y = 43
_GUIDANCE_BTN_X = _GUIDANCE_CENTER_X - _BTN_W // 2

# Title positions (below faction overview strip which ends at Y=97)
_TITLE_Y = 102
_BTN_START_Y = 129

# Vertical center of the playable hex map area (between ribbon and submit button)
_MAP_CENTER_Y = (_TITLE_Y + SCREEN_HEIGHT - 60) // 2  # = (102+740)//2 = 421

# Card picker dimensions
_CARD_W = 110
_CARD_H = 145         # vertical (left-panel) card pickers
_CARD_SPACING = 5
_CARD_H_TALL = 170    # taller layout used by _calc_card_rects

_INFLUENCE_TOOLTIP = (
    "The number of additional Agenda cards a Spirit draws when "
    "choosing for their Guided Faction. Set to 3 when Guidance "
    "begins, it decreases by 1 each turn. The Spirit is ejected "
    "when it reaches 0."
)

_AFFINITY_TOOLTIP = (
    "When two Spirits try to Guide the same Faction, Affinity determines who succeeds. "
    "A matching Habitat Affinity wins outright. A matching Race Affinity wins if no "
    "one has the Habitat. If no Spirit holds a relevant Affinity, guidance is Contested."
)

_AGENDA_POOL_TOOLTIP = (
    "All possible Agendas a Faction can draw and play. The base "
    "pool contains 1 of each type: Trade, Steal, Expand, "
    "and Change. When a Spirit is ejected, they replace one card "
    "in the pool with another of their choice. Spirits with "
    "more Influence draw more options from it."
)

_WAR_TOOLTIP = (
    "If two Factions have -2 Regard or less after one of them plays Steal, "
    "a War is declared. At the end of the turn where it is declared, a War "
    "becomes ripe and two neighboring hexes, one belonging to each Faction, "
    "are chosen as the Battleground. At the end of the next turn, the ripe "
    "War resolves.\n\n"
    "If the war involves a Guided Faction, its Spirit chooses the Battleground. "
    "If both Factions are Guided, each Spirit picks the enemy's side; "
    "incompatible picks are randomized."
)

_WAR_RESOLVES_TOOLTIP = (
    "When a ripe War resolves, both Factions roll a 6-sided die and add the "
    "number of their Territories to the roll. The Faction with the higher "
    "total wins.\n\n"
    "The victorious Faction gains 1 gold and plays a random Agenda card as "
    "Spoils of War. Expand drawn as Spoils will conquer the enemy side of "
    "the Battleground instead of its usual effect. Other Agendas have their "
    "normal effect, including Trade granting gold and Regard with other "
    "Trade cards played this turn.\n\n"
    "If the winning Faction is Guided, the Spirit gets to draw additional "
    "Agendas as Spoils equal to its current Influence before choosing one to "
    "resolve.\n\n"
    "The losing Faction loses 1 gold. In the case of a tie, both Factions "
    "lose 1 gold."
)

_GOLD_TOOLTIP = "Resource used to pay for Expand Agendas. Cannot go below 0."

_TRADE_AGENDA_TOOLTIP = "Trade\n+1 gold, +1 gold for every other Faction playing Trade this turn.\n+1 Regard with each other Faction playing Trade this turn."
_STEAL_AGENDA_TOOLTIP = "Steal\n-1 Regard with and -1 gold to all neighbors. +1 gold for each gold lost. War erupts at -2 Regard."
_EXPAND_AGENDA_TOOLTIP = "Expand\nGuided: choose a reachable neutral hex to claim (cost = territories). If multiple Spirits pick the same hex, both fail. Unguided: random. If unavailable or lacking gold, +1 gold instead."

_MODIFIER_TOOLTIP = (
    "Permanently improves a specific Agenda when used by the Faction implementing the modifier. "
    "These bonuses stack. Possible modifiers:\n"
    "Trade: +1 gold and +1 Regard per co-trader\n"
    "Steal: +1 gold stolen and -1 regard to affected neighbors\n"
    "Expand: -1 cost on successful Expands, +1 gold on failed Expands"
)

_CONTESTED_TOOLTIP = (
    "If several Spirits attempt to Guide the same Faction on a given turn, "
    "the Guidance fails. This prevents all involved Spirits from Guiding "
    "that Faction for exactly 1 turn. This only occurs if no contesting Spirit "
    "holds a Habitat or Race Affinity for that Faction.\n\n"
    "Spirits can only place 1 Idol per successful Guidance."
)

_GUIDANCE_HOVER_REGIONS = [
    HoverRegion("Agenda pool", _AGENDA_POOL_TOOLTIP, sub_regions=[
        HoverRegion("Influence", _INFLUENCE_TOOLTIP, sub_regions=[]),
    ]),
    HoverRegion("Influence", _INFLUENCE_TOOLTIP, sub_regions=[]),
    HoverRegion("Gold", _GOLD_TOOLTIP, sub_regions=[]),
    HoverRegion("gold", _GOLD_TOOLTIP, sub_regions=[]),
    HoverRegion("War", _WAR_TOOLTIP, sub_regions=[
        HoverRegion("resolves", _WAR_RESOLVES_TOOLTIP, sub_regions=[]),
    ]),
    HoverRegion("modifier", _MODIFIER_TOOLTIP, sub_regions=[
        HoverRegion("Trade", _TRADE_AGENDA_TOOLTIP, sub_regions=[]),
        HoverRegion("Steal", _STEAL_AGENDA_TOOLTIP, sub_regions=[]),
        HoverRegion("Expand", _EXPAND_AGENDA_TOOLTIP, sub_regions=[]),
    ]),
    HoverRegion("Contested", _CONTESTED_TOOLTIP, sub_regions=[]),
]

_WAR_HOVER_REGIONS = [
    HoverRegion("resolves", _WAR_RESOLVES_TOOLTIP, sub_regions=[]),
]

_RIBBON_WAR_HOVER_REGIONS = [
    HoverRegion("War", _WAR_TOOLTIP, sub_regions=[
        HoverRegion("resolves", _WAR_RESOLVES_TOOLTIP, sub_regions=[]),
    ]),
]

_CHOICE_CARD_Y = 140  # cards start below title text (title at y=102, page indicator at y=121)


@dataclass
class SpoilsEntry:
    """One pending spoils card-pick for a single war."""
    cards: list
    loser: str
    selected: int = -1


class GameScene:
    def __init__(self, app):
        self.app = app
        self.hex_renderer = HexRenderer()
        self.ui_renderer = UIRenderer()
        self.animation = AnimationManager()
        self.input_handler = InputHandler()
        self.input_handler.camera_y = SCREEN_HEIGHT // 2 - _MAP_CENTER_Y
        self.orchestrator = AnimationOrchestrator(
            self.animation, self.hex_renderer, self.input_handler)
        load_assets()

        self.game_state: dict = {}
        self.phase = ""
        self.turn = 0
        self.factions: dict = {}
        self.spirits: dict = {}
        self.wars: list = []
        self.all_idols: list = []
        self._render_idols_cache: list = []   # built in render(), reused by _update_idol_hover
        self.hex_ownership: dict[tuple[int, int], str | None] = {}
        # Deferred display state: lags behind real state while animations play
        self._display_hex_ownership: dict[tuple[int, int], str | None] | None = None
        self._display_factions: dict | None = None
        self._display_wars: list | None = None
        self.waiting_for: list[str] = []
        self.has_submitted: bool = False
        self.spectator_mode: bool = False
        self.event_log: list[str] = []
        self.event_log_scroll_offset: int = 0
        self.event_log_h_scroll_offset: int = 0
        self.event_log_enlarged: bool = False
        # Per-spirit influence values from last state update (for fade animation detection)
        self._influence_prev: dict[str, int] = {}

        # Faction display order (left-to-right by starting hex x-position)
        self.faction_order: list[str] = list(FACTION_NAMES)

        # Faction overview tracking
        self.faction_agendas_this_turn: dict[str, str] = {}
        self.faction_spoils_agendas_this_turn: dict[str, list[str]] = {}
        self._pending_ribbon_clear_on_next_agenda: bool = False
        self._pending_agenda_log_info: dict[str, dict] = {}

        # Phase-specific state
        self.phase_options: dict = {}
        self.selected_faction: str | None = None
        self.selected_hex: tuple[int, int] | None = None
        self.selected_idol_type: str | None = None
        self.panel_faction: str | None = None
        self.preview_guidance: str | None = None
        self.preview_idol: tuple | None = None  # (idol_type, q, r)

        # Fading error message (e.g. invalid hex click)
        self._hex_error_message: str = ""
        self._hex_error_timer: float = 0.0

        # Agenda state
        self.agenda_hand: list[dict] = []
        self.selected_agenda_index: int = -1

        # Change/ejection/spoils state
        self.change_cards: list[str] = []
        self.ejection_pending = False
        self.ejection_faction = ""
        self.ejection_pool: list[str] = []
        self.selected_ejection_remove_type: str | None = None
        self.selected_ejection_add_type: str | None = None
        self.spoils_entries: list[SpoilsEntry] = []
        self.spoils_change_entries: list[SpoilsEntry] = []
        self.spoils_display_index: int = 0
        self.faction_panel_scroll_offset: int = 0
        self.spoils_nav_left_rect: pygame.Rect | None = None
        self.spoils_nav_right_rect: pygame.Rect | None = None

        # Battleground choice state
        self.battleground_choice_wars: list[dict] = []
        self.battleground_selections: dict[str, Any] = {}  # war_id -> pair_index or (q,r)
        self.battleground_display_index: int = 0
        self.battleground_selectable_hexes: set[tuple] = set()
        self.battleground_selected_hexes: set[tuple] = set()  # both hexes of current selection
        self.battleground_hex_to_choice: dict[tuple, Any] = {}  # hex -> pair_index or (q,r)
        self.battleground_nav_left_rect: pygame.Rect | None = None
        self.battleground_nav_right_rect: pygame.Rect | None = None

        # Expand choice state
        self.expand_choice_hexes: set[tuple] = set()
        self.expand_choice_faction: str = ""

        # In-game menu (top-right)
        self._ingame_menu_open: bool = False
        self._ingame_menu_confirm_exit: bool = False
        self._ingame_menu_btn_rect: pygame.Rect | None = None
        self._ingame_menu_item_rects: list[tuple[str, pygame.Rect]] = []
        self._ingame_confirm_yes_rect: pygame.Rect | None = None
        self._ingame_confirm_no_rect: pygame.Rect | None = None

        # UI buttons
        self.action_buttons: list[Button] = []
        self.remove_buttons: list[Button] = []
        self.submit_button: Button | None = None
        self.faction_buttons: list[Button] = []
        self.faction_button_ids: list[str] = []
        self.idol_buttons: list[Button] = []

        # Title labels (rects + tooltip text)
        self.guidance_title_rect: pygame.Rect | None = None
        self.guidance_title_hovered: bool = False
        self.idol_title_rect: pygame.Rect | None = None
        self.idol_title_hovered: bool = False

        # Idol hover tooltip
        self.hovered_idol = None  # idol object or None
        self.idol_tooltip_spirit_rects: list[tuple[str, pygame.Rect]] = []

        # Agenda hover tooltip state
        self.hovered_card_tooltip: str | None = None
        self.hovered_card_rect: pygame.Rect | None = None
        self.agenda_label_rects: list[tuple[str, str, bool, pygame.Rect]] = []
        self.hovered_agenda_label_fid: str | None = None
        self.hovered_agenda_label_type: str | None = None
        self.hovered_agenda_label_is_spoils: bool = False
        self.hovered_agenda_label_rect: pygame.Rect | None = None
        self.hovered_anim_tooltip: str | None = None
        self.hovered_anim_rect: pygame.Rect | None = None
        # Pool icon hover state
        self.pool_icon_rects: dict[str, pygame.Rect] = {}
        self.hovered_pool_faction: str | None = None
        # Ribbon war indicator hover state
        self.ribbon_war_rects: dict[str, pygame.Rect] = {}
        self.hovered_ribbon_war_fid: str | None = None
        # Ribbon worship sigil hover state
        self.ribbon_worship_rects: dict[str, pygame.Rect] = {}
        self.hovered_ribbon_worship_fid: str | None = None
        # Guided hex sigil hover state
        self.hovered_guided_hex_spirit: str | None = None
        # Ribbon faction cell rects (for click handling)
        self.ribbon_faction_rects: dict[str, pygame.Rect] = {}

        # Faction panel / VP hover tooltip state
        self.hovered_panel_guided: bool = False
        self.hovered_panel_worship: bool = False
        self.hovered_panel_war: bool = False
        self.hovered_vp_spirit_id: str | None = None

        # Spirit panel state (which spirit's panel to show, or None)
        self.spirit_panel_spirit_id: str | None = None
        self.hovered_spirit_panel_guidance: bool = False
        self.hovered_spirit_panel_influence: bool = False
        self.hovered_spirit_panel_worship: str | None = None  # faction_id or None
        self.hovered_spirit_panel_affinity: bool = False
        self._spirit_panel_rects: dict = {}          # rects returned from draw_spirit_panel (right pop-out)
        # Persistent spirit panel (bottom-left) hover state
        self.hovered_persistent_spirit_guidance: bool = False
        self.hovered_persistent_spirit_influence: bool = False
        self.hovered_persistent_spirit_worship: str | None = None
        self.hovered_persistent_spirit_affinity: bool = False
        self._persistent_spirit_panel_rects: dict = {}  # rects returned from draw_spirit_panel (bottom-left)
        # Ejection title keyword hover state
        self.ejection_keyword_rects: dict[str, list[pygame.Rect]] = {}
        self.hovered_ejection_keyword: str | None = None

        # Change tracking for faction panel
        self.change_tracker = FactionChangeTracker()
        self.popup_manager = PopupManager()
        self.tooltip_registry = TooltipRegistry()
        self.highlighted_log_index: int | None = None
        self.panel_change_rects: list[tuple[pygame.Rect, int]] = []

        self._font = None
        self._small_font = None

        # Tutorial overlay (active in tutorial mode)
        self.tutorial: TutorialManager | None = None
        self._tutorial_anim_notified: bool = False
        self._tutorial_last_step: int = -1

        # Queued PHASE_RESULT payloads — processed one at a time as animations finish
        self._phase_result_queue: list[dict] = []
        # Deferred game-over event: set when game_over payload is processed,
        # consumed (scene transition) once all animations have settled.
        self._pending_game_over: dict | None = None
        # Final game-over state — stay in game_scene and show scores in-place.
        self.game_over: bool = False
        self.game_over_data: dict | None = None
        self._game_over_bold_font = None
        self._game_over_win_font = None

        # Network message dispatch table (built after all state is initialised)
        self._net_handlers = {
            MessageType.GAME_START:   self._handle_game_start,
            MessageType.PHASE_START:  self._handle_phase_start,
            MessageType.PHASE_RESULT: self._handle_phase_result,
            MessageType.WAITING_FOR:  self._handle_waiting_for,
            MessageType.GAME_OVER:    self._handle_game_over,
            MessageType.ERROR:        self._handle_error,
        }

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

    def _update_state_from_snapshot(self, data: dict):
        """Update local state from a game state snapshot dict."""
        self.turn = data.get("turn", self.turn)
        self.phase = data.get("phase", self.phase)
        self.factions = data.get("factions", self.factions)
        update_faction_races({
            fid: fdata.get("race", "") if isinstance(fdata, dict) else ""
            for fid, fdata in self.factions.items()
        })
        # Snapshot old influence before overwriting spirits, so we can detect decreases
        old_influences = {sid: s.get("influence", 0) for sid, s in self.spirits.items()}
        self.spirits = data.get("spirits", self.spirits)
        # Start fade-out animations for circles that lost influence
        for sid, spirit in self.spirits.items():
            new_inf = spirit.get("influence", 0)
            old_inf = old_influences.get(sid, self._influence_prev.get(sid, new_inf))
            if old_inf > new_inf:
                for idx in range(new_inf, old_inf):
                    self.animation.add_tween(f"infl_{sid}_{idx}", 1.0, 0.0, 3.0)
            self._influence_prev[sid] = new_inf

        # Parse wars
        self.wars = []
        for w in data.get("wars", []):
            self.wars.append(w)

        # Parse idols
        self.all_idols = []
        for i in data.get("all_idols", []):
            self.all_idols.append(i)

        # Parse hex ownership
        self.hex_ownership = {}
        for key, owner in data.get("hex_ownership", {}).items():
            parts = key.split(",")
            if len(parts) == 2:
                q, r = int(parts[0]), int(parts[1])
                self.hex_ownership[(q, r)] = owner

        # Faction display order
        if "faction_order" in data:
            self.faction_order = data["faction_order"]
            self.orchestrator.faction_order = self.faction_order

    def _snapshot_display_state(self):
        """Capture current state into display fields before updating real state.

        Only snapshots if display state isn't already set (preserves display
        state across multiple PHASE_RESULT messages during animation).
        """
        if self._display_hex_ownership is None:
            self._display_hex_ownership = dict(self.hex_ownership)
        if self._display_factions is None:
            import copy
            self._display_factions = copy.deepcopy(self.factions)
        if self._display_wars is None:
            import copy
            self._display_wars = copy.deepcopy(self.wars)

    def _clear_display_state(self):
        """Clear deferred display state so rendering uses real state."""
        self._display_hex_ownership = None
        self._display_factions = None
        self._display_wars = None

    def _get_influence_fills(self, spirit_id: str) -> list[float]:
        """Return a list of 3 fill values (0.0-1.0) for each influence circle slot.

        Filled slots use 1.0; slots lost since last update use a fading tween value.
        """
        influence = self.spirits.get(spirit_id, {}).get("influence", 0)
        fills = []
        for idx in range(3):
            if idx < influence:
                fills.append(1.0)
            else:
                fills.append(self.animation.get_tween_value(f"infl_{spirit_id}_{idx}", 0.0))
        return fills

    @property
    def display_hex_ownership(self) -> dict:
        return self._display_hex_ownership if self._display_hex_ownership is not None else self.hex_ownership

    @property
    def display_factions(self) -> dict:
        return self._display_factions if self._display_factions is not None else self.factions

    @property
    def display_wars(self) -> list:
        return self._display_wars if self._display_wars is not None else self.wars

    def handle_event(self, event):
        self.input_handler.handle_camera_event(event)

        if event.type == pygame.MOUSEWHEEL:
            _cur_event_log_h = _EVENT_LOG_H_ENLARGED if self.event_log_enlarged else _EVENT_LOG_H
            _cur_faction_panel_h = _FACTION_PANEL_MAX_H + _EVENT_LOG_H - _cur_event_log_h
            _event_log_y = 102 + _cur_faction_panel_h + 4 + _SPIRIT_PANEL_MAX_H + 4
            log_rect = getattr(self, '_event_log_render_rect', None) or pygame.Rect(_FACTION_PANEL_X, _event_log_y, _PANEL_W, _cur_event_log_h)
            mx, my = pygame.mouse.get_pos()
            if log_rect.collidepoint(mx, my):
                visible_count = (_cur_event_log_h - 26) // 16
                max_offset = max(0, len(self.event_log) - visible_count)
                self.event_log_scroll_offset += event.y
                self.event_log_scroll_offset = max(0, min(self.event_log_scroll_offset, max_offset))
                self.event_log_h_scroll_offset += event.x * 16
                self.event_log_h_scroll_offset = max(0, self.event_log_h_scroll_offset)
            # Faction panel scroll
            fp_rect = self.ui_renderer.faction_panel_rect
            if fp_rect and fp_rect.collidepoint(mx, my):
                content_h = getattr(self.ui_renderer, '_faction_panel_content_h', 0)
                max_scroll = max(0, content_h - _cur_faction_panel_h)
                self.faction_panel_scroll_offset = max(0, min(
                    self.faction_panel_scroll_offset - event.y * 16, max_scroll))

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.game_over:
                self.app.set_scene("menu")
                return
            self.popup_manager.handle_escape()

        if event.type == pygame.MOUSEMOTION:
            for btn in self.action_buttons + self.remove_buttons + self.faction_buttons + self.idol_buttons:
                btn.update(event.pos)
            if self.submit_button:
                self.submit_button.update(event.pos)
            # Title label hover tracking
            if self.guidance_title_rect:
                self.guidance_title_hovered = self.guidance_title_rect.collidepoint(event.pos)
            if self.idol_title_rect:
                self.idol_title_hovered = self.idol_title_rect.collidepoint(event.pos)
            # Idol hover detection on hex map
            self._update_idol_hover(event.pos)
            # Agenda card/label/animation hover detection
            self._update_agenda_hover(event.pos)
            # Faction panel guided/worship hover detection
            self._update_panel_hover(event.pos)
            # Spirit panel hover detection
            self._update_spirit_panel_hover(event.pos)
            # Ejection title keyword hover detection
            self._update_ejection_title_hover(event.pos)
            # Agenda pool icon hover detection
            self.hovered_pool_faction = None
            for fid, rect in self.pool_icon_rects.items():
                if rect.collidepoint(event.pos):
                    self.hovered_pool_faction = fid
                    break
            # Ribbon war indicator hover detection
            self.hovered_ribbon_war_fid = None
            for fid, rect in self.ribbon_war_rects.items():
                if rect.collidepoint(event.pos):
                    self.hovered_ribbon_war_fid = fid
                    break
            # Ribbon worship sigil hover detection
            self.hovered_ribbon_worship_fid = None
            for fid, rect in self.ribbon_worship_rects.items():
                if rect.collidepoint(event.pos):
                    self.hovered_ribbon_worship_fid = fid
                    break
            # Guided hex sigil hover detection
            self._update_guided_hex_hover(event.pos)
            # Popup keyword hover
            self.popup_manager.update_hover(event.pos)
            # Tutorial: notify when player hovers something with a tooltip
            if self.tutorial and (self.hovered_card_tooltip or self.hovered_idol
                                  or self.hovered_pool_faction or self.hovered_ribbon_war_fid):
                self.tutorial.notify_action("tooltip_hovered", {})

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # In-game menu: confirm exit dialog takes priority
            if self._ingame_menu_confirm_exit:
                if self._ingame_confirm_yes_rect and self._ingame_confirm_yes_rect.collidepoint(event.pos):
                    self.app.set_scene("menu")
                    return
                if self._ingame_confirm_no_rect and self._ingame_confirm_no_rect.collidepoint(event.pos):
                    self._ingame_menu_confirm_exit = False
                    return
                return  # swallow all clicks while confirm is open
            # In-game menu button toggle
            if self._ingame_menu_btn_rect and self._ingame_menu_btn_rect.collidepoint(event.pos):
                self._ingame_menu_open = not self._ingame_menu_open
                return
            # In-game menu items (when open)
            if self._ingame_menu_open:
                for label, rect in self._ingame_menu_item_rects:
                    if rect.collidepoint(event.pos):
                        self._ingame_menu_open = False
                        if label == "settings":
                            settings_scene = self.app.scenes.get("settings")
                            if settings_scene:
                                settings_scene.return_scene = "game"
                            self.app.set_scene("settings")
                        elif label == "exit":
                            self._ingame_menu_confirm_exit = True
                        return
                # Click outside menu: close it
                self._ingame_menu_open = False

            # Tutorial input gate: let tutorial consume/block clicks first
            if self.tutorial:
                consumed = self.tutorial.handle_click(event.pos)
                if self.tutorial.return_to_menu_requested:
                    self.app.set_scene("menu")
                    return
                if consumed:
                    return
                if self.tutorial.is_hard_blocking():
                    return  # block all game input
            # Event log expand/collapse toggle (always accessible)
            if (self.ui_renderer.event_log_expand_rect and
                    self.ui_renderer.event_log_expand_rect.collidepoint(event.pos)):
                self.event_log_enlarged = not self.event_log_enlarged
                return

            if not (self.spectator_mode and not self.game_over):
                # Check submit button
                if self.submit_button and self.submit_button.clicked(event.pos):
                    if not (self.tutorial and self.tutorial.is_blocking_submit()):
                        self._submit_action()
                    return

                # Check ejection remove buttons
                for btn in self.remove_buttons:
                    if btn.clicked(event.pos):
                        chosen_remove = btn.text.lower()
                        if self.selected_ejection_add_type == chosen_remove:
                            return
                        self.selected_ejection_remove_type = chosen_remove
                        return

                # Check action buttons
                for btn in self.action_buttons:
                    if btn.clicked(event.pos):
                        self._handle_action_button(btn.text)
                        return

                # Check faction buttons
                for btn, fid in zip(self.faction_buttons, self.faction_button_ids):
                    if btn.clicked(event.pos):
                        self._handle_faction_select(fid)
                        # Notify guidance_selected for step 6 gate
                        if self.tutorial and btn.enabled:
                            self.tutorial.notify_action("guidance_selected", {"faction": fid})
                        return

                # Check idol type buttons
                for btn in self.idol_buttons:
                    if btn.clicked(event.pos):
                        self._handle_idol_select(btn.text.lower())
                        return

                # Check agenda card clicks
                if self.agenda_hand:
                    for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.agenda_hand))):
                        if rect.collidepoint(event.pos):
                            self.selected_agenda_index = i
                            return

                # Check change card clicks
                if self.change_cards:
                    for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.change_cards))):
                        if rect.collidepoint(event.pos):
                            self._submit_card_choice(i, MessageType.SUBMIT_CHANGE_CHOICE, "change_cards")
                            return

                # Check spoils card clicks (one-at-a-time display)
                if self.spoils_entries:
                    idx = max(0, min(self.spoils_display_index, len(self.spoils_entries) - 1))
                    entry = self.spoils_entries[idx]
                    rects = self._calc_left_choice_card_rects(len(entry.cards))
                    for i, rect in enumerate(rects):
                        if rect.collidepoint(event.pos):
                            entry.selected = i
                            return
                    # Nav arrows
                    if self.spoils_nav_left_rect and self.spoils_nav_left_rect.collidepoint(event.pos):
                        self.spoils_display_index = max(0, self.spoils_display_index - 1)
                        return
                    if self.spoils_nav_right_rect and self.spoils_nav_right_rect.collidepoint(event.pos):
                        self.spoils_display_index = min(len(self.spoils_entries) - 1, self.spoils_display_index + 1)
                        return

                # Battleground nav arrows (multiple wars)
                if self.phase == SubPhase.BATTLEGROUND_CHOICE and self.battleground_choice_wars:
                    if (self.battleground_nav_left_rect
                            and self.battleground_nav_left_rect.collidepoint(event.pos)):
                        self.battleground_display_index = max(
                            0, self.battleground_display_index - 1)
                        self._refresh_battleground_hex_sets()
                        self.selected_hex = None
                        return
                    if (self.battleground_nav_right_rect
                            and self.battleground_nav_right_rect.collidepoint(event.pos)):
                        self.battleground_display_index = min(
                            len(self.battleground_choice_wars) - 1,
                            self.battleground_display_index + 1)
                        self._refresh_battleground_hex_sets()
                        self.selected_hex = None
                        return

                # Check spoils change card clicks (one-at-a-time display)
                if self.spoils_change_entries:
                    idx = max(0, min(self.spoils_display_index, len(self.spoils_change_entries) - 1))
                    entry = self.spoils_change_entries[idx]
                    rects = self._calc_left_choice_card_rects(len(entry.cards))
                    for i, rect in enumerate(rects):
                        if rect.collidepoint(event.pos):
                            entry.selected = i
                            return
                    # Nav arrows
                    if self.spoils_nav_left_rect and self.spoils_nav_left_rect.collidepoint(event.pos):
                        self.spoils_display_index = max(0, self.spoils_display_index - 1)
                        return
                    if self.spoils_nav_right_rect and self.spoils_nav_right_rect.collidepoint(event.pos):
                        self.spoils_display_index = min(len(self.spoils_change_entries) - 1, self.spoils_display_index + 1)
                        return

            # Check change delta chip clicks (faction panel)
            for rect, log_idx in self.panel_change_rects:
                if rect.collidepoint(event.pos):
                    if self.highlighted_log_index == log_idx:
                        self.highlighted_log_index = None
                    else:
                        self.highlighted_log_index = log_idx
                        # Auto-scroll event log to show highlighted entry
                        _cur_event_log_h = _EVENT_LOG_H_ENLARGED if self.event_log_enlarged else _EVENT_LOG_H
                        visible_count = (_cur_event_log_h - 26) // 16
                        total = len(self.event_log)
                        if total > visible_count:
                            # scroll_offset=0 shows last entries; we want log_idx visible
                            offset = total - log_idx - visible_count
                            self.event_log_scroll_offset = max(0, min(offset, total - visible_count))
                    if self.tutorial:
                        self.tutorial.notify_action("delta_clicked", {})
                    return

            # Idol tooltip: click spirit names to toggle that spirit's panel
            for sid, name_rect in self.idol_tooltip_spirit_rects:
                if name_rect.collidepoint(event.pos):
                    if self.spirit_panel_spirit_id == sid:
                        self.spirit_panel_spirit_id = None
                    else:
                        self.spirit_panel_spirit_id = sid
                    return

            # Spirit panel: click on any name in VP HUD toggles that spirit's panel
            for sid, vp_rect in self.ui_renderer.vp_hover_rects.items():
                if vp_rect.collidepoint(event.pos):
                    if self.spirit_panel_spirit_id == sid:
                        self.spirit_panel_spirit_id = None
                    else:
                        self.spirit_panel_spirit_id = sid
                    return

            # Click on spirit panel itself should not close it
            sp_rect = self._spirit_panel_rects.get("panel")
            if self.spirit_panel_spirit_id and sp_rect and sp_rect.collidepoint(event.pos):
                return

            # Clicking elsewhere closes the spirit panel
            if self.spirit_panel_spirit_id:
                self.spirit_panel_spirit_id = None

            # Ribbon faction name click — same effect as clicking that faction on the map
            for fid, rect in self.ribbon_faction_rects.items():
                if rect.collidepoint(event.pos):
                    self.panel_faction = fid
                    self.spirit_panel_spirit_id = None
                    self.faction_panel_scroll_offset = 0
                    if self.phase == Phase.VAGRANT_PHASE.value and self.faction_buttons:
                        available = set(self.phase_options.get("available_factions", []))
                        blocked = set(self.phase_options.get("worship_blocked", []))
                        if fid in available and fid not in blocked:
                            self.selected_faction = fid
                            if self.tutorial:
                                self.tutorial.notify_action("guidance_selected", {"faction": fid})
                    if self.tutorial:
                        self.tutorial.notify_action("faction_selected", {"faction": fid})
                    return

            # Hex click
            hex_coord = self.hex_renderer.get_hex_at_screen(
                event.pos[0], event.pos[1], self.input_handler,
                SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
            )
            if hex_coord:
                self._handle_hex_click(hex_coord)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if self.popup_manager.has_popups():
                self.popup_manager.handle_right_click(
                    event.pos, self.small_font, SCREEN_WIDTH)
                if self.tutorial:
                    self.tutorial.notify_action("tooltip_unfrozen", {})
            else:
                self._try_pin_hovered_tooltip(event.pos)
                if self.tutorial:
                    self.tutorial.notify_action("tooltip_frozen", {})

    def _handle_action_button(self, text: str):
        if self.ejection_pending:
            chosen_add = text.lower()
            if self.selected_ejection_remove_type == chosen_add:
                return
            self.selected_ejection_add_type = chosen_add
            return

    def _handle_faction_select(self, faction_id: str):
        self.selected_faction = faction_id
        self.panel_faction = faction_id
        self.spirit_panel_spirit_id = None
        self.faction_panel_scroll_offset = 0
        if self.tutorial:
            self.tutorial.notify_action("faction_selected", {"faction": faction_id})

    def _handle_idol_select(self, idol_type: str):
        self.selected_idol_type = idol_type

    def _handle_hex_click(self, hex_coord: tuple[int, int]):
        if self.phase == SubPhase.BATTLEGROUND_CHOICE:
            if hex_coord in self.battleground_selectable_hexes:
                idx = min(self.battleground_display_index,
                          len(self.battleground_choice_wars) - 1)
                wc = self.battleground_choice_wars[idx]
                war_id = wc["war_id"]
                choice = self.battleground_hex_to_choice[hex_coord]
                self.battleground_selections[war_id] = choice
                self.selected_hex = hex_coord
                self._update_battleground_selected_hexes(wc, choice)
            return
        if self.phase == SubPhase.EXPAND_CHOICE:
            if hex_coord in self.expand_choice_hexes:
                self.selected_hex = hex_coord
            return
        if self.phase == Phase.VAGRANT_PHASE.value and self.hex_ownership.get(hex_coord) is None:
            # Neutral hex during vagrant phase: select for idol placement
            my_id = self.app.my_spirit_id
            q, r = hex_coord
            if any(
                isinstance(idol, dict)
                and idol.get("owner_spirit") == my_id
                and idol.get("position", {}).get("q") == q
                and idol.get("position", {}).get("r") == r
                for idol in self.all_idols
            ):
                self._hex_error_message = "Hex already contains one of your Idols!"
                self._hex_error_timer = 2.0
                return
            self.selected_hex = hex_coord
        else:
            owner = self.hex_ownership.get(hex_coord)
            if owner:
                self.panel_faction = owner
                self.spirit_panel_spirit_id = None
                self.faction_panel_scroll_offset = 0
                # If guidance is available, also set as guide target
                if self.phase == Phase.VAGRANT_PHASE.value and self.faction_buttons:
                    available = set(self.phase_options.get("available_factions", []))
                    blocked = set(self.phase_options.get("worship_blocked", []))
                    if owner in available and owner not in blocked:
                        self.selected_faction = owner
                        if self.tutorial:
                            self.tutorial.notify_action("guidance_selected", {"faction": owner})
                if self.tutorial:
                    self.tutorial.notify_action("faction_selected", {"faction": owner})

    def _submit_action(self):
        if self.phase == Phase.VAGRANT_PHASE.value:
            can_swell = self.phase_options.get("can_swell", False)
            payload = {}
            if can_swell:
                payload["swell"] = True
            if self.selected_faction:
                payload["guide_target"] = self.selected_faction
            if self.selected_idol_type and self.selected_hex:
                payload["idol_type"] = self.selected_idol_type
                payload["idol_q"] = self.selected_hex[0]
                payload["idol_r"] = self.selected_hex[1]
            if payload:
                # Store previews before clearing
                if self.selected_faction:
                    self.preview_guidance = self.selected_faction
                if self.selected_idol_type and self.selected_hex:
                    self.preview_idol = (self.selected_idol_type,
                                         self.selected_hex[0], self.selected_hex[1])
                self.app.network.send(MessageType.SUBMIT_VAGRANT_ACTION, payload)
                self._clear_selection()
                self.has_submitted = True
                if self.tutorial:
                    self.tutorial.notify_action("vagrant_submitted", {})
        elif self.phase == Phase.AGENDA_PHASE.value:
            if self.selected_agenda_index >= 0:
                self.app.network.send(MessageType.SUBMIT_AGENDA_CHOICE, {
                    "agenda_index": self.selected_agenda_index,
                })
                self._clear_selection()
                self.has_submitted = True
                if self.tutorial:
                    self.tutorial.notify_action("agenda_submitted", {})
        elif self.phase == SubPhase.EJECTION_CHOICE:
            if (
                self.selected_ejection_remove_type
                and self.selected_ejection_add_type
                and self.selected_ejection_remove_type != self.selected_ejection_add_type
            ):
                self.app.network.send(MessageType.SUBMIT_EJECTION_AGENDA, {
                    "remove_type": self.selected_ejection_remove_type,
                    "add_type": self.selected_ejection_add_type,
                })
                self._clear_selection()
                self.ejection_pending = False
                self.has_submitted = True
                if self.tutorial:
                    self.tutorial.notify_action("ejection_submitted", {})
        elif self.phase == SubPhase.SPOILS_CHOICE:
            if all(e.selected >= 0 for e in self.spoils_entries):
                self.app.network.send(MessageType.SUBMIT_SPOILS_CHOICE,
                    {"card_indices": [e.selected for e in self.spoils_entries]})
                self.spoils_entries = []
                self.has_submitted = True
        elif self.phase == SubPhase.SPOILS_CHANGE_CHOICE:
            if all(e.selected >= 0 for e in self.spoils_change_entries):
                self.app.network.send(MessageType.SUBMIT_SPOILS_CHANGE_CHOICE,
                    {"card_indices": [e.selected for e in self.spoils_change_entries]})
                self.spoils_change_entries = []
                self.has_submitted = True
        elif self.phase == SubPhase.EXPAND_CHOICE:
            if self.selected_hex:
                q, r = self.selected_hex
                self.app.network.send(MessageType.SUBMIT_EXPAND_CHOICE, {"q": q, "r": r})
                self.expand_choice_hexes = set()
                self.expand_choice_faction = ""
                self.selected_hex = None
                self.has_submitted = True
        elif self.phase == SubPhase.BATTLEGROUND_CHOICE:
            if len(self.battleground_selections) >= len(self.battleground_choice_wars):
                self._do_submit_battleground()

    def _submit_card_choice(self, index: int, msg_type: MessageType, card_attr: str):
        self.app.network.send(msg_type, {"card_index": index})
        setattr(self, card_attr, [])
        self.has_submitted = True

    def _clear_selection(self):
        self.selected_faction = None
        self.selected_hex = None
        self.selected_idol_type = None
        self.panel_faction = None
        self.selected_agenda_index = -1
        self.selected_ejection_remove_type = None
        self.selected_ejection_add_type = None
        self.ejection_pool = []
        self.agenda_hand = []
        self.action_buttons = []
        self.remove_buttons = []
        self.faction_buttons = []
        self.idol_buttons = []
        self.submit_button = None
        self.guidance_title_rect = None
        self.guidance_title_hovered = False
        self.idol_title_rect = None
        self.idol_title_hovered = False
        self.ejection_keyword_rects = {}
        self.hovered_ejection_keyword = None
        self.battleground_choice_wars = []
        self.battleground_selections = {}
        self.battleground_display_index = 0
        self.battleground_selectable_hexes = set()
        self.battleground_selected_hexes = set()
        self.battleground_hex_to_choice = {}
        self.expand_choice_hexes = set()
        self.expand_choice_faction = ""

    def handle_network(self, msg_type, payload):
        handler = self._net_handlers.get(msg_type)
        if handler:
            handler(payload)

    def _handle_game_start(self, payload):
        self._phase_result_queue = []
        self._pending_game_over = None
        self.game_over = False
        self.game_over_data = None
        self._update_state_from_snapshot(payload)
        self.change_tracker.snapshot_and_reset(self.factions, self.spirits)
        self.event_log.append("Game started.")
        self.spectator_mode = self.app.my_spirit_id not in self.spirits
        # Activate tutorial overlay in tutorial mode
        if self.app.tutorial_mode and not self.spectator_mode:
            self.tutorial = TutorialManager()
            self.tutorial.activate()
            self._tutorial_anim_notified = False
        else:
            self.tutorial = None

    def _handle_phase_start(self, payload):
        phase = payload.get("phase", "")
        action = payload.get("options", {}).get("action", "")
        needs_input = action not in ("none", "") or phase in (
            SubPhase.CHANGE_CHOICE, SubPhase.SPOILS_CHOICE,
            SubPhase.SPOILS_CHANGE_CHOICE, SubPhase.EJECTION_CHOICE,
            SubPhase.BATTLEGROUND_CHOICE, SubPhase.EXPAND_CHOICE)
        should_defer = (
            needs_input
            and (
                self.orchestrator.has_animations_playing()
                or self._phase_result_queue
                or (self.tutorial and self.tutorial.is_blocking_phase_ui())
            )
        )
        if should_defer:
            self.orchestrator.deferred_phase_start = payload
        else:
            self.phase = payload.get("phase", self.phase)
            self.turn = payload.get("turn", self.turn)
            self.phase_options = payload.get("options", {})
            self._setup_phase_ui()

    def _handle_waiting_for(self, payload):
        self.waiting_for = payload.get("players_remaining", [])

    def _handle_phase_result(self, payload):
        """Queue PHASE_RESULT for sequential processing in update()."""
        if self.tutorial:
            self.tutorial.notify_game_event("phase_result_received", {})
        self._phase_result_queue.append(payload)

    def _process_phase_result(self, payload):
        active_sub_phase = self.phase if self.phase in (
            SubPhase.CHANGE_CHOICE, SubPhase.SPOILS_CHOICE, SubPhase.SPOILS_CHANGE_CHOICE,
            SubPhase.EJECTION_CHOICE, SubPhase.BATTLEGROUND_CHOICE,
            SubPhase.EXPAND_CHOICE) else None
        # Snapshot display state before updating so animations render old state
        events = payload.get("events", [])
        _ANIM_ORDER = {
            "trade": 0, "steal": 1,
            "expand": 2, "expand_failed": 2, "expand_spoils": 2,
            "change": 3,
        }
        agenda_events = [e for e in events if e.get("type", "") in _ANIM_ORDER
                       and not e.get("is_guided_modifier")]
        if agenda_events and "state" in payload:
            # Clear any stale display state before re-snapshotting so that
            # fast AI-only games (queue never fully drains) always get a fresh
            # baseline for hex-reveal and war-reveal animations each turn.
            self._clear_display_state()
            self._snapshot_display_state()
        if "state" in payload:
            self._update_state_from_snapshot(payload["state"])
        # Preserve sub-phases while this player still has cards to choose
        if active_sub_phase == SubPhase.CHANGE_CHOICE and self.change_cards:
            self.phase = active_sub_phase
        elif active_sub_phase == SubPhase.SPOILS_CHOICE and self.spoils_entries:
            self.phase = active_sub_phase
        elif active_sub_phase == SubPhase.SPOILS_CHANGE_CHOICE and self.spoils_change_entries:
            self.phase = active_sub_phase
        elif active_sub_phase == SubPhase.EJECTION_CHOICE and self.ejection_pending:
            self.phase = active_sub_phase
        elif active_sub_phase == SubPhase.BATTLEGROUND_CHOICE and self.battleground_choice_wars:
            self.phase = active_sub_phase
        elif active_sub_phase == SubPhase.EXPAND_CHOICE and self.expand_choice_hexes:
            self.phase = active_sub_phase
        # Log events (consolidate agenda play + resolution into one line)
        self._log_events_batch(events)
        # VP gain animations
        for event in events:
            if event.get("type") == "vp_scored":
                vp = event.get("vp_gained", 0)
                sid = event.get("spirit", "")
                if vp > 0 and sid:
                    vp_pos = self.ui_renderer.vp_positions.get(sid)
                    if vp_pos:
                        self.animation.add_effect_animation(TextAnimation(
                            f"+{vp} VP", vp_pos[0], vp_pos[1] + 16,
                            (80, 255, 80),
                            delay=0.0, duration=3.0, drift_pixels=40,
                            direction=1, screen_space=True,
                        ))
                        # Idol VP beams: one streaking beam per contributing idol
                        faction_id = event.get("faction", "")
                        wars_won = event.get("wars_won", 0)
                        gold_gained_ev = event.get("gold_gained", 0)
                        territories_gained = event.get("territories_gained", 0)
                        active_types = {}
                        if event.get("battle_idols", 0) > 0 and wars_won > 0:
                            active_types["battle"] = (255, 60, 80)
                        if event.get("affluence_idols", 0) > 0 and gold_gained_ev > 0:
                            active_types["affluence"] = (255, 200, 50)
                        if event.get("spread_idols", 0) > 0 and territories_gained > 0:
                            active_types["spread"] = (60, 220, 100)
                        if faction_id and active_types:
                            spirit_idx_map = {
                                s: i for i, s in enumerate(sorted(self.spirits.keys()))
                            }
                            beam_delay = 0.0
                            for idol_data in self.all_idols:
                                if not isinstance(idol_data, dict):
                                    continue
                                pos = idol_data.get("position", {})
                                q, r = pos.get("q"), pos.get("r")
                                if self.hex_ownership.get((q, r)) != faction_id:
                                    continue
                                beam_color = active_types.get(idol_data.get("type"))
                                if beam_color is None:
                                    continue
                                wx, wy = axial_to_pixel(q, r, HEX_SIZE)
                                player_idx = spirit_idx_map.get(
                                    idol_data.get("owner_spirit"), 0
                                )
                                angle = math.radians(-90 + player_idx * 60)
                                wx += math.cos(angle) * (HEX_SIZE / 2)
                                wy += math.sin(angle) * (HEX_SIZE / 2)
                                self.animation.add_effect_animation(IdolBeamAnimation(
                                    wx, wy,
                                    vp_pos[0], vp_pos[1] + 8,
                                    beam_color,
                                    delay=beam_delay, duration=1.5,
                                ))
                                beam_delay += 0.07
            elif event.get("type") == "swell":
                sid = event.get("spirit", "")
                if sid:
                    vp_pos = self.ui_renderer.vp_positions.get(sid)
                    if vp_pos:
                        self.animation.add_effect_animation(TextAnimation(
                            "+10 VP (Swell)", vp_pos[0], vp_pos[1] + 16,
                            (220, 200, 60),
                            delay=0.0, duration=3.0, drift_pixels=40,
                            direction=1, screen_space=True,
                        ))
        # Trigger agenda events immediately, but preserve turn_start segmentation
        # for bootstrap payloads so Turn 1 and Turn 2 do not animate concurrently.
        if agenda_events:
            turn_batched_events: list[list[dict]] = []
            current_turn_batch: list[dict] = []
            saw_turn_markers = False
            for event in events:
                etype = event.get("type", "")
                if etype == "turn_start":
                    saw_turn_markers = True
                    if current_turn_batch:
                        turn_batched_events.append(current_turn_batch)
                        current_turn_batch = []
                    continue
                if (etype in _ANIM_ORDER or etype == "war_erupted") and not event.get("is_guided_modifier"):
                    current_turn_batch.append(event)
            if current_turn_batch:
                turn_batched_events.append(current_turn_batch)

            if not saw_turn_markers:
                war_events = [e for e in events if e.get("type") == "war_erupted"]
                anim_events = agenda_events + war_events
                self.orchestrator.process_agenda_events(
                    anim_events, self.hex_ownership, self.small_font)
            else:
                for batch in turn_batched_events:
                    self.orchestrator.process_agenda_events(
                        batch, self.hex_ownership, self.small_font)
        # Clear previews after processing phase results
        self.preview_guidance = None
        self.preview_idol = None

    def _refire_tutorial_phase_events(self):
        """Re-fire phase events for steps that became pending while already in the relevant phase."""
        if not self.tutorial or not self.tutorial._step_pending_show:
            return
        idx = self.tutorial.step_idx
        action = self.phase_options.get("action", "none")
        # Steps 8 and 10 trigger on agenda_phase_started; may already be in that phase
        if idx in (8, 10) and self.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
            hand = self.phase_options.get("hand", [])
            self.tutorial.notify_game_event("agenda_phase_started", {
                "turn": self.turn,
                "draw_count": len(hand),
            })
        # Step 14 triggers on ejection_phase_started
        elif idx == 14 and self.phase == SubPhase.EJECTION_CHOICE:
            self.tutorial.notify_game_event("ejection_phase_started", {"turn": self.turn})

    def _handle_game_over(self, payload):
        # Game-over event will be in the PHASE_RESULT events; transition scene
        self.app.set_scene("results")

    def _handle_error(self, payload):
        self.event_log.append(f"Error: {payload.get('message', '?')}")

    def _setup_change_choice_ui(self):
        self.change_cards = self.phase_options.get("cards") or []
        if self.tutorial:
            my_spirit = self.spirits.get(self.app.my_spirit_id, {})
            influence = my_spirit.get("influence", 0)
            self.tutorial.notify_game_event("change_drawn", {
                "influence": influence,
                "card_count": len(self.change_cards),
            })

    def _setup_spoils_choice_ui(self):
        if self.tutorial:
            self.tutorial.notify_game_event("guided_spoils_drawn", {})
        choices = self.phase_options.get("choices", [])
        if choices:
            self.spoils_entries = [
                SpoilsEntry(cards=c.get("cards", []), loser=c.get("loser", ""))
                for c in choices
            ]
        else:
            # Backwards compat: single-war format
            cards = self.phase_options.get("cards", [])
            loser = self.phase_options.get("loser", "")
            self.spoils_entries = [SpoilsEntry(cards=cards, loser=loser)] if cards else []
        self.spoils_display_index = 0
        self.submit_button = Button(
            pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
            "Confirm", (60, 130, 60)
        )

    def _setup_spoils_change_choice_ui(self):
        choices = self.phase_options.get("choices", [])
        if choices:
            self.spoils_change_entries = [
                SpoilsEntry(cards=c.get("cards", []), loser=c.get("loser", ""))
                for c in choices
            ]
        else:
            cards = self.phase_options.get("cards", [])
            loser = self.phase_options.get("loser", "")
            self.spoils_change_entries = [SpoilsEntry(cards=cards, loser=loser)] if cards else []
        self.spoils_display_index = 0
        self.submit_button = Button(
            pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
            "Confirm", (60, 130, 60)
        )

    def _setup_ejection_choice_ui(self):
        self.ejection_pending = True
        self.ejection_faction = self.phase_options.get("faction", "")
        self.ejection_pool = self.phase_options.get("agenda_pool", [])
        self.selected_ejection_remove_type = None
        self.selected_ejection_add_type = None
        modifiers = self._get_faction_modifiers(self.ejection_faction)
        btn_x, btn_w, btn_h, btn_gap = 20, 157, 36, 6
        # Build remove buttons (one per unique type in the current pool) — vertical
        y_remove = 300
        self.remove_buttons = []
        seen_types: list[str] = []
        for at_str in self.ejection_pool:
            if at_str not in seen_types:
                seen_types.append(at_str)
        for i, at_str in enumerate(seen_types):
            tooltip = build_agenda_tooltip(at_str, modifiers)
            btn = Button(
                pygame.Rect(btn_x, y_remove + i * (btn_h + btn_gap), btn_w, btn_h),
                at_str.title(), (110, 50, 50),
                tooltip=tooltip,
                tooltip_always=True,
            )
            self.remove_buttons.append(btn)
        # Build add buttons (all agenda types) — vertical, below remove buttons
        n_remove = len(seen_types)
        y_add = y_remove + n_remove * (btn_h + btn_gap) + 28
        self.action_buttons = []
        for i, at in enumerate(AgendaType):
            tooltip = build_agenda_tooltip(at.value, modifiers)
            btn = Button(
                pygame.Rect(btn_x, y_add + i * (btn_h + btn_gap), btn_w, btn_h),
                at.value.title(), (80, 60, 130),
                tooltip=tooltip,
                tooltip_always=True,
            )
            self.action_buttons.append(btn)
        self.submit_button = Button(
            pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
            "Confirm", (60, 130, 60)
        )

    def _setup_expand_choice_ui(self):
        """Set up state for the expand_choice sub-phase."""
        hexes = self.phase_options.get("hexes", [])
        self.expand_choice_hexes = {(h["q"], h["r"]) for h in hexes}
        self.expand_choice_faction = self.phase_options.get("faction", "")
        self.selected_hex = None
        self.submit_button = Button(
            pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
            "Confirm", (60, 130, 60)
        )

    def _setup_battleground_choice_ui(self):
        """Set up state for the battleground_choice sub-phase."""
        wars = self.phase_options.get("wars", [])
        self.battleground_choice_wars = wars
        self.battleground_selections = {}
        self.battleground_display_index = 0
        self._refresh_battleground_hex_sets()
        self.submit_button = Button(
            pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
            "Confirm", (60, 130, 60)
        )
        # Auto-select any war with only one possible choice
        for wc in self.battleground_choice_wars:
            if wc["war_id"] in self.battleground_selections:
                continue
            if wc["mode"] == "full":
                pairs = wc.get("pairs", [])
                if len(pairs) == 1:
                    self.battleground_selections[wc["war_id"]] = 0
            else:
                enemy_hexes = wc.get("enemy_hexes", [])
                if len(enemy_hexes) == 1:
                    h = enemy_hexes[0]
                    self.battleground_selections[wc["war_id"]] = (h["q"], h["r"])
        # Update highlight for the displayed war after auto-selection
        self._refresh_battleground_hex_sets()
        # If all wars were auto-selected, submit immediately (no interaction needed)
        if (self.battleground_choice_wars
                and len(self.battleground_selections) >= len(self.battleground_choice_wars)):
            self._do_submit_battleground()

    def _refresh_battleground_hex_sets(self):
        """Rebuild the selectable hex set for the currently displayed war."""
        self.battleground_selectable_hexes = set()
        self.battleground_hex_to_choice = {}
        if not self.battleground_choice_wars:
            self.battleground_selected_hexes = set()
            return
        idx = min(self.battleground_display_index, len(self.battleground_choice_wars) - 1)
        wc = self.battleground_choice_wars[idx]
        if wc["mode"] == "full":
            for i, pair in enumerate(wc.get("pairs", [])):
                ha = (pair["hex_a"]["q"], pair["hex_a"]["r"])
                hb = (pair["hex_b"]["q"], pair["hex_b"]["r"])
                self.battleground_selectable_hexes.add(ha)
                self.battleground_selectable_hexes.add(hb)
                # Each hex maps to the pair index (clicking either hex selects the pair)
                if ha not in self.battleground_hex_to_choice:
                    self.battleground_hex_to_choice[ha] = i
                if hb not in self.battleground_hex_to_choice:
                    self.battleground_hex_to_choice[hb] = i
        else:  # enemy_side
            for h in wc.get("enemy_hexes", []):
                coord = (h["q"], h["r"])
                self.battleground_selectable_hexes.add(coord)
                self.battleground_hex_to_choice[coord] = coord
        # Reflect any existing selection for this war as the selected-pair highlight
        existing = self.battleground_selections.get(wc["war_id"])
        self._update_battleground_selected_hexes(wc, existing)

    def _update_battleground_selected_hexes(self, wc: dict, choice):
        """Update battleground_selected_hexes to reflect the chosen pair/hex."""
        if choice is None:
            self.battleground_selected_hexes = set()
            return
        if wc["mode"] == "full":
            pairs = wc.get("pairs", [])
            if isinstance(choice, int) and 0 <= choice < len(pairs):
                pair = pairs[choice]
                ha = (pair["hex_a"]["q"], pair["hex_a"]["r"])
                hb = (pair["hex_b"]["q"], pair["hex_b"]["r"])
                self.battleground_selected_hexes = {ha, hb}
            else:
                self.battleground_selected_hexes = set()
        else:
            self.battleground_selected_hexes = {choice}

    def _do_submit_battleground(self):
        """Send the battleground choice to the server and reset state."""
        choices = []
        for wc in self.battleground_choice_wars:
            sel = self.battleground_selections.get(wc["war_id"])
            if sel is None:
                return
            if wc["mode"] == "full":
                choices.append({"war_id": wc["war_id"], "pair_index": sel})
            else:
                choices.append({"war_id": wc["war_id"],
                                "hex": {"q": sel[0], "r": sel[1]}})
        self.app.network.send(MessageType.SUBMIT_BATTLEGROUND_CHOICE,
            {"choices": choices})
        self.battleground_choice_wars = []
        self.battleground_selections = {}
        self.battleground_selectable_hexes = set()
        self.battleground_selected_hexes = set()
        self.selected_hex = None
        self.has_submitted = True

    def _setup_phase_ui(self):
        """Build UI elements for the current phase."""
        self._clear_selection()
        self.has_submitted = False
        action = self.phase_options.get("action", "none")
        # Tutorial phase notifications (fired when UI is actually set up)
        if self.tutorial:
            if self.phase == Phase.VAGRANT_PHASE.value and action == "choose":
                self.tutorial.notify_game_event("vagrant_phase_started", {
                    "turn": self.turn,
                })
            elif self.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
                hand = self.phase_options.get("hand", [])
                self.tutorial.notify_game_event("agenda_phase_started", {
                    "turn": self.turn,
                    "draw_count": len(hand),
                })
            elif self.phase == SubPhase.EJECTION_CHOICE:
                self.tutorial.notify_game_event("ejection_phase_started", {
                    "turn": self.turn,
                })

        _SUB_PHASE_SETUP = {
            SubPhase.CHANGE_CHOICE:        self._setup_change_choice_ui,
            SubPhase.SPOILS_CHOICE:        self._setup_spoils_choice_ui,
            SubPhase.SPOILS_CHANGE_CHOICE: self._setup_spoils_change_choice_ui,
            SubPhase.EJECTION_CHOICE:      self._setup_ejection_choice_ui,
            SubPhase.BATTLEGROUND_CHOICE:  self._setup_battleground_choice_ui,
            SubPhase.EXPAND_CHOICE:        self._setup_expand_choice_ui,
        }
        if self.phase in _SUB_PHASE_SETUP:
            _SUB_PHASE_SETUP[self.phase]()
            return

        if self.phase == Phase.VAGRANT_PHASE.value and action == "choose":
            # Build faction buttons (left) and idol buttons (right)
            self._build_faction_buttons()
            if self.phase_options.get("can_place_idol", True):
                self._build_idol_buttons()
            if self.phase_options.get("can_swell"):
                self.submit_button = Button(
                    pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
                    "Swell", (140, 110, 20),
                    tooltip="No Guidance targets available.\nSwell to gain 10 VP.",
                    tooltip_always=True,
                )
            else:
                self.submit_button = Button(
                    pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
                    "Confirm", (60, 130, 60)
                )

        elif self.phase == Phase.AGENDA_PHASE.value and action == "choose_agenda":
            hand = self.phase_options.get("hand", [])
            _agenda_order = {"trade": 0, "steal": 1, "expand": 2, "change": 3}
            self.agenda_hand = sorted(hand, key=lambda c: _agenda_order.get(c.get("agenda_type", ""), 99))
            self.selected_agenda_index = -1
            self.submit_button = Button(
                pygame.Rect(20, SCREEN_HEIGHT - 60, 156, 48),
                "Confirm", (60, 130, 60)
            )

    def _count_spirit_idols_in_faction(self, spirit_id: str, faction_id: str) -> int:
        """Count idols owned by a spirit in a faction's territory."""
        count = 0
        for idol in self.all_idols:
            if isinstance(idol, dict):
                if idol.get('owner_spirit') == spirit_id:
                    pos = idol.get('position', {})
                    q, r = pos.get('q'), pos.get('r')
                    if self.hex_ownership.get((q, r)) == faction_id:
                        count += 1
        return count

    def _build_guidance_tooltip(self, faction_id: str, is_blocked: bool,
                                is_contested_blocked: bool = False) -> str:
        """Build tooltip for a Guidance faction button."""
        fdata = self.factions.get(faction_id, {})
        worship_id = fdata.get("worship_spirit") if isinstance(fdata, dict) else None
        lines = []
        if is_contested_blocked:
            lines.append("Contested last turn;")
            lines.append("cannot target this turn.")
        elif is_blocked:
            lines.append("This Faction Worships you;")
            lines.append("you cannot Guide them.")
        elif worship_id:
            name = self.spirits.get(worship_id, {}).get("name", worship_id[:6])
            lines.append(f"Worshipping: {name}")
            my_id = self.app.my_spirit_id
            my_idols = self._count_spirit_idols_in_faction(my_id, faction_id)
            their_idols = self._count_spirit_idols_in_faction(worship_id, faction_id)
            if my_idols >= their_idols:
                lines.append("Guiding will make you Worshipped")
            else:
                lines.append(f"You need more Idols to become")
                lines.append(f"Worshipped ({my_idols} vs {their_idols})")
        else:
            lines.append("Not Worshipped by any Spirit")
            lines.append("Guiding will make you Worshipped")
        return "\n".join(lines)

    def _build_faction_buttons(self):
        available = [
            fid for fid in self.phase_options.get("available_factions", [])
            if not self.factions.get(fid, {}).get("eliminated", False)
        ]
        blocked = self.phase_options.get("worship_blocked", [])
        contested_blocked = self.phase_options.get("contested_blocked", [])
        self.faction_buttons = []
        self.faction_button_ids = []
        all_factions = available + blocked + contested_blocked
        all_factions.sort(key=lambda fid: self.faction_order.index(fid) if fid in self.faction_order else 999)
        for i, fid in enumerate(all_factions):
            color = FACTION_COLORS.get(fid, (100, 100, 100))
            is_blocked = fid in blocked
            is_contested_blocked = fid in contested_blocked
            tooltip = self._build_guidance_tooltip(fid, is_blocked, is_contested_blocked)
            btn = Button(
                pygame.Rect(_GUIDANCE_BTN_X, _BTN_START_Y + i * _BTN_STEP_Y, _BTN_W, _BTN_H),
                faction_full_name(fid),
                color=tuple(max(c // 2, 30) for c in color),
                text_color=(255, 255, 255),
                tooltip=tooltip,
                tooltip_always=True,
            )
            if is_blocked or is_contested_blocked:
                btn.enabled = False
            self.faction_buttons.append(btn)
            self.faction_button_ids.append(fid)
        # Set up guidance title rect
        title_w = 100
        self.guidance_title_rect = pygame.Rect(
            _GUIDANCE_CENTER_X - title_w // 2, _TITLE_Y, title_w, 22
        )

    def _build_idol_buttons(self):
        idol_tooltips = {
            IdolType.BATTLE: f"{BATTLE_IDOL_VP} VP for each war won\nby the Worshipping Faction",
            IdolType.AFFLUENCE: f"{AFFLUENCE_IDOL_VP} VP for each gold gained\nby the Worshipping Faction",
            IdolType.SPREAD: f"{SPREAD_IDOL_VP} VP for each territory gained\nby the Worshipping Faction",
        }
        # Place idol buttons below guidance buttons on the left side
        n_factions = len(self.faction_buttons)
        last_guidance_bottom = _BTN_START_Y + (n_factions - 1) * _BTN_STEP_Y + _BTN_H
        idol_title_y = last_guidance_bottom + 10
        idol_start_y = idol_title_y + 28  # title height (22) + 6px gap
        self.idol_buttons = []
        for i, it in enumerate(IdolType):
            colors = {
                IdolType.BATTLE: (130, 50, 50),
                IdolType.AFFLUENCE: (130, 120, 30),
                IdolType.SPREAD: (50, 120, 50),
            }
            btn = Button(
                pygame.Rect(_GUIDANCE_BTN_X, idol_start_y + i * _BTN_STEP_Y, _BTN_W, _BTN_H),
                it.value.title(), colors.get(it, (80, 80, 80)),
                tooltip=idol_tooltips.get(it),
                tooltip_always=True,
            )
            self.idol_buttons.append(btn)
        # Set up idol title rect (same center x as guidance)
        title_w = 130
        self.idol_title_rect = pygame.Rect(
            _GUIDANCE_CENTER_X - title_w // 2, idol_title_y, title_w, 22
        )

    def _calc_card_rects(self, count: int, start_x: int = 20, y: int = 125,
                         centered: bool = False) -> list[pygame.Rect]:
        spacing = 10
        if centered:
            total_w = count * (_CARD_W + spacing) - spacing
            start_x = SCREEN_WIDTH // 2 - total_w // 2
        return [pygame.Rect(start_x + i * (_CARD_W + spacing), y, _CARD_W, _CARD_H_TALL)
                for i in range(count)]

    def _calc_left_choice_card_rects(self, count: int, y: int = _CHOICE_CARD_Y) -> list[pygame.Rect]:
        """Card rects stacked vertically in the left panel."""
        card_x = max(20, (_HEX_MAP_LEFT_X - _CARD_W) // 2)
        return [pygame.Rect(card_x, y + i * (_CARD_H + _CARD_SPACING), _CARD_W, _CARD_H)
                for i in range(count)]

    def _update_guided_hex_hover(self, mouse_pos):
        """Check if mouse is hovering over the guidance sigil at a hex center."""
        hex_coord = self.hex_renderer.get_hex_at_screen(
            mouse_pos[0], mouse_pos[1], self.input_handler,
            SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
        )
        if hex_coord is None:
            self.hovered_guided_hex_spirit = None
            return
        faction_id = self.hex_ownership.get(hex_coord)
        if not faction_id:
            self.hovered_guided_hex_spirit = None
            return
        fdata = self.factions.get(faction_id, {})
        guiding = fdata.get("guiding_spirit") if isinstance(fdata, dict) else None
        if not guiding:
            self.hovered_guided_hex_spirit = None
            return
        # Check mouse is within sigil hit radius at hex center
        wx, wy = axial_to_pixel(hex_coord[0], hex_coord[1], HEX_SIZE)
        sx, sy = self.input_handler.world_to_screen(wx, wy, SCREEN_WIDTH, SCREEN_HEIGHT)
        sigil_hit_radius = HEX_SIZE / 3
        if math.dist(mouse_pos, (sx, sy)) <= sigil_hit_radius:
            self.hovered_guided_hex_spirit = guiding
        else:
            self.hovered_guided_hex_spirit = None

    def _update_idol_hover(self, mouse_pos):
        """Check if mouse is hovering over a placed idol on the hex map."""
        if not self._render_idols_cache:
            self.hovered_idol = None
            self.idol_tooltip_spirit_rects = []
            return
        spirit_index_map = {
            sid: i for i, sid in enumerate(sorted(self.spirits.keys()))
        }
        self.hovered_idol = self.hex_renderer.get_idol_at_screen(
            mouse_pos[0], mouse_pos[1], self._render_idols_cache,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            spirit_index_map,
        )
        if self.hovered_idol is None:
            self.idol_tooltip_spirit_rects = []

    def _get_faction_modifiers(self, faction_id: str) -> dict:
        """Get the change_modifiers for a given faction."""
        fdata = self.factions.get(faction_id, {})
        if isinstance(fdata, dict):
            return fdata.get("change_modifiers", {})
        return {}

    def _update_agenda_hover(self, mouse_pos):
        """Check if mouse is hovering over agenda cards, faction labels, or animations."""
        self.hovered_card_tooltip = None
        self.hovered_card_rect = None
        self.hovered_agenda_label_fid = None
        self.hovered_agenda_label_type = None
        self.hovered_agenda_label_is_spoils = False
        self.hovered_agenda_label_rect = None
        self.hovered_anim_tooltip = None
        self.hovered_anim_rect = None

        mx, my = mouse_pos

        # Check card pickers (agenda hand, change cards, spoils cards, spoils change cards)
        modifiers = self._get_current_faction_modifiers()

        if self.agenda_hand:
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.agenda_hand))):
                if rect.collidepoint(mx, my):
                    atype = self.agenda_hand[i].get("agenda_type", "")
                    self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers)
                    self.hovered_card_rect = rect
                    return

        if self.change_cards:
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.change_cards))):
                if rect.collidepoint(mx, my):
                    self.hovered_card_tooltip = build_modifier_tooltip(self.change_cards[i])
                    self.hovered_card_rect = rect
                    return

        if self.spoils_entries:
            sidx = max(0, min(self.spoils_display_index, len(self.spoils_entries) - 1))
            entry = self.spoils_entries[sidx]
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(entry.cards))):
                if rect.collidepoint(mx, my):
                    atype = entry.cards[i]
                    self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers, is_spoils=True)
                    self.hovered_card_rect = rect
                    return

        if self.spoils_change_entries:
            sidx = max(0, min(self.spoils_display_index, len(self.spoils_change_entries) - 1))
            entry = self.spoils_change_entries[sidx]
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(entry.cards))):
                if rect.collidepoint(mx, my):
                    self.hovered_card_tooltip = build_modifier_tooltip(entry.cards[i])
                    self.hovered_card_rect = rect
                    return

        # Check faction ribbon agenda labels
        for fid, agenda_type, is_spoils, rect in self.agenda_label_rects:
            if rect.collidepoint(mx, my):
                self.hovered_agenda_label_fid = fid
                self.hovered_agenda_label_type = agenda_type
                self.hovered_agenda_label_is_spoils = is_spoils
                self.hovered_agenda_label_rect = rect
                return

        # Check persistent agenda slide animations
        for anim in self.animation.get_persistent_agenda_animations():
            if not anim.active or not anim.agenda_type:
                continue
            img_w = anim.image.get_width()
            img_h = anim.image.get_height()
            anim_rect = pygame.Rect(int(anim.x), int(anim.y), img_w, img_h)
            if anim_rect.collidepoint(mx, my):
                fid = anim.faction_id
                fmod = self._get_faction_modifiers(fid)
                self.hovered_anim_tooltip = build_agenda_tooltip(
                    anim.agenda_type, fmod, is_spoils=anim.is_spoils)
                self.hovered_anim_rect = anim_rect
                return

    def _update_panel_hover(self, mouse_pos):
        """Check if mouse is hovering over hoverable faction panel labels."""
        mx, my = mouse_pos
        r = self.ui_renderer.panel_guided_rect
        self.hovered_panel_guided = r is not None and r.collidepoint(mx, my)
        r = self.ui_renderer.panel_worship_rect
        self.hovered_panel_worship = r is not None and r.collidepoint(mx, my)
        r = self.ui_renderer.panel_war_rect
        self.hovered_panel_war = r is not None and r.collidepoint(mx, my)

    def _update_vp_hover(self, mouse_pos):
        """Check if mouse is hovering over a player name in the VP HUD."""
        mx, my = mouse_pos
        self.hovered_vp_spirit_id = None
        for sid, rect in self.ui_renderer.vp_hover_rects.items():
            if rect.collidepoint(mx, my):
                self.hovered_vp_spirit_id = sid
                return

    def _check_spirit_panel_hover(self, rects: dict, mx: int, my: int):
        """Return (guidance_hov, influence_hov, worship_hov, affinity_hov) for a spirit panel's rects dict."""
        r = rects.get("guidance")
        guidance = r is not None and r.collidepoint(mx, my)
        r = rects.get("influence")
        influence = r is not None and r.collidepoint(mx, my)
        worship = None
        for fid, rect in rects.get("worship", {}).items():
            if rect.collidepoint(mx, my):
                worship = fid
                break
        r = rects.get("affinity")
        affinity = r is not None and r.collidepoint(mx, my)
        return guidance, influence, worship, affinity

    def _update_spirit_panel_hover(self, mouse_pos):
        """Check if mouse is hovering over elements in either spirit panel."""
        mx, my = mouse_pos
        if not self.spirit_panel_spirit_id:
            self.hovered_spirit_panel_guidance = False
            self.hovered_spirit_panel_influence = False
            self.hovered_spirit_panel_worship = None
            self.hovered_spirit_panel_affinity = False
        else:
            (self.hovered_spirit_panel_guidance,
             self.hovered_spirit_panel_influence,
             self.hovered_spirit_panel_worship,
             self.hovered_spirit_panel_affinity) = self._check_spirit_panel_hover(self._spirit_panel_rects, mx, my)
        (self.hovered_persistent_spirit_guidance,
         self.hovered_persistent_spirit_influence,
         self.hovered_persistent_spirit_worship,
         self.hovered_persistent_spirit_affinity) = self._check_spirit_panel_hover(self._persistent_spirit_panel_rects, mx, my)

    def _update_ejection_title_hover(self, mouse_pos):
        """Check if mouse is hovering over keyword spans in ejection title text."""
        self.hovered_ejection_keyword = None
        if self.phase != "ejection_choice":
            return
        mx, my = mouse_pos
        for keyword, rects in self.ejection_keyword_rects.items():
            for rect in rects:
                if rect.collidepoint(mx, my):
                    self.hovered_ejection_keyword = keyword
                    return

    def _try_pin_hovered_tooltip(self, mouse_pos):
        """Pin the currently active tooltip from the registry as a popup."""
        self.tooltip_registry.try_pin(self.popup_manager, self.small_font, SCREEN_WIDTH)

    def _count_idol_vp_for_faction(self, faction_id: str):
        """Count total VP per event type from idols in a faction's territory.

        Returns (battle_vp, spread_vp, affluence_vp) totals.
        """
        battle_count = 0
        spread_count = 0
        affluence_count = 0
        for idol in self.all_idols:
            if isinstance(idol, dict):
                pos = idol.get('position', {})
                q, r = pos.get('q'), pos.get('r')
                if self.hex_ownership.get((q, r)) == faction_id:
                    itype = idol.get('type', '')
                    if itype == IdolType.BATTLE.value:
                        battle_count += 1
                    elif itype == IdolType.SPREAD.value:
                        spread_count += 1
                    elif itype == IdolType.AFFLUENCE.value:
                        affluence_count += 1
        return (
            battle_count * BATTLE_IDOL_VP,
            spread_count * SPREAD_IDOL_VP,
            affluence_count * AFFLUENCE_IDOL_VP,
        )

    _GUIDANCE_GENERIC_TOOLTIP = (
        "A Spirit can Guide a Faction by choosing it during the "
        "Vagrant phase. While Guiding, the Spirit draws from the "
        "Faction's Agenda pool and picks which Agenda the Faction "
        "plays each turn. Guidance lasts until the Spirit's "
        "Influence runs out."
    )

    _UNGUIDED_FACTION_TOOLTIP = (
        "This Faction is not currently Guided by any Spirit. "
        "An unguided Faction draws and plays 1 random Agenda "
        "from its Agenda pool each turn. A Vagrant Spirit can "
        "choose to Guide it during the Vagrant phase."
    )

    def _build_guidance_panel_tooltip(self, spirit_id: str | None) -> str:
        """Build tooltip text for Guided by / VP name hover."""
        if not spirit_id:
            return self._UNGUIDED_FACTION_TOOLTIP
        spirit = self.spirits.get(spirit_id, {})
        influence = spirit.get("influence", 0)
        return (
            "When Guidance begins, the Spirit's Influence is set to 3. "
            "Spirits draw 1 Agenda card + however much Influence they have "
            "from the Guided Faction's Agenda pool, choose 1 of the drawn "
            "Agendas for their Guided Faction to play, then lose 1 Influence. "
            f"This Spirit currently has {influence} remaining Influence and "
            f"will become Vagrant again after that many turns."
        )

    def _build_ribbon_war_tooltip(self, fid: str) -> str:
        """Build 'At War with: Mountain, Mesa' tooltip for ribbon war indicator."""
        war_names = []
        for w in self.display_wars:
            fa = w.get('faction_a') if isinstance(w, dict) else getattr(w, 'faction_a', None)
            fb = w.get('faction_b') if isinstance(w, dict) else getattr(w, 'faction_b', None)
            if fa == fid:
                war_names.append(faction_full_name(fb))
            elif fb == fid:
                war_names.append(faction_full_name(fa))
        if not war_names:
            return "At War with: (none)"
        return f"At War with: {', '.join(war_names)}"

    def _build_worship_panel_tooltip(self, faction_id: str) -> str:
        """Build tooltip text for Worshipping hover."""
        worship_id = self.ui_renderer.panel_worship_spirit_id
        battle_vp, spread_vp, affluence_vp = self._count_idol_vp_for_faction(faction_id)

        def _fmt(v):
            return f"{v:g}"

        if worship_id:
            name = self.spirits.get(worship_id, {}).get("name", worship_id[:6])
            return (
                f"At the end of every turn, this Faction will give {name} "
                f"{_fmt(battle_vp)} VPs for each battle it won, "
                f"{_fmt(spread_vp)} VPs for each new Territory it acquired and "
                f"{_fmt(affluence_vp)} VPs for each gold it acquired during that turn."
            )
        else:
            return (
                f"At the end of every turn, this Faction would give "
                f"{_fmt(battle_vp)} VPs for each battle it won, "
                f"{_fmt(spread_vp)} VPs for each new Territory it acquired and "
                f"{_fmt(affluence_vp)} VPs for each gold it acquired during that turn "
                f"to whoever it Worships. The first Spirit to Guide it will become Worshipped."
            )

    def _build_spirit_worship_tooltip(self, faction_id: str, spirit_id: str) -> str:
        """Build tooltip for a faction worshipping a spirit in the spirit panel."""
        battle_vp, spread_vp, affluence_vp = self._count_idol_vp_for_faction(faction_id)
        faction_name = faction_full_name(faction_id)

        def _fmt(v):
            return f"{v:g}"

        if spirit_id == self.app.my_spirit_id:
            return (
                f"{faction_name} Worships you. Each turn it gives you "
                f"{_fmt(battle_vp)} VP per battle won, "
                f"{_fmt(spread_vp)} VP per territory gained, and "
                f"{_fmt(affluence_vp)} VP per gold earned."
            )
        else:
            spirit_name = self.spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            return (
                f"{faction_name} Worships {spirit_name}. Each turn it gives them "
                f"{_fmt(battle_vp)} VP per battle won, "
                f"{_fmt(spread_vp)} VP per territory gained, and "
                f"{_fmt(affluence_vp)} VP per gold earned."
            )

    def _offer_spirit_panel_tooltip(self, spirit_id: str, rects: dict,
                                     guidance_hov: bool, influence_hov: bool,
                                     worship_hov: "str | None", below: bool,
                                     affinity_hov: bool = False):
        """Offer the appropriate tooltip for whichever element of a spirit panel is hovered."""
        if guidance_hov:
            spirit = self.spirits.get(spirit_id, {})
            tooltip = (self._build_guidance_panel_tooltip(spirit_id)
                       if spirit.get("guided_faction") else self._GUIDANCE_GENERIC_TOOLTIP)
            r = rects["guidance"]
            anchor = r.bottom if below else r.top
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS, r.centerx, anchor, below=below,
            ))
        elif influence_hov:
            r = rects["influence"]
            anchor = r.bottom if below else r.top
            self.tooltip_registry.offer(TooltipDescriptor(
                _INFLUENCE_TOOLTIP, _GUIDANCE_HOVER_REGIONS, r.centerx, anchor, below=below,
            ))
        elif worship_hov:
            tooltip = self._build_spirit_worship_tooltip(worship_hov, spirit_id)
            r = rects["worship"][worship_hov]
            anchor = r.bottom if below else r.top
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS, r.centerx, anchor, below=below,
            ))
        elif affinity_hov and rects.get("affinity"):
            r = rects["affinity"]
            anchor = r.bottom if below else r.top
            self.tooltip_registry.offer(TooltipDescriptor(
                _AFFINITY_TOOLTIP, _GUIDANCE_HOVER_REGIONS, r.centerx, anchor, below=below,
            ))

    def _log_event(self, event: dict):
        from client.scenes.event_logger import log_event
        etype = log_event(event, self.event_log, self.spirits,
                          self.app.my_spirit_id, self.faction_agendas_this_turn)
        # Record change for faction panel delta display
        self.change_tracker.process_event(
            event, len(self.event_log) - 1, self.factions, self.spirits)
        # Side effects that touch scene state
        if etype == "turn_start":
            self.change_tracker.snapshot_and_reset(self.factions, self.spirits)
            self.highlighted_log_index = None
            self._pending_ribbon_clear_on_next_agenda = True
        elif etype == "guide_contested":
            if self.app.my_spirit_id in event.get("spirits", []):
                self.preview_guidance = None
            if self.tutorial:
                self.tutorial.notify_game_event("guide_contested", event)
        elif etype == "war_erupted":
            if self.tutorial:
                self.tutorial.notify_game_event("war_erupted", event)
        elif etype == "faction_eliminated":
            if self.tutorial:
                self.tutorial.notify_game_event("faction_eliminated", event)

    @staticmethod
    def _format_faction_list(factions: list[str]) -> str:
        if not factions:
            return ""
        names = [faction_full_name(fid) for fid in factions]
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return f"{', '.join(names[:-1])}, and {names[-1]}"

    def _build_consolidated_agenda_line(self, play_info: dict, resolution_event: dict) -> str:
        faction_id = play_info["faction"]
        fname = faction_full_name(faction_id)
        agenda = play_info["agenda"].title()
        verb = "randomly play" if play_info["source"] == "random" else "play"
        guided_part = ""
        spirit_id = play_info.get("spirit")
        if spirit_id:
            spirit_name = self.spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            guided_part = f" guided by {spirit_name}"

        etype = resolution_event.get("type", "")
        if etype == "trade":
            gold = resolution_event.get("gold_gained", 0)
            co_traders = resolution_event.get("co_traders", [])
            if co_traders:
                regard = resolution_event.get("regard_gain", 0)
                others = self._format_faction_list(co_traders)
                return f"{fname} {verb} {agenda}{guided_part} for {gold} gold and +{regard} regard with {others}."
            return f"{fname} {verb} {agenda}{guided_part} for {gold} gold."

        if etype == "steal":
            gold = resolution_event.get("gold_gained", 0)
            penalty = resolution_event.get("regard_penalty", 1)
            neighbors = resolution_event.get("neighbors", [])
            if neighbors:
                others = self._format_faction_list(neighbors)
                return f"{fname} {verb} {agenda}{guided_part} for {gold} gold and -{penalty} regard with {others}."
            return f"{fname} {verb} {agenda}{guided_part} for {gold} gold."

        if etype == "expand":
            cost = resolution_event.get("cost", 0)
            return f"{fname} {verb} {agenda}{guided_part} and expand territory for {cost} gold."

        if etype == "expand_failed":
            gained = resolution_event.get("gold_gained", 0)
            return f"{fname} {verb} {agenda}{guided_part} but couldn't expand and gained {gained} gold."

        if etype == "change":
            mod = resolution_event.get("modifier", "?")
            return f"{fname} {verb} {agenda}{guided_part} and upgrade {mod}."

        return f"{fname} {verb} {agenda}{guided_part}."

    def _log_events_batch(self, events: list[dict]):
        resolution_to_agenda = {
            "trade": "trade",
            "steal": "steal",
            "expand": "expand",
            "expand_failed": "expand",
            "change": "change",
        }

        for event in events:
            etype = event.get("type", "")

            if etype in ("agenda_chosen", "agenda_random"):
                if self._pending_ribbon_clear_on_next_agenda:
                    self.faction_agendas_this_turn.clear()
                    self.faction_spoils_agendas_this_turn.clear()
                    self._pending_agenda_log_info.clear()
                    self._pending_ribbon_clear_on_next_agenda = False
                faction_id = event.get("faction", "")
                agenda = event.get("agenda", "")
                if faction_id and agenda:
                    self._pending_agenda_log_info[faction_id] = {
                        "faction": faction_id,
                        "agenda": agenda,
                        "source": "random" if etype == "agenda_random" else "chosen",
                        "spirit": event.get("spirit"),
                    }
                    self.faction_agendas_this_turn[faction_id] = agenda
                continue

            # Guided change choice echo event is an intermediate step; keep it out of log.
            if etype == "change" and event.get("is_guided_modifier"):
                continue

            if event.get("is_spoils"):
                spoils_agenda_type = None
                if etype in ("trade", "steal", "change"):
                    spoils_agenda_type = etype
                elif etype in ("expand", "expand_failed", "expand_spoils"):
                    spoils_agenda_type = "expand"
                if spoils_agenda_type:
                    faction_id = event.get("faction", "")
                    if faction_id:
                        self.faction_spoils_agendas_this_turn.setdefault(faction_id, []).append(
                            spoils_agenda_type)

            faction_id = event.get("faction", "")
            pending = self._pending_agenda_log_info.get(faction_id)
            expected_agenda = resolution_to_agenda.get(etype)
            if pending and expected_agenda and pending.get("agenda") == expected_agenda:
                line = self._build_consolidated_agenda_line(pending, event)
                self.event_log.append(line)
                log_index = len(self.event_log) - 1
                self.change_tracker.process_event(
                    event, log_index, self.factions, self.spirits)
                del self._pending_agenda_log_info[faction_id]
                continue

            self._log_event(event)

    def update(self, dt):
        self.animation.update(dt)
        if self._hex_error_timer > 0:
            self._hex_error_timer = max(0.0, self._hex_error_timer - dt)
        # Incrementally reveal hexes, gold, and wars as animations become active
        if self._display_hex_ownership is not None:
            self.orchestrator.apply_hex_reveals(self._display_hex_ownership)
        if self._display_factions is not None:
            self.orchestrator.apply_gold_deltas(self._display_factions)
            self.orchestrator.apply_change_modifier_deltas(self._display_factions)
        if self._display_wars is not None:
            self.orchestrator.apply_war_reveals(self._display_wars)
        # Drain queued PHASE_RESULT messages one at a time, waiting for each
        # animation batch to finish before processing the next.  Non-animating
        # payloads (war / scoring / cleanup with no agenda events) are consumed
        # immediately since is_all_done() stays True after they are processed.
        # Must run before try_show_deferred_phase_ui so snapshots can't overwrite
        # a PHASE_START that was deferred because the queue was non-empty.
        if not (self.tutorial and self.tutorial.is_blocking_animations()):
            while not self.orchestrator.has_animations_playing() and self._phase_result_queue and not self._pending_game_over:
                payload = self._phase_result_queue.pop(0)
                game_over_event = next(
                    (e for e in payload.get("events", []) if e.get("type") == "game_over"),
                    None,
                )
                self._process_phase_result(payload)
                if game_over_event:
                    self._pending_game_over = game_over_event
                    break
        # Tutorial: step tracking + animation-done notification.
        # Must run BEFORE try_show_deferred_phase_ui so that block_phase_ui can be
        # set by animations_done (step 10) before the next phase is shown.
        if self.tutorial:
            if self.tutorial.step_idx != self._tutorial_last_step:
                self._tutorial_last_step = self.tutorial.step_idx
                self._tutorial_anim_notified = False
                self._refire_tutorial_phase_events()
            block_ui = self.tutorial.is_blocking_phase_ui()
            anim_idle = (
                not self.orchestrator.has_animations_playing()
                and not self._phase_result_queue
                and (not self.orchestrator.deferred_phase_start or block_ui)
            )
            if anim_idle:
                if not self._tutorial_anim_notified:
                    self._tutorial_anim_notified = True
                    self.tutorial.notify_game_event(
                        "animations_done", {"phase": self.phase, "turn": self.turn})
            else:
                self._tutorial_anim_notified = False
        if not (self.tutorial and self.tutorial.is_blocking_phase_ui()):
            self.orchestrator.try_show_deferred_phase_ui(self)
        # Clear display state when all animations are done
        if self._display_hex_ownership is not None and not self.orchestrator.has_animations_playing():
            self._clear_display_state()
        # Once game_over animations have settled, show final scores in-place.
        if not self.orchestrator.has_animations_playing() and self._pending_game_over:
            self.game_over_data = self._pending_game_over
            self._pending_game_over = None
            self.game_over = True

    def _register_ui_rects_for_tooltips(self):
        """Populate the popup_manager rect registry for tooltip placement scoring."""
        rects: list[tuple[pygame.Rect, int]] = []

        # TEXT rects (high penalty) — areas with important readable info
        # HUD bar
        rects.append((pygame.Rect(0, 0, SCREEN_WIDTH, 40), _WEIGHT_TEXT))
        # Faction overview strip
        rects.append((pygame.Rect(0, 42, SCREEN_WIDTH, 55), _WEIGHT_TEXT))
        # Event log (dynamic height)
        _ev_cur_h = _EVENT_LOG_H_ENLARGED if self.event_log_enlarged else _EVENT_LOG_H
        _ev_fp_h = _FACTION_PANEL_MAX_H + _EVENT_LOG_H - _ev_cur_h
        _ev_log_y = 102 + _ev_fp_h + 4 + _SPIRIT_PANEL_MAX_H + 4
        rects.append((pygame.Rect(_FACTION_PANEL_X, _ev_log_y, _PANEL_W, _ev_cur_h), _WEIGHT_TEXT))
        # Faction panel
        fp = self.ui_renderer.faction_panel_rect
        if fp:
            rects.append((fp, _WEIGHT_TEXT))
        # Spirit panel
        sp = self._spirit_panel_rects.get("panel")
        if sp:
            rects.append((sp, _WEIGHT_TEXT))
        # Pinned popup rects
        for popup in self.popup_manager._stack:
            rects.append((popup.rect, _WEIGHT_TEXT))

        # NON_TEXT rects (low penalty) — buttons and cards
        for btn in self.action_buttons + self.faction_buttons + self.idol_buttons:
            rects.append((btn.rect, _WEIGHT_NON_TEXT))
        if self.submit_button:
            rects.append((self.submit_button.rect, _WEIGHT_NON_TEXT))
        # Card rects (if cards are showing)
        if self.agenda_hand:
            for cr in self._calc_left_choice_card_rects(len(self.agenda_hand)):
                rects.append((cr, _WEIGHT_NON_TEXT))
        if self.change_cards:
            for cr in self._calc_left_choice_card_rects(len(self.change_cards)):
                rects.append((cr, _WEIGHT_NON_TEXT))
        if self.spoils_entries:
            sidx = max(0, min(self.spoils_display_index, len(self.spoils_entries) - 1))
            entry = self.spoils_entries[sidx]
            for cr in self._calc_left_choice_card_rects(len(entry.cards)):
                rects.append((cr, _WEIGHT_NON_TEXT))
        if self.spoils_change_entries:
            sidx = max(0, min(self.spoils_display_index, len(self.spoils_change_entries) - 1))
            entry = self.spoils_change_entries[sidx]
            for cr in self._calc_left_choice_card_rects(len(entry.cards)):
                rects.append((cr, _WEIGHT_NON_TEXT))

        set_ui_rects(rects)

    def render(self, screen: pygame.Surface):
        screen.fill(theme.BG_SCREEN)

        # Parse idol data for rendering
        render_idols = []
        for idol_data in self.all_idols:
            if isinstance(idol_data, dict):
                render_idols.append(type('Idol', (), {
                    'type': IdolType(idol_data['type']),
                    'position': type('Pos', (), {
                        'q': idol_data['position']['q'],
                        'r': idol_data['position']['r'],
                    })(),
                    'owner_spirit': idol_data.get('owner_spirit'),
                })())
        self._render_idols_cache = render_idols

        # Parse wars for rendering (use display state if available)
        render_wars = []
        for w in self.display_wars:
            if isinstance(w, dict):
                war_obj = type('War', (), {
                    'faction_a': w.get('faction_a', ''),
                    'faction_b': w.get('faction_b', ''),
                    'is_ripe': w.get('is_ripe', False),
                    'battleground': None,
                })()
                if w.get("battleground"):
                    bg = w["battleground"]
                    war_obj.battleground = (
                        type('H', (), {'q': bg[0]['q'], 'r': bg[0]['r']})(),
                        type('H', (), {'q': bg[1]['q'], 'r': bg[1]['r']})(),
                    )
                render_wars.append(war_obj)

        # Draw hex grid (use display state if available)
        hex_own = self.display_hex_ownership
        highlight = None

        # Battleground choice: highlight selectable hexes (excluding the selected pair)
        if self.phase == SubPhase.BATTLEGROUND_CHOICE and self.battleground_selectable_hexes:
            highlight = self.battleground_selectable_hexes - self.battleground_selected_hexes
        # Expand choice: highlight reachable neutral hexes
        elif self.phase == SubPhase.EXPAND_CHOICE and self.expand_choice_hexes:
            highlight = self.expand_choice_hexes

        # Compute preview idol (post-confirm or pre-confirm)
        render_preview_idol = self.preview_idol
        if not render_preview_idol and self.selected_idol_type and self.selected_hex:
            render_preview_idol = (self.selected_idol_type,
                                   self.selected_hex[0], self.selected_hex[1])

        # Build spirit_id -> player_index mapping (sorted for stability)
        spirit_index_map = {
            sid: i for i, sid in enumerate(sorted(self.spirits.keys()))
        }

        # Build faction_id -> spirit_index for guidance and worship indicators
        faction_spirit_index = {}
        faction_worship = {}
        for faction_id, fdata in self.factions.items():
            fdict = fdata if isinstance(fdata, dict) else {}
            guiding = fdict.get("guiding_spirit")
            if guiding and guiding in spirit_index_map:
                faction_spirit_index[faction_id] = spirit_index_map[guiding]
            worship = fdict.get("worship_spirit")
            if worship and worship in spirit_index_map:
                faction_worship[faction_id] = spirit_index_map[worship]

        self.hex_renderer.draw_hex_grid(
            screen, hex_own,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            idols=render_idols, wars=render_wars,
            selected_hex=self.selected_hex,
            selected_hexes=self.battleground_selected_hexes or None,
            highlight_hexes=highlight,
            spirit_index_map=spirit_index_map,
            preview_idol=render_preview_idol,
            faction_spirit_index=faction_spirit_index,
            faction_worship=faction_worship,
            highlight_spirit_id=self.spirit_panel_spirit_id,
        )

        # Tutorial war-arrow glow (drawn on top of hex grid, under UI panels)
        if self.tutorial and self.tutorial.highlight_war_arrows and render_wars:
            pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 3.0)
            self.hex_renderer.draw_war_glow_arrows(
                screen, render_wars, hex_own,
                self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT, pulse=pulse)

        # Draw world-space effect animations (border text + arrows)
        self.orchestrator.render_effect_animations(screen, screen_space_only=False, small_font=self.small_font)

        # Draw HUD
        self.ui_renderer.draw_hud(screen, self.phase, self.turn,
                                   self.spirits, self.app.my_spirit_id)

        # Compute preview guidance dict
        preview_guid_dict = None
        preview_fid = self.preview_guidance or self.selected_faction
        if preview_fid:
            my_name = self.spirits.get(self.app.my_spirit_id, {}).get("name", "?")
            preview_guid_dict = {preview_fid: my_name}

        # Draw faction overview strip — always use live factions so worship/pool
        # stay current even when _display_factions is stale during AI-only games.
        disp_factions = self.factions
        animated_agenda_factions = self.animation.get_persistent_agenda_factions()
        self.agenda_label_rects, self.pool_icon_rects, self.ribbon_war_rects, self.ribbon_worship_rects = self.ui_renderer.draw_faction_overview(
            screen, disp_factions, self.faction_agendas_this_turn,
            wars=render_wars,
            faction_spoils_agendas=self.faction_spoils_agendas_this_turn,
            spirits=self.spirits,
            preview_guidance=preview_guid_dict,
            animated_agenda_factions=animated_agenda_factions,
            faction_order=self.faction_order,
        )
        if self.faction_order:
            cell_w = SCREEN_WIDTH // len(self.faction_order)
            self.ribbon_faction_rects = {
                fid: pygame.Rect(i * cell_w, 42, cell_w, 55)
                for i, fid in enumerate(self.faction_order)
            }

        # Draw persistent agenda slide animations (on top of overview strip)
        self.orchestrator.render_persistent_agenda_animations(screen)

        # Draw screen-space effect animations (gold text overlays)
        self.orchestrator.render_effect_animations(screen, screen_space_only=True, small_font=self.small_font)

        # Right column layout (dynamic: event log may be enlarged, shrinking faction panel)
        _cur_event_log_h = _EVENT_LOG_H_ENLARGED if self.event_log_enlarged else _EVENT_LOG_H
        _cur_faction_panel_h = _FACTION_PANEL_MAX_H + _EVENT_LOG_H - _cur_event_log_h
        _spirit_panel_y = 102 + _cur_faction_panel_h + 4
        _event_log_y = _spirit_panel_y + _SPIRIT_PANEL_MAX_H + 4

        # Draw spirit panel OR faction panel (top of right column)
        self.panel_change_rects = []
        if self.spirit_panel_spirit_id:
            # Spirit panel (top of right column)
            spirit = self.spirits.get(self.spirit_panel_spirit_id, {})
            fills = self._get_influence_fills(self.spirit_panel_spirit_id)
            self._spirit_panel_rects = self.ui_renderer.draw_spirit_panel(
                screen, spirit, self.factions, self.all_idols,
                self.hex_ownership, _FACTION_PANEL_X, 102, _PANEL_W,
                my_spirit_id=self.spirit_panel_spirit_id,
                circle_fills=fills,
                spirit_index_map=spirit_index_map,
                max_height=_FACTION_PANEL_MAX_H,
            )
            # Clear faction panel rects
            self.ui_renderer.faction_panel_rect = None
            self.ui_renderer.panel_guided_rect = None
            self.ui_renderer.panel_worship_rect = None
            self.ui_renderer.panel_war_rect = None
        else:
            # Faction panel (top of right column)
            pf = self.panel_faction
            if not pf:
                my_spirit = self.spirits.get(self.app.my_spirit_id, {})
                pf = my_spirit.get("guided_faction")
            real_faction_data = self.factions.get(pf) if pf else None
            if pf and real_faction_data:
                self.ui_renderer.draw_faction_panel(
                    screen, real_faction_data,
                    _FACTION_PANEL_X, 102, _PANEL_W,
                    spirits=self.spirits,
                    preview_guidance=preview_guid_dict,
                    change_tracker=self.change_tracker,
                    panel_faction_id=pf,
                    highlight_log_idx=self.highlighted_log_index,
                    change_rects=self.panel_change_rects,
                    wars=render_wars,
                    all_factions=self.factions,
                    faction_order=self.faction_order,
                    scroll_offset=self.faction_panel_scroll_offset,
                    max_height=_cur_faction_panel_h,
                )
            else:
                self.ui_renderer.faction_panel_rect = None
                self.ui_renderer.panel_guided_rect = None
                self.ui_renderer.panel_worship_rect = None
                self.ui_renderer.panel_war_rect = None
            # Clear spirit panel rects
            self._spirit_panel_rects = {}

        # Draw persistent spirit stats panel (middle of right column)
        my_spirit = self.spirits.get(self.app.my_spirit_id, {})
        if my_spirit:
            fills = self._get_influence_fills(self.app.my_spirit_id)
            self._persistent_spirit_panel_rects = self.ui_renderer.draw_spirit_panel(
                screen, my_spirit, self.factions, self.all_idols,
                self.hex_ownership, _FACTION_PANEL_X, _spirit_panel_y, _PANEL_W,
                my_spirit_id=self.app.my_spirit_id,
                circle_fills=fills,
                spirit_index_map=spirit_index_map,
                max_height=_SPIRIT_PANEL_MAX_H,
            )

        # Draw event log (bottom of right column); auto-widen when enlarged
        if self.event_log_enlarged and self.event_log:
            _sm_font = self.ui_renderer.small_font
            _max_msg_w = max((_sm_font.size(t)[0] for t in self.event_log), default=0)
            _elog_w = min(SCREEN_WIDTH - 4, _max_msg_w + 32)
            _elog_x = SCREEN_WIDTH - _elog_w - 2
        else:
            _elog_w = _PANEL_W
            _elog_x = _FACTION_PANEL_X
        self._event_log_render_rect = pygame.Rect(_elog_x, _event_log_y, _elog_w, _cur_event_log_h)
        self.ui_renderer.draw_event_log(
            screen, self.event_log,
            _elog_x, _event_log_y, _elog_w, _cur_event_log_h,
            scroll_offset=self.event_log_scroll_offset,
            highlight_log_idx=self.highlighted_log_index,
            h_scroll_offset=self.event_log_h_scroll_offset,
            enlarged=self.event_log_enlarged,
        )

        # Draw waiting indicator near confirm button area, only after player has submitted
        if (self.has_submitted or self.spectator_mode) and self.waiting_for and not self.orchestrator.deferred_phase_start:
            self.ui_renderer.draw_waiting_overlay(
                screen, self.waiting_for, self.spirits,
                x=20, y=SCREEN_HEIGHT - 90,
            )

        # Reset tooltip registry for this frame (before phase-specific UI
        # which may offer tooltips, and before the main tooltip registration block)
        self.tooltip_registry.clear()

        # Phase-specific UI
        if self.phase == Phase.VAGRANT_PHASE.value:
            self._render_vagrant_ui(screen)
        elif self.phase == Phase.AGENDA_PHASE.value:
            if not (self.tutorial and self.tutorial.hide_phase_ui):
                self._render_agenda_ui(screen)
        elif self.phase == SubPhase.CHANGE_CHOICE:
            self._render_change_ui(screen)
        elif self.phase == SubPhase.EJECTION_CHOICE:
            self._render_ejection_ui(screen)
        elif self.phase == SubPhase.SPOILS_CHOICE:
            self._render_spoils_ui(screen)
        elif self.phase == SubPhase.SPOILS_CHANGE_CHOICE:
            self._render_spoils_change_ui(screen)
        elif self.phase == SubPhase.BATTLEGROUND_CHOICE:
            self._render_battleground_ui(screen)
        elif self.phase == SubPhase.EXPAND_CHOICE:
            self._render_expand_choice_ui(screen)

        # Register UI rects for tooltip placement scoring
        self._register_ui_rects_for_tooltips()

        # Rebuilt only while idol hover tooltip is actively rendered.
        self.idol_tooltip_spirit_rects = []

        # Agenda hover tooltips
        if self.hovered_card_tooltip and self.hovered_card_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self.hovered_card_tooltip, _GUIDANCE_HOVER_REGIONS,
                self.hovered_card_rect.centerx, self.hovered_card_rect.top,
            ))
        elif self.hovered_agenda_label_fid and self.hovered_agenda_label_rect:
            fmod = self._get_faction_modifiers(self.hovered_agenda_label_fid)
            agenda_str = self.hovered_agenda_label_type or ""
            if agenda_str:
                tooltip = build_agenda_tooltip(
                    agenda_str, fmod, is_spoils=self.hovered_agenda_label_is_spoils)
                self.tooltip_registry.offer(TooltipDescriptor(
                    tooltip, _GUIDANCE_HOVER_REGIONS,
                    self.hovered_agenda_label_rect.centerx,
                    self.hovered_agenda_label_rect.bottom, below=True,
                ))
        elif self.hovered_anim_tooltip and self.hovered_anim_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self.hovered_anim_tooltip, _GUIDANCE_HOVER_REGIONS,
                self.hovered_anim_rect.centerx,
                self.hovered_anim_rect.bottom, below=True,
            ))

        # Idol hover tooltip (custom renderer for clickable spirit names;
        # also offer text to registry for right-click-to-pin)
        if self.hovered_idol:
            if not self.popup_manager.has_popups():
                self._render_idol_tooltip(screen)
            tooltip_text, _ = self._build_idol_tooltip_text(self.hovered_idol)
            mx, my = pygame.mouse.get_pos()
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip_text, _GUIDANCE_HOVER_REGIONS, mx, my,
            ))

        # Faction panel guided/worship hover tooltips
        if self.hovered_panel_guided:
            tooltip = self._build_guidance_panel_tooltip(
                self.ui_renderer.panel_guided_spirit_id)
            r = self.ui_renderer.panel_guided_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))
        elif self.hovered_panel_worship and self.ui_renderer.panel_faction_id:
            tooltip = self._build_worship_panel_tooltip(
                self.ui_renderer.panel_faction_id)
            r = self.ui_renderer.panel_worship_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip, _GUIDANCE_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))
        elif self.hovered_panel_war and self.ui_renderer.panel_war_rect:
            r = self.ui_renderer.panel_war_rect
            self.tooltip_registry.offer(TooltipDescriptor(
                _WAR_TOOLTIP, _WAR_HOVER_REGIONS,
                r.centerx, r.bottom, below=True,
            ))

        # Spirit panel hover tooltips (right pop-out)
        if self.spirit_panel_spirit_id:
            self._offer_spirit_panel_tooltip(
                self.spirit_panel_spirit_id, self._spirit_panel_rects,
                self.hovered_spirit_panel_guidance, self.hovered_spirit_panel_influence,
                self.hovered_spirit_panel_worship, below=True,
                affinity_hov=self.hovered_spirit_panel_affinity,
            )
        # Persistent spirit panel hover tooltips (bottom-left, always visible)
        self._offer_spirit_panel_tooltip(
            self.app.my_spirit_id, self._persistent_spirit_panel_rects,
            self.hovered_persistent_spirit_guidance, self.hovered_persistent_spirit_influence,
            self.hovered_persistent_spirit_worship, below=False,
            affinity_hov=self.hovered_persistent_spirit_affinity,
        )

        # Agenda pool icon hover tooltip
        if self.hovered_pool_faction:
            pool_rect = self.pool_icon_rects.get(self.hovered_pool_faction)
            if pool_rect:
                fdata = self.display_factions.get(self.hovered_pool_faction, {})
                pool_types = fdata.get("agenda_pool", []) if isinstance(fdata, dict) else []
                change_modifiers = fdata.get("change_modifiers", {}) if isinstance(fdata, dict) else {}
                if pool_types:
                    counts: dict[str, int] = {}
                    for pt in pool_types:
                        counts[pt] = counts.get(pt, 0) + 1
                    fname = faction_full_name(self.hovered_pool_faction)
                    lines = [f"{fname} Agenda Pool"]
                    for at_str in ["steal", "trade", "expand", "change"]:
                        c = counts.get(at_str, 0)
                        mod = change_modifiers.get(at_str, 0)
                        mod_str = "+" * mod if mod > 0 else ""
                        suffix = f" {mod_str}" if mod_str else ""
                        if c == 0:
                            lines.append(f"  {at_str.title()}{suffix}: none")
                        elif c == 1:
                            lines.append(f"  {at_str.title()}{suffix}")
                        else:
                            lines.append(f"  {c}x {at_str.title()}{suffix}")
                    tooltip_text = "\n".join(lines)
                    self.tooltip_registry.offer(TooltipDescriptor(
                        tooltip_text, [],
                        pool_rect.centerx, pool_rect.bottom, below=True,
                    ))

        # Guided hex sigil hover tooltip
        if self.hovered_guided_hex_spirit:
            name = self.spirits.get(self.hovered_guided_hex_spirit, {}).get("name", "?")
            mx, my = pygame.mouse.get_pos()
            self.tooltip_registry.offer(TooltipDescriptor(
                f"Guided by {name}", [], mx, my,
            ))

        # Ribbon war indicator hover tooltip
        if self.hovered_ribbon_war_fid:
            war_rect = self.ribbon_war_rects.get(self.hovered_ribbon_war_fid)
            if war_rect:
                tooltip_text = self._build_ribbon_war_tooltip(self.hovered_ribbon_war_fid)
                self.tooltip_registry.offer(TooltipDescriptor(
                    tooltip_text, _RIBBON_WAR_HOVER_REGIONS,
                    war_rect.centerx, war_rect.bottom, below=True,
                ))

        # Ribbon worship sigil hover tooltip
        if self.hovered_ribbon_worship_fid:
            fid = self.hovered_ribbon_worship_fid
            fdata = self.factions.get(fid, {})
            worship_id = fdata.get("worship_spirit") if isinstance(fdata, dict) else None
            sigil_rect = self.ribbon_worship_rects.get(fid)
            if worship_id and sigil_rect:
                spirit_name = self.spirits.get(worship_id, {}).get("name", worship_id[:6])
                faction_name = faction_full_name(fid)
                worship_sub_tooltip = self._build_spirit_worship_tooltip(fid, worship_id)
                hover_regions = [HoverRegion("Worshipping", worship_sub_tooltip, sub_regions=[])]
                self.tooltip_registry.offer(TooltipDescriptor(
                    f"{faction_name} are Worshipping {spirit_name}",
                    hover_regions,
                    sigil_rect.centerx, sigil_rect.bottom, below=True,
                ))

        # Fading error message (hex click errors, etc.)
        if self._hex_error_timer > 0 and self._hex_error_message:
            _ERR_FADE_DURATION = 0.5
            alpha = min(1.0, self._hex_error_timer / _ERR_FADE_DURATION) * 255
            surf = self.small_font.render(self._hex_error_message, True, (255, 90, 70))
            surf.set_alpha(int(alpha))
            screen.blit(surf, surf.get_rect(center=(SCREEN_WIDTH // 2, 108)))

        # Final scores panel (drawn after everything else so it's always visible)
        if self.game_over:
            self._render_game_over_panel(screen)

        # Tutorial overlay (drawn after game-over panel, before tooltips)
        if self.tutorial:
            tut_rects = {
                "faction_info": pygame.Rect(_FACTION_PANEL_X, 102, _PANEL_W, _cur_faction_panel_h),
                "spirit_panel": pygame.Rect(
                    _FACTION_PANEL_X, _spirit_panel_y, _PANEL_W, _SPIRIT_PANEL_MAX_H),
                "event_log": pygame.Rect(
                    _FACTION_PANEL_X, _event_log_y, _PANEL_W, _cur_event_log_h),
            }
            for fid, r in self.ribbon_faction_rects.items():
                tut_rects[f"ribbon_{fid}"] = r
            for btn, fid in zip(self.faction_buttons, self.faction_button_ids):
                tut_rects[f"guidance_btn_{fid}"] = btn.rect
            if self.agenda_hand:
                card_rects = self._calc_left_choice_card_rects(len(self.agenda_hand))
                tut_rects["agenda_cards_area"] = pygame.Rect(
                    card_rects[0].x, card_rects[0].y,
                    card_rects[0].w, card_rects[-1].bottom - card_rects[0].y,
                )
            for fid, r in self.ribbon_war_rects.items():
                tut_rects[f"ribbon_war_{fid}"] = r
            if self.ui_renderer.panel_war_rect:
                tut_rects["panel_war"] = self.ui_renderer.panel_war_rect
            self.tutorial.exposed_rects = tut_rects
            self.tutorial.render(screen, self.font, self.small_font)

        # Render the single active tooltip (suppressed when popups are open)
        self.tooltip_registry.render(screen, self.small_font, self.popup_manager)

        # Pinned popups (drawn on top of everything)
        self.popup_manager.render(screen, self.small_font)

        # In-game menu button and dropdown (always on top)
        self._render_ingame_menu(screen)

    def _render_game_over_panel(self, screen: pygame.Surface):
        """Draw the final scores panel on the left side of the screen."""
        if not self.game_over_data:
            return
        if self._game_over_bold_font is None:
            self._game_over_bold_font = get_font(16, bold=True)
        if self._game_over_win_font is None:
            self._game_over_win_font = get_font(20, bold=True)

        winners = self.game_over_data.get("winners", [])
        scores = self.game_over_data.get("scores", {})
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        n = len(sorted_scores)
        row_h = 22
        panel_w = 210
        panel_h = 30 + n * row_h + (30 if winners else 0) + 22
        panel_x = 10
        # Center vertically in the play area below the faction ribbon (y=97)
        play_top = 97
        play_bot = SCREEN_HEIGHT - 20
        panel_y = max(play_top + 8, (play_top + play_bot - panel_h) // 2)

        overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        overlay.fill((20, 20, 30, 220))
        screen.blit(overlay, (panel_x, panel_y))
        pygame.draw.rect(screen, (130, 130, 170),
                         pygame.Rect(panel_x, panel_y, panel_w, panel_h), 1, border_radius=4)

        header = self.font.render("Final Scores", True, theme.TEXT_BRIGHT)
        screen.blit(header, (panel_x + 10, panel_y + 8))

        y = panel_y + 30
        for spirit_id, vp in sorted_scores:
            spirit = self.spirits.get(spirit_id, {})
            name = spirit.get("name", spirit_id[:8])
            is_winner = spirit_id in winners
            row_font = self._game_over_bold_font if is_winner else self.font
            color = (255, 220, 130) if is_winner else (190, 190, 210)
            text = row_font.render(f"{name}: {vp} VP", True, color)
            screen.blit(text, (panel_x + 10, y))
            y += row_h

        if winners:
            winner_id = winners[0]
            winner_name = self.spirits.get(winner_id, {}).get("name", winner_id[:8])
            win_text = self._game_over_win_font.render(f"{winner_name} wins!", True, (255, 220, 120))
            screen.blit(win_text, (panel_x + 10, y + 4))
            y += 30

        hint = self.small_font.render("Esc → menu", True, (120, 120, 145))
        screen.blit(hint, (panel_x + 10, panel_y + panel_h - 17))

    def _render_ingame_menu(self, screen: pygame.Surface):
        """Draw the in-game menu button and dropdown overlay."""
        btn_w, btn_h = 70, 26
        btn_x = SCREEN_WIDTH - btn_w - 6
        btn_y = 7
        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        self._ingame_menu_btn_rect = btn_rect

        # Button background
        btn_bg = (55, 55, 75) if not self._ingame_menu_open else (75, 75, 100)
        pygame.draw.rect(screen, btn_bg, btn_rect, border_radius=4)
        pygame.draw.rect(screen, (100, 100, 130), btn_rect, 1, border_radius=4)
        label = self.small_font.render("\u2630 Menu", True, (190, 190, 215))
        screen.blit(label, (btn_rect.x + (btn_w - label.get_width()) // 2,
                             btn_rect.y + (btn_h - label.get_height()) // 2))

        # Dropdown items
        if self._ingame_menu_open:
            items = [("settings", "Settings"), ("exit", "Exit to Main Menu")]
            item_w = 160
            item_h = 28
            drop_x = SCREEN_WIDTH - item_w - 6
            drop_y = btn_rect.bottom + 2
            drop_rect = pygame.Rect(drop_x, drop_y, item_w, len(items) * item_h + 4)
            pygame.draw.rect(screen, (30, 30, 45), drop_rect, border_radius=4)
            pygame.draw.rect(screen, (90, 90, 120), drop_rect, 1, border_radius=4)
            mx, my = pygame.mouse.get_pos()
            self._ingame_menu_item_rects = []
            for i, (key, text) in enumerate(items):
                ir = pygame.Rect(drop_x + 2, drop_y + 2 + i * item_h, item_w - 4, item_h)
                self._ingame_menu_item_rects.append((key, ir))
                if ir.collidepoint(mx, my):
                    pygame.draw.rect(screen, (60, 60, 85), ir, border_radius=3)
                surf = self.small_font.render(text, True, (200, 200, 220))
                screen.blit(surf, (ir.x + 10, ir.y + (item_h - surf.get_height()) // 2))

        # Confirm exit dialog
        if self._ingame_menu_confirm_exit:
            dlg_w, dlg_h = 280, 100
            dlg_x = SCREEN_WIDTH // 2 - dlg_w // 2
            dlg_y = SCREEN_HEIGHT // 2 - dlg_h // 2
            dlg_rect = pygame.Rect(dlg_x, dlg_y, dlg_w, dlg_h)
            pygame.draw.rect(screen, (20, 20, 35), dlg_rect, border_radius=6)
            pygame.draw.rect(screen, (130, 110, 60), dlg_rect, 2, border_radius=6)
            title_surf = self.font.render("Exit to main menu?", True, (220, 200, 120))
            screen.blit(title_surf, (dlg_x + (dlg_w - title_surf.get_width()) // 2, dlg_y + 14))
            btn_y2 = dlg_y + 56
            yes_rect = pygame.Rect(dlg_x + 30, btn_y2, 90, 30)
            no_rect = pygame.Rect(dlg_x + dlg_w - 120, btn_y2, 90, 30)
            pygame.draw.rect(screen, (100, 50, 50), yes_rect, border_radius=4)
            pygame.draw.rect(screen, (50, 80, 50), no_rect, border_radius=4)
            yes_surf = self.font.render("Yes", True, (230, 180, 180))
            no_surf = self.font.render("No", True, (180, 220, 180))
            screen.blit(yes_surf, (yes_rect.x + (yes_rect.w - yes_surf.get_width()) // 2,
                                   yes_rect.y + (yes_rect.h - yes_surf.get_height()) // 2))
            screen.blit(no_surf, (no_rect.x + (no_rect.w - no_surf.get_width()) // 2,
                                  no_rect.y + (no_rect.h - no_surf.get_height()) // 2))
            self._ingame_confirm_yes_rect = yes_rect
            self._ingame_confirm_no_rect = no_rect

    def _build_idol_tooltip_text(self, idol):
        idol_type = idol.type
        owner_id = idol.owner_spirit
        owner_name = (self.spirits.get(owner_id, {}).get("name", owner_id[:6])
                      if owner_id else "Unknown")
        clickable_spirits: dict[str, str] = {}
        if owner_id:
            clickable_spirits[owner_id] = owner_name
        type_name = idol_type.value.title()

        # Determine territory ownership
        q, r = idol.position.q, idol.position.r
        faction_id = self.hex_ownership.get((q, r))
        faction_name = faction_full_name(faction_id) if faction_id else None

        if faction_id:
            # Idol is in a faction's territory
            worship_id = None
            fdata = self.factions.get(faction_id)
            if isinstance(fdata, dict):
                worship_id = fdata.get("worship_spirit")
            worship_name = (self.spirits.get(worship_id, {}).get("name", worship_id[:6])
                            if worship_id else None)
            if worship_id and worship_name:
                clickable_spirits[worship_id] = worship_name
            header = (f"{type_name} Idol placed by {owner_name}, "
                      f"currently in the custody of {faction_name}")
            if idol_type == IdolType.BATTLE:
                if worship_name:
                    vp_line = (f"When {faction_name} win a War, the Spirit they "
                               f"Worship - {worship_name} - gains {BATTLE_IDOL_VP} VP "
                               f"at the end of the turn.")
                else:
                    vp_line = (f"When {faction_name} win a War and Worship a Spirit, "
                               f"that Spirit gains {BATTLE_IDOL_VP} VP at the end of the turn.")
            elif idol_type == IdolType.AFFLUENCE:
                if worship_name:
                    vp_line = (f"When {faction_name} gain gold, the Spirit they "
                               f"Worship - {worship_name} - gains {AFFLUENCE_IDOL_VP} VP "
                               f"at the end of the turn.")
                else:
                    vp_line = (f"When {faction_name} gain gold and Worship a Spirit, "
                               f"that Spirit gains {AFFLUENCE_IDOL_VP} VP at the end of the turn.")
            else:  # SPREAD
                if worship_name:
                    vp_line = (f"When {faction_name} gain a Territory, the Spirit they "
                               f"Worship - {worship_name} - gains {SPREAD_IDOL_VP} VP "
                               f"at the end of the turn.")
                else:
                    vp_line = (f"When {faction_name} gain a Territory and Worship a Spirit, "
                               f"that Spirit gains {SPREAD_IDOL_VP} VP at the end of the turn.")
        else:
            # Idol is on neutral ground
            header = (f"{type_name} Idol placed by {owner_name}, "
                      f"currently on neutral grounds")
            if idol_type == IdolType.BATTLE:
                vp_line = (f"After a Faction claims the Territory this Idol is on, "
                           f"it will grant the Spirit they Worship {BATTLE_IDOL_VP} VP "
                           f"for each War the Faction wins.")
            elif idol_type == IdolType.AFFLUENCE:
                vp_line = (f"After a Faction claims the Territory this Idol is on, "
                           f"it will grant the Spirit they Worship {AFFLUENCE_IDOL_VP} VP "
                           f"for each gold the Faction gains.")
            else:  # SPREAD
                vp_line = (f"After a Faction claims the Territory this Idol is on, "
                           f"it will grant the Spirit they Worship {SPREAD_IDOL_VP} VP "
                           f"for each Territory the Faction gains.")

        return f"{header}\n{vp_line}", clickable_spirits

    def _render_idol_tooltip(self, screen):
        tooltip_text, clickable_spirits = self._build_idol_tooltip_text(self.hovered_idol)
        mx, my = pygame.mouse.get_pos()
        max_width = 350
        lines = _wrap_text(tooltip_text, self.small_font, max_width)
        line_h = self.small_font.get_linesize()
        rendered_widths = [self.small_font.size(line)[0] for line in lines]
        content_w = max(rendered_widths) if rendered_widths else 0
        tip_w = content_w + 16
        tip_h = len(lines) * line_h + 12
        tip_x = mx - tip_w // 2
        if tip_x < 4:
            tip_x = 4
        if tip_x + tip_w > SCREEN_WIDTH - 4:
            tip_x = SCREEN_WIDTH - 4 - tip_w
        tip_y = my - tip_h - 4
        tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
        pygame.draw.rect(screen, theme.BG_TOOLTIP, tip_rect, border_radius=4)
        pygame.draw.rect(screen, theme.BORDER_TOOLTIP, tip_rect, 1, border_radius=4)

        keyword_names = list(dict.fromkeys(clickable_spirits.values()))
        name_rects = render_rich_lines(
            screen, self.small_font, lines, tip_x + 8, tip_y + 6,
            keywords=keyword_names,
            hovered_keyword=None,
            normal_color=theme.TEXT_TOOLTIP,
            keyword_color=(140, 220, 255),
            hovered_keyword_color=(140, 220, 255),
        )

        self.idol_tooltip_spirit_rects = []
        for sid, name in clickable_spirits.items():
            for rect in name_rects.get(name, []):
                self.idol_tooltip_spirit_rects.append((sid, rect))

    _GUIDANCE_TITLE_TOOLTIP = (
        "Select a Faction to Guide. If you are not the only Spirit "
        "attempting to Guide that Faction this turn, both of you will "
        "fail and choose again next turn.\n\n"
        "If successful, for the next 3 turns you will choose among "
        "several options whenever that Faction would ordinarily draw a "
        "random Agenda card or Change modifier: 3 additional choices "
        "this turn, 2 additional choices next turn and 1 additional "
        "choice the turn after that. You will be ejected after this "
        "last turn of Guidance, but you will leave behind a lasting "
        "effect: replacing one Agenda card in its Agenda pool with one of your choice.\n\n"
        "Additionally, every time you begin and end Guidance of a "
        "Faction, you will attempt to become Worshipped by that Faction. "
        "If that Faction is not Worshipping any Spirit, you automatically "
        "succeed. If they are Worshipping another Spirit, you become "
        "their new object of Worship if you have as many or more Idols "
        "in the Faction's Territories as the Spirit they currently Worship.\n\n"
        "You cannot begin Guiding a Faction that Worships you."
    )

    _IDOL_TITLE_TOOLTIP = (
        "Choose a neutral Territory and Idol type to place. When inside "
        "a Faction's Territory, the Spirit Worshipped by that Faction "
        "gains Victory Points at the end of every turn if that Faction "
        "succeeds at winning Wars, gaining gold or expanding their "
        "Territory, depending on which Idols are present.\n\n"
        "Idols in neutral Territory beckon all neighboring Factions: "
        "if they Expand, Territories with Idols in them are prioritized "
        "over ones without Idols."
    )

    def _render_vagrant_ui(self, screen):
        # Draw "Guidance" title
        if self.guidance_title_rect and self.faction_buttons:
            title_surf = self.font.render("Guidance", True, theme.TEXT_HIGHLIGHT)
            tx = self.guidance_title_rect.centerx - title_surf.get_width() // 2
            ty = self.guidance_title_rect.y
            screen.blit(title_surf, (tx, ty))
            draw_dotted_underline(screen, tx, ty + title_surf.get_height(),
                                  title_surf.get_width())

        # Draw "Idol placement" title
        if self.idol_title_rect and self.idol_buttons:
            title_surf = self.font.render("Idol placement", True, theme.TEXT_HIGHLIGHT)
            tx = self.idol_title_rect.centerx - title_surf.get_width() // 2
            ty = self.idol_title_rect.y
            screen.blit(title_surf, (tx, ty))
            draw_dotted_underline(screen, tx, ty + title_surf.get_height(),
                                  title_surf.get_width())

        # Draw faction buttons (left) with selection highlight
        for btn in self.faction_buttons:
            if self.selected_faction and btn.text == faction_full_name(self.selected_faction):
                pygame.draw.rect(screen, (255, 255, 255), btn.rect.inflate(4, 4), 2, border_radius=8)
            btn.draw(screen, self.font)

        # Draw idol buttons (right) with selection highlight
        for btn in self.idol_buttons:
            if self.selected_idol_type and btn.text.lower() == self.selected_idol_type:
                pygame.draw.rect(screen, (255, 255, 255), btn.rect.inflate(4, 4), 2, border_radius=8)
            btn.draw(screen, self.font)

        # Register button tooltips with the tooltip registry
        for btn in self.faction_buttons:
            if btn.tooltip and btn.hovered and (btn.tooltip_always or not btn.enabled):
                self.tooltip_registry.offer(TooltipDescriptor(
                    btn.tooltip, _GUIDANCE_HOVER_REGIONS,
                    btn.rect.centerx, btn.rect.top,
                ))
        for btn in self.idol_buttons:
            if btn.tooltip and btn.hovered and (btn.tooltip_always or not btn.enabled):
                self.tooltip_registry.offer(TooltipDescriptor(
                    btn.tooltip, _GUIDANCE_HOVER_REGIONS,
                    btn.rect.centerx, btn.rect.top,
                ))

        # Title tooltips
        if self.guidance_title_hovered and self.guidance_title_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self._GUIDANCE_TITLE_TOOLTIP, _GUIDANCE_HOVER_REGIONS,
                self.guidance_title_rect.centerx,
                self.guidance_title_rect.bottom, below=True,
            ))
        if self.idol_title_hovered and self.idol_title_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self._IDOL_TITLE_TOOLTIP, _GUIDANCE_HOVER_REGIONS,
                self.idol_title_rect.centerx,
                self.idol_title_rect.bottom, below=True,
            ))

        # Submit button
        if self.submit_button:
            has_guide = bool(self.selected_faction)
            has_idol = bool(self.selected_idol_type and self.selected_hex)
            can_guide = bool(self.phase_options.get("available_factions"))
            can_place_idol = bool(self.idol_buttons) and bool(self.phase_options.get("neutral_hexes"))
            can_swell = self.phase_options.get("can_swell", False)
            if can_swell:
                # Swell requires placing an idol first if idol placement is available
                self.submit_button.enabled = has_idol if can_place_idol else True
            elif can_guide and can_place_idol:
                self.submit_button.enabled = has_guide and has_idol
            else:
                self.submit_button.enabled = has_guide or has_idol

            # Selection info right above the Confirm/Swell button
            parts = []
            if self.selected_faction:
                fname = faction_full_name(self.selected_faction)
                parts.append(f"Guide: {fname}")
            if self.selected_idol_type:
                parts.append(f"Idol: {self.selected_idol_type}")
            if self.selected_hex:
                parts.append(f"Hex: ({self.selected_hex[0]}, {self.selected_hex[1]})")
            if parts:
                text = self.font.render(" | ".join(parts), True, theme.TEXT_HIGHLIGHT)
                screen.blit(text, (20, self.submit_button.rect.top - text.get_height() - 4))

            # Disabled tooltip: explain what's still needed
            if not self.submit_button.enabled:
                missing = []
                if can_swell:
                    # Swell disabled because idol not yet placed
                    if not self.selected_idol_type and not self.selected_hex:
                        missing.append("an Idol type and a hex location before Swelling")
                    elif not self.selected_idol_type:
                        missing.append("an Idol type before Swelling")
                    elif not self.selected_hex:
                        missing.append("a hex location for your Idol before Swelling")
                else:
                    if can_guide and not has_guide:
                        missing.append("a Faction to Guide")
                    if can_place_idol:
                        if not self.selected_idol_type and not self.selected_hex:
                            missing.append("an Idol type and a hex location")
                        elif not self.selected_idol_type:
                            missing.append("an Idol type")
                        elif not self.selected_hex:
                            missing.append("a hex location for your Idol")
                if missing:
                    self.submit_button.tooltip = "Still needed: " + ", ".join(missing)
                else:
                    self.submit_button.tooltip = None
            elif not can_swell:
                self.submit_button.tooltip = None

            self.submit_button.draw(screen, self.font)
            if (self.submit_button.tooltip and self.submit_button.hovered
                    and (not self.submit_button.enabled or self.submit_button.tooltip_always)):
                self.tooltip_registry.offer(TooltipDescriptor(
                    self.submit_button.tooltip, _GUIDANCE_HOVER_REGIONS,
                    self.submit_button.rect.centerx, self.submit_button.rect.top,
                ))

    def _get_current_faction_modifiers(self) -> dict:
        """Get the change_modifiers for the current player's guided faction."""
        my_spirit = self.spirits.get(self.app.my_spirit_id, {})
        fid = my_spirit.get("guided_faction")
        if fid and fid in self.factions:
            return self.factions[fid].get("change_modifiers", {})
        return {}

    def _render_agenda_ui(self, screen):
        if self.agenda_hand:
            my_spirit = self.spirits.get(self.app.my_spirit_id, {})
            faction_id = my_spirit.get("guided_faction", "")
            faction_name = faction_full_name(faction_id) if faction_id else "your Faction"

            card_rects = self._calc_left_choice_card_rects(len(self.agenda_hand))
            start_x = card_rects[0].x if card_rects else 20
            start_y = card_rects[0].y if card_rects else _CHOICE_CARD_Y

            title = self.font.render(f"Choose agenda for {faction_name}:", True, theme.TEXT_BRIGHT)
            title_x = max(4, start_x + 2)
            screen.blit(title, (title_x, 102))

            modifiers = self._get_current_faction_modifiers()
            faction_data = self.factions.get(faction_id, {})
            faction_territories = len(faction_data.get("territories", []))
            self.ui_renderer.draw_card_hand(
                screen, self.agenda_hand,
                self.selected_agenda_index,
                start_x, start_y,
                modifiers=modifiers,
                card_images=agenda_card_images,
                vertical=True,
                territories=faction_territories,
            )

        if self.submit_button:
            self.submit_button.enabled = self.selected_agenda_index >= 0
            self.submit_button.draw(screen, self.font)

    def _render_change_ui(self, screen):
        if not self.change_cards:
            return
        my_spirit = self.spirits.get(self.app.my_spirit_id, {})
        fid = my_spirit.get("guided_faction", "")
        faction_name = faction_full_name(fid) if fid else "your Faction"

        hand = []
        for card_name in self.change_cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        card_rects = self._calc_left_choice_card_rects(len(hand))
        start_x = card_rects[0].x if card_rects else 20
        start_y = card_rects[0].y if card_rects else _CHOICE_CARD_Y

        title = self.font.render(f"Choose modifier for {faction_name}:", True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (max(4, start_x + 2), 102))

        modifiers = self._get_current_faction_modifiers()
        self.ui_renderer.draw_card_hand(
            screen, hand, -1,
            start_x, start_y,
            modifiers=modifiers,
            card_images=agenda_card_images,
            show_preview_plus=True,
            vertical=True,
        )

    def _render_ejection_ui(self, screen):
        faction_name = faction_full_name(self.ejection_faction)
        title_text = (
            f"As the last remnants of your Influence leave the {faction_name} faction, "
            f"you nudge their future. Choose one card to remove from {faction_name}'s Agenda pool "
            f"and one to add in its place:"
        )
        keywords = ["Influence", "Agenda pool"]
        text_x = 20
        max_text_width = max(220, _HEX_MAP_LEFT_X - 30)
        lines = _wrap_text(title_text, self.font, max_text_width)
        line_h = self.font.get_linesize()
        title_h = len(lines) * line_h
        buttons_top = min(
            (btn.rect.top for btn in self.remove_buttons + self.action_buttons),
            default=SCREEN_HEIGHT - 240,
        )
        # Keep wrapped title clear of section labels ("Remove"/"Add"), not just buttons.
        first_label_y = buttons_top - line_h - 8
        text_bottom_limit = first_label_y - 8
        text_y = max(96, text_bottom_limit - title_h)
        self.ejection_keyword_rects = render_rich_lines(
            screen, self.font, lines, text_x, text_y,
            keywords=keywords,
            hovered_keyword=self.hovered_ejection_keyword,
            normal_color=theme.TEXT_HIGHLIGHT,
            keyword_color=theme.TEXT_KEYWORD,
            hovered_keyword_color=theme.TEXT_KEYWORD_HOV,
        )

        # Section labels
        if self.remove_buttons:
            remove_label_y = self.remove_buttons[0].rect.top - line_h - 8
            lbl = self.font.render("Remove:", True, (200, 120, 120))
            screen.blit(lbl, (text_x, remove_label_y))
        if self.action_buttons:
            add_label_y = self.action_buttons[0].rect.top - line_h - 8
            lbl = self.font.render("Add:", True, (120, 200, 120))
            screen.blit(lbl, (text_x, add_label_y))

        # Highlight and draw remove buttons
        for btn in self.remove_buttons:
            btn.enabled = btn.text.lower() != self.selected_ejection_add_type
            if self.selected_ejection_remove_type and btn.text.lower() == self.selected_ejection_remove_type:
                btn.color = (160, 60, 60)
            else:
                btn.color = (110, 50, 50)
            btn.draw(screen, self.font)

        # Highlight and draw add buttons
        for btn in self.action_buttons:
            btn.enabled = btn.text.lower() != self.selected_ejection_remove_type
            if self.selected_ejection_add_type and btn.text.lower() == self.selected_ejection_add_type:
                btn.color = (80, 150, 80)
            else:
                btn.color = (80, 60, 130)
            btn.draw(screen, self.font)

        # Register tooltips for all ejection buttons
        all_ejection_btns = self.remove_buttons + self.action_buttons
        for btn in all_ejection_btns:
            if btn.tooltip and btn.hovered and (btn.tooltip_always or not btn.enabled):
                self.tooltip_registry.offer(TooltipDescriptor(
                    btn.tooltip, _GUIDANCE_HOVER_REGIONS,
                    btn.rect.centerx, btn.rect.top,
                ))
        if self.hovered_ejection_keyword:
            tooltip = _INFLUENCE_TOOLTIP if self.hovered_ejection_keyword == "Influence" else _AGENDA_POOL_TOOLTIP
            rects = self.ejection_keyword_rects.get(self.hovered_ejection_keyword, [])
            if rects:
                mx, my = pygame.mouse.get_pos()
                anchor = rects[0]
                for rect in rects:
                    if rect.collidepoint(mx, my):
                        anchor = rect
                        break
                self.tooltip_registry.offer(TooltipDescriptor(
                    tooltip, _GUIDANCE_HOVER_REGIONS,
                    anchor.centerx, anchor.bottom, below=True,
                ))

        # Confirm button
        if self.submit_button:
            same_type = (
                self.selected_ejection_remove_type is not None
                and self.selected_ejection_add_type is not None
                and self.selected_ejection_remove_type == self.selected_ejection_add_type
            )
            self.submit_button.enabled = (
                self.selected_ejection_remove_type is not None
                and self.selected_ejection_add_type is not None
                and not same_type
            )
            self.submit_button.tooltip = (
                "Choose a different Agenda to add."
                if same_type else None
            )
            self.submit_button.draw(screen, self.font)

    def _render_battleground_ui(self, screen):
        """Render the battleground choice instruction panel."""
        if not self.battleground_choice_wars:
            return
        n = len(self.battleground_choice_wars)
        idx = min(self.battleground_display_index, n - 1)
        wc = self.battleground_choice_wars[idx]
        war_id = wc["war_id"]
        mode = wc["mode"]
        fa = faction_full_name(wc.get("faction_a", ""))
        fb = faction_full_name(wc.get("faction_b", ""))
        enemy = faction_full_name(wc.get("enemy_faction", ""))

        # Title
        title_text = f"Battleground: {fa} vs {fb}"
        title = self.font.render(title_text, True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (20, 102))

        # Page indicator for multiple wars
        if n > 1:
            page_text = f"War {idx + 1} / {n}"
            page_surf = self.font.render(page_text, True, theme.TEXT_DIM)
            screen.blit(page_surf, (20, 122))
            # Nav arrows
            arrow_y = 122
            arrow_w, arrow_h = 18, 18
            left_rect = pygame.Rect(180, arrow_y, arrow_w, arrow_h)
            right_rect = pygame.Rect(202, arrow_y, arrow_w, arrow_h)
            pygame.draw.polygon(screen, (180, 180, 180),
                [(left_rect.right, left_rect.top),
                 (left_rect.left, left_rect.centery),
                 (left_rect.right, left_rect.bottom)])
            pygame.draw.polygon(screen, (180, 180, 180),
                [(right_rect.left, right_rect.top),
                 (right_rect.right, right_rect.centery),
                 (right_rect.left, right_rect.bottom)])
            self.battleground_nav_left_rect = left_rect
            self.battleground_nav_right_rect = right_rect
        else:
            self.battleground_nav_left_rect = None
            self.battleground_nav_right_rect = None

        # Mode instruction
        if mode == "full":
            instruction = "Click any border hex on the map to choose a battleground pair."
        else:
            instruction = f"Click a {enemy} border hex to set the enemy side."

        lines = _wrap_text(instruction, self.font, 220)
        line_h = self.font.get_linesize()
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, theme.TEXT_NORMAL)
            screen.blit(surf, (20, 146 + i * line_h))

        # Per-war selection status
        status_y = 146 + len(lines) * line_h + 12
        for i, war_choice in enumerate(self.battleground_choice_wars):
            wid = war_choice["war_id"]
            chosen = self.battleground_selections.get(wid)
            wfa = faction_full_name(war_choice.get("faction_a", ""))
            wfb = faction_full_name(war_choice.get("faction_b", ""))
            label = f"{wfa} vs {wfb}"
            color = (100, 220, 100) if chosen is not None else (180, 180, 180)
            check = " ✓" if chosen is not None else ""
            s = self.font.render(f"{label}{check}", True, color)
            screen.blit(s, (20, status_y + i * line_h))

        # Hint about what the battleground is used for
        hint_y = status_y + len(self.battleground_choice_wars) * line_h + 10
        hint = self.font.render("Expand Spoils claims the losing side hex.", True, theme.TEXT_DIM)
        screen.blit(hint, (20, hint_y))

        # Submit button — enabled only when all wars chosen
        if self.submit_button:
            all_chosen = len(self.battleground_selections) >= len(self.battleground_choice_wars)
            self.submit_button.enabled = all_chosen
            if not all_chosen:
                self.submit_button.tooltip = "Select a hex for each war first."
                self.submit_button.tooltip_always = True
            else:
                self.submit_button.tooltip = None
                self.submit_button.tooltip_always = False
            self.submit_button.draw(screen, self.font)

    def _render_expand_choice_ui(self, screen):
        faction_name = faction_full_name(self.expand_choice_faction)
        title = self.font.render(f"Expand: {faction_name}", True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (20, 102))

        instruction = "Click a highlighted hex to choose where to expand."
        lines = _wrap_text(instruction, self.font, 220)
        line_h = self.font.get_linesize()
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, theme.TEXT_NORMAL)
            screen.blit(surf, (20, 130 + i * line_h))

        if self.submit_button:
            self.submit_button.enabled = self.selected_hex is not None
            if not self.submit_button.enabled:
                self.submit_button.tooltip = "Select a hex first."
                self.submit_button.tooltip_always = True
            else:
                self.submit_button.tooltip = None
                self.submit_button.tooltip_always = False
            self.submit_button.draw(screen, self.font)

    def _render_spoils_ui(self, screen):
        if not self.spoils_entries:
            return
        n = len(self.spoils_entries)
        idx = max(0, min(self.spoils_display_index, n - 1))
        entry = self.spoils_entries[idx]

        modifiers = self._get_current_faction_modifiers()

        hand = [{"agenda_type": card} for card in entry.cards]
        card_rects = self._calc_left_choice_card_rects(len(hand))
        start_x = card_rects[0].x if card_rects else 20
        start_y = card_rects[0].y if card_rects else _CHOICE_CARD_Y

        # Title and nav arrows above cards
        opponent_name = faction_full_name(entry.loser) if entry.loser else ""
        title_text = (f"Spoils vs {opponent_name}:"
                      if opponent_name else "Spoils of War:")
        title = self.font.render(title_text, True, (255, 200, 100))
        title_x = max(4, start_x + 2)
        screen.blit(title, (title_x, 102))

        self.spoils_nav_left_rect = None
        self.spoils_nav_right_rect = None
        if n > 1:
            page_text = f"[{idx + 1}/{n}]"
            page_surf = self.small_font.render(page_text, True, (200, 200, 200))
            screen.blit(page_surf, (title_x, 121))

        self.ui_renderer.draw_card_hand(
            screen, hand, entry.selected,
            start_x, start_y,
            modifiers=modifiers,
            card_images=agenda_card_images,
            is_spoils=True,
            vertical=True,
        )

        if n > 1:
            if idx > 0:
                left_surf = self.font.render("\u25c4", True, (200, 200, 200))
                left_x = max(4, title_x - left_surf.get_width() - 6)
                screen.blit(left_surf, (left_x, 102))
                self.spoils_nav_left_rect = pygame.Rect(left_x, 102, left_surf.get_width(), left_surf.get_height())
            if idx < n - 1:
                right_surf = self.font.render("\u25ba", True, (200, 200, 200))
                right_x = title_x + title.get_width() + 6
                screen.blit(right_surf, (right_x, 102))
                self.spoils_nav_right_rect = pygame.Rect(right_x, 102, right_surf.get_width(), right_surf.get_height())

        # Submit button
        if self.submit_button:
            all_selected = all(e.selected >= 0 for e in self.spoils_entries)
            self.submit_button.enabled = all_selected
            if not all_selected:
                unselected_wars = [
                    faction_full_name(self.spoils_entries[i].loser) or f"War {i + 1}"
                    for i in range(n) if self.spoils_entries[i].selected < 0
                ]
                self.submit_button.tooltip = "Still need to choose: " + ", ".join(unselected_wars)
                self.submit_button.tooltip_always = True
            else:
                self.submit_button.tooltip = None
            self.submit_button.draw(screen, self.font)
            if (self.submit_button.tooltip and self.submit_button.hovered
                    and (not self.submit_button.enabled or self.submit_button.tooltip_always)):
                self.tooltip_registry.offer(TooltipDescriptor(
                    self.submit_button.tooltip, _GUIDANCE_HOVER_REGIONS,
                    self.submit_button.rect.centerx, self.submit_button.rect.top,
                ))

    def _render_spoils_change_ui(self, screen):
        if not self.spoils_change_entries:
            return
        n = len(self.spoils_change_entries)
        idx = max(0, min(self.spoils_display_index, n - 1))
        entry = self.spoils_change_entries[idx]

        hand = []
        for card_name in entry.cards:
            desc = self.ui_renderer._build_modifier_description(card_name)
            hand.append({"agenda_type": card_name, "description": desc})
        card_rects = self._calc_left_choice_card_rects(len(hand))
        start_x = card_rects[0].x if card_rects else 20
        start_y = card_rects[0].y if card_rects else _CHOICE_CARD_Y

        # Title and nav arrows above cards
        opponent_name = faction_full_name(entry.loser) if entry.loser else ""
        title_text = (f"Spoils vs {opponent_name} - modifier:"
                      if opponent_name else "Spoils - Choose modifier:")
        title = self.font.render(title_text, True, (255, 200, 100))
        title_x = max(4, start_x + 2)
        screen.blit(title, (title_x, 102))

        self.spoils_nav_left_rect = None
        self.spoils_nav_right_rect = None
        if n > 1:
            page_text = f"[{idx + 1}/{n}]"
            page_surf = self.small_font.render(page_text, True, (200, 200, 200))
            screen.blit(page_surf, (title_x, 121))

        self.ui_renderer.draw_card_hand(
            screen, hand, entry.selected,
            start_x, start_y,
            card_images=agenda_card_images,
            vertical=True,
        )

        if n > 1:
            if idx > 0:
                left_surf = self.font.render("\u25c4", True, (200, 200, 200))
                left_x = max(4, title_x - left_surf.get_width() - 6)
                screen.blit(left_surf, (left_x, 102))
                self.spoils_nav_left_rect = pygame.Rect(left_x, 102, left_surf.get_width(), left_surf.get_height())
            if idx < n - 1:
                right_surf = self.font.render("\u25ba", True, (200, 200, 200))
                right_x = title_x + title.get_width() + 6
                screen.blit(right_surf, (right_x, 102))
                self.spoils_nav_right_rect = pygame.Rect(right_x, 102, right_surf.get_width(), right_surf.get_height())

        # Submit button
        if self.submit_button:
            all_selected = all(e.selected >= 0 for e in self.spoils_change_entries)
            self.submit_button.enabled = all_selected
            if not all_selected:
                unselected_wars = [
                    faction_full_name(self.spoils_change_entries[i].loser) or f"War {i + 1}"
                    for i in range(n) if self.spoils_change_entries[i].selected < 0
                ]
                self.submit_button.tooltip = "Still need to choose: " + ", ".join(unselected_wars)
                self.submit_button.tooltip_always = True
            else:
                self.submit_button.tooltip = None
            self.submit_button.draw(screen, self.font)
            if (self.submit_button.tooltip and self.submit_button.hovered
                    and (not self.submit_button.enabled or self.submit_button.tooltip_always)):
                self.tooltip_registry.offer(TooltipDescriptor(
                    self.submit_button.tooltip, _GUIDANCE_HOVER_REGIONS,
                    self.submit_button.rect.centerx, self.submit_button.rect.top,
                ))
