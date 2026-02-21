# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow rules

- **Never commit or push** unless the user explicitly asks you to. Do not proactively create commits, tags, or push to remote after completing a task.
- **Version tags**: When asked to commit and push as the "next version", check existing tags (`git tag -l`) and increment — never overwrite an existing tag. If `v1.64` already exists, the next version is `v1.65`.

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
`LOBBY → VAGRANT → AGENDA → WAR → SCORING → CLEANUP → (loop until 100 VP)`

Each phase: wait for input → validate → resolve → broadcast → transition. Driven by `server/game_state.py`.

`Phase.SETUP` exists in the enum but the game never transitions into it. Setup (one automated turn — all-random) runs during `LOBBY` before the first `VAGRANT` phase begins. Each faction's starting Change modifiers are determined by its habitat (see `HABITAT_STARTING_MODIFIERS` in `shared/constants.py`), set before the automated turn.

### Sub-phases
Several phases trigger sub-phases where the server waits for a specific player choice before continuing. These are **bare strings**, not in the `Phase` enum:
- `change_choice` — After a Change agenda resolves, the guiding spirit picks a modifier card
- `ejection_choice` — When a spirit is ejected (0 influence), they pick one agenda card to remove from the faction's pool and one to add in its place (pool size stays the same)
- `spoils_choice` — After war victories, the winning guided spirit picks spoils agenda cards for ALL wars at once (multi-pick UI). Server sends a `choices` list with one entry per war won.
- `spoils_change_choice` — If any spoils cards are Change, the spirit picks modifier cards for all of them at once

### Core game concepts
- **6 factions** (Mountain, Mesa, Sand, Plains, River, Jungle) on a hex grid (axial coords, side-length 5)
- **Spirits** (players) indirectly control factions via guidance and influence
- **Agenda pool** — cards are sampled with replacement (`random.choices`), never consumed. Duplicates are possible. `replace_agenda_card()` (ejection) swaps one card type for another, keeping the pool size constant.
- **Agenda resolution order** is always: Trade → Steal → Expand → Change (same-type resolves simultaneously)
- **Wars** have a two-turn lifecycle: erupt → ripen → resolve. All ripe wars resolve simultaneously using snapshotted territory counts; gold changes are applied as a net batch after all wars resolve.
- **Guidance cooldown**: if two or more spirits contest the same faction in the same vagrant phase (neither gets it), all contesting spirits are blocked from targeting that faction for the next vagrant phase. Tracked in `game_state.guidance_cooldowns` (dict of spirit_id → set of blocked faction_ids); cleared at the start of each vagrant phase.
- **Worship** (`worship_spirit` on factions): spirits compete for faction Worship via idol counts; a spirit cannot guide a faction that Worships them
- **Scoring**: VP from idols in faction territories where the spirit has Worship (Battle/Affluence/Spread idol types)
- **Faction elimination**: factions with 0 territories are eliminated (guiding spirit ejected, Worship cleared, wars cancelled)

### Simultaneous resolution
"Simultaneous" means all factions playing the same agenda type resolve in one step, using the game state from before any of them applied:
- **Steal**: If A and B both Steal and are neighbors, neither takes gold from the other (both had gold reduced "at the same time"), but regard still drops
- **Expand**: If two factions expand into the same neutral hex, neither gets it (contested). If a faction expands into a hex adjacent to multiple factions, all neighbor regard changes apply. For spoils expand, if two factions target the same battleground hex, neither gets it (contested — both get expand_failed gold bonus).
- **Trade**: All gold gains and regard changes are calculated from pre-resolution state
- **Wars**: All ripe wars resolve using territory counts snapshotted before any war resolves. Gold changes are applied as net deltas after all wars complete.

### War spoils
Wars can generate spoils choices. When a faction wins a war, a spoils card is drawn from the faction's agenda pool. If the winning faction is guided by a spirit, the spirit draws `1 + influence` cards (with replacement, duplicates possible) and chooses one. If the chosen card is Change, a follow-up modifier choice is triggered. All spoils are collected in batch: non-guided auto choices wait for all guided spirits to submit, then everything resolves simultaneously via `finalize_all_spoils()` in standard agenda order. If two factions target the same hex via spoils Expand, neither gets it (contested — both receive the expand_failed gold bonus). A spirit winning multiple wars submits all spoils choices at once (list of card indices).

### Card choice flow
Several game moments follow the same pattern: the server sends a list of cards to a specific player, the client renders a card picker UI, the player clicks a card, and the client sends back the chosen index. This pattern is used for:
- **Agenda choice** (AGENDA_PHASE): spirit draws `1 + influence` cards from pool, picks one
- **Change modifier** (change_choice): spirit picks from the Change modifier deck
- **Ejection agenda** (ejection_choice): ejected spirit picks a type to remove and a type to add (two-step UI). Server sends `agenda_pool` (current pool list) in options. Client sends `remove_type` + `add_type`.
- **Spoils cards** (spoils_choice): spirit picks from drawn spoils cards for ALL wars at once. Server sends `options.choices` (list of {cards, loser}). Client renders multiple card pickers vertically. Client sends back `card_indices` (list of chosen index per war).
- **Spoils Change modifiers** (spoils_change_choice): follow-up if any spoils cards are Change. Same multi-pick pattern.

### Client scene system
Scenes implement `handle_event()`, `update(dt)`, `render(screen)`. One active at a time. `game_scene.py` is the largest file (~2274 lines) handling all gameplay phases.

### Client animation pipeline
When the client receives a `PHASE_RESULT` message, it doesn't immediately update the UI. Instead:
1. Events are split into **animation batches**: regular events, then spoils events
2. Each batch plays sequentially — the next batch starts only after the current one finishes
3. **Effect animations** (expand arrows, war icons) play alongside or after agenda animations
4. **Player input is deferred** until all animation batches finish — UI buttons and card pickers don't appear until animations complete
5. `client/scenes/animation_orchestrator.py` translates game events into animation calls; it coordinates the pipeline and is instantiated by `game_scene.py`
6. Low-level animation state (tweens, timers) lives in `client/renderer/animation.py` (`AnimationManager`, `Tween`, `AgendaAnimation`, etc.)

### Networking
- Server: asyncio + websockets, supports multiple concurrent game rooms
- Client: WebSocket on background thread with message queue, polled each frame by the PyGame main loop
- Information hiding: players only see their own drawn cards during choice phases

## Common modification patterns

### Adding a hover tooltip
This is a multi-file pattern used repeatedly:
1. **`client/renderer/ui_renderer.py`**: Store a `pygame.Rect` as an instance variable (e.g., `self.panel_foo_rect`) during rendering
2. **`client/scenes/game_scene.py` init**: Add hover state bool/string (e.g., `self.hovered_foo = False`)
3. **`game_scene.py` MOUSEMOTION handler**: Add collision check (`rect.collidepoint(mx, my)`) to update hover state
4. **`game_scene.py` render method**: Draw tooltip with `draw_multiline_tooltip()` when hover state is active
5. Clear rects when the parent UI element is not drawn (to avoid phantom tooltips from stale rects)

### PHASE_RESULT data flow
When a `PHASE_RESULT` arrives in `game_scene.handle_network()`:
1. Display state is snapshotted for animations (`_snapshot_display_state`)
2. `self.factions`/`self.spirits` are updated to the **final post-event state** via `_update_state_from_snapshot`
3. Events are then logged sequentially via `_log_event`, which feeds the change tracker
4. **Important**: By the time `change_tracker.process_event` runs, `self.factions` already has the final state — the tracker relies on its own `old_state` snapshots, not on comparing `self.factions` before/after

### Change tracker / display state lifecycle
- `snapshot_and_reset()` is called on `turn_start` events — it deep-copies current faction state as `old_state` and preserves the previous turn's data in `prev_old_state`/`prev_changes`
- `_use_prev()` returns True between turns (no current changes yet), causing the panel to show previous turn's deltas until new events arrive
- Display state (`_display_hex_ownership`) is a separate snapshot used only by the animation system to render hex ownership from before the state update

## Key file sizes
- `client/scenes/game_scene.py` — ~2274 lines, the largest file; handles all gameplay phases, hover detection, UI setup, and network message processing
- `client/renderer/ui_renderer.py` — ~1088 lines; all HUD, panels, tooltips, and card rendering
- `client/scenes/animation_orchestrator.py` — ~494 lines; translates game events into animation calls
- `server/agenda.py` — ~530 lines; all agenda resolution logic
- `server/game_state.py` — ~925 lines; the game state machine driving all phase transitions

## Testing
- Tests live in `tests/` and cover **server logic only** (agenda resolution, war, scoring, protocol serialization)
- There are **no client rendering tests** — client UI changes must be verified manually by running the game
- Always run `python -m pytest tests/` after modifying server code

## Game design docs
- `Impetus v5.md` — Game rules and mechanics
- `Impetus v5 technical.md` — Technical rule details (setup, phase resolution)
