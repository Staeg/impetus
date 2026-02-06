# Impetus v5

## Summary

You play as a Spirit with the ability to take control of Factions to shape their future and expand the reach of your faith.

You gain Victory Points whenever Factions which have your Idols and Presence win fights, expand their territory and make lots of gold. First to 10 Victory Points wins.

## Turn structure

All Spirits start in a Vagrant state.  
All Factions start at 0 Regard with each other.

* All Vagrant Spirits can choose to Possess a Faction that is currently not Possessed or to place one of three Idol types on a neutral territory.  
  * These choices are made in secret and then resolved simultaneously.  
  * Several Idols can end up on the same territory.  
  * If several Spirits try to Possess the same Faction, all of them waste their turn.  
  * Successfully Possessing a Faction sets a Spirit’s Influence to 3\.  
* All Spirits draw 1 Agenda card \+ however much Influence they have from the Possessed Faction’s Agenda deck, choose 1 of the drawn Agendas for their Possessed Faction to play, then lose 1 Influence.  
  * This choice is made in secret, then revealed simultaneously.  
* Factions without a Spirit Possessing them just draw a random Agenda card from their decks.  
* Agendas are resolved in the following order:  
  * Trade  
  * Bond  
  * Steal  
  * Expand  
  * Change  
* Spirits with 0 Influence Possessing a Faction add one Agenda card of their choice to that Faction’s deck, then become Vagrant.

## Agenda phase

Each Faction starts with 1 of each Agenda in their deck.

* Steal: \-1 Regard with and \-1 gold to all neighbors. \+1 gold to this Faction for each gold lost by neighbors. Then a War erupts with any neighboring Factions who have \-2 Regard or less with this Faction.  
* Bond: \+1 Regard with all neighbors.   
* Trade: \+1 gold, \+1 gold for every other Faction playing Trade this turn.  
* Expand: spend gold equal to the number of this Faction’s territories to claim a random new one; if none are available or it lacks gold, \+1 gold instead.  
  * If there are any neutral Territories with Idols in them within reach: the Faction chooses at random between those territories.  
* Change: draw a card from the Change modifier deck, then shuffle it back in.  
  * If possessed, the Spirit draws additional cards equal to their current Influence and chooses 1 among them.

## War

Each Faction’s Power baseline is equal to the number of Territories it controls.

* War erupts whenever two neighboring Factions have \-2 Regard or lower after one or both of them resolve a Steal action.  
* After the Agenda Phase, all Wars that erupted this turn become Ripe and all Wars from the previous turn which are already Ripe are resolved.  
  * When a War becomes Ripe, a random border between two hexes owned by those two Factions is chosen as the Battleground.  
* To determine the winner, both Factions roll a 6-sided die and add their Power.  
* The loser loses 1 gold. The winner gains 1 gold and draws an additional Agenda card and resolves it. This Agenda card is referred to as Spoils of War.  
  * Expand functions differently when drawn as Spoils of War: instead of paying gold to expand into neutral territory, the winning Faction takes control of the hex on the loser’s side of the Battleground.  
    * In the unlikely event that two Factions both win a War against the same Faction and draw Expand to conquer the same hex, the Faction with greater Power succeeds. A further tie is resolved randomly.  
  * Other Agendas function as normal, including the possibility of Steal starting another War between the same Factions.  
  * Trade Spoils of War also give 1 gold to every other Faction that resolved Trade normally this turn.  
* In the event of a tie, both Factions lose 1 gold and no Spoils of War are drawn.

## Change modifiers

Each card modifies one of the other 4 Agendas of this Faction permanently.

* Trade: \+1 gold for each other Trade Agenda  
* Bond: \+1 Regard  
* Steal: \+1 gold stolen and \-1 regard to affected neighbors  
* Expand: \-1 cost on successful Expands, \+1 gold on failed Expands

## Idols and Victory Points

Three kinds of Idols exist: Battle Idols that reward winning Wars, Affluence Idols that reward getting gold and Spread Idols that reward gaining territory. Having Presence in a Faction matters for scoring Victory Points \- so long as a Spirit has Presence, they benefit from *all* Idols in that Faction’s territory, not just their own.

* Whenever a Spirit Possesses a Faction or stops Possessing a Faction and becomes Vagrant:  
  * If there is no other Spirit’s Presence in this Faction: they place their Presence in this Faction.  
  * If there is another Spirit’s Presence in this Faction: check which Spirit has more Idols in this Faction’s territory. In the case of a tie or if the Possessing Spirit has more, they replace the Presence with their own.  
  * If their Presence is already there: nothing happens.  
* Factions with a Presence in them can score Victory Points for the Spirit whose Presence is there, based on what kinds of Idols are in its territory (but ignoring which Spirit those Idols belong to):  
  * 0.5 VP per Battle Idol  
  * 0.2 VP per Affluence Idol for each gold gained  
  * 0.5 VP per Spread Idol for each new territory taken  
  * These Victory Points are summed together and rounded down, then added to that Spirit’s total.

