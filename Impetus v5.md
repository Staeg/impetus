# Impetus v5

## Overview

You play as a Spirit with the ability to take control of Factions to shape their future and expand the reach of your faith.

You gain Victory Points whenever Factions which have your Idols and Worship win fights, expand their territory and make lots of gold. The game is played across three Eras — Dawn, Dusk, and Midnight — each lasting until any player reaches the Era's VP threshold. A player's VP carries over between Eras.

## Eras

| Era | Name     | VP Threshold | Document          |
|-----|----------|--------------|-------------------|
| 1   | Dawn     | 100 VP       | [Era 1.md](Era%201.md)     |
| 2   | Dusk     | TBD          | [Era 2.md](Era%202.md)     |
| 3   | Midnight | TBD          | [Era 3.md](Era%203.md)     |

Each Era introduces new mechanisms and removes some from the previous one. The first player to reach the Era threshold triggers a transition — the game continues into the next Era without resetting VP totals. The player who first reaches the final Era's threshold wins.

## Core concepts (all Eras)

These concepts persist across all Eras:

- **Factions** — Six factions on a hex grid, each with an Agenda pool, gold, territory, and inter-faction Regard
- **Spirits** — Players who guide Factions, place Idols, and earn VP through Worship
- **Guidance** — A Spirit can guide one non-Worshipping Faction at a time; guiding sets Influence to 3, which decreases each turn
- **Idols** — Three types (Battle, Affluence, Spread) placed on neutral hexes; scoring depends on the Worshipped Spirit
- **Worship** — A Spirit that Worships a Faction scores VP from all Idols in that Faction's territory
- **Wars** — Erupt from low Regard after Steal; resolved the following turn using territory-based Power

## Documents

| Document | Audience | Contents |
|---|---|---|
| [Era 1.md](Era%201.md) | Players | Full player-facing rules for Era 1 (Dawn) |
| [Era 1 Technical.md](Era%201%20Technical.md) | Developers | Implementation reference: data structures, phase logic, protocol, client pipeline |
| [Era 2.md](Era%202.md) | Players | Era 2 (Dusk) rules — placeholder |
| [Era 2 Technical.md](Era%202%20Technical.md) | Developers | Era 2 implementation delta — placeholder |
| [Era 3.md](Era%203.md) | Players | Era 3 (Midnight) rules — placeholder |
| [Era 3 Technical.md](Era%203%20Technical.md) | Developers | Era 3 implementation delta — placeholder |
