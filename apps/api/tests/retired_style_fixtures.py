"""Historical snapshots for backwards-compatibility tests, never a product catalog."""

import json
from pathlib import Path

from clipper.shorts.series import SeriesStyle


def starter_styles() -> list[SeriesStyle]:
    data = json.loads((Path(__file__).parent / "fixtures/retired_series_styles.json").read_text())
    return [SeriesStyle.model_validate(style) for style in data]
