from clipper.api.schemas import ClipResponse
from clipper.domain.editing_plan import EditingPlanV1
from clipper.editorial import recommend_for_publishing


def test_publish_recommendation_rewards_strong_short_form_candidate(make_plan) -> None:  # type: ignore[no-untyped-def]
    recommendation = recommend_for_publishing(make_plan(start=10, end=40, score=88))

    assert recommendation.score == 89
    assert recommendation.confidence == "high"
    assert "30s duration fits the views-focused version" in recommendation.reasons


def test_publish_recommendation_penalizes_very_long_candidate(make_plan) -> None:  # type: ignore[no-untyped-def]
    short = recommend_for_publishing(make_plan(start=0, end=40, score=75))
    long = recommend_for_publishing(make_plan(start=0, end=120, score=75))

    assert short.score > long.score
    assert any("tighter views edit" in reason for reason in long.reasons)


def test_publish_recommendation_uses_joined_duration_for_revenue_version(make_plan) -> None:  # type: ignore[no-untyped-def]
    payload = make_plan(start=0, end=100, score=80).model_dump(mode="json")
    payload["optimization_goal"] = "revenue"
    payload["source_slices"] = [
        {"start_seconds": 0, "end_seconds": 35},
        {"start_seconds": 65, "end_seconds": 100},
    ]

    recommendation = recommend_for_publishing(EditingPlanV1.model_validate(payload))

    assert "70s duration fits the revenue-focused version" in recommendation.reasons


def test_clip_response_includes_publish_recommendation(make_plan) -> None:  # type: ignore[no-untyped-def]
    response = ClipResponse.model_validate(
        {
            "id": "clip-1",
            "approval_status": "pending",
            "plan": make_plan(score=90),
            "preview_path": None,
            "final_path": None,
            "publications": [],
        }
    )

    assert response.model_dump()["publish_recommendation"]["score"] >= 90
