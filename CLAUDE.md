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

### Sub-phases
Several phases trigger sub-phases where the server waits for a specific player choice before continuing. These are **bare strings**, not in the `Phase` enum:
- `change_choice` — After a Change agenda resolves, the guiding spirit picks a modifier card
- `ejection_choice` — When a spirit is ejected (0 influence), they pick an agenda card to add to the faction's deck
- `spoils_choice` — After a war victory, the winning guided spirit picks a spoils agenda card
- `spoils_change_choice` — If the spoils card is Change, the spirit picks a modifier card

### Core game concepts
- **6 factions** (Mountain, Mesa, Sand, Plains, River, Jungle) on a hex grid (axial coords, side-length 5)
- **Spirits** (players) indirectly control factions via guidance and influence
- **Agenda resolution order** is always: Trade → Bond → Steal → Expand → Change (same-type resolves simultaneously)
- **Wars** have a two-turn lifecycle: erupt → ripen → resolve (resolve ripe first, then ripen new)
- **Worship** (`worship_spirit` on factions): spirits compete for faction Worship via idol counts; a spirit cannot guide a faction that Worships them
- **Scoring**: VP from idols in faction territories where the spirit has Worship (Battle/Affluence/Spread idol types)
- **Faction elimination**: factions with 0 territories are eliminated (guiding spirit ejected, Worship cleared, wars cancelled)

### Simultaneous resolution
"Simultaneous" means all factions playing the same agenda type resolve in one step, using the game state from before any of them applied:
- **Steal**: If A and B both Steal and are neighbors, neither takes gold from the other (both had gold reduced "at the same time"), but regard still drops
- **Expand**: If two factions expand into the same neutral hex, neither gets it (contested). If a faction expands into a hex adjacent to multiple factions, all neighbor regard changes apply
- **Trade/Bond**: All gold gains and regard changes are calculated from pre-resolution state

### War spoils
Wars can generate spoils choices. When a guided faction wins a war, the guiding spirit draws `1 + influence` spoils cards and chooses one to add permanently to the faction's deck. If the chosen card is Change, a follow-up modifier choice is triggered. Spoils agendas resolve in the standard agenda order (Trade → Bond → Steal → Expand → Change) in a separate sub-pass after war resolution.

### Card choice flow
Several game moments follow the same pattern: the server sends a list of cards to a specific player, the client renders a card picker UI, the player clicks a card, and the client sends back the chosen index. This pattern is used for:
- **Agenda choice** (AGENDA_PHASE): spirit draws `1 + influence` cards, picks one
- **Change modifier** (change_choice): spirit picks from the Change modifier deck
- **Ejection agenda** (ejection_choice): ejected spirit picks an agenda type to add
- **Spoils card** (spoils_choice): spirit picks from drawn spoils cards
- **Spoils Change modifier** (spoils_change_choice): follow-up if spoils card was Change

### Client scene system
Scenes implement `handle_event()`, `update(dt)`, `render(screen)`. One active at a time. `game_scene.py` is the largest file (~1385 lines) handling all gameplay phases.

### Client animation pipeline
When the client receives a `PHASE_RESULT` message, it doesn't immediately update the UI. Instead:
1. Events are split into **animation batches**: regular events, then spoils events
2. Each batch plays sequentially — the next batch starts only after the current one finishes
3. **Effect animations** (expand arrows, war icons) play alongside or after agenda animations
4. **Player input is deferred** until all animation batches finish — UI buttons and card pickers don't appear until animations complete
5. Animation state lives in `client/renderer/animation.py` (`AnimationManager`, `Tween`, `AgendaAnimation`, etc.)

### Networking
- Server: asyncio + websockets, supports multiple concurrent game rooms
- Client: WebSocket on background thread with message queue, polled each frame by the PyGame main loop
- Information hiding: players only see their own drawn cards during choice phases

## Game design docs
- `Impetus v5.md` — Game rules and mechanics
- `Impetus v5 technical.md` — Technical rule details (setup, phase resolution)
