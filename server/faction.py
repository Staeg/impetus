"""Faction model: gold, territories, agenda deck, modifiers, regard."""

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
        self.agenda_deck: list[AgendaCard] = [
            AgendaCard(AgendaType.STEAL),
            AgendaCard(AgendaType.BOND),
            AgendaCard(AgendaType.TRADE),
            AgendaCard(AgendaType.EXPAND),
            AgendaCard(AgendaType.CHANGE),
        ]
        self.change_modifiers: dict[str, int] = {
            ChangeModifierTarget.TRADE.value: 0,
            ChangeModifierTarget.BOND.value: 0,
            ChangeModifierTarget.STEAL.value: 0,
            ChangeModifierTarget.EXPAND.value: 0,
        }
        self.regard: dict[str, int] = {}
        self.guiding_spirit: Optional[str] = None
        self.presence_spirit: Optional[str] = None
        self.eliminated: bool = False
        # Turn tracking for scoring
        self.gold_gained_this_turn: int = 0
        self.territories_gained_this_turn: int = 0
        self.wars_won_this_turn: int = 0
        # Agenda deck tracking for cleanup
        self.played_agenda_this_turn: list[AgendaCard] = []
        self.spoils_cards_this_turn: list[AgendaCard] = []

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
        """Draw `count` cards from the shuffled agenda deck.

        Cards are removed from the deck when drawn. They should be
        returned via played_agenda_this_turn during cleanup.
        """
        random.shuffle(self.agenda_deck)
        n = min(count, len(self.agenda_deck))
        hand = self.agenda_deck[:n]
        self.agenda_deck = self.agenda_deck[n:]
        return hand

    def draw_random_agenda(self) -> AgendaCard:
        """Draw a single random agenda card (for non-guided factions)."""
        return random.choice(self.agenda_deck)

    def add_agenda_card(self, agenda_type: AgendaType):
        self.agenda_deck.append(AgendaCard(agenda_type))

    def add_spoils_card(self, agenda_type: AgendaType):
        """Stage a Spoils of War card for permanent addition during cleanup."""
        self.spoils_cards_this_turn.append(AgendaCard(agenda_type))

    def cleanup_deck(self):
        """Return all played and spoils cards to the deck and shuffle."""
        self.agenda_deck.extend(self.played_agenda_this_turn)
        self.agenda_deck.extend(self.spoils_cards_this_turn)
        self.played_agenda_this_turn.clear()
        self.spoils_cards_this_turn.clear()
        random.shuffle(self.agenda_deck)

    def shuffle_agenda_deck(self):
        random.shuffle(self.agenda_deck)

    def to_state(self, hex_map) -> FactionState:
        territories = hex_map.get_faction_territories(self.faction_id)
        return FactionState(
            faction_id=self.faction_id,
            color=self.color,
            gold=self.gold,
            territories=[HexCoord(q, r) for q, r in territories],
            agenda_deck=list(self.agenda_deck),
            change_modifiers=dict(self.change_modifiers),
            regard=dict(self.regard),
            guiding_spirit=self.guiding_spirit,
            presence_spirit=self.presence_spirit,
            eliminated=self.eliminated,
        )
