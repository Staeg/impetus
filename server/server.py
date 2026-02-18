"""WebSocket server: lobby/room management, game lifecycle."""

import asyncio
import json
import traceback
import uuid
import string
import random
from typing import Optional
import websockets
from websockets.asyncio.server import serve, ServerConnection

from shared.constants import MessageType, Phase, AgendaType
from shared.protocol import create_message, parse_message
from server.game_state import GameState


class PlayerSession:
    def __init__(self, ws: ServerConnection, player_name: str, spirit_id: str):
        self.ws = ws
        self.player_name = player_name
        self.spirit_id = spirit_id
        self.ready = False
        self.connected = True


class GameRoom:
    def __init__(self, room_code: str):
        self.room_code = room_code
        self.players: dict[str, PlayerSession] = {}  # spirit_id -> session
        self.game_state: Optional[GameState] = None
        self.started = False

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

    def reconnect_player(self, spirit_id: str, ws: ServerConnection):
        if spirit_id in self.players:
            self.players[spirit_id].ws = ws
            self.players[spirit_id].connected = True

    def all_ready(self) -> bool:
        return (len(self.players) >= 2 and
                all(p.ready for p in self.players.values()))

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
                    await ws.send(create_message(MessageType.ERROR, {"message": "Invalid message format"}))
                    continue

                print(f"[server] Received {msg_type.value} from {spirit_id or 'new'}")
                if msg_type == MessageType.JOIN_GAME:
                    room_code, spirit_id = await self._handle_join(ws, payload)
                    print(f"[server] Join result: room={room_code}, spirit={spirit_id}")
                    if room_code and spirit_id:
                        self.ws_to_room[ws] = (room_code, spirit_id)
                elif room_code and spirit_id:
                    try:
                        await self._handle_game_message(room_code, spirit_id, msg_type, payload)
                    except Exception as e:
                        print(f"[server] Error handling {msg_type.value} from {spirit_id}: {e}")
                        traceback.print_exc()
                        room = self.rooms.get(room_code)
                        if room:
                            await room.send_to(spirit_id, create_message(MessageType.ERROR,
                                {"message": "Server error processing action"}))
                else:
                    await ws.send(create_message(MessageType.ERROR, {"message": "Not in a room"}))
        except websockets.exceptions.ConnectionClosed:
            pass
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
                await ws.send(create_message(MessageType.ERROR, {"message": f"Room {room_code} not found"}))
                return None, None
            if room.started:
                # Try reconnect
                for sid, session in room.players.items():
                    if session.player_name == player_name and not session.connected:
                        room.reconnect_player(sid, ws)
                        # Send current game state
                        if room.game_state:
                            snapshot = room.game_state.get_snapshot()
                            await ws.send(create_message(MessageType.GAME_START, snapshot.to_dict()))
                        return room_code, sid
                await ws.send(create_message(MessageType.ERROR, {"message": "Game already started"}))
                return None, None
        else:
            # Create new room with requested code or random
            if create_room:
                room_code = create_room.upper()[:6]
                if room_code in self.rooms:
                    await ws.send(create_message(MessageType.ERROR, {"message": f"Room {room_code} already exists"}))
                    return None, None
            else:
                room_code = self._generate_room_code()
            room = GameRoom(room_code)
            self.rooms[room_code] = room

        # Check for duplicate name in lobby
        for existing in room.players.values():
            if existing.player_name.lower() == player_name.lower():
                await ws.send(create_message(MessageType.ERROR,
                    {"message": f"Name '{player_name}' is already taken"}))
                return None, None

        spirit_id = str(uuid.uuid4())[:8]
        session = PlayerSession(ws, player_name, spirit_id)
        room.add_player(session)

        await ws.send(create_message(MessageType.LOBBY_STATE, {
            "room_code": room_code,
            "spirit_id": spirit_id,
            "player_name": player_name,
        }))
        await self._broadcast_lobby_state(room)
        return room_code, spirit_id

    async def _broadcast_lobby_state(self, room: GameRoom):
        players = [
            {"spirit_id": s.spirit_id, "name": s.player_name, "ready": s.ready, "connected": s.connected}
            for s in room.players.values()
        ]
        await room.broadcast(create_message(MessageType.LOBBY_STATE, {
            "room_code": room.room_code,
            "players": players,
        }))

    async def _handle_game_message(self, room_code: str, spirit_id: str,
                                    msg_type: MessageType, payload: dict):
        room = self.rooms.get(room_code)
        if not room:
            return

        if msg_type == MessageType.READY:
            session = room.players.get(spirit_id)
            if session:
                session.ready = not session.ready
                await self._broadcast_lobby_state(room)
                if room.all_ready() and not room.started:
                    await self._start_game(room)

        elif msg_type == MessageType.SUBMIT_VAGRANT_ACTION:
            if room.game_state and room.game_state.phase == Phase.VAGRANT_PHASE:
                error = room.game_state.submit_action(spirit_id, payload)
                if error:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR, {"message": error}))
                else:
                    await self._broadcast_waiting(room)
                    if room.game_state.all_inputs_received():
                        await self._resolve_and_advance(room)

        elif msg_type == MessageType.SUBMIT_AGENDA_CHOICE:
            if room.game_state and room.game_state.phase == Phase.AGENDA_PHASE:
                error = room.game_state.submit_action(spirit_id, payload)
                if error:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR, {"message": error}))
                else:
                    await self._broadcast_waiting(room)
                    if room.game_state.all_inputs_received():
                        await self._handle_agenda_resolution(room)

        elif msg_type == MessageType.SUBMIT_CHANGE_CHOICE:
            if room.game_state:
                error, change_events = room.game_state.submit_change_choice(
                    spirit_id, payload.get("card_index", 0))
                if error:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR, {"message": error}))
                else:
                    # Collect change events; don't broadcast until all spirits have chosen
                    if not hasattr(room, '_pending_change_events'):
                        room._pending_change_events = []
                    room._pending_change_events.extend(change_events)
                    # Update waiting list
                    if room.game_state.has_pending_change_choices():
                        waiting_for = list(room.game_state.change_pending.keys())
                        await room.broadcast(create_message(MessageType.WAITING_FOR, {
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
                        await self._auto_resolve_phases(room)

        elif msg_type == MessageType.SUBMIT_EJECTION_AGENDA:
            if room.game_state:
                error = room.game_state.submit_ejection_choice(
                    spirit_id,
                    payload.get("remove_type", ""),
                    payload.get("add_type", ""),
                )
                if error:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR, {"message": error}))
                elif room.game_state.has_pending_sub_choices():
                    waiting_for = list(room.game_state.ejection_pending.keys())
                    await room.broadcast(create_message(MessageType.WAITING_FOR, {
                        "players_remaining": waiting_for,
                    }))
                else:
                    events = room.game_state.finalize_sub_choices()
                    await self._broadcast_phase_result(room, events)
                    await self._auto_resolve_phases(room)

        elif msg_type == MessageType.SUBMIT_SPOILS_CHOICE:
            if room.game_state:
                card_indices = payload.get("card_indices", [])
                # Backwards compat: single card_index → list
                if not card_indices and "card_index" in payload:
                    card_indices = [payload["card_index"]]
                error, events = room.game_state.submit_spoils_choice(
                    spirit_id, card_indices)
                if error:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    # Check if this spirit now needs change modifier choices
                    pending_list = room.game_state.spoils_pending.get(spirit_id)
                    if pending_list and any(p.get("stage") == "change_choice" for p in pending_list):
                        change_pendings = [p for p in pending_list if p.get("stage") == "change_choice"]
                        change_options = []
                        for p in change_pendings:
                            change_options.append({
                                "cards": [c.value for c in p.get("change_cards", [])],
                                "loser": p.get("loser", ""),
                            })
                        await room.send_to(spirit_id, create_message(MessageType.PHASE_START, {
                            "phase": "spoils_change_choice",
                            "turn": room.game_state.turn,
                            "options": {"choices": change_options},
                        }))
                        waiting_for = list(room.game_state.spoils_pending.keys())
                        await room.broadcast(create_message(MessageType.WAITING_FOR, {
                            "players_remaining": waiting_for,
                        }))
                    elif not room.game_state.spoils_pending:
                        await self._auto_resolve_phases(room)
                    else:
                        waiting_for = list(room.game_state.spoils_pending.keys())
                        await room.broadcast(create_message(MessageType.WAITING_FOR, {
                            "players_remaining": waiting_for,
                        }))

        elif msg_type == MessageType.SUBMIT_SPOILS_CHANGE_CHOICE:
            if room.game_state:
                card_indices = payload.get("card_indices", [])
                if not card_indices and "card_index" in payload:
                    card_indices = [payload["card_index"]]
                error, events = room.game_state.submit_spoils_change_choice(
                    spirit_id, card_indices)
                if error:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR, {"message": error}))
                else:
                    await self._broadcast_phase_result(room, events)
                    if not room.game_state.spoils_pending:
                        await self._auto_resolve_phases(room)
                    else:
                        waiting_for = list(room.game_state.spoils_pending.keys())
                        await room.broadcast(create_message(MessageType.WAITING_FOR, {
                            "players_remaining": waiting_for,
                        }))

    async def _start_game(self, room: GameRoom):
        room.started = True
        player_info = [
            {"spirit_id": s.spirit_id, "name": s.player_name}
            for s in room.players.values()
        ]
        room.game_state = GameState()
        initial_snapshot, turn_results = room.game_state.setup_game(player_info)

        # Send initial state (pre-setup) so client starts with just starting hexes
        await room.broadcast(create_message(MessageType.GAME_START, initial_snapshot.to_dict()))

        # Send each automated turn with its own post-turn snapshot so the
        # client's animation system can diff hex ownership correctly.
        for events, snapshot in turn_results:
            await room.broadcast(create_message(MessageType.PHASE_RESULT, {
                "phase": room.game_state.phase.value,
                "events": events,
                "state": snapshot.to_dict(),
            }))

        # Send phase options to each player
        await self._send_phase_options(room)

    async def _send_phase_options(self, room: GameRoom):
        gs = room.game_state
        for spirit_id in gs.spirits:
            options = gs.get_phase_options(spirit_id)
            await room.send_to(spirit_id, create_message(MessageType.PHASE_START, {
                "phase": gs.phase.value,
                "turn": gs.turn,
                "options": options,
            }))
        await self._broadcast_waiting(room)

    async def _broadcast_waiting(self, room: GameRoom):
        gs = room.game_state
        remaining = gs.get_spirits_needing_input()
        await room.broadcast(create_message(MessageType.WAITING_FOR, {
            "players_remaining": remaining,
        }))

    async def _handle_agenda_resolution(self, room: GameRoom):
        """Handle agenda phase after all inputs received: prepare changes first."""
        gs = room.game_state
        change_events = gs.prepare_change_choices()
        await self._broadcast_phase_result(room, change_events)

        if gs.has_pending_change_choices():
            # Send change_choice to each pending spirit
            for spirit_id, cards in gs.change_pending.items():
                await room.send_to(spirit_id, create_message(MessageType.PHASE_START, {
                    "phase": "change_choice",
                    "turn": gs.turn,
                    "options": {"cards": [c.value for c in cards]},
                }))
            waiting_for = list(gs.change_pending.keys())
            await room.broadcast(create_message(MessageType.WAITING_FOR, {
                "players_remaining": waiting_for,
            }))
            return

        # No change choices needed - resolve immediately
        events = gs.resolve_agenda_phase_after_changes()
        await self._broadcast_phase_result(room, events)
        await self._auto_resolve_phases(room)

    async def _send_ejection_options(self, room: GameRoom):
        """Send ejection choice options to spirits that need them."""
        gs = room.game_state
        for spirit_id, faction_id in gs.ejection_pending.items():
            faction = gs.factions[faction_id]
            agenda_pool = [c.agenda_type.value for c in faction.agenda_pool]
            await room.send_to(spirit_id, create_message(MessageType.PHASE_START, {
                "phase": "ejection_choice",
                "turn": gs.turn,
                "options": {
                    "faction": faction_id,
                    "agenda_pool": agenda_pool,
                    "agenda_types": [at.value for at in AgendaType],
                },
            }))
        waiting_for = list(gs.ejection_pending.keys())
        await room.broadcast(create_message(MessageType.WAITING_FOR, {
            "players_remaining": waiting_for,
        }))

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
            events = gs.resolve_current_phase()
            await self._broadcast_phase_result(room, events)
            if gs.phase == Phase.GAME_OVER:
                return
            # If spoils choices are pending, send ALL options to each spirit
            if gs.spoils_pending:
                for sid, pending_list in gs.spoils_pending.items():
                    choices = []
                    for p in pending_list:
                        choices.append({
                            "cards": [c.value for c in p["cards"]],
                            "loser": p.get("loser", ""),
                        })
                    await room.send_to(sid, create_message(MessageType.PHASE_START, {
                        "phase": "spoils_choice",
                        "turn": gs.turn,
                        "options": {"choices": choices},
                    }))
                waiting_for = list(gs.spoils_pending.keys())
                await room.broadcast(create_message(MessageType.WAITING_FOR, {
                    "players_remaining": waiting_for,
                }))
                return
            # If ejection choices are pending (after scoring), send options and stop
            if gs.ejection_pending:
                await self._send_ejection_options(room)
                return

        # Now at a phase that needs player input
        if gs.phase in (Phase.VAGRANT_PHASE, Phase.AGENDA_PHASE):
            await self._send_phase_options(room)
            # If no spirit actually needs input, resolve immediately
            if gs.all_inputs_received():
                await self._resolve_and_advance(room)

    async def _broadcast_phase_result(self, room: GameRoom, events: list):
        gs = room.game_state
        snapshot = gs.get_snapshot()
        await room.broadcast(create_message(MessageType.PHASE_RESULT, {
            "phase": gs.phase.value,
            "events": events,
            "state": snapshot.to_dict(),
        }))

    async def run(self):
        async with serve(self.handle_connection, self.host, self.port):
            print(f"Server running on ws://{self.host}:{self.port}")
            await asyncio.Future()  # run forever


async def main(host: str = "localhost", port: int = 8765):
    server = GameServer(host, port)
    await server.run()
