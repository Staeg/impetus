"""Faction model: gold, territories, agenda pool, modifiers, regard."""

import random
from typing import Optional
from shared.constants import (
    AgendaType, FACTION_COLORS, FACTION_START_HEXES,
    STARTING_GOLD, AGENDA_RESOLUTION_ORDER, ChangeModifierTarget,
)
from shared.models import AgendaCard, FactionState, HexCoord


class Faction:
    """Server-side faction state."""

    def __init__(self, faction_id: str):
        self.faction_id = faction_id
        self.color = FACTION_COLORS[faction_id]
        self.gold: int = STARTING_GOLD
        self.agenda_pool: list[AgendaCard] = [
            AgendaCard(AgendaType.STEAL),
            AgendaCard(AgendaType.TRADE),
            AgendaCard(AgendaType.EXPAND),
            AgendaCard(AgendaType.CHANGE),
        ]
        self.change_modifiers: dict[str, int] = {
            ChangeModifierTarget.TRADE.value: 0,
            ChangeModifierTarget.STEAL.value: 0,
            ChangeModifierTarget.EXPAND.value: 0,
        }
        self.regard: dict[str, int] = {}
        self.guiding_spirit: Optional[str] = None
        self.worship_spirit: Optional[str] = None
        self.eliminated: bool = False
        # Turn tracking for scoring
        self.gold_gained_this_turn: int = 0
        self.territories_gained_this_turn: int = 0
        self.wars_won_this_turn: int = 0
        # Played agenda tracking for cleanup
        self.played_agenda_this_turn: list[AgendaCard] = []

    def reset_turn_tracking(self):
        self.gold_gained_this_turn = 0
        self.territories_gained_this_turn = 0
        self.wars_won_this_turn = 0

    def add_gold(self, amount: int):
        if amount > 0:
            self.gold_gained_this_turn += amount
        self.gold += amount
        if self.gold < 0:
            self.gold = 0

    def lose_gold(self, amount: int) -> int:
        """Lose up to `amount` gold. Returns the actual amount lost."""
        actual = min(self.gold, amount)
        self.gold -= actual
        return actual

    def get_regard(self, other_faction_id: str) -> int:
        return self.regard.get(other_faction_id, 0)

    def modify_regard(self, other_faction_id: str, delta: int):
        current = self.regard.get(other_faction_id, 0)
        self.regard[other_faction_id] = current + delta

    def draw_agenda_cards(self, count: int) -> list[AgendaCard]:
        """Draw `count` cards from the agenda pool (with replacement).

        The pool is never depleted — cards are sampled with replacement,
        so duplicates are possible.
        """
        return random.choices(self.agenda_pool, k=count)

    def draw_random_agenda(self) -> AgendaCard:
        """Draw a single random agenda card (for non-guided factions).

        The pool is never depleted.
        """
        return random.choice(self.agenda_pool)

    def replace_agenda_card(self, remove_type: AgendaType, add_type: AgendaType):
        """Replace one card of remove_type with add_type in the agenda pool.

        The pool size stays the same. If remove_type is not found (shouldn't
        happen in normal gameplay), appends add_type as a fallback.
        """
        for i, card in enumerate(self.agenda_pool):
            if card.agenda_type == remove_type:
                self.agenda_pool[i] = AgendaCard(add_type)
                return
        # Fallback: type not in pool (shouldn't happen)
        self.agenda_pool.append(AgendaCard(add_type))

    def add_change_modifier(self, card_value: str):
        self.change_modifiers[card_value] = self.change_modifiers.get(card_value, 0) + 1

    def cleanup_deck(self):
        """Clear turn tracking. The pool is static — no cards to return."""
        self.played_agenda_this_turn.clear()

    def shuffle_agenda_pool(self):
        random.shuffle(self.agenda_pool)

    def to_state(self, hex_map) -> FactionState:
        territories = hex_map.get_faction_territories(self.faction_id)
        return FactionState(
            faction_id=self.faction_id,
            color=self.color,
            gold=self.gold,
            territories=[HexCoord(q, r) for q, r in territories],
            agenda_pool=list(self.agenda_pool),
            change_modifiers=dict(self.change_modifiers),
            regard=dict(self.regard),
            guiding_spirit=self.guiding_spirit,
            worship_spirit=self.worship_spirit,
            eliminated=self.eliminated,
        )
