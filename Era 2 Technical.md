# Era 2 Technical Reference - Dusk

This document describes the implemented Era 2 delta in the current codebase.

Era 2 begins when any Spirit reaches the active VP target during scoring. The game does not end there. Instead, the server transitions from Era 1 into Era 2, raises the target, and keeps the same match running.

## Shared data changes

### `shared/constants.py`

- Added `Era` with `ERA_1` and `ERA_2`
- Added Era 2 tuning constants:
  - `ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER = 0.5`
  - `ERA2_DEFAULT_CARD_DRAW = 3`
  - `ERA2_SHORT_DEAL_VP = 5`
- Renamed the third idol label to `Sprawl` while preserving compatibility aliases:
  - `IdolType.SPRAWL = "sprawl"`
  - `IdolType.SPREAD = "sprawl"`

### `shared/models.py`

`FactionState` now carries:
- `guidance_step`
- `restrained_agenda`
- `queued_agendas`
- `shaping_effects`

`SpiritState` now carries:
- `adaptation_effects`

`WarState` now carries:
- `battleground_a`
- `battleground_b`
- `declared_turn`
- `resolve_turn`
- `is_staged`

`GameStateSnapshot` now carries:
- `era`
- `vp_target`

### `shared/protocol.py`

Added client submissions:
- `submit_restrain_choice`
- `submit_shaping_choice`
- `submit_adaptation_choice`
- `submit_respawn_choice`
- `submit_battleground_choice`
- `submit_war_support_choice`

Added new sub-phases:
- `restrain_choice`
- `shaping_choice`
- `adaptation_choice`
- `respawn_choice`
- `battleground_choice`
- `war_support_choice`

## Server flow changes

### `server/game_state.py`

Persistent Era 2 state:
- `current_era`
- `base_vp_target`
- `shaping_deck`
- `adaptation_deck`

New pending-choice stores:
- `restrain_pending`
- `shaping_pending`
- `adaptation_pending`
- `battleground_pending`
- `war_support_pending`

### Era transition

- `_resolve_scoring()` now transitions from Era 1 into Era 2 instead of ending the game.
- The new threshold becomes `max_vp + (base_vp_target * 2)`.
- An `era_transition` event is emitted for the client.
- On every Era transition, all currently guiding Spirits are queued for ejection and get an agenda-replacement choice for their guided Faction before normal play continues.
- If the lobby skips player-played Era 1, the server simulates Era 1 entirely under AI control, then starts player control at Era 2 with VP totals reset to 0 and the VP target reset to `base_vp_target * 2`.

### Era 2 guidance

- Newly guided Factions start at `restrain`.
- Guided Factions no longer use the Era 1 influence-based agenda hand while in Era 2.
- The server precomputes and stores the remaining three Agendas after Restrain.
- Shape and Adapt deal cards from persistent decks.
- If a Spirit receives fewer than 2 cards during Shape or Adapt, it gets 5 VP instead.
- On the Eject turn, the last queued Agenda is played and the normal ejection flow still applies.

### Era 2 war lifecycle

- New wars are created as declarations during Steal.
- On the same turn, the server stages them by assigning a Battleground border.
- They resolve on the next turn's War Phase once `resolve_turn <= current_turn`.
- If exactly one side is guided, that Spirit chooses the Battleground from the full set of border pairs.
- If both sides are guided, or neither side is guided, the Battleground is selected randomly.
- During Era 2 War Phase, each guiding Spirit with a side in the war chooses which side receives its extra dice.
- `Battle Blessing` upgrades that contribution from 1 die to 3 dice.
- Extra support is resolved as actual additional d6 rolls, not as flat Power.

### Spoils Expand

- Era 2 Spoils Expand is bound to the loser's Battleground hex from the resolved war.
- If that exact hex is no longer owned by the loser when Spoils resolves, the Expand fails and grants the normal failed-Expand gold bonus.
- Guided winners do not get a separate territory-pick sub-phase for Era 2 Spoils Expand.

### Worship

- Worship can only be stolen by the Spirit currently guiding that Faction.
- The server re-checks whether Worship should change:
  - when Guidance begins
  - after every territory ownership change affecting that Faction
  - immediately before Guidance ends
- On a tie, the currently guiding Spirit wins Worship.

### Implemented post-war shaping

- `Glory in War`: winner gets an extra Spoils draw
- `Pyrrhic Defeat`: loser also gets Spoils
- `Turn the Other Cheek`: after the war, negative Regard with the opposing Faction is restored back toward 0

## Agenda hooks

### `server/agenda.py`

`resolve_agendas()` now injects permanent Shaping effects into agenda counts:
- `Amplified Steal`
- `Amplified Trade`
- `Amplified Expand`
- `Amplified Change`

Implemented Shaping rule hooks:
- `Globalization`
- `Fair Weather Friends`
- `Hellbound`
- `Unilateral Agreement`
- `Special Military Operations`
- `Havoc`

## Scoring changes

### `server/scoring.py`

Era 2 scoring changes:
- Idol value splits:
  - 50% to the worshipped Spirit
  - 50% to the Idol owner
- `Usurper` grants the worshipped Spirit an extra full 50% share on top of that split
- Affluence Idol output is halved in Era 2
- Devotion cards apply faction-based multipliers
- Avatar cards apply idol-type multipliers

## Client and UI changes

### `client/scenes/game_scene.py`

Added snapshot-driven scene state for:
- current era
- current VP target
- battleground-choice entries
- war-support entries

Added rendering and submission support for:
- Restrain
- Shape
- Adapt
- battleground selection
- war-support selection

### `client/scenes/game_phase_controller.py`

Added setup and submit handling for all new Era 2 sub-phases.

### `client/renderer/ui_renderer.py`

The top HUD now shows:
- current era
- current VP target

### `client/renderer/hex_renderer.py`

When a war has a staged Battleground, the renderer draws the war marker on that specific border pair instead of every shared border.

### `client/scenes/event_logger.py`

Added client-visible event text for:
- `war_declared`
- `war_staged`
- `era_transition`
- `restrained`
- `shaping_chosen`
- `adaptation_chosen`

## Era 3

Era 3 is still future work. The current codebase does not define `ERA_3`, and no Era 3 gameplay flow exists yet.
