from clipper.api.schemas import ClipResponse
from clipper.editorial import recommend_for_publishing


def test_publish_recommendation_rewards_strong_short_form_candidate(make_plan) -> None:  # type: ignore[no-untyped-def]
    recommendation = recommend_for_publishing(make_plan(start=10, end=40, score=88))

    assert recommendation.score == 89
    assert recommendation.confidence == "high"
    assert "30s duration fits short-form viewing" in recommendation.reasons


def test_publish_recommendation_penalizes_very_long_candidate(make_plan) -> None:  # type: ignore[no-untyped-def]
    short = recommend_for_publishing(make_plan(start=0, end=40, score=75))
    long = recommend_for_publishing(make_plan(start=0, end=120, score=75))

    assert short.score > long.score
    assert any("tighter edit" in reason for reason in long.reasons)


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
