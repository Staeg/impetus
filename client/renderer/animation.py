"""Simple animation and tween system."""

import time


class Tween:
    """A simple value tween."""

    def __init__(self, start: float, end: float, duration: float):
        self.start_val = start
        self.end_val = end
        self.duration = duration
        self.elapsed = 0.0
        self.done = False

    def update(self, dt: float) -> float:
        self.elapsed += dt
        t = min(1.0, self.elapsed / self.duration) if self.duration > 0 else 1.0
        # Ease out cubic
        t = 1.0 - (1.0 - t) ** 3
        if self.elapsed >= self.duration:
            self.done = True
        return self.start_val + (self.end_val - self.start_val) * t

    @property
    def value(self) -> float:
        t = min(1.0, self.elapsed / self.duration) if self.duration > 0 else 1.0
        t = 1.0 - (1.0 - t) ** 3
        return self.start_val + (self.end_val - self.start_val) * t


class AnimationManager:
    """Manages a collection of animations."""

    def __init__(self):
        self.tweens: dict[str, Tween] = {}
        self.flash_timers: dict[str, float] = {}

    def add_tween(self, key: str, start: float, end: float, duration: float):
        self.tweens[key] = Tween(start, end, duration)

    def flash(self, key: str, duration: float = 0.5):
        self.flash_timers[key] = duration

    def update(self, dt: float):
        done_keys = []
        for key, tween in self.tweens.items():
            tween.update(dt)
            if tween.done:
                done_keys.append(key)
        for key in done_keys:
            del self.tweens[key]

        done_flashes = []
        for key, remaining in self.flash_timers.items():
            self.flash_timers[key] -= dt
            if self.flash_timers[key] <= 0:
                done_flashes.append(key)
        for key in done_flashes:
            del self.flash_timers[key]

        # Update agenda animations
        if hasattr(self, "agenda_animations"):
            for anim in self.agenda_animations:
                anim.update(dt)
            self.agenda_animations = [a for a in self.agenda_animations if not a.done]

        # Update effect animations
        if hasattr(self, "effect_animations"):
            for anim in self.effect_animations:
                anim.update(dt)
            self.effect_animations = [a for a in self.effect_animations if not a.done]

        # Update persistent agenda animations
        if hasattr(self, "persistent_agenda_animations"):
            for anim in self.persistent_agenda_animations:
                anim.update(dt)
            self.persistent_agenda_animations = [
                a for a in self.persistent_agenda_animations if not a.done]

    def get_tween_value(self, key: str, default: float = 0.0) -> float:
        if key in self.tweens:
            return self.tweens[key].value
        return default

    def is_flashing(self, key: str) -> bool:
        return key in self.flash_timers

    # --- Agenda animations (old world-space) ---

    def add_agenda_animation(self, anim: "AgendaAnimation"):
        if not hasattr(self, "agenda_animations"):
            self.agenda_animations: list[AgendaAnimation] = []
        self.agenda_animations.append(anim)

    def get_active_agenda_animations(self) -> list["AgendaAnimation"]:
        if not hasattr(self, "agenda_animations"):
            return []
        return [a for a in self.agenda_animations if not a.done]

    # --- Persistent agenda slide animations ---

    def add_persistent_agenda_animation(self, anim: "AgendaSlideAnimation"):
        if not hasattr(self, "persistent_agenda_animations"):
            self.persistent_agenda_animations: list[AgendaSlideAnimation] = []
        self.persistent_agenda_animations.append(anim)

    def get_persistent_agenda_animations(self) -> list["AgendaSlideAnimation"]:
        if not hasattr(self, "persistent_agenda_animations"):
            return []
        return [a for a in self.persistent_agenda_animations if not a.done]

    def get_persistent_agenda_factions(self) -> set[str]:
        """Return set of faction_ids that have active persistent agenda animations."""
        result = set()
        for a in self.get_persistent_agenda_animations():
            if not a.done:
                result.add(a.faction_id)
        return result

    def start_agenda_fadeout(self, spoils_only=False):
        """Trigger fade-out on active persistent agenda animations.

        Animations that haven't become active yet (still in delay) are
        cancelled immediately since they were never visible.

        If spoils_only is True, only fade spoils animations.
        """
        if not hasattr(self, "persistent_agenda_animations"):
            return
        for anim in self.persistent_agenda_animations:
            if not anim.done:
                if spoils_only and not anim.is_spoils:
                    continue
                if anim.active:
                    anim.start_fadeout()
                else:
                    anim.done = True

    def has_active_persistent_agenda_animations(self) -> bool:
        """Return True if any persistent agenda animations are currently visible."""
        if not hasattr(self, "persistent_agenda_animations"):
            return False
        return any(a.active and not a.done for a in self.persistent_agenda_animations)

    def get_spoils_count_for_faction(self, faction_id: str) -> int:
        """Count non-done spoils animations for a faction (for stacking index)."""
        if not hasattr(self, "persistent_agenda_animations"):
            return 0
        return sum(1 for a in self.persistent_agenda_animations
                   if not a.done and a.is_spoils and a.faction_id == faction_id)

    def is_all_done(self) -> bool:
        """Return True when no blocking animations are playing.

        Auto-fadeout animations (setup Change modifiers) are non-blocking
        since they manage their own lifecycle.
        """
        if hasattr(self, "persistent_agenda_animations"):
            if any(a.active and not a.done and a.auto_fadeout_after is None
                   for a in self.persistent_agenda_animations):
                return False
        if hasattr(self, "effect_animations") and any(not a.done for a in self.effect_animations):
            return False
        return True

    def has_active_spoils_animations(self) -> bool:
        """Return True if any active spoils animations exist."""
        if not hasattr(self, "persistent_agenda_animations"):
            return False
        return any(a.active and not a.done and a.is_spoils
                   for a in self.persistent_agenda_animations)

    # --- Effect animations ---

    def add_effect_animation(self, anim):
        if not hasattr(self, "effect_animations"):
            self.effect_animations: list = []
        self.effect_animations.append(anim)

    def get_active_effect_animations(self) -> list:
        if not hasattr(self, "effect_animations"):
            return []
        return [a for a in self.effect_animations if not a.done]


class AgendaAnimation:
    """Floating agenda icon that rises and fades over a faction's territory."""

    def __init__(self, image: "pygame.Surface", world_x: float, world_y: float,
                 delay: float = 0.0, duration: float = 1.5, rise_pixels: float = 40):
        self.image = image
        self.world_x = world_x
        self.world_y = world_y
        self.delay = delay
        self.duration = duration
        self.rise_pixels = rise_pixels
        self.elapsed = 0.0
        self.done = False

    def update(self, dt: float):
        self.elapsed += dt
        if self.elapsed >= self.delay + self.duration:
            self.done = True

    @property
    def active(self) -> bool:
        """True when past the delay and not yet done."""
        return self.elapsed >= self.delay and not self.done

    @property
    def progress(self) -> float:
        """0-1 progress through the visible portion of the animation."""
        if self.elapsed < self.delay:
            return 0.0
        t = (self.elapsed - self.delay) / self.duration
        return min(1.0, max(0.0, t))

    @property
    def alpha(self) -> int:
        """Alpha value: holds full for first 30%, then fades out."""
        p = self.progress
        if p < 0.3:
            return 255
        # Fade from 1.0 to 0.0 over remaining 70%
        fade = 1.0 - (p - 0.3) / 0.7
        return max(0, int(255 * fade))

    @property
    def y_offset(self) -> float:
        """Ease-out upward drift in pixels."""
        p = self.progress
        # Ease out: 1 - (1-t)^2
        eased = 1.0 - (1.0 - p) ** 2
        return -eased * self.rise_pixels


class AgendaSlideAnimation:
    """Agenda icon that slides from below faction name into the overview strip and persists."""

    SLIDE_DURATION = 0.75
    FADEOUT_DURATION = 3.0

    def __init__(self, image: "pygame.Surface", faction_id: str,
                 target_x: float, target_y: float,
                 start_x: float, start_y: float,
                 delay: float = 0.0,
                 auto_fadeout_after: float | None = None,
                 is_spoils: bool = False):
        self.image = image
        self.faction_id = faction_id
        self.is_spoils = is_spoils
        self.target_x = target_x
        self.target_y = target_y
        self.start_x = start_x
        self.start_y = start_y
        self.delay = delay
        self.auto_fadeout_after = auto_fadeout_after
        self.elapsed = 0.0
        self.done = False
        self._fading_out = False
        self._fadeout_elapsed = 0.0

    def update(self, dt: float):
        self.elapsed += dt
        if self._fading_out:
            self._fadeout_elapsed += dt
            if self._fadeout_elapsed >= self.FADEOUT_DURATION:
                self.done = True
        elif (self.auto_fadeout_after is not None
              and self.elapsed >= self.delay + self.SLIDE_DURATION + self.auto_fadeout_after):
            self.start_fadeout()

    def start_fadeout(self):
        if self._fading_out:
            return
        self._fading_out = True
        self._fadeout_elapsed = 0.0

    @property
    def active(self) -> bool:
        return self.elapsed >= self.delay and not self.done

    @property
    def slide_progress(self) -> float:
        """0-1 progress through the slide-in phase."""
        if self.elapsed < self.delay:
            return 0.0
        t = (self.elapsed - self.delay) / self.SLIDE_DURATION
        return min(1.0, max(0.0, t))

    @property
    def x(self) -> float:
        p = self.slide_progress
        eased = 1.0 - (1.0 - p) ** 3  # ease-out cubic
        return self.start_x + (self.target_x - self.start_x) * eased

    @property
    def y(self) -> float:
        p = self.slide_progress
        eased = 1.0 - (1.0 - p) ** 3
        return self.start_y + (self.target_y - self.start_y) * eased

    @property
    def alpha(self) -> int:
        if self._fading_out:
            t = min(1.0, self._fadeout_elapsed / self.FADEOUT_DURATION)
            return max(0, int(255 * (1.0 - t)))
        return 255


class TextAnimation:
    """Floating text that drifts and fades. Works in world or screen coords."""

    def __init__(self, text: str, x: float, y: float, color: tuple,
                 delay: float = 0.0, duration: float = 1.5,
                 drift_pixels: float = 20, direction: int = -1,
                 screen_space: bool = False):
        self.text = text
        self.x = x
        self.y = y
        self.color = color
        self.delay = delay
        self.duration = duration
        self.drift_pixels = drift_pixels
        self.direction = direction  # -1 = up, 1 = down
        self.screen_space = screen_space
        self.elapsed = 0.0
        self.done = False

    def update(self, dt: float):
        self.elapsed += dt
        if self.elapsed >= self.delay + self.duration:
            self.done = True

    @property
    def active(self) -> bool:
        return self.elapsed >= self.delay and not self.done

    @property
    def progress(self) -> float:
        if self.elapsed < self.delay:
            return 0.0
        t = (self.elapsed - self.delay) / self.duration
        return min(1.0, max(0.0, t))

    @property
    def alpha(self) -> int:
        p = self.progress
        if p < 0.3:
            return 255
        fade = 1.0 - (p - 0.3) / 0.7
        return max(0, int(255 * fade))

    @property
    def y_offset(self) -> float:
        p = self.progress
        eased = 1.0 - (1.0 - p) ** 2
        return self.direction * eased * self.drift_pixels


class ArrowAnimation:
    """Arrow between two hexes that fades in and out."""

    def __init__(self, from_hex: tuple, to_hex: tuple, color: tuple,
                 delay: float = 0.0, duration: float = 1.5):
        self.from_hex = from_hex
        self.to_hex = to_hex
        self.color = color
        self.delay = delay
        self.duration = duration
        self.elapsed = 0.0
        self.done = False
        self.screen_space = False  # always world-space

    def update(self, dt: float):
        self.elapsed += dt
        if self.elapsed >= self.delay + self.duration:
            self.done = True

    @property
    def active(self) -> bool:
        return self.elapsed >= self.delay and not self.done

    @property
    def progress(self) -> float:
        if self.elapsed < self.delay:
            return 0.0
        t = (self.elapsed - self.delay) / self.duration
        return min(1.0, max(0.0, t))

    @property
    def alpha(self) -> int:
        p = self.progress
        if p < 0.3:
            return 255
        fade = 1.0 - (p - 0.3) / 0.7
        return max(0, int(255 * fade))
