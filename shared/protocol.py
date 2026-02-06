"""Network protocol message definitions and serialization."""

import json
from shared.constants import MessageType


def create_message(msg_type: MessageType, payload: dict = None) -> str:
    """Create a JSON message string."""
    return json.dumps({
        "type": msg_type.value,
        "payload": payload or {},
    })


def parse_message(data: str) -> tuple[MessageType, dict]:
    """Parse a JSON message string into (type, payload)."""
    msg = json.loads(data)
    return MessageType(msg["type"]), msg.get("payload", {})
