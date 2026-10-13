from pathlib import Path

import cv2
import numpy as np
import pytest

from clipper.domain.editing_plan import ThumbnailTemplate
from clipper.rendering.thumbnails import ThumbnailCandidate, ThumbnailRenderer


@pytest.mark.parametrize("template", list(ThumbnailTemplate))
def test_thumbnail_templates_render_platform_sized_png(
    tmp_path: Path,
    template: ThumbnailTemplate,
) -> None:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:, :, 0] = np.linspace(20, 200, 1280, dtype=np.uint8)
    image[:, :, 1] = 80
    image[:, :, 2] = 140
    output = tmp_path / f"{template.value}.png"

    ThumbnailRenderer().render(
        ThumbnailCandidate(12.5, image, 0.9),
        "A Strong Thumbnail Hook",
        template,
        output,
    )

    rendered = cv2.imread(str(output))
    assert rendered is not None
    assert rendered.shape == (720, 1280, 3)
