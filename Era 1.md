# Era 1 — Dawn

Era 1 lasts until any player reaches **100 Victory Points**. VP is not reset when Era 2 begins.

---

## Before the first turn

The map is a hexagonal grid. Six Factions each start with one territory near the centre; every other hex is neutral. Each Faction begins with a small pool of Agenda cards (one of each type) and permanent Change modifiers determined by their habitat. Nobody starts with any gold.

A single automated setup turn plays out before players take any actions — each Faction draws and plays a random Agenda card. You will see the results of this turn when the game begins.

---

## Each turn

A full turn has four phases that happen in order:

1. **Vagrant Phase** — Spirits without a Faction choose one to Guide, and may place an Idol.
2. **Agenda Phase** — Spirits choose what their Faction does this turn.
3. **War Phase** — Battles between hostile Factions are resolved.
4. **Scoring Phase** — Victory Points are awarded based on Idol types and Faction performance.

---

## Vagrant Phase

Any Spirit who is not currently Guiding a Faction is **Vagrant**. Vagrant Spirits must:

- **Choose a Faction to Guide** — pick any Faction that is currently Unguided and that does not already Worship you. Your choice is secret until all choices are revealed simultaneously.
- **Place an Idol** — if you have not placed one during this vagrant stint, you must also place one of your three Idol types on any neutral hex on the map. You can place it anywhere — there is no adjacency restriction.

If you can only do one of the two (e.g. all Factions are already Guided, or you have already placed an Idol), you do only what you can.

**Contesting guidance**: If two or more Spirits choose the same Faction, nobody Guides it — all contesting Spirits waste their turn. On top of that, each contesting Spirit is blocked from choosing that same Faction next Vagrant phase (guidance cooldown).

**Succeeding**: Successfully Guiding a Faction sets your Influence with that Faction to **3**.

**Worship**: When you take or leave Guidance of a Faction, Worship is checked — see the Idols and Victory Points section.

---

## Agenda Phase

Every Faction plays one Agenda card each turn.

- **Guided Factions**: You draw **1 + your current Influence** cards from your Faction's pool, pick one in secret, then your Influence drops by 1. Cards are drawn with replacement — duplicates are possible.
- **Unguided Factions**: They draw and play a random card with no player input.

After all Agendas are chosen, they resolve in a fixed order: **Trade → Steal → Expand → Change**. All Factions playing the same type resolve simultaneously.

**When your Influence reaches 0**, you choose one Agenda card type to remove from your Faction's pool and one to add (the pool stays the same size), then you become Vagrant again.

---

## The four Agendas

### Trade
+1 gold, plus +1 gold for every other Faction also playing Trade this turn. Gain +1 Regard with each of those co-trading Factions.

### Steal
−1 gold and −1 Regard to each neighbouring Faction. +1 gold for each neighbour who loses gold. If any neighbour's Regard with you drops to −2 or lower, a **War erupts** between you.

Resolution is simultaneous — if two neighbours both Steal from each other, neither gains gold from the other (both lost simultaneously), but both take the Regard penalty.

### Expand
Spend gold equal to your current territory count to claim an adjacent neutral hex. If you cannot afford it or there are no neutral hexes within reach, +1 gold instead.

- **Guided**: Your Spirit picks which hex to claim. Guided Expands resolve before Unguided ones. If two Guided Spirits pick the same hex, both fail and both receive the gold bonus instead.
- **Unguided**: Picks randomly, preferring hexes that have Idols on them.

### Change
Draw a card from the Change modifier deck and apply it permanently to this Faction. The modifier deck is then reshuffled.

- **Guided**: You draw additional cards equal to your current Influence and choose which one to apply.

Change modifiers permanently boost one of the other three Agendas:
- **Trade modifier**: +1 gold and +1 Regard per co-trading Faction
- **Steal modifier**: +1 gold stolen and −1 Regard to affected neighbours
- **Expand modifier**: −1 cost on successful Expands, +1 gold on failed Expands

### Habitat starting modifiers

Each Faction begins the game with a head start in Change modifiers based on their home terrain:

| Habitat  | Starting Modifiers        |
|----------|---------------------------|
| Mountain | Trade ×1, Steal ×1        |
| Mesa     | Trade ×2                  |
| Sand     | Steal ×1, Expand ×1       |
| Plains   | Expand ×2                 |
| River    | Trade ×1, Expand ×1       |
| Jungle   | Steal ×2                  |

---

## War

Each Faction's **Power** equals the number of territories it controls.

Wars resolve **immediately** — a War that erupts during the Agenda Phase is resolved in that same turn's War Phase.

**War erupts** at the end of a Steal resolution when two neighbouring Factions reach −2 Regard or lower.

**Resolving the War**:
All Wars resolve simultaneously. Each Faction's Power is snapshotted at the start of the War Phase — territory changes from one War do not affect another's Power.

- **If exactly one Faction is Guided**: the Guiding Spirit decides which Faction wins.
- **If both or neither Faction is Guided**: both Factions roll a six-sided die and add their Power. The highest total wins. On a tie, no Spoils are drawn.

No gold is exchanged for winning or losing a War.

**After the War**:
- The **winner** draws a **Spoils of War** Agenda card from their pool.
  - If Guided, the Spirit draws **1 + their Influence** Spoils cards and picks one.

**Spoils resolution**: All Spoils are batched and resolved simultaneously in standard Agenda order (Trade → Steal → Expand → Change).

- **Spoils Expand** works differently: the winning Faction claims any territory belonging to the losing Faction. If Guided, the Spirit picks which territory. If unguided, a territory is chosen at random, prioritising hexes with the most Idols. If two Factions both target the same hex this way, neither gets it.
- **Spoils Steal** can trigger new Wars.
- **Spoils Trade** also gives the bonus gold and Regard to every Faction that played Trade normally this turn.

---

## Idols and Victory Points

There are three Idol types, each rewarding different Faction behaviour:

| Idol         | Scores when…                | Amount              |
|--------------|-----------------------------|---------------------|
| Battle Idol  | Faction wins a War           | 5 VP per Idol per War won |
| Affluence Idol | Faction gains gold this turn | 2 VP per Idol per gold gained |
| Spread Idol  | Faction gains territory      | 5 VP per Idol per territory gained |

You score VP only from Factions whose **Worship** you hold. Once you have a Faction's Worship, every Idol in that Faction's territory counts for you — not just your own.

**How Worship is determined**: Worship is checked whenever you take or leave Guidance of a Faction.
- If no one else holds that Faction's Worship: you gain it.
- If someone else holds it: whoever has more of their own Idols inside that Faction's territory wins the Worship. On a tie, the Guiding Spirit wins.
- If you already hold the Worship: nothing changes.

**Restriction**: You cannot Guide a Faction that already Worships you.

---

## Faction Respawn

If a Faction ever reaches 0 territories, at the end of that turn:
- It loses all of its Gold.
- It gains a new hex anywhere on the game board. If it is Guided, its Spirit chooses which neutral hex it reappears on. Otherwise, a random neutral hex is chosen.

The Faction continues to participate in all phases normally from its new position.
