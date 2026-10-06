from clipper.domain.editing_plan import ContentMode, TimeRange
from clipper.rendering.tracking import (
    CropPoint,
    VisualAnalysis,
    keyframes_for_clip,
    smooth_crop_path,
)


def test_tracking_points_are_smoothed_and_retimed_across_source_slices() -> None:
    analysis = VisualAnalysis(
        face_points=(
            CropPoint(10, 0.1, 0.5),
            CropPoint(11, 0.9, 0.5),
            CropPoint(30, 0.8, 0.4),
        ),
        sampled_frames=3,
        frames_with_faces=3,
    )

    points = keyframes_for_clip(
        analysis,
        ContentMode.TALKING_HEAD,
        [TimeRange(start_seconds=10, end_seconds=12), TimeRange(start_seconds=30, end_seconds=31)],
    )

    assert [point.time_seconds for point in points] == [0, 1, 2]
    assert points[1].center_x < 0.9
    assert points[-1].confidence == 1


def test_tracking_velocity_is_limited() -> None:
    points = smooth_crop_path(
        [CropPoint(0, 0, 0), CropPoint(0.1, 1, 1)],
        smoothing=1,
        max_velocity_per_second=0.5,
    )

    assert points[-1].center_x == 0.05
    assert points[-1].center_y == 0.05
