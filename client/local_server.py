"""Embedded single-player server: runs GameServer on a background thread."""

import asyncio
import socket
import threading


def _find_free_port() -> int:
    """Ask the OS for an available port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalServer:
    """Runs a GameServer in a background asyncio thread for single-player use."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.port: int = 0

    def start(self) -> int:
        """Start the embedded server. Returns the port it is listening on."""
        self.port = _find_free_port()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self.port

    def _run(self):
        from server.server import GameServer
        asyncio.set_event_loop(self._loop)
        server = GameServer("127.0.0.1", self.port)
        try:
            self._loop.run_until_complete(server.run())
        except Exception:
            pass

    def stop(self):
        """Stop the embedded server."""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop = None
        self._thread = None
        self.port = 0
