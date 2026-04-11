# Era 2 Technical Reference - Dusk

This document describes the implemented Era 2 delta in the current codebase.

Era 2 begins when any Spirit reaches the active VP target during scoring. The game does not end there. Instead, the server transitions to Era 2, raises the target to `highest_vp + base_vp_target`, and keeps the same match running.

---

## Shared data changes

### `shared/constants.py`

- Added `Era` with `ERA_1` and `ERA_2`.
- Added Era 2 tuning constants:
  - `ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER = 0.5`
  - `ERA2_DEFAULT_CARD_DRAW = 3`
  - `ERA2_SHORT_DEAL_VP = 5`
- Renamed the third idol label to `Sprawl` while preserving compatibility aliases:
  - `IdolType.SPRAWL = "sprawl"`
  - `IdolType.SPREAD = "sprawl"`
  - `SPRAWL_IDOL_VP = 5`
  - `SPREAD_IDOL_VP = SPRAWL_IDOL_VP`

### `shared/era_data.py`

- Added the Era 2 guidance-step constants:
  - `restrain`
  - `shape`
  - `adapt`
  - `eject`
- Added the authoritative Shaping and Adaptation card lists.

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

Added new client submissions:
- `submit_restrain_choice`
- `submit_shaping_choice`
- `submit_adaptation_choice`
- `submit_battleground_choice`
- `submit_war_support_choice`

Added new sub-phases:
- `restrain_choice`
- `shaping_choice`
- `adaptation_choice`
- `battleground_choice`
- `war_support_choice`

---

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

Era transition:
- `_resolve_scoring()` now transitions from Era 1 into Era 2 instead of ending the game.
- The new threshold becomes `max_vp + base_vp_target`.
- An `era_transition` event is emitted for the client.
- On every Era transition, all currently guiding spirits are queued for ejection and get an agenda-replacement choice for their guided faction before normal play continues.
- If the lobby skips player-played Era 1, the server simulates Era 1 entirely under AI control, then starts player control at Era 2 with VP totals reset to 0 and the VP target reset to `base_vp_target`.

Era 2 guidance:
- Newly guided factions start at `restrain`.
- Guided factions no longer use the Era 1 influence-based agenda hand while in Era 2.
- The server precomputes and stores the remaining three agendas after Restrain.
- Shape and Adapt deal cards from persistent decks.
- If a spirit receives fewer than 2 cards during Shape or Adapt, it gets 5 VP instead.
- On the Eject turn, the last queued agenda is played and the normal ejection flow still applies.

Era 2 war lifecycle:
- New wars are created as declarations during Steal.
- On the same turn, the server stages them by assigning a battleground border.
- They resolve on the next turn's War Phase once `resolve_turn <= current_turn`.
- During Era 2 War Phase, each guiding spirit with a side in the war chooses which side receives its extra die.
- `Battle Blessing` upgrades that contribution from 1 die to 3 dice.

Implemented post-war shaping:
- `Glory in War`: winner gets an extra Spoils draw.
- `Pyrrhic Defeat`: loser also gets Spoils.
- `Turn the Other Cheek`: after the war, negative Regard with the opposing faction is restored back toward 0.

### `server/agenda.py`

`resolve_agendas()` now injects permanent Shaping effects into agenda counts:
- `Amplified Steal`
- `Amplified Trade`
- `Amplified Expand`
- `Amplified Change`

Implemented Shaping rule hooks:
- `Globalization`: Steal affects all factions, but only neighboring pairs can create wars.
- `Fair Weather Friends`: doubles positive Regard gains with stronger factions and doubles Regard losses with weaker factions.
  - Current implementation interprets "stronger" and "weaker" by territory count at resolution time.
- `Hellbound`: blocks trade-based Regard gains involving that faction.
- `Unilateral Agreement`: Trade treats other factions' Expand plays as extra co-trader-style partners for the shaped faction.
- `Special Military Operations`: normal Expand may target adjacent enemy territory instead of only neutral hexes.
- `Havoc`: Change also mutates a random idol in the faction's territory to one of the other two idol types.

### `server/scoring.py`

Era 2 scoring changes:
- Idols split value:
  - 50% to the worshipped spirit
  - 50% to the idol owner
- `Usurper` grants the worshipped spirit an extra full 50% share on top of that split.
- Affluence idol output is halved in Era 2.
- Devotion cards apply faction-based multipliers.
- Avatar cards apply idol-type multipliers.

### `server/hex_map.py`

Added `get_expand_targets(faction_id, allow_enemy=False)` so the server can expose both neutral-only and enemy-taking Expand targets through one path.

### `server/server.py`

The server now:
- sends the new Era 2 sub-phase prompts
- gathers battleground and war-support selections
- routes Shape and Adapt card selection to the correct deck/state
- exposes Special Military Operations expand targets to both AI and human players
- supports lobby era-selection flags for Era 1 and Era 2
- can bootstrap directly into Era 2 by replaying a suppressed-animation, AI-controlled simulated Era 1

---

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

The new choice surfaces reuse the existing left-column card flow and compact confirmation patterns rather than replacing the main HUD.

### `client/scenes/game_phase_controller.py`

Added setup and submit handling for all new Era 2 sub-phases.

### `client/renderer/ui_renderer.py`

The top HUD now shows:
- current era
- current VP target

This was added as a compact strip extension to preserve the established Era 1 layout.

### `client/renderer/hex_renderer.py`

When a war has a staged battleground, the renderer draws the war marker on that specific border pair instead of every shared border.

### `client/scenes/event_logger.py`

Added client-visible event text for:
- `war_declared`
- `war_staged`
- `era_transition`
- `restrained`
- `shaping_chosen`
- `adaptation_chosen`

---

## Terminology normalization

Global terminology changes applied across runtime/docs:
- the third idol type is now `Sprawl`
- wars use `declaration` language at creation time
- delayed wars use `staged` language before resolution

The rename is global, but only Era 2 changes mechanics.

---

## Known implementation notes

- Era 1 mechanics remain intact apart from the terminology rename.
- Era 2 battleground selection uses existing faction borders and stores the exact two border hexes in `WarState`.
- Shape and Adapt cards are permanently removed from their deck only when chosen. Unchosen dealt cards return to the deck.
- There is automated server-test coverage for the pre-existing ruleset, but the new Era 2 UI flow still benefits from manual local-transport verification.
