"""Tests for protocol serialization."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.constants import MessageType
from shared.protocol import create_message, parse_message
from shared.models import (
    HexCoord, Idol, FactionState, SpiritState, WarState, GameStateSnapshot,
)
from shared.constants import IdolType, Phase


class TestProtocol:
    def test_create_and_parse(self):
        msg = create_message(MessageType.JOIN_GAME, {"player_name": "Alice"})
        msg_type, payload = parse_message(msg)
        assert msg_type == MessageType.JOIN_GAME
        assert payload["player_name"] == "Alice"

    def test_empty_payload(self):
        msg = create_message(MessageType.READY)
        msg_type, payload = parse_message(msg)
        assert msg_type == MessageType.READY
        assert payload == {}

    def test_complex_payload(self):
        msg = create_message(MessageType.PHASE_RESULT, {
            "phase": "agenda",
            "events": [{"type": "trade", "faction": "mountain", "gold_gained": 3}],
        })
        msg_type, payload = parse_message(msg)
        assert msg_type == MessageType.PHASE_RESULT
        assert len(payload["events"]) == 1


class TestModelSerialization:
    def test_hex_coord(self):
        h = HexCoord(3, -2)
        d = h.to_dict()
        h2 = HexCoord.from_dict(d)
        assert h == h2

    def test_idol(self):
        idol = Idol(IdolType.BATTLE, HexCoord(1, 2), "spirit_1")
        d = idol.to_dict()
        idol2 = Idol.from_dict(d)
        assert idol2.type == IdolType.BATTLE
        assert idol2.position == HexCoord(1, 2)
        assert idol2.owner_spirit == "spirit_1"

    def test_spirit_state(self):
        s = SpiritState("s1", "Alice", influence=3, is_vagrant=False, possessed_faction="mountain")
        d = s.to_dict()
        s2 = SpiritState.from_dict(d)
        assert s2.spirit_id == "s1"
        assert s2.name == "Alice"
        assert s2.influence == 3

    def test_war_state(self):
        w = WarState("w1", "mountain", "mesa", is_ripe=True,
                     battleground=(HexCoord(1, -1), HexCoord(1, 0)))
        d = w.to_dict()
        w2 = WarState.from_dict(d)
        assert w2.is_ripe is True
        assert w2.battleground[0] == HexCoord(1, -1)
