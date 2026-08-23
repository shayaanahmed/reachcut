import re
import unicodedata

from clipper.captions.models import CaptionCue
from clipper.domain.transcript import Word


def phrase_cues(words: list[Word], max_words: int = 6, max_chars: int = 34) -> list[CaptionCue]:
    """Group timed words into readable phrases without formatting them."""

    cues: list[CaptionCue] = []
    current: list[Word] = []
    for word in words:
        proposed = " ".join([*(item.text for item in current), word.text])
        pause = bool(current and word.start_seconds - current[-1].end_seconds > 0.45)
        if current and (len(current) >= max_words or len(proposed) > max_chars or pause):
            cues.append(_cue(current))
            current = []
        current.append(word)
    if current:
        cues.append(_cue(current))
    return cues


def _cue(words: list[Word]) -> CaptionCue:
    return CaptionCue(
        words[0].start_seconds,
        words[-1].end_seconds,
        _join_words(words),
        tuple(words),
    )


def _join_words(words: list[Word]) -> str:
    text = " ".join(unicodedata.normalize("NFC", word.text.strip()) for word in words)
    # Urdu/Arabic and Latin punctuation should not acquire an artificial leading space.
    return re.sub(r"\s+([,.!?،؛؟۔:])", r"\1", text)  # noqa: RUF001
