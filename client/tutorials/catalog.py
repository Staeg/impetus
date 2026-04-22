from __future__ import annotations

from client.tutorials.scenarios import ADVANCED_SCENARIOS, BASICS_SCENARIOS
from client.tutorials.types import TutorialCatalogEntry


TUTORIAL_CATALOG: dict[str, TutorialCatalogEntry] = {
    "basics": TutorialCatalogEntry(
        id="basics",
        title="Basics",
        description="A guided Era 1 onboarding arc covering the core turn loop.",
        entry_scenarios=BASICS_SCENARIOS,
    ),
    "advanced": TutorialCatalogEntry(
        id="advanced",
        title="Advanced Mechanics",
        description="Short deterministic chapters for rarer Era 1 edge cases.",
        entry_scenarios=ADVANCED_SCENARIOS,
    ),
}
