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

from shared.constants import MessageType, Phase, SubPhase, AgendaType, VP_TO_WIN
from shared.protocol import create_message, parse_message
from server.game_state import GameState
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
            # Reject if at human player cap (spectators don't count toward cap)
            if room.human_player_count() >= 5:
                await ws.send(create_message(MessageType.ERROR, {"message": "Room full."}))
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

        # First player becomes host
        if not room.host_spirit_id:
            room.host_spirit_id = spirit_id

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
            for s in room.players.values() if not s.is_spectator
        ]
        spectators = [
            {"spirit_id": s.spirit_id, "name": s.player_name, "connected": s.connected}
            for s in room.players.values() if s.is_spectator
        ]
        await room.broadcast(create_message(MessageType.LOBBY_STATE, {
            "room_code": room.room_code,
            "players": players,
            "spectators": spectators,
            "host_spirit_id": room.host_spirit_id,
            "vp_to_win": room.vp_to_win,
            "ai_player_count": room.ai_player_count,
            "all_ready": room.can_start(),
        }))

    async def _handle_game_message(self, room_code: str, spirit_id: str,
                                    msg_type: MessageType, payload: dict):
        room = self.rooms.get(room_code)
        if not room:
            return

        if msg_type == MessageType.READY:
            session = room.players.get(spirit_id)
            if session and not session.is_spectator:
                session.ready = not session.ready
                await self._broadcast_lobby_state(room)

        elif msg_type == MessageType.START_GAME:
            if spirit_id != room.host_spirit_id:
                await room.send_to(spirit_id, create_message(MessageType.ERROR,
                    {"message": "Only the host can start the game"}))
                return
            if not room.can_start():
                await room.send_to(spirit_id, create_message(MessageType.ERROR,
                    {"message": "Not all players are ready"}))
                return
            if not room.started:
                await self._start_game(room)

        elif msg_type == MessageType.SET_LOBBY_OPTIONS:
            if spirit_id != room.host_spirit_id:
                await room.send_to(spirit_id, create_message(MessageType.ERROR,
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
            await self._broadcast_lobby_state(room)

        elif msg_type == MessageType.TOGGLE_SPECTATOR:
            session = room.players.get(spirit_id)
            if not session:
                return
            if session.is_spectator:
                # Become player — check capacity
                if room.human_player_count() >= 5:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR,
                        {"message": "Room full."}))
                    return
                session.is_spectator = False
                # Ensure room has a host if host slot was empty
                if not room.host_spirit_id:
                    room.host_spirit_id = spirit_id
            else:
                # Become spectator — check spectator cap
                if room.spectator_count() >= 10:
                    await room.send_to(spirit_id, create_message(MessageType.ERROR,
                        {"message": "Spectator slots full."}))
                    return
                session.is_spectator = True
                session.ready = False
            await self._broadcast_lobby_state(room)

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
                    if pending_list and any(p.stage == "change_choice" for p in pending_list):
                        change_pendings = [p for p in pending_list if p.stage == "change_choice"]
                        change_options = []
                        for p in change_pendings:
                            change_options.append({
                                "cards": [c.value for c in p.change_cards],
                                "loser": p.loser,
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
        initial_snapshot, turn_results = room.game_state.setup_game(
            player_info, vp_to_win=room.vp_to_win)

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
        # Auto-resolve AI inputs
        await self._resolve_ai_inputs(room)

    async def _resolve_ai_inputs(self, room: GameRoom):
        """Submit actions on behalf of AI spirits and trigger resolution if complete."""
        gs = room.game_state
        if room.tutorial_mode and gs.phase == Phase.VAGRANT_PHASE:
            # Sequential AI vagrant actions with faction exclusion to prevent contention
            taken: set[str] = set()
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
        if gs.all_inputs_received():
            if gs.phase == Phase.VAGRANT_PHASE:
                await self._resolve_and_advance(room)
            elif gs.phase == Phase.AGENDA_PHASE:
                await self._handle_agenda_resolution(room)

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

        # All change choices done (AI-only or none) — broadcast modifier events if any
        if room._pending_change_events:
            all_change_events = room._pending_change_events
            room._pending_change_events = []
            await self._broadcast_phase_result(room, all_change_events)

        # Resolve immediately
        events = gs.resolve_agenda_phase_after_changes()
        await self._broadcast_phase_result(room, events)
        await self._auto_resolve_phases(room)

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
            # If spoils choices are pending, auto-submit for AI then send to humans
            if gs.spoils_pending:
                ai_spoils_events = []
                # Auto-submit spoils for AI spirits
                for sid in list(room.ai_spirit_ids):
                    if sid in gs.spoils_pending:
                        pending_list = gs.spoils_pending[sid]
                        err, evts = gs.submit_spoils_choice(
                            sid, ai.get_ai_spoils_choice(pending_list))
                        if not err:
                            ai_spoils_events.extend(evts)
                # Auto-submit spoils change choices for AI spirits
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
                if ai_spoils_events:
                    await self._broadcast_phase_result(room, ai_spoils_events)
                if not gs.spoils_pending:
                    # All spoils were AI — phase advanced to SCORING, continue loop
                    continue
                # Human spirits still have pending spoils — send options
                for sid, pending_list in gs.spoils_pending.items():
                    choices = []
                    for p in pending_list:
                        choices.append({
                            "cards": [c.value for c in p.cards],
                            "loser": p.loser,
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
