from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from clipper.domain.editing_plan import ContentMode, CropKeyframe, TimeRange, TrackingStrategy


@dataclass(frozen=True)
class CropPoint:
    time_seconds: float
    center_x: float
    center_y: float
    confidence: float = 1.0


@dataclass(frozen=True)
class VisualAnalysis:
    """Adapter-neutral face, group, and action observations on the source timeline."""

    face_points: tuple[CropPoint, ...] = ()
    group_points: tuple[CropPoint, ...] = ()
    action_points: tuple[CropPoint, ...] = ()
    sampled_frames: int = 0
    frames_with_faces: int = 0

    @property
    def face_coverage(self) -> float:
        return self.frames_with_faces / self.sampled_frames if self.sampled_frames else 0

    def as_artifact(self) -> dict[str, object]:
        return {
            "face_points": [point.__dict__ for point in self.face_points],
            "group_points": [point.__dict__ for point in self.group_points],
            "action_points": [point.__dict__ for point in self.action_points],
            "sampled_frames": self.sampled_frames,
            "frames_with_faces": self.frames_with_faces,
        }

    @classmethod
    def from_artifact(cls, payload: dict[str, object]) -> VisualAnalysis:
        def points(key: str) -> tuple[CropPoint, ...]:
            raw = payload.get(key, [])
            if not isinstance(raw, list):
                return ()
            return tuple(
                CropPoint(
                    time_seconds=float(str(item["time_seconds"])),
                    center_x=float(str(item["center_x"])),
                    center_y=float(str(item["center_y"])),
                    confidence=float(str(item.get("confidence", 1))),
                )
                for item in raw
                if isinstance(item, dict)
            )

        return cls(
            face_points=points("face_points"),
            group_points=points("group_points"),
            action_points=points("action_points"),
            sampled_frames=int(str(payload.get("sampled_frames", 0))),
            frames_with_faces=int(str(payload.get("frames_with_faces", 0))),
        )


class VisualTrackingProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def analyze(
        self,
        source: Path,
        cancelled: TrackingCancellationProbe,
        progress: TrackingProgressReporter,
    ) -> VisualAnalysis: ...


TrackingCancellationProbe = Callable[[], bool]
TrackingProgressReporter = Callable[[float], None]


def smooth_crop_path(
    points: list[CropPoint], smoothing: float = 0.25, max_velocity_per_second: float = 0.8
) -> list[CropPoint]:
    """Exponential smoothing with a normalized velocity limit."""

    if not points:
        return []
    result = [points[0]]
    for point in points[1:]:
        previous = result[-1]
        elapsed = max(point.time_seconds - previous.time_seconds, 1e-6)
        target_x = previous.center_x + smoothing * (point.center_x - previous.center_x)
        target_y = previous.center_y + smoothing * (point.center_y - previous.center_y)
        limit = max_velocity_per_second * elapsed
        delta_x = min(max(target_x - previous.center_x, -limit), limit)
        delta_y = min(max(target_y - previous.center_y, -limit), limit)
        result.append(
            CropPoint(
                point.time_seconds,
                min(max(previous.center_x + delta_x, 0), 1),
                min(max(previous.center_y + delta_y, 0), 1),
            )
        )
    return result


def strategy_for_mode(mode: ContentMode) -> TrackingStrategy:
    return {
        ContentMode.PODCAST: TrackingStrategy.ACTIVE_SPEAKER,
        ContentMode.SPORTS: TrackingStrategy.ACTION,
        ContentMode.TUTORIAL: TrackingStrategy.OBJECT,
        ContentMode.GAMEPLAY: TrackingStrategy.ACTION,
    }.get(mode, TrackingStrategy.FACE)


def keyframes_for_clip(
    analysis: VisualAnalysis,
    mode: ContentMode,
    slices: list[TimeRange],
) -> list[CropKeyframe]:
    """Map source observations onto a gap-free clip timeline and smooth crop motion."""

    strategy = strategy_for_mode(mode)
    if strategy is TrackingStrategy.ACTION or strategy is TrackingStrategy.OBJECT:
        source_points = analysis.action_points
    elif strategy is TrackingStrategy.ACTIVE_SPEAKER:
        source_points = analysis.group_points or analysis.face_points
    else:
        source_points = analysis.face_points
    mapped: list[CropPoint] = []
    offset = 0.0
    for source_slice in slices:
        for point in source_points:
            if source_slice.start_seconds <= point.time_seconds <= source_slice.end_seconds:
                mapped.append(
                    CropPoint(
                        offset + point.time_seconds - source_slice.start_seconds,
                        point.center_x,
                        point.center_y,
                        point.confidence,
                    )
                )
        offset += source_slice.end_seconds - source_slice.start_seconds
    smoothed = smooth_crop_path(mapped, smoothing=0.35, max_velocity_per_second=0.45)
    return [
        CropKeyframe(
            time_seconds=point.time_seconds,
            center_x=point.center_x,
            center_y=point.center_y,
            confidence=point.confidence,
        )
        for point in smoothed
    ]
