from __future__ import annotations

from dataclasses import dataclass
import sys
from types import SimpleNamespace

from client.tutorials.catalog import TUTORIAL_CATALOG

if "pygame" not in sys.modules:
    sys.modules["pygame"] = SimpleNamespace(
        Rect=object,
        Surface=object,
        font=SimpleNamespace(Font=object),
    )

from client.tutorials.runtime import TutorialRuntimeController


@dataclass
class DummyScene:
    feedback: str | None = None
    context: dict | None = None

    def __post_init__(self) -> None:
        if self.context is None:
            self.context = {}

    def set_tutorial_feedback(self, message: str | None) -> None:
        self.feedback = message

    def get_tutorial_context(self) -> dict:
        return self.context


class DummyApp:
    def __init__(self) -> None:
        self.started: list[tuple[str, int]] = []
        self.exited = False

    def start_tutorial(self, campaign_id: str, scenario_index: int = 0) -> None:
        self.started.append((campaign_id, scenario_index))

    def exit_tutorial_to_menu(self) -> None:
        self.exited = True


def test_tutorial_catalog_bootstraps_all_scenarios() -> None:
    for campaign in TUTORIAL_CATALOG.values():
        assert campaign.entry_scenarios
        for scenario in campaign.entry_scenarios:
            result = scenario.bootstrap()
            assert result.game_state.phase is not None
            assert result.human_spirit_id in result.game_state.spirits
            assert scenario.steps


def test_runtime_blocks_actions_not_allowed_by_step() -> None:
    app = DummyApp()
    runtime = TutorialRuntimeController(app, "basics")
    scene = DummyScene(context={"inspection_tags": set()})
    runtime.attach_scene(scene)

    allowed, message = runtime.can_perform("submit", {}, scene)

    assert not allowed
    assert message is not None


def test_runtime_completes_after_matching_event() -> None:
    app = DummyApp()
    runtime = TutorialRuntimeController(app, "advanced", scenario_index=3)
    scene = DummyScene()
    runtime.attach_scene(scene)

    runtime.handle_semantic_event("winner_choice_selected", {"war_id": "war-1"})

    assert runtime.progress.awaiting_acknowledgement is True


def test_runtime_advance_moves_to_next_step_before_next_scenario() -> None:
    app = DummyApp()
    runtime = TutorialRuntimeController(app, "basics")
    runtime.progress.awaiting_acknowledgement = True

    runtime.advance()

    assert runtime.progress.step_index == 1
    assert app.started == []
    assert app.exited is False
