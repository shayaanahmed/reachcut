from collections.abc import Callable

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Segment
from clipper.editorial import diverse_top_plans, semantic_windows


def test_windows_preserve_segment_boundaries() -> None:
    segments = [
        Segment(id=i, text=f"Idea {i}.", start_seconds=i * 30, end_seconds=(i + 1) * 30, words=[])
        for i in range(5)
    ]
    windows = semantic_windows(segments, target_seconds=60, max_seconds=90)
    assert [window.segment_ids for window in windows] == [(0, 1), (2, 3), (4,)]


def test_diversity_removes_overlapping_candidate(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    plans = [make_plan(0, 30, 90), make_plan(5, 28, 89), make_plan(50, 80, 70)]
    selected = diverse_top_plans(plans, 2)
    assert [(p.source.start_seconds, p.source.end_seconds) for p in selected] == [(0, 30), (50, 80)]
