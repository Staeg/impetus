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

    def get_tween_value(self, key: str, default: float = 0.0) -> float:
        if key in self.tweens:
            return self.tweens[key].value
        return default

    def is_flashing(self, key: str) -> bool:
        return key in self.flash_timers
