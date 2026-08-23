"""Compatibility entry point for rendering.

New code should use :class:`clipper.rendering.VideoRenderer`.
"""

from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1
from clipper.rendering import RenderRequest, VideoRenderer


def render_vertical(
    source: Path, plan: EditingPlanV1, subtitles: Path, output: Path, preview: bool = True
) -> dict[str, object]:
    return VideoRenderer().render(RenderRequest(source, plan, subtitles, output, preview))
