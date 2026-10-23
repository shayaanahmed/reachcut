from collections.abc import Callable

import pytest

from clipper.domain.editing_plan import EditingPlanV1


@pytest.fixture
def make_plan() -> Callable[..., EditingPlanV1]:
    def factory(start: float = 10, end: float = 40, score: int = 80) -> EditingPlanV1:
        return EditingPlanV1.model_validate(
            {
                "schema_version": "1.0",
                "source": {"start_seconds": start, "end_seconds": end},
                "scores": {
                    "overall": score,
                    "hook": score,
                    "clarity": score,
                    "payoff": score,
                    "visual_interest": score,
                },
                "rationale": "A self-contained idea with a clear payoff.",
                "hook": {"text": "A useful opening", "start_seconds": 0, "end_seconds": 2},
                "caption_style": "clean",
                "emphasis": [],
                "effects": [],
                "cta": None,
            }
        )

    return factory


@pytest.fixture(autouse=True)
def isolate_background_schedulers(monkeypatch: pytest.MonkeyPatch) -> None:
    # TestClient lifespan must never process real local projects or publish posts.
    import clipper.main as main

    monkeypatch.setattr(main, "initialize_account_identities", lambda: None)
    monkeypatch.setattr(main, "run_growth_cycle", lambda: None)
    monkeypatch.setattr(main, "run_project_cycle", lambda **kwargs: None)
    monkeypatch.setattr(main, "run_automation_cycle", lambda: [])
    monkeypatch.setattr(main, "run_story_video_cycle", lambda: None)
    monkeypatch.setattr(main, "run_informative_cycle", lambda: None)
    monkeypatch.setattr(main, "run_publication_cycle", lambda: None)
