from dataclasses import dataclass


@dataclass(frozen=True)
class CropPoint:
    time_seconds: float
    center_x: float
    center_y: float


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
