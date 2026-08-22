from __future__ import annotations

from dataclasses import dataclass

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Segment


@dataclass(frozen=True)
class TranscriptChunk:
    start_seconds: float
    end_seconds: float
    text: str
    segment_ids: tuple[int, ...]


def semantic_windows(
    segments: list[Segment], target_seconds: float = 90, max_seconds: float = 180
) -> list[TranscriptChunk]:
    """Create sentence-aligned model windows without splitting transcript segments."""
    windows: list[TranscriptChunk] = []
    current: list[Segment] = []
    for segment in segments:
        if current and segment.end_seconds - current[0].start_seconds > max_seconds:
            windows.append(_window(current))
            current = []
        current.append(segment)
        duration = current[-1].end_seconds - current[0].start_seconds
        if duration >= target_seconds and segment.text.rstrip().endswith((".", "!", "?")):
            windows.append(_window(current))
            current = []
    if current:
        windows.append(_window(current))
    return windows


def _window(segments: list[Segment]) -> TranscriptChunk:
    return TranscriptChunk(
        start_seconds=segments[0].start_seconds,
        end_seconds=segments[-1].end_seconds,
        text=" ".join(segment.text for segment in segments),
        segment_ids=tuple(segment.id for segment in segments),
    )


def diverse_top_plans(
    plans: list[EditingPlanV1], count: int, max_overlap_ratio: float = 0.3
) -> list[EditingPlanV1]:
    selected: list[EditingPlanV1] = []
    for plan in sorted(plans, key=lambda item: item.scores.overall, reverse=True):
        if all(_overlap_ratio(plan, other) <= max_overlap_ratio for other in selected):
            selected.append(plan)
            if len(selected) == count:
                break
    return selected


def _overlap_ratio(left: EditingPlanV1, right: EditingPlanV1) -> float:
    overlap = max(
        0,
        min(left.source.end_seconds, right.source.end_seconds)
        - max(left.source.start_seconds, right.source.start_seconds),
    )
    shortest = min(
        left.source.end_seconds - left.source.start_seconds,
        right.source.end_seconds - right.source.start_seconds,
    )
    return overlap / shortest
