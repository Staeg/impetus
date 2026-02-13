# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Impetus is a multiplayer turn-based strategy game built with PyGame (client) and Python asyncio/websockets (server). It uses an **authoritative server** architecture — all game logic runs on the server; clients only render state and send inputs.

## Commands

```bash
# Run client (default localhost:8765)
python main.py
python main.py client <host> <port>

# Run server
python main.py server
python main.py server <host> <port>

# Run tests
python -m pytest tests/

# Build Windows executable
pyinstaller impetus.spec --noconfirm
```

## Architecture

**Client-Server over WebSocket** with JSON messages (`{type, payload}`). See `ARCHITECTURE.md` for the full protocol spec and system details.

### Key directories
- `server/` — Authoritative game logic: state machine, hex map, factions, spirits, agendas, wars, scoring
- `client/` — PyGame rendering: scene system (Menu → Lobby → Game → Results), hex/UI renderers, animations
- `shared/` — Code used by both: constants/enums, serializable dataclasses, protocol definitions, hex math
- `tests/` — pytest suite covering server logic and protocol serialization (no client rendering tests)

### Game state machine
`LOBBY → SETUP → VAGRANT → AGENDA → WAR → SCORING → CLEANUP → (loop until 10 VP)`

Each phase: wait for input → validate → resolve → broadcast → transition. Driven by `server/game_state.py`.

### Core game concepts
- **6 factions** (Mountain, Mesa, Sand, Plains, River, Jungle) on a hex grid (axial coords, side-length 5)
- **Spirits** (players) indirectly control factions via guidance and influence
- **Agenda resolution order** is always: Steal → Bond → Trade → Expand → Change (same-type resolves simultaneously)
- **Wars** have a two-turn lifecycle: erupt → ripen → resolve (resolve ripe first, then ripen new)
- **Worship** (called "presence" in code variables): spirits compete for faction Worship via idol counts; a spirit cannot guide a faction that Worships them
- **Scoring**: VP from idols in faction territories where the spirit has Worship (Battle/Affluence/Spread idol types)
- **Faction elimination**: factions with 0 territories are eliminated (guiding spirit ejected, Worship cleared, wars cancelled)

### Client scene system
Scenes implement `handle_event()`, `update(dt)`, `render(screen)`. One active at a time. `game_scene.py` is the largest file (~1060 lines) handling all gameplay phases.

### Networking
- Server: asyncio + websockets, supports multiple concurrent game rooms
- Client: WebSocket on background thread with message queue, polled each frame by the PyGame main loop
- Information hiding: players only see their own drawn cards during choice phases

## Game design docs
- `Impetus v5.md` — Game rules and mechanics
- `Impetus v5 technical.md` — Technical rule details (setup, phase resolution)
