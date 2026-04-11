"""Serializable data classes for game entities.

Used by both client and server for network communication.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from shared.constants import IdolType, AgendaType, Phase, ChangeModifierTarget, FACTION_NAMES, Era


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
    agenda_pool: list[AgendaCard] = field(default_factory=list)
    change_modifiers: dict[str, int] = field(default_factory=dict)
    regard: dict[str, int] = field(default_factory=dict)
    guiding_spirit: Optional[str] = None
    worship_spirit: Optional[str] = None
    race: str = ""
    guidance_step: str = ""
    restrained_agenda: Optional[str] = None
    queued_agendas: list[str] = field(default_factory=list)
    shaping_effects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "faction_id": self.faction_id,
            "color": list(self.color),
            "gold": self.gold,
            "territories": [h.to_dict() for h in self.territories],
            "agenda_pool": [
                c.agenda_type.value if hasattr(c.agenda_type, 'value') else c.agenda_type
                for c in self.agenda_pool
            ],
            "change_modifiers": self.change_modifiers,
            "regard": self.regard,
            "guiding_spirit": self.guiding_spirit,
            "worship_spirit": self.worship_spirit,
            "race": self.race,
            "guidance_step": self.guidance_step,
            "restrained_agenda": self.restrained_agenda,
            "queued_agendas": self.queued_agendas,
            "shaping_effects": self.shaping_effects,
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
            worship_spirit=d.get("worship_spirit"),
            race=d.get("race", ""),
            guidance_step=d.get("guidance_step", ""),
            restrained_agenda=d.get("restrained_agenda"),
            queued_agendas=d.get("queued_agendas", []),
            shaping_effects=d.get("shaping_effects", []),
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
    habitat_affinity: str = ""
    race_affinity: str = ""
    adaptation_effects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "spirit_id": self.spirit_id,
            "name": self.name,
            "influence": self.influence,
            "is_vagrant": self.is_vagrant,
            "guided_faction": self.guided_faction,
            "idols": [i.to_dict() for i in self.idols],
            "victory_points": self.victory_points,
            "habitat_affinity": self.habitat_affinity,
            "race_affinity": self.race_affinity,
            "adaptation_effects": self.adaptation_effects,
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
            habitat_affinity=d.get("habitat_affinity", ""),
            race_affinity=d.get("race_affinity", ""),
            adaptation_effects=d.get("adaptation_effects", []),
        )


@dataclass
class WarState:
    war_id: str
    faction_a: str
    faction_b: str
    battleground_a: Optional[HexCoord] = None
    battleground_b: Optional[HexCoord] = None
    resolve_turn: int = 0
    declared_turn: int = 0
    is_staged: bool = False

    def to_dict(self) -> dict:
        return {
            "war_id": self.war_id,
            "faction_a": self.faction_a,
            "faction_b": self.faction_b,
            "battleground_a": self.battleground_a.to_dict() if self.battleground_a else None,
            "battleground_b": self.battleground_b.to_dict() if self.battleground_b else None,
            "resolve_turn": self.resolve_turn,
            "declared_turn": self.declared_turn,
            "is_staged": self.is_staged,
        }

    @staticmethod
    def from_dict(d: dict) -> WarState:
        return WarState(
            war_id=d["war_id"],
            faction_a=d["faction_a"],
            faction_b=d["faction_b"],
            battleground_a=HexCoord.from_dict(d["battleground_a"]) if d.get("battleground_a") else None,
            battleground_b=HexCoord.from_dict(d["battleground_b"]) if d.get("battleground_b") else None,
            resolve_turn=d.get("resolve_turn", 0),
            declared_turn=d.get("declared_turn", 0),
            is_staged=d.get("is_staged", False),
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
    faction_order: list[str] = None
    era: Era = Era.ERA_1
    vp_target: int = 0

    def __post_init__(self):
        if self.faction_order is None:
            self.faction_order = list(FACTION_NAMES)

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "phase": self.phase.value,
            "factions": {k: v.to_dict() for k, v in self.factions.items()},
            "spirits": {k: v.to_dict() for k, v in self.spirits.items()},
            "wars": [w.to_dict() for w in self.wars],
            "all_idols": [i.to_dict() for i in self.all_idols],
            "hex_ownership": self.hex_ownership,
            "faction_order": self.faction_order,
            "era": self.era.value,
            "vp_target": self.vp_target,
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
            faction_order=d.get("faction_order", list(FACTION_NAMES)),
            era=Era(d.get("era", Era.ERA_1.value)),
            vp_target=d.get("vp_target", 0),
        )
