"""Caption-artifact checks, explicitly distinct from rendered-pixel inspection."""

import re
import unicodedata


def _seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def inspect_ass(document: str, duration: float) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    font_size = 58.0
    for line in document.splitlines():
        if line.startswith("Style: Caption,"):
            font_size = float(line.split(",")[2])
        if not line.startswith("Dialogue:"):
            continue
        fields = line.split(",", 9)
        if len(fields) != 10:
            continue
        start, end = _seconds(fields[1]), _seconds(fields[2])
        text = re.sub(r"\{[^}]*\}", "", fields[9])
        if start < 0 or end <= start or end > duration + 0.25:
            findings.append(
                {
                    "code": "caption_timing",
                    "severity": "warning",
                    "start": start,
                    "message": "Caption timing falls outside the clip",
                    "basis": "caption_artifact",
                }
            )
        if fields[3] != "Caption":
            continue
        # Conservative estimate; shaping, glyph widths and actual pixels still
        # require visual review. Never label this as detected rendered overflow.
        lines = text.split(r"\N")
        if any(
            sum(0 if unicodedata.combining(c) else 1 for c in part) * font_size * 0.6 > 936
            for part in lines
        ):
            findings.append(
                {
                    "code": "caption_layout",
                    "severity": "warning",
                    "start": start,
                    "message": (
                        "Caption line may exceed the safe width; estimated from "
                        "caption text and font size."
                    ),
                    "basis": "caption_artifact_estimate",
                }
            )
    return findings
