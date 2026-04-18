# Era 2 - Dusk

Era 2 begins as soon as any Spirit reaches the current VP target during scoring. The game does not end there. Instead, the match continues with a new target equal to:

`current highest VP + (lobby VP target * 2)`

If the lobby target was 100, and the leader reaches 107, the new target becomes 307.

If the lobby is configured to skip player-played Era 1, the game first runs an all-AI Era 1 simulation to the same VP threshold, then hands control to players at Era 2. In that mode, VP totals reset to 0 at the start of player-controlled Era 2 and the new target becomes double the lobby target.

When the game changes eras, every Spirit currently guiding a Faction is ejected from that Faction and gets the normal agenda replacement choice before play continues.

## Changes from Era 1

### Idols and VP

No new Idols can be placed once Era 2 begins.

Idols now split their VP benefits:
- 50% goes to the Spirit currently worshipped by the Faction
- 50% goes to the Spirit who originally placed the Idol

If the same Spirit both owns the Idol and is worshipped, it still receives the full value.

Affluence Idols are reduced by 50% in Era 2.

### Wars: declaration, staging, and delayed resolution

Wars no longer resolve on the same turn they are created.

1. A **War is declared** at the end of a Steal resolution when two neighboring Factions reach -2 Regard or lower.
2. That same turn, the war is **staged** by selecting a Battleground on the border between the two Factions.
3. The war resolves at the next turn's War Phase.

All staged wars resolve simultaneously. Power is still snapshotted before any war resolves.

Each Spirit guiding one of the combatants adds one extra six-sided die to either side of that war. The die does not have to support the Faction they are guiding.

If a Spirit has **Battle Blessing**, it adds 3 dice instead of 1.

### Battlegrounds

The Battleground is a specific border line between one hex controlled by each Faction.

- If exactly one side is guided, that Spirit chooses the Battleground from the full set of border pairs.
- If both sides are guided, or neither side is guided, the Battleground is chosen randomly.

Spoils Expand uses the Battleground:
- the winner takes the loser's Battleground hex
- if that exact hex is no longer owned by the loser when Spoils resolves, the Expand fails
- if two Factions both target the same hex this way, both attempts fail
- a failed Spoils Expand grants the normal failed-Expand gold bonus after modifiers

### Guidance cycle

Unguided Factions still behave exactly as they did in Era 1.

Guided Factions now follow a fixed four-turn cycle:

1. `Restrain`
2. `Shape`
3. `Adapt`
4. `Eject`

#### Restrain

Instead of playing an Agenda immediately, the Spirit chooses which one of the Faction's four Agenda types will be skipped for this guidance stint.

The other three Agendas are shuffled into a hidden queue and will be played in that order over the next three turns.

#### Shape

The Spirit draws 3 Shaping cards from the Shaping deck and chooses 1 for the guided Faction.

- chosen cards are removed from the deck permanently
- unchosen dealt cards return to the deck
- card shortage is allocated randomly across all Spirits currently shaping
- if a Spirit gets fewer than 2 cards, it gains 5 VP instead and does not shape

#### Adapt

The Spirit draws 3 Adaptation cards from the Adaptation deck and chooses 1 for itself.

The same dealing and shortage rules from Shape apply here as well.

#### Eject

On the turn the third queued Agenda is played, the Spirit is ejected using the same agenda-replacement rule as Era 1.

If the Spirit has **Changer of Ways**, it performs one additional random replacement.

## Worship

Worship can only be stolen by the Spirit currently guiding that Faction.

The game checks for a Worship change:
- when Guidance begins
- after every change to that Faction's owned territory
- immediately before Guidance ends

If the guiding Spirit has at least as many of their own Idols in the Faction's territory as the current Worship holder, Worship shifts to the guiding Spirit. On a tie, the guiding Spirit wins.

## Shaping and Adaptation decks

See:
- [Shaping.md](/C:/Users/staeg/impetus/Shaping.md)
- [Adaptation.md](/C:/Users/staeg/impetus/Adaptation.md)

## Era 3

Era 3 is still planned, but it does not exist in the game yet.

## Technical reference

Implementation notes live in [Era 2 Technical.md](/C:/Users/staeg/impetus/Era%202%20Technical.md).
