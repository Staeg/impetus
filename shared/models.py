"""Serializable data classes for game entities.

Used by both client and server for network communication.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from shared.constants import IdolType, AgendaType, Phase, ChangeModifierTarget


@dataclass
class HexCoord:
    q: int
    r: int

    def to_tuple(self) -> tuple[int, int]:
        return (self.q, self.r)

    @staticmethod
    def from_tuple(t: tuple[int, int]) -> HexCoord:
        return HexCoord(q=t[0], r=t[1])

    def to_dict(self) -> dict:
        return {"q": self.q, "r": self.r}

    @staticmethod
    def from_dict(d: dict) -> HexCoord:
        return HexCoord(q=d["q"], r=d["r"])

    def __hash__(self):
        return hash((self.q, self.r))

    def __eq__(self, other):
        if isinstance(other, HexCoord):
            return self.q == other.q and self.r == other.r
        return False


@dataclass
class Idol:
    type: IdolType
    position: HexCoord
    owner_spirit: str

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "position": self.position.to_dict(),
            "owner_spirit": self.owner_spirit,
        }

    @staticmethod
    def from_dict(d: dict) -> Idol:
        return Idol(
            type=IdolType(d["type"]),
            position=HexCoord.from_dict(d["position"]),
            owner_spirit=d["owner_spirit"],
        )


@dataclass
class AgendaCard:
    agenda_type: AgendaType

    def to_dict(self) -> dict:
        return {"agenda_type": self.agenda_type.value}

    @staticmethod
    def from_dict(d: dict) -> AgendaCard:
        return AgendaCard(agenda_type=AgendaType(d["agenda_type"]))


@dataclass
class FactionState:
    faction_id: str
    color: tuple[int, int, int]
    gold: int = 0
    territories: list[HexCoord] = field(default_factory=list)
    agenda_deck: list[AgendaCard] = field(default_factory=list)
    change_modifiers: dict[str, int] = field(default_factory=dict)
    regard: dict[str, int] = field(default_factory=dict)
    guiding_spirit: Optional[str] = None
    presence_spirit: Optional[str] = None
    eliminated: bool = False

    def to_dict(self) -> dict:
        # Count extra agenda cards (beyond 1 base copy per type)
        type_counts: dict[str, int] = {}
        for card in self.agenda_deck:
            t = card.agenda_type.value if hasattr(card.agenda_type, 'value') else card.agenda_type
            type_counts[t] = type_counts.get(t, 0) + 1
        agenda_deck_extra = {t: c - 1 for t, c in type_counts.items() if c > 1}

        return {
            "faction_id": self.faction_id,
            "color": list(self.color),
            "gold": self.gold,
            "territories": [h.to_dict() for h in self.territories],
            "agenda_deck_size": len(self.agenda_deck),
            "agenda_deck_extra": agenda_deck_extra,
            "change_modifiers": self.change_modifiers,
            "regard": self.regard,
            "guiding_spirit": self.guiding_spirit,
            "presence_spirit": self.presence_spirit,
            "eliminated": self.eliminated,
        }

    @staticmethod
    def from_dict(d: dict) -> FactionState:
        return FactionState(
            faction_id=d["faction_id"],
            color=tuple(d["color"]),
            gold=d["gold"],
            territories=[HexCoord.from_dict(h) for h in d["territories"]],
            change_modifiers=d.get("change_modifiers", {}),
            regard=d.get("regard", {}),
            guiding_spirit=d.get("guiding_spirit"),
            presence_spirit=d.get("presence_spirit"),
            eliminated=d.get("eliminated", False),
        )


@dataclass
class SpiritState:
    spirit_id: str
    name: str
    influence: int = 0
    is_vagrant: bool = True
    guided_faction: Optional[str] = None
    idols: list[Idol] = field(default_factory=list)
    victory_points: int = 0

    def to_dict(self) -> dict:
        return {
            "spirit_id": self.spirit_id,
            "name": self.name,
            "influence": self.influence,
            "is_vagrant": self.is_vagrant,
            "guided_faction": self.guided_faction,
            "idols": [i.to_dict() for i in self.idols],
            "victory_points": self.victory_points,
        }

    @staticmethod
    def from_dict(d: dict) -> SpiritState:
        return SpiritState(
            spirit_id=d["spirit_id"],
            name=d["name"],
            influence=d.get("influence", 0),
            is_vagrant=d.get("is_vagrant", True),
            guided_faction=d.get("guided_faction"),
            idols=[Idol.from_dict(i) for i in d.get("idols", [])],
            victory_points=d.get("victory_points", 0),
        )


@dataclass
class WarState:
    war_id: str
    faction_a: str
    faction_b: str
    is_ripe: bool = False
    battleground: Optional[tuple[HexCoord, HexCoord]] = None

    def to_dict(self) -> dict:
        bg = None
        if self.battleground:
            bg = [self.battleground[0].to_dict(), self.battleground[1].to_dict()]
        return {
            "war_id": self.war_id,
            "faction_a": self.faction_a,
            "faction_b": self.faction_b,
            "is_ripe": self.is_ripe,
            "battleground": bg,
        }

    @staticmethod
    def from_dict(d: dict) -> WarState:
        bg = None
        if d.get("battleground"):
            bg = (HexCoord.from_dict(d["battleground"][0]),
                  HexCoord.from_dict(d["battleground"][1]))
        return WarState(
            war_id=d["war_id"],
            faction_a=d["faction_a"],
            faction_b=d["faction_b"],
            is_ripe=d.get("is_ripe", False),
            battleground=bg,
        )


@dataclass
class GameStateSnapshot:
    """Full game state sent to clients."""
    turn: int
    phase: Phase
    factions: dict[str, FactionState]
    spirits: dict[str, SpiritState]
    wars: list[WarState]
    all_idols: list[Idol]
    hex_ownership: dict[str, Optional[str]]  # "q,r" -> faction_id or None

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "phase": self.phase.value,
            "factions": {k: v.to_dict() for k, v in self.factions.items()},
            "spirits": {k: v.to_dict() for k, v in self.spirits.items()},
            "wars": [w.to_dict() for w in self.wars],
            "all_idols": [i.to_dict() for i in self.all_idols],
            "hex_ownership": self.hex_ownership,
        }

    @staticmethod
    def from_dict(d: dict) -> GameStateSnapshot:
        return GameStateSnapshot(
            turn=d["turn"],
            phase=Phase(d["phase"]),
            factions={k: FactionState.from_dict(v) for k, v in d["factions"].items()},
            spirits={k: SpiritState.from_dict(v) for k, v in d["spirits"].items()},
            wars=[WarState.from_dict(w) for w in d["wars"]],
            all_idols=[Idol.from_dict(i) for i in d["all_idols"]],
            hex_ownership=d["hex_ownership"],
        )
