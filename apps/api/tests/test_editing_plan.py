from collections.abc import Callable

import pytest
from pydantic import ValidationError

from clipper.domain.editing_plan import EditingPlanV1


def test_rejects_unknown_effect(make_plan: Callable[..., EditingPlanV1]) -> None:
    payload = make_plan().model_dump(mode="json")
    payload["effects"] = [{"time_seconds": 2, "type": "flash_every_second", "parameters": {}}]
    with pytest.raises(ValidationError):
        EditingPlanV1.model_validate(payload)


def test_rejects_relative_time_outside_clip(make_plan: Callable[..., EditingPlanV1]) -> None:
    payload = make_plan(start=20, end=40).model_dump(mode="json")
    payload["hook"] = {"text": "Too late", "start_seconds": 19, "end_seconds": 21}
    with pytest.raises(ValidationError, match="exceeds selected source duration"):
        EditingPlanV1.model_validate(payload)


def test_clamps_zoom_values(make_plan: Callable[..., EditingPlanV1]) -> None:
    payload = make_plan().model_dump(mode="json")
    payload["effects"] = [
        {
            "time_seconds": 2,
            "type": "punch_zoom",
            "parameters": {"scale": 9, "duration_seconds": 99},
        }
    ]
    effect = EditingPlanV1.model_validate(payload).effects[0]
    assert effect.parameters == {"scale": 1.35, "duration_seconds": 8.0}


def test_validates_ready_to_paste_hashtags(make_plan: Callable[..., EditingPlanV1]) -> None:
    payload = make_plan().model_dump(mode="json")
    payload["suggested_title"] = "The One Detail Everyone Misses"
    payload["hashtags"] = ["#UsefulTips", "missing-prefix"]

    with pytest.raises(ValidationError, match="String should match pattern"):
        EditingPlanV1.model_validate(payload)
