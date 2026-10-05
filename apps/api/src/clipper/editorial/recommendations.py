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
    duration = plan.source.end_seconds - plan.source.start_seconds
    duration_score = _duration_score(duration)
    weighted = (
        scores.hook * 0.30
        + scores.clarity * 0.25
        + scores.payoff * 0.25
        + scores.visual_interest * 0.15
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
    if 20 <= duration <= 60:
        reasons.append(f"{duration:.0f}s duration fits short-form viewing")
    elif duration < 20:
        reasons.append(f"{duration:.0f}s duration is concise but may need more context")
    else:
        reasons.append(f"{duration:.0f}s duration may need a tighter edit")
    return PublishRecommendation(score=score, confidence=confidence, reasons=reasons)


def _duration_score(duration: float) -> int:
    if 20 <= duration <= 60:
        return 100
    if 12 <= duration < 20 or 60 < duration <= 90:
        return 75
    return 45
