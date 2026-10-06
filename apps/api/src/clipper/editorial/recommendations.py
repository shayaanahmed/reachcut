from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from clipper.domain.editing_plan import EditingPlanV1


class PublishRecommendation(BaseModel):
    """Explainable estimate of a clip's short-form publishing potential."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    confidence: Literal["high", "medium", "low"]
    reasons: list[str] = Field(min_length=2, max_length=4)


def recommend_for_publishing(plan: EditingPlanV1) -> PublishRecommendation:
    """Score stable editorial signals without claiming future views or revenue."""

    scores = plan.scores
    duration = plan.timeline_duration
    duration_score = _duration_score(duration, plan.optimization_goal)
    weighted = (
        scores.hook * 0.35
        + scores.clarity * 0.30
        + scores.payoff * 0.25
        + scores.visual_interest * 0.05
        + scores.overall * 0.05
    )
    score = round(weighted * 0.9 + duration_score * 0.1)
    confidence: Literal["high", "medium", "low"]
    if score >= 80:
        confidence = "high"
    elif score >= 65:
        confidence = "medium"
    else:
        confidence = "low"

    named_scores = {
        "Opening hook": scores.hook,
        "Standalone clarity": scores.clarity,
        "Payoff": scores.payoff,
        "Visual interest": scores.visual_interest,
    }
    strongest = sorted(named_scores.items(), key=lambda item: item[1], reverse=True)[:2]
    reasons = [f"{label} is {value}/100" for label, value in strongest]
    if plan.optimization_goal == "revenue" and 61 <= duration <= 90:
        reasons.append(f"{duration:.0f}s duration fits the revenue-focused version")
    elif plan.optimization_goal == "views" and 20 <= duration <= 40:
        reasons.append(f"{duration:.0f}s duration fits the views-focused version")
    elif duration < (61 if plan.optimization_goal == "revenue" else 20):
        reasons.append(f"{duration:.0f}s duration may need more context for this version")
    else:
        reasons.append(f"{duration:.0f}s duration may need a tighter {plan.optimization_goal} edit")
    return PublishRecommendation(score=score, confidence=confidence, reasons=reasons)


def _duration_score(duration: float, goal: Literal["views", "revenue"]) -> int:
    if goal == "revenue":
        if 61 <= duration <= 90:
            return 100
        if 50 <= duration < 61 or 90 < duration <= 120:
            return 75
        return 45
    if 20 <= duration <= 40:
        return 100
    if 12 <= duration < 20 or 40 < duration <= 60:
        return 75
    return 45
