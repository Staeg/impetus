# Impetus Architecture

This document reflects the current code layout and runtime behavior of Impetus.

## Overview

Impetus uses an authoritative client-server architecture:

- `server/` owns game rules, turn sequencing, resolution, and validation.
- `client/` owns rendering, local interaction, animations, menus, and transport adapters.
- `shared/` defines protocol strings, enums, serializable models, and hex math used by both sides.

The client is not the source of truth for gameplay state. It displays server snapshots, stages local selections, and replays `phase_result` events into animation and UI systems.

## Top-level layout

```text
impetus/
|-- main.py
|-- AGENTS.md
|-- ARCHITECTURE.md
|-- graphics/
|-- client/
|-- server/
|-- shared/
`-- tests/
```

### Key directories

- `graphics/`
  Agenda and UI art loaded by the client. Manifest-backed agenda assets are resolved from here.
- `client/`
  PyGame application, scenes, rendering helpers, local/replay transport, settings, tutorial flow.
- `server/`
  WebSocket server, game-state machine, resolution systems, AI helpers, prompt helpers for pending choices.
- `shared/`
  Constants, protocol strings, dataclasses, and hex-coordinate utilities.
- `tests/`
  Server-heavy tests plus protocol/model coverage.

## Entry points

`main.py` supports four runtime modes:

- `python main.py`
- `python main.py client <host> <port>`
- `python main.py server <host> <port>`
- `python main.py replay <path-to-jsonl>`

Replay mode feeds previously recorded inbound network traffic into the real client for debugging animation and UI behavior.

## Client architecture

### App shell

`client/app.py` owns:

- PyGame initialization
- the scene registry
- the main update/render loop
- inbound network dispatch
- optional replay recording through `IMPETUS_REPLAY_LOG`

Scene transitions are simple and explicit:

- `MenuScene`
- `LobbyScene`
- `GameScene`
- `ResultsScene`
- `SettingsScene`

### Transport layer

The client can run against three transport paths:

- `client/network.py`
  Real WebSocket transport on a background thread
- `client/local_transport.py`
  In-process server for local/single-player verification using the real server code
- `client/replay.py`
  Read-only transport that replays recorded inbound messages

### Gameplay scene structure

`client/scenes/game_scene.py` is the main gameplay shell. It still coordinates most gameplay presentation, but the architecture is split into smaller responsibilities:

- `client/scenes/game_scene.py`
  Core scene state, high-level event routing, network handling, rendering orchestration
- `client/scenes/game_phase_controller.py`
  Phase/sub-phase UI setup and submission logic
- `client/scenes/animation_orchestrator.py`
  Translates server events into agenda/effect animations
- `client/scenes/change_tracker.py`
  Tracks per-turn faction deltas for the faction panel
- `client/scenes/event_logger.py`
  Event log formatting helpers

### Input boundaries

Input is split into layers:

- `client/input_handler.py`
  Camera panning and screen/world/hex coordinate conversion
- `client/input_actions.py`
  Semantic gameplay action mapping from raw PyGame events
- `client/scenes/game_scene.py`
  Consumes those actions in the current phase/sub-phase context

This keeps camera math separate from gameplay intent and makes tutorial/spectator/input-gating logic easier to extend.

### Rendering boundaries

Rendering responsibilities are divided as follows:

- `client/renderer/hex_renderer.py`
  Hex-map drawing, map hit testing, ownership highlights
- `client/renderer/ui_renderer.py`
  HUD, faction panels, cards, labels, and many render-time rect registrations
- `client/renderer/animation.py`
  Low-level animation primitives and timing
- `client/renderer/popup_manager.py`
  Pinned and hover tooltip layout/interaction
- `client/renderer/assets.py`
  Agenda image loading and scaled/composite caches
- `client/renderer/asset_manifest.py`
  Stable asset keys and path resolution

### Asset policy

The client no longer assumes arbitrary filenames scattered through render code. Agenda art is keyed through a manifest in `client/renderer/asset_manifest.py`, then loaded in `client/renderer/assets.py`.

Current shipped art is resolved from `graphics/`.

## Server architecture

### Core rule ownership

The server owns:

- phase transitions
- validation of all player submissions
- simultaneous agenda resolution
- war creation and resolution
- scoring
- secret information boundaries

Important files:

- `server/game_state.py`
  Authoritative game state, turn flow, pending-choice state, snapshots
- `server/agenda.py`
  Agenda resolution and simultaneous effects
- `server/war.py`
  War data and war resolution helpers
- `server/scoring.py`
  VP computation
- `server/hex_map.py`
  Game-specific board state and adjacency queries
- `server/faction.py`
  Faction model and per-turn faction state
- `server/spirit.py`
  Spirit/player model

### Network orchestration

`server/server.py` owns room management and the transport-facing game loop:

- player join/reconnect
- ready/start flow
- per-room submission wakeups
- broadcasting snapshots and events
- AI auto-submission

Pending choice prompting is partially de-duplicated through `server/pending_choices.py`, which provides:

- `PendingChoicePrompt`
- `send_choice_prompts(...)`
- `broadcast_waiting_for(...)`

This helper layer centralizes the common `phase_start` + `waiting_for` pattern used by expand, change, ejection, spoils, and respawn flows.

## Phase model

### Main phases

The game loop runs through:

`LOBBY -> VAGRANT_PHASE -> AGENDA_PHASE -> WAR_PHASE -> SCORING -> CLEANUP`

`Phase.SETUP` exists as an enum value but setup does not run as a standalone phase. The automated opening turn is performed during startup before players begin turn 2 in `VAGRANT_PHASE`.

### Interactive sub-phases

Interactive sub-phases are protocol strings, not `Phase` enum values:

- `change_choice`
- `ejection_choice`
- `expand_choice`
- `winner_choice`
- `spoils_choice`
- `spoils_change_choice`
- `spoils_expand_choice`
- `respawn_choice`

The client treats these the same way as main phases for UI setup and submission.

## State and display lifecycle

When the client receives a `PHASE_RESULT`:

1. It snapshots display state for animation.
2. It applies the final server snapshot to gameplay state.
3. It logs the event stream sequentially.
4. It drives the change tracker and animation orchestrator from those events.

This means:

- live client state is usually already at the post-resolution snapshot
- animation/display code must use its own preserved pre-change data when needed

The key display-state helpers live in `GameScene` and `FactionChangeTracker`.

## Protocol

Protocol strings live in `shared/protocol.py`.

Important groups:

- `C2S`
  Client-to-server message names
- `S2C`
  Server-to-client message names
- `SubPhase`
  Interactive sub-phase identifiers

The wire format is JSON with `type` and `payload`.

## Testing and debug strategy

- Server logic should be covered with `pytest` tests in `tests/`
- Client rendering is still manually verified
- `client/local_transport.py` is the preferred path for manual UI/gameplay verification because it exercises the real server
- replay capture/playback exists to debug client behavior without a live session

## Practical modification guidance

- For new gameplay UI, prefer adding logic to `game_phase_controller.py` rather than expanding `GameScene` directly.
- For new interaction verbs, update `client/input_actions.py` before adding more raw PyGame branching.
- For new pending server choices, prefer `server/pending_choices.py` helpers instead of hand-rolled message loops.
- For new client art, add a stable manifest key first, then load from the manifest-backed loader.
