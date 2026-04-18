# Era 1 - Dawn

Era 1 lasts until any player reaches **100 Victory Points**. If Era 2 is enabled, reaching that threshold transitions the match into Era 2 instead of ending it.

## Before the first turn

The map is a hexagonal grid. Six Factions each start with one territory near the center; every other hex is neutral. Each Faction begins with a small pool of Agenda cards and permanent Change modifiers determined by its habitat. Nobody starts with any gold.

A single automated setup turn plays out before players take any actions - each Faction draws and plays a random Agenda card. You will see the results of this turn when the game begins.

## Each turn

A full turn has four phases that happen in order:

1. **Vagrant Phase** - Spirits without a Faction choose one to Guide, and may place an Idol.
2. **Agenda Phase** - Spirits choose what their Faction does this turn.
3. **War Phase** - Battles between hostile Factions are resolved.
4. **Scoring Phase** - Victory Points are awarded based on Idol types and Faction performance.

## Vagrant Phase

Any Spirit who is not currently guiding a Faction is **Vagrant**. Vagrant Spirits must:

- **Choose a Faction to Guide** - pick any Faction that is currently Unguided and that does not already Worship you. Your choice is secret until all choices are revealed simultaneously.
- **Place an Idol** - if you have not placed one during this vagrant stint, you must also place one of your three Idol types on any neutral hex on the map. You can place it anywhere - there is no adjacency restriction.

If you can only do one of the two, you do only what you can.

### Contesting guidance

If two or more Spirits choose the same Faction, the game resolves the contest in this order:

1. If exactly one of those Spirits has a matching habitat affinity for that Faction, that Spirit wins Guidance.
2. Otherwise, if exactly one of the remaining tied Spirits has a race affinity matching that Faction's race, that Spirit wins Guidance.
3. Otherwise, nobody guides the Faction. All contesting Spirits waste their turn and cannot choose that same Faction next Vagrant phase.

Successfully guiding a Faction sets your Influence with that Faction to **3**.

## Agenda Phase

Every Faction plays one Agenda card each turn.

- **Guided Factions**: You draw **1 + your current Influence** cards from your Faction's pool, pick one in secret, then your Influence drops by 1.
- **Unguided Factions**: They draw and play a random card with no player input.

After all Agendas are chosen, they resolve in a fixed order: **Trade -> Steal -> Expand -> Change**. All Factions playing the same type resolve simultaneously.

When your Influence reaches 0, you choose one Agenda card type to remove from your Faction's pool and one to add. The pool stays the same size, then you become Vagrant again.

## The four Agendas

### Trade

+1 gold, plus +1 gold for every other Faction also playing Trade this turn, plus +1 gold for every Faction playing Expand this turn. Gain +1 Regard with each co-trading Faction.

### Steal

-1 gold and -1 Regard to each neighboring Faction. +1 gold for each neighbor who loses gold. If any neighbor's Regard with you drops to -2 or lower, a **War is declared** between you.

Resolution is simultaneous.

### Expand

Spend gold equal to your current territory count to claim an adjacent neutral hex. If you cannot afford it or there are no neutral hexes within reach, gain the failed-Expand gold bonus instead.

- **Guided**: Your Spirit picks which hex to claim before resolution.
- **Unguided**: Picks randomly, preferring hexes that have Idols on them.

If two Factions target the same hex, both fail and both receive the failed-Expand gold bonus instead.

### Change

Draw a card from the Change modifier deck and apply it permanently to this Faction. The modifier deck is then reshuffled.

- **Guided**: You draw additional cards equal to your current Influence and choose which one to apply.

Change modifiers permanently boost one of the other three Agendas:
- **Trade modifier**: +1 gold and +1 Regard per co-trading Faction
- **Steal modifier**: +1 gold stolen and -1 Regard to affected neighbors
- **Expand modifier**: -1 cost on successful Expands, +1 gold on failed Expands

## Habitat starting modifiers

Each Faction begins the game with a head start in Change modifiers based on its home terrain:

| Habitat  | Starting Modifiers |
|----------|--------------------|
| Mountain | Trade x1, Steal x1 |
| Mesa     | Trade x2 |
| Sand     | Steal x1, Expand x1 |
| Plains   | Expand x2 |
| River    | Trade x1, Expand x1 |
| Jungle   | Steal x2 |

## War

Each Faction's **Power** equals the number of territories it controls.

Wars resolve immediately in Era 1 - a War that is declared during the Agenda Phase resolves in that same turn's War Phase.

If exactly one Faction is guided, that Spirit decides which Faction wins. If both or neither Faction is guided, both Factions roll a six-sided die and add their Power. The highest total wins. On a tie, no Spoils are drawn.

No gold is exchanged for winning or losing a War.

After the War:
- The winner draws a **Spoils of War** Agenda card from its pool.
- If Guided, the Spirit draws **1 + their Influence** Spoils cards and picks one.

All Spoils are batched and resolved simultaneously in standard Agenda order.

## Idols and Victory Points

There are three Idol types, each rewarding different Faction behavior:

| Idol | Scores when... | Amount |
|------|----------------|--------|
| Battle Idol | Faction wins a War | 5 VP per Idol per War won |
| Affluence Idol | Faction gains gold this turn | 2 VP per Idol per gold gained |
| Sprawl Idol | Faction gains territory | 5 VP per Idol per territory gained |

You score VP only from Factions whose **Worship** you hold. Once you have a Faction's Worship, every Idol in that Faction's territory counts for you - not just your own.

### Worship

Worship can only be stolen by the Spirit currently guiding that Faction.

The game checks for a Worship change:
- when Guidance begins
- after every change to that Faction's owned territory
- immediately before Guidance ends

If no one currently holds the Faction's Worship, the guiding Spirit gains it. Otherwise, compare the number of that Spirit's own Idols in the Faction's current territory to the current Worship holder's count. If the guiding Spirit has at least as many, Worship shifts to the guiding Spirit. On a tie, the guiding Spirit wins.

Restriction: You cannot guide a Faction that already Worships you.

## Faction Respawn

If a Faction ever reaches 0 territories, at the end of that turn:
- It loses all of its gold.
- It gains a new hex anywhere on the game board. If it is Guided, its Spirit chooses which neutral hex it reappears on. Otherwise, a random neutral hex is chosen.

The Faction continues to participate in all phases normally from its new position.
