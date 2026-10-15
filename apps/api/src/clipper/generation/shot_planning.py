"""Choose native shot lengths without splitting short continuous actions into a montage."""

import re
from typing import Literal

from clipper.generation.contracts import StoryPlanningRequest


def shot_durations(request: StoryPlanningRequest, format_name: str = "") -> list[Literal[5, 10]]:
    story = request.story.lower()
    continuous_format = any(
        token in format_name.lower() for token in ("hydraulic", "cctv", "doorbell", "bodycam")
    )
    fixed_camera = bool(re.search(r"\b(?:fixed|static)[ -]camera\b", story))
    single_shot = "continuous shot" in story or "single shot" in story
    continuous = request.shot_mode == "continuous" or (
        request.shot_mode == "auto" and (continuous_format or fixed_camera or single_shot)
    )
    duration = max(5, min(60, request.target_duration_seconds))
    if not continuous:
        return [5] * max(1, round(duration / 5))
    lengths: list[Literal[5, 10]] = [10] * (duration // 10)
    if duration % 10:
        lengths.append(5)
    return lengths
