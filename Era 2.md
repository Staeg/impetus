# Era 2 - Dusk

Era 2 begins as soon as any Spirit reaches the current VP target during scoring. VP totals carry over. Instead of ending the game, the match continues with a new target equal to:

`current highest VP + the lobby VP target`

If the lobby target was 100, and the leader reaches 107, the new target becomes 207.

When the game changes eras, every spirit currently guiding a faction is ejected from that faction and gets the normal agenda replacement choice before play continues.

If the lobby is configured to skip player-played Era 1, the game first runs an all-AI Era 1 simulation to the same VP threshold, then hands control to players at Era 2. In that mode, VP totals reset to 0 at the start of player-controlled Era 2.

---

## Changes from Era 1

### Idols and VP

No new idols can be placed once Era 2 begins.

Idols now split their VP benefits:
- 50% goes to the spirit currently worshipped by the faction
- 50% goes to the spirit who originally placed the idol

If the same spirit both owns the idol and is worshipped, it still receives the full value.

Affluence idols are reduced by 50% in Era 2.

### Wars: declaration, staging, and delayed resolution

Wars no longer resolve on the same turn they are created.

1. A **War is declared** at the end of a Steal resolution when two neighbouring factions reach -2 Regard or lower.
2. That same turn, the war is **staged** by selecting a Battleground on the border between the two factions.
3. The war resolves at the next turn's War Phase.

All staged wars resolve simultaneously. Power is still snapshotted before any war resolves.

Each spirit guiding one of the combatants adds one extra six-sided die to either side of that war. The die does not have to support the faction they are guiding.

If a spirit has **Battle Blessing**, it adds 3 dice instead of 1.

### Battlegrounds

The Battleground is a specific border line between one hex controlled by each faction.

- If exactly one side is guided, that spirit chooses the battleground.
- If both sides are guided, or neither side is guided, the battleground is chosen randomly.

Spoils Expand uses the Battleground:
- the winner takes the loser's battleground hex
- if two factions both target the same hex this way, both attempts fail

### Guidance cycle

Unguided factions still behave exactly as they did in Era 1.

Guided factions now follow a fixed four-turn cycle:

1. `Restrain`
2. `Shape`
3. `Adapt`
4. `Eject`

#### Restrain

Instead of playing an agenda immediately, the spirit chooses which one of the faction's four agenda types will be skipped for this guidance stint.

The other three agendas are shuffled into a hidden queue and will be played in that order over the next three turns.

#### Shape

The spirit draws 3 Shaping cards from the Shaping deck and chooses 1 for the guided faction.

- chosen cards are removed from the deck permanently
- unchosen dealt cards return to the deck
- card shortage is allocated randomly across all spirits currently shaping
- if a spirit gets fewer than 2 cards, it gains 5 VP instead and does not shape

#### Adapt

The spirit draws 3 Adaptation cards from the Adaptation deck and chooses 1 for itself.

The same dealing and shortage rules from Shape apply here as well.

#### Eject

On the turn the third queued agenda is played, the spirit is ejected using the same agenda-replacement rule as Era 1.

If the spirit has **Changer of Ways**, it performs one additional random replacement.

---

## Shaping and Adaptation decks

See:
- [Shaping.md](/C:/Users/staeg/impetus/Shaping.md)
- [Adaptation.md](/C:/Users/staeg/impetus/Adaptation.md)

---

## Technical reference

Implementation notes live in [Era 2 Technical.md](/C:/Users/staeg/impetus/Era%202%20Technical.md).
