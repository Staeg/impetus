# Era 1 Technical Reference - Dawn

This document describes the current Era 1 implementation in the codebase. Era 1 is fully playable today. Era 3 is still future work and is not represented here.

## Shared constants

### `shared/constants.py`

- `Phase` includes:
  - `LOBBY`
  - `SETUP`
  - `VAGRANT_PHASE`
  - `AGENDA_PHASE`
  - `WAR_PHASE`
  - `SCORING`
  - `CLEANUP`
  - `GAME_OVER`
- `AgendaType` includes:
  - `STEAL`
  - `TRADE`
  - `EXPAND`
  - `CHANGE`
- `IdolType` includes:
  - `BATTLE`
  - `AFFLUENCE`
  - `SPRAWL`

Key Era 1 values:
- `STARTING_GOLD = 0`
- `STARTING_INFLUENCE = 3`
- `VP_TO_WIN = 100`
- `MAP_SIDE_LENGTH = 5`

## Protocol

### Client -> Server

- `JOIN_GAME`
- `READY`
- `START_GAME`
- `SET_LOBBY_OPTIONS`
- `TOGGLE_SPECTATOR`
- `SUBMIT_VAGRANT_ACTION`
- `SUBMIT_AGENDA_CHOICE`
- `SUBMIT_EXPAND_CHOICE`
- `SUBMIT_CHANGE_CHOICE`
- `SUBMIT_EJECTION_AGENDA`
- `SUBMIT_SPOILS_CHOICE`
- `SUBMIT_SPOILS_CHANGE_CHOICE`
- `SUBMIT_SPOILS_EXPAND_CHOICE`
- `SUBMIT_WINNER_CHOICE`
- `SUBMIT_RESTRAIN_CHOICE`
- `SUBMIT_SHAPING_CHOICE`
- `SUBMIT_ADAPTATION_CHOICE`
- `SUBMIT_RESPAWN_CHOICE`
- `SUBMIT_BATTLEGROUND_CHOICE`
- `SUBMIT_WAR_SUPPORT_CHOICE`

### Server -> Client

- `LOBBY_STATE`
- `GAME_START`
- `PHASE_START`
- `WAITING_FOR`
- `PHASE_RESULT`
- `GAME_OVER`
- `ERROR`

### Sub-phases

- `change_choice`
- `expand_choice`
- `ejection_choice`
- `spoils_choice`
- `spoils_change_choice`
- `spoils_expand_choice`
- `winner_choice`
- `restrain_choice`
- `shaping_choice`
- `adaptation_choice`
- `respawn_choice`
- `battleground_choice`
- `war_support_choice`

Era 1 uses only the Era 1 subset during normal play, but the shared protocol surface includes the later-era hooks too.

## Setup flow

`Phase.SETUP` exists in the enum but is not entered during normal runtime. Setup runs inside `setup_game()` while the game is still in the lobby.

Setup does the following:
1. Builds the map
2. Creates all Factions
3. Creates all Spirits
4. Assigns Faction races and Spirit affinities
5. Applies habitat starting modifiers
6. Runs one automated opening turn
7. Starts players on Turn 2 in `VAGRANT_PHASE`

## Vagrant Phase

### Guidance contests

If multiple Spirits target the same Faction, the implementation resolves the contest in this order:
1. Unique habitat-affinity match wins
2. Otherwise, unique race-affinity match wins
3. Otherwise, the contest fails and all tied Spirits get a one-turn cooldown for that Faction

### Idol placement

- Idols can be placed on any neutral hex
- A Spirit can place only one Idol per vagrant stint
- Era 2 disables further Idol placement, but Era 1 keeps it active

## Agenda Phase

- Guided Spirits draw `1 + influence` cards and choose one
- Unguided Factions draw randomly
- Guided Change and Expand choices are collected before resolution
- Influence drops by 1 for each guided Spirit during Era 1

## War Phase

### Era 1 resolution

- Wars declared during the Agenda Phase resolve in the same turn's War Phase
- If exactly one side is guided, the guiding Spirit chooses the winner
- If both or neither side is guided, the war resolves by d6 plus snapshotted Power
- No gold changes are applied for winning or losing Era 1 wars

### Spoils

- Winners draw from their Agenda pool
- Guided Spirits with multiple draws choose their Spoils card
- Guided Era 1 Spoils Expand can require a follow-up territory pick
- Spoils resolve simultaneously in standard agenda order

## Worship

Worship is not re-evaluated continuously during scoring.

The current rule is:
- only the Spirit currently guiding a Faction can steal its Worship
- Worship is checked when Guidance begins
- Worship is checked after every territory ownership change that affects that Faction
- Worship is checked immediately before Guidance ends
- on a tie, the guiding Spirit wins

## Scoring

`server/scoring.py` calculates VP from:
- Battle Idols x wars won
- Affluence Idols x gold gained
- Sprawl Idols x territories gained

If Era 2 is enabled, hitting the Era 1 target transitions into Era 2 instead of ending the match.

## Client architecture

Important gameplay files:
- `client/scenes/game_scene.py`
- `client/scenes/game_phase_controller.py`
- `client/scenes/animation_orchestrator.py`
- `client/scenes/change_tracker.py`
- `client/renderer/ui_renderer.py`
- `client/renderer/hex_renderer.py`
- `client/renderer/animation.py`

The client still shares one codepath with later-era features, so some structs and message handlers include Era 2 concepts even during Era 1.
