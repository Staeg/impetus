"""In-process transport: replaces loopback WebSocket for single-player."""

import asyncio
import sys
import threading

from shared.protocol import create_message, parse_message


class FakeWebSocket:
    """Mimics websockets.ServerConnection for use with GameServer.handle_connection()."""

    remote_address = ("local", 0)

    def __init__(self, incoming: asyncio.Queue, outgoing: asyncio.Queue):
        self._incoming = incoming   # client→server messages
        self._outgoing = outgoing   # server→client messages

    async def send(self, message: str):
        await self._outgoing.put(message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self._incoming.get()
        if msg is None:             # None sentinel = disconnect
            raise StopAsyncIteration
        return msg


class LocalTransport:
    """Drop-in replacement for NetworkClient for single-player.

    Desktop: runs GameServer.handle_connection() in a background asyncio event loop
    on a daemon thread (communicating via in-process queues).

    WASM (sys.platform == "emscripten"): schedules handle_connection() as a
    concurrent asyncio.Task in the same event loop as the game loop.
    """

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._task: asyncio.Task | None = None
        self._client_to_server: asyncio.Queue | None = None
        self._server_to_client: asyncio.Queue | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._client_to_server = asyncio.Queue()
        self._server_to_client = asyncio.Queue()
        self._connected = True
        if sys.platform == "emscripten":
            # WASM: run server as a concurrent task in the current event loop.
            # No threads — everything shares the browser's single event loop.
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._serve())
        else:
            # Desktop: run server in a dedicated background event loop on a daemon thread.
            if self._thread and self._thread.is_alive():
                self.stop()
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        from server.server import GameServer
        server = GameServer("local", 0)
        fake_ws = FakeWebSocket(self._client_to_server, self._server_to_client)
        await server.handle_connection(fake_ws)

    def send(self, msg_type, payload=None):
        msg = create_message(msg_type, payload)
        if sys.platform == "emscripten":
            # WASM: same event loop — direct put is safe.
            if self._client_to_server:
                self._client_to_server.put_nowait(msg)
        else:
            # Desktop: cross-thread put via call_soon_threadsafe.
            if self._loop and self._client_to_server:
                self._loop.call_soon_threadsafe(self._client_to_server.put_nowait, msg)

    def poll(self):
        """Non-blocking: get one (msg_type, payload) or None."""
        if self._server_to_client and not self._server_to_client.empty():
            raw = self._server_to_client.get_nowait()
            return parse_message(raw) if raw else None
        return None

    def poll_all(self):
        """Non-blocking: drain all pending (msg_type, payload) pairs."""
        msgs = []
        if self._server_to_client:
            while not self._server_to_client.empty():
                raw = self._server_to_client.get_nowait()
                if raw:
                    msgs.append(parse_message(raw))
        return msgs

    def connect(self, host, port):
        pass  # no-op — already connected via start()

    def disconnect(self):
        self._connected = False
        if sys.platform == "emscripten":
            if self._client_to_server:
                self._client_to_server.put_nowait(None)
        else:
            if self._loop and self._client_to_server:
                self._loop.call_soon_threadsafe(self._client_to_server.put_nowait, None)

    def stop(self):
        self.disconnect()
        if sys.platform == "emscripten":
            if self._task and not self._task.done():
                self._task.cancel()
        else:
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._loop.stop)
