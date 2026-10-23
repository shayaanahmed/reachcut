"""Map measured ASR word timing to the display script only when words agree."""

import re

from clipper.captions.models import CaptionCue
from clipper.domain.transcript import Transcript


def align_display_script(text: str, transcript: Transcript, duration: float) -> list[CaptionCue]:
    tokens = text.split()
    measured = [word for segment in transcript.segments for word in segment.words]

    def normalized(value: str) -> str:
        return re.sub(r"[^\w\u0600-\u06ff]", "", value.casefold())

    if not measured or [normalized(t) for t in tokens] != [normalized(w.text) for w in measured]:
        raise ValueError("Measured words do not match the display script; review phrase captions")
    cues: list[CaptionCue] = []
    for start in range(0, len(tokens), 6):
        words = measured[start : start + 6]
        if any(w.end_seconds <= w.start_seconds or w.end_seconds > duration + 0.2 for w in words):
            raise ValueError("Alignment timestamps are invalid")
        cues.append(
            CaptionCue(
                words[0].start_seconds,
                min(duration, words[-1].end_seconds),
                " ".join(tokens[start : start + 6]),
                tuple(words),
            )
        )
    return cues
