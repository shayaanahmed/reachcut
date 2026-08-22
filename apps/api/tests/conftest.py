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
