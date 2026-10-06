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


def retime_text(words: list[Word], text: str) -> list[Word]:
    """Map corrected display text onto the original clip timing without mutating the transcript."""

    tokens = text.split()
    if not words or not tokens:
        return []
    start = words[0].start_seconds
    duration = max(words[-1].end_seconds - start, 0.01)
    weights = [max(len(token.strip()), 1) for token in tokens]
    total_weight = sum(weights)
    elapsed_weight = 0
    corrected: list[Word] = []
    for token, weight in zip(tokens, weights, strict=True):
        token_start = start + duration * elapsed_weight / total_weight
        elapsed_weight += weight
        token_end = start + duration * elapsed_weight / total_weight
        corrected.append(Word(text=token, start_seconds=token_start, end_seconds=token_end))
    return corrected


def bilingual_cues(primary: list[CaptionCue], translated: list[CaptionCue]) -> list[CaptionCue]:
    """Attach translated phrases to primary cues that occupy the same timeline region."""

    combined: list[CaptionCue] = []
    for cue in primary:
        secondary = " ".join(
            translated_cue.text
            for translated_cue in translated
            if translated_cue.end_seconds > cue.start_seconds
            and translated_cue.start_seconds < cue.end_seconds
        ).strip()
        combined.append(
            CaptionCue(
                cue.start_seconds,
                cue.end_seconds,
                cue.text,
                cue.words,
                secondary or None,
            )
        )
    return combined


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
