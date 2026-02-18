# Impetus v5

## Summary

You play as a Spirit with the ability to take control of Factions to shape their future and expand the reach of your faith.

You gain Victory Points whenever Factions which have your Idols and Worship win fights, expand their territory and make lots of gold. First to 10 Victory Points wins.

## Turn structure

All Spirits start in a Vagrant state.  
All Factions start at 0 Regard with each other.

* All Vagrant Spirits choose to Guide a Faction that is currently not Guided and, if they have not already placed an Idol during this vagrant stint, to place one of three Idol types on a neutral territory. If both options are available, they must do both. If only one option is available, they do that one.
  * A Spirit cannot Guide a Faction that Worships them.
  * These choices are made in secret and then resolved simultaneously.
  * Several Idols can end up on the same territory.
  * If several Spirits try to Guide the same Faction, all of them waste their turn.
  * Successfully Guiding a Faction sets a Spirit's Influence to 3\.
* All Spirits draw 1 Agenda card \+ however much Influence they have from the Guided Faction's Agenda pool, choose 1 of the drawn Agendas for their Guided Faction to play, then lose 1 Influence. Cards are sampled with replacement from the pool and are never removed, so duplicates are possible in a single draw.
  * This choice is made in secret, then revealed simultaneously.
* Factions without a Spirit Guiding them just draw a random Agenda card from their pool.
* Agendas are resolved in the following order:
  * Trade
  * Steal
  * Expand
  * Change
* Spirits with 0 Influence Guiding a Faction replace one Agenda card in that Faction's pool with another of their choice, then become Vagrant.

## Agenda phase

Each Faction starts with 1 of each Agenda in their pool. The pool is static — cards are sampled with replacement and never consumed.

* Steal: \-1 Regard with and \-1 gold to all neighbors. \+1 gold to this Faction for each gold lost by neighbors. Then a War erupts with any neighboring Factions who have \-2 Regard or less with this Faction.
* Trade: \+1 gold, \+1 gold for every other Faction playing Trade this turn. \+1 Regard with each other Faction playing Trade this turn.
* Expand: spend gold equal to the number of this Faction’s territories to claim a random new one; if none are available or it lacks gold, \+1 gold instead.  
  * If there are any neutral Territories with Idols in them within reach: the Faction chooses at random between those territories.  
* Change: draw a card from the Change modifier deck, then shuffle it back in.  
  * If guided, the Spirit draws additional cards equal to their current Influence and chooses 1 among them to modify.

## War

Each Faction's Power baseline is equal to the number of Territories it controls.

* War erupts whenever two neighboring Factions have \-2 Regard or lower after one or both of them resolve a Steal action.
* After the Agenda Phase, all Ripe Wars from the previous turn are resolved first. Then all Wars that erupted this turn become Ripe.
  * When a War becomes Ripe, a random border between two hexes owned by those two Factions is chosen as the Battleground.
* All Ripe Wars are resolved simultaneously. Each Faction's Power is snapshotted from its territory count at the start of the War Phase, so territory changes from one war do not affect another war's Power calculations.
* To determine the winner, both Factions roll a 6-sided die and add their Power.
* Gold changes from all wars (losses and gains) are applied simultaneously after all wars are resolved.
* The loser loses 1 gold. The winner gains 1 gold and draws a Spoils of War Agenda card from their Faction's pool and resolves it. If the winning Faction is guided by a Spirit, the Spirit draws 1 \+ their Influence Spoils cards and chooses 1 among them.
  * All Spoils of War are collected into a batch and then resolved simultaneously, following the standard agenda resolution order (Trade → Steal → Expand → Change).
  * Expand functions differently when drawn as Spoils of War: instead of paying gold to expand into neutral territory, the winning Faction takes control of the hex on the loser's side of the Battleground.
    * If two Factions both win a War against the same Faction and draw Expand to conquer the same hex, the hex is contested and neither Faction gets it.
  * Other Agendas function as normal, including the possibility of Steal starting another War between the same Factions.
  * Trade Spoils of War also give 1 gold and Regard (plus their Trade Change modifier) to every other Faction that resolved Trade normally this turn.
* In the event of a tie, both Factions lose 1 gold and no Spoils of War are drawn.

## Change modifiers

Each card modifies one of the other 3 Agendas of this Faction permanently.

* Trade: \+1 gold and \+1 Regard per co-trader
* Steal: \+1 gold stolen and \-1 regard to affected neighbors
* Expand: \-1 cost on successful Expands, \+1 gold on failed Expands

## Idols and Victory Points

Three kinds of Idols exist: Battle Idols that reward winning Wars, Affluence Idols that reward getting gold and Spread Idols that reward gaining territory. Having a Faction's Worship matters for scoring Victory Points \- so long as a Spirit has a Faction's Worship, they benefit from *all* Idols in that Faction's territory, not just their own.

* Whenever a Spirit Guides a Faction or stops Guiding a Faction and becomes Vagrant:
  * If no other Spirit has this Faction's Worship: they gain this Faction's Worship.
  * If another Spirit has this Faction's Worship: check which Spirit has more Idols in this Faction's territory. In the case of a tie or if the Guiding Spirit has more, they replace the Worship with their own.
  * If they already have this Faction's Worship: nothing happens.
* A Spirit cannot Guide a Faction that Worships them.
* Factions with a Worshipped Spirit can score Victory Points for that Spirit, based on what kinds of Idols are in its territory (but ignoring which Spirit those Idols belong to):
  * 0.5 VP per Battle Idol for each War won this turn
  * 0.2 VP per Affluence Idol for each gold gained this turn
  * 0.5 VP per Spread Idol for each new territory taken this turn
  * These Victory Points are summed together and rounded down, then added to that Spirit's total.

## Faction Elimination

A Faction with 0 territories is eliminated. When eliminated:
* Its guiding Spirit is ejected and becomes Vagrant.
* Its Worship is cleared.
* Any active Wars involving the eliminated Faction are cancelled.

