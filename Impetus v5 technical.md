## Impetus v5 technical

* Setup (triggered only once at the start of the game)
  * A hexagonal map of side length 5 is generated
  * The map itself is made of hexes
  * The middle hex of the map is empty
  * All the hexes surrounding the middle hex are each controlled by a different Faction
    * Color coded red: Mountain Faction
    * Color coded orange: Mesa Faction
    * Color coded yellow: Sand Faction
    * Color coded green: Plains Faction
    * Color coded blue: River Faction
    * Color coded purple: Jungle Faction
  * All the other hexes start empty
  * Empty hexes are considered Neutral
  * Each Faction draws and resolves a random Change modifier
  * A single setup turn is played where each Faction draws and resolves a random Agenda card (players have no input during this turn)  
* Vagrant Phase
  * Spirits choose their actions: if both Guidance and Idol placement are available, they must do both; otherwise they do whichever is available
    * A Spirit cannot Guide a Faction that Worships them
    * A Spirit can only place one Idol per vagrant stint (resets when they Guide or become Vagrant again)
  * After all Spirits have confirmed their actions, reveal them
  * All Idols are placed
  * All Factions with only 1 Spirit trying to Guide them become Guided by that Spirit and that Spirit's Influence is set to 3
    * Worship changes are checked
  * All Factions with \>1 Spirit trying to Guide them remain not Guided, and the Spirits remain Vagrant
* Agenda Phase
  * All Spirits currently Guiding a Faction draw 1 \+ \[their Influence\] Agenda cards from their Faction's pool (sampled with replacement; duplicates possible) and choose 1 of them
  * All choices are revealed and all non-Guided Factions draw a random Agenda card from their pool
  * All Spirits currently Guiding a Faction lose 1 Influence
  * Agendas are resolved in order (but each step is simultaneous):
    * Trade: \+1 gold, \+1 gold for every other Faction playing Trade this turn. \+1 Regard with each other Faction playing Trade this turn.
    * Steal: \-1 Regard with and \-1 gold to all neighbors. \+1 gold to this Faction for each gold lost by neighbors. Then a War erupts with any neighboring Factions who have \-2 Regard or less with this Faction.
    * Expand: spend gold equal to the number of this Faction's territories to claim a random new one; if none are available or it lacks gold, \+1 gold instead.
      * If there are any neutral Territories with Idols in them within reach: the Faction chooses at random between those territories.
    * Change: draw a card from the Change modifier deck, then shuffle it back in.  
      * If guided, the Spirit draws additional cards equal to their current Influence and chooses 1 among them.
  * Any Spirits with 0 Influence currently Guiding a Faction are ejected; they replace one Agenda card in that Faction's Agenda pool with another of their choice (pool size stays the same)
    * Worship changes are checked
* War phase
  * Each Faction's Power is snapshotted from its territory count at the start of the War Phase; all wars use this snapshot
  * Any Ripe wars are resolved simultaneously \- each combatant rolls a 6-sided die and adds their snapshotted Power
  * Gold changes from all wars (winner gains, loser/tie losses) are applied simultaneously after all wars are resolved
  * Whoever is victorious draws a Spoils of War Agenda card from their Faction's pool. If the winning Faction is guided by a Spirit, the Spirit draws 1 \+ their Influence Spoils cards and chooses 1 among them.
  * All Spoils of War are collected into a batch and resolved simultaneously in standard agenda order (Trade → Steal → Expand → Change)
    * If two Spoils Expands target the same hex, the hex is contested and neither Faction gets it
  * Any non-Ripe Wars become Ripe and a random Battleground is selected  
* Scoring
  * For each Faction that has any Spirit's Worship:
    * That Spirit gains 0.5 Victory Points for all Wars won this turn per Battle Idol in that Faction’s territory  
    * That Spirit gains 0.2 Victory Points for each gold gained this turn per Affluence Idol in that Faction’s territory  
    * That Spirit gains 0.5 Victory Points for each new Territory gained this turn per Spread Idol in that Faction’s territory  
  * All Victory Point counts are then rounded down to the next integer.  
  * If any Spirit has 10 Victory Points, the game ends.  
    * If there is a tie for most Victory Points at this moment, the victory is shared.  
* Cleanup
  * The Agenda pool is static \- cards are sampled with replacement and never consumed, so no reshuffling is needed.

A Faction with 0 territories is eliminated. Its guiding Spirit is ejected, its Worship is cleared, and any active Wars involving it are cancelled. Eliminated Factions skip all phases.

Each step is resolved simultaneously. For example, if two neighboring Factions play Steal, they do not take any gold from each other even if one Faction has 0 gold and the other has 1, but they get \-2 Regard with each other.
Similarly, if two Wars are resolved at the same time, their Spoils of War are batched and resolved simultaneously in the standard agenda order. If two Factions both win a War against the same Faction and draw Expand to conquer the same hex, the hex is contested and neither Faction gets it.