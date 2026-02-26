"""Main PyGame loop, scene manager, event dispatch."""

from __future__ import annotations
import asyncio
import sys
import pygame
from shared.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, MessageType, DEFAULT_HOST, DEFAULT_PORT,
)
from client.local_transport import LocalTransport
from client.network import NetworkClient
from client.scenes.menu import MenuScene
from client.scenes.lobby import LobbyScene
from client.scenes.game_scene import GameScene
from client.scenes.results import ResultsScene
from client.scenes.settings_scene import SettingsScene
from client.settings import load_settings, save_settings


class App:
    """Main application: manages scenes, network, and the game loop."""

    def __init__(self, server_host: str = DEFAULT_HOST, server_port: int = DEFAULT_PORT):
        pygame.init()
        settings = load_settings()
        self.fullscreen: bool = settings.get("fullscreen", False)
        self.screen = self._apply_display_mode()
        pygame.display.set_caption(TITLE)
        pygame.key.set_repeat(400, 35)
        self.clock = pygame.time.Clock()
        self.running = True

        self.server_host = server_host
        self.server_port = server_port
        self.network = NetworkClient()
        self.my_spirit_id = ""
        self.local_transport: LocalTransport | None = None
        self.tutorial_mode: bool = False

        self.scenes: dict = {}
        self.current_scene = None
        self._init_scenes()
        self.set_scene("menu")

    def _apply_display_mode(self) -> pygame.Surface:
        if sys.platform == "emscripten":
            # SCALED conflicts with the CSS resize handler in WASM; use 0.
            flags = 0
        else:
            flags = pygame.SCALED
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        return pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        pygame.display.toggle_fullscreen()
        if sys.platform != "emscripten":
            save_settings({"fullscreen": self.fullscreen})

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

    def _handle_network_message(self, msg_type: MessageType, payload: dict):
        scene_name = type(self.current_scene).__name__ if self.current_scene else "None"
        print(f"[app] Message: {msg_type.value} -> {scene_name}")
        # Handle scene transitions
        if msg_type == MessageType.GAME_START:
            self.set_scene("game")
            # Forward to game scene
            self.current_scene.handle_network(msg_type, payload)
            return

        # Forward to current scene
        if self.current_scene and hasattr(self.current_scene, "handle_network"):
            self.current_scene.handle_network(msg_type, payload)
