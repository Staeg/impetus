"""Primary gameplay scene: hex map, UI, phases."""

from __future__ import annotations
import math
from typing import Any
import pygame
from dataclasses import dataclass
from shared.constants import (
    Phase, AgendaType, IdolType, MAP_SIDE_LENGTH,
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES, FACTION_COLORS,
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPRAWL_IDOL_VP, SPREAD_IDOL_VP,
)
from shared.protocol import C2S, S2C, SubPhase
from shared.hex_utils import axial_to_pixel, hex_vertices
from shared.era_data import (
    GUIDANCE_STEP_RESTRAIN,
    GUIDANCE_STEP_SHAPE,
    GUIDANCE_STEP_ADAPT,
    GUIDANCE_STEP_EJECT,
    get_era_card_info,
)
from client.faction_names import faction_full_name, update_faction_races
from client.renderer.hex_renderer import HexRenderer
from client.renderer.ui_renderer import (
    UIRenderer, Button, build_agenda_tooltip, build_modifier_tooltip,
    draw_dotted_underline, _draw_text_in_rect, _wrap_text, render_rich_lines, render_event_log_line,
)
from client.renderer.font_cache import get_font
import client.theme as theme
from client.renderer.animation import (
    AnimationManager, TextAnimation, IdolBeamAnimation,
    TokenArcAnimation, TokenSplitAnimation, TokenShakeFadeAnimation,
)
from client.renderer.assets import load_assets, agenda_card_images
from client.input_handler import InputHandler
from client.input_actions import map_game_input
from client.scenes.animation_orchestrator import AnimationOrchestrator
from client.scenes.change_tracker import FactionChangeTracker
from client.scenes.game_phase_controller import GamePhaseController
from client.scenes.subphase_state import should_preserve_subphase
from client.renderer.popup_manager import (
    PopupManager, HoverRegion, TooltipDescriptor, TooltipRegistry,
    set_ui_rects, _WEIGHT_TEXT, _WEIGHT_NON_TEXT,
)


def _recompute_layout_globals() -> None:
    global _HEX_MAP_HALF_W, _HEX_MAP_LEFT_X, _HEX_MAP_RIGHT_X
    global _FACTION_PANEL_X, _PANEL_W
    global _FACTION_PANEL_MAX_H, _SPIRIT_PANEL_MAX_H, _EVENT_LOG_H, _EVENT_LOG_H_ENLARGED
    global _GUIDANCE_CENTER_X, _BTN_W, _BTN_H, _BTN_STEP_Y, _GUIDANCE_BTN_X, _BOARD_ZOOM
    global _TITLE_Y, _BTN_START_Y, _RIBBON_BOTTOM_Y, _MAP_CENTER_Y
    global _CARD_W, _CARD_H, _CARD_SPACING, _CARD_H_TALL
    base_screen_w = 1280
    base_screen_h = 800
    base_faction_panel_h = 300
    base_spirit_panel_h = 195
    base_event_log_h = 191

    _BOARD_ZOOM = min(1.5, SCREEN_WIDTH / base_screen_w, SCREEN_HEIGHT / base_screen_h)

    # Approximate hex map screen bounds (default camera) for centering UI
    base_hex_map_half_w = math.sqrt(3) * HEX_SIZE * (MAP_SIDE_LENGTH - 0.5)
    _HEX_MAP_HALF_W = int(base_hex_map_half_w * _BOARD_ZOOM)
    _HEX_MAP_LEFT_X = SCREEN_WIDTH // 2 - _HEX_MAP_HALF_W
    _HEX_MAP_RIGHT_X = SCREEN_WIDTH // 2 + _HEX_MAP_HALF_W

    # Right column layout: starts just past map right edge
    _FACTION_PANEL_X = _HEX_MAP_RIGHT_X + 14
    _PANEL_W = SCREEN_WIDTH - _FACTION_PANEL_X - 2

    available_sidebar_h = max(280, SCREEN_HEIGHT - 102 - 4)
    _SPIRIT_PANEL_MAX_H = base_spirit_panel_h
    remaining_sidebar_h = max(120, available_sidebar_h - _SPIRIT_PANEL_MAX_H - 8)
    sidebar_ratio = base_faction_panel_h / (base_faction_panel_h + base_event_log_h)
    _FACTION_PANEL_MAX_H = max(220, int(round(remaining_sidebar_h * sidebar_ratio)))
    _EVENT_LOG_H = max(140, remaining_sidebar_h - _FACTION_PANEL_MAX_H)
    _EVENT_LOG_H_ENLARGED = max(400, int(_EVENT_LOG_H * 1.45))

    # Centering positions for button column (left side only)
    _GUIDANCE_CENTER_X = _HEX_MAP_LEFT_X // 2
    _BTN_W = 157
    _BTN_H = 37
    _BTN_STEP_Y = 43
    _GUIDANCE_BTN_X = _GUIDANCE_CENTER_X - _BTN_W // 2

    # Title positions (below faction overview strip which ends at Y=97)
    _TITLE_Y = 102
    _BTN_START_Y = 129
    _RIBBON_BOTTOM_Y = 97
    _MAP_CENTER_Y = (_RIBBON_BOTTOM_Y + SCREEN_HEIGHT) // 2

    # Card picker dimensions
    _CARD_W = 110
    _CARD_H = 145
    _CARD_SPACING = 5
    _CARD_H_TALL = 170


_recompute_layout_globals()

_INFLUENCE_TOOLTIP = (
    "The number of additional Agenda cards a Spirit draws when "
    "choosing for their Guided Faction. Set to 3 when Guidance "
    "begins, it decreases by 1 each turn. The Spirit is ejected "
    "when it reaches 0."
)

_ERA2_CYCLE_TOOLTIP = (
    "Era 2 Guidance follows a four-turn cycle: Restrain an Agenda, Shape the Faction, "
    "Adapt your Spirit, then face Ejection on the fourth turn."
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
    "a War is declared. The War resolves immediately during the same turn's "
    "War Phase.\n\n"
    "If only one Faction is Guided, that Spirit decides which Faction wins. "
    "If both or neither Faction is Guided, both sides roll a 6-sided die and "
    "add their Territory count — highest total wins."
)

_WAR_RESOLVES_TOOLTIP = (
    "When a War resolves, the winner gets Spoils of War: a random Agenda card.\n\n"
    "If the winning Faction is Guided, the Spirit draws 1 + Influence cards "
    "and picks one to resolve.\n\n"
    "Spoils Expand works differently: instead of claiming a neutral hex, the "
    "winner conquers any Territory belonging to the loser. It costs gold equal "
    "to territory count (same as normal Expand). If the Faction is Guided, the "
    "Spirit chooses which enemy Territory to take; otherwise a random Territory "
    "is chosen. If two Factions target the same hex, both fail and receive the "
    "gold consolation instead.\n\n"
    "Other Spoils Agendas work normally. No gold is gained or lost from War itself."
)

_SPOILS_TOOLTIP = (
    "Spoils are bonus Agenda rewards earned after winning a War. Pick one reward for each defeated faction shown here. "
    "Your choice resolves immediately and may differ from spoils won against other factions in the same turn."
)

_GOLD_TOOLTIP = "Resource used to pay for Expand Agendas. Cannot go below 0."

_TRADE_AGENDA_TOOLTIP = "Trade\n+1 gold, +1 gold for every other Faction playing Trade this turn, +1 gold for every Faction playing Expand this turn.\n+1 Regard with each other Faction playing Trade (not Expand) this turn."
_STEAL_AGENDA_TOOLTIP = "Steal\n-1 Regard with and -1 gold to all neighbors. +1 gold for each gold lost. War is declared at -2 Regard and resolves immediately."
_EXPAND_AGENDA_TOOLTIP = "Expand\nGuided: choose a reachable neutral hex to claim (cost = territories). If multiple Spirits pick the same hex, both fail. Unguided: random. If unavailable or lacking gold, +1 gold instead."

_MODIFIER_TOOLTIP = (
    "Permanently improves a specific Agenda when used by the Faction implementing the modifier. "
    "These bonuses stack. Possible modifiers:\n"
    "Trade: +1 gold and +1 Regard per co-trader\n"
    "Steal: +1 gold stolen and -1 regard to affected neighbors\n"
    "Expand: -1 cost on successful Expands, +1 gold on failed Expands"
)

_CONTESTED_TOOLTIP = (
    "If several Spirits without a relevant Affinity attempt to Guide the same Faction on a given turn, "
    "the Guidance fails. This prevents all involved Spirits from Guiding "
    "that Faction for exactly 1 turn.\n\n"
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
    expanded: bool = True


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
        self.phase_controller = GamePhaseController(self)
        load_assets()

        self.game_state: dict = {}
        self.phase = ""
        self.turn = 0
        self.current_era = "era_1"
        self.vp_target = 0
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
        self._display_idols: list | None = None
        self._display_spirits: dict | None = None
        self._pending_idol_reveal_delay: float | None = None
        self.waiting_for: list[str] = []
        self.has_submitted: bool = False
        self.spectator_mode: bool = False
        self.event_log: list[str] = []
        self.event_log_meta: list[dict] = []
        self.event_log_scroll_offset: int = 0
        self.event_log_h_scroll_offset: int = 0
        self.event_log_enlarged: bool = False
        self._event_log_cycle_log_idx: int | None = None
        self._event_log_cycle_target_index: int = 0
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
        self.preview_idol: tuple | None = None  # (idol_type, q, r, player_idx)

        # Fading error message (e.g. invalid hex click)
        self._hex_error_message: str = ""
        self._hex_error_timer: float = 0.0

        # Agenda state
        self.agenda_hand: list[dict] = []
        self.selected_agenda_index: int = -1
        self.selected_restrain_index: int = -1

        # Change/ejection/spoils state
        self.change_cards: list[str] = []
        self.battleground_choice_entries: list[dict] = []
        self.battleground_choice_buttons: list[dict] = []
        self.battleground_choice_index: int = 0
        self.battleground_selections: dict[str, int] = {}
        self.war_support_entries: list[dict] = []
        self.war_support_buttons: list[dict] = []
        self.war_support_selections: dict[str, str] = {}
        self.ejection_pending = False
        self.ejection_faction = ""
        self.ejection_pool: list[str] = []
        self.selected_ejection_remove_type: str | None = None
        self.selected_ejection_add_type: str | None = None
        self.spoils_entries: list[SpoilsEntry] = []
        self.spoils_change_entries: list[SpoilsEntry] = []
        self.spoils_display_index: int = 0
        self.faction_panel_scroll_offset: int = 0
        self.persistent_spirit_panel_scroll_offset: int = 0
        self.spoils_nav_left_rect: pygame.Rect | None = None
        self.spoils_nav_right_rect: pygame.Rect | None = None
        self.spoils_toggle_rects: list[pygame.Rect] = []
        self.spoils_card_rects: list[list[pygame.Rect]] = []
        self.spoils_panel_rects: list[pygame.Rect] = []
        self.spoils_help_rect: pygame.Rect | None = None

        # Winner choice state (one-guided war: spirit picks who wins)
        self.winner_choice_wars: list[dict] = []  # [{war_id, faction_a, faction_b, guided_faction}]
        self.winner_selections: dict[str, str] = {}  # war_id -> chosen winner faction_id
        self.winner_choice_buttons: list[dict] = []  # [{war_id, faction, rect}]

        # Spoils expand choice state (spirit picks enemy territory to conquer)
        self.spoils_expand_choices: list[dict] = []  # [{loser, available_hexes}]
        self.spoils_expand_display_index: int = 0
        self.spoils_expand_selectable_hexes: set[tuple] = set()
        self.spoils_expand_selections: list[tuple] = []  # chosen hex per entry
        self.spoils_expand_nav_left_rect: pygame.Rect | None = None
        self.spoils_expand_nav_right_rect: pygame.Rect | None = None

        # Expand choice state
        self.expand_choice_hexes: set[tuple] = set()
        self.expand_choice_faction: str = ""

        # Respawn choice state
        self.respawn_choice_hexes: set[tuple] = set()
        self.respawn_choice_faction: str = ""

        # In-game menu (top-right)
        self._ingame_menu_open: bool = False
        self._ingame_menu_confirm_exit: bool = False
        self._ingame_menu_btn_rect: pygame.Rect | None = None
        self._ingame_menu_item_rects: list[tuple[str, pygame.Rect]] = []
        self._ingame_confirm_yes_rect: pygame.Rect | None = None
        self._ingame_confirm_no_rect: pygame.Rect | None = None
        self.disconnected_players: list[dict] = []
        self.disconnect_kick_buttons: dict[str, Button] = {}
        self.status_banner_message: str | None = None
        self.status_banner_timer: float = 0.0

        # UI buttons
        self.action_buttons: list[Button] = []
        self.remove_buttons: list[Button] = []
        self.submit_button: Button | None = None
        self.faction_buttons: list[Button] = []
        self.faction_button_ids: list[str] = []
        self.idol_buttons: list[Button] = []
        self.idol_drag_sources: list[dict] = []
        self.dragging_idol: dict | None = None

        # Title labels (rects + tooltip text)
        self.guidance_title_rect: pygame.Rect | None = None
        self.guidance_title_hovered: bool = False
        self.idol_title_rect: pygame.Rect | None = None
        self.idol_title_hovered: bool = False
        self.guidance_summary_rect: pygame.Rect | None = None
        self.guidance_summary_keyword_rects: dict[str, list[pygame.Rect]] = {}
        self.hovered_guidance_summary_keyword: str | None = None

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
        self.hovered_panel_shaping: str | None = None
        self.hovered_vp_spirit_id: str | None = None
        self.hovered_text_faction_id: str | None = None
        self.hovered_text_faction_rect: pygame.Rect | None = None
        self.hovered_event_log_tooltip: tuple[str, pygame.Rect] | None = None

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
        self._battleground_arrow_rects: list[dict] = []
        # Ejection title keyword hover state
        self.ejection_keyword_rects: dict[str, list[pygame.Rect]] = {}
        self.ejection_faction_rects: list[pygame.Rect] = []
        self.hovered_ejection_keyword: str | None = None

        # Change tracking for faction panel
        self.change_tracker = FactionChangeTracker()
        self.popup_manager = PopupManager()
        self.tooltip_registry = TooltipRegistry()
        self.highlighted_log_index: int | None = None
        self.panel_change_rects: list[tuple[pygame.Rect, int]] = []

        self._font = None
        self._small_font = None

        self.tutorial_feedback_message: str | None = None
        self._tutorial_context: dict[str, Any] = {"inspection_tags": set()}

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
            S2C.GAME_START:   self._handle_game_start,
            S2C.PHASE_START:  self._handle_phase_start,
            S2C.PHASE_RESULT: self._handle_phase_result,
            S2C.WAITING_FOR:  self._handle_waiting_for,
            S2C.GAME_OVER:    self._handle_game_over,
            S2C.ERROR:        self._handle_error,
            S2C.PRESENCE_STATE: self._handle_presence_state,
            S2C.SYSTEM_MESSAGE: self._handle_system_message,
        }
        self._apply_viewport_layout()

    def _apply_viewport_layout(self) -> None:
        self.input_handler.zoom = _BOARD_ZOOM
        self.input_handler.camera_y = (SCREEN_HEIGHT / 2 - _MAP_CENTER_Y) / max(_BOARD_ZOOM, 0.01)

    def on_resize(self, width: int, height: int) -> None:
        _recompute_layout_globals()
        self._apply_viewport_layout()
        if self.phase == Phase.VAGRANT_PHASE.value and self.phase_options.get("action") == "choose":
            self._build_faction_buttons()
            if self.phase_options.get("can_place_idol", True):
                self._build_idol_buttons()
            else:
                self.idol_buttons = []
                self.idol_title_rect = None
        if self.submit_button:
            self.submit_button.rect.y = SCREEN_HEIGHT - 60

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

    def set_tutorial_feedback(self, message: str | None) -> None:
        self.tutorial_feedback_message = message

    def get_tutorial_context(self) -> dict[str, Any]:
        return self._tutorial_context

    def clear_tutorial_state(self) -> None:
        self.tutorial_feedback_message = None
        self._tutorial_context = {"inspection_tags": set()}

    def get_tutorial_overlay_layout(self) -> dict[str, Any]:
        avoid_rects: list[pygame.Rect] = []
        if self.agenda_hand:
            avoid_rects.extend(self._calc_left_choice_card_rects(len(self.agenda_hand)))
        if self.change_cards:
            avoid_rects.extend(self._calc_left_choice_card_rects(len(self.change_cards)))
        for panel_cards in self.spoils_card_rects:
            avoid_rects.extend(panel_cards)
        avoid_rects.extend(self.remove_buttons[i].rect for i in range(len(self.remove_buttons)))
        avoid_rects.extend(self.action_buttons[i].rect for i in range(len(self.action_buttons)))
        if self.phase == Phase.VAGRANT_PHASE.value:
            avoid_rects.extend(btn.rect for btn in self.faction_buttons)
            avoid_rects.extend(btn.rect for btn in self.idol_buttons)
            if self.submit_button:
                selection_rect = pygame.Rect(
                    18,
                    max(_RIBBON_BOTTOM_Y + 12, self.submit_button.rect.top - 34),
                    max(260, _HEX_MAP_LEFT_X - 36),
                    28,
                )
                avoid_rects.append(selection_rect)
        if self.submit_button:
            preferred = pygame.Rect(
                18,
                self.submit_button.rect.top - 158,
                430,
                136,
            )
        else:
            preferred = pygame.Rect(18, 108, 430, 136)
        candidates = [
            preferred,
            pygame.Rect(18, 108, 430, 136),
            pygame.Rect(_FACTION_PANEL_X, 108, min(430, _PANEL_W), 136),
        ]
        message_rect = candidates[-1]
        top_limit = _RIBBON_BOTTOM_Y + 10
        for candidate in candidates:
            if candidate.top < top_limit:
                continue
            if any(candidate.colliderect(rect.inflate(14, 14)) for rect in avoid_rects):
                continue
            message_rect = candidate
            break
        return {"message_rect": message_rect}

    def draw_tutorial_highlights(self, screen: pygame.Surface, highlights: list[Any]) -> None:
        if screen.get_width() < 32 or screen.get_height() < 32:
            return
        pulse = 0.7 + 0.3 * math.sin(pygame.time.get_ticks() / 180.0)
        for spec in highlights:
            accent = spec.accent
            if spec.kind == "faction":
                self._draw_tutorial_rects(screen, accent, pulse, self._faction_highlight_rects(spec.value))
                faction_hexes = {
                    hex_coord
                    for hex_coord, owner in self.hex_ownership.items()
                    if owner == spec.value
                }
                self._draw_tutorial_hexes(screen, accent, pulse, faction_hexes)
            elif spec.kind == "neutral_hexes":
                neutral_hexes = {
                    hex_coord
                    for hex_coord, owner in self.hex_ownership.items()
                    if owner is None
                }
                self._draw_tutorial_hexes(screen, accent, pulse, neutral_hexes)
            elif spec.kind == "idol_tokens":
                self._draw_tutorial_idols(screen, accent, pulse)
            elif spec.kind == "idol_type":
                rects = [btn.rect for btn in self.idol_buttons if btn.text.lower() == str(spec.value).title().lower()]
                self._draw_tutorial_rects(screen, accent, pulse, rects)
            elif spec.kind == "agenda_type":
                rects = []
                if self.agenda_hand:
                    for index, rect in enumerate(self._calc_left_choice_card_rects(len(self.agenda_hand))):
                        if self.agenda_hand[index].get("agenda_type") == spec.value:
                            rects.append(rect)
                self._draw_tutorial_rects(screen, accent, pulse, rects)
            elif spec.kind == "selectable_hexes":
                self._draw_tutorial_hexes(screen, accent, pulse, self._tutorial_selectable_hexes(str(spec.value)))
            elif spec.kind == "submit_button":
                rects = [self.submit_button.rect] if self.submit_button else []
                self._draw_tutorial_rects(screen, accent, pulse, rects)
            elif spec.kind == "change_cards":
                rects = self._calc_left_choice_card_rects(len(self.change_cards)) if self.change_cards else []
                self._draw_tutorial_rects(screen, accent, pulse, rects)
            elif spec.kind == "winner_choices":
                self._draw_tutorial_rects(screen, accent, pulse, [btn["rect"] for btn in self.winner_choice_buttons])
            elif spec.kind == "spoils_cards":
                self._draw_tutorial_rects(
                    screen,
                    accent,
                    pulse,
                    [rect for panel_cards in self.spoils_card_rects for rect in panel_cards],
                )
            elif spec.kind == "spoils_change_cards":
                self._draw_tutorial_rects(
                    screen,
                    accent,
                    pulse,
                    [rect for panel_cards in self.spoils_card_rects for rect in panel_cards],
                )
            elif spec.kind == "ejection_remove_buttons":
                self._draw_tutorial_rects(screen, accent, pulse, [btn.rect for btn in self.remove_buttons])
            elif spec.kind == "ejection_add_buttons":
                self._draw_tutorial_rects(screen, accent, pulse, [btn.rect for btn in self.action_buttons])
            elif spec.kind == "panel_counter":
                self._draw_tutorial_rects(screen, accent, pulse, self._panel_counter_rects(spec.value))
            elif spec.kind == "war" and self.wars:
                self.hex_renderer.draw_war_glow_arrows(
                    screen,
                    self.wars,
                    self.hex_ownership,
                    self.input_handler,
                    SCREEN_WIDTH,
                    SCREEN_HEIGHT,
                    pulse=pulse,
                )

    def _panel_counter_rects(self, counter_name: str) -> list[pygame.Rect]:
        if counter_name == "worship" and self.ui_renderer.panel_worship_rect:
            return [self.ui_renderer.panel_worship_rect]
        if counter_name == "influence":
            rect = self._persistent_spirit_panel_rects.get("influence")
            return [rect] if rect else []
        if counter_name == "guidance":
            rect = self._persistent_spirit_panel_rects.get("guidance")
            return [rect] if rect else []
        return []

    def _faction_highlight_rects(self, faction_id: str) -> list[pygame.Rect]:
        rects: list[pygame.Rect] = []
        ribbon_rect = self.ribbon_faction_rects.get(faction_id)
        if ribbon_rect:
            rects.append(ribbon_rect)
        for btn, fid in zip(self.faction_buttons, self.faction_button_ids):
            if fid == faction_id:
                rects.append(btn.rect)
        if self.panel_faction == faction_id and self.ui_renderer.faction_panel_rect:
            rects.append(self.ui_renderer.faction_panel_rect)
        return rects

    def _tutorial_selectable_hexes(self, selector: str) -> set[tuple[int, int]]:
        if selector == "idol":
            return {
                hex_coord
                for hex_coord, owner in self.hex_ownership.items()
                if owner is None
            }
        if selector == "expand":
            return set(self.expand_choice_hexes)
        if selector == "respawn":
            return set(self.respawn_choice_hexes)
        if selector == "spoils_expand":
            return set(self.spoils_expand_selectable_hexes)
        return set()

    def _draw_tutorial_rects(
        self,
        screen: pygame.Surface,
        accent: tuple[int, int, int],
        pulse: float,
        rects: list[pygame.Rect],
    ) -> None:
        for rect in rects:
            if rect.width <= 0 or rect.height <= 0:
                continue
            pad_x = 6 if rect.width <= 180 else 8
            pad_y = 4 if rect.height <= 40 else 6
            glow_rect = rect.inflate(pad_x * 2, pad_y * 2)
            radius = max(8, min(18, glow_rect.height // 2))
            overlay = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
            alpha = int(28 + 30 * pulse)
            pygame.draw.rect(overlay, (*accent, alpha), overlay.get_rect(), border_radius=radius)
            screen.blit(overlay, glow_rect.topleft)
            pygame.draw.rect(screen, accent, glow_rect, 2, border_radius=radius)

    def _draw_tutorial_hexes(
        self,
        screen: pygame.Surface,
        accent: tuple[int, int, int],
        pulse: float,
        hexes: set[tuple[int, int]],
    ) -> None:
        if SCREEN_WIDTH < 32 or SCREEN_HEIGHT < 32:
            return
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        border_width = 2 + int(round(pulse * 2))
        for q, r in hexes:
            verts = hex_vertices(q, r, HEX_SIZE)
            screen_verts = [
                self.input_handler.world_to_screen(vx, vy, SCREEN_WIDTH, SCREEN_HEIGHT)
                for vx, vy in verts
            ]
            pygame.draw.polygon(overlay, (*accent, 34), screen_verts)
            pygame.draw.polygon(screen, accent, screen_verts, border_width)
        screen.blit(overlay, (0, 0))

    def _draw_tutorial_idols(
        self,
        screen: pygame.Surface,
        accent: tuple[int, int, int],
        pulse: float,
    ) -> None:
        if not self.display_idols:
            return
        spirit_index_map = {sid: i for i, sid in enumerate(sorted(self.spirits.keys()))}
        ring_width = 2 + int(round(pulse * 2))
        for idol in self.display_idols:
            owner_spirit = getattr(idol, "owner_spirit", None)
            player_idx = spirit_index_map.get(owner_spirit, 0)
            ix, iy = self.hex_renderer.get_idol_slot_screen(
                idol.position.q,
                idol.position.r,
                player_idx,
                self.input_handler,
                SCREEN_WIDTH,
                SCREEN_HEIGHT,
            )
            pygame.draw.circle(screen, accent, (ix, iy), self.hex_renderer.get_idol_radius() + 8, ring_width)

    def _tutorial_runtime(self):
        return getattr(self.app, "tutorial_runtime", None)

    def _tutorial_notify(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        runtime = self._tutorial_runtime()
        if runtime:
            runtime.handle_semantic_event(event_type, payload or {})

    def _tutorial_guard(self, action_kind: str, payload: dict[str, Any] | None = None) -> bool:
        runtime = self._tutorial_runtime()
        if not runtime:
            return True
        allowed, message = runtime.can_perform(action_kind, payload or {}, self)
        if not allowed:
            self._hex_error_message = message or "That action is locked for this tutorial step."
            self._hex_error_timer = 2.0
            runtime.set_feedback(message or "That action is locked for this tutorial step.")
            return False
        return True

    def _update_state_from_snapshot(self, data: dict, suppress_animations: bool = False):
        """Update local state from a game state snapshot dict."""
        self.turn = data.get("turn", self.turn)
        self.phase = data.get("phase", self.phase)
        self.current_era = data.get("era", self.current_era)
        self.vp_target = data.get("vp_target", self.vp_target)
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
            if (not suppress_animations) and old_inf > new_inf:
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
        if self._display_idols is None:
            import copy
            self._display_idols = copy.deepcopy(self.all_idols)
        if self._display_spirits is None:
            import copy
            self._display_spirits = copy.deepcopy(self.spirits)

    def _clear_display_state(self):
        """Clear deferred display state so rendering uses real state."""
        self._display_hex_ownership = None
        self._display_factions = None
        self._display_wars = None
        self._display_idols = None
        self._display_spirits = None
        self._pending_idol_reveal_delay = None

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

    @property
    def display_idols(self) -> list:
        return self._display_idols if self._display_idols is not None else self.all_idols

    @property
    def display_spirits(self) -> dict:
        return self._display_spirits if self._display_spirits is not None else self.spirits

    def handle_event(self, event):
        self.input_handler.handle_camera_event(event)
        action = map_game_input(event)

        if action and action.kind == "scroll_ui":
            _cur_event_log_h = _EVENT_LOG_H_ENLARGED if self.event_log_enlarged else _EVENT_LOG_H
            _cur_faction_panel_h = _FACTION_PANEL_MAX_H + _EVENT_LOG_H - _cur_event_log_h
            _event_log_y = 102 + _cur_faction_panel_h + 4 + _SPIRIT_PANEL_MAX_H + 4
            log_rect = getattr(self, '_event_log_render_rect', None) or pygame.Rect(_FACTION_PANEL_X, _event_log_y, _PANEL_W, _cur_event_log_h)
            mx, my = pygame.mouse.get_pos()
            if log_rect.collidepoint(mx, my):
                visible_count = (_cur_event_log_h - 26) // 16
                max_offset = max(0, len(self.event_log) - visible_count)
                self.event_log_scroll_offset += action.payload["y"]
                self.event_log_scroll_offset = max(0, min(self.event_log_scroll_offset, max_offset))
                self.event_log_h_scroll_offset += action.payload["x"] * 16
                self.event_log_h_scroll_offset = max(0, self.event_log_h_scroll_offset)
            # Faction panel scroll
            fp_rect = self.ui_renderer.faction_panel_rect
            if fp_rect and fp_rect.collidepoint(mx, my):
                content_h = getattr(self.ui_renderer, '_faction_panel_content_h', 0)
                max_scroll = max(0, content_h - _cur_faction_panel_h)
                self.faction_panel_scroll_offset = max(0, min(
                    self.faction_panel_scroll_offset - action.payload["y"] * 16, max_scroll))
            persistent_rect = self._persistent_spirit_panel_rects.get("panel")
            if persistent_rect and persistent_rect.collidepoint(mx, my):
                content_h = getattr(self.ui_renderer, '_spirit_panel_content_h', 0)
                max_scroll = max(0, content_h - _SPIRIT_PANEL_MAX_H)
                self.persistent_spirit_panel_scroll_offset = max(
                    0,
                    min(self.persistent_spirit_panel_scroll_offset - action.payload["y"] * 16, max_scroll),
                )

        if action and action.kind == "cancel":
            if self.game_over:
                self.app.leave_game_to_menu()
                return
            self.popup_manager.handle_escape()

        if action and action.kind == "hover":
            mouse_pos = action.payload
            for btn in self.action_buttons + self.remove_buttons + self.faction_buttons + self.idol_buttons:
                btn.update(mouse_pos)
            if self.submit_button:
                self.submit_button.update(mouse_pos)
            if self.dragging_idol:
                self.dragging_idol["pos"] = mouse_pos
            # Title label hover tracking
            if self.guidance_title_rect:
                self.guidance_title_hovered = self.guidance_title_rect.collidepoint(mouse_pos)
            if self.idol_title_rect:
                self.idol_title_hovered = self.idol_title_rect.collidepoint(mouse_pos)
            # Idol hover detection on hex map
            self._update_idol_hover(mouse_pos)
            # Agenda card/label/animation hover detection
            self._update_agenda_hover(mouse_pos)
            # Faction panel guided/worship hover detection
            self._update_panel_hover(mouse_pos)
            self._update_guidance_summary_hover(mouse_pos)
            # Spirit panel hover detection
            self._update_spirit_panel_hover(mouse_pos)
            self._update_clickable_faction_hover(mouse_pos)
            # Ejection title keyword hover detection
            self._update_ejection_title_hover(mouse_pos)
            # Agenda pool icon hover detection
            self.hovered_pool_faction = None
            for fid, rect in self.pool_icon_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.hovered_pool_faction = fid
                    break
            # Ribbon war indicator hover detection
            self.hovered_ribbon_war_fid = None
            for fid, rect in self.ribbon_war_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.hovered_ribbon_war_fid = fid
                    break
            # Ribbon worship sigil hover detection
            self.hovered_ribbon_worship_fid = None
            for fid, rect in self.ribbon_worship_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.hovered_ribbon_worship_fid = fid
                    break
            # Guided hex sigil hover detection
            self._update_guided_hex_hover(mouse_pos)
            # Popup keyword hover
            self.popup_manager.update_hover(mouse_pos)
            for button in self.disconnect_kick_buttons.values():
                button.update(mouse_pos)

        if action and action.kind == "primary_click":
            click_pos = action.payload
            for player in self.disconnected_players:
                spirit_id = player.get("spirit_id")
                button = self.disconnect_kick_buttons.get(spirit_id)
                if not spirit_id or not button:
                    continue
                if button.clicked(click_pos):
                    if int(player.get("disconnected_seconds", 0)) < 30 or not self._can_vote_kick(player):
                        return
                    self.app.network.send(C2S.VOTE_KICK_DISCONNECTED, {
                        "target_spirit_id": spirit_id,
                    })
                    return
            # In-game menu: confirm exit dialog takes priority
            if self._ingame_menu_confirm_exit:
                if self._ingame_confirm_yes_rect and self._ingame_confirm_yes_rect.collidepoint(click_pos):
                    self.app.leave_game_to_menu()
                    return
                if self._ingame_confirm_no_rect and self._ingame_confirm_no_rect.collidepoint(click_pos):
                    self._ingame_menu_confirm_exit = False
                    return
                return  # swallow all clicks while confirm is open
            # In-game menu button toggle
            if self._ingame_menu_btn_rect and self._ingame_menu_btn_rect.collidepoint(click_pos):
                self._ingame_menu_open = not self._ingame_menu_open
                return
            # In-game menu items (when open)
            if self._ingame_menu_open:
                for label, rect in self._ingame_menu_item_rects:
                    if rect.collidepoint(click_pos):
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

            runtime = self._tutorial_runtime()
            if runtime and runtime.handle_click(click_pos):
                return
            clicked_log_idx = self._get_clicked_event_log_index(click_pos)
            if clicked_log_idx != self._event_log_cycle_log_idx:
                self._reset_event_log_cycle()
            # Event log expand/collapse toggle (always accessible)
            if (self.ui_renderer.event_log_expand_rect and
                    self.ui_renderer.event_log_expand_rect.collidepoint(click_pos)):
                self.event_log_enlarged = not self.event_log_enlarged
                return

            if not (self.spectator_mode and not self.game_over):
                # Check submit button
                if self.submit_button and self.submit_button.clicked(event.pos):
                    if self._tutorial_guard("submit", {"phase": self.phase}):
                        self._submit_action()
                    return

                # Check ejection remove buttons
                for btn in self.remove_buttons:
                    if btn.clicked(event.pos):
                        chosen_remove = btn.text.lower()
                        if self.selected_ejection_add_type == chosen_remove:
                            return
                        self.selected_ejection_remove_type = chosen_remove
                        self._tutorial_notify("ejection_remove_selected", {"agenda_type": chosen_remove})
                        return

                # Check action buttons
                for btn in self.action_buttons:
                    if btn.clicked(event.pos):
                        self._handle_action_button(btn.text)
                        return

                # Check faction buttons
                for btn, fid in zip(self.faction_buttons, self.faction_button_ids):
                    if btn.clicked(event.pos):
                        if not self._tutorial_guard("select_faction", {"faction": fid}):
                            return
                        self._handle_faction_select(fid)
                        self._tutorial_notify("select_faction", {"faction": fid})
                        return

                # Check idol type buttons
                for btn in self.idol_buttons:
                    if btn.clicked(event.pos):
                        if not self._tutorial_guard("select_idol", {"idol_type": btn.text.lower()}):
                            return
                        if self.current_era == "era_1":
                            self._begin_idol_drag(btn)
                            self._tutorial_notify("select_idol", {"idol_type": btn.text.lower()})
                            return
                        self._handle_idol_select(btn.text.lower())
                        self._tutorial_notify("select_idol", {"idol_type": btn.text.lower()})
                        return

                if self._is_mouse_over_selected_preview(event.pos):
                    if self._begin_selected_preview_drag():
                        return

                # Check agenda card clicks
                if self.agenda_hand:
                    for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.agenda_hand))):
                        if rect.collidepoint(event.pos):
                            if not self._tutorial_guard("select_agenda", {"agenda_index": i, "agenda": self.agenda_hand[i].get("agenda_type", "")}):
                                return
                            self.selected_agenda_index = i
                            self._tutorial_notify("select_agenda", {"agenda_index": i, "agenda": self.agenda_hand[i].get("agenda_type", "")})
                            return

                # Check change card clicks
                if self.change_cards:
                    for i, rect in enumerate(self._calc_left_choice_card_rects(len(self.change_cards))):
                        if rect.collidepoint(event.pos):
                            if self.phase == SubPhase.CHANGE_CHOICE and not self._tutorial_guard("select_change_card", {"card_index": i, "card": self.change_cards[i]}):
                                return
                            if self.phase == SubPhase.CHANGE_CHOICE:
                                self._submit_card_choice(i, C2S.SUBMIT_CHANGE_CHOICE, "change_cards")
                                self._tutorial_notify("change_choice_selected", {"card_index": i, "card": self.change_cards[i]})
                            elif self.phase == SubPhase.RESTRAIN_CHOICE:
                                self.selected_restrain_index = i
                            elif self.phase == SubPhase.SHAPING_CHOICE:
                                self.app.network.send(C2S.SUBMIT_SHAPING_CHOICE, {"card_name": self.change_cards[i]})
                                self.change_cards = []
                                self.has_submitted = True
                            elif self.phase == SubPhase.ADAPTATION_CHOICE:
                                self.app.network.send(C2S.SUBMIT_ADAPTATION_CHOICE, {"card_name": self.change_cards[i]})
                                self.change_cards = []
                                self.has_submitted = True
                            return

                # Check spoils card clicks (one-at-a-time display)
                if self.spoils_entries:
                    for idx, rect in enumerate(self.spoils_toggle_rects):
                        if rect.collidepoint(event.pos):
                            self.spoils_entries[idx].expanded = not self.spoils_entries[idx].expanded
                            return
                    for entry, rects in zip(self.spoils_entries, self.spoils_card_rects):
                        for i, rect in enumerate(rects):
                            if rect.collidepoint(event.pos):
                                if not self._tutorial_guard("select_spoils_card", {"card_index": i, "card": entry.cards[i]}):
                                    return
                                entry.selected = i
                                entry.expanded = True
                                self._tutorial_notify("spoils_choice_selected", {"card_index": i, "card": entry.cards[i]})
                                return

                # Winner choice buttons
                if self.phase == SubPhase.WINNER_CHOICE and self.winner_choice_buttons:
                    for btn in self.winner_choice_buttons:
                        if btn["rect"].collidepoint(event.pos):
                            if not self._tutorial_guard("select_winner", {"war_id": btn["war_id"], "winner": btn["faction"]}):
                                return
                            self.winner_selections[btn["war_id"]] = btn["faction"]
                            self._tutorial_notify("winner_choice_selected", {"war_id": btn["war_id"], "winner": btn["faction"]})
                            return

                if self.phase == SubPhase.BATTLEGROUND_CHOICE and self.battleground_choice_buttons:
                    for btn in self.battleground_choice_buttons:
                        if btn["rect"].collidepoint(event.pos):
                            self.battleground_selections[btn["war_id"]] = btn["pair_index"]
                            return

                if self.phase == SubPhase.WAR_SUPPORT_CHOICE and self.war_support_buttons:
                    for btn in self.war_support_buttons:
                        if btn["rect"].collidepoint(event.pos):
                            self.war_support_selections[btn["war_id"]] = btn["faction"]
                            return

                # Spoils expand nav arrows (multiple wars)
                if self.phase == SubPhase.SPOILS_EXPAND_CHOICE and self.spoils_expand_choices:
                    if (self.spoils_expand_nav_left_rect
                            and self.spoils_expand_nav_left_rect.collidepoint(event.pos)):
                        self.spoils_expand_display_index = max(
                            0, self.spoils_expand_display_index - 1)
                        self._refresh_spoils_expand_hex_set()
                        self.selected_hex = None
                        return
                    if (self.spoils_expand_nav_right_rect
                            and self.spoils_expand_nav_right_rect.collidepoint(event.pos)):
                        self.spoils_expand_display_index = min(
                            len(self.spoils_expand_choices) - 1,
                            self.spoils_expand_display_index + 1)
                        self._refresh_spoils_expand_hex_set()
                        self.selected_hex = None
                        return

                # Check spoils change card clicks (one-at-a-time display)
                if self.spoils_change_entries:
                    for idx, rect in enumerate(self.spoils_toggle_rects):
                        if rect.collidepoint(event.pos):
                            self.spoils_change_entries[idx].expanded = not self.spoils_change_entries[idx].expanded
                            return
                    for entry, rects in zip(self.spoils_change_entries, self.spoils_card_rects):
                        for i, rect in enumerate(rects):
                            if rect.collidepoint(event.pos):
                                if not self._tutorial_guard("select_spoils_change_card", {"card_index": i, "card": entry.cards[i]}):
                                    return
                                entry.selected = i
                                entry.expanded = True
                                self._tutorial_notify("spoils_change_selected", {"card_index": i, "card": entry.cards[i]})
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

            if any(rect.collidepoint(event.pos) for rect in self.ejection_faction_rects):
                self._select_faction_from_text(self.ejection_faction)
                return

            for rects in (self._spirit_panel_rects, self._persistent_spirit_panel_rects):
                guidance_rect = rects.get("guidance")
                if guidance_rect and guidance_rect.collidepoint(event.pos):
                    spirit_id = self.spirit_panel_spirit_id if rects is self._spirit_panel_rects else self.app.my_spirit_id
                    guided_faction = self.spirits.get(spirit_id, {}).get("guided_faction")
                    if guided_faction:
                        self._select_faction_from_text(guided_faction)
                        return
                for fid, rect in rects.get("worship", {}).items():
                    if rect.collidepoint(event.pos):
                        self._select_faction_from_text(fid)
                        return

            for fid, rect in self.ui_renderer.panel_war_opponent_rects.items():
                if rect.collidepoint(event.pos):
                    self._select_faction_from_text(fid)
                    return
            if clicked_log_idx is not None:
                self._handle_event_log_click(clicked_log_idx)
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
                    self._select_faction_from_text(fid)
                    return

            # Hex click
            hex_coord = self.hex_renderer.get_hex_at_screen(
                event.pos[0], event.pos[1], self.input_handler,
                SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
            )
            if hex_coord:
                self._handle_hex_click(hex_coord)
                return

            # Battleground selection now happens on map arrows.
            if self.phase == SubPhase.BATTLEGROUND_CHOICE:
                for btn in self.battleground_choice_buttons:
                    if btn["rect"].collidepoint(event.pos):
                        self.battleground_selections[btn["war_id"]] = btn["pair_index"]
                        return

            # Empty background / neutral space clears focused faction or spirit selections.
            panel_rects = [
                self.ui_renderer.faction_panel_rect,
                self._persistent_spirit_panel_rects.get("panel"),
                self._spirit_panel_rects.get("panel"),
                getattr(self, "_event_log_render_rect", None),
            ]
            if any(rect and rect.collidepoint(event.pos) for rect in panel_rects):
                return
            if not self.popup_manager.has_popups():
                self._clear_focus_selection()
                return

        if action and action.kind == "secondary_click":
            if self.popup_manager.has_popups():
                self.popup_manager.handle_right_click(
                    action.payload, self.small_font, SCREEN_WIDTH)
            else:
                self._try_pin_hovered_tooltip(action.payload)

        if action and action.kind == "primary_release" and self.dragging_idol:
            self._finish_idol_drag(action.payload)

    def _handle_action_button(self, text: str):
        if self.ejection_pending:
            chosen_add = text.lower()
            if self.selected_ejection_remove_type == chosen_add:
                return
            self.selected_ejection_add_type = chosen_add
            self._tutorial_notify("ejection_add_selected", {"agenda_type": chosen_add})
            return

    def _handle_faction_select(self, faction_id: str):
        self.selected_faction = faction_id
        self.panel_faction = faction_id
        self.spirit_panel_spirit_id = None
        self.faction_panel_scroll_offset = 0
        self._tutorial_notify("focus_faction", {"faction": faction_id})
        self._tutorial_notify("inspect_faction", {"faction": faction_id})

    def _select_faction_from_text(self, faction_id: str):
        self.panel_faction = faction_id
        self.spirit_panel_spirit_id = None
        self.faction_panel_scroll_offset = 0
        if self.phase == Phase.VAGRANT_PHASE.value and self.faction_buttons:
            available = set(self.phase_options.get("available_factions", []))
            blocked = set(self.phase_options.get("worship_blocked", []))
            if faction_id in available and faction_id not in blocked:
                self.selected_faction = faction_id
                self._tutorial_notify("select_faction", {"faction": faction_id})
        self._tutorial_notify("focus_faction", {"faction": faction_id})
        self._tutorial_notify("inspect_faction", {"faction": faction_id})

    def _clear_focus_selection(self):
        self.panel_faction = None
        self.spirit_panel_spirit_id = None
        self.selected_faction = None
        self.faction_panel_scroll_offset = 0

    def _clear_panel_selection(self):
        self.panel_faction = None
        self.spirit_panel_spirit_id = None
        self.faction_panel_scroll_offset = 0

    def _handle_idol_select(self, idol_type: str):
        self.selected_idol_type = idol_type

    def _begin_idol_drag(self, btn: Button) -> None:
        idol_type = IdolType(btn.text.lower())
        self.dragging_idol = {
            "idol_type": idol_type,
            "pos": pygame.mouse.get_pos(),
            "radius": max(10, btn.rect.width // 4),
        }

    def _begin_selected_preview_drag(self) -> bool:
        """Pick up the currently marked idol placement from the map."""
        if not (self.selected_idol_type and self.selected_hex):
            return False
        try:
            idol_type = IdolType(self.selected_idol_type)
        except ValueError:
            return False
        self.dragging_idol = {
            "idol_type": idol_type,
            "pos": pygame.mouse.get_pos(),
            "radius": self.hex_renderer.get_idol_radius(),
            "origin_hex": self.selected_hex,
            "origin_type": self.selected_idol_type,
        }
        self.selected_hex = None
        return True

    def _is_mouse_over_selected_preview(self, mouse_pos: tuple[int, int]) -> bool:
        """Return True when the cursor is over the current preview idol on the board."""
        if not (self.selected_idol_type and self.selected_hex):
            return False
        player_idx = 0
        if self.app.my_spirit_id in self.spirits:
            player_idx = sorted(self.spirits.keys()).index(self.app.my_spirit_id)
        ix, iy = self.hex_renderer.get_idol_slot_screen(
            self.selected_hex[0], self.selected_hex[1], player_idx,
            self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
        )
        cx, cy = self.input_handler.world_to_screen(
            *axial_to_pixel(self.selected_hex[0], self.selected_hex[1], HEX_SIZE),
            SCREEN_WIDTH, SCREEN_HEIGHT,
        )
        screen_hex_radius = math.dist((ix, iy), (cx, cy)) * 2
        hit_radius = self.hex_renderer.get_idol_radius(screen_hex_radius) + 5
        return (mouse_pos[0] - ix) ** 2 + (mouse_pos[1] - iy) ** 2 <= hit_radius ** 2

    def _finish_idol_drag(self, mouse_pos: tuple[int, int]) -> None:
        drag = self.dragging_idol
        self.dragging_idol = None
        if not drag:
            return
        def _restore_origin() -> None:
            if drag.get("origin_hex") and drag.get("origin_type"):
                self.selected_hex = drag["origin_hex"]
                self.selected_idol_type = drag["origin_type"]
        hex_coord = self.hex_renderer.get_hex_at_screen(
            mouse_pos[0], mouse_pos[1], self.input_handler,
            SCREEN_WIDTH, SCREEN_HEIGHT, set(self.hex_ownership.keys())
        )
        if not hex_coord:
            _restore_origin()
            return
        if self.phase != Phase.VAGRANT_PHASE.value or self.current_era != "era_1":
            _restore_origin()
            return
        if self.hex_ownership.get(hex_coord) is not None:
            self._hex_error_message = "Idols can only be dropped on neutral hexes."
            self._hex_error_timer = 2.0
            _restore_origin()
            return
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
            _restore_origin()
            return
        self.selected_idol_type = drag["idol_type"].value
        self.selected_hex = hex_coord

    def _get_highlighted_war_pairs(self) -> dict[str, tuple[tuple[int, int], tuple[int, int]]]:
        highlighted = {}
        if self.phase != SubPhase.BATTLEGROUND_CHOICE:
            return highlighted
        for entry in self.battleground_choice_entries:
            pair_index = self.battleground_selections.get(entry["war_id"])
            if pair_index is None:
                continue
            pair = entry.get("pairs", [])[pair_index]
            highlighted[entry["war_id"]] = (
                (pair["a"]["q"], pair["a"]["r"]),
                (pair["b"]["q"], pair["b"]["r"]),
            )
        return highlighted

    def _handle_hex_click(self, hex_coord: tuple[int, int]):
        if self.phase == SubPhase.SPOILS_EXPAND_CHOICE:
            if hex_coord in self.spoils_expand_selectable_hexes:
                if not self._tutorial_guard("select_hex", {"hex": hex_coord, "kind": "spoils_expand"}):
                    return
                idx = min(self.spoils_expand_display_index, len(self.spoils_expand_choices) - 1)
                self.spoils_expand_selections[idx] = hex_coord
                self.selected_hex = hex_coord
                self._tutorial_notify("spoils_expand_choice_selected", {"hex": hex_coord})
            return
        if self.phase == SubPhase.EXPAND_CHOICE:
            if hex_coord in self.expand_choice_hexes:
                if not self._tutorial_guard("select_hex", {"hex": hex_coord, "kind": "expand"}):
                    return
                self.selected_hex = hex_coord
                self._tutorial_notify("expand_choice_selected", {"hex": hex_coord})
            return
        if self.phase == SubPhase.RESPAWN_CHOICE:
            if hex_coord in self.respawn_choice_hexes:
                if not self._tutorial_guard("select_hex", {"hex": hex_coord, "kind": "respawn"}):
                    return
                self.selected_hex = hex_coord
                self._tutorial_notify("respawn_choice_selected", {"hex": hex_coord})
            return
        if self.phase == Phase.VAGRANT_PHASE.value and self.hex_ownership.get(hex_coord) is None:
            if self.current_era == "era_1":
                self._clear_focus_selection()
                return
            self._clear_focus_selection()
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
            if not self._tutorial_guard("select_hex", {"hex": hex_coord, "kind": "idol"}):
                return
            self.selected_hex = hex_coord
            self._tutorial_notify("select_hex", {"hex": hex_coord, "kind": "idol"})
        else:
            owner = self.hex_ownership.get(hex_coord)
            if owner:
                self._tutorial_context.setdefault("inspection_tags", set()).add("owned")
                if any(
                    isinstance(idol, dict)
                    and idol.get("position", {}).get("q") == hex_coord[0]
                    and idol.get("position", {}).get("r") == hex_coord[1]
                    for idol in self.all_idols
                ):
                    self._tutorial_context["inspection_tags"].add("idol")
                    self._tutorial_notify("inspect_idol", {"hex": hex_coord, "owner": owner})
                self._tutorial_notify("inspect_hex", {"hex": hex_coord, "owner": owner})
                self._select_faction_from_text(owner)
            else:
                self._tutorial_context.setdefault("inspection_tags", set()).add("neutral")
                self._tutorial_notify("inspect_hex", {"hex": hex_coord, "owner": None})
                self._clear_focus_selection()

    def _submit_action(self):
        self.phase_controller.submit_current_phase()

    def _submit_card_choice(self, index: int, msg_type: str, card_attr: str):
        self.app.network.send(msg_type, {"card_index": index})
        setattr(self, card_attr, [])
        self.has_submitted = True

    def _clear_selection(self):
        self.selected_faction = None
        self.selected_hex = None
        self.selected_idol_type = None
        self.panel_faction = None
        self.selected_agenda_index = -1
        self.selected_restrain_index = -1
        self.selected_ejection_remove_type = None
        self.selected_ejection_add_type = None
        self.ejection_pool = []
        self.agenda_hand = []
        self.action_buttons = []
        self.remove_buttons = []
        self.faction_buttons = []
        self.idol_buttons = []
        self.idol_drag_sources = []
        self.dragging_idol = None
        self.submit_button = None
        self.guidance_title_rect = None
        self.guidance_title_hovered = False
        self.idol_title_rect = None
        self.idol_title_hovered = False
        self.guidance_summary_rect = None
        self.guidance_summary_keyword_rects = {}
        self.hovered_guidance_summary_keyword = None
        self.ejection_keyword_rects = {}
        self.ejection_faction_rects = []
        self.hovered_ejection_keyword = None
        self.winner_choice_wars = []
        self.winner_selections = {}
        self.winner_choice_buttons = []
        self.battleground_choice_entries = []
        self.battleground_choice_buttons = []
        self.battleground_selections = {}
        self.war_support_entries = []
        self.war_support_buttons = []
        self.war_support_selections = {}
        self.spoils_expand_choices = []
        self.spoils_expand_selections = []
        self.spoils_expand_selectable_hexes = set()
        self.spoils_toggle_rects = []
        self.spoils_card_rects = []
        self.spoils_panel_rects = []
        self.spoils_help_rect = None
        self._battleground_arrow_rects = []
        self.expand_choice_hexes = set()
        self.expand_choice_faction = ""
        self.respawn_choice_hexes = set()
        self.respawn_choice_faction = ""

    def handle_network(self, msg_type, payload):
        handler = self._net_handlers.get(msg_type)
        if handler:
            handler(payload)

    def _handle_game_start(self, payload):
        self._phase_result_queue = []
        self._pending_game_over = None
        self.game_over = False
        self.game_over_data = None
        self._ingame_menu_open = False
        self._ingame_menu_confirm_exit = False
        self.disconnected_players = []
        self.disconnect_kick_buttons = {}
        self.status_banner_message = None
        self.status_banner_timer = 0.0
        self.event_log = []
        self.event_log_meta = []
        self._reset_event_log_cycle()
        self._update_state_from_snapshot(payload)
        self.change_tracker.snapshot_and_reset(self.factions, self.spirits)
        self.event_log.append("Game started.")
        self.event_log_meta.append({"factions": [], "spans": []})
        self.spectator_mode = self.app.my_spirit_id not in self.spirits
        self.clear_tutorial_state()
        runtime = self._tutorial_runtime()
        if runtime and not self.spectator_mode:
            runtime.attach_scene(self)
        self._tutorial_notify("game_started", {"turn": self.turn})

    def _handle_phase_start(self, payload):
        phase = payload.get("phase", "")
        action = payload.get("options", {}).get("action", "")
        needs_input = action not in ("none", "") or phase in (
            SubPhase.CHANGE_CHOICE, SubPhase.RESTRAIN_CHOICE, SubPhase.SHAPING_CHOICE,
            SubPhase.ADAPTATION_CHOICE, SubPhase.SPOILS_CHOICE,
            SubPhase.SPOILS_CHANGE_CHOICE, SubPhase.SPOILS_EXPAND_CHOICE,
            SubPhase.WINNER_CHOICE, SubPhase.BATTLEGROUND_CHOICE, SubPhase.WAR_SUPPORT_CHOICE,
            SubPhase.EJECTION_CHOICE,
            SubPhase.EXPAND_CHOICE, SubPhase.RESPAWN_CHOICE)
        should_defer = (
            needs_input
            and (
                self.orchestrator.has_animations_playing()
                or self._phase_result_queue
            )
        )
        if should_defer:
            self.orchestrator.deferred_phase_start = payload
        else:
            self.phase = payload.get("phase", self.phase)
            self.turn = payload.get("turn", self.turn)
            self.phase_options = payload.get("options", {})
            self._setup_phase_ui()
            self._tutorial_notify("phase_start", {"phase": self.phase, "turn": self.turn, "options": self.phase_options})

    def _handle_waiting_for(self, payload):
        self.waiting_for = payload.get("players_remaining", [])

    def _handle_presence_state(self, payload):
        players = payload.get("players", [])
        self.disconnected_players = [
            player for player in players
            if (
                not player.get("connected", True)
                and not player.get("is_spectator", False)
                and not player.get("is_ai", False)
            )
        ]
        self._rebuild_disconnect_kick_buttons()

    def _handle_system_message(self, payload):
        message = payload.get("message", "")
        if not message:
            return
        self.event_log.append(message)
        self.event_log_meta.append({"factions": [], "spans": []})
        self.status_banner_message = message
        self.status_banner_timer = 5.0

    def _handle_phase_result(self, payload):
        """Queue PHASE_RESULT for sequential processing in update()."""
        self._phase_result_queue.append(payload)

    def _process_phase_result(self, payload):
        active_sub_phase = self.phase if self.phase in (
            SubPhase.CHANGE_CHOICE, SubPhase.RESTRAIN_CHOICE, SubPhase.SHAPING_CHOICE,
            SubPhase.ADAPTATION_CHOICE, SubPhase.SPOILS_CHOICE, SubPhase.SPOILS_CHANGE_CHOICE,
            SubPhase.SPOILS_EXPAND_CHOICE, SubPhase.WINNER_CHOICE, SubPhase.BATTLEGROUND_CHOICE,
            SubPhase.WAR_SUPPORT_CHOICE, SubPhase.EJECTION_CHOICE, SubPhase.EXPAND_CHOICE,
            SubPhase.RESPAWN_CHOICE) else None
        suppress_animations = bool(payload.get("suppress_animations"))
        # Snapshot display state before updating so animations render old state
        events = payload.get("events", [])
        _ANIM_ORDER = {
            "trade": 0, "steal": 1,
            "expand": 2, "expand_failed": 2, "expand_spoils": 2,
            "change": 3,
        }
        agenda_events = [e for e in events if e.get("type", "") in _ANIM_ORDER
                       and not e.get("is_guided_modifier")]
        vagrant_anim_events = {
            "idol_placed", "guided", "guide_contested", "worship_gained", "worship_replaced",
        }
        has_vagrant_resolution = any(e.get("type") in vagrant_anim_events for e in events)
        if (not suppress_animations) and agenda_events and "state" in payload:
            # Clear any stale display state before re-snapshotting so that
            # fast AI-only games (queue never fully drains) always get a fresh
            # baseline for hex-reveal and war-reveal animations each turn.
            self._clear_display_state()
            self._snapshot_display_state()
        elif (not suppress_animations) and has_vagrant_resolution and "state" in payload:
            self._clear_display_state()
            self._snapshot_display_state()
        if "state" in payload:
            self._update_state_from_snapshot(payload["state"], suppress_animations=suppress_animations)
        # Preserve sub-phases while this player still has cards to choose
        if should_preserve_subphase(active_sub_phase, {
            "change_cards": self.change_cards,
            "spoils_entries": self.spoils_entries,
            "spoils_change_entries": self.spoils_change_entries,
            "spoils_expand_choices": self.spoils_expand_choices,
            "winner_choice_wars": self.winner_choice_wars,
            "battleground_choice_entries": self.battleground_choice_entries,
            "war_support_entries": self.war_support_entries,
            "ejection_pending": self.ejection_pending,
            "expand_choice_hexes": self.expand_choice_hexes,
            "respawn_choice_hexes": self.respawn_choice_hexes,
        }):
            self.phase = active_sub_phase
        if has_vagrant_resolution and not suppress_animations:
            self._queue_vagrant_resolution_animations(events)
        # Log events (consolidate agenda play + resolution into one line)
        self._log_events_batch(events)
        # VP gain animations
        for event in ([] if suppress_animations else events):
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
                        if event.get("sprawl_idols", event.get("spread_idols", 0)) > 0 and territories_gained > 0:
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
        if agenda_events and not suppress_animations:
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
                if (etype in _ANIM_ORDER or etype == "war_declared") and not event.get("is_guided_modifier"):
                    current_turn_batch.append(event)
            if current_turn_batch:
                turn_batched_events.append(current_turn_batch)

            if not saw_turn_markers:
                war_events = [e for e in events if e.get("type") == "war_declared"]
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
        self._tutorial_notify("phase_result_applied", {"events": events, "phase": self.phase, "turn": self.turn})

    def _handle_game_over(self, payload):
        # Game-over event will be in the PHASE_RESULT events; transition scene
        self.app.set_scene("results")

    def _handle_error(self, payload):
        self.event_log.append(f"Error: {payload.get('message', '?')}")
        self.event_log_meta.append({"factions": [], "spans": []})

    def _can_vote_kick(self, player: dict) -> bool:
        my_spirit_id = self.app.my_spirit_id
        if not my_spirit_id or my_spirit_id == player.get("spirit_id"):
            return False
        if float(player.get("disconnected_seconds", 0)) < 30.0:
            return False
        if my_spirit_id in set(player.get("kick_voters", [])):
            return False
        return my_spirit_id in set(player.get("required_voters", []))

    def _rebuild_disconnect_kick_buttons(self) -> None:
        self.disconnect_kick_buttons = {}
        if not self.disconnected_players:
            return
        panel_rect = self._disconnect_panel_rect()
        row_y = panel_rect.y + 34
        for player in self.disconnected_players:
            button = Button(
                pygame.Rect(panel_rect.right - 106, row_y + 4, 92, 28),
                "Vote Kick",
                (120, 76, 60),
            )
            self.disconnect_kick_buttons[player["spirit_id"]] = button
            row_y += 42

    def _disconnect_panel_rect(self) -> pygame.Rect:
        panel_width = 280
        panel_height = 42 + 42 * max(1, len(self.disconnected_players))
        return pygame.Rect(SCREEN_WIDTH - panel_width - 16, 52, panel_width, panel_height)

    def _advance_disconnect_presence(self, dt: float) -> None:
        for player in self.disconnected_players:
            player["disconnected_seconds"] = float(player.get("disconnected_seconds", 0.0)) + dt

    def _setup_change_choice_ui(self):
        self.phase_controller._setup_change_choice_ui()

    def _setup_spoils_choice_ui(self):
        self.phase_controller._setup_spoils_choice_ui()

    def _setup_spoils_change_choice_ui(self):
        self.phase_controller._setup_spoils_change_choice_ui()

    def _setup_ejection_choice_ui(self):
        self.phase_controller._setup_ejection_choice_ui()

    def _setup_expand_choice_ui(self):
        self.phase_controller._setup_expand_choice_ui()

    def _setup_respawn_choice_ui(self):
        self.phase_controller._setup_respawn_choice_ui()

    def _setup_winner_choice_ui(self):
        self.phase_controller._setup_winner_choice_ui()

    def _do_submit_winner_choice(self):
        """Send winner choices to the server and reset state."""
        choices = []
        for wc in self.winner_choice_wars:
            sel = self.winner_selections.get(wc["war_id"])
            if sel is None:
                return
            choices.append({"war_id": wc["war_id"], "winner": sel})
        self.app.network.send(C2S.SUBMIT_WINNER_CHOICE, {"choices": choices})
        self._tutorial_notify("winner_choice_submitted", {"choices": choices})
        self.winner_choice_wars = []
        self.winner_selections = {}
        self.winner_choice_buttons = []
        self.has_submitted = True

    def _setup_spoils_expand_choice_ui(self):
        self.phase_controller._setup_spoils_expand_choice_ui()

    def _refresh_spoils_expand_hex_set(self):
        """Rebuild the selectable hex set for the currently displayed expand choice."""
        self.spoils_expand_selectable_hexes = set()
        if not self.spoils_expand_choices:
            return
        idx = min(self.spoils_expand_display_index, len(self.spoils_expand_choices) - 1)
        entry = self.spoils_expand_choices[idx]
        for h in entry.get("available_hexes", []):
            self.spoils_expand_selectable_hexes.add((h["q"], h["r"]))

    def _do_submit_spoils_expand_choice(self):
        """Send spoils expand target choices to the server and reset state."""
        if any(s is None for s in self.spoils_expand_selections):
            return
        choices = [{"hex": {"q": sel[0], "r": sel[1]}} for sel in self.spoils_expand_selections]
        self.app.network.send(C2S.SUBMIT_SPOILS_EXPAND_CHOICE, {"choices": choices})
        self._tutorial_notify("spoils_expand_submitted", {"choices": choices})
        self.spoils_expand_choices = []
        self.spoils_expand_selections = []
        self.spoils_expand_selectable_hexes = set()
        self.selected_hex = None
        self.has_submitted = True

    def _setup_phase_ui(self):
        """Build UI elements for the current phase."""
        self.phase_controller.setup_phase_ui()

    def _setup_main_phase_ui(self, action: str):
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

    def _get_faction_race(self, faction_id: str) -> str:
        fdata = self.factions.get(faction_id, {})
        if isinstance(fdata, dict):
            return fdata.get("race", "")
        return ""

    def _get_affinity_priority(self, spirit_id: str, faction_id: str) -> tuple[int, str | None]:
        spirit = self.spirits.get(spirit_id, {})
        faction_race = self._get_faction_race(faction_id)
        if spirit.get("habitat_affinity") == faction_id:
            return 2, "Habitat"
        if faction_race and spirit.get("race_affinity") == faction_race:
            return 1, "Race"
        return 0, None

    def _get_stronger_affinity_spirits(self, faction_id: str) -> list[str]:
        my_id = self.app.my_spirit_id
        my_priority, _ = self._get_affinity_priority(my_id, faction_id)
        stronger: list[tuple[int, str]] = []
        for spirit_id, spirit in self.spirits.items():
            if spirit_id == my_id:
                continue
            other_priority, _ = self._get_affinity_priority(spirit_id, faction_id)
            if other_priority > my_priority:
                stronger.append((other_priority, spirit.get("name", spirit_id[:6])))
        stronger.sort(key=lambda item: (-item[0], item[1]))
        return [name for _, name in stronger]

    def _build_guidance_summary_lines(self, faction_id: str) -> list[str]:
        fdata = self.factions.get(faction_id, {})
        worship_id = fdata.get("worship_spirit") if isinstance(fdata, dict) else None
        my_id = self.app.my_spirit_id
        lines: list[str] = []
        for name in self._get_stronger_affinity_spirits(faction_id)[:2]:
            lines.append(f"{name} has more Affinity")
        if worship_id == my_id:
            lines.append("Will still Worship you")
        elif worship_id:
            worship_name = self.spirits.get(worship_id, {}).get("name", worship_id[:6])
            my_idols = self._count_spirit_idols_in_faction(my_id, faction_id)
            their_idols = self._count_spirit_idols_in_faction(worship_id, faction_id)
            if my_idols >= their_idols:
                lines.append(f"Will usurp Worship from {worship_name}")
            else:
                lines.append(f"Will still Worship {worship_name}")
        else:
            lines.append("Will begin Worshipping you")
        return lines

    def _wrap_guidance_summary_lines(self, lines: list[str], max_width: int) -> list[str]:
        """Wrap semantic guidance summary lines to the available box width."""
        wrapped: list[str] = []
        for line in lines:
            split = _wrap_text(line, self.small_font, max_width)
            if split:
                wrapped.extend(split)
            else:
                wrapped.append("")
        return wrapped

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
            lines.append("This faction already worships you;")
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
        lines.append("")
        stronger = self._get_stronger_affinity_spirits(faction_id)
        if stronger:
            lines.append("Affinity priority over you:")
            for name in stronger:
                lines.append(name)
        else:
            lines.append("No other Spirit has Affinity priority over you.")
        return "\n".join(lines)

    def _build_faction_buttons(self):
        available = list(self.phase_options.get("available_factions", []))
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
        summary_top = _BTN_START_Y + max(0, len(all_factions)) * _BTN_STEP_Y + 4
        self.guidance_summary_rect = pygame.Rect(
            max(12, _GUIDANCE_BTN_X - 6),
            summary_top,
            _BTN_W + 12,
            84,
        )

    def _build_idol_buttons(self):
        idol_tooltips = {
            IdolType.BATTLE: f"{BATTLE_IDOL_VP} VP for each war won\nby the Worshipping Faction",
            IdolType.AFFLUENCE: f"{AFFLUENCE_IDOL_VP} VP for each gold gained\nby the Worshipping Faction\n(halved in Era 2)",
            IdolType.SPREAD: f"{SPREAD_IDOL_VP} VP for each territory gained\nby the Worshipping Faction",
        }
        summary_bottom = self.guidance_summary_rect.bottom if self.guidance_summary_rect else (_BTN_START_Y + 180)
        idol_title_y = summary_bottom + 10
        idol_start_y = idol_title_y + 30
        self.idol_buttons = []
        self.idol_drag_sources = []
        icon_size = 52
        gap = 10
        total_w = len(list(IdolType)) * icon_size + (len(list(IdolType)) - 1) * gap
        start_x = _GUIDANCE_CENTER_X - total_w // 2
        for i, it in enumerate(IdolType):
            colors = {
                IdolType.BATTLE: (130, 50, 50),
                IdolType.AFFLUENCE: (130, 120, 30),
                IdolType.SPREAD: (50, 120, 50),
            }
            rect = pygame.Rect(start_x + i * (icon_size + gap), idol_start_y, icon_size, icon_size)
            btn = Button(
                rect,
                it.value.title(), colors.get(it, (80, 80, 80)),
                tooltip=idol_tooltips.get(it),
                tooltip_always=True,
            )
            self.idol_buttons.append(btn)
            self.idol_drag_sources.append({"idol_type": it, "rect": rect})
        # Set up idol title rect (same center x as guidance)
        title_w = 130
        self.idol_title_rect = pygame.Rect(
            _GUIDANCE_CENTER_X - title_w // 2, idol_title_y, title_w, 22
        )

    @staticmethod
    def _build_arc_control(start_pos: tuple[float, float], end_pos: tuple[float, float],
                           height_scale: float = 0.22) -> tuple[float, float]:
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        distance = max(1.0, math.hypot(dx, dy))
        mid_x = (start_pos[0] + end_pos[0]) / 2
        mid_y = (start_pos[1] + end_pos[1]) / 2
        nx = -dy / distance
        ny = dx / distance
        lift = distance * height_scale
        return mid_x + nx * lift, mid_y + ny * lift - lift * 0.45

    def _get_spirit_hud_anchor(self, spirit_id: str) -> tuple[float, float]:
        vp_pos = self.ui_renderer.vp_positions.get(spirit_id)
        if vp_pos:
            return float(vp_pos[0]), float(vp_pos[1]) + 10.0
        sorted_spirits = list(sorted(self.spirits.keys()))
        idx = sorted_spirits.index(spirit_id) if spirit_id in sorted_spirits else 0
        return 120.0 + idx * 90.0, 24.0

    def _get_faction_territory_coords(self, faction_id: str) -> list[tuple[int, int]]:
        fdata = self.factions.get(faction_id, {})
        territories = fdata.get("territories", []) if isinstance(fdata, dict) else []
        coords: list[tuple[int, int]] = []
        for entry in territories:
            if isinstance(entry, dict) and "q" in entry and "r" in entry:
                coords.append((entry["q"], entry["r"]))
        return coords

    def _get_faction_central_hex(self, faction_id: str) -> tuple[int, int] | None:
        coords = self._get_faction_territory_coords(faction_id)
        if not coords:
            return None
        avg_q = sum(q for q, _ in coords) / len(coords)
        avg_r = sum(r for _, r in coords) / len(coords)
        return min(coords, key=lambda item: (item[0] - avg_q) ** 2 + (item[1] - avg_r) ** 2)

    def _queue_vagrant_resolution_animations(self, events: list[dict]) -> None:
        idol_events = [e for e in events if e.get("type") == "idol_placed"]
        guided_by_faction = {
            e.get("faction"): e.get("spirit")
            for e in events
            if e.get("type") == "guided" and e.get("faction") and e.get("spirit")
        }
        contested_by_faction = {
            e.get("faction"): e
            for e in events
            if e.get("type") == "guide_contested" and e.get("faction")
        }
        spirit_index_map = {sid: i for i, sid in enumerate(sorted(self.spirits.keys()))}

        for event in idol_events:
            spirit_id = event.get("spirit")
            hex_data = event.get("hex", {})
            idol_type_str = event.get("idol_type")
            if not spirit_id or "q" not in hex_data or "r" not in hex_data or not idol_type_str:
                continue
            try:
                idol_type = IdolType(idol_type_str)
            except ValueError:
                continue
            start_pos = self._get_spirit_hud_anchor(spirit_id)
            player_idx = spirit_index_map.get(spirit_id, 0)
            end_pos = self.hex_renderer.get_idol_slot_screen(
                hex_data["q"], hex_data["r"], player_idx,
                self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
            )
            self.animation.add_effect_animation(TokenArcAnimation(
                start_pos=start_pos,
                end_pos=end_pos,
                control_pos=self._build_arc_control(start_pos, end_pos),
                token_kind="idol",
                token_data={
                    "idol_type": idol_type,
                    "radius": self.hex_renderer.get_idol_radius(),
                },
                delay=0.0,
                duration=1.0,
            ))

        if idol_events and self._display_idols is not None:
            self._pending_idol_reveal_delay = 1.0

        guidance_travel_delay = 1.0 if idol_events else 0.0
        travel_duration = 1.0
        contest_duration = 1.0
        split_duration = 0.5
        target_factions = sorted(set(guided_by_faction.keys()) | set(contested_by_faction.keys()))
        for faction_id in target_factions:
            central_hex = self._get_faction_central_hex(faction_id)
            if not central_hex:
                continue
            central_slot_positions: dict[str, tuple[int, int]] = {}
            winner_id = guided_by_faction.get(faction_id)
            contest_event = contested_by_faction.get(faction_id)
            contenders: list[str] = []
            if contest_event:
                contenders.extend(contest_event.get("spirits", []))
            if winner_id and winner_id not in contenders:
                contenders.append(winner_id)
            if not contenders and winner_id:
                contenders = [winner_id]
            for spirit_id in contenders:
                player_idx = spirit_index_map.get(spirit_id, 0)
                end_pos = self.hex_renderer.get_idol_slot_screen(
                    central_hex[0], central_hex[1], player_idx,
                    self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
                )
                central_slot_positions[spirit_id] = end_pos
                start_pos = self._get_spirit_hud_anchor(spirit_id)
                self.animation.add_effect_animation(TokenArcAnimation(
                    start_pos=start_pos,
                    end_pos=end_pos,
                    control_pos=self._build_arc_control(start_pos, end_pos, height_scale=0.16),
                    token_kind="spirit",
                    token_data={
                        "spirit_idx": player_idx,
                        "screen_radius": self.hex_renderer.hex_size,
                        "color": (0, 0, 0),
                    },
                    delay=guidance_travel_delay,
                    duration=travel_duration,
                ))

            if contest_event:
                fading_ids = list(contest_event.get("spirits", []))
                for spirit_id in fading_ids:
                    self.animation.add_effect_animation(TokenShakeFadeAnimation(
                        center_pos=central_slot_positions[spirit_id],
                        token_kind="spirit",
                        token_data={
                            "spirit_idx": spirit_index_map.get(spirit_id, 0),
                            "screen_radius": self.hex_renderer.hex_size,
                            "color": (0, 0, 0),
                        },
                        delay=guidance_travel_delay + travel_duration,
                        duration=contest_duration,
                    ))
                if winner_id and winner_id in central_slot_positions:
                    self.animation.add_effect_animation(TokenSplitAnimation(
                        start_pos=central_slot_positions[winner_id],
                        end_pos=central_slot_positions[winner_id],
                        token_kind="spirit",
                        token_data={
                            "spirit_idx": spirit_index_map.get(winner_id, 0),
                            "screen_radius": self.hex_renderer.hex_size,
                            "color": (0, 0, 0),
                        },
                        delay=guidance_travel_delay + travel_duration,
                        duration=contest_duration,
                    ))

            if winner_id:
                split_start_delay = guidance_travel_delay + travel_duration
                if contest_event:
                    split_start_delay += contest_duration
                start_pos = central_slot_positions.get(winner_id)
                if start_pos is None:
                    continue
                for q, r in self._get_faction_territory_coords(faction_id):
                    end_pos = self.input_handler.world_to_screen(
                        *axial_to_pixel(q, r, HEX_SIZE),
                        SCREEN_WIDTH, SCREEN_HEIGHT,
                    )
                    self.animation.add_effect_animation(TokenSplitAnimation(
                        start_pos=start_pos,
                        end_pos=end_pos,
                        token_kind="spirit",
                        token_data={
                            "spirit_idx": spirit_index_map.get(winner_id, 0),
                            "screen_radius": self.hex_renderer.hex_size,
                            "color": (0, 0, 0),
                        },
                        delay=split_start_delay,
                        duration=split_duration,
                    ))

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
            rects = self._calc_left_choice_card_rects(len(self.agenda_hand))
            hotspots = self.ui_renderer.get_card_modifier_hotspots(
                self.agenda_hand,
                rects[0].x if rects else 20,
                rects[0].y if rects else _CHOICE_CARD_Y,
                modifiers=modifiers,
                vertical=True,
            )
            for i, rect in enumerate(rects):
                if rect.collidepoint(mx, my):
                    for plus_rect in hotspots[i]:
                        if plus_rect.collidepoint(mx, my):
                            atype = self.agenda_hand[i].get("agenda_type", "")
                            self.hovered_card_tooltip = build_modifier_tooltip(atype)
                            self.hovered_card_rect = plus_rect
                            return
                    atype = self.agenda_hand[i].get("agenda_type", "")
                    self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers)
                    self.hovered_card_rect = rect
                    return

        if self.change_cards:
            change_hand = self._build_change_hand()
            for i, rect in enumerate(self._calc_left_choice_card_rects(len(change_hand))):
                if rect.collidepoint(mx, my):
                    self.hovered_card_tooltip = change_hand[i].get("tooltip", build_modifier_tooltip(self.change_cards[i]))
                    self.hovered_card_rect = rect
                    return

        if self.spoils_entries:
            for panel_idx, rects in enumerate(self.spoils_card_rects):
                entry = self.spoils_entries[panel_idx]
                for card_idx, rect in enumerate(rects):
                    if rect.collidepoint(mx, my):
                        atype = entry.cards[card_idx]
                        self.hovered_card_tooltip = build_agenda_tooltip(atype, modifiers, is_spoils=True)
                        self.hovered_card_rect = rect
                        return

        if self.spoils_change_entries:
            for panel_idx, rects in enumerate(self.spoils_card_rects):
                entry = self.spoils_change_entries[panel_idx]
                for card_idx, rect in enumerate(rects):
                    if rect.collidepoint(mx, my):
                        self.hovered_card_tooltip = build_modifier_tooltip(entry.cards[card_idx])
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
        self.hovered_panel_shaping = None
        for card_name, rect in self.ui_renderer.panel_shaping_rects.items():
            if rect.collidepoint(mx, my):
                self.hovered_panel_shaping = card_name
                break

    def _update_guidance_summary_hover(self, mouse_pos):
        """Check whether the guidance summary keywords are hovered."""
        self.hovered_guidance_summary_keyword = None
        mx, my = mouse_pos
        for keyword, rects in self.guidance_summary_keyword_rects.items():
            for rect in rects:
                if rect.collidepoint(mx, my):
                    self.hovered_guidance_summary_keyword = keyword
                    return

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

    def _update_clickable_faction_hover(self, mouse_pos):
        self.hovered_text_faction_id = None
        self.hovered_text_faction_rect = None
        self.hovered_event_log_tooltip = None
        for fid, rect in self.ribbon_faction_rects.items():
            if rect.collidepoint(mouse_pos):
                self.hovered_text_faction_id = fid
                self.hovered_text_faction_rect = rect
                return
        for tooltip, rect in self.ui_renderer.event_log_tooltip_rects:
            if rect.collidepoint(mouse_pos):
                self.hovered_event_log_tooltip = (tooltip, rect)
                return
        for rect_map in (
            self.ui_renderer.panel_war_opponent_rects,
            self._spirit_panel_rects.get("worship", {}),
            self._persistent_spirit_panel_rects.get("worship", {}),
        ):
            for fid, rect in rect_map.items():
                if rect.collidepoint(mouse_pos):
                    self.hovered_text_faction_id = fid
                    self.hovered_text_faction_rect = rect
                    return
        for rect in self.ejection_faction_rects:
            if rect.collidepoint(mouse_pos):
                self.hovered_text_faction_id = self.ejection_faction
                self.hovered_text_faction_rect = rect
                return
        for fid, rects in self.ui_renderer.event_log_faction_rects.items():
            for rect in rects:
                if rect.collidepoint(mouse_pos):
                    self.hovered_text_faction_id = fid
                    self.hovered_text_faction_rect = rect
                    return

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

    def _try_pin_hovered_tooltip(self, mouse_pos) -> bool:
        """Pin the currently active tooltip from the registry as a popup.

        Returns True if a tooltip was successfully pinned, False if nothing was active.
        """
        return self.tooltip_registry.try_pin(self.popup_manager, self.small_font, SCREEN_WIDTH)

    def _count_idol_vp_for_faction(self, faction_id: str):
        """Count total VP per event type from idols in a faction's territory.

        Returns (battle_vp, sprawl_vp, affluence_vp) totals.
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
            affluence_count * AFFLUENCE_IDOL_VP * (0.5 if self.current_era == "era_2" else 1.0),
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

    def _build_worship_tooltip(self, faction_id: str, worship_id: str | None) -> str:
        """Build tooltip text for a faction's Worship status."""
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

    def _build_worship_panel_tooltip(self, faction_id: str) -> str:
        """Build tooltip text for Worshipping hover."""
        return self._build_worship_tooltip(faction_id, self.ui_renderer.panel_worship_spirit_id)

    def _build_spirit_worship_tooltip(self, faction_id: str, spirit_id: str) -> str:
        """Build tooltip for a faction worshipping a spirit in the spirit panel."""
        battle_vp, spread_vp, affluence_vp = self._count_idol_vp_for_faction(faction_id)
        faction_name = faction_full_name(faction_id)

        def _fmt(v):
            return f"{v:g}"

        if spirit_id == self.app.my_spirit_id:
            return (
                f"The {faction_name} faction worships you. Each turn it gives you "
                f"{_fmt(battle_vp)} VP per battle won, "
                f"{_fmt(spread_vp)} VP per territory gained, and "
                f"{_fmt(affluence_vp)} VP per gold earned."
            )
        else:
            spirit_name = self.spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            return (
                f"The {faction_name} faction worships {spirit_name}. Each turn it gives them "
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
                _ERA2_CYCLE_TOOLTIP if self.current_era == "era_2" else _INFLUENCE_TOOLTIP,
                _GUIDANCE_HOVER_REGIONS, r.centerx, anchor, below=below,
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
        etype = log_event(
            event,
            self.event_log,
            self.event_log_meta,
            self.spirits,
            self.app.my_spirit_id,
            self.faction_agendas_this_turn,
        )
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
            self._tutorial_notify("guide_contested", event)
        elif etype == "war_declared":
            self._tutorial_notify("war_declared", event)
        elif etype == "faction_respawned":
            self._tutorial_notify("faction_respawned", event)

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
        verb = "randomly plays" if play_info["source"] == "random" else "plays"
        subject = f"The {fname} faction"
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
                return f"{subject} {verb} {agenda}{guided_part} for {gold} gold and +{regard} regard with {others}."
            return f"{subject} {verb} {agenda}{guided_part} for {gold} gold."

        if etype == "steal":
            gold = resolution_event.get("gold_gained", 0)
            penalty = resolution_event.get("regard_penalty", 1)
            neighbors = resolution_event.get("neighbors", [])
            if neighbors:
                others = self._format_faction_list(neighbors)
                return f"{subject} {verb} {agenda}{guided_part} for {gold} gold and -{penalty} regard with {others}."
            return f"{subject} {verb} {agenda}{guided_part} for {gold} gold."

        if etype == "expand":
            cost = resolution_event.get("cost", 0)
            return f"{subject} {verb} {agenda}{guided_part} and expands territory for {cost} gold."

        if etype == "expand_failed":
            gained = resolution_event.get("gold_gained", 0)
            return f"{subject} {verb} {agenda}{guided_part} but couldn't expand and gained {gained} gold."

        if etype == "change":
            mod = resolution_event.get("modifier", "?")
            return f"{subject} {verb} {agenda}{guided_part} and upgrades {mod}."

        return f"{subject} {verb} {agenda}{guided_part}."

    def _build_consolidated_agenda_meta(self, play_info: dict, resolution_event: dict) -> dict:
        factions: list[str] = []
        faction_id = play_info.get("faction")
        if faction_id:
            factions.append(faction_id)
        for field in ("co_traders", "neighbors"):
            for fid in resolution_event.get(field, []):
                if fid and fid not in factions:
                    factions.append(fid)
        return {"factions": factions, "spans": []}

    def _reset_event_log_cycle(self) -> None:
        self._event_log_cycle_log_idx = None
        self._event_log_cycle_target_index = 0

    def _get_clicked_event_log_index(self, pos: tuple[int, int]) -> int | None:
        for rect, log_idx in self.ui_renderer.event_log_line_rects:
            if rect.collidepoint(pos):
                return log_idx
        return None

    def _handle_event_log_click(self, log_idx: int) -> None:
        self.highlighted_log_index = log_idx
        meta = self.event_log_meta[log_idx] if 0 <= log_idx < len(self.event_log_meta) else {}
        targets = list(meta.get("factions", []))
        if not targets:
            return
        if self._event_log_cycle_log_idx != log_idx:
            self._event_log_cycle_log_idx = log_idx
            self._event_log_cycle_target_index = 0
        else:
            self._event_log_cycle_target_index = (self._event_log_cycle_target_index + 1) % len(targets)
        self._select_faction_from_text(targets[self._event_log_cycle_target_index])

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
                self.event_log_meta.append(self._build_consolidated_agenda_meta(pending, event))
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
        if self._pending_idol_reveal_delay is not None:
            self._pending_idol_reveal_delay -= dt
            if self._pending_idol_reveal_delay <= 0:
                import copy
                self._display_idols = copy.deepcopy(self.all_idols)
                self._pending_idol_reveal_delay = None
        if self.status_banner_timer > 0.0:
            self.status_banner_timer = max(0.0, self.status_banner_timer - dt)
            if self.status_banner_timer == 0.0:
                self.status_banner_message = None
        if self.disconnected_players:
            self._advance_disconnect_presence(dt)
            self._rebuild_disconnect_kick_buttons()
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
        runtime = self._tutorial_runtime()
        if runtime:
            runtime.update(dt)
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
            for panel_rect in self.spoils_panel_rects:
                rects.append((panel_rect, _WEIGHT_NON_TEXT))
            for panel_cards in self.spoils_card_rects:
                for cr in panel_cards:
                    rects.append((cr, _WEIGHT_NON_TEXT))
        if self.spoils_change_entries:
            for panel_rect in self.spoils_panel_rects:
                rects.append((panel_rect, _WEIGHT_NON_TEXT))
            for panel_cards in self.spoils_card_rects:
                for cr in panel_cards:
                    rects.append((cr, _WEIGHT_NON_TEXT))
        if self.spoils_help_rect:
            rects.append((self.spoils_help_rect, _WEIGHT_TEXT))

        set_ui_rects(rects)

    def render(self, screen: pygame.Surface):
        screen.fill(theme.BG_SCREEN)

        # Parse idol data for rendering
        render_idols = []
        for idol_data in self.display_idols:
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
        war_source = self.display_wars
        if self._display_wars is not None and not self.wars and not self.orchestrator.should_hold_display_wars(self.phase):
            war_source = self.wars
        for w in war_source:
            if isinstance(w, dict):
                war_obj = type('War', (), {
                    'war_id': w.get('war_id'),
                    'faction_a': w.get('faction_a', ''),
                    'faction_b': w.get('faction_b', ''),
                    'battleground_a': w.get('battleground_a'),
                    'battleground_b': w.get('battleground_b'),
                    'resolve_turn': w.get('resolve_turn', 0),
                    'declared_turn': w.get('declared_turn', 0),
                    'is_staged': w.get('is_staged', False),
                })()
                render_wars.append(war_obj)
            else:
                render_wars.append(w)

        # Draw hex grid (use display state if available)
        hex_own = self.display_hex_ownership
        highlight = None

        # Spoils expand choice: highlight selectable hexes for current entry
        if self.phase == SubPhase.SPOILS_EXPAND_CHOICE and self.spoils_expand_selectable_hexes:
            highlight = self.spoils_expand_selectable_hexes
        # Expand choice: highlight reachable neutral hexes
        elif self.phase == SubPhase.EXPAND_CHOICE and self.expand_choice_hexes:
            highlight = self.expand_choice_hexes
        # Respawn choice: highlight all neutral hexes
        elif self.phase == SubPhase.RESPAWN_CHOICE and self.respawn_choice_hexes:
            highlight = self.respawn_choice_hexes

        # Build spirit_id -> player_index mapping (sorted for stability)
        spirit_index_map = {
            sid: i for i, sid in enumerate(sorted(self.spirits.keys()))
        }

        # Compute preview idol (post-confirm or pre-confirm)
        render_preview_idol = self.preview_idol
        if not render_preview_idol and self.selected_idol_type and self.selected_hex:
            render_preview_idol = (
                self.selected_idol_type,
                self.selected_hex[0],
                self.selected_hex[1],
                spirit_index_map.get(self.app.my_spirit_id, 0),
            )

        # Build faction_id -> spirit_index for guidance and worship indicators
        faction_spirit_index = {}
        faction_worship = {}
        disp_factions = self.display_factions
        for faction_id, fdata in disp_factions.items():
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
            selected_hex=None if self.phase == Phase.VAGRANT_PHASE.value and self.current_era == "era_1" else self.selected_hex,
            selected_hexes=None,
            highlight_hexes=highlight,
            selected_faction_outline=self.selected_faction,
            spirit_index_map=spirit_index_map,
            preview_idol=render_preview_idol,
            faction_spirit_index=faction_spirit_index,
            faction_worship=faction_worship,
            highlight_spirit_id=self.spirit_panel_spirit_id,
            highlighted_war_pairs=self._get_highlighted_war_pairs(),
        )

        # Draw world-space effect animations (border text + arrows)
        self.orchestrator.render_effect_animations(screen, screen_space_only=False, small_font=self.small_font)

        # Draw HUD
        self.ui_renderer.draw_hud(screen, self.phase, self.turn,
                                  self.spirits, self.app.my_spirit_id,
                                  era=self.current_era, vp_target=self.vp_target)

        # Compute preview guidance dict
        preview_guid_dict = None
        preview_fid = self.preview_guidance or self.selected_faction
        if preview_fid:
            my_name = self.spirits.get(self.app.my_spirit_id, {}).get("name", "?")
            preview_guid_dict = {preview_fid: my_name}

        # Draw faction overview strip — always use live factions so worship/pool
        # stay current even when _display_factions is stale during AI-only games.
        # Gold is overridden with tweened values to animate smoothly.
        disp_factions = self.display_factions
        gold_overrides: dict[str, int] = {}
        for fid in (self.faction_order or self.factions):
            key = f"gold_display_{fid}"
            if key in self.animation.tweens:
                gold_overrides[fid] = int(self.animation.get_tween_value(key))
            elif self._display_factions is not None:
                fd = self._display_factions.get(fid, {})
                gold_overrides[fid] = (fd.get("gold", 0) if isinstance(fd, dict)
                                       else getattr(fd, "gold", 0))
        animated_agenda_factions = self.animation.get_persistent_agenda_factions()
        self.agenda_label_rects, self.pool_icon_rects, self.ribbon_war_rects, self.ribbon_worship_rects = self.ui_renderer.draw_faction_overview(
            screen, disp_factions, self.faction_agendas_this_turn,
            wars=render_wars,
            faction_spoils_agendas=self.faction_spoils_agendas_this_turn,
            spirits=self.spirits,
            preview_guidance=preview_guid_dict,
            animated_agenda_factions=animated_agenda_factions,
            faction_order=self.faction_order,
            gold_overrides=gold_overrides,
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
            spirit = self.display_spirits.get(self.spirit_panel_spirit_id, {})
            fills = self._get_influence_fills(self.spirit_panel_spirit_id)
            self._spirit_panel_rects = self.ui_renderer.draw_spirit_panel(
                screen, spirit, self.display_factions, self.display_idols,
                self.display_hex_ownership, _FACTION_PANEL_X, 102, _PANEL_W,
                my_spirit_id=self.spirit_panel_spirit_id,
                circle_fills=fills,
                spirit_index_map=spirit_index_map,
                max_height=_FACTION_PANEL_MAX_H,
                era=self.current_era,
            )
            # Clear faction panel rects
            self.ui_renderer.faction_panel_rect = None
            self.ui_renderer.panel_guided_rect = None
            self.ui_renderer.panel_worship_rect = None
            self.ui_renderer.panel_war_rect = None
        else:
            # Faction panel (top of right column)
            pf = self.panel_faction
            real_faction_data = self.display_factions.get(pf) if pf else None
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
                    all_factions=self.display_factions,
                    faction_order=self.faction_order,
                    scroll_offset=self.faction_panel_scroll_offset,
                    max_height=_cur_faction_panel_h,
                )
            else:
                self.ui_renderer.faction_panel_rect = None
                self.ui_renderer.panel_guided_rect = None
                self.ui_renderer.panel_worship_rect = None
                self.ui_renderer.panel_war_rect = None
                self.ui_renderer.panel_shaping_rects = {}
            # Clear spirit panel rects
            self._spirit_panel_rects = {}

        # Draw persistent spirit stats panel (middle of right column)
        my_spirit = self.display_spirits.get(self.app.my_spirit_id, {})
        if my_spirit:
            fills = self._get_influence_fills(self.app.my_spirit_id)
            self._persistent_spirit_panel_rects = self.ui_renderer.draw_spirit_panel(
                screen, my_spirit, self.display_factions, self.display_idols,
                self.display_hex_ownership, _FACTION_PANEL_X, _spirit_panel_y, _PANEL_W,
                my_spirit_id=self.app.my_spirit_id,
                circle_fills=fills,
                spirit_index_map=spirit_index_map,
                max_height=_SPIRIT_PANEL_MAX_H,
                scroll_offset=self.persistent_spirit_panel_scroll_offset,
                era=self.current_era,
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
            screen, self.event_log, self.event_log_meta,
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
            self._render_agenda_ui(screen)
        elif self.phase in (SubPhase.CHANGE_CHOICE, SubPhase.RESTRAIN_CHOICE,
                            SubPhase.SHAPING_CHOICE, SubPhase.ADAPTATION_CHOICE):
            self._render_change_ui(screen)
        elif self.phase == SubPhase.EJECTION_CHOICE:
            self._render_ejection_ui(screen)
        elif self.phase == SubPhase.SPOILS_CHOICE:
            self._render_spoils_ui(screen)
        elif self.phase == SubPhase.SPOILS_CHANGE_CHOICE:
            self._render_spoils_change_ui(screen)
        elif self.phase == SubPhase.WINNER_CHOICE:
            self._render_winner_choice_ui(screen)
        elif self.phase == SubPhase.SPOILS_EXPAND_CHOICE:
            self._render_spoils_expand_choice_ui(screen)
        elif self.phase == SubPhase.EXPAND_CHOICE:
            self._render_expand_choice_ui(screen)
        elif self.phase == SubPhase.RESPAWN_CHOICE:
            self._render_respawn_choice_ui(screen)
        elif self.phase == SubPhase.BATTLEGROUND_CHOICE:
            self._render_battleground_choice_ui(screen)
        elif self.phase == SubPhase.WAR_SUPPORT_CHOICE:
            self._render_war_support_choice_ui(screen)

        # Register UI rects for tooltip placement scoring
        self._register_ui_rects_for_tooltips()

        # Rebuilt only while idol hover tooltip is actively rendered.
        self.idol_tooltip_spirit_rects = []

        # Agenda hover tooltips
        if self.hovered_card_tooltip and self.hovered_card_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self.hovered_card_tooltip, _GUIDANCE_HOVER_REGIONS,
                self.hovered_card_rect.centerx, self.hovered_card_rect.top,
                avoid_rects=[self.hovered_card_rect],
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
                    avoid_rects=[self.hovered_agenda_label_rect],
                ))
        elif self.hovered_anim_tooltip and self.hovered_anim_rect:
            self.tooltip_registry.offer(TooltipDescriptor(
                self.hovered_anim_tooltip, _GUIDANCE_HOVER_REGIONS,
                self.hovered_anim_rect.centerx,
                self.hovered_anim_rect.bottom, below=True,
                avoid_rects=[self.hovered_anim_rect],
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
        elif self.hovered_panel_shaping:
            info = get_era_card_info(self.hovered_panel_shaping) or {}
            rect = self.ui_renderer.panel_shaping_rects.get(self.hovered_panel_shaping)
            if rect:
                self.tooltip_registry.offer(TooltipDescriptor(
                    info.get("tooltip", info.get("body", self.hovered_panel_shaping)),
                    _GUIDANCE_HOVER_REGIONS,
                    rect.centerx, rect.bottom, below=True,
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
        mx, my = pygame.mouse.get_pos()
        for rects in (self._spirit_panel_rects, self._persistent_spirit_panel_rects):
            for card_name, rect in rects.get("adaptation", {}).items():
                if rect.collidepoint(mx, my):
                    info = get_era_card_info(card_name) or {}
                    self.tooltip_registry.offer(TooltipDescriptor(
                        info.get("tooltip", info.get("body", card_name)),
                        _GUIDANCE_HOVER_REGIONS,
                        rect.centerx, rect.bottom, below=True,
                    ))
                    break

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
        if self.hovered_text_faction_id and self.hovered_text_faction_rect:
            faction_data = self.display_factions.get(self.hovered_text_faction_id, {})
            worship_id = faction_data.get("worship_spirit") if isinstance(faction_data, dict) else None
            self.tooltip_registry.offer(TooltipDescriptor(
                self._build_worship_tooltip(self.hovered_text_faction_id, worship_id),
                _GUIDANCE_HOVER_REGIONS,
                self.hovered_text_faction_rect.centerx,
                self.hovered_text_faction_rect.bottom,
                below=True,
            ))
        if self.hovered_event_log_tooltip:
            tooltip, rect = self.hovered_event_log_tooltip
            self.tooltip_registry.offer(TooltipDescriptor(
                tooltip,
                _GUIDANCE_HOVER_REGIONS,
                rect.centerx,
                rect.top,
            ))

        if self.spoils_help_rect and self.spoils_help_rect.collidepoint(pygame.mouse.get_pos()):
            self.tooltip_registry.offer(TooltipDescriptor(
                _SPOILS_TOOLTIP,
                _GUIDANCE_HOVER_REGIONS,
                self.spoils_help_rect.centerx,
                self.spoils_help_rect.bottom,
                below=True,
                avoid_rects=[self.spoils_help_rect],
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

        if self.status_banner_message and self.status_banner_timer > 0.0:
            self._render_status_banner(screen)
        if self.disconnected_players:
            self._render_disconnect_panel(screen)

        # Final scores panel (drawn after everything else so it's always visible)
        if self.game_over:
            self._render_game_over_panel(screen)

        runtime = self._tutorial_runtime()
        if runtime:
            runtime.render_overlay(screen, self.font, self.small_font)

        # Render the single active tooltip (suppressed when popups are open)
        self.tooltip_registry.render(screen, self.small_font, self.popup_manager)

        # Pinned popups (drawn on top of everything)
        self.popup_manager.render(screen, self.small_font)

        # In-game menu button and dropdown (always on top)
        self._render_ingame_menu(screen)

    def _render_status_banner(self, screen: pygame.Surface) -> None:
        if not self.status_banner_message:
            return
        surf = self.small_font.render(self.status_banner_message, True, (245, 232, 190))
        rect = surf.get_rect()
        bg_rect = pygame.Rect(0, 0, rect.width + 28, rect.height + 12)
        bg_rect.midtop = (SCREEN_WIDTH // 2, 48)
        pygame.draw.rect(screen, (44, 36, 30), bg_rect, border_radius=10)
        pygame.draw.rect(screen, (189, 155, 90), bg_rect, 1, border_radius=10)
        screen.blit(surf, surf.get_rect(center=bg_rect.center))

    def _render_disconnect_panel(self, screen: pygame.Surface) -> None:
        panel_rect = self._disconnect_panel_rect()
        pygame.draw.rect(screen, (24, 26, 35), panel_rect, border_radius=10)
        pygame.draw.rect(screen, (125, 96, 78), panel_rect, 2, border_radius=10)
        title = self.small_font.render("Disconnected Players", True, (226, 216, 196))
        screen.blit(title, (panel_rect.x + 12, panel_rect.y + 10))

        row_y = panel_rect.y + 34
        for player in self.disconnected_players:
            elapsed = int(player.get("disconnected_seconds", 0))
            remaining = max(0, 30 - elapsed)
            voters = set(player.get("kick_voters", []))
            required_voters = set(player.get("required_voters", []))
            eligible = self._can_vote_kick(player)
            button = self.disconnect_kick_buttons.get(player.get("spirit_id"))

            name = self.small_font.render(player.get("name", "?"), True, (210, 210, 220))
            status_text = f"{elapsed}s offline"
            if player.get("required_voters"):
                status_text += f"  {len(voters)}/{len(required_voters)} votes"
            status = self.small_font.render(status_text, True, (144, 152, 170))
            screen.blit(name, (panel_rect.x + 12, row_y))
            screen.blit(status, (panel_rect.x + 12, row_y + 16))

            if button:
                if remaining > 0:
                    button.text = f"Kick in {remaining}s"
                elif self.app.my_spirit_id in voters:
                    button.text = "Voted"
                elif eligible:
                    button.text = "Vote Kick"
                else:
                    button.text = "Waiting"
                button.draw(screen, self.small_font)
            row_y += 42

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
                               f"at the end of the turn (halved in Era 2).")
                else:
                    vp_line = (f"When {faction_name} gain gold and Worship a Spirit, "
                               f"that Spirit gains {AFFLUENCE_IDOL_VP} VP at the end of the turn "
                               f"(halved in Era 2).")
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
                           f"for each gold the Faction gains (halved in Era 2).")
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

    def _draw_submit_button(self, screen):
        """Draw the submit button and register its tooltip when appropriate."""
        if not self.submit_button:
            return
        self.submit_button.draw(screen, self.font)
        if (self.submit_button.tooltip and self.submit_button.hovered
                and (not self.submit_button.enabled or self.submit_button.tooltip_always)):
            self.tooltip_registry.offer(TooltipDescriptor(
                self.submit_button.tooltip, _GUIDANCE_HOVER_REGIONS,
                self.submit_button.rect.centerx, self.submit_button.rect.top,
            ))

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

        # Guidance summary
        if self.guidance_summary_rect:
            if self.selected_faction:
                summary_lines = self._wrap_guidance_summary_lines(
                    self._build_guidance_summary_lines(self.selected_faction),
                    self.guidance_summary_rect.width - 16,
                )
            else:
                summary_lines = self._wrap_guidance_summary_lines(
                    ["Select a faction to preview Guidance."],
                    self.guidance_summary_rect.width - 16,
                )
            line_h = self.small_font.get_linesize()
            summary_h = 12 + len(summary_lines) * line_h
            self.guidance_summary_rect.height = max(36, summary_h)
            pygame.draw.rect(screen, (22, 22, 34), self.guidance_summary_rect, border_radius=8)
            pygame.draw.rect(screen, (78, 78, 104), self.guidance_summary_rect, 1, border_radius=8)
            self.guidance_summary_keyword_rects = render_rich_lines(
                screen,
                self.small_font,
                summary_lines,
                self.guidance_summary_rect.x + 8,
                self.guidance_summary_rect.y + 6,
                keywords=["Affinity", "Worship"],
                hovered_keyword=self.hovered_guidance_summary_keyword,
                normal_color=theme.TEXT_NORMAL,
                keyword_color=(140, 220, 255),
                hovered_keyword_color=(190, 240, 255),
            )

        # Draw idol sources
        if self.current_era == "era_1":
            for source in self.idol_drag_sources:
                rect = source["rect"]
                self.hex_renderer.draw_idol_token(
                    screen,
                    rect.centerx,
                    rect.centery,
                    source["idol_type"],
                    max(11, min(rect.width, rect.height) // 3),
                    outline_color=(255, 255, 255) if self.selected_idol_type == source["idol_type"].value else None,
                )
        else:
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
        if self.selected_faction and self.guidance_summary_rect:
            if self.hovered_guidance_summary_keyword == "Affinity":
                affinity_rects = self.guidance_summary_keyword_rects.get("Affinity", [])
                if affinity_rects:
                    rect = affinity_rects[0]
                    self.tooltip_registry.offer(TooltipDescriptor(
                        _AFFINITY_TOOLTIP,
                        _GUIDANCE_HOVER_REGIONS,
                        rect.centerx,
                        rect.bottom,
                        below=True,
                    ))
            elif self.hovered_guidance_summary_keyword == "Worship":
                worship_rects = self.guidance_summary_keyword_rects.get("Worship", [])
                if worship_rects:
                    rect = worship_rects[0]
                    faction_data = self.factions.get(self.selected_faction, {})
                    worship_id = faction_data.get("worship_spirit") if isinstance(faction_data, dict) else None
                    self.tooltip_registry.offer(TooltipDescriptor(
                        self._build_worship_tooltip(self.selected_faction, worship_id),
                        _GUIDANCE_HOVER_REGIONS,
                        rect.centerx,
                        rect.bottom,
                        below=True,
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

            self._draw_submit_button(screen)

        if self.dragging_idol:
            drag = self.dragging_idol
            self.hex_renderer.draw_idol_token(
                screen,
                int(drag["pos"][0]),
                int(drag["pos"][1]),
                drag["idol_type"],
                drag["radius"],
            )

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
            self._draw_submit_button(screen)

    def _build_change_hand(self) -> list[dict]:
        hand = []
        for card_name in self.change_cards:
            if self.phase == SubPhase.CHANGE_CHOICE:
                desc = self.ui_renderer._build_modifier_description(card_name)
                tooltip = build_modifier_tooltip(card_name)
                title = card_name.title()
            else:
                info = get_era_card_info(card_name) or {}
                desc = _wrap_text(info.get("body", card_name), self.small_font, 96)
                tooltip = info.get("tooltip", card_name)
                title = card_name
            hand.append({
                "agenda_type": card_name,
                "title": title,
                "description": desc,
                "tooltip": tooltip,
            })
        return hand

    def _render_change_ui(self, screen):
        if not self.change_cards:
            return
        my_spirit = self.spirits.get(self.app.my_spirit_id, {})
        fid = my_spirit.get("guided_faction", "")
        faction_name = faction_full_name(fid) if fid else "your Faction"

        hand = self._build_change_hand()
        card_rects = self._calc_left_choice_card_rects(len(hand))
        start_x = card_rects[0].x if card_rects else 20
        start_y = card_rects[0].y if card_rects else _CHOICE_CARD_Y

        if self.phase == SubPhase.RESTRAIN_CHOICE:
            title_text = f"Restrain {faction_name}: choose the agenda to skip"
        elif self.phase == SubPhase.SHAPING_CHOICE:
            title_text = f"Shape {faction_name}: choose one card"
        elif self.phase == SubPhase.ADAPTATION_CHOICE:
            title_text = "Adapt: choose one card"
        else:
            title_text = f"Choose modifier for {faction_name}:"
        title = self.font.render(title_text, True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (max(4, start_x + 2), 102))

        modifiers = self._get_current_faction_modifiers()
        self.ui_renderer.draw_card_hand(
            screen, hand, self.selected_restrain_index if self.phase == SubPhase.RESTRAIN_CHOICE else -1,
            start_x, start_y,
            modifiers=modifiers,
            card_images=agenda_card_images,
            show_preview_plus=self.phase == SubPhase.CHANGE_CHOICE,
            vertical=True,
        )
        if self.phase == SubPhase.RESTRAIN_CHOICE and 0 <= self.selected_restrain_index < len(card_rects):
            rect = card_rects[self.selected_restrain_index]
            inset = 12
            pygame.draw.line(screen, (220, 50, 50), (rect.left + inset, rect.top + inset), (rect.right - inset, rect.bottom - inset), 6)
            pygame.draw.line(screen, (220, 50, 50), (rect.right - inset, rect.top + inset), (rect.left + inset, rect.bottom - inset), 6)
        if self.phase == SubPhase.RESTRAIN_CHOICE and self.submit_button:
            self.submit_button.enabled = self.selected_restrain_index >= 0
            self.submit_button.tooltip = "Choose an Agenda to restrain first." if self.selected_restrain_index < 0 else None
            self.submit_button.tooltip_always = self.selected_restrain_index < 0
            self._draw_submit_button(screen)

    def _render_battleground_choice_ui(self, screen):
        if not self.battleground_choice_entries:
            return
        title = self.font.render("Stage War: choose a battleground", True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (20, 102))
        instructions = _wrap_text(
            "Click one of the red border arrows on the map. A staged battleground is emphasized with triple arrows.",
            self.font,
            220,
        )
        for i, line in enumerate(instructions):
            screen.blit(self.font.render(line, True, theme.TEXT_NORMAL), (20, 130 + i * self.font.get_linesize()))
        self.battleground_choice_buttons = []
        self._battleground_arrow_rects = []
        for entry in self.battleground_choice_entries:
            war_id = entry["war_id"]
            for idx, pair in enumerate(entry.get("pairs", [])):
                a = (pair["a"]["q"], pair["a"]["r"])
                b = (pair["b"]["q"], pair["b"]["r"])
                rect = self.hex_renderer.get_arrow_hitbox(
                    a, b, self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT)
                self.battleground_choice_buttons.append({"war_id": war_id, "pair_index": idx, "rect": rect})
        summary_y = 130 + len(instructions) * self.font.get_linesize() + 12
        for row, entry in enumerate(self.battleground_choice_entries):
            war_id = entry["war_id"]
            chosen = self.battleground_selections.get(war_id)
            label = f"{faction_full_name(entry['faction_a'])} vs {faction_full_name(entry['faction_b'])}"
            status = "Chosen" if chosen is not None else "Pending"
            color = (230, 185, 50) if chosen is None else (150, 210, 150)
            surf = self.small_font.render(f"{label}: {status}", True, color)
            screen.blit(surf, (20, summary_y + row * 18))
        if self.submit_button:
            ready = len(self.battleground_selections) >= len(self.battleground_choice_entries)
            self.submit_button.enabled = ready
            self.submit_button.tooltip = "Choose a battleground for each staged war." if not ready else None
            self.submit_button.tooltip_always = not ready
            self._draw_submit_button(screen)

    def _render_war_support_choice_ui(self, screen):
        if not self.war_support_entries:
            return
        title = self.font.render("War Support: assign your extra die", True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (20, 102))
        self.war_support_buttons = []
        y = 150
        for entry in self.war_support_entries:
            war_id = entry["war_id"]
            for faction_id, x in ((entry["faction_a"], 20), (entry["faction_b"], 250)):
                rect = pygame.Rect(x, y, 180, 42)
                selected = self.war_support_selections.get(war_id) == faction_id
                faction_color = tuple(FACTION_COLORS.get(faction_id, (150, 150, 150)))
                bg_color = tuple(max(c // 5, 8) for c in faction_color)
                pygame.draw.rect(screen, bg_color, rect, border_radius=6)
                pygame.draw.rect(screen, (255, 255, 255) if selected else (190, 190, 210), rect, 2 if selected else 1, border_radius=6)
                _draw_text_in_rect(screen, faction_full_name(faction_id), rect, self.font, faction_color)
                self.war_support_buttons.append({"war_id": war_id, "faction": faction_id, "rect": rect})
            y += 60
        if self.submit_button:
            ready = len(self.war_support_selections) >= len(self.war_support_entries)
            self.submit_button.enabled = ready
            self._draw_submit_button(screen)

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
        self.ejection_keyword_rects = {}
        self.ejection_faction_rects = []
        faction_name = faction_full_name(self.ejection_faction)
        for line_idx, line in enumerate(lines):
            tooltip_spans = []
            for keyword in keywords:
                start = 0
                while True:
                    pos = line.find(keyword, start)
                    if pos < 0:
                        break
                    tooltip_spans.append({
                        "start": pos,
                        "end": pos + len(keyword),
                        "kind": "tooltip",
                        "tooltip": _INFLUENCE_TOOLTIP if keyword == "Influence" else _AGENDA_POOL_TOOLTIP,
                    })
                    start = pos + len(keyword)
            spans = tooltip_spans + [{
                "start": pos,
                "end": pos + len(faction_name),
                "kind": "faction",
                "faction_id": self.ejection_faction,
            } for pos in range(len(line)) if line.startswith(faction_name, pos)]
            faction_rects, tooltip_rects = render_event_log_line(
                screen,
                self.font,
                line,
                text_x,
                text_y + line_idx * line_h,
                theme.TEXT_HIGHLIGHT,
                spans=spans,
            )
            self.ejection_faction_rects.extend(faction_rects.get(self.ejection_faction, []))
            for tooltip, rect in tooltip_rects:
                self.ejection_keyword_rects.setdefault(
                    "Influence" if tooltip == _INFLUENCE_TOOLTIP else "Agenda pool",
                    [],
                ).append(rect)

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
            self._draw_submit_button(screen)

    def _render_winner_choice_ui(self, screen):
        """Render the winner choice UI (one-guided war: spirit picks who wins)."""
        if not self.winner_choice_wars:
            return
        title = self.font.render("Choose War Outcome", True, theme.TEXT_HIGHLIGHT)
        screen.blit(title, (20, 102))
        instruction = "You are guiding one side. Choose which faction wins each war."
        lines = _wrap_text(instruction, self.font, 220)
        line_h = self.font.get_linesize()
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, theme.TEXT_NORMAL)
            screen.blit(surf, (20, 122 + i * line_h))

        # Draw faction buttons
        for btn in self.winner_choice_buttons:
            war_id = btn["war_id"]
            faction_id = btn["faction"]
            rect = btn["rect"]
            selected = self.winner_selections.get(war_id) == faction_id
            faction_color = tuple(FACTION_COLORS.get(faction_id, (150, 150, 150)))
            bg_color = tuple(max(c // 5, 8) for c in faction_color)
            pygame.draw.rect(screen, bg_color, rect, border_radius=6)
            pygame.draw.rect(screen, (255, 255, 255) if selected else (180, 180, 180), rect, 2 if selected else 1, border_radius=6)
            label = faction_full_name(faction_id)
            _draw_text_in_rect(screen, label, rect, self.font, faction_color)

        if self.submit_button:
            all_chosen = len(self.winner_selections) >= len(self.winner_choice_wars)
            self.submit_button.enabled = all_chosen
            self.submit_button.tooltip = "Choose a winner for each war first." if not all_chosen else None
            self.submit_button.tooltip_always = not all_chosen
            self._draw_submit_button(screen)

    def _render_spoils_expand_choice_ui(self, screen):
        """Render the spoils expand choice UI (spirit picks enemy territory to conquer)."""
        if not self.spoils_expand_choices:
            return
        n = len(self.spoils_expand_choices)
        idx = min(self.spoils_expand_display_index, n - 1)
        entry = self.spoils_expand_choices[idx]
        loser = faction_full_name(entry.get("loser", ""))

        title_rect = pygame.Rect(20, 102, max(220, _HEX_MAP_LEFT_X - 30), self.font.get_linesize() * 2 + 4)
        _draw_text_in_rect(screen, f"Expand Spoils: Conquer {loser}", title_rect, self.font, theme.TEXT_HIGHLIGHT)

        if n > 1:
            page_text = f"War {idx + 1} / {n}"
            page_surf = self.font.render(page_text, True, theme.TEXT_DIM)
            screen.blit(page_surf, (20, 122))
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
            self.spoils_expand_nav_left_rect = left_rect
            self.spoils_expand_nav_right_rect = right_rect
        else:
            self.spoils_expand_nav_left_rect = None
            self.spoils_expand_nav_right_rect = None

        instruction = f"Click a highlighted hex to claim a {loser} territory."
        lines = _wrap_text(instruction, self.font, 220)
        line_h = self.font.get_linesize()
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, theme.TEXT_NORMAL)
            screen.blit(surf, (20, 146 + i * line_h))

        # Per-war selection status
        status_y = 146 + len(lines) * line_h + 12
        for i, ch in enumerate(self.spoils_expand_choices):
            sel = self.spoils_expand_selections[i] if i < len(self.spoils_expand_selections) else None
            ch_loser = faction_full_name(ch.get("loser", ""))
            color = (100, 220, 100) if sel is not None else (180, 180, 180)
            check = " ✓" if sel is not None else ""
            s = self.font.render(f"vs {ch_loser}{check}", True, color)
            screen.blit(s, (20, status_y + i * line_h))

        if self.submit_button:
            all_chosen = all(s is not None for s in self.spoils_expand_selections)
            self.submit_button.enabled = all_chosen
            self.submit_button.tooltip = "Select a hex for each war first." if not all_chosen else None
            self.submit_button.tooltip_always = not all_chosen
            self._draw_submit_button(screen)

    def _render_respawn_choice_ui(self, screen):
        faction_name = faction_full_name(self.respawn_choice_faction)
        title_rect = pygame.Rect(20, 102, max(220, _HEX_MAP_LEFT_X - 30), self.font.get_linesize() * 2 + 4)
        _draw_text_in_rect(screen, f"Respawn: {faction_name}", title_rect, self.font, (255, 160, 60))

        instruction = "Your faction lost all territory and must respawn. Click any highlighted neutral hex to choose where it reappears."
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
            self._draw_submit_button(screen)

    def _render_expand_choice_ui(self, screen):
        faction_name = faction_full_name(self.expand_choice_faction)
        title_rect = pygame.Rect(20, 102, max(220, _HEX_MAP_LEFT_X - 30), self.font.get_linesize() * 2 + 4)
        _draw_text_in_rect(screen, f"Expand: {faction_name}", title_rect, self.font, theme.TEXT_HIGHLIGHT)

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
            self._draw_submit_button(screen)

    def _render_spoils_ui(self, screen):
        self._render_spoils_dropdown_list(screen, self.spoils_entries, is_change=False)

    def _render_spoils_change_ui(self, screen):
        self._render_spoils_dropdown_list(screen, self.spoils_change_entries, is_change=True)

    def _render_spoils_dropdown_list(self, screen, entries, is_change: bool):
        if not entries:
            return

        title_text = "Spoils of War" if not is_change else "Spoils of War - Modifiers"
        info_box_w = max(220, _HEX_MAP_LEFT_X - 36)
        info_box_x = max(18, (_HEX_MAP_LEFT_X - info_box_w) // 2)
        info_pad_x = 12
        info_pad_y = 8
        info_inner_w = info_box_w - info_pad_x * 2
        title_lines = _wrap_text(title_text, self.font, info_inner_w)
        body_text = (
            "Choose one reward under each defeated faction. If you picked Change as Spoils, "
            "choose one modifier reward for each of those Change Agendas."
            if is_change else
            "Choose your Spoils by clicking one reward under each defeated faction."
        )
        body_lines = _wrap_text(body_text, self.small_font, info_inner_w)
        info_box_h = (
            info_pad_y * 2
            + len(title_lines) * self.font.get_linesize()
            + 6
            + len(body_lines) * self.small_font.get_linesize()
        )
        info_box_y = max(_RIBBON_BOTTOM_Y + 18, _MAP_CENTER_Y - info_box_h // 2)
        info_rect = pygame.Rect(info_box_x, info_box_y, info_box_w, info_box_h)
        pygame.draw.rect(screen, (24, 24, 34), info_rect, border_radius=8)
        pygame.draw.rect(screen, (120, 120, 145), info_rect, 1, border_radius=8)
        text_y = info_box_y + info_pad_y
        for line in title_lines:
            title = self.font.render(line, True, (255, 200, 100))
            screen.blit(title, (info_box_x + info_pad_x, text_y))
            text_y += self.font.get_linesize()
        text_y += 6
        help_rects = render_rich_lines(
            screen, self.small_font, body_lines, info_box_x + info_pad_x, text_y,
            keywords=["Spoils", "Change Agendas"] if is_change else ["Spoils"],
            hovered_keyword=None,
            normal_color=(190, 190, 200),
            keyword_color=theme.TEXT_KEYWORD,
            hovered_keyword_color=theme.TEXT_KEYWORD_HOV,
        )
        spoils_keyword_rects = help_rects.get("Spoils", [])
        if spoils_keyword_rects:
            self.spoils_help_rect = spoils_keyword_rects[0].copy()
            for rect in spoils_keyword_rects[1:]:
                self.spoils_help_rect.union_ip(rect)
        else:
            self.spoils_help_rect = None

        self.spoils_nav_left_rect = None
        self.spoils_nav_right_rect = None
        self.spoils_toggle_rects = []
        self.spoils_card_rects = [[] for _ in entries]

        modifiers = self._get_current_faction_modifiers()
        top_y = _RIBBON_BOTTOM_Y
        self.spoils_panel_rects = []

        for idx, entry in enumerate(entries):
            faction_id = getattr(entry, "loser", "")
            faction_color = tuple(FACTION_COLORS.get(faction_id, (120, 120, 120)))
            bg_color = tuple(max(c // 5, 8) for c in faction_color)
            pending = entry.selected < 0

            ribbon_rect = self.ribbon_faction_rects.get(faction_id)
            if ribbon_rect:
                panel_x = ribbon_rect.x
                panel_w = ribbon_rect.width
            else:
                cell_w = SCREEN_WIDTH // max(1, len(self.faction_order or self.factions))
                panel_x = idx * cell_w
                panel_w = cell_w

            card_count = len(entry.cards)
            inner_pad = 4
            card_gap = 4
            columns = min(3, max(1, card_count))
            available_w = max(90, panel_w - inner_pad * 2 - card_gap * (columns - 1))
            card_w = max(56, available_w // columns)
            card_h = card_w
            row_count = (card_count + columns - 1) // columns if entry.expanded else 0
            body_h = 0 if not entry.expanded else (8 + row_count * card_h + max(0, row_count - 1) * 6 + 8)
            toggle_h = 14
            panel_h = body_h + toggle_h
            panel_rect = pygame.Rect(panel_x, top_y, panel_w, panel_h)
            self.spoils_panel_rects.append(panel_rect)
            pygame.draw.rect(screen, bg_color, panel_rect)
            pygame.draw.rect(screen, faction_color, pygame.Rect(panel_x, top_y, 3, panel_h))
            pygame.draw.rect(
                screen,
                bg_color,
                pygame.Rect(panel_x + 3, top_y, max(7, panel_w - 3), max(10, panel_h - toggle_h)),
            )
            bar_color = faction_color if pending else bg_color
            toggle_rect = pygame.Rect(panel_x, panel_rect.bottom - toggle_h, panel_w, toggle_h)
            pygame.draw.rect(screen, bar_color, toggle_rect)
            pygame.draw.rect(screen, faction_color, pygame.Rect(panel_x, toggle_rect.top, 3, toggle_h))
            tri_cx = toggle_rect.centerx
            tri_cy = toggle_rect.centery + (1 if entry.expanded else -1)
            tri_half_w = 6
            tri_half_h = 4
            if entry.expanded:
                triangle = [
                    (tri_cx - tri_half_w, tri_cy + tri_half_h),
                    (tri_cx + tri_half_w, tri_cy + tri_half_h),
                    (tri_cx, tri_cy - tri_half_h),
                ]
            else:
                triangle = [
                    (tri_cx - tri_half_w, tri_cy - tri_half_h),
                    (tri_cx + tri_half_w, tri_cy - tri_half_h),
                    (tri_cx, tri_cy + tri_half_h),
                ]
            pygame.draw.polygon(screen, (0, 0, 0), triangle)
            self.spoils_toggle_rects.append(toggle_rect)
            if entry.expanded:
                hand = []
                for card_name in entry.cards:
                    if is_change:
                        hand.append({
                            "agenda_type": card_name,
                            "title": card_name.title(),
                            "description": self.ui_renderer._build_modifier_description(card_name),
                            "tooltip": build_modifier_tooltip(card_name),
                        })
                    else:
                        hand.append({"agenda_type": card_name})

                start_x = panel_x + max(4, (panel_w - (columns * card_w + (columns - 1) * card_gap)) // 2)
                start_y = top_y + 8
                card_rects = []
                for card_idx, card in enumerate(hand):
                    col = card_idx % columns
                    row = card_idx // columns
                    cx = start_x + col * (card_w + card_gap)
                    cy = start_y + row * (card_h + 6)
                    rect = pygame.Rect(cx, cy, card_w, card_h)
                    card_rects.append(rect)
                    self._draw_compact_spoils_card(
                        screen, rect, card,
                        selected=(entry.selected == card_idx),
                        modifiers=modifiers if not is_change else None,
                        is_spoils=not is_change,
                        is_change=is_change,
                    )
                    if entry.selected >= 0 and entry.selected != card_idx:
                        shade = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                        shade.fill((25, 25, 35, 120))
                        screen.blit(shade, rect.topleft)
                self.spoils_card_rects[idx] = card_rects

        if self.submit_button:
            all_selected = all(entry.selected >= 0 for entry in entries)
            self.submit_button.enabled = all_selected
            if not all_selected:
                missing = [faction_full_name(entry.loser) or f"War {i + 1}"
                           for i, entry in enumerate(entries) if entry.selected < 0]
                self.submit_button.tooltip = "Still need to choose: " + ", ".join(missing)
                self.submit_button.tooltip_always = True
            else:
                self.submit_button.tooltip = None
                self.submit_button.tooltip_always = False
            self._draw_submit_button(screen)

    def _draw_compact_spoils_card(self, screen, rect, card, selected, modifiers, is_spoils, is_change):
        bg = (60, 80, 120) if selected else (40, 40, 55)
        border = (200, 200, 255) if selected else (80, 80, 100)
        pygame.draw.rect(screen, bg, rect, border_radius=6)
        pygame.draw.rect(screen, border, rect, 2, border_radius=6)

        title_font = self.ui_renderer._get_font(11)
        agenda_type = card.get("agenda_type", "?")
        title_lines = _wrap_text(card.get("title", agenda_type), title_font, rect.width - 8)[:2]
        for i, line in enumerate(title_lines):
            surf = title_font.render(line, True, (220, 220, 240))
            screen.blit(surf, (rect.centerx - surf.get_width() // 2, rect.y + 5 + i * 11))

        img = agenda_card_images.get(agenda_type)
        content_top = rect.y + 7 + len(title_lines) * 11
        if img:
            icon_w = max(24, rect.width - 14)
            icon_h = max(24, rect.bottom - 6 - content_top)
            scale = min(icon_w / max(1, img.get_width()), icon_h / max(1, img.get_height()))
            img_w = max(1, int(img.get_width() * scale))
            img_h = max(1, int(img.get_height() * scale))
            scaled = pygame.transform.smoothscale(img, (img_w, img_h))
            ix = rect.centerx - scaled.get_width() // 2
            iy = content_top + max(1, (icon_h - scaled.get_height()) // 2)
            screen.blit(scaled, (ix, iy))
