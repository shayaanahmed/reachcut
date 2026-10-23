"""Bounded references to bundled or locally generated template artwork."""

import re
from pathlib import Path

from clipper.shorts.series import SeriesStyle

BUILTIN_ART = Path(__file__).parent / "assets" / "templates"


def template_artwork(root: Path, style: SeriesStyle) -> Path | None:
    asset = style.design.background_asset_id if style.design else ""
    if not asset:
        return None
    if re.fullmatch(r"builtin-(electric|paper|blueprint|mint|coral|midnight)", asset):
        path = BUILTIN_ART / f"{asset}.png"
    elif re.fullmatch(r"[a-f0-9]{64}", asset):
        path = root / f"{asset}.png"
    else:
        raise ValueError("Unknown template artwork reference")
    if not path.is_file():
        raise ValueError("Template artwork is unavailable; regenerate this design")
    return path
