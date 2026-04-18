## Impetus v5 technical

This file tracks the current cross-era gameplay implementation. Era 1 and Era 2 are implemented. Era 3 is still planned for the future and does not exist yet in runtime code.

### Setup

- A hexagonal map of side length 5 is generated
- The middle hex is empty
- The six surrounding hexes are starting Faction territories
- Other hexes start neutral
- Factions begin with habitat-based Change modifiers
- A single automated setup turn is played before players take control

### Vagrant Phase

- Spirits choose Guidance and Idol placement when both are available
- A Spirit cannot guide a Faction that already Worships them
- A Spirit can place only one Idol per vagrant stint
- Idol placement is on any neutral hex with no adjacency restriction
- If multiple Spirits target the same Faction, contests resolve by:
  - unique habitat-affinity match
  - otherwise unique race-affinity match
  - otherwise failure with one-turn cooldown

### Agenda Phase

- Guided Spirits draw `1 + influence` Agendas in Era 1 and pick one
- Unguided Factions draw a random Agenda
- Guided Change and Expand sub-choices are collected before resolution
- Resolution order is `Trade -> Steal -> Expand -> Change`
- Expand failures grant the modified failed-Expand gold bonus

### Worship

- Worship can only be stolen by the Spirit currently guiding that Faction
- The game checks for a Worship shift:
  - when Guidance begins
  - after every territory ownership change affecting that Faction
  - immediately before Guidance ends
- If the guiding Spirit has at least as many own Idols in that Faction's territory as the current Worship holder, Worship shifts to the guiding Spirit
- On a tie, the guiding Spirit wins

### Era 1 wars

- Wars declared by Steal resolve in the same turn
- If exactly one side is guided, that Spirit chooses the winner
- If both or neither side is guided, the war resolves by d6 plus snapshotted Power
- No gold changes are applied for winning or losing a war

### Era 2 wars

- Wars are declared during Steal, staged the same turn, and resolved on the following turn
- If exactly one side is guided, that Spirit chooses the Battleground from the full set of border pairs
- If both sides are guided, or neither side is guided, the Battleground is random
- Each guiding Spirit chooses which side receives their extra support dice
- `Battle Blessing` upgrades that support from 1 extra die to 3 extra dice

### Spoils of War

- Winners draw a Spoils Agenda from their pool
- Guided Spirits with multiple draws choose their Spoils card
- Era 1 guided Spoils Expand can require a territory choice
- Era 2 Spoils Expand uses the loser's Battleground hex
- If that exact Battleground hex is gone by the time Spoils resolves, the Expand fails and grants the modified failed-Expand gold bonus
- Spoils resolve simultaneously in standard agenda order

### Scoring

- Battle Idol: 5 VP per Idol per War won
- Affluence Idol: 2 VP per Idol per gold gained
- Sprawl Idol: 5 VP per Idol per territory gained
- Era 2 splits Idol value between Worship holder and Idol owner
- Era 2 halves Affluence Idol output

### Era progression

- Reaching the Era 1 threshold transitions into Era 2 if Era 2 is enabled
- The new Era 2 target becomes `highest_vp + (base_vp_target * 2)`
- If the match started from simulated Era 1, VP resets to 0 and the Era 2 target becomes `base_vp_target * 2`
