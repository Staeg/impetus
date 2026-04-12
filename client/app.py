"""Main PyGame loop, scene manager, event dispatch."""

from __future__ import annotations
import asyncio
import os
import sys
import pygame
import shared.constants as shared_constants
import client.scenes.menu as menu_scene_module
import client.scenes.lobby as lobby_scene_module
import client.scenes.settings_scene as settings_scene_module
import client.scenes.results as results_scene_module
import client.scenes.game_scene as game_scene_module
import client.scenes.game_phase_controller as game_phase_controller_module
import client.scenes.animation_orchestrator as animation_orchestrator_module
import client.tutorial as tutorial_module
from shared.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, DEFAULT_HOST, DEFAULT_PORT,
)
from shared.protocol import S2C
from client.local_transport import LocalTransport
from client.network import NetworkClient
from client.replay import ReplayRecorder
from client.scenes.menu import MenuScene
from client.scenes.lobby import LobbyScene
from client.scenes.game_scene import GameScene
from client.scenes.results import ResultsScene
from client.scenes.settings_scene import SettingsScene
from client.settings import load_settings, save_settings


class App:
    """Main application: manages scenes, network, and the game loop."""

    def __init__(self, server_host: str = DEFAULT_HOST, server_port: int = DEFAULT_PORT,
                 network=None):
        pygame.init()
        self.settings = load_settings()
        settings = self.settings
        self.display_mode: str = self._load_display_mode(settings)
        self._toggle_restore_mode: str = (
            self.display_mode if self.display_mode != "fullscreen" else "borderless"
        )
        self.windowed_size: tuple[int, int] = self._load_windowed_size(settings)
        self.screen = self._apply_display_mode()
        pygame.display.set_caption(TITLE)
        pygame.key.set_repeat(400, 35)
        self.clock = pygame.time.Clock()
        self.running = True

        self.server_host = server_host
        self.server_port = server_port
        self.network = network or NetworkClient()
        self.my_spirit_id = ""
        self.local_transport: LocalTransport | None = None
        self.tutorial_mode: bool = False
        replay_log = os.environ.get("IMPETUS_REPLAY_LOG")
        self.replay_recorder = ReplayRecorder(replay_log) if replay_log else None

        self.scenes: dict = {}
        self.current_scene = None
        self._init_scenes()
        self._broadcast_display_size(*self.screen.get_size())
        self.set_scene("menu")

    def _load_windowed_size(self, settings: dict) -> tuple[int, int]:
        size = settings.get("windowed_size")
        if (isinstance(size, list) or isinstance(size, tuple)) and len(size) == 2:
            try:
                width = max(960, int(size[0]))
                height = max(640, int(size[1]))
                return (width, height)
            except (TypeError, ValueError):
                pass
        return (SCREEN_WIDTH, SCREEN_HEIGHT)

    def _load_display_mode(self, settings: dict) -> str:
        mode = settings.get("display_mode")
        if mode in {"windowed", "borderless", "fullscreen"}:
            return mode
        if settings.get("fullscreen"):
            return "fullscreen"
        return "borderless"

    @property
    def fullscreen(self) -> bool:
        return self.display_mode == "fullscreen"

    def _save_display_settings(self) -> None:
        if sys.platform == "emscripten":
            return
        self.settings["display_mode"] = self.display_mode
        self.settings["fullscreen"] = self.fullscreen
        self.settings["windowed_size"] = [self.windowed_size[0], self.windowed_size[1]]
        save_settings(self.settings)

    def _get_fullscreen_size(self) -> tuple[int, int]:
        display = pygame.display.get_desktop_sizes()
        if display:
            return display[0]
        info = pygame.display.Info()
        return (info.current_w, info.current_h)

    def _position_window(self, size: tuple[int, int]) -> None:
        """Place the current SDL window predictably after a mode switch."""
        if sys.platform == "emscripten":
            return
        try:
            from pygame._sdl2.video import Window
            window = Window.from_display_module()
        except Exception:
            return
        try:
            desktop_w, desktop_h = self._get_fullscreen_size()
            if self.display_mode == "borderless":
                window.size = size
                window.position = (0, 0)
            elif self.display_mode == "windowed":
                window.size = size
                pos_x = max(0, (desktop_w - size[0]) // 2)
                pos_y = max(0, (desktop_h - size[1]) // 2)
                window.position = (pos_x, pos_y)
        except Exception:
            pass

    def _apply_display_mode(self) -> pygame.Surface:
        if sys.platform == "emscripten":
            # SCALED conflicts with the CSS resize handler in WASM; use 0.
            flags = 0
            size = (SCREEN_WIDTH, SCREEN_HEIGHT)
        else:
            flags = 0
            size = self.windowed_size
            if self.display_mode == "windowed":
                flags |= pygame.RESIZABLE
                os.environ["SDL_VIDEO_CENTERED"] = "1"
                os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
            elif self.display_mode == "borderless":
                flags |= pygame.NOFRAME
                size = self._get_fullscreen_size()
                os.environ["SDL_VIDEO_CENTERED"] = "0"
                os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
            elif self.display_mode == "fullscreen":
                flags |= pygame.FULLSCREEN
                size = self._get_fullscreen_size()
                os.environ["SDL_VIDEO_CENTERED"] = "0"
                os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
        screen = pygame.display.set_mode(size, flags)
        if self.display_mode == "windowed":
            self.windowed_size = screen.get_size()
        self._position_window(screen.get_size())
        return screen

    def set_display_mode(self, mode: str) -> None:
        if mode not in {"windowed", "borderless", "fullscreen"}:
            return
        self.display_mode = mode
        if mode != "fullscreen":
            self._toggle_restore_mode = mode
        self.screen = self._apply_display_mode()
        self._broadcast_display_size(*self.screen.get_size())
        self._save_display_settings()

    def toggle_fullscreen(self):
        if self.display_mode == "fullscreen":
            self.set_display_mode(self._toggle_restore_mode)
        else:
            self._toggle_restore_mode = self.display_mode
            self.set_display_mode("fullscreen")

    def _handle_window_resize(self, size: tuple[int, int]) -> None:
        if self.display_mode != "windowed" or sys.platform == "emscripten":
            return
        width = max(960, int(size[0]))
        height = max(640, int(size[1]))
        self.windowed_size = (width, height)
        self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self._position_window(self.screen.get_size())
        self._broadcast_display_size(*self.screen.get_size())
        self._save_display_settings()

    def _broadcast_display_size(self, width: int, height: int) -> None:
        shared_constants.SCREEN_WIDTH = width
        shared_constants.SCREEN_HEIGHT = height
        modules = [
            menu_scene_module,
            lobby_scene_module,
            settings_scene_module,
            results_scene_module,
            game_scene_module,
            game_phase_controller_module,
            animation_orchestrator_module,
            tutorial_module,
        ]
        for module in modules:
            setattr(module, "SCREEN_WIDTH", width)
            setattr(module, "SCREEN_HEIGHT", height)
            recompute = getattr(module, "_recompute_layout_globals", None)
            if callable(recompute):
                recompute()
        for scene in self.scenes.values():
            on_resize = getattr(scene, "on_resize", None)
            if callable(on_resize):
                on_resize(width, height)

    def _init_scenes(self):
        self.scenes["menu"] = MenuScene(self)
        self.scenes["lobby"] = LobbyScene(self)
        self.scenes["game"] = GameScene(self)
        self.scenes["results"] = ResultsScene(self)
        self.scenes["settings"] = SettingsScene(self)

    def set_scene(self, scene_name: str):
        self.current_scene = self.scenes.get(scene_name)

    def start_local_transport(self) -> None:
        if self.local_transport:
            self.local_transport.stop()
        transport = LocalTransport()
        transport.start()
        self.local_transport = transport
        self.network = transport

    def stop_local_transport(self) -> None:
        if self.local_transport:
            self.local_transport.stop()
            self.local_transport = None
        self.network = NetworkClient()

    def connect_to_server(self):
        if not self.network.connected:
            self.network.connect(self.server_host, self.server_port)

    async def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            # Process pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
                if event.type == pygame.VIDEORESIZE:
                    self._handle_window_resize(event.size)
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                    continue
                if self.current_scene:
                    self.current_scene.handle_event(event)

            # Process network messages
            for msg_type, payload in self.network.poll_all():
                self._handle_network_message(msg_type, payload)

            # Update
            if self.current_scene:
                self.current_scene.update(dt)

            # Render
            if self.current_scene:
                self.current_scene.render(self.screen)

            pygame.display.flip()
            await asyncio.sleep(0)

        self.network.disconnect()
        self.stop_local_transport()
        pygame.quit()

    def _handle_network_message(self, msg_type: str, payload: dict):
        scene_name = type(self.current_scene).__name__ if self.current_scene else "None"
        print(f"[app] Message: {msg_type} -> {scene_name}")
        if self.replay_recorder:
            self.replay_recorder.record(msg_type, payload)
        # Handle scene transitions
        if msg_type == S2C.GAME_START:
            self.set_scene("game")
            # Forward to game scene
            self.current_scene.handle_network(msg_type, payload)
            return

        # Forward to current scene
        if self.current_scene and hasattr(self.current_scene, "handle_network"):
            self.current_scene.handle_network(msg_type, payload)
