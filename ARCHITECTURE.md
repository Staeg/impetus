# Impetus - Architecture

This document describes the technical architecture for Impetus, a multiplayer turn-based strategy game built with PyGame. It serves as the implementation guide and orientation reference for development.

## High-Level Overview

Impetus uses a **client-server model** with an **authoritative server**. All game logic runs on the server; clients render state and send player inputs. This prevents cheating and keeps game state consistent across players.

```
┌──────────┐  WebSocket  ┌──────────┐  WebSocket  ┌──────────┐
│  Client   │◄──────────►│  Server  │◄──────────►│  Client   │
│ (PyGame)  │            │ (Python) │            │ (PyGame)  │
└──────────┘             └──────────┘             └──────────┘
      ▲                        ▲                        ▲
  Rendering              Game Logic                Rendering
  Input                  State Machine             Input
  Audio                  Validation                Audio
```

## Project Structure

```
impetus/
├── main.py                     # Entry point - launches client or server via CLI args
├── requirements.txt
├── ARCHITECTURE.md
├── Impetus v5.md               # Game design document
├── Impetus v5 technical.md     # Technical game rules
│
├── server/                     # Authoritative game server
│   ├── __init__.py
│   ├── server.py               # WebSocket server, lobby/room management
│   ├── game_state.py           # Core game state machine and turn resolution
│   ├── hex_map.py              # Hex grid generation, adjacency, pathfinding
│   ├── faction.py              # Faction model (gold, territories, agenda pool, modifiers)
│   ├── spirit.py               # Spirit model (influence, worship, idols, VP)
│   ├── war.py                  # War eruption tracking, ripening, resolution
│   ├── agenda.py               # Agenda card system and resolution logic
│   └── scoring.py              # Victory point calculation per phase
│
├── client/                     # PyGame client
│   ├── __init__.py
│   ├── app.py                  # Main loop, scene manager, event dispatch
│   ├── network.py              # WebSocket client, message queue, reconnection
│   ├── scenes/                 # Game screens (one active at a time)
│   │   ├── __init__.py
│   │   ├── menu.py             # Main menu, host/join options
│   │   ├── lobby.py            # Pre-game lobby, player list, ready state
│   │   ├── game_scene.py       # Primary gameplay scene (hex map, UI, phases)
│   │   └── results.py          # End-of-game scoreboard
│   ├── renderer/               # All drawing code, stateless where possible
│   │   ├── __init__.py
│   │   ├── hex_renderer.py     # Hex grid drawing, territory coloring, borders
│   │   ├── ui_renderer.py      # HUD, cards, faction info panels, phase indicators
│   │   └── animation.py        # Tweens, transitions, war/expand visual effects
│   └── input_handler.py        # Mouse/keyboard mapping, hex picking, UI interaction
│
├── shared/                     # Code shared between client and server
│   ├── __init__.py
│   ├── constants.py            # Game constants (map size, faction colors, VP thresholds)
│   ├── models.py               # Serializable data classes for game entities
│   ├── protocol.py             # Message type definitions and serialization
│   └── hex_utils.py            # Hex math (axial coords, distance, neighbors, rings)
│
├── assets/                     # Game assets
│   ├── fonts/
│   ├── images/
│   └── sounds/
│
└── tests/                      # Test suite mirroring src structure
    ├── test_hex_map.py
    ├── test_game_state.py
    ├── test_agenda.py
    ├── test_war.py
    ├── test_scoring.py
    └── test_protocol.py
```

## Core Systems

### 1. Hex Grid (`shared/hex_utils.py`, `server/hex_map.py`)

Uses **axial coordinates** (q, r) for hex math. This is the standard approach for hex grids - it makes neighbor calculation, distance, and ring generation trivial with simple arithmetic.

```
Axial coordinate system (flat-top hexagons):

        (0,-2)  (1,-2)
     (-1,-1) (0,-1) (1,-1)
  (-2,0) (-1,0) (0,0) (1,0) (2,0)
     (-1,1) (0,1)  (1,1)
        (0,2)  (-1,2)
```

- `shared/hex_utils.py` - Pure math: coordinate conversions (axial ↔ pixel ↔ cube), neighbor directions, distance, line drawing, ring/spiral iteration. Used by both client (for click-to-hex picking) and server.
- `server/hex_map.py` - Game-specific map state: generates the side-5 hex grid, tracks ownership (faction or neutral), idol placement per hex, and provides queries like "neutral hexes reachable by faction X" or "border hexes between factions X and Y."

The six factions start on the six hexes surrounding center (0,0). Center is empty/neutral. All other hexes start neutral. Starting positions are randomized each game. During setup, each faction receives habitat-based starting Change modifiers (see table below), then a single autopilot turn is played where all factions draw and resolve a random agenda card without player input.

**Habitat starting Change modifiers:**

| Habitat  | Starting Modifiers        |
|----------|---------------------------|
| Mountain | Trade ×1, Steal ×1        |
| Mesa     | Trade ×2                  |
| Sand     | Steal ×1, Expand ×1       |
| Plains   | Expand ×2                 |
| River    | Trade ×1, Expand ×1       |
| Jungle   | Steal ×2                  |

### 2. Game State Machine (`server/game_state.py`)

The game progresses through a fixed sequence of phases each turn. The state machine drives the entire flow.

```
LOBBY → SETUP → VAGRANT_PHASE → AGENDA_PHASE → WAR_PHASE → SCORING → CLEANUP ─┐
                     ▲                                                          │
                     └──────────────────────────────────────────────────────────┘
                                    (loop until 10 VP)
```

Each phase:
1. **Waits** for required player inputs (if any).
2. **Validates** submitted actions.
3. **Resolves** the phase logic.
4. **Broadcasts** results to all clients.
5. **Transitions** to the next phase.

Phase details:

| Phase | Player Input Required | Resolution |
|---|---|---|
| VAGRANT_PHASE | Vagrant spirits choose: guide a faction AND/OR place an idol (must do both if both available). Cannot guide a faction that Worships them. One idol per vagrant stint. | Simultaneous reveal. Contested guidance fails. Idols placed. Influence set to 3 on success. Worship checked. |
| AGENDA_PHASE | Guiding spirits choose 1 agenda from drawn hand | Simultaneous reveal. Non-guided factions draw randomly. Resolve in order: Trade → Steal → Expand → Change. Eject 0-influence spirits (they choose agenda to add). Worship checked. |
| WAR_PHASE | None (dice rolls are server-side), unless guided spirits need to choose spoils cards | Resolve ripe wars first: roll + power. Losers lose gold, winners gain gold + spoils agenda (guided spirits draw 1+influence spoils cards and choose). Then ripen new wars (select battlegrounds). Spoils resolved in agenda order. Check for faction eliminations. |
| SCORING | None | Calculate VP per spirit based on idols in factions where they have Worship. Round down. Check for 10 VP winner. |
| CLEANUP | None | Clear `played_agenda_this_turn` on each faction (no cards to return since the deck is a pool sampled with replacement). Advance turn counter. |

The `GameState` object holds all mutable game data: the hex map, all factions, all spirits, current phase, pending wars, and the turn counter. It exposes methods like `submit_action(spirit_id, action)` and `resolve_current_phase()`.

### 3. Faction Model (`server/faction.py`)

Each faction tracks:
- `name` and `color` (Mountain/red, Mesa/orange, Sand/yellow, Plains/green, River/blue, Jungle/purple)
- `gold: int` (starts at 0, minimum 0 - gold cannot go negative)
- `territories: set[HexCoord]` (starts with 1 hex)
- `agenda_pool: list[AgendaCard]` (starts with 1 of each: Steal, Trade, Expand, Change; cards are sampled with replacement via `random.choices`, never consumed, so drawn hands can contain duplicates; ejection replaces one card type with another, keeping pool size constant)
- `change_modifiers: dict[ChangeModifierTarget, int]` (accumulated Change upgrades per agenda type)
- `regard: dict[FactionId, int]` (bilateral regard with other factions, starts at 0)
- `guiding_spirit: Optional[SpiritId]`
- `worship_spirit: Optional[SpiritId]` (the spirit whose Worship this faction holds)
- `eliminated: bool` (True when faction has 0 territories; eliminated factions skip all phases)

Neighbors are determined dynamically: two factions are neighbors if any of their territories are adjacent on the hex grid.

When a spirit is ejected (0 influence), they choose one card type to remove and one to add via `replace_agenda_card()`, keeping the pool size constant.

A faction with 0 territories is eliminated: its guiding spirit is ejected, its Worship is cleared, and any active wars involving it are cancelled.

### 4. Spirit Model (`server/spirit.py`)

Each spirit (player) tracks:
- `spirit_id: str`
- `influence: int` (0-3, only meaningful while guiding)
- `is_vagrant: bool`
- `guided_faction: Optional[FactionId]`
- `has_placed_idol_as_vagrant: bool` (limits one idol per vagrant stint, resets on guide/become vagrant)
- `idols: list[Idol]` (each idol has a type and hex location)
- `victory_points: int`

### 5. Agenda System (`server/agenda.py`)

Agenda resolution is the heart of the game. Each agenda type is resolved as a discrete step, but all factions playing the same agenda resolve **simultaneously** within that step.

Resolution order: Trade → Steal → Expand → Change.

Simultaneous resolution matters most for Steal: if A and B are neighbors and both Steal, neither takes gold from the other (both had their gold reduced "at the same time"), but regard drops by -2 between them.

Trade also grants bilateral regard between co-traders: each trading faction gains `1 + trade_modifier` regard with every other trading faction.

The Change modifier system is cumulative. A faction's Change modifiers permanently boost subsequent plays of that agenda type.

Spoils of War agendas are collected and resolved in batch. After all wars are resolved, all spoils draws happen first: guided spirits draw 1 + influence spoils cards each, while non-guided factions auto-draw. Guided spirits submit all their war spoils choices at once (a list of card indices, one per war won). Non-guided auto-choices wait for all guided spirits to submit. Once all choices are in, all spoils resolve simultaneously via `finalize_all_spoils()` in the standard agenda order (Trade → Steal → Expand → Change). If two factions target the same hex via spoils Expand, neither gets it (contested — both receive the `expand_failed` gold bonus instead). If a chosen spoils card is Change, a follow-up modifier sub-choice is triggered (same batched pattern).

### 6. War System (`server/war.py`)

Wars have a two-turn lifecycle:
1. **Eruption**: Triggered during Steal resolution when regard hits -2 or lower. War is created in "pending" state.
2. **Resolution**: At the start of the War Phase, all ripe wars from the *previous* turn are resolved **simultaneously**. Territory counts are snapshotted before any war resolves, and all wars use the same pre-resolution power values (number of territories). Each side rolls 1d6 + power. Higher total wins. `War.resolve()` takes pre-computed power values and returns a result dict without side effects. Gold changes from all wars are calculated as net gains/losses first, then applied simultaneously after all wars are resolved. Winners draw spoils (see Spoils section below).
3. **Ripening**: After resolution, pending wars become ripe. A random border hex pair between the two factions is chosen as the battleground.

Multiple wars can exist simultaneously. A faction can be involved in multiple wars in the same turn.

### 7. Scoring System (`server/scoring.py`)

After each turn, for each faction with a spirit's Worship:
- Count idols in that faction's territory (all idols, regardless of which spirit placed them)
- Per Battle Idol: +0.5 VP for each war won this turn
- Per Affluence Idol: +0.2 VP for each gold gained this turn
- Per Spread Idol: +0.5 VP for each new territory gained this turn
- Sum and **floor** the total, then add to the spirit's VP

Tracking "gold gained this turn" and "territories gained this turn" requires the game state to record deltas during resolution, not just final values.

## Networking

### Protocol (`shared/protocol.py`)

All messages are JSON objects over WebSocket with a `type` field and a `payload` field:

```json
{"type": "submit_action", "payload": {"action": "guide", "target": "plains"}}
{"type": "phase_result", "payload": {"phase": "agenda", "events": [...]}}
```

Message types fall into two categories:

**Client → Server:**
| Type | When | Payload |
|---|---|---|
| `join_game` | Lobby | `{player_name}` |
| `ready` | Lobby | `{}` |
| `submit_vagrant_action` | Vagrant phase | `{guide_target, idol_type, idol_q, idol_r}` (guide faction AND/OR place idol) |
| `submit_agenda_choice` | Agenda phase | `{agenda_index}` (index into drawn hand) |
| `submit_change_choice` | Agenda/Change sub-phase | `{card_index}` (index into drawn change cards) |
| `submit_ejection_agenda` | Agenda/ejection sub-phase | `{remove_type, add_type}` (card type to remove and add to faction pool) |
| `submit_spoils_choice` | War/spoils sub-phase | `{card_indices}` (list of indices, one per war won, into each drawn spoils hand) |
| `submit_spoils_change_choice` | War/spoils Change sub-phase | `{card_index}` (index into drawn change cards) |

**Server → Client:**
| Type | When | Payload |
|---|---|---|
| `lobby_state` | Lobby updates | `{players, ready_states}` |
| `game_start` | Game begins | `{full_initial_state}` |
| `phase_start` | Each phase begins | `{phase, your_options}` (e.g., drawn agenda hand) |
| `waiting_for` | Player submits | `{players_remaining}` |
| `phase_result` | Phase resolves | `{events[], updated_state}` |
| `game_over` | 10 VP reached | `{winner, final_scores}` |
| `error` | Invalid action | `{message}` |

### Information Hiding

The server must not leak secret information. During choice phases:
- Each player only sees their own drawn cards.
- `waiting_for` only reveals *which* players haven't submitted, not *what* others chose.
- After simultaneous reveal, all choices are broadcast in `phase_result`.

### Server Implementation (`server/server.py`)

Uses the `websockets` library. Manages:
- **Rooms**: Each game is a room with a unique code. Players join by code.
- **Player sessions**: Maps WebSocket connections to spirit IDs. Handles disconnection/reconnection by holding a player's slot open for a timeout period.
- **Game lifecycle**: Creates a `GameState` when all players ready up, drives the phase loop, and tears down when the game ends.

A single server process can host multiple concurrent game rooms.

### Client Networking (`client/network.py`)

Runs the WebSocket connection on a **background thread** with a message queue. The PyGame main loop polls the queue each frame for incoming messages. Outgoing messages are sent directly from the main thread (WebSocket send is thread-safe in `websockets`).

This avoids blocking the render loop on network I/O.

```
Main Thread (PyGame loop):          Network Thread:
┌─────────────────────┐            ┌─────────────────────┐
│ poll message queue   │◄───────── │ recv from server     │
│ handle input         │            │ put in queue         │
│ update scene         │            │                     │
│ render               │            │                     │
│ send actions ────────│──────────►│ (send is direct)     │
└─────────────────────┘            └─────────────────────┘
```

## Client Architecture

### Scene System (`client/app.py`, `client/scenes/`)

The client uses a simple **scene stack**. One scene is active at a time. Each scene implements:
- `handle_event(event)` - Process PyGame events and network messages.
- `update(dt)` - Tick logic and animations.
- `render(screen)` - Draw to the screen.

Scenes: `MenuScene` → `LobbyScene` → `GameScene` → `ResultsScene`.

### Game Scene (`client/scenes/game_scene.py`)

The main gameplay scene. Manages sub-states corresponding to server phases:
- Displays the hex map, faction info panels, and phase-specific UI.
- In input phases (Vagrant, Agenda choice), presents clickable options and sends the choice to the server.
- In resolution phases (War, Scoring), plays back events from the server as animations.

### Hex Rendering (`client/renderer/hex_renderer.py`)

- Draws flat-top hexagons using polygon vertices computed from axial coords.
- Each hex is colored by owning faction (or grey for neutral).
- Idols are drawn as small icons within their hex.
- War battlegrounds are highlighted.
- Supports camera pan and zoom for the hex map viewport.

### UI Rendering (`client/renderer/ui_renderer.py`)

- HUD: current phase, turn number, player VP totals.
- Faction info panel: selected faction's gold, territories, regard, modifiers.
- Card hand: drawn agenda cards during choice phases, clickable to select.
- Event log: scrollable text log of resolved events.

## Shared Data Models (`shared/models.py`)

Serializable dataclasses used by both client and server. These are the canonical representations of game entities that cross the network boundary.

```python
@dataclass
class HexCoord:
    q: int
    r: int

@dataclass
class Idol:
    type: IdolType          # BATTLE, AFFLUENCE, SPREAD
    position: HexCoord
    owner_spirit: str

@dataclass
class FactionState:
    faction_id: str
    color: tuple[int, int, int]
    gold: int
    territories: list[HexCoord]
    agenda_pool: list[AgendaCard]
    change_modifiers: dict[str, int]
    regard: dict[str, int]
    guiding_spirit: str | None
    worship_spirit: str | None
    eliminated: bool

@dataclass
class SpiritState:
    spirit_id: str
    name: str
    influence: int
    is_vagrant: bool
    guided_faction: str | None
    idols: list[Idol]
    victory_points: int

@dataclass
class WarState:
    war_id: str
    faction_a: str
    faction_b: str
    is_ripe: bool
    battleground: tuple[HexCoord, HexCoord] | None
```

These are serialized to/from JSON for network transit. The server holds the full `GameState`; clients receive a filtered view of these models each phase.

## Distribution (Steam / itch.io)

### Packaging

Use **PyInstaller** to bundle the client into a standalone executable (no Python installation required for players):

```bash
pyinstaller --onedir --windowed --name Impetus main.py
```

This produces a `dist/Impetus/` folder with the executable and all dependencies. Assets are bundled alongside it.

### Server Hosting

The game server runs separately from the client and is **not** bundled into the distributed build. It is deployed to a cloud host (a basic VPS or container service is sufficient for WebSocket workloads). Players connect to the server's public address.

For development and local play, the client can launch a server subprocess on `localhost` when hosting a game.

### Steam Integration

For Steam distribution, integrate **Steamworks** via a Python binding (e.g., `steamworks` PyPI package) to support:
- Steam authentication (verify player identity server-side)
- Friends list and invites (invite friends to a game room)
- Achievements
- Rich presence (show current game state in Steam profile)

This is an additive layer - the game functions without it, and the Steamworks integration is only active when launched through Steam.

### itch.io

itch.io distribution is simpler: upload the PyInstaller output as a zip. The itch.io app (Butler) can handle updates. No special SDK integration needed.

## Testing Strategy

- **Unit tests** for all server game logic (hex math, agenda resolution, war resolution, scoring). These are the most critical tests since the server is authoritative.
- **Protocol tests** to verify message serialization/deserialization round-trips.
- **Integration tests** that simulate a full game by driving the `GameState` through multiple turns with scripted inputs, asserting expected outcomes.
- **No client rendering tests** - visual correctness is verified manually. Client logic is kept minimal (display state, send input) to reduce the testing surface.

Run with: `python -m pytest tests/`

## Dependencies

| Package | Purpose |
|---|---|
| `pygame` | Client rendering, input, audio |
| `websockets` | Client and server WebSocket communication |
| `pytest` | Testing |

Minimal dependency footprint. No game engine framework beyond PyGame - the game's turn-based nature and 2D hex rendering don't benefit from heavier engines.
