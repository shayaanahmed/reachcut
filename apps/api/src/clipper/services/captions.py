from __future__ import annotations

from dataclasses import dataclass

from clipper.domain.transcript import Word


@dataclass(frozen=True)
class CaptionCue:
    start_seconds: float
    end_seconds: float
    text: str


def phrase_cues(words: list[Word], max_words: int = 6, max_chars: int = 34) -> list[CaptionCue]:
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
        words[0].start_seconds, words[-1].end_seconds, " ".join(w.text for w in words)
    )


def subtitle_timestamp(seconds: float, vtt: bool = False) -> str:
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    separator = "." if vtt else ","
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{ms:03}"


def serialize_srt(cues: list[CaptionCue]) -> str:
    return (
        "\n\n".join(
            f"{index}\n{subtitle_timestamp(cue.start_seconds)} --> "
            f"{subtitle_timestamp(cue.end_seconds)}\n{cue.text}"
            for index, cue in enumerate(cues, 1)
        )
        + "\n"
    )


def serialize_vtt(cues: list[CaptionCue]) -> str:
    body = "\n\n".join(
        f"{subtitle_timestamp(cue.start_seconds, True)} --> "
        f"{subtitle_timestamp(cue.end_seconds, True)}\n{cue.text}"
        for cue in cues
    )
    return f"WEBVTT\n\n{body}\n"
