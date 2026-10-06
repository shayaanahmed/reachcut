from collections.abc import Callable

import pytest
from pydantic import ValidationError

from clipper.domain.editing_plan import EditingPlanV1, TimeRange


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


def test_legacy_plan_defaults_to_views_and_one_contiguous_source(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    payload = make_plan(start=10, end=40).model_dump(mode="json")
    for field in ("source_slices", "optimization_goal", "crop_focus_x", "crop_focus_y"):
        payload.pop(field)

    plan = EditingPlanV1.model_validate(payload)

    assert plan.optimization_goal == "views"
    assert plan.source_slices == []
    assert plan.timeline_duration == 30
    assert (plan.crop_focus_x, plan.crop_focus_y) == (0.5, 0.5)


def test_multi_slice_plan_uses_the_joined_timeline_duration(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    payload = make_plan(start=10, end=50).model_dump(mode="json")
    payload["source_slices"] = [
        {"start_seconds": 10, "end_seconds": 20},
        {"start_seconds": 40, "end_seconds": 50},
    ]

    plan = EditingPlanV1.model_validate(payload)

    assert plan.timeline_duration == 20
    assert plan.source_slices == [
        TimeRange(start_seconds=10, end_seconds=20),
        TimeRange(start_seconds=40, end_seconds=50),
    ]


def test_rejects_overlapping_source_slices(make_plan: Callable[..., EditingPlanV1]) -> None:
    payload = make_plan(start=10, end=50).model_dump(mode="json")
    payload["source_slices"] = [
        {"start_seconds": 10, "end_seconds": 30},
        {"start_seconds": 25, "end_seconds": 50},
    ]

    with pytest.raises(ValidationError, match="ordered and non-overlapping"):
        EditingPlanV1.model_validate(payload)


def test_translation_and_secondary_media_require_complete_timeline_data(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    payload = make_plan(start=0, end=20).model_dump(mode="json")
    payload["caption_config"].update(
        {"translation_mode": "bilingual", "target_language": "de", "translated_text": "Hallo"}
    )
    payload["secondary_media"] = [
        {
            "asset_id": "game-1",
            "filename": "game.mp4",
            "kind": "gameplay",
            "start_seconds": 2,
            "end_seconds": 18,
        }
    ]

    plan = EditingPlanV1.model_validate(payload)

    assert plan.caption_config.translation_mode == "bilingual"
    assert plan.secondary_media[0].placement == "bottom"

    payload["secondary_media"][0]["end_seconds"] = 22
    with pytest.raises(ValidationError, match="secondary media range exceeds"):
        EditingPlanV1.model_validate(payload)
