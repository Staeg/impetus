"""WebSocket server: lobby/room management, game lifecycle."""

import asyncio
import json
import traceback
import uuid
import string
import random
from typing import Optional
try:
    import websockets
    from websockets.asyncio.server import serve, ServerConnection
except ImportError:
    websockets = None  # type: ignore
    serve = None  # type: ignore
    ServerConnection = None  # type: ignore

from shared.constants import Phase, AgendaType, VP_TO_WIN
from shared.constants import Era
from shared.protocol import create_message, parse_message, C2S, S2C, SubPhase
from server.game_state import GameState
from server.pending_choices import (
    PendingChoicePrompt,
    broadcast_waiting_for,
    send_choice_prompts,
)
from server import ai


class PlayerSession:
    def __init__(self, ws: ServerConnection, player_name: str, spirit_id: str):
        self.ws = ws
        self.player_name = player_name
        self.spirit_id = spirit_id
        self.ready = False
        self.connected = True
        self.is_spectator = False


class GameRoom:
    def __init__(self, room_code: str):
        self.room_code = room_code
        self.players: dict[str, PlayerSession] = {}  # spirit_id -> session
        self.game_state: Optional[GameState] = None
        self.started = False
        self.host_spirit_id: str = ""
        self.vp_to_win: int = VP_TO_WIN
        self.ai_player_count: int = 0
        self.ai_spirit_ids: set[str] = set()
        self.tutorial_mode: bool = False
        self.play_era1: bool = True
        self.play_era2: bool = True
        self._submission_event: asyncio.Event = asyncio.Event()

    def signal_submission(self) -> None:
        """Wake the game loop to check if all submissions are in."""
        self._submission_event.set()

    async def wait_for_submission(self) -> None:
        """Block until signalled; clears after waking."""
        await self._submission_event.wait()
        self._submission_event.clear()

    def add_player(self, session: PlayerSession):
        self.players[session.spirit_id] = session

    def remove_player(self, spirit_id: str):
        if spirit_id in self.players:
            if self.started:
                # Keep for reconnection, just mark disconnected
                self.players[spirit_id].connected = False
            else:
                # Pre-game: fully remove from lobby
                del self.players[spirit_id]
                # Transfer host if needed
                if self.host_spirit_id == spirit_id:
                    remaining = [p.spirit_id for p in self.players.values()
                                 if not p.is_spectator]
                    self.host_spirit_id = remaining[0] if remaining else ""

    def reconnect_player(self, spirit_id: str, ws: ServerConnection):
        if spirit_id in self.players:
            self.players[spirit_id].ws = ws
            self.players[spirit_id].connected = True

    def can_start(self) -> bool:
        human = [p for p in self.players.values() if not p.is_spectator]
        return all(p.ready for p in human) and (len(human) + self.ai_player_count) >= 1

    def human_player_count(self) -> int:
        return sum(1 for p in self.players.values() if not p.is_spectator)

    def spectator_count(self) -> int:
        return sum(1 for p in self.players.values() if p.is_spectator)

    def connected_players(self) -> list[PlayerSession]:
        return [p for p in self.players.values() if p.connected]

    async def broadcast(self, message: str, exclude: str = None):
        for session in self.connected_players():
            if session.spirit_id != exclude:
                try:
                    await session.ws.send(message)
                except Exception:
                    session.connected = False

    async def send_to(self, spirit_id: str, message: str):
        session = self.players.get(spirit_id)
        if session and session.connected:
            try:
                await session.ws.send(message)
            except Exception:
                session.connected = False


class GameServer:
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.rooms: dict[str, GameRoom] = {}
        self.ws_to_room: dict[ServerConnection, tuple[str, str]] = {}  # ws -> (room_code, spirit_id)

    def _generate_room_code(self) -> str:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase, k=4))
            if code not in self.rooms:
                return code

    async def handle_connection(self, ws: ServerConnection):
        print(f"[server] New connection from {ws.remote_address}")
        room_code = None
        spirit_id = None
        try:
            async for raw_message in ws:
                try:
                    msg_type, payload = parse_message(raw_message)
                except Exception as e:
                    print(f"[server] Parse error: {e}")
                    await ws.send(create_message(S2C.ERROR, {"message": "Invalid message format"}))
                    continue

                print(f"[server] Received {msg_type} from {spirit_id or 'new'}")
                if msg_type == C2S.JOIN_GAME:
                    room_code, spirit_id = await self._handle_join(ws, payload)
                    print(f"[server] Join result: room={room_code}, spirit={spirit_id}")
                    if room_code and spirit_id:
                        self.ws_to_room[ws] = (room_code, spirit_id)
                elif room_code and spirit_id:
                    try:
                        await self._handle_game_message(room_code, spirit_id, msg_type, payload)
                    except Exception as e:
                        print(f"[server] Error handling {msg_type} from {spirit_id}: {e}")
                        traceback.print_exc()
                        room = self.rooms.get(room_code)
                        if room:
                            await room.send_to(spirit_id, create_message(S2C.ERROR,
                                {"message": "Server error processing action"}))
                else:
                    await ws.send(create_message(S2C.ERROR, {"message": "Not in a room"}))
        except Exception as e:
            if not (websockets and isinstance(e, websockets.exceptions.ConnectionClosed)):
                raise
        finally:
            if room_code and spirit_id:
                room = self.rooms.get(room_code)
                if room:
                    room.remove_player(spirit_id)
                    if not room.players:
                        del self.rooms[room_code]
                    else:
                        await self._broadcast_lobby_state(room)
            if ws in self.ws_to_room:
                del self.ws_to_room[ws]

    async def _handle_join(self, ws, payload) -> tuple[Optional[str], Optional[str]]:
        player_name = payload.get("player_name", "Unknown")
        room_code = payload.get("room_code")
        create_room = payload.get("create_room")

        if room_code:
            # Join existing room
            room = self.rooms.get(room_code)
            if not room:
                await ws.send(create_message(S2C.ERROR, {"message": f"Room {room_code} not found"}))
                return None, None
            if room.started:
                # Try reconnect
                for sid, session in room.players.items():
                    if session.player_name == player_name and not session.connected:
                        room.reconnect_player(sid, ws)
                        # Send current game state
                        if room.game_state:
                            snapshot = room.game_state.get_snapshot()
                            await ws.send(create_message(S2C.GAME_START, snapshot.to_dict()))
                        return room_code, sid
                await ws.send(create_message(S2C.ERROR, {"message": "Game already started"}))
                return None, None
            # Reject if at human player cap (spectators don't count toward cap)
            if room.human_player_count() >= 5:
                await ws.send(create_message(S2C.ERROR, {"message": "Room full."}))
                return None, None
        else:
            # Create new room with requested code or random
            if create_room:
                room_code = create_room.upper()[:6]
                if room_code in self.rooms:
                    existing = self.rooms[room_code]
                    if existing.game_state and existing.game_state.phase == Phase.GAME_OVER:
                        del self.rooms[room_code]
                    else:
                        await ws.send(create_message(S2C.ERROR, {"message": f"Room {room_code} already exists"}))
                        return None, None
            else:
                room_code = self._generate_room_code()
            room = GameRoom(room_code)
            self.rooms[room_code] = room

        # Check for duplicate name in lobby
        for existing in room.players.values():
            if existing.player_name.lower() == player_name.lower():
                await ws.send(create_message(S2C.ERROR,
                    {"message": f"Name '{player_name}' is already taken"}))
                return None, None

        spirit_id = str(uuid.uuid4())[:8]
        session = PlayerSession(ws, player_name, spirit_id)
        room.add_player(session)

        # First player becomes host
        if not room.host_spirit_id:
            room.host_spirit_id = spirit_id

        await ws.send(create_message(S2C.LOBBY_STATE, {
            "room_code": room_code,
            "spirit_id": spirit_id,
            "player_name": player_name,
        }))
        await self._broadcast_lobby_state(room)
        return room_code, spirit_id

    async def _broadcast_lobby_state(self, room: GameRoom):
        players = [
            {"spirit_id": s.spirit_id, "name": s.player_name, "ready": s.ready, "connected": s.connected}
            for s in room.players.values() if not s.is_spectator
        ]
        spectators = [
            {"spirit_id": s.spirit_id, "name": s.player_name, "connected": s.connected}
            for s in room.players.values() if s.is_spectator
        ]
        await room.broadcast(create_message(S2C.LOBBY_STATE, {
            "room_code": room.room_code,
            "players": players,
            "spectators": spectators,
            "host_spirit_id": room.host_spirit_id,
            "vp_to_win": room.vp_to_win,
            "ai_player_count": room.ai_player_count,
            "play_era1": room.play_era1,
            "play_era2": room.play_era2,
            "all_ready": room.can_start(),
        }))

    async def _handle_game_message(self, room_code: str, spirit_id: str,
                                    msg_type: str, payload: dict):
        room = self.rooms.get(room_code)
        if not room:
            return

        if msg_type == C2S.READY:
            session = room.players.get(spirit_id)
            if session and not session.is_spectator:
                session.ready = not session.ready
                await self._broadcast_lobby_state(room)

        elif msg_type == C2S.START_GAME:
            if spirit_id != room.host_spirit_id:
                await room.send_to(spirit_id, create_message(S2C.ERROR,
                    {"message": "Only the host can start the game"}))
                return
            if not room.can_start():
                await room.send_to(spirit_id, create_message(S2C.ERROR,
                    {"message": "Not all players are ready"}))
                return
            if not room.started:
                await self._start_game(room)

        elif msg_type == C2S.SET_LOBBY_OPTIONS:
            if spirit_id != room.host_spirit_id:
                await room.send_to(spirit_id, create_message(S2C.ERROR,
                    {"message": "Only the host can change lobby options"}))
                return
            if "vp_to_win" in payload:
                room.vp_to_win = max(50, min(250, int(payload["vp_to_win"])))
            if "ai_count" in payload:
                ai_count = max(0, min(5, int(payload["ai_count"])))
                # Total human + AI must not exceed 5
                if room.human_player_count() + ai_count > 5:
                    ai_count = max(0, 5 - room.human_player_count())
                room.ai_player_count = ai_count
            if "tutorial_mode" in payload:
                room.tutorial_mode = bool(payload["tutorial_mode"])
            if "play_era1" in payload or "play_era2" in payload:
                next_era1 = bool(payload.get("play_era1", room.play_era1))
                next_era2 = bool(payload.get("play_era2", room.play_era2))
                if next_era1 or next_era2:
                    room.play_era1 = next_era1
                    room.play_era2 = next_era2
            await self._broadcast_lobby_state(room)

        elif msg_type == C2S.TOGGLE_SPECTATOR:
            session = room.players.get(spirit_id)
            if not session:
                return
            if session.is_spectator:
                # Become player — check capacity
                if room.human_player_count() >= 5:
                    await room.send_to(spirit_id, create_message(S2C.ERROR,
                        {"message": "Room full."}))
                    return
                session.is_spectator = False
                # Ensure room has a host if host slot was empty
                if not room.host_spirit_id:
                    room.host_spirit_id = spirit_id
            else:
                # Become spectator — check spectator cap
                if room.spectator_count() >= 10:
                    await room.send_to(spirit_id, create_message(S2C.ERROR,
                        {"message": "Spectator slots full."}))
                    return
                session.is_spectator = True
                session.ready = False
            await self._broadcast_lobby_state(room)

        elif msg_type == C2S.SUBMIT_VAGRANT_ACTION:
            if room.game_state and room.game_state.phase == Phase.VAGRANT_PHASE:
                error = room.game_state.submit_action(spirit_id, payload)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_waiting(room)
                    room.signal_submission()
                    # In tutorial mode AIs wait for humans; trigger their submissions now
                    await self._resolve_ai_inputs(room)

        elif msg_type == C2S.SUBMIT_AGENDA_CHOICE:
            if room.game_state and room.game_state.phase == Phase.AGENDA_PHASE:
                error = room.game_state.submit_action(spirit_id, payload)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_waiting(room)
                    room.signal_submission()

        elif msg_type == C2S.SUBMIT_EXPAND_CHOICE:
            if room.game_state:
                q = int(payload.get("q", 0))
                r = int(payload.get("r", 0))
                error = room.game_state.submit_expand_choice(spirit_id, q, r)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                elif not room.game_state.has_pending_expand_choices():
                    # All expand choices received — proceed to change choices
                    await self._handle_change_choices_after_expand(room)
                else:
                    waiting_for = list(room.game_state.expand_pending.keys())
                    await room.broadcast(create_message(S2C.WAITING_FOR, {
                        "players_remaining": waiting_for,
                    }))

        elif msg_type == C2S.SUBMIT_CHANGE_CHOICE:
            if room.game_state:
                error, change_events = room.game_state.submit_change_choice(
                    spirit_id, payload.get("card_index", 0))
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    # Collect change events; don't broadcast until all spirits have chosen
                    if not hasattr(room, '_pending_change_events'):
                        room._pending_change_events = []
                    room._pending_change_events.extend(change_events)
                    # Update waiting list
                    if room.game_state.has_pending_change_choices():
                        waiting_for = list(room.game_state.change_pending.keys())
                        await room.broadcast(create_message(S2C.WAITING_FOR, {
                            "players_remaining": waiting_for,
                        }))
                    else:
                        # All changes submitted - broadcast all change events together
                        all_change_events = room._pending_change_events
                        room._pending_change_events = []
                        await self._broadcast_phase_result(room, all_change_events)
                        # Now resolve all agendas
                        events = room.game_state.resolve_agenda_phase_after_changes()
                        await self._broadcast_phase_result(room, events)
                        if room.game_state.has_pending_battleground_choices():
                            await self._send_battleground_options(room)
                        else:
                            await self._auto_resolve_phases(room)

        elif msg_type == C2S.SUBMIT_RESTRAIN_CHOICE:
            if room.game_state:
                error, events = room.game_state.submit_restrain_choice(
                    spirit_id, payload.get("agenda_type", ""))
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.restrain_pending:
                        await broadcast_waiting_for(room, list(room.game_state.restrain_pending.keys()))
                    else:
                        await self._handle_shaping_choices(room)

        elif msg_type == C2S.SUBMIT_SHAPING_CHOICE:
            if room.game_state:
                error, events = room.game_state.submit_shaping_choice(
                    spirit_id, payload.get("card_name", ""))
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.shaping_pending:
                        await broadcast_waiting_for(room, list(room.game_state.shaping_pending.keys()))
                    else:
                        await self._handle_adaptation_choices(room)

        elif msg_type == C2S.SUBMIT_ADAPTATION_CHOICE:
            if room.game_state:
                error, events = room.game_state.submit_adaptation_choice(
                    spirit_id, payload.get("card_name", ""))
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.adaptation_pending:
                        await broadcast_waiting_for(room, list(room.game_state.adaptation_pending.keys()))
                    else:
                        await self._handle_expand_and_change_choices(room)

        elif msg_type == C2S.SUBMIT_BATTLEGROUND_CHOICE:
            if room.game_state:
                error, events = room.game_state.submit_battleground_choice(
                    spirit_id, payload.get("choices", []))
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.has_pending_battleground_choices():
                        await broadcast_waiting_for(room, list(room.game_state.battleground_pending.keys()))
                    else:
                        await self._auto_resolve_phases(room)

        elif msg_type == C2S.SUBMIT_WAR_SUPPORT_CHOICE:
            if room.game_state:
                error, events = room.game_state.submit_war_support_choice(
                    spirit_id, payload.get("choices", []))
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.has_pending_war_support_choices():
                        await broadcast_waiting_for(room, list(room.game_state.war_support_pending.keys()))
                    else:
                        await self._auto_resolve_phases(room)

        elif msg_type == C2S.SUBMIT_EJECTION_AGENDA:
            if room.game_state:
                error = room.game_state.submit_ejection_choice(
                    spirit_id,
                    payload.get("remove_type", ""),
                    payload.get("add_type", ""),
                )
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                elif room.game_state.has_pending_sub_choices():
                    waiting_for = list(room.game_state.ejection_pending.keys())
                    await room.broadcast(create_message(S2C.WAITING_FOR, {
                        "players_remaining": waiting_for,
                    }))
                else:
                    events = room.game_state.finalize_sub_choices()
                    await self._broadcast_phase_result(room, events)
                    await self._auto_resolve_phases(room)

        elif msg_type == C2S.SUBMIT_SPOILS_CHOICE:
            if room.game_state:
                card_indices = payload.get("card_indices", [])
                # Backwards compat: single card_index → list
                if not card_indices and "card_index" in payload:
                    card_indices = [payload["card_index"]]
                error, events = room.game_state.submit_spoils_choice(
                    spirit_id, card_indices)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    pending_list = room.game_state.spoils_pending.get(spirit_id)
                    if pending_list and any(p.stage == SubPhase.CHANGE_CHOICE for p in pending_list):
                        ai_evts = await self._auto_resolve_ai_spoils(room)
                        if ai_evts:
                            await self._broadcast_phase_result(room, ai_evts)
                        change_pendings = [p for p in pending_list if p.stage == SubPhase.CHANGE_CHOICE]
                        change_options = [{"cards": [c.value for c in p.change_cards], "loser": p.loser}
                                          for p in change_pendings]
                        await room.send_to(spirit_id, create_message(S2C.PHASE_START, {
                            "phase": SubPhase.SPOILS_CHANGE_CHOICE,
                            "turn": room.game_state.turn,
                            "options": {"choices": change_options},
                        }))
                        waiting_for = list(room.game_state.spoils_pending.keys())
                        await room.broadcast(create_message(S2C.WAITING_FOR,
                            {"players_remaining": waiting_for}))
                    elif pending_list and any(p.stage == SubPhase.SPOILS_EXPAND_CHOICE for p in pending_list):
                        ai_evts = await self._auto_resolve_ai_spoils(room)
                        if ai_evts:
                            await self._broadcast_phase_result(room, ai_evts)
                        await self._send_spoils_expand_options(room, spirit_id, pending_list)
                    elif not room.game_state.spoils_pending:
                        await self._auto_resolve_phases(room)
                    else:
                        ai_evts = await self._auto_resolve_ai_spoils(room)
                        if ai_evts:
                            await self._broadcast_phase_result(room, ai_evts)
                        if not room.game_state.spoils_pending:
                            await self._auto_resolve_phases(room)
                        else:
                            waiting_for = list(room.game_state.spoils_pending.keys())
                            await room.broadcast(create_message(S2C.WAITING_FOR,
                                {"players_remaining": waiting_for}))

        elif msg_type == C2S.SUBMIT_SPOILS_CHANGE_CHOICE:
            if room.game_state:
                card_indices = payload.get("card_indices", [])
                if not card_indices and "card_index" in payload:
                    card_indices = [payload["card_index"]]
                error, events = room.game_state.submit_spoils_change_choice(
                    spirit_id, card_indices)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    pending_list = room.game_state.spoils_pending.get(spirit_id)
                    if pending_list and any(p.stage == SubPhase.SPOILS_EXPAND_CHOICE for p in pending_list):
                        ai_evts = await self._auto_resolve_ai_spoils(room)
                        if ai_evts:
                            await self._broadcast_phase_result(room, ai_evts)
                        await self._send_spoils_expand_options(room, spirit_id, pending_list)
                    elif not room.game_state.spoils_pending:
                        await self._auto_resolve_phases(room)
                    else:
                        ai_evts = await self._auto_resolve_ai_spoils(room)
                        if ai_evts:
                            await self._broadcast_phase_result(room, ai_evts)
                        if not room.game_state.spoils_pending:
                            await self._auto_resolve_phases(room)
                        else:
                            waiting_for = list(room.game_state.spoils_pending.keys())
                            await room.broadcast(create_message(S2C.WAITING_FOR, {
                                "players_remaining": waiting_for,
                            }))

        elif msg_type == C2S.SUBMIT_SPOILS_EXPAND_CHOICE:
            if room.game_state:
                choices = payload.get("choices", [])
                error, events = room.game_state.submit_spoils_expand_choice(spirit_id, choices)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if not room.game_state.spoils_pending:
                        await self._auto_resolve_phases(room)
                    else:
                        ai_evts = await self._auto_resolve_ai_spoils(room)
                        if ai_evts:
                            await self._broadcast_phase_result(room, ai_evts)
                        if not room.game_state.spoils_pending:
                            await self._auto_resolve_phases(room)
                        else:
                            waiting_for = list(room.game_state.spoils_pending.keys())
                            await room.broadcast(create_message(S2C.WAITING_FOR, {
                                "players_remaining": waiting_for,
                            }))

        elif msg_type == C2S.SUBMIT_WINNER_CHOICE:
            if room.game_state:
                choices = payload.get("choices", [])
                error, events = room.game_state.submit_winner_choice(spirit_id, choices)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.has_pending_winner_choices():
                        waiting_for = list(room.game_state.winner_choice_pending.keys())
                        await room.broadcast(create_message(S2C.WAITING_FOR,
                            {"players_remaining": waiting_for}))
                    elif room.game_state.spoils_pending:
                        await self._send_spoils_options(room)
                    else:
                        await self._auto_resolve_phases(room)

        elif msg_type == C2S.SUBMIT_RESPAWN_CHOICE:
            if room.game_state:
                q = int(payload.get("q", 0))
                r = int(payload.get("r", 0))
                error, events = room.game_state.submit_respawn_choice(spirit_id, q, r)
                if error:
                    await room.send_to(spirit_id, create_message(S2C.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if room.game_state.respawn_pending:
                        waiting_for = list(room.game_state.respawn_pending.keys())
                        await room.broadcast(create_message(S2C.WAITING_FOR,
                            {"players_remaining": waiting_for}))
                    else:
                        await self._auto_resolve_phases(room)


    async def _start_game(self, room: GameRoom):
        room.started = True
        # Only non-spectator humans participate as spirits
        player_info = [
            {"spirit_id": s.spirit_id, "name": s.player_name}
            for s in room.players.values()
            if not s.is_spectator
        ]
        # Add AI players
        if room.ai_player_count > 0:
            ai_names = ai.assign_ai_names(room.ai_player_count)
            for name in ai_names:
                ai_sid = str(uuid.uuid4())[:8]
                room.ai_spirit_ids.add(ai_sid)
                player_info.append({"spirit_id": ai_sid, "name": name})

        room.game_state = GameState()
        room.game_state.tutorial_mode = room.tutorial_mode
        room.game_state.ai_spirit_ids = set(room.ai_spirit_ids)
        enabled_eras = set()
        if room.play_era1:
            enabled_eras.add(Era.ERA_1)
        if room.play_era2:
            enabled_eras.add(Era.ERA_2)
        initial_snapshot, turn_results = room.game_state.setup_game(
            player_info, vp_to_win=room.vp_to_win, enabled_eras=enabled_eras)

        if not room.play_era1 and room.play_era2:
            room.game_state.started_from_simulated_era1 = True
            sim_results = self._simulate_until_era2(room)
            turn_results.extend(sim_results)

        # Send initial state (pre-setup) so client starts with just starting hexes
        await room.broadcast(create_message(S2C.GAME_START, initial_snapshot.to_dict()))

        # Send each automated turn with its own post-turn snapshot so the
        # client's animation system can diff hex ownership correctly.
        for events, snapshot in turn_results:
            await room.broadcast(create_message(S2C.PHASE_RESULT, {
                "phase": room.game_state.phase.value,
                "events": events,
                "state": snapshot.to_dict(),
                "suppress_animations": room.game_state.started_from_simulated_era1,
            }))

        await self._auto_resolve_phases(room)
        asyncio.create_task(self._run_game_loop(room))

    def _simulate_until_era2(self, room: GameRoom) -> list[tuple[list[dict], object]]:
        """Run a full AI-controlled Era 1 until Era 2 is reached."""
        gs = room.game_state
        results: list[tuple[list[dict], object]] = []
        all_spirit_ids = list(gs.spirits.keys())

        while gs.current_era == Era.ERA_1 and gs.phase != Phase.GAME_OVER:
            if gs.phase == Phase.VAGRANT_PHASE:
                for sid in all_spirit_ids:
                    if gs.needs_input(sid) and sid not in gs.pending_actions:
                        action = ai.get_ai_vagrant_action(gs, sid)
                        if action:
                            gs.submit_action(sid, action)
                events = gs.resolve_current_phase()
                results.append((events, gs.get_snapshot()))
                continue

            if gs.phase == Phase.AGENDA_PHASE:
                for sid in all_spirit_ids:
                    if gs.needs_input(sid) and sid not in gs.pending_actions:
                        action = ai.get_ai_agenda_choice(gs, sid)
                        if action:
                            gs.submit_action(sid, action)
                events = gs.resolve_current_phase()
                results.append((events, gs.get_snapshot()))
                if gs.has_pending_battleground_choices():
                    bg_events: list[dict] = []
                    for sid, entries in list(gs.battleground_pending.items()):
                        _, evts = gs.submit_battleground_choice(sid, ai.get_ai_battleground_choice(entries))
                        bg_events.extend(evts)
                    results.append((bg_events, gs.get_snapshot()))
                continue

            if gs.phase == Phase.WAR_PHASE:
                if gs.has_pending_winner_choices():
                    events: list[dict] = []
                    for sid, entries in list(gs.winner_choice_pending.items()):
                        _, evts = gs.submit_winner_choice(sid, ai.get_ai_winner_choice(entries))
                        events.extend(evts)
                    results.append((events, gs.get_snapshot()))
                    continue
                if gs.has_pending_war_support_choices():
                    events = []
                    for sid, entries in list(gs.war_support_pending.items()):
                        guided_faction = gs.spirits[sid].guided_faction if sid in gs.spirits else None
                        _, evts = gs.submit_war_support_choice(
                            sid, ai.get_ai_war_support_choice(entries, guided_faction))
                        events.extend(evts)
                    results.append((events, gs.get_snapshot()))
                    continue
                if gs.spoils_pending:
                    events = []
                    for sid in list(gs.spoils_pending.keys()):
                        pending_list = gs.spoils_pending[sid]
                        _, evts = gs.submit_spoils_choice(sid, ai.get_ai_spoils_choice(pending_list))
                        events.extend(evts)
                    for sid in list(gs.spoils_pending.keys()):
                        pending_list = gs.spoils_pending[sid]
                        change_pendings = [p for p in pending_list if p.stage == SubPhase.CHANGE_CHOICE]
                        if change_pendings:
                            _, evts = gs.submit_spoils_change_choice(
                                sid, ai.get_ai_spoils_change_choice(change_pendings))
                            events.extend(evts)
                    for sid in list(gs.spoils_pending.keys()):
                        pending_list = gs.spoils_pending[sid]
                        expand_pendings = [p for p in pending_list if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
                        if expand_pendings:
                            _, evts = gs.submit_spoils_expand_choice(
                                sid, ai.get_ai_spoils_expand_choice(expand_pendings))
                            events.extend(evts)
                    results.append((events, gs.get_snapshot()))
                    continue
                if gs.respawn_pending:
                    events = []
                    for sid in list(gs.respawn_pending.keys()):
                        neutral = list(gs.hex_map.get_neutral_hexes())
                        if neutral:
                            _, evts = gs.submit_respawn_choice(sid, neutral[0][0], neutral[0][1])
                            events.extend(evts)
                    results.append((events, gs.get_snapshot()))
                    continue
                events = gs.resolve_current_phase()
                results.append((events, gs.get_snapshot()))
                continue

            if gs.phase == Phase.SCORING:
                if gs.ejection_pending:
                    events = []
                    for sid, faction_id in list(gs.ejection_pending.items()):
                        pool = [c.agenda_type.value for c in gs.factions[faction_id].agenda_pool]
                        remove_type, add_type = ai.get_ai_ejection_choice(pool, [at.value for at in AgendaType])
                        gs.submit_ejection_choice(sid, remove_type, add_type)
                    events = gs.finalize_sub_choices()
                    results.append((events, gs.get_snapshot()))
                    continue
                events = gs.resolve_current_phase()
                results.append((events, gs.get_snapshot()))
                if gs.started_from_simulated_era1 and gs.current_era == Era.ERA_2:
                    if gs.ejection_pending:
                        transition_events: list[dict] = []
                        for sid, faction_id in list(gs.ejection_pending.items()):
                            pool = [c.agenda_type.value for c in gs.factions[faction_id].agenda_pool]
                            remove_type, add_type = ai.get_ai_ejection_choice(pool, [at.value for at in AgendaType])
                            gs.submit_ejection_choice(sid, remove_type, add_type)
                        transition_events.extend(gs.finalize_sub_choices())
                        results.append((transition_events, gs.get_snapshot()))
                    if gs.phase == Phase.CLEANUP:
                        cleanup_events = gs.resolve_current_phase()
                        results.append((cleanup_events, gs.get_snapshot()))
                    break
                continue

            if gs.phase == Phase.CLEANUP:
                events = gs.resolve_current_phase()
                results.append((events, gs.get_snapshot()))
                continue

            break

        return results

    async def _run_game_loop(self, room: GameRoom):
        """Drive VAGRANT and AGENDA phase transitions using event-based waiting."""
        gs = room.game_state
        await self._send_phase_options(room)
        while gs.phase != Phase.GAME_OVER:
            await room.wait_for_submission()
            if not gs.all_inputs_received():
                continue  # Spurious wakeup; wait for next signal
            if gs.phase == Phase.VAGRANT_PHASE:
                events = gs.resolve_current_phase()
                await self._broadcast_phase_result(room, events)
                await self._auto_resolve_phases(room)
            elif gs.phase == Phase.AGENDA_PHASE:
                await self._handle_agenda_resolution(room)

    async def _send_phase_options(self, room: GameRoom):
        gs = room.game_state
        for spirit_id in gs.spirits:
            options = gs.get_phase_options(spirit_id)
            await room.send_to(spirit_id, create_message(S2C.PHASE_START, {
                "phase": gs.phase.value,
                "turn": gs.turn,
                "options": options,
            }))
        await self._broadcast_waiting(room)
        # Auto-resolve AI inputs
        await self._resolve_ai_inputs(room)

    async def _resolve_ai_inputs(self, room: GameRoom):
        """Submit actions on behalf of AI spirits and trigger resolution if complete."""
        gs = room.game_state
        if room.tutorial_mode and gs.phase == Phase.VAGRANT_PHASE:
            # In tutorial mode: wait for all human players to submit before assigning
            # AI factions, so we can exclude human choices and prevent contention.
            human_spirit_ids = set(gs.spirits.keys()) - room.ai_spirit_ids
            humans_pending = [
                sid for sid in human_spirit_ids
                if gs.needs_input(sid) and sid not in gs.pending_actions
            ]
            if humans_pending:
                return  # Wait for humans to submit first
            # Collect human-chosen factions so AIs avoid them
            taken: set[str] = set()
            for sid in human_spirit_ids:
                gt = gs.pending_actions.get(sid, {}).get("guide_target")
                if gt:
                    taken.add(gt)
            for sid in sorted(list(room.ai_spirit_ids)):
                if gs.needs_input(sid) and sid not in gs.pending_actions:
                    action = ai.get_ai_vagrant_action(gs, sid, excluded_factions=taken)
                    if action.get("guide_target"):
                        taken.add(action["guide_target"])
                    if action:
                        gs.submit_action(sid, action)
        else:
            for sid in list(room.ai_spirit_ids):
                if gs.needs_input(sid) and sid not in gs.pending_actions:
                    if gs.phase == Phase.VAGRANT_PHASE:
                        action = ai.get_ai_vagrant_action(gs, sid)
                    elif gs.phase == Phase.AGENDA_PHASE:
                        action = ai.get_ai_agenda_choice(gs, sid)
                    else:
                        continue
                    if action:
                        gs.submit_action(sid, action)
        await self._broadcast_waiting(room)
        room.signal_submission()

    async def _broadcast_waiting(self, room: GameRoom):
        gs = room.game_state
        remaining = gs.get_spirits_needing_input()
        await broadcast_waiting_for(room, remaining)

    async def _handle_agenda_resolution(self, room: GameRoom):
        """Handle agenda phase after all inputs received: prepare expand/change choices first."""
        gs = room.game_state
        if gs.is_era2():
            await self._handle_restrain_choices(room)
            return
        change_events = gs.prepare_change_choices()
        await self._broadcast_phase_result(room, change_events)

        if not hasattr(room, '_pending_change_events'):
            room._pending_change_events = []

        # Identify guided Expand factions that need a hex choice
        gs.prepare_expand_choices()

        # Auto-submit expand choices for AI spirits
        for sid in list(room.ai_spirit_ids):
            if sid in gs.expand_pending:
                faction_id = gs.expand_pending[sid]
                allow_enemy = "Special Military Operations" in gs.factions[faction_id].shaping_effects
                reachable = list(gs.hex_map.get_expand_targets(faction_id, allow_enemy=allow_enemy))
                if reachable:
                    chosen = ai.get_ai_expand_choice(reachable, gs.hex_map, sid)
                    gs.submit_expand_choice(sid, chosen[0], chosen[1])

        if gs.has_pending_expand_choices():
            # Send expand_choice to each remaining human spirit
            prompts = []
            for spirit_id, faction_id in gs.expand_pending.items():
                allow_enemy = "Special Military Operations" in gs.factions[faction_id].shaping_effects
                reachable = gs.hex_map.get_expand_targets(faction_id, allow_enemy=allow_enemy)
                prompts.append(PendingChoicePrompt(
                    spirit_id=spirit_id,
                    phase=SubPhase.EXPAND_CHOICE,
                    turn=gs.turn,
                    options={
                        "faction": faction_id,
                        "hexes": [{"q": h[0], "r": h[1]} for h in sorted(reachable)],
                    },
                ))
            await send_choice_prompts(room, prompts)
            await broadcast_waiting_for(room, list(gs.expand_pending.keys()))
            return

        # No expand choices pending — proceed to change choices
        await self._handle_change_choices_after_expand(room)

    async def _handle_restrain_choices(self, room: GameRoom):
        gs = room.game_state
        events = gs.prepare_restrain_choices()
        if events:
            await self._broadcast_phase_result(room, events)
        for sid in list(room.ai_spirit_ids):
            if sid in gs.restrain_pending:
                cards = gs.restrain_pending[sid]
                err, evts = gs.submit_restrain_choice(sid, ai.get_ai_restrain_choice(cards))
                if not err and evts:
                    await self._broadcast_phase_result(room, evts)
        if gs.restrain_pending:
            prompts = [
                PendingChoicePrompt(
                    spirit_id=spirit_id,
                    phase=SubPhase.RESTRAIN_CHOICE,
                    turn=gs.turn,
                    options={"cards": [card.value for card in cards]},
                )
                for spirit_id, cards in gs.restrain_pending.items()
            ]
            await send_choice_prompts(room, prompts)
            await broadcast_waiting_for(room, list(gs.restrain_pending.keys()))
            return
        await self._handle_shaping_choices(room)

    async def _handle_shaping_choices(self, room: GameRoom):
        gs = room.game_state
        events = gs.prepare_shaping_choices()
        if events:
            await self._broadcast_phase_result(room, events)
        for sid in list(room.ai_spirit_ids):
            if sid in gs.shaping_pending:
                err, evts = gs.submit_shaping_choice(sid, ai.get_ai_card_name_choice(gs.shaping_pending[sid]))
                if not err and evts:
                    await self._broadcast_phase_result(room, evts)
        if gs.shaping_pending:
            prompts = [
                PendingChoicePrompt(
                    spirit_id=spirit_id,
                    phase=SubPhase.SHAPING_CHOICE,
                    turn=gs.turn,
                    options={"cards": cards},
                )
                for spirit_id, cards in gs.shaping_pending.items()
            ]
            await send_choice_prompts(room, prompts)
            await broadcast_waiting_for(room, list(gs.shaping_pending.keys()))
            return
        await self._handle_adaptation_choices(room)

    async def _handle_adaptation_choices(self, room: GameRoom):
        gs = room.game_state
        events = gs.prepare_adaptation_choices()
        if events:
            await self._broadcast_phase_result(room, events)
        for sid in list(room.ai_spirit_ids):
            if sid in gs.adaptation_pending:
                err, evts = gs.submit_adaptation_choice(sid, ai.get_ai_card_name_choice(gs.adaptation_pending[sid]))
                if not err and evts:
                    await self._broadcast_phase_result(room, evts)
        if gs.adaptation_pending:
            prompts = [
                PendingChoicePrompt(
                    spirit_id=spirit_id,
                    phase=SubPhase.ADAPTATION_CHOICE,
                    turn=gs.turn,
                    options={"cards": cards},
                )
                for spirit_id, cards in gs.adaptation_pending.items()
            ]
            await send_choice_prompts(room, prompts)
            await broadcast_waiting_for(room, list(gs.adaptation_pending.keys()))
            return
        await self._handle_expand_and_change_choices(room)

    async def _handle_expand_and_change_choices(self, room: GameRoom):
        gs = room.game_state
        change_events = gs.prepare_change_choices()
        await self._broadcast_phase_result(room, change_events)

        if not hasattr(room, '_pending_change_events'):
            room._pending_change_events = []

        gs.prepare_expand_choices()

        for sid in list(room.ai_spirit_ids):
            if sid in gs.expand_pending:
                faction_id = gs.expand_pending[sid]
                allow_enemy = "Special Military Operations" in gs.factions[faction_id].shaping_effects
                reachable = list(gs.hex_map.get_expand_targets(faction_id, allow_enemy=allow_enemy))
                if reachable:
                    chosen = ai.get_ai_expand_choice(reachable, gs.hex_map, sid)
                    gs.submit_expand_choice(sid, chosen[0], chosen[1])

        if gs.has_pending_expand_choices():
            prompts = []
            for spirit_id, faction_id in gs.expand_pending.items():
                allow_enemy = "Special Military Operations" in gs.factions[faction_id].shaping_effects
                reachable = gs.hex_map.get_expand_targets(faction_id, allow_enemy=allow_enemy)
                prompts.append(PendingChoicePrompt(
                    spirit_id=spirit_id,
                    phase=SubPhase.EXPAND_CHOICE,
                    turn=gs.turn,
                    options={
                        "faction": faction_id,
                        "hexes": [{"q": h[0], "r": h[1]} for h in sorted(reachable)],
                    },
                ))
            await send_choice_prompts(room, prompts)
            await broadcast_waiting_for(room, list(gs.expand_pending.keys()))
            return

        await self._handle_change_choices_after_expand(room)

    async def _handle_change_choices_after_expand(self, room: GameRoom):
        """Handle change choices (or auto-resolve and proceed to resolution)."""
        gs = room.game_state

        if not hasattr(room, '_pending_change_events'):
            room._pending_change_events = []

        # Auto-submit change choices for AI spirits
        for sid in list(room.ai_spirit_ids):
            if sid in gs.change_pending:
                cards = gs.change_pending[sid]
                idx = ai.get_ai_change_choice(cards)
                err, evts = gs.submit_change_choice(sid, idx)
                if not err:
                    room._pending_change_events.extend(evts)

        if gs.has_pending_change_choices():
            # Send change_choice to each remaining human spirit
            prompts = [
                PendingChoicePrompt(
                    spirit_id=spirit_id,
                    phase=SubPhase.CHANGE_CHOICE,
                    turn=gs.turn,
                    options={"cards": [c.value for c in cards]},
                )
                for spirit_id, cards in gs.change_pending.items()
            ]
            await send_choice_prompts(room, prompts)
            await broadcast_waiting_for(room, list(gs.change_pending.keys()))
            return

        # All choices done — broadcast modifier events if any, then resolve
        if room._pending_change_events:
            all_change_events = room._pending_change_events
            room._pending_change_events = []
            await self._broadcast_phase_result(room, all_change_events)

        events = gs.resolve_agenda_phase_after_changes()
        await self._broadcast_phase_result(room, events)
        if gs.has_pending_battleground_choices():
            await self._send_battleground_options(room)
        else:
            await self._auto_resolve_phases(room)

    async def _send_battleground_options(self, room: GameRoom):
        gs = room.game_state
        ai_events = []
        for sid in list(room.ai_spirit_ids):
            if sid in gs.battleground_pending:
                err, evts = gs.submit_battleground_choice(
                    sid, ai.get_ai_battleground_choice(gs.battleground_pending[sid]))
                if not err:
                    ai_events.extend(evts)
        if ai_events:
            await self._broadcast_phase_result(room, ai_events)
        if not gs.has_pending_battleground_choices():
            await self._auto_resolve_phases(room)
            return
        prompts = []
        for sid, entries in gs.battleground_pending.items():
            choice_entries = []
            for entry in entries:
                choice_entries.append({
                    "war_id": entry["war_id"],
                    "faction_a": entry["faction_a"],
                    "faction_b": entry["faction_b"],
                    "pairs": [
                        {
                            "a": {"q": pair[0][0], "r": pair[0][1]},
                            "b": {"q": pair[1][0], "r": pair[1][1]},
                        }
                        for pair in entry["pairs"]
                    ],
                })
            prompts.append(PendingChoicePrompt(
                spirit_id=sid,
                phase=SubPhase.BATTLEGROUND_CHOICE,
                turn=gs.turn,
                options={"choices": choice_entries},
            ))
        await send_choice_prompts(room, prompts)
        await broadcast_waiting_for(room, list(gs.battleground_pending.keys()))

    async def _send_war_support_options(self, room: GameRoom):
        gs = room.game_state
        ai_events = []
        for sid in list(room.ai_spirit_ids):
            if sid in gs.war_support_pending:
                guided_faction = gs.spirits[sid].guided_faction if sid in gs.spirits else None
                err, evts = gs.submit_war_support_choice(
                    sid, ai.get_ai_war_support_choice(gs.war_support_pending[sid], guided_faction))
                if not err:
                    ai_events.extend(evts)
        if ai_events:
            await self._broadcast_phase_result(room, ai_events)
        if not gs.has_pending_war_support_choices():
            await self._auto_resolve_phases(room)
            return
        prompts = []
        for sid, entries in gs.war_support_pending.items():
            prompts.append(PendingChoicePrompt(
                spirit_id=sid,
                phase=SubPhase.WAR_SUPPORT_CHOICE,
                turn=gs.turn,
                options={"choices": entries},
            ))
        await send_choice_prompts(room, prompts)
        await broadcast_waiting_for(room, list(gs.war_support_pending.keys()))

    async def _send_respawn_options(self, room: GameRoom):
        """Auto-submit AI respawn choices and send options to human spirits."""
        gs = room.game_state
        ai_events = []
        for sid in list(room.ai_spirit_ids):
            if sid in gs.respawn_pending:
                neutral = list(gs.hex_map.get_neutral_hexes())
                if neutral:
                    chosen = random.choice(neutral)
                    err, evts = gs.submit_respawn_choice(sid, chosen[0], chosen[1])
                    if not err:
                        ai_events.extend(evts)
        if ai_events:
            await self._broadcast_phase_result(room, ai_events)
        if not gs.respawn_pending:
            await self._auto_resolve_phases(room)
            return
        prompts = []
        for spirit_id in list(gs.respawn_pending.keys()):
            neutral = [{"q": h[0], "r": h[1]} for h in sorted(gs.hex_map.get_neutral_hexes())]
            prompts.append(PendingChoicePrompt(
                spirit_id=spirit_id,
                phase=SubPhase.RESPAWN_CHOICE,
                turn=gs.turn,
                options={
                    "faction": gs.respawn_pending[spirit_id],
                    "hexes": neutral,
                },
            ))
        await send_choice_prompts(room, prompts)
        await broadcast_waiting_for(room, list(gs.respawn_pending.keys()))

    async def _send_ejection_options(self, room: GameRoom):
        """Send ejection choice options to spirits that need them."""
        gs = room.game_state

        # Auto-submit ejection choices for AI spirits
        for sid in list(room.ai_spirit_ids):
            if sid in gs.ejection_pending:
                faction_id = gs.ejection_pending[sid]
                faction = gs.factions[faction_id]
                agenda_pool = [c.agenda_type.value for c in faction.agenda_pool]
                agenda_types = [at.value for at in AgendaType]
                remove_type, add_type = ai.get_ai_ejection_choice(agenda_pool, agenda_types)
                gs.submit_ejection_choice(sid, remove_type, add_type)

        if not gs.ejection_pending:
            # All ejections were AI — finalize immediately
            events = gs.finalize_sub_choices()
            await self._broadcast_phase_result(room, events)
            await self._auto_resolve_phases(room)
            return

        # Send to remaining human spirits
        prompts = []
        for spirit_id, faction_id in gs.ejection_pending.items():
            faction = gs.factions[faction_id]
            agenda_pool = [c.agenda_type.value for c in faction.agenda_pool]
            prompts.append(PendingChoicePrompt(
                spirit_id=spirit_id,
                phase=SubPhase.EJECTION_CHOICE,
                turn=gs.turn,
                options={
                    "faction": faction_id,
                    "agenda_pool": agenda_pool,
                    "agenda_types": [at.value for at in AgendaType],
                },
            ))
        await send_choice_prompts(room, prompts)
        await broadcast_waiting_for(room, list(gs.ejection_pending.keys()))

    async def _send_spoils_options(self, room: GameRoom):
        """Send spoils_choice phase_start to all human spirits with pending spoils."""
        gs = room.game_state
        prompts = []
        for sid, pending_list in gs.spoils_pending.items():
            choices = [{"cards": [c.value for c in p.cards], "loser": p.loser}
                       for p in pending_list]
            prompts.append(PendingChoicePrompt(
                spirit_id=sid,
                phase=SubPhase.SPOILS_CHOICE,
                turn=gs.turn,
                options={"choices": choices},
            ))
        await send_choice_prompts(room, prompts)
        await broadcast_waiting_for(room, list(gs.spoils_pending.keys()))

    async def _auto_resolve_ai_spoils(self, room: GameRoom) -> list:
        """Auto-resolve any AI spirits still in spoils_pending. Returns combined events."""
        gs = room.game_state
        ai_events = []
        for sid in list(room.ai_spirit_ids):
            if sid in gs.spoils_pending:
                pending_list = gs.spoils_pending[sid]
                err, evts = gs.submit_spoils_choice(sid, ai.get_ai_spoils_choice(pending_list))
                if not err:
                    ai_events.extend(evts)
        for sid in list(room.ai_spirit_ids):
            if sid in gs.spoils_pending:
                pending_list = gs.spoils_pending[sid]
                change_pendings = [p for p in pending_list if p.stage == SubPhase.CHANGE_CHOICE]
                if change_pendings:
                    err, evts = gs.submit_spoils_change_choice(
                        sid, ai.get_ai_spoils_change_choice(change_pendings))
                    if not err:
                        ai_events.extend(evts)
        for sid in list(room.ai_spirit_ids):
            if sid in gs.spoils_pending:
                pending_list = gs.spoils_pending[sid]
                expand_pendings = [p for p in pending_list
                                   if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
                if expand_pendings:
                    err, evts = gs.submit_spoils_expand_choice(
                        sid, ai.get_ai_spoils_expand_choice(expand_pendings))
                    if not err:
                        ai_events.extend(evts)
        return ai_events

    async def _send_spoils_expand_options(self, room: GameRoom, spirit_id: str, pending_list):
        """Send spoils_expand_choice to a spirit whose pending entry needs a target hex."""
        gs = room.game_state
        expand_pendings = [p for p in pending_list if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
        choices = [
            {
                "loser": p.loser,
                "available_hexes": [{"q": h[0], "r": h[1]} for h in p.expand_hexes],
            }
            for p in expand_pendings
        ]
        await send_choice_prompts(room, [PendingChoicePrompt(
            spirit_id=spirit_id,
            phase=SubPhase.SPOILS_EXPAND_CHOICE,
            turn=gs.turn,
            options={"choices": choices},
        )])
        await broadcast_waiting_for(room, list(gs.spoils_pending.keys()))

    async def _resolve_and_advance(self, room: GameRoom):
        """Resolve current phase and advance. Used for non-agenda phases."""
        gs = room.game_state
        events = gs.resolve_current_phase()
        await self._broadcast_phase_result(room, events)
        await self._auto_resolve_phases(room)

    async def _auto_resolve_phases(self, room: GameRoom):
        """Auto-resolve phases that don't need player input."""
        gs = room.game_state
        while gs.phase in (Phase.WAR_PHASE, Phase.SCORING, Phase.CLEANUP):
            # Check for pending sub-choices before resolving (avoids re-entering WAR_PHASE)
            if gs.respawn_pending:
                await self._send_respawn_options(room)
                return
            events = gs.resolve_current_phase()
            await self._broadcast_phase_result(room, events)
            if gs.phase == Phase.GAME_OVER:
                return
            if gs.has_pending_war_support_choices():
                for sid in list(room.ai_spirit_ids):
                    if sid in gs.war_support_pending:
                        choices = []
                        for entry in gs.war_support_pending[sid]:
                            choices.append({
                                "target": entry["faction_a"]
                                if entry["faction_a"] == gs.spirits[sid].guided_faction
                                else entry["faction_b"]
                            })
                        await self._handle_game_message(room.room_code, sid, C2S.SUBMIT_WAR_SUPPORT_CHOICE, {"choices": choices})
                if gs.has_pending_war_support_choices():
                    await self._send_war_support_options(room)
                    return
            # If winner choices are pending, auto-submit for AI then send to humans
            if gs.winner_choice_pending:
                ai_winner_events = []
                for sid in list(room.ai_spirit_ids):
                    if sid in gs.winner_choice_pending:
                        err, evts = gs.submit_winner_choice(
                            sid, ai.get_ai_winner_choice(gs.winner_choice_pending[sid]))
                        if not err:
                            ai_winner_events.extend(evts)
                if ai_winner_events:
                    await self._broadcast_phase_result(room, ai_winner_events)
                if not gs.winner_choice_pending:
                    # All winner choices were AI — spoils may now be pending
                    pass  # fall through to spoils check below
                else:
                    for sid, war_choices in gs.winner_choice_pending.items():
                        await room.send_to(sid, create_message(S2C.PHASE_START, {
                            "phase": SubPhase.WINNER_CHOICE,
                            "turn": gs.turn,
                            "options": {"choices": war_choices},
                        }))
                    waiting_for = list(gs.winner_choice_pending.keys())
                    await room.broadcast(create_message(S2C.WAITING_FOR,
                        {"players_remaining": waiting_for}))
                    return
            # If spoils choices are pending, auto-submit for AI then send to humans
            if gs.spoils_pending:
                ai_spoils_events = []
                for sid in list(room.ai_spirit_ids):
                    if sid in gs.spoils_pending:
                        pending_list = gs.spoils_pending[sid]
                        err, evts = gs.submit_spoils_choice(
                            sid, ai.get_ai_spoils_choice(pending_list))
                        if not err:
                            ai_spoils_events.extend(evts)
                for sid in list(room.ai_spirit_ids):
                    if sid in gs.spoils_pending:
                        pending_list = gs.spoils_pending[sid]
                        change_pendings = [p for p in pending_list
                                           if p.stage == SubPhase.CHANGE_CHOICE]
                        if change_pendings:
                            err, evts = gs.submit_spoils_change_choice(
                                sid, ai.get_ai_spoils_change_choice(change_pendings))
                            if not err:
                                ai_spoils_events.extend(evts)
                for sid in list(room.ai_spirit_ids):
                    if sid in gs.spoils_pending:
                        pending_list = gs.spoils_pending[sid]
                        expand_pendings = [p for p in pending_list
                                           if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
                        if expand_pendings:
                            err, evts = gs.submit_spoils_expand_choice(
                                sid, ai.get_ai_spoils_expand_choice(expand_pendings))
                            if not err:
                                ai_spoils_events.extend(evts)
                if ai_spoils_events:
                    await self._broadcast_phase_result(room, ai_spoils_events)
                if not gs.spoils_pending:
                    continue
                await self._send_spoils_options(room)
                return
            # If respawn choices are pending (after war/spoils), send options and stop
            if gs.respawn_pending:
                await self._send_respawn_options(room)
                return
            # If ejection choices are pending (after scoring), send options and stop
            if gs.ejection_pending:
                await self._send_ejection_options(room)
                return

        # Now at a phase that needs player input; game loop handles resolution
        if gs.phase in (Phase.VAGRANT_PHASE, Phase.AGENDA_PHASE):
            await self._send_phase_options(room)
            # _send_phase_options → _resolve_ai_inputs → signal_submission; game loop drives resolution

    async def _broadcast_phase_result(self, room: GameRoom, events: list):
        gs = room.game_state
        snapshot = gs.get_snapshot()
        await room.broadcast(create_message(S2C.PHASE_RESULT, {
            "phase": gs.phase.value,
            "events": events,
            "state": snapshot.to_dict(),
        }))

    async def run(self):
        from websockets.asyncio.server import serve
        async with serve(self.handle_connection, self.host, self.port):
            print(f"Server running on ws://{self.host}:{self.port}")
            await asyncio.Future()  # run forever


async def main(host: str = "localhost", port: int = 8765):
    server = GameServer(host, port)
    await server.run()
