"""WebSocket client: background thread, message queue, reconnection."""

import asyncio
import json
import threading
import queue
import time
from typing import Optional
import websockets

from shared.constants import MessageType
from shared.protocol import create_message, parse_message


class NetworkClient:
    """Manages WebSocket connection on a background thread."""

    def __init__(self):
        self.incoming: queue.Queue = queue.Queue()
        self._outgoing: queue.Queue = queue.Queue()
        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._uri = ""
        self._should_stop = False

    def connect(self, host: str, port: int):
        self._uri = f"ws://{host}:{port}"
        self._should_stop = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_and_listen())

    async def _connect_and_listen(self):
        retry_delay = 1
        while not self._should_stop:
            try:
                async with websockets.connect(self._uri) as ws:
                    self._ws = ws
                    self._connected = True
                    retry_delay = 1
                    print(f"[net] Connected to {self._uri}")
                    # Flush any messages queued before connection was ready
                    while not self._outgoing.empty():
                        try:
                            queued = self._outgoing.get_nowait()
                            await ws.send(queued)
                            print(f"[net] Flushed queued message")
                        except queue.Empty:
                            break
                    try:
                        async for message in ws:
                            try:
                                msg_type, payload = parse_message(message)
                                self.incoming.put((msg_type, payload))
                                print(f"[net] Received: {msg_type.value}")
                            except Exception as e:
                                print(f"[net] Parse error: {e}")
                    except websockets.exceptions.ConnectionClosed:
                        print("[net] Connection closed")
                    finally:
                        self._connected = False
                        self._ws = None
            except Exception as e:
                print(f"[net] Connection error: {e}")

            if not self._should_stop:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    def send(self, msg_type: MessageType, payload: dict = None):
        """Send a message to the server (called from main thread).

        If not yet connected, queues the message to be sent once the connection is ready.
        """
        message = create_message(msg_type, payload)
        if self._ws and self._connected and self._loop:
            asyncio.run_coroutine_threadsafe(self._ws.send(message), self._loop)
        else:
            self._outgoing.put(message)

    def poll(self) -> Optional[tuple[MessageType, dict]]:
        """Non-blocking poll for the next incoming message."""
        try:
            return self.incoming.get_nowait()
        except queue.Empty:
            return None

    def poll_all(self) -> list[tuple[MessageType, dict]]:
        """Poll all pending incoming messages."""
        messages = []
        while True:
            msg = self.poll()
            if msg is None:
                break
            messages.append(msg)
        return messages

    @property
    def connected(self) -> bool:
        return self._connected

    def disconnect(self):
        self._should_stop = True
        if self._ws and self._loop:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
        self._connected = False
