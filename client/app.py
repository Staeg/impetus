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
from shared.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, DEFAULT_HOST, DEFAULT_PORT,
)
from shared.protocol import C2S, S2C
from client.local_transport import LocalTransport
from client.network import NetworkClient
from client.replay import ReplayRecorder
from client.scenes.menu import MenuScene
from client.scenes.lobby import LobbyScene
from client.scenes.game_scene import GameScene
from client.scenes.results import ResultsScene
from client.scenes.settings_scene import SettingsScene
from client.settings import load_settings, save_settings
from client.tutorials.catalog import TUTORIAL_CATALOG
from client.tutorials.runtime import TutorialRuntimeController
from client.tutorials.transport import LocalTutorialTransport


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
        self.local_transport = None
        self.tutorial_runtime: TutorialRuntimeController | None = None
        self.multiplayer_rejoins = self._load_multiplayer_rejoins(settings)
        self.multiplayer_rejoin = None
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

    def _session_key(self, server_host: str, server_port: int, room_code: str, player_name: str) -> str:
        return "|".join([
            server_host.strip().casefold(),
            str(int(server_port)),
            room_code.strip().upper(),
            player_name.strip().casefold(),
        ])

    def _coerce_multiplayer_rejoin(self, saved: dict | None) -> dict | None:
        if not isinstance(saved, dict):
            return None
        required = {"player_name", "room_code", "reconnect_token", "server_host", "server_port"}
        if not required.issubset(saved):
            return None
        session = dict(saved)
        session["player_name"] = str(session["player_name"]).strip()
        session["room_code"] = str(session["room_code"]).strip().upper()
        session["server_host"] = str(session["server_host"]).strip()
        session["server_port"] = int(session["server_port"])
        session["reconnect_token"] = str(session["reconnect_token"])
        if not session["player_name"] or not session["room_code"] or not session["server_host"]:
            return None
        return session

    def _load_multiplayer_rejoins(self, settings: dict) -> dict[str, dict]:
        sessions: dict[str, dict] = {}
        saved_map = settings.get("multiplayer_rejoins")
        if isinstance(saved_map, dict):
            for saved in saved_map.values():
                session = self._coerce_multiplayer_rejoin(saved)
                if session:
                    sessions[self._session_key(
                        session["server_host"],
                        session["server_port"],
                        session["room_code"],
                        session["player_name"],
                    )] = session
        legacy = self._coerce_multiplayer_rejoin(settings.get("multiplayer_rejoin"))
        if legacy:
            sessions[self._session_key(
                legacy["server_host"],
                legacy["server_port"],
                legacy["room_code"],
                legacy["player_name"],
            )] = legacy
        return sessions

    @property
    def fullscreen(self) -> bool:
        return self.display_mode == "fullscreen"

    def _save_display_settings(self) -> None:
        if sys.platform == "emscripten":
            return
        self.settings["display_mode"] = self.display_mode
        self.settings["fullscreen"] = self.fullscreen
        self.settings["windowed_size"] = [self.windowed_size[0], self.windowed_size[1]]
        if self.multiplayer_rejoins:
            self.settings["multiplayer_rejoins"] = {
                key: dict(session)
                for key, session in self.multiplayer_rejoins.items()
            }
        else:
            self.settings.pop("multiplayer_rejoins", None)
        self.settings.pop("multiplayer_rejoin", None)
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
                # `set_mode(..., NOFRAME)` already recreated the window at the
                # requested desktop size. Resizing the SDL window again here
                # has been unstable when returning from exclusive fullscreen.
                window.position = (0, 0)
            elif self.display_mode == "windowed":
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
        if mode == self.display_mode:
            return
        self.display_mode = mode
        if mode != "fullscreen":
            self._toggle_restore_mode = mode
        self.screen = self._apply_display_mode()
        pygame.event.pump()
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

    def get_saved_multiplayer_rejoin(
        self,
        player_name: str | None,
        room_code: str | None,
        server_host: str | None,
        server_port: int | None = None,
    ) -> dict | None:
        if not player_name or not room_code or not server_host or server_port is None:
            return None
        return self.multiplayer_rejoins.get(
            self._session_key(server_host, server_port, room_code, player_name)
        )

    def has_saved_multiplayer_rejoin(
        self,
        player_name: str | None = None,
        room_code: str | None = None,
        server_host: str | None = None,
        server_port: int | None = None,
    ) -> bool:
        if player_name is None and room_code is None and server_host is None and server_port is None:
            return bool(self.multiplayer_rejoins)
        return self.get_saved_multiplayer_rejoin(player_name, room_code, server_host, server_port) is not None

    def _set_network_rejoin_payload(self, payload: dict | None) -> None:
        setter = getattr(self.network, "set_rejoin_payload", None)
        if callable(setter):
            setter(payload)

    def _clear_network_rejoin_payload(self) -> None:
        clearer = getattr(self.network, "clear_rejoin_payload", None)
        if callable(clearer):
            clearer()

    def remember_multiplayer_session(self, payload: dict) -> None:
        session = {
            "player_name": payload["player_name"],
            "room_code": payload["room_code"],
            "reconnect_token": payload["reconnect_token"],
            "server_host": payload["server_host"],
            "server_port": int(payload["server_port"]),
        }
        session_key = self._session_key(
            session["server_host"],
            session["server_port"],
            session["room_code"],
            session["player_name"],
        )
        self.multiplayer_rejoins[session_key] = session
        self.multiplayer_rejoin = session
        self._set_network_rejoin_payload({
            "player_name": session["player_name"],
            "room_code": session["room_code"],
            "reconnect_token": session["reconnect_token"],
        })
        self._save_display_settings()

    def clear_saved_multiplayer_rejoin(
        self,
        player_name: str | None = None,
        room_code: str | None = None,
        server_host: str | None = None,
        server_port: int | None = None,
    ) -> None:
        session = None
        if player_name and room_code and server_host and server_port is not None:
            session = {
                "player_name": player_name,
                "room_code": room_code,
                "server_host": server_host,
                "server_port": server_port,
            }
        elif self.multiplayer_rejoin:
            session = self.multiplayer_rejoin
        if session:
            self.multiplayer_rejoins.pop(self._session_key(
                session["server_host"],
                int(session["server_port"]),
                session["room_code"],
                session["player_name"],
            ), None)
        else:
            self.multiplayer_rejoins.clear()
        self.multiplayer_rejoin = None
        self._clear_network_rejoin_payload()
        self._save_display_settings()

    def rejoin_saved_multiplayer_game(
        self,
        player_name: str,
        room_code: str,
        server_host: str,
        server_port: int,
    ) -> None:
        session = self.get_saved_multiplayer_rejoin(player_name, room_code, server_host, server_port)
        if not session:
            return
        session = dict(session)
        self.multiplayer_rejoin = session
        self.server_host = session["server_host"]
        self.server_port = int(session["server_port"])
        menu = self.scenes.get("menu")
        if menu:
            menu.player_name = session["player_name"]
            menu.room_code = session["room_code"]
            menu.host_code = session["room_code"]
            menu.server_address = f'{session["server_host"]}:{session["server_port"]}'
            menu.active_flow = "join_multiplayer"
            menu.active_input = "room_code"
        self.connect_to_server()
        self.network.send(C2S.JOIN_GAME, {
            "player_name": session["player_name"],
            "room_code": session["room_code"],
            "reconnect_token": session["reconnect_token"],
        })
        self.set_scene("lobby")

    def leave_game_to_menu(self) -> None:
        self.return_to_main_menu(clear_saved_multiplayer=True)

    def _clear_tutorial_runtime(self) -> None:
        if self.tutorial_runtime:
            self.tutorial_runtime.detach_scene()
        self.tutorial_runtime = None
        game_scene = self.scenes.get("game")
        clear_tutorial_state = getattr(game_scene, "clear_tutorial_state", None)
        if callable(clear_tutorial_state):
            clear_tutorial_state()

    def start_local_transport(self) -> None:
        self.stop_local_transport()
        self._clear_network_rejoin_payload()
        self.multiplayer_rejoin = None
        transport = LocalTransport()
        transport.start()
        self.local_transport = transport
        self.network = transport

    def stop_local_transport(self) -> None:
        if self.local_transport:
            self.local_transport.stop()
            self.local_transport = None
        self.network = NetworkClient()
        self._clear_tutorial_runtime()
        if self.multiplayer_rejoin:
            self._set_network_rejoin_payload({
                "player_name": self.multiplayer_rejoin["player_name"],
                "room_code": self.multiplayer_rejoin["room_code"],
                "reconnect_token": self.multiplayer_rejoin["reconnect_token"],
            })

    def start_tutorial(self, campaign_id: str, scenario_index: int = 0) -> None:
        catalog_entry = TUTORIAL_CATALOG[campaign_id]
        scenario = catalog_entry.entry_scenarios[scenario_index]
        bootstrap_result = scenario.bootstrap()
        self.stop_local_transport()
        transport = LocalTutorialTransport(bootstrap_result)
        transport.start()
        self.local_transport = transport
        self.network = transport
        self.my_spirit_id = bootstrap_result.human_spirit_id
        self.tutorial_runtime = TutorialRuntimeController(self, campaign_id, scenario_index=scenario_index)

    def exit_tutorial_to_menu(self) -> None:
        self.return_to_main_menu(clear_saved_multiplayer=True)

    def connect_to_server(self):
        if not self.network.connected:
            self.network.connect(self.server_host, self.server_port)

    def return_to_main_menu(self, clear_saved_multiplayer: bool) -> None:
        menu_state = {}
        menu_scene = self.scenes.get("menu")
        if menu_scene and hasattr(menu_scene, "get_persistent_state"):
            menu_state = menu_scene.get_persistent_state()
        if self.local_transport:
            self.stop_local_transport()
        else:
            self._clear_tutorial_runtime()
            self._clear_network_rejoin_payload()
            self.network.disconnect()
            self.network = NetworkClient()
        self.my_spirit_id = ""
        if clear_saved_multiplayer:
            self.clear_saved_multiplayer_rejoin()
        self._init_scenes()
        self._broadcast_display_size(*self.screen.get_size())
        menu_scene = self.scenes.get("menu")
        if menu_scene and hasattr(menu_scene, "apply_persistent_state"):
            menu_scene.apply_persistent_state(menu_state)
        if not clear_saved_multiplayer and self.multiplayer_rejoin:
            self._set_network_rejoin_payload({
                "player_name": self.multiplayer_rejoin["player_name"],
                "room_code": self.multiplayer_rejoin["room_code"],
                "reconnect_token": self.multiplayer_rejoin["reconnect_token"],
            })
        self.set_scene("menu")

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
        if msg_type == S2C.SESSION_INFO:
            session_payload = dict(payload)
            session_payload["server_host"] = self.server_host
            session_payload["server_port"] = self.server_port
            self.my_spirit_id = payload.get("spirit_id", self.my_spirit_id)
            self.remember_multiplayer_session(session_payload)
            return
        # Handle scene transitions
        if msg_type == S2C.GAME_START:
            self.set_scene("game")
            # Forward to game scene
            self.current_scene.handle_network(msg_type, payload)
            return

        # Forward to current scene
        if self.current_scene and hasattr(self.current_scene, "handle_network"):
            self.current_scene.handle_network(msg_type, payload)
