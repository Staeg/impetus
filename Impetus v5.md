# Impetus v5

## Overview

You play as a Spirit with the ability to take control of Factions to shape their future and expand the reach of your faith.

You gain Victory Points whenever Factions which have your Idols and Worship win fights, expand their territory, and make lots of gold. The long-term design is a three-Era game: Dawn, Dusk, and Midnight. Each Era has its own VP threshold, and players progress forward through the Eras instead of starting over.

Current implementation note: Era 1 (Dawn) and Era 2 (Dusk) exist in-game today. Era 3 (Midnight) is still planned for the future and does not exist yet in the playable build.

## Eras

| Era | Name     | VP Threshold | Document |
|-----|----------|--------------|----------|
| 1   | Dawn     | 100 VP       | [Era 1.md](Era%201.md) |
| 2   | Dusk     | TBD          | [Era 2.md](Era%202.md) |
| 3   | Midnight | TBD          | [Era 3.md](Era%203.md) (planned, not implemented yet) |

Each Era introduces new mechanisms and removes some from the previous one. The first player to reach the current Era threshold triggers a transition into the next Era. Era 3 remains future work, so the current game ends after Era 2 if that Era is enabled.

## Core concepts

These concepts persist across all planned Eras:

- **Factions** - Six factions on a hex grid, each with an Agenda pool, gold, territory, and inter-faction Regard
- **Spirits** - Players who guide Factions, place Idols, and earn VP through Worship
- **Guidance** - A Spirit can guide one non-Worshipping Faction at a time; guiding sets Influence to 3, which decreases each turn in Era 1 and drives the guidance cycle in Era 2
- **Idols** - Three types (Battle, Affluence, Sprawl) placed on neutral hexes; scoring depends on Worship and Era rules
- **Worship** - A Spirit that Worships a Faction scores VP from all Idols in that Faction's territory
- **Wars** - Erupt from low Regard after Steal; Era 1 resolves them immediately, while Era 2 stages them for the following turn

## Documents

| Document | Audience | Contents |
|---|---|---|
| [Era 1.md](Era%201.md) | Players | Full player-facing rules for Era 1 (Dawn) |
| [Era 1 Technical.md](Era%201%20Technical.md) | Developers | Era 1 implementation reference: data structures, phase logic, protocol, and client pipeline |
| [Era 2.md](Era%202.md) | Players | Era 2 (Dusk) rules and current gameplay notes |
| [Era 2 Technical.md](Era%202%20Technical.md) | Developers | Era 2 implementation delta and current behavior |
| [Era 3.md](Era%203.md) | Players | Era 3 (Midnight) design placeholder - not implemented yet |
| [Era 3 Technical.md](Era%203%20Technical.md) | Developers | Era 3 implementation placeholder - not implemented yet |
