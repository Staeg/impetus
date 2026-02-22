"""Simple animation and tween system."""

import time


def ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


def ease_out_quad(t):
    return 1.0 - (1.0 - t) ** 2


def fade_alpha(progress, hold=0.3):
    if progress < hold:
        return 255
    return max(0, int(255 * (1.0 - (progress - hold) / (1.0 - hold))))


class BaseAnimation:
    """Base class for delay/duration animations with active, progress, alpha."""

    def __init__(self, delay=0.0, duration=1.5):
        self.delay = delay
        self.duration = duration
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
        return fade_alpha(self.progress)


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
        t = ease_out_cubic(t)
        if self.elapsed >= self.duration:
            self.done = True
        return self.start_val + (self.end_val - self.start_val) * t

    @property
    def value(self) -> float:
        t = min(1.0, self.elapsed / self.duration) if self.duration > 0 else 1.0
        t = ease_out_cubic(t)
        return self.start_val + (self.end_val - self.start_val) * t


class AnimationManager:
    """Manages a collection of animations."""

    def __init__(self):
        self.tweens: dict[str, Tween] = {}
        self.flash_timers: dict[str, float] = {}
        self.agenda_animations: list[AgendaAnimation] = []
        self.effect_animations: list = []
        self.persistent_agenda_animations: list[AgendaSlideAnimation] = []

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

        for anim in self.agenda_animations:
            anim.update(dt)
        self.agenda_animations = [a for a in self.agenda_animations if not a.done]

        for anim in self.effect_animations:
            anim.update(dt)
        self.effect_animations = [a for a in self.effect_animations if not a.done]

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
        self.agenda_animations.append(anim)

    def get_active_agenda_animations(self) -> list["AgendaAnimation"]:
        return [a for a in self.agenda_animations if not a.done]

    # --- Persistent agenda slide animations ---

    def add_persistent_agenda_animation(self, anim: "AgendaSlideAnimation"):
        self.persistent_agenda_animations.append(anim)

    def get_persistent_agenda_animations(self) -> list["AgendaSlideAnimation"]:
        return [a for a in self.persistent_agenda_animations if not a.done]

    def get_persistent_agenda_factions(self) -> set[str]:
        """Return set of faction_ids that have active persistent agenda animations."""
        result = set()
        for a in self.get_persistent_agenda_animations():
            if not a.done:
                result.add(a.faction_id)
        return result

    def has_active_persistent_agenda_animations(self) -> bool:
        """Return True if any persistent agenda animations are currently visible."""
        return any(a.active and not a.done for a in self.persistent_agenda_animations)

    def get_spoils_count_for_faction(self, faction_id: str) -> int:
        """Count non-done spoils animations for a faction (for stacking index)."""
        return sum(1 for a in self.persistent_agenda_animations
                   if not a.done and a.is_spoils and a.faction_id == faction_id)

    def is_all_done(self) -> bool:
        """Return True when no animations are actively in motion.

        Settled persistent animations (slide complete, not fading) are
        not considered blocking.
        """
        if any(not a.done and not a.is_settled
               for a in self.persistent_agenda_animations):
            return False
        if any(not a.done for a in self.effect_animations):
            return False
        return True

    def has_active_spoils_animations(self) -> bool:
        """Return True if any active spoils animations exist."""
        return any(a.active and not a.done and a.is_spoils
                   for a in self.persistent_agenda_animations)

    # --- Effect animations ---

    def add_effect_animation(self, anim):
        self.effect_animations.append(anim)

    def get_active_effect_animations(self) -> list:
        return [a for a in self.effect_animations if not a.done]


class AgendaAnimation(BaseAnimation):
    """Floating agenda icon that rises and fades over a faction's territory."""

    def __init__(self, image: "pygame.Surface", world_x: float, world_y: float,
                 delay: float = 0.0, duration: float = 1.5, rise_pixels: float = 40):
        super().__init__(delay=delay, duration=duration)
        self.image = image
        self.world_x = world_x
        self.world_y = world_y
        self.rise_pixels = rise_pixels

    @property
    def y_offset(self) -> float:
        """Ease-out upward drift in pixels."""
        eased = ease_out_quad(self.progress)
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
                 is_spoils: bool = False,
                 agenda_type: str = ""):
        self.image = image
        self.faction_id = faction_id
        self.is_spoils = is_spoils
        self.agenda_type = agenda_type
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
        # Hex reveal: when set, the display hex map updates after hex_reveal_delay seconds
        self.hex_reveal: tuple[int, int] | None = None
        self.hex_reveal_faction: str | None = None
        self.hex_reveal_delay: float = 0.0   # extra seconds after anim.delay before revealing
        self._hex_revealed: bool = False
        # Gold reveal: display gold updates when this anim becomes active
        self.gold_delta: int = 0
        self.gold_delta_faction: str | None = None
        self.gold_deltas: list[tuple[str, int]] = []
        self._gold_applied: bool = False
        # War reveal: display war updates when this anim becomes active
        self.war_reveals: list[dict] | None = None
        self._wars_revealed: bool = False
        # Change modifier reveal: display change_modifiers updates when this anim becomes active
        self.change_modifier: str | None = None
        self._change_modifier_applied: bool = False

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
    def is_settled(self) -> bool:
        """True when slide is complete and animation is just displayed (not fading)."""
        return self.active and not self._fading_out and self.slide_progress >= 1.0

    @property
    def slide_progress(self) -> float:
        """0-1 progress through the slide-in phase."""
        if self.elapsed < self.delay:
            return 0.0
        t = (self.elapsed - self.delay) / self.SLIDE_DURATION
        return min(1.0, max(0.0, t))

    @property
    def x(self) -> float:
        eased = ease_out_cubic(self.slide_progress)
        return self.start_x + (self.target_x - self.start_x) * eased

    @property
    def y(self) -> float:
        eased = ease_out_cubic(self.slide_progress)
        return self.start_y + (self.target_y - self.start_y) * eased

    @property
    def alpha(self) -> int:
        if self._fading_out:
            t = min(1.0, self._fadeout_elapsed / self.FADEOUT_DURATION)
            return max(0, int(255 * (1.0 - t)))
        return 255


class TextAnimation(BaseAnimation):
    """Floating text that drifts and fades. Works in world or screen coords."""

    def __init__(self, text: str, x: float, y: float, color: tuple,
                 delay: float = 0.0, duration: float = 1.5,
                 drift_pixels: float = 20, direction: int = -1,
                 screen_space: bool = False):
        super().__init__(delay=delay, duration=duration)
        self.text = text
        self.x = x
        self.y = y
        self.color = color
        self.drift_pixels = drift_pixels
        self.direction = direction  # -1 = up, 1 = down
        self.screen_space = screen_space

    @property
    def y_offset(self) -> float:
        eased = ease_out_quad(self.progress)
        return self.direction * eased * self.drift_pixels


class ArrowAnimation(BaseAnimation):
    """Arrow between two hexes that fades in and out."""

    def __init__(self, from_hex: tuple, to_hex: tuple, color: tuple,
                 delay: float = 0.0, duration: float = 1.5):
        super().__init__(delay=delay, duration=duration)
        self.from_hex = from_hex
        self.to_hex = to_hex
        self.color = color
        self.screen_space = False  # always world-space


class IdolBeamAnimation(BaseAnimation):
    """Glowing beam that travels from an idol (world-space) to the VP counter (screen-space)."""

    TRAIL_FRAC = 1.0  # fraction of the full path shown as trail at any moment

    def __init__(self, start_world_x: float, start_world_y: float,
                 end_screen_x: float, end_screen_y: float,
                 color: tuple,
                 delay: float = 0.0, duration: float = 0.75):
        super().__init__(delay=delay, duration=duration)
        self.start_world_x = start_world_x
        self.start_world_y = start_world_y
        self.end_screen_x = end_screen_x
        self.end_screen_y = end_screen_y
        self.color = color
        self.screen_space = True  # rendered in the screen-space pass

    @property
    def alpha(self) -> int:
        # Stay full brightness until 75% through the journey, then fade out quickly
        return fade_alpha(self.progress, hold=0.75)
