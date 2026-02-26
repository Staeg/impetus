"""Mouse/keyboard mapping, hex picking, UI interaction."""

from __future__ import annotations
import pygame
from shared.hex_utils import pixel_to_axial


class InputHandler:
    """Translates raw pygame events into game actions."""

    def __init__(self):
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = 1.0  # Fixed, no longer adjustable
        self._dragging = False
        self._drag_start = (0, 0)
        self._drag_cam_start = (0.0, 0.0)

    def screen_to_world(self, sx: int, sy: int, screen_w: int, screen_h: int) -> tuple[float, float]:
        """Convert screen pixel to world coordinates."""
        wx = (sx - screen_w / 2) + self.camera_x
        wy = (sy - screen_h / 2) + self.camera_y
        return wx, wy

    def world_to_screen(self, wx: float, wy: float, screen_w: int, screen_h: int) -> tuple[int, int]:
        """Convert world coordinates to screen pixel."""
        sx = int((wx - self.camera_x) + screen_w / 2)
        sy = int((wy - self.camera_y) + screen_h / 2)
        return sx, sy

    def screen_to_hex(self, sx: int, sy: int, screen_w: int, screen_h: int,
                      hex_size: float) -> tuple[int, int]:
        """Convert screen pixel to hex axial coordinate."""
        wx, wy = self.screen_to_world(sx, sy, screen_w, screen_h)
        return pixel_to_axial(wx, wy, hex_size)

    def handle_camera_event(self, event: pygame.event.Event):
        """Handle camera pan from mouse events."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2:  # Middle mouse
                self._dragging = True
                self._drag_start = event.pos
                self._drag_cam_start = (self.camera_x, self.camera_y)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self._dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                dx = event.pos[0] - self._drag_start[0]
                dy = event.pos[1] - self._drag_start[1]
                self.camera_x = self._drag_cam_start[0] - dx
                self.camera_y = self._drag_cam_start[1] - dy
