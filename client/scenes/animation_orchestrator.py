"""Animation orchestration: batching, creation, and rendering of agenda/effect animations."""

import pygame
from shared.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, HEX_SIZE, FACTION_NAMES, FACTION_DISPLAY_NAMES,
)
from shared.hex_utils import axial_to_pixel, hex_neighbors
from client.renderer.animation import (
    AnimationManager, AgendaSlideAnimation, TextAnimation, ArrowAnimation,
)
from client.renderer.assets import agenda_images


class AnimationOrchestrator:
    """Manages animation queuing, batch processing, and rendering."""

    def __init__(self, animation_manager: AnimationManager,
                 hex_renderer, input_handler):
        self.animation = animation_manager
        self.hex_renderer = hex_renderer
        self.input_handler = input_handler
        self.queue: list[list[dict]] = []
        self.fading: bool = False
        self.deferred_phase_start: dict | None = None

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
            idx = FACTION_NAMES.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 97)
        cell_w = SCREEN_WIDTH // len(FACTION_NAMES)
        cx = idx * cell_w
        abbr = FACTION_DISPLAY_NAMES.get(faction_id, faction_id)
        abbr_w = small_font.size(abbr)[0]
        gold_x = cx + 6 + abbr_w + 6
        return (gold_x, 97)

    @staticmethod
    def _get_agenda_label_pos(faction_id: str, img_width: int, row: int = 0) -> tuple[int, int]:
        """Get the target screen position for an agenda slide animation."""
        try:
            idx = FACTION_NAMES.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 46)
        cell_w = SCREEN_WIDTH // len(FACTION_NAMES)
        cx = idx * cell_w
        target_x = cx + cell_w - img_width - 6
        target_y = 42 + 4 + row * 24
        return target_x, target_y

    @staticmethod
    def _get_agenda_slide_start(faction_id: str, img_width: int, row: int = 0) -> tuple[int, int]:
        """Get the start screen position for an agenda slide animation (below strip)."""
        target_x, _ = AnimationOrchestrator._get_agenda_label_pos(faction_id, img_width, row)
        start_y = 42 + 55 + 20
        return target_x, start_y

    @staticmethod
    def _get_faction_strip_pos(faction_id: str) -> tuple[int, int]:
        """Get position below a faction's name in the overview strip for regard text."""
        try:
            idx = FACTION_NAMES.index(faction_id)
        except ValueError:
            return (SCREEN_WIDTH // 2, 101)
        cell_w = SCREEN_WIDTH // len(FACTION_NAMES)
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

        elif etype == "bond":
            regard_gain = event.get("regard_gain", 1)
            neighbors = event.get("neighbors", [])
            for nfid in neighbors:
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

    # --- Batch processing ---

    def try_process_next_batch(self, hex_ownership: dict, small_font):
        """Process the next queued animation batch when current animations are done."""
        if not self.queue:
            return
        if self.fading:
            if not self.animation.has_active_persistent_agenda_animations():
                self.fading = False
                batch = self.queue.pop(0)
                self._process_batch(batch, hex_ownership, small_font)
            return
        if not self.animation.is_all_done():
            return
        if self.animation.get_persistent_agenda_animations():
            self.animation.start_agenda_fadeout()
            self.fading = True
            return
        batch = self.queue.pop(0)
        self._process_batch(batch, hex_ownership, small_font)

    def _process_batch(self, agenda_events: list[dict],
                       hex_ownership: dict, small_font):
        """Create animations for a batch of agenda events."""
        _ANIM_ORDER = {
            "trade": 0, "bond": 1, "steal": 2,
            "expand": 3, "expand_failed": 3, "expand_spoils": 3,
            "change": 4,
        }
        regular_events = [e for e in agenda_events if not e.get("is_spoils")]
        spoils_events = [e for e in agenda_events if e.get("is_spoils")]

        # Allocate per-faction rows deterministically across the full batch
        # so regular + spoils cards stack without overlap.
        next_row_by_faction: dict[str, int] = {}

        def _claim_row(faction_id: str, base_row: int = 0) -> int:
            if faction_id not in next_row_by_faction:
                existing = sum(
                    1
                    for a in self.animation.get_persistent_agenda_animations()
                    if not a.done and a.faction_id == faction_id
                )
                next_row_by_faction[faction_id] = max(base_row, existing)
            row = next_row_by_faction[faction_id]
            next_row_by_faction[faction_id] += 1
            return row

        # --- Regular events ---
        regular_events.sort(key=lambda e: _ANIM_ORDER.get(e["type"], 99))
        agenda_anim_index = 0
        for event in regular_events:
            etype = event["type"]
            if etype == "change":
                modifier = event.get("modifier", "")
                img_key = f"change_{modifier}" if f"change_{modifier}" in agenda_images else "change"
            elif etype == "expand_failed":
                img_key = "expand_failed"
            else:
                img_key = {"steal": "steal", "bond": "bond", "trade": "trade",
                           "expand": "expand", "expand_spoils": "expand"}[etype]
            img = agenda_images.get(img_key)
            faction_id = event.get("faction")
            if not img:
                print(f"[anim] No image for '{img_key}' (loaded: {list(agenda_images.keys())})")
            elif not faction_id:
                print(f"[anim] No faction_id in {etype} event")
            else:
                delay = agenda_anim_index * 1.0
                img_w = img.get_width()
                row = _claim_row(faction_id, base_row=0)
                target_x, target_y = self._get_agenda_label_pos(faction_id, img_w, row)
                start_x, start_y = self._get_agenda_slide_start(faction_id, img_w, row)
                anim = AgendaSlideAnimation(
                    img, faction_id,
                    target_x, target_y,
                    start_x, start_y,
                    delay=delay,
                    agenda_type=etype,
                )
                # Tag expand animations with hex reveal info
                if etype in ("expand", "expand_spoils"):
                    target_hex = event.get("hex")
                    if target_hex:
                        anim.hex_reveal = (target_hex["q"], target_hex["r"])
                        anim.hex_reveal_faction = faction_id
                self.animation.add_persistent_agenda_animation(anim)
                self.create_effect_animations(event, faction_id, delay,
                                              hex_ownership, small_font)
                agenda_anim_index += 1

        # --- Spoils events (stack below regular agenda icons) ---
        spoils_events.sort(key=lambda e: _ANIM_ORDER.get(e["type"], 99))
        spoils_anim_index = 0
        for event in spoils_events:
            etype = event["type"]
            if etype == "change":
                modifier = event.get("modifier", "")
                img_key = f"change_{modifier}" if f"change_{modifier}" in agenda_images else "change"
            elif etype == "expand_failed":
                img_key = "expand_failed"
            else:
                img_key = {"steal": "steal", "bond": "bond", "trade": "trade",
                           "expand": "expand", "expand_spoils": "expand"}[etype]
            img = agenda_images.get(img_key)
            faction_id = event.get("faction")
            if not img:
                print(f"[anim] No image for '{img_key}' (loaded: {list(agenda_images.keys())})")
            elif not faction_id:
                print(f"[anim] No faction_id in {etype} event")
            else:
                delay = spoils_anim_index * 1.0
                row = _claim_row(faction_id, base_row=1)
                img_w = img.get_width()
                target_x, target_y = self._get_agenda_label_pos(faction_id, img_w, row)
                start_x, start_y = self._get_agenda_slide_start(faction_id, img_w, row)
                anim = AgendaSlideAnimation(
                    img, faction_id,
                    target_x, target_y,
                    start_x, start_y,
                    delay=delay,
                    is_spoils=True,
                    agenda_type=etype,
                )
                # Tag expand spoils animations with hex reveal info
                if etype in ("expand", "expand_spoils"):
                    target_hex = event.get("hex")
                    if target_hex:
                        anim.hex_reveal = (target_hex["q"], target_hex["r"])
                        anim.hex_reveal_faction = faction_id
                self.animation.add_persistent_agenda_animation(anim)
                self.create_effect_animations(event, faction_id, delay,
                                              hex_ownership, small_font)
                spoils_anim_index += 1

        total_anims = agenda_anim_index + spoils_anim_index
        if total_anims > 0:
            print(f"[anim] Created {total_anims} agenda animations ({agenda_anim_index} regular, {spoils_anim_index} spoils)")

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

    # --- State queries ---

    def has_animations_playing(self) -> bool:
        """Check if any animations are active (queued, in motion, or visible)."""
        if self.queue or self.fading:
            return True
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
        if self.queue or self.fading:
            return
        if not self.animation.is_all_done():
            return
        if self.animation.has_active_persistent_agenda_animations():
            self.animation.start_agenda_fadeout()
            return
        payload = self.deferred_phase_start
        self.deferred_phase_start = None
        scene.phase = payload.get("phase", scene.phase)
        scene.turn = payload.get("turn", scene.turn)
        scene.phase_options = payload.get("options", {})
        scene._setup_phase_ui()
