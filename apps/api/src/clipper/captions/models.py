from dataclasses import dataclass

from clipper.domain.transcript import Word


@dataclass(frozen=True)
class CaptionCue:
    """A display-ready phrase and its source word timings."""

    start_seconds: float
    end_seconds: float
    text: str
    words: tuple[Word, ...] = ()
