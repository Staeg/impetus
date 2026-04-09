"""Replay recording and playback helpers for client debugging."""

from __future__ import annotations

import json
import time
from pathlib import Path


class ReplayRecorder:
    """Append inbound network traffic to a JSONL replay file."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, msg_type: str, payload: dict) -> None:
        entry = {
            "t": round(time.time(), 6),
            "type": msg_type,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


class ReplayTransport:
    """Read a recorded replay file and feed it to the app as inbound messages."""

    def __init__(self, path: str):
        replay_path = Path(path)
        self._messages: list[tuple[str, dict]] = []
        with replay_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                self._messages.append((entry["type"], entry.get("payload", {})))
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int) -> None:
        # Replay is already "connected" to its recorded stream.
        return

    def poll(self):
        if not self._messages:
            return None
        return self._messages.pop(0)

    def poll_all(self) -> list[tuple[str, dict]]:
        if not self._messages:
            return []
        next_message = self._messages.pop(0)
        if not self._messages:
            self._connected = False
        return [next_message]

    def send(self, msg_type: str, payload: dict | None = None) -> None:
        # Replays are read-only.
        return

    def disconnect(self) -> None:
        self._connected = False
