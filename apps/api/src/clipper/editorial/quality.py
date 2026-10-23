"""Evidence-based plan checks. Scores remain editorial estimates."""

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript


def candidate_findings(plan: EditingPlanV1, transcript: Transcript) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    slices = plan.source_slices or [plan.source]
    segments = transcript.segments
    for item in slices:
        for boundary, position in ((item.start_seconds, "opening"), (item.end_seconds, "ending")):
            crossing = next(
                (s for s in segments if s.start_seconds + 0.15 < boundary < s.end_seconds - 0.15),
                None,
            )
            if crossing:
                findings.append(
                    {
                        "code": "sentence_boundary",
                        "severity": "warning",
                        "start": boundary,
                        "message": (
                            f"The {position} is inside a transcript segment; "
                            "check sentence context."
                        ),
                        "basis": "source_transcript",
                    }
                )
    if plan.scores.overall < 50:
        findings.append(
            {
                "code": "weak_selection",
                "severity": "warning",
                "start": plan.source.start_seconds,
                "message": "Low editorial estimate; review whether this moment is worth keeping.",
                "basis": "editorial_estimate",
            }
        )
    return findings


def distinct_candidates(plans: list[EditingPlanV1], minimum_score: int = 40) -> list[EditingPlanV1]:
    selected: list[EditingPlanV1] = []
    for plan in sorted(plans, key=lambda p: p.scores.overall, reverse=True):
        # Never pad output with low-scoring or near-identical moments.
        if plan.scores.overall < minimum_score:
            continue
        a = plan.source
        duplicate = False
        for prior in selected:
            b = prior.source
            overlap = max(
                0.0, min(a.end_seconds, b.end_seconds) - max(a.start_seconds, b.start_seconds)
            )
            if (
                overlap / min(a.end_seconds - a.start_seconds, b.end_seconds - b.start_seconds)
                > 0.75
            ):
                duplicate = True
                break
        if not duplicate:
            selected.append(plan)
    return selected
