"""Main PyGame loop, scene manager, event dispatch."""

import pygame
from shared.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, MessageType, DEFAULT_HOST, DEFAULT_PORT,
)
from client.network import NetworkClient
from client.scenes.menu import MenuScene
from client.scenes.lobby import LobbyScene
from client.scenes.game_scene import GameScene
from client.scenes.results import ResultsScene


class App:
    """Main application: manages scenes, network, and the game loop."""

    def __init__(self, server_host: str = DEFAULT_HOST, server_port: int = DEFAULT_PORT):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.server_host = server_host
        self.server_port = server_port
        self.network = NetworkClient()
        self.my_spirit_id = ""

        self.scenes: dict = {}
        self.current_scene = None
        self._init_scenes()
        self.set_scene("menu")

    def _init_scenes(self):
        self.scenes["menu"] = MenuScene(self)
        self.scenes["lobby"] = LobbyScene(self)
        self.scenes["game"] = GameScene(self)
        self.scenes["results"] = ResultsScene(self)

    def set_scene(self, scene_name: str):
        self.current_scene = self.scenes.get(scene_name)

    def connect_to_server(self):
        if not self.network.connected:
            self.network.connect(self.server_host, self.server_port)

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            # Process pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
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

        self.network.disconnect()
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

        if msg_type == MessageType.GAME_OVER:
            # Check if game_over event is in phase_result events
            pass

        # Check for game over in phase results
        if msg_type == MessageType.PHASE_RESULT:
            events = payload.get("events", [])
            for event in events:
                if event.get("type") == "game_over":
                    game_scene = self.scenes.get("game")
                    if game_scene:
                        game_scene.handle_network(msg_type, payload)
                    results = self.scenes.get("results")
                    if results:
                        results.set_results(
                            event.get("winners", []),
                            event.get("scores", {}),
                            game_scene.spirits if game_scene else {},
                        )
                    self.set_scene("results")
                    return

        # Forward to current scene
        if self.current_scene and hasattr(self.current_scene, "handle_network"):
            self.current_scene.handle_network(msg_type, payload)
