# Impetus

A multiplayer turn-based strategy game built with PyGame and Python. Players take on the role of spirits who indirectly control factions on a hex grid, competing to reach 10 victory points through guidance, influence, and worship.

## Requirements

- Python 3.10+
- Dependencies: `pygame`, `websockets`, `pytest`

```bash
pip install -r requirements.txt
```

## Running the Game

### Start a server

```bash
python main.py server
```

By default the server listens on `localhost:8765`. To bind to a specific host and port:

```bash
python main.py server 0.0.0.0 9000
```

A single server process can host multiple concurrent game rooms.

### Start a client

```bash
python main.py
```

This launches the PyGame client and connects to `localhost:8765`. To connect to a remote server:

```bash
python main.py client <host> <port>
```

### Run tests

```bash
python -m pytest tests/
```

Tests cover server-side game logic only (agenda resolution, war, scoring, protocol serialization). Client changes must be verified manually.

## Building a Standalone Executable

```bash
pyinstaller impetus.spec --noconfirm
```

This produces a distributable executable that does not require a Python installation.

## Architecture

Impetus uses an **authoritative server** model. All game logic runs on the server; clients only render state and send player inputs. Communication happens over WebSocket using JSON messages.

```
Client (PyGame)  <--WebSocket-->  Server (Python asyncio)  <--WebSocket-->  Client (PyGame)
```

### Project Structure

```
impetus/
├── main.py              # Entry point (launches client or server)
├── server/              # Authoritative game logic
│   ├── server.py        # WebSocket server, lobby/room management
│   ├── game_state.py    # Game state machine and phase transitions
│   ├── hex_map.py       # Hex grid, ownership, adjacency
│   ├── faction.py       # Faction model (gold, territories, deck)
│   ├── spirit.py        # Spirit model (influence, idols, VP)
│   ├── war.py           # War lifecycle (erupt, ripen, resolve)
│   ├── agenda.py        # Agenda card resolution
│   └── scoring.py       # Victory point calculation
├── client/              # PyGame rendering client
│   ├── app.py           # Main loop and scene manager
│   ├── network.py       # WebSocket client on background thread
│   ├── scenes/          # Menu, Lobby, Game, Results screens
│   └── renderer/        # Hex grid, UI panels, animations
├── shared/              # Code shared by client and server
│   ├── constants.py     # Game constants and enums
│   ├── models.py        # Serializable data classes
│   ├── protocol.py      # Message type definitions
│   └── hex_utils.py     # Hex coordinate math
└── tests/               # pytest suite (server logic only)
```

### Game Flow

Each turn progresses through a fixed sequence of phases:

```
LOBBY → SETUP → VAGRANT → AGENDA → WAR → SCORING → CLEANUP → (repeat until 10 VP)
```

- **Vagrant**: Unguided spirits choose a faction to guide and/or place an idol.
- **Agenda**: Guiding spirits draw agenda cards and choose one. Agendas resolve in order: Trade, Steal, Expand, Change.
- **War**: Wars that erupted last turn are resolved (dice + faction power). Winners draw spoils cards.
- **Scoring**: VP awarded based on idol placement and faction worship.
- **Cleanup**: Decks reshuffled, turn counter advanced.

### Game Concepts

- **6 Factions** (Mountain, Mesa, Sand, Plains, River, Jungle) occupy territories on a hex grid.
- **Spirits** (players) guide factions indirectly through influence and agenda choices.
- **Worship** is earned by placing idols in a faction's territory; a spirit scores VP from factions that worship them.
- **Wars** erupt when regard between factions drops too low, and resolve over two turns.

For full rules, see `Impetus v5.md`. For technical details, see `ARCHITECTURE.md`.
