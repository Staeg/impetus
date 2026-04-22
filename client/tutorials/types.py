from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol


TutorialCampaignId = Literal["basics", "advanced"]


class TutorialSceneAdapter(Protocol):
    def set_tutorial_feedback(self, message: str | None) -> None: ...
    def get_tutorial_context(self) -> dict[str, Any]: ...
    def clear_tutorial_state(self) -> None: ...


@dataclass(frozen=True)
class TutorialHighlightSpec:
    kind: str
    value: Any
    accent: tuple[int, int, int] = (244, 210, 113)


@dataclass(frozen=True)
class TutorialInputGate:
    allowed_actions: set[str]
    validator: Callable[[str, dict[str, Any], TutorialSceneAdapter], tuple[bool, str | None]] | None = None


@dataclass(frozen=True)
class TutorialCompletionRule:
    event_types: set[str]
    predicate: Callable[[dict[str, Any], TutorialSceneAdapter], bool] | None = None
    min_matches: int = 1


@dataclass(frozen=True)
class TutorialStepDefinition:
    id: str
    objective_text: str
    help_text: str
    allowed_actions: set[str]
    highlights: list[TutorialHighlightSpec] = field(default_factory=list)
    completion_rule: TutorialCompletionRule | None = None
    requires_observation: bool = False
    input_gate: TutorialInputGate | None = None


@dataclass(frozen=True)
class TutorialScenarioDefinition:
    id: str
    title: str
    bootstrap: Callable[[], Any]
    steps: list[TutorialStepDefinition]
    completion_summary: str


@dataclass(frozen=True)
class TutorialCatalogEntry:
    id: TutorialCampaignId
    title: str
    description: str
    entry_scenarios: list[TutorialScenarioDefinition]
