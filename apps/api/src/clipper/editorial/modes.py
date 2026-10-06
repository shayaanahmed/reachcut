from dataclasses import dataclass

from clipper.domain.editing_plan import ContentMode
from clipper.domain.transcript import Transcript


@dataclass(frozen=True)
class ModeSignals:
    face_coverage: float = 0
    motion_confidence: float = 0


def infer_content_mode(
    title: str,
    original_filename: str,
    transcript: Transcript,
    signals: ModeSignals | None = None,
) -> ContentMode:
    """Infer a conservative editing mode from project context and visual summaries."""

    text = " ".join(
        [title, original_filename, *(segment.text for segment in transcript.segments[:30])]
    ).casefold()
    keyword_modes: tuple[tuple[ContentMode, tuple[str, ...]], ...] = (
        (
            ContentMode.SPORTS,
            (
                "football",
                "soccer",
                "basketball",
                "boxing",
                "mma",
                "ufc",
                "knockout",
                "match highlights",
                "goal ",
                "cricket",
                "tennis",
                "racing",
            ),
        ),
        (
            ContentMode.GAMEPLAY,
            ("gameplay", "gaming", "twitch", "stream", "minecraft", "fortnite", "speedrun"),
        ),
        (
            ContentMode.PODCAST,
            ("podcast", "interview", "conversation", "episode", "guest"),
        ),
        (
            ContentMode.TUTORIAL,
            ("tutorial", "how to", "walkthrough", "demo", "course", "step by step"),
        ),
        (
            ContentMode.PRODUCT,
            ("review", "product", "unboxing", "discount", "offer", "buy", "features"),
        ),
        (
            ContentMode.NEWS,
            ("news", "breaking", "report", "explained", "analysis", "update"),
        ),
        (ContentMode.REACTION, ("reaction", "reacts", "watching")),
    )
    for mode, keywords in keyword_modes:
        if any(keyword in text for keyword in keywords):
            return mode
    observed = signals or ModeSignals()
    if observed.face_coverage >= 0.25:
        return ContentMode.TALKING_HEAD
    if observed.motion_confidence >= 0.35:
        return ContentMode.SPORTS
    return ContentMode.AUTO
