"""Animation orchestration: creation and rendering of agenda/effect animations."""

import pygame
from shared.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES,
)
from client.faction_names import faction_full_name
from shared.hex_utils import axial_to_pixel, hex_neighbors
from client.renderer.animation import (
    AnimationManager, AgendaSlideAnimation, TextAnimation, ArrowAnimation,
)
from client.renderer.assets import agenda_images


class AnimationOrchestrator:
    """Manages agenda/effect animation creation and rendering."""

    def __init__(self, animation_manager: AnimationManager,
                 hex_renderer, input_handler):
        self.animation = animation_manager
        self.hex_renderer = hex_renderer
        self.input_handler = input_handler
        self.deferred_phase_start: dict | None = None
        self.faction_order: list[str] = list(FACTION_NAMES)

    # --- Position helpers ---

    @staticmethod
    def _get_faction_centroid(hex_ownership: dict, faction_id: str) -> tuple[float | None, float | None]:
        """Get the world-coordinate centroid of a faction's territory."""
        owned = [(q, r) for (q, r), owner in hex_ownership.items()
                 if owner == faction_id]
        if not owned:
            return None, None
        avg_q = sum(q for q, r in owned) / len(owned)
        avg_r = sum(r for q, r in owned) / len(owned)
        best = min(owned, key=lambda h: (h[0] - avg_q) ** 2 + (h[1] - avg_r) ** 2)
        return axial_to_pixel(best[0], best[1], HEX_SIZE)

    def _get_gold_display_pos(self, faction_id: str, small_font) -> tuple[int, int]:
        """Get screen position below the faction's gold text in the overview strip."""
        try:
            idx = self.faction_order.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 97)
        cell_w = SCREEN_WIDTH // len(self.faction_order)
        cx = idx * cell_w
        abbr = faction_full_name(faction_id)
        abbr_w = small_font.size(abbr)[0]
        gold_x = cx + 6 + abbr_w + 6
        return (gold_x, 97)

    def _get_agenda_label_pos(self, faction_id: str, img_width: int, row: int = 0) -> tuple[int, int]:
        """Get the target screen position for an agenda slide animation."""
        try:
            idx = self.faction_order.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 46)
        cell_w = SCREEN_WIDTH // len(self.faction_order)
        cx = idx * cell_w
        target_x = cx + cell_w - img_width - 6
        target_y = 42 + 4 + row * 24
        return target_x, target_y

    def _get_agenda_slide_start(self, faction_id: str, img_width: int, row: int = 0) -> tuple[int, int]:
        """Get the start screen position for an agenda slide animation (below strip)."""
        target_x, _ = self._get_agenda_label_pos(faction_id, img_width, row)
        start_y = 42 + 55 + 20
        return target_x, start_y

    def _get_faction_strip_pos(self, faction_id: str) -> tuple[int, int]:
        """Get position below a faction's name in the overview strip for regard text."""
        try:
            idx = self.faction_order.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 101)
        cell_w = SCREEN_WIDTH // len(self.faction_order)
        cx = idx * cell_w
        return (cx + 6, 97 + 4)

    def _get_border_midpoints(self, hex_ownership: dict,
                              faction_a: str, faction_b: str) -> list[tuple[float, float]]:
        """Get world-space midpoints of all border edges between two factions."""
        pairs = self.hex_renderer._get_border_pairs(hex_ownership, faction_a, faction_b)
        midpoints = []
        for h1, h2 in pairs:
            x1, y1 = axial_to_pixel(h1[0], h1[1], HEX_SIZE)
            x2, y2 = axial_to_pixel(h2[0], h2[1], HEX_SIZE)
            midpoints.append(((x1 + x2) / 2, (y1 + y2) / 2))
        return midpoints

    # --- Effect animation creation ---

    def create_effect_animations(self, event: dict, faction_id: str,
                                 delay: float, hex_ownership: dict, small_font):
        """Create effect animations for an agenda event."""
        etype = event.get("type", "")

        if etype in ("trade", "trade_spoils_bonus"):
            gold = event.get("gold_gained", 0)
            if gold > 0:
                gx, gy = self._get_gold_display_pos(faction_id, small_font)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{gold}g", gx, gy, (255, 220, 60),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))
            regard_gain = event.get("regard_gain", 0)
            co_traders = event.get("co_traders", [])
            if regard_gain > 0:
                for nfid in co_traders:
                    rx, ry = self._get_faction_strip_pos(nfid)
                    self.animation.add_effect_animation(TextAnimation(
                        f"+{regard_gain}", rx, ry, (100, 200, 255),
                        delay=delay, duration=3.0, drift_pixels=40,
                        direction=1, screen_space=True,
                    ))

        elif etype == "steal":
            gold = event.get("gold_gained", 0)
            regard_penalty = event.get("regard_penalty", 1)
            neighbors = event.get("neighbors", [])
            if gold > 0:
                gx, gy = self._get_gold_display_pos(faction_id, small_font)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{gold}g", gx, gy, (255, 220, 60),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))
            for nfid in neighbors:
                rx, ry = self._get_faction_strip_pos(nfid)
                self.animation.add_effect_animation(TextAnimation(
                    f"-{regard_penalty}", rx, ry, (255, 80, 80),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))

        elif etype in ("expand", "expand_spoils"):
            target_hex = event.get("hex")
            if target_hex:
                tq, tr = target_hex["q"], target_hex["r"]
                for nq, nr in hex_neighbors(tq, tr):
                    if hex_ownership.get((nq, nr)) == faction_id:
                        self.animation.add_effect_animation(ArrowAnimation(
                            (nq, nr), (tq, tr), (80, 220, 80),
                            delay=delay, duration=3.0,
                        ))

        elif etype == "expand_failed":
            gold = event.get("gold_gained", 0)
            if gold > 0:
                gx, gy = self._get_gold_display_pos(faction_id, small_font)
                self.animation.add_effect_animation(TextAnimation(
                    f"+{gold}g", gx, gy, (255, 220, 60),
                    delay=delay, duration=3.0, drift_pixels=40,
                    direction=1, screen_space=True,
                ))

    # --- Agenda animation creation ---

    def _get_append_delay_from_existing_agendas(self) -> float:
        """Return delay needed to start after all currently scheduled agenda slides."""
        max_remaining = 0.0
        for anim in self.animation.get_persistent_agenda_animations():
            if anim.done:
                continue
            remaining = (anim.delay + AgendaSlideAnimation.SLIDE_DURATION) - anim.elapsed
            if remaining > max_remaining:
                max_remaining = remaining
        return max(0.0, max_remaining)

    _ANIM_ORDER = {
        "trade": 0, "steal": 1,
        "expand": 2, "expand_failed": 2, "expand_spoils": 2,
        "change": 3,
    }

    def _process_event_list(self, events: list[dict], hex_ownership: dict, small_font,
                            is_spoils: bool, base_row: int, claim_row,
                            base_delay: float, offset_start: int,
                            war_by_faction: dict) -> int:
        """Create slide/effect animations for one batch of sorted agenda events.

        Returns the number of animations actually created (for computing
        timeline offsets in a subsequent batch).
        """
        anim_index = 0
        for event in events:
            etype = event["type"]
            if etype == "change":
                modifier = event.get("modifier", "")
                img_key = f"change_{modifier}" if f"change_{modifier}" in agenda_images else "change"
            elif etype == "expand_failed":
                img_key = "expand_failed"
            else:
                img_key = {"steal": "steal", "trade": "trade",
                           "expand": "expand", "expand_spoils": "expand"}[etype]
            img = agenda_images.get(img_key)
            faction_id = event.get("faction")
            if not img:
                print(f"[anim] No image for '{img_key}' (loaded: {list(agenda_images.keys())})")
            elif not faction_id:
                print(f"[anim] No faction_id in {etype} event")
            else:
                delay = base_delay + (offset_start + anim_index) * 1.0
                img_w = img.get_width()
                row = claim_row(faction_id, base_row=base_row)
                target_x, target_y = self._get_agenda_label_pos(faction_id, img_w, row)
                start_x, start_y = self._get_agenda_slide_start(faction_id, img_w, row)
                anim = AgendaSlideAnimation(
                    img, faction_id,
                    target_x, target_y,
                    start_x, start_y,
                    delay=delay,
                    auto_fadeout_after=0.0,
                    is_spoils=is_spoils,
                    agenda_type=etype,
                )
                # Tag expand animations with hex reveal info
                if etype in ("expand", "expand_spoils"):
                    target_hex = event.get("hex")
                    if target_hex:
                        anim.hex_reveal = (target_hex["q"], target_hex["r"])
                        anim.hex_reveal_faction = faction_id
                # Tag gold delta for incremental ribbon updates
                gold_gained = event.get("gold_gained", 0)
                if gold_gained:
                    anim.gold_delta = gold_gained
                    anim.gold_delta_faction = faction_id
                gold_deltas: list[tuple[str, int]] = []
                if gold_gained:
                    gold_deltas.append((faction_id, gold_gained))
                if etype == "steal":
                    steal_amount = event.get("regard_penalty", 1)
                    for nfid in event.get("neighbors", []):
                        if steal_amount:
                            gold_deltas.append((nfid, -steal_amount))
                elif etype == "expand":
                    cost = event.get("cost", 0)
                    if cost:
                        gold_deltas.append((faction_id, -cost))
                if gold_deltas:
                    anim.gold_deltas = gold_deltas
                # Tag war reveals onto steal animations (regular events only)
                if not is_spoils and etype == "steal" and faction_id in war_by_faction:
                    anim.war_reveals = war_by_faction[faction_id]
                # Tag change modifier onto change animations
                if etype == "change":
                    modifier = event.get("modifier", "")
                    if modifier:
                        anim.change_modifier = modifier
                self.animation.add_persistent_agenda_animation(anim)
                self.create_effect_animations(event, faction_id, delay,
                                              hex_ownership, small_font)
                anim_index += 1
        return anim_index

    def process_agenda_events(self, agenda_events: list[dict],
                              hex_ownership: dict, small_font,
                              delay_offset: float = 0.0) -> float:
        """Create agenda/effect animations for a set of agenda events.

        Returns the duration window consumed (in seconds) so callers can
        sequence multiple sets without overlap.
        """
        base_delay = self._get_append_delay_from_existing_agendas() + max(0.0, delay_offset)

        # Extract war events for tagging onto steal animations
        war_events = [e for e in agenda_events if e.get("type") == "war_erupted"]
        war_by_faction: dict[str, list[dict]] = {}
        for we in war_events:
            war_by_faction.setdefault(we["faction_a"], []).append(we)
            war_by_faction.setdefault(we["faction_b"], []).append(we)

        regular_events = [e for e in agenda_events
                          if not e.get("is_spoils") and e.get("type") != "war_erupted"]
        spoils_events = [e for e in agenda_events if e.get("is_spoils")]

        def _claim_row(faction_id: str, base_row: int = 0) -> int:
            return base_row

        regular_events.sort(key=lambda e: self._ANIM_ORDER.get(e["type"], 99))
        spoils_events.sort(key=lambda e: self._ANIM_ORDER.get(e["type"], 99))

        regular_count = self._process_event_list(
            regular_events, hex_ownership, small_font,
            is_spoils=False, base_row=0, claim_row=_claim_row,
            base_delay=base_delay, offset_start=0,
            war_by_faction=war_by_faction,
        )
        spoils_count = self._process_event_list(
            spoils_events, hex_ownership, small_font,
            is_spoils=True, base_row=0, claim_row=_claim_row,
            base_delay=base_delay, offset_start=regular_count,
            war_by_faction=war_by_faction,
        )

        total_anims = regular_count + spoils_count
        if total_anims > 0:
            print(f"[anim] Created {total_anims} agenda animations ({regular_count} regular, {spoils_count} spoils)")
        if total_anims <= 0:
            return 0.0
        # Duration consumed by this event set on the local timeline.
        return (total_anims - 1) * 1.0 + AgendaSlideAnimation.SLIDE_DURATION

    # --- Rendering ---

    def render_persistent_agenda_animations(self, screen: pygame.Surface):
        """Draw active persistent agenda slide animations in screen space."""
        for anim in self.animation.get_persistent_agenda_animations():
            if not anim.active:
                continue
            img = anim.image.copy()
            img.set_alpha(anim.alpha)
            screen.blit(img, (int(anim.x), int(anim.y)))

    def render_effect_animations(self, screen: pygame.Surface,
                                 screen_space_only: bool, small_font):
        """Draw active effect animations (text and arrows)."""
        for anim in self.animation.get_active_effect_animations():
            if not anim.active:
                continue
            if screen_space_only and not anim.screen_space:
                continue
            if not screen_space_only and anim.screen_space:
                continue

            if isinstance(anim, TextAnimation):
                alpha = anim.alpha
                if alpha <= 0:
                    continue
                text_surf = small_font.render(anim.text, True, anim.color)
                text_surf.set_alpha(alpha)
                if anim.screen_space:
                    sx, sy = anim.x, anim.y + anim.y_offset
                else:
                    sx, sy = self.input_handler.world_to_screen(
                        anim.x, anim.y + anim.y_offset,
                        SCREEN_WIDTH, SCREEN_HEIGHT,
                    )
                screen.blit(text_surf, (int(sx), int(sy)))

            elif isinstance(anim, ArrowAnimation):
                alpha = anim.alpha
                if alpha <= 0:
                    continue
                color = tuple(int(c * alpha / 255) for c in anim.color)
                self.hex_renderer._draw_hex_arrow(
                    screen, anim.from_hex, anim.to_hex, color,
                    self.input_handler, SCREEN_WIDTH, SCREEN_HEIGHT,
                    width=3, head_size=8, unidirectional=True,
                )

    # --- Hex reveal ---

    def apply_hex_reveals(self, display_hex_ownership: dict):
        """Incrementally reveal hex ownership as expand animations become active."""
        for anim in self.animation.get_persistent_agenda_animations():
            if (anim.active and anim.hex_reveal is not None
                    and not anim._hex_revealed):
                display_hex_ownership[anim.hex_reveal] = anim.hex_reveal_faction
                anim._hex_revealed = True

    def apply_gold_deltas(self, display_factions: dict):
        """Incrementally update gold display as agenda animations become active."""
        for anim in self.animation.get_persistent_agenda_animations():
            if anim.active and not anim._gold_applied:
                applied = False
                if getattr(anim, "gold_deltas", None):
                    for fid, delta in anim.gold_deltas:
                        if fid and fid in display_factions and delta:
                            fd = display_factions[fid]
                            fd["gold"] = max(0, fd.get("gold", 0) + delta)
                            applied = True
                elif anim.gold_delta:
                    fid = anim.gold_delta_faction
                    if fid and fid in display_factions:
                        fd = display_factions[fid]
                        fd["gold"] = max(0, fd.get("gold", 0) + anim.gold_delta)
                        applied = True
                if applied:
                    anim._gold_applied = True

    def apply_war_reveals(self, display_wars: list):
        """Incrementally reveal wars as steal animations become active."""
        for anim in self.animation.get_persistent_agenda_animations():
            if anim.active and anim.war_reveals and not anim._wars_revealed:
                for wd in anim.war_reveals:
                    fa, fb = wd["faction_a"], wd["faction_b"]
                    already = any(
                        (w.get("faction_a") == fa and w.get("faction_b") == fb)
                        or (w.get("faction_a") == fb and w.get("faction_b") == fa)
                        for w in display_wars
                    )
                    if not already:
                        display_wars.append(wd)
                anim._wars_revealed = True

    def apply_change_modifier_deltas(self, display_factions: dict):
        """Incrementally update change_modifiers display as change animations become active."""
        for anim in self.animation.get_persistent_agenda_animations():
            if anim.active and not anim._change_modifier_applied and anim.change_modifier:
                fid = anim.faction_id
                if fid and fid in display_factions:
                    fd = display_factions[fid]
                    mods = fd.get("change_modifiers")
                    if mods is not None:
                        mods[anim.change_modifier] = mods.get(anim.change_modifier, 0) + 1
                anim._change_modifier_applied = True

    # --- State queries ---

    def has_animations_playing(self) -> bool:
        """Check if any animations are active (queued, in motion, or visible)."""
        if not self.animation.is_all_done():
            return True
        if self.animation.has_active_persistent_agenda_animations():
            return True
        return False

    def try_show_deferred_phase_ui(self, scene):
        """Show deferred PHASE_START UI once all animations have finished.

        Mutates scene.phase, scene.turn, scene.phase_options and calls
        scene._setup_phase_ui() when ready.
        """
        if not self.deferred_phase_start:
            return
        if not self.animation.is_all_done():
            return
        payload = self.deferred_phase_start
        self.deferred_phase_start = None
        scene.phase = payload.get("phase", scene.phase)
        scene.turn = payload.get("turn", scene.turn)
        scene.phase_options = payload.get("options", {})
        scene._setup_phase_ui()
