import pytest

from clipper.services.tracking import CropPoint, smooth_crop_path


def test_crop_smoothing_limits_velocity_and_bounds() -> None:
    result = smooth_crop_path(
        [CropPoint(0, 0.1, 0.5), CropPoint(0.1, 1.2, -0.2)],
        smoothing=1,
        max_velocity_per_second=0.5,
    )
    assert result[1].center_x == pytest.approx(0.15)
    assert result[1].center_y == pytest.approx(0.45)
