"""Network protocol message definitions and serialization."""

import json


class C2S:
    """Client → Server message type identifiers."""
    JOIN_GAME                   = "join_game"
    READY                       = "ready"
    START_GAME                  = "start_game"
    SET_LOBBY_OPTIONS           = "set_lobby_options"
    TOGGLE_SPECTATOR            = "toggle_spectator"
    SUBMIT_VAGRANT_ACTION       = "submit_vagrant_action"
    SUBMIT_AGENDA_CHOICE        = "submit_agenda_choice"
    SUBMIT_CHANGE_CHOICE        = "submit_change_choice"
    SUBMIT_RESTRAIN_CHOICE      = "submit_restrain_choice"
    SUBMIT_SHAPING_CHOICE       = "submit_shaping_choice"
    SUBMIT_ADAPTATION_CHOICE    = "submit_adaptation_choice"
    SUBMIT_EJECTION_AGENDA      = "submit_ejection_agenda"
    SUBMIT_SPOILS_CHOICE         = "submit_spoils_choice"
    SUBMIT_SPOILS_CHANGE_CHOICE  = "submit_spoils_change_choice"
    SUBMIT_SPOILS_EXPAND_CHOICE  = "submit_spoils_expand_choice"
    SUBMIT_WINNER_CHOICE         = "submit_winner_choice"
    SUBMIT_EXPAND_CHOICE         = "submit_expand_choice"
    SUBMIT_RESPAWN_CHOICE        = "submit_respawn_choice"
    SUBMIT_BATTLEGROUND_CHOICE   = "submit_battleground_choice"
    SUBMIT_WAR_SUPPORT_CHOICE    = "submit_war_support_choice"
    VOTE_KICK_DISCONNECTED       = "vote_kick_disconnected"


class S2C:
    """Server → Client message type identifiers."""
    LOBBY_STATE  = "lobby_state"
    GAME_START   = "game_start"
    PHASE_START  = "phase_start"
    WAITING_FOR  = "waiting_for"
    PHASE_RESULT = "phase_result"
    GAME_OVER    = "game_over"
    ERROR        = "error"
    SESSION_INFO = "session_info"
    PRESENCE_STATE = "presence_state"
    SYSTEM_MESSAGE = "system_message"


class SubPhase:
    """Sub-phase identifiers sent as the phase field of PHASE_START."""
    CHANGE_CHOICE        = "change_choice"
    RESTRAIN_CHOICE      = "restrain_choice"
    SHAPING_CHOICE       = "shaping_choice"
    ADAPTATION_CHOICE    = "adaptation_choice"
    EJECTION_CHOICE      = "ejection_choice"
    SPOILS_CHOICE        = "spoils_choice"
    SPOILS_CHANGE_CHOICE = "spoils_change_choice"
    SPOILS_EXPAND_CHOICE = "spoils_expand_choice"
    WINNER_CHOICE        = "winner_choice"
    EXPAND_CHOICE        = "expand_choice"
    RESPAWN_CHOICE       = "respawn_choice"
    BATTLEGROUND_CHOICE  = "battleground_choice"
    WAR_SUPPORT_CHOICE   = "war_support_choice"


def create_message(msg_type: str, payload: dict = None) -> str:
    """Create a JSON message string."""
    return json.dumps({
        "type": msg_type,
        "payload": payload or {},
    })


def parse_message(data: str) -> tuple[str, dict]:
    """Parse a JSON message string into (type, payload)."""
    msg = json.loads(data)
    return msg["type"], msg.get("payload", {})
