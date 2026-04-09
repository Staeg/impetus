# AGENTS.md

This file provides guidance to Codex and other agents working in this repository.

## Workflow rules

- Never commit or push unless the user explicitly asks you to.
- When asked to commit and push as the "next version", inspect existing tags with `git tag -l` and increment instead of overwriting.
- The worktree may already contain user edits. Read before changing and do not revert unrelated work.

## Project overview

Impetus is a multiplayer turn-based strategy game with:

- An authoritative Python server in `server/`
- A PyGame client in `client/`
- Shared protocol, models, and hex math in `shared/`

All game rules and turn resolution live on the server. The client renders state, plays animations, gathers local UI intent, and sends validated player choices.

## Useful commands

```bash
python main.py
python main.py client <host> <port>
python main.py server
python main.py server <host> <port>
python main.py replay <path-to-jsonl>
python -m pytest tests/
pyinstaller impetus.spec --noconfirm
```

## Source of truth

- Runtime behavior beats docs when they disagree.
- `shared/protocol.py` is the source of truth for message names.
- `server/game_state.py` is the source of truth for phase state, pending choices, and turn flow.
- `server/server.py` is the source of truth for how those pending choices are surfaced to clients.

## High-value architecture notes

- `client/scenes/game_scene.py` is still the main gameplay shell, but phase-specific submit/setup logic is now routed through `client/scenes/game_phase_controller.py`. If you are changing a choice flow, inspect both files.
- `client/input_handler.py` only owns camera movement and coordinate conversion. Semantic gameplay input mapping now starts in `client/input_actions.py`, then flows through `GameScene`.
- The client animation and delta-display pipeline is split across:
  - `client/scenes/game_scene.py`
  - `client/scenes/animation_orchestrator.py`
  - `client/scenes/change_tracker.py`
  A visible gameplay UI fix is often incomplete if only one of those files changes.
- Local single-player does not use a fake rules path. `client/local_transport.py` runs the real server in-process and is the best manual-verification path for client work.
- Pending player-choice prompting on the server is shared through `server/pending_choices.py`. If a sub-phase is sending `phase_start` and `waiting_for`, prefer using those helpers instead of open-coding more message loops.

## Gameplay flow notes

- Main phases: `LOBBY -> VAGRANT_PHASE -> AGENDA_PHASE -> WAR_PHASE -> SCORING -> CLEANUP`
- Interactive sub-phases are string-valued identifiers in `shared/protocol.py`:
  - `change_choice`
  - `ejection_choice`
  - `expand_choice`
  - `winner_choice`
  - `spoils_choice`
  - `spoils_change_choice`
  - `spoils_expand_choice`
  - `respawn_choice`
- Setup does not enter `Phase.SETUP`; the automated opening turn runs during lobby-to-game startup.

## Assets and packaging

- Client-rendered agenda art lives under `graphics/`, not a generic `assets/` tree.
- Stable agenda asset keys are defined in `client/renderer/asset_manifest.py`.
- `client/renderer/assets.py` loads those manifest-backed graphics and builds scaled/composite variants.
- PyInstaller builds resolve graphics through `_MEIPASS`; source runs resolve from the repo.

## Debugging and verification

- For UI or animation bugs, verify the symptom itself, not just the surrounding code path.
- For gameplay UI work, prefer a local transport/manual pass that covers:
  - a normal `phase_start`
  - at least one sub-phase choice
  - at least one animated `phase_result`
- Replay capture/playback exists for client debugging:
  - set `IMPETUS_REPLAY_LOG` to record inbound server traffic to JSONL
  - run `python main.py replay <path>` to replay a recorded stream into the client
- There are no automated client rendering tests. Do not claim a UI issue is fixed based only on unit tests or a successful import/build.

## Change guidance

- Prefer extracting new seams over further expanding `GameScene`.
- If you add a new interactive sub-phase, update all three:
  - `shared/protocol.py`
  - `server/game_state.py` and/or `server/server.py`
  - client phase setup/render/submit handling
- If you add new client art, give it a stable manifest key instead of scattering filename knowledge across render code.

## Testing

- Server logic changes should run `python -m pytest tests/` when `pytest` is available in the environment.
- Client-only changes still need manual verification.
