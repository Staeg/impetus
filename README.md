# Impetus

A multiplayer turn-based strategy game built with PyGame and Python. Players take on the role of spirits who indirectly control factions on a hex grid, competing to reach 100 victory points through guidance, influence, and worship.

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

For full rules, see `Impetus v5.md`. For technical details, see `ARCHITECTURE.md`.
