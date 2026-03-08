# Era 1 Technical Reference — Dawn

This document is intended for developers and coding assistants. It covers the full implementation of Era 1 gameplay: data structures, server-side phase logic, client-server protocol, client rendering and animation pipeline, and key invariants. See [Era 1.md](Era%201.md) for player-facing rules.

---

## Repository layout

```
server/
  game_state.py    — GameState: authoritative phase machine (~925 lines)
  agenda.py        — All agenda resolution functions (~530 lines)
  war.py           — War dataclass and resolution (~86 lines)
  scoring.py       — VP calculation (~50 lines)
  faction.py       — Faction state and agenda pool (~117 lines)
  spirit.py        — Spirit (player) state (~58 lines)
  hex_map.py       — Hex grid, ownership, idol tracking (~102 lines)
  server.py        — WebSocket server, room management (~868 lines)
  ai.py            — AI decision logic (~155 lines)

client/
  app.py                       — Scene manager, network routing (~app)
  network.py                   — WebSocket client on background thread
  scenes/
    game_scene.py              — Primary gameplay scene (~2274 lines)
    animation_orchestrator.py  — Event → animation translation (~494 lines)
    change_tracker.py          — Per-turn faction delta tracking (~237 lines)
    lobby.py, menu.py, results.py, settings_scene.py — Other scenes
  renderer/
    ui_renderer.py             — HUD, panels, buttons, tooltips (~1088 lines)
    hex_renderer.py            — Hex grid, wars, idols
    animation.py               — Tween, AgendaSlideAnimation, etc.
    assets.py, font_cache.py   — Asset loading

shared/
  constants.py    — Enums and game constants
  protocol.py     — C2S / S2C message type strings, SubPhase strings
  models.py       — Serialisable dataclasses (FactionState, SpiritState, etc.)
  hex_utils.py    — Axial hex math (coordinate conversion, neighbours, etc.)
```

---

## Shared constants (`shared/constants.py`)

### Enums

```python
class Phase(Enum):
    LOBBY, SETUP, VAGRANT_PHASE, AGENDA_PHASE, WAR_PHASE,
    SCORING, CLEANUP, GAME_OVER

class AgendaType(Enum):
    STEAL, TRADE, EXPAND, CHANGE

AGENDA_RESOLUTION_ORDER = [TRADE, STEAL, EXPAND, CHANGE]

class IdolType(Enum):
    BATTLE, AFFLUENCE, SPREAD

class ChangeModifierTarget(Enum):
    TRADE, STEAL, EXPAND

CHANGE_DECK = [ChangeModifierTarget.TRADE, .STEAL, .EXPAND]

class FactionId(Enum):
    MOUNTAIN, MESA, SAND, PLAINS, RIVER, JUNGLE
```

### Key numeric constants

| Constant | Value | Meaning |
|---|---|---|
| `STARTING_GOLD` | 0 | Each Faction's initial gold |
| `STARTING_INFLUENCE` | 3 | Influence set when a Spirit guides a Faction |
| `MAX_INFLUENCE` | 3 | Cap (not enforced beyond assignment) |
| `VP_TO_WIN` | 100 | Default Era 1 end threshold |
| `BATTLE_IDOL_VP` | 5 | VP per Battle Idol per War won |
| `AFFLUENCE_IDOL_VP` | 2 | VP per Affluence Idol per gold gained |
| `SPREAD_IDOL_VP` | 5 | VP per Spread Idol per territory gained |
| `MAP_SIDE_LENGTH` | 5 | Hex grid side length (31 total hexes) |

### Map constants

- `FACTION_START_HEXES` — `dict[FactionId → (q, r)]` — the six starting positions around the centre hex.
- `HABITAT_STARTING_MODIFIERS` — `dict[str → list[ChangeModifierTarget]]` — initial Change modifiers per habitat name.

---

## Shared models (`shared/models.py`)

All dataclasses are JSON-serialisable via `.to_dict()` / `.from_dict()`.

| Class | Purpose | Key fields |
|---|---|---|
| `HexCoord` | Axial hex coordinate | `q, r` |
| `Idol` | A placed idol | `type: IdolType, position: HexCoord, owner_spirit: str` |
| `AgendaCard` | One card in a pool | `agenda_type: AgendaType` |
| `FactionState` | Serialisable faction snapshot | `faction_id, color, gold, territories, agenda_pool, change_modifiers, regard, guiding_spirit, worship_spirit, race` |
| `SpiritState` | Serialisable spirit snapshot | `spirit_id, name, influence, is_vagrant, guided_faction, idols, victory_points, habitat_affinity, race_affinity` |
| `WarState` | Serialisable war snapshot | `war_id, faction_a, faction_b` |
| `GameStateSnapshot` | Full state for client | `turn, phase, factions, spirits, wars, all_idols, hex_ownership, faction_order` |

`GameStateSnapshot.hex_ownership` is `dict["q,r" → faction_id | None]`.

---

## Protocol (`shared/protocol.py`)

### Client → Server (`C2S`)

| Message | Sent when |
|---|---|
| `JOIN_GAME` | Client connects and joins/creates a room |
| `READY` | Player marks themselves ready in lobby |
| `START_GAME` | Host starts the game |
| `SET_LOBBY_OPTIONS` | Host changes vp_to_win, ai count, tutorial mode |
| `TOGGLE_SPECTATOR` | Toggle spectator mode |
| `SUBMIT_VAGRANT_ACTION` | Spirit submits guidance / idol placement |
| `SUBMIT_AGENDA_CHOICE` | Spirit picks agenda card from hand |
| `SUBMIT_EXPAND_CHOICE` | Spirit picks hex for guided Expand |
| `SUBMIT_CHANGE_CHOICE` | Spirit picks Change modifier card |
| `SUBMIT_EJECTION_AGENDA` | Ejected spirit picks card to remove and add |
| `SUBMIT_SPOILS_CHOICE` | Spirit picks spoils card(s) after winning wars |
| `SUBMIT_SPOILS_CHANGE_CHOICE` | Follow-up modifier pick if spoils card was Change |
| `SUBMIT_SPOILS_EXPAND_CHOICE` | Spirit picks enemy territory to claim per Expand spoils |
| `SUBMIT_WINNER_CHOICE` | Spirit decides which faction wins when only one side is guided |

### Server → Client (`S2C`)

| Message | Sent when |
|---|---|
| `LOBBY_STATE` | Room state broadcast (player list, settings) |
| `GAME_START` | Game begins; includes initial snapshot |
| `PHASE_START` | New phase or sub-phase begins; includes options for that spirit |
| `WAITING_FOR` | List of spirits still to submit |
| `PHASE_RESULT` | Phase resolved; includes events list and final state snapshot |
| `GAME_OVER` | A player reached VP threshold; includes final state |
| `ERROR` | Server-side validation failure |

### Sub-phases (`SubPhase` strings)

Sub-phases are bare strings sent as the `phase` field inside a `PHASE_START` message, not members of the `Phase` enum.

| SubPhase | Trigger |
|---|---|
| `change_choice` | Guided spirit played Change; must pick modifier card |
| `expand_choice` | Guided spirit can afford Expand; must pick target hex |
| `ejection_choice` | Spirit was ejected (0 influence); must pick card to remove/add |
| `spoils_choice` | Spirit won one or more wars; must pick spoils card per war |
| `spoils_change_choice` | One or more spoils cards was Change; must pick modifier(s) |
| `spoils_expand_choice` | One or more spoils cards was Expand (guided); must pick enemy territory per war |
| `winner_choice` | Exactly one side of a war is Guided; spirit decides which faction wins |

---

## Server architecture

### `server/server.py` — WebSocket server

**Key classes**: `PlayerSession`, `GameRoom`, `GameServer`

#### `GameRoom`
- `room_code: str` — 4-letter room identifier
- `players: dict[spirit_id → PlayerSession]`
- `game_state: GameState`
- `vp_to_win: int`, `ai_player_count: int`, `tutorial_mode: bool`
- `ai_spirit_ids: set[str]`
- `signal_submission()` / `wait_for_submission()` — asyncio Event used to wake the game loop when any spirit submits

#### `GameServer` message routing

`_handle_game_message(room_code, spirit_id, msg_type, payload)` dispatches incoming C2S messages:

- `SUBMIT_VAGRANT_ACTION` → `game_state.submit_action()`
- `SUBMIT_AGENDA_CHOICE` → `game_state.submit_action()`
- `SUBMIT_EXPAND_CHOICE` → `game_state.submit_expand_choice()`
- `SUBMIT_CHANGE_CHOICE` → `game_state.submit_change_choice()` → broadcast events
- `SUBMIT_EJECTION_AGENDA` → `game_state.submit_ejection_choice()`
- `SUBMIT_SPOILS_CHOICE` → `game_state.submit_spoils_choice()` → broadcast events
- `SUBMIT_SPOILS_CHANGE_CHOICE` → `game_state.submit_spoils_change_choice()`
- `SUBMIT_SPOILS_EXPAND_CHOICE` → `game_state.submit_spoils_expand_choice()` → broadcast events
- `SUBMIT_WINNER_CHOICE` → `game_state.submit_winner_choice()` → broadcast events

After each submission, `room.signal_submission()` wakes the game loop.

#### `_run_game_loop(room)` — main async loop

```
VAGRANT_PHASE:
  _send_phase_options()          → PHASE_START to each spirit
  _resolve_ai_inputs()           → AI spirits auto-submit
  wait_for_submission()          → block until all submitted
  game_state.resolve_current_phase()
  _broadcast_phase_result(events)
  _auto_resolve_phases()

AGENDA_PHASE:
  _send_phase_options()          → PHASE_START (hand of cards)
  _resolve_ai_inputs()
  wait_for_submission()
  _handle_agenda_resolution()    → prepares change/expand choices
    _send_ejection_options()     if ejection choices pending
  _auto_resolve_phases()

WAR_PHASE / SCORING / CLEANUP:
  _auto_resolve_phases() resolves these without player input,
  checking for pending sub-phases after each step
```

#### AI resolution (`server/ai.py`)

All AI decisions are random or simple heuristic:

| Function | Logic |
|---|---|
| `get_ai_vagrant_action()` | Guide faction first (prefer gaining Worship), then place idol (prefer own-idol hexes) |
| `get_ai_agenda_choice()` | Random pick from drawn hand |
| `get_ai_change_choice()` | Random modifier |
| `get_ai_expand_choice()` | Prefer own-idol hexes > empty hexes > enemy-idol hexes |
| `get_ai_ejection_choice()` | Random remove + random add |
| `get_ai_spoils_choice()` | Random pick per war |
| `get_ai_winner_choice()` | Always picks its own guided faction to win |
| `get_ai_spoils_expand_choice()` | Picks first available enemy territory |

In tutorial mode, AI spirits wait for all human spirits to submit in VAGRANT_PHASE before submitting their own actions.

---

## Game state machine (`server/game_state.py`)

### `GameState` — key attributes

```python
turn: int
phase: Phase
hex_map: HexMap
factions: dict[str, Faction]
spirits: dict[str, Spirit]
wars: list[War]

# Phase inputs (cleared each phase)
pending_actions: dict[str, dict]       # spirit_id → submitted action
drawn_hands: dict[str, list]           # spirit_id → agenda cards drawn

# Sub-phase state
change_pending: dict[str, list]        # spirit_id → drawn modifier cards
expand_pending: dict[str, str]         # spirit_id → faction_id
expand_chosen: dict[str, tuple]        # spirit_id → chosen hex
ejection_pending: dict[str, str]       # spirit_id → faction_id
spoils_pending: dict[str, list[SpoilsPendingEntry]]
winner_choice_pending: dict[str, list[dict]]   # spirit_id → [{war_id, faction_a, faction_b, guided_faction}]

# Cooldowns
guidance_cooldowns: dict[str, set[str]]  # spirit_id → blocked faction_ids

# Spoils helpers
normal_trade_factions: list[str]       # factions that traded normally (for spoils Trade bonus)
```

### `SpoilsPendingEntry`

```python
winner: str          # winning faction_id
loser: str
cards: list          # drawn agenda types for this war
expand_hexes: list   # available enemy territories for Expand spoils (if any)
expand_target: tuple | None  # auto-chosen target for unguided Expand
stage: str           # "" | SubPhase.CHANGE_CHOICE | SubPhase.SPOILS_EXPAND_CHOICE
change_cards: list   # modifier options (populated on second stage)
```

### Phase transitions

```
LOBBY → (setup_game) → VAGRANT_PHASE → AGENDA_PHASE → WAR_PHASE → SCORING → CLEANUP → VAGRANT_PHASE
                                                                                           ↓ (if VP_TO_WIN reached)
                                                                                        GAME_OVER
```

`Phase.SETUP` exists in the enum but is never transitioned into. Setup runs inside `setup_game()` during the LOBBY phase.

### Setup (`setup_game`)

1. Build `HexMap` (side length 5, 31 hexes).
2. Create 6 `Faction` objects; assign random `race` from `RACES`; apply `HABITAT_STARTING_MODIFIERS`.
3. Create one `Spirit` per player; assign random `habitat_affinity` and `race_affinity`.
4. Place each faction at its `FACTION_START_HEXES` position.
5. Run Turn 1 automatically: each faction draws a random agenda, resolve agendas, run war/scoring/cleanup.
6. Return `(initial_snapshot, [(events, post_turn_snapshot)])` for server to broadcast.

### Vagrant Phase resolution (`_resolve_vagrant_phase`)

1. **Idols placed** unconditionally from `pending_actions`.
2. **Guidance resolved**: group guide attempts by target faction.
   - Single contestant → spirit guides the faction; `spirit.guide_faction(faction_id)`.
   - Multiple contestants → nobody guides:
     - Check habitat affinity match → winner if exactly one.
     - Check race affinity match → winner if exactly one.
     - No winner → all contested spirits added to `guidance_cooldowns[spirit_id].add(faction_id)`.
   - Tutorial mode override: turn 2 only; if exactly one human and rest AI, human wins.
3. `_check_worship(faction, spirit, events)` is called for every newly guided faction.
4. Cooldowns from the **previous** vagrant phase are cleared at the **start** of this method.

### Agenda Phase resolution (`_resolve_agenda_phase`)

1. Distribute drawn hands: each guided spirit draws `1 + influence` cards via `faction.draw_agenda_cards(n)`.
2. All guided spirits submit `agenda_index`; unguided factions draw random card.
3. Influence decremented by 1 for each guided spirit.
4. **Pre-resolution sub-choices collected**:
   - `prepare_change_choices()` — for guided spirits playing CHANGE, draw modifier cards → `change_pending`.
   - `prepare_expand_choices()` — for guided spirits playing EXPAND who can afford and have reachable hexes → `expand_pending`.
   - Server sends PHASE_START for each sub-phase; waits for all submissions.
5. Call `agenda.resolve_agendas(...)` with all collected choices.
6. **Ejection**: any guided spirit with 0 influence after resolution → `ejection_pending`; server prompts `ejection_choice`.

### War Phase resolution (`_resolve_war_phase`)

1. **Snapshot power**: `power_snapshot[faction_id] = len(hex_map.get_faction_territories(faction_id))`.
2. **Resolve all wars** (wars resolve immediately — no two-turn lifecycle):
   - **Exactly one side Guided**: spirit decides winner → `winner_choice_pending[spirit_id].append({war_id, ...})`.
   - **Both or neither Guided**: `war.resolve(power_a, power_b)` — dice + power; no gold changes applied.
3. If `winner_choice_pending` has any entries: server sends `winner_choice` PHASE_START; spirit submits `choices: [{war_id, winner}]` via `SUBMIT_WINNER_CHOICE`.
4. After all winner choices: collect all war results and proceed to spoils.
5. **Draw spoils**: call `agenda.resolve_spoils(...)` → returns `(spoils_pending, auto_spoils_choices)`.
   - Non-guided winners and single-draw guided winners → `auto_spoils_choices` (batch finalized immediately).
   - Multi-draw guided winners → `spoils_pending`; server sends `spoils_choice` PHASE_START.
6. If any spoils card is **Expand** (guided winner): server sends `spoils_expand_choice` PHASE_START; spirit submits `choices: [{hex: {q, r}}]` via `SUBMIT_SPOILS_EXPAND_CHOICE`.
7. After all spoils choices received: `agenda.finalize_all_spoils(...)`.

### Scoring (`_resolve_scoring`)

Calls `scoring.calculate_scoring(factions, spirits, hex_map)`:

```python
for faction in factions.values():
    if not faction.worship_spirit:
        continue
    spirit = spirits[faction.worship_spirit]
    idols = hex_map.get_idols_in_territories(faction.faction_id)
    battle = count(idols, BATTLE)  * BATTLE_IDOL_VP  * faction.wars_won_this_turn
    affluence = count(idols, AFFLUENCE) * AFFLUENCE_IDOL_VP * faction.gold_gained_this_turn
    spread = count(idols, SPREAD)   * SPREAD_IDOL_VP  * faction.territories_gained_this_turn
    spirit.victory_points += battle + affluence + spread
```

If any spirit reaches `vp_to_win`, the game transitions to `GAME_OVER`.

### Cleanup (`_resolve_cleanup`)

- `faction.reset_turn_tracking()` — zeroes `gold_gained_this_turn`, `territories_gained_this_turn`, `wars_won_this_turn`.
- `faction.cleanup_deck()` — clears `played_agenda_this_turn`.
- Transitions to `VAGRANT_PHASE` if game not over.

### Worship check (`_check_worship`)

Called after any guidance change (new guidance or ejection):

```
if no current worship_spirit:
    spirit gains Worship
elif count_spirit_idols_in_faction(new_spirit) >= count_spirit_idols_in_faction(old_spirit):
    new_spirit displaces old_spirit as Worship holder
else:
    no change
```

### `get_phase_options(spirit_id)` — per-spirit phase options

Returns a dict consumed by the server's `_send_phase_options()` and forwarded to the client as the `options` field of `PHASE_START`.

- **VAGRANT_PHASE**: `available_factions` (non-guided, non-worshipping-you), `neutral_hexes`, `can_place_idol`, cooldown-excluded factions.
- **AGENDA_PHASE**: `hand` (drawn agenda cards as list of `AgendaType` strings), `influence`.

Sub-phase options are built separately and sent by the server just before waiting for that sub-phase's submissions.

---

## Agenda resolution (`server/agenda.py`)

### `resolve_agendas(factions, hex_map, agenda_choices, wars, events, is_spoils, spoils_conquests, normal_trade_factions, faction_counts, guided_expand_choices)`

Top-level resolver. Iterates `AGENDA_RESOLUTION_ORDER`, calling the appropriate `_resolve_*` function. Each step is simultaneous — all factions playing the same type resolve together using state from before that step.

#### `_resolve_trade`
- Calculates gold and regard gains using pre-resolution state.
- Co-trader bonus: +1 gold per other faction also trading.
- Spoils variant: adds bonus from normal-trade factions too.

#### `_resolve_steal`
- Snapshot neighbour gold before applying any changes.
- Each stealing faction collects gold from original neighbour balances.
- Each victim's gold decremented by net stolen (cannot go below 0).
- Triggers war if regard drops to ≤ −2 after steal.

#### `_resolve_expand`
- Guided choices pre-collected into `guided_expand_choices`.
- Collect all targets, detect contests (two or more factions targeting the same hex → all fail).
- Fail gives the `expand_fail_bonus` gold (`expand_modifier` on the Expand card).
- Spoils variant: claims a territory from the losing faction, no gold cost.
- Faction's `territories_gained_this_turn` is incremented on success.

#### `_resolve_change`
- Draw from `CHANGE_DECK` (already pre-collected for guided spirits via `change_pending`).
- Call `faction.add_change_modifier(modifier_target)`.
- Applied `faction_counts` times if the same faction played Change multiple times (spoils only).

### `resolve_spoils(factions, hex_map, war_results, wars, events, normal_trade_factions, spirits)`

For each winning faction:
- Non-guided or single-draw: append to `auto_spoils_choices`.
- Guided with multiple draws: populate `spoils_pending[spirit_id]` with `SpoilsPendingEntry`.

Returns `(spoils_pending, auto_spoils_choices)`.

### `finalize_all_spoils(factions, hex_map, wars, events, all_spoils, normal_trade_factions)`

Batch-resolves all spoils simultaneously:
1. Detect contested Expand spoils (two factions targeting the same enemy territory → both fail, both get expand_fail gold).
2. Call `resolve_agendas()` once per agenda type.

---

## Server-side data classes

### `Faction` (`server/faction.py`)

```python
faction_id: str
gold: int                        # current gold
agenda_pool: list[AgendaCard]    # static 4-card pool
change_modifiers: dict[ChangeModifierTarget, int]
regard: dict[str, int]           # faction_id → regard
guiding_spirit: Optional[str]
worship_spirit: Optional[str]
race: str
gold_gained_this_turn: int       # tracking for scoring
territories_gained_this_turn: int
wars_won_this_turn: int
played_agenda_this_turn: list[AgendaCard]
```

Key methods:
- `add_gold(amount)` — also increments `gold_gained_this_turn` if positive.
- `draw_agenda_cards(count)` — `random.choices(pool, k=count)` (with replacement).
- `replace_agenda_card(remove_type, add_type)` — ejection pool mutation.
- `to_state(hex_map) → FactionState` — serialise, includes `hex_map.get_faction_territories()`.

### `Spirit` (`server/spirit.py`)

```python
spirit_id: str
influence: int
is_vagrant: bool
guided_faction: Optional[str]
has_placed_idol_as_vagrant: bool
idols: list[Idol]
victory_points: int
habitat_affinity: str
race_affinity: str
```

Key methods:
- `guide_faction(faction_id)` — sets `is_vagrant=False`, `guided_faction`, `influence=STARTING_INFLUENCE`.
- `become_vagrant()` — clears guided state.
- `place_idol(idol_type, position) → Idol`.
- `count_idols_in_hexes(hex_set) → int`.

### `War` (`server/war.py`)

```python
war_id: str              # UUID prefix (8 chars)
faction_a, faction_b: str
```

Key methods:
- `resolve(power_a, power_b) → dict` — rolls 1d6 per faction + power; returns full result dict.
- `resolve_forced(winner, guided_faction) → dict` — spirit-decided outcome; marks `forced=True` in result.
- `to_state() → WarState` — serialise.

### `HexMap` (`server/hex_map.py`)

```python
all_hexes: set[tuple[int,int]]
ownership: dict[tuple, Optional[str]]
idols: list[Idol]
```

Key methods (all O(n) or O(territories)):
- `get_faction_territories(faction_id) → set`
- `get_neutral_hexes() → set`
- `get_reachable_neutral_hexes(faction_id) → set` — neutrals adjacent to faction territory.
- `get_border_hex_pairs(faction_a, faction_b) → list[(hex_a, hex_b)]`
- `are_factions_neighbors(faction_a, faction_b) → bool`
- `get_live_neighbor_ids(faction_id, factions) → list[str]`
- `claim_hex(hex_coord, faction_id)` — sets ownership.
- `get_idols_in_territories(faction_id) → list[Idol]`
- `count_spirit_idols_in_faction(spirit_id, faction_id) → int`
- `get_random_reachable_neutral(faction_id) → (q, r)` — prefers idol hexes.

---

## Hex math (`shared/hex_utils.py`)

Axial coordinate system (pointy-top hexagons):

```python
hex_neighbor(q, r, direction)          # one of 6 neighbours
hex_neighbors(q, r) → list             # all 6
hex_distance(q1, r1, q2, r2) → int
axial_to_pixel(q, r, hex_size) → (x, y)
pixel_to_axial(px, py, hex_size) → (q, r)
hex_ring(center_q, center_r, radius) → list
hex_spiral(center_q, center_r, radius) → list
generate_hex_grid(side_length) → set   # side_length=5 → 31 hexes
hex_vertices(q, r, hex_size) → list[(x,y)]
hexes_are_adjacent(q1, r1, q2, r2) → bool
```

No pygame dependency — safe to import in both server and client contexts.

---

## Client networking (`client/network.py`)

### `NetworkClient`

Runs a background `asyncio` event loop in a `threading.Thread`. The PyGame main loop and the WebSocket loop never share a thread.

```
Main thread:  send(msg_type, payload)    → _outgoing queue
              poll() / poll_all()        ← incoming queue

Background:   _connect_and_listen()
                flush outgoing queue → ws.send()
                ws.recv() → parse_message() → incoming queue
```

- Exponential backoff retry on connection failure (1 s → 30 s max).
- `send()` queues messages if not yet connected; flushed automatically on reconnect.
- Message format: `shared.protocol.create_message()` → JSON string; `parse_message()` → `(msg_type, payload)`.

---

## Client application (`client/app.py`)

### `App`

- `current_scene` — one of `menu`, `lobby`, `game`, `results`, `settings`.
- `network: NetworkClient` (or `LocalTransport` for in-process testing).
- `my_spirit_id: str` — assigned by server on join.

#### `run()` — main async game loop (60 FPS)

```
for each frame:
  1. pygame events → current_scene.handle_event(event)
  2. network.poll_all() → _handle_network_message(msg_type, payload)
  3. current_scene.update(dt)
  4. current_scene.render(screen)
  5. pygame.display.flip(); await asyncio.sleep(0)
```

`_handle_network_message()` special-cases `S2C.GAME_START` to call `set_scene("game")` before forwarding the payload.

Scene interface: `handle_event(event)`, `update(dt)`, `render(screen)`, optional `handle_network(msg_type, payload)`.

---

## Client gameplay scene (`client/scenes/game_scene.py`)

~2274 lines. The largest file. All gameplay UI, phase management, and animation coordination lives here.

### Key state groups

**Game state** (updated from server snapshots):
```python
turn, phase
factions: dict[str, FactionState]
spirits: dict[str, SpiritState]
wars: list[WarState]
all_idols: list[Idol]
hex_ownership: dict[(q,r), str|None]
faction_order: list[str]
```

**Display state** (stale copy used while animations play):
```python
_display_hex_ownership
_display_factions
_display_wars
```

**Phase-specific input state**:
```python
# VAGRANT_PHASE
selected_faction, selected_hex, selected_idol_type

# AGENDA_PHASE
agenda_hand: list[dict]
selected_agenda_index: int

# CHANGE_CHOICE / SPOILS_CHANGE_CHOICE
change_cards: list[str]
spoils_change_entries: list[SpoilsEntry]

# SPOILS_CHOICE
spoils_entries: list[SpoilsEntry]
spoils_display_index: int

# EJECTION_CHOICE
ejection_pending, ejection_faction, ejection_pool
selected_ejection_remove_type, selected_ejection_add_type

# BATTLEGROUND_CHOICE
battleground_choice_wars, battleground_selections
battleground_selectable_hexes, battleground_selected_hexes

# EXPAND_CHOICE
expand_choice_hexes, expand_choice_faction, selected_hex
```

**Animation state**:
```python
animation: AnimationManager
orchestrator: AnimationOrchestrator
hex_renderer: HexRenderer
ui_renderer: UIRenderer
```

**Phase result queue**:
```python
_phase_result_queue: list[dict]   # PHASE_RESULT payloads, processed one at a time
_pending_game_over: dict | None
```

### Network message routing (`handle_network`)

Dispatch table `_net_handlers`:

| Message | Handler |
|---|---|
| `GAME_START` | `_handle_game_start` |
| `PHASE_START` | `_handle_phase_start` |
| `PHASE_RESULT` | `_handle_phase_result` (queues) |
| `WAITING_FOR` | `_handle_waiting_for` |
| `GAME_OVER` | `_handle_game_over` |
| `ERROR` | `_handle_error` |

### `PHASE_RESULT` processing pipeline

1. **`_handle_phase_result(payload)`** — appends to `_phase_result_queue`.
2. **`update(dt)`** — drains queue one entry at a time; only processes next when `orchestrator.has_animations_playing()` is False.
3. **`_process_phase_result(payload)`**:
   - `_snapshot_display_state()` — deep-copy `hex_ownership`, `factions`, `wars` into `_display_*` fields.
   - `_update_state_from_snapshot(payload["state"])` — update real state immediately.
   - Log events via `_log_events_batch(events)` → `change_tracker.process_event()`.
   - `orchestrator.process_agenda_events(events, ...)` → creates `AgendaSlideAnimation` objects with hex/gold/war reveal triggers.
   - VP-scored events → `IdolBeamAnimation` towards VP counter position.

By the time `process_event` runs, `self.factions` already has the final post-event state. The change tracker relies on its own `old_state` snapshot, not on comparing `self.factions` before and after.

### `PHASE_START` processing

`_handle_phase_start(payload)`:
- If animations are playing: store in `orchestrator.deferred_phase_start`.
- Else: call `_setup_phase_ui()` immediately.

`_setup_phase_ui()` routes to sub-phase setup methods via a dispatch table:

| Phase | Setup method |
|---|---|
| `vagrant_phase` | Build faction/idol buttons |
| `agenda_phase` | Populate `agenda_hand`; set `selected_agenda_index = -1` |
| `change_choice` | `_setup_change_choice_ui()` |
| `expand_choice` | `_setup_expand_choice_ui()` |
| `spoils_choice` | `_setup_spoils_choice_ui()` |
| `spoils_change_choice` | Setup spoils change entries |
| `ejection_choice` | `_setup_ejection_choice_ui()` |
| `battleground_choice` | `_setup_battleground_choice_ui()` |

### `update(dt)`

Each frame:
1. `animation.update(dt)` — advance all tweens and animations.
2. `orchestrator.apply_hex_reveals(display_hex_ownership)` — update display map as animations become active.
3. `orchestrator.apply_gold_deltas(display_factions)` — update displayed gold.
4. `orchestrator.apply_war_reveals(display_wars)` — update displayed wars.
5. Drain `_phase_result_queue` (one per frame if no animations playing).
6. `orchestrator.try_show_deferred_phase_ui(self)` — show deferred PHASE_START when ready.
7. Clear `_display_*` state when `animation.is_all_done()` and no deferred phase pending.

### `render(screen)`

Render order (back to front):
1. Hex grid via `HexRenderer` — uses `_display_hex_ownership` if active, else `hex_ownership`.
2. World-space effect animations (arrows, gold text) via `orchestrator.render_effect_animations()`.
3. HUD (phase, turn, VP) via `ui_renderer.draw_hud()`.
4. Faction overview strip via `ui_renderer.draw_faction_overview()`.
5. Persistent agenda slide animations via `orchestrator.render_persistent_agenda_animations()`.
6. Screen-space animations (idol beams, VP text) via `orchestrator.render_effect_animations(screen_space_only=True)`.
7. Spirit or faction panel (right column) via `ui_renderer.draw_spirit_panel()` / `draw_faction_panel()`.
8. Event log (bottom right) via `ui_renderer.draw_event_log()`.
9. Phase UI (left column: buttons, cards, submit button).
10. In-game menu.
11. Tooltip (via `popup_manager` for sticky, or inline for hover).

### Hover detection

`MOUSEMOTION` triggers a chain of `_update_*_hover()` helpers:
- `_update_idol_hover()` — which idol on the map is under cursor
- `_update_agenda_hover()` — card/label/agenda animation under cursor
- `_update_panel_hover()` — faction panel guided/worship/war areas
- `_update_spirit_panel_hover()` — spirit panel elements

UI rects are stored as instance variables set during `render()` (e.g. `self.panel_guided_rect`, `self.vp_positions`). Right-click opens sticky tooltips via `popup_manager`.

---

## Animation pipeline (`client/`)

### `AnimationManager` (`client/renderer/animation.py`)

Owns all live animation collections:

```python
tweens: dict[key → Tween]
flash_timers: dict[key → float]
agenda_animations: list[AgendaAnimation]           # legacy floating icons
effect_animations: list                            # TextAnimation, ArrowAnimation, IdolBeamAnimation
persistent_agenda_animations: list[AgendaSlideAnimation]
```

Key queries:
- `is_all_done() → bool` — True when no non-settled animations active (settled persistent anims don't block).
- `has_active_spoils_animations() → bool`
- `get_persistent_agenda_factions() → set` — factions with active ribbon slides (suppress ribbon text for those).

### `AnimationOrchestrator` (`client/scenes/animation_orchestrator.py`)

Translates game events into animation objects. Called by `_process_phase_result()`.

**`process_agenda_events(events, hex_ownership, small_font)`**:
1. For each event, create effect animations (`create_effect_animations()`):
   - `trade` → `TextAnimation` (gold amount, regard changes for co-traders)
   - `steal` → `TextAnimation` (gold stolen, regard losses for victims)
   - `expand` / `expand_spoils` → `ArrowAnimation` (from territory centroid to target hex)
   - `expand_failed` → `TextAnimation` (+gold amount)
2. Create `AgendaSlideAnimation` for each faction's played agenda (slides from below strip into ribbon).
3. Attach reveal metadata to each `AgendaSlideAnimation`:
   - `hex_reveal` — hex to add to `_display_hex_ownership` when animation becomes active
   - `gold_delta` — `(faction_id, amount)` pair applied to `_display_factions`
   - `war_reveals` — wars to add to `_display_wars`
   - `change_modifier` — modifier to apply to `_display_factions`

**`has_animations_playing() → bool`** — True if `AnimationManager.is_all_done()` is False.

### Animation classes (`client/renderer/animation.py`)

| Class | Purpose |
|---|---|
| `Tween` | Single linear-to-eased float value (ease_out_cubic) |
| `BaseAnimation` | Base with delay, duration, progress, alpha |
| `AgendaSlideAnimation` | Slides agenda icon into ribbon; persists until fadeout; carries reveal triggers |
| `TextAnimation` | Floating text (world or screen space) |
| `ArrowAnimation` | Hex-to-hex directional arrow |
| `IdolBeamAnimation` | Curved beam from world idol position to screen VP counter |

`AgendaSlideAnimation.is_settled` — True when slide-in complete and not fading. Settled animations remain in the ribbon but do not block `is_all_done()`.

---

## Change tracker (`client/scenes/change_tracker.py`)

`FactionChangeTracker` snapshots faction state at turn start and accumulates deltas as events arrive.

**`snapshot_and_reset(factions, spirits)`** — called on `turn_start` events:
- Deep-copies current state into `old_state` and `old_spirits`.
- Preserves previous turn data in `prev_old_state` / `prev_changes`.

**`_use_prev() → bool`** — True when `changes` is empty (no events yet this turn). Panel shows previous turn's deltas until new data arrives.

**`process_event(event, log_index, factions, spirits)`** — records `ChangeEntry` objects:
- `field` values: `"gold"`, `"territories"`, `"regard"`, `"modifier"`, `"guiding_spirit"`, `"worship_spirit"`
- `log_index` links the delta chip in the faction panel to the corresponding event log line.

Queried by `UIRenderer.draw_faction_panel()` to render clickable delta chips.

---

## UI renderer (`client/renderer/ui_renderer.py`)

### `Button`

```python
rect, text, color, text_color, hover_color
hovered: bool, enabled: bool
tooltip: str, tooltip_always: bool
```

### `UIRenderer` key render methods

| Method | Draws |
|---|---|
| `draw_hud(surface, phase, turn, spirits, my_spirit_id)` | Top bar: phase/turn text, VP counters per spirit |
| `draw_faction_overview(...)` | Six-faction strip (y=42–97): name, gold, agenda cards, pool icons, worship sigil, war indicators |
| `draw_faction_panel(...)` | Scrollable right panel: gold+delta, territories+delta, guiding spirit, worship, regard per neighbour, modifiers, agenda pool, active wars |
| `draw_spirit_panel(...)` | Scrollable right panel: spirit info, influence circles, idol counts, guided factions |
| `draw_event_log(...)` | Scrollable text log; expandable toggle button |
| `draw_multiline_tooltip(...)` | Tooltip box at anchor position |
| `render_rich_lines(...)` | Text with keyword highlighting and dotted underlines |

**Rects stored during render** (used by game_scene hover detection):
- `self.panel_guided_rect` / `panel_guided_spirit_id`
- `self.panel_worship_rect` / `panel_worship_spirit_id`
- `self.panel_war_rect` / `panel_faction_id`
- `self.faction_panel_rect`
- `self.vp_positions: dict[spirit_id → (x, y)]`
- `self.vp_hover_rects: dict[spirit_id → Rect]`
- `self.event_log_expand_rect`

**Adding a hover tooltip** (multi-file pattern):
1. `ui_renderer.py` — store the rect as an instance variable during rendering.
2. `game_scene.py __init__` — add hover state bool/string.
3. `game_scene.py MOUSEMOTION handler` — `rect.collidepoint(mx, my)` to update state.
4. `game_scene.py render` — call `draw_multiline_tooltip()` when state is active.
5. Clear rects when parent element is not drawn (avoid phantom tooltips).

---

## Key invariants

- **Authoritative server**: All game logic on server; clients render received state only.
- **Agenda pool static**: Cards sampled with replacement; no cards consumed except via ejection's `replace_agenda_card()`.
- **Simultaneous resolution**: Every agenda type resolves all participating factions before any state mutation is visible to others.
- **Display state lag**: `_display_*` fields hold the pre-event snapshot and are only cleared when all animations have settled. The real `factions`/`hex_ownership` are updated immediately on receipt of PHASE_RESULT.
- **PHASE_RESULT queue**: Processed one at a time; next payload held until `orchestrator.has_animations_playing()` is False.
- **Change tracker timing**: `snapshot_and_reset()` is called on `turn_start` events, before any agenda events. By the time `process_event()` runs per-event, `self.factions` already reflects final state — the tracker uses its own `old_state` snapshot for delta computation.
- **Worship stability**: `_check_worship()` is only called on guidance take/leave, never mid-phase.
- **War finality**: Resolved wars are removed from `self.wars`. Ripe wars stay until resolved next turn.
- **Faction respawn**: 0 territories → faction loses all gold and gains a new hex anywhere on the map. If guided, the spirit picks the hex via `respawn_choice` sub-phase (after war spoils); otherwise a random neutral hex is chosen. The faction always persists and continues playing normally.

---

## Era-specific scope

Everything described in this document belongs to Era 1 only. If a mechanism is changed or removed in Era 2, the Era 2 Technical document will describe the delta and reference the specific constants, methods, and message types affected. Constants such as `VP_TO_WIN` may need to become per-era values; the `Phase` enum and `SubPhase` strings may require additions for new sub-phases introduced in later Eras.
