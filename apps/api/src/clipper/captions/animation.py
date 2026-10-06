import re

from clipper.captions.models import CaptionCue
from clipper.domain.editing_plan import CaptionConfig, Emphasis


def animated_events(
    cue: CaptionCue, config: CaptionConfig, emphasis: list[Emphasis] | None = None
) -> list[tuple[float, float, str]]:
    """Return timed ASS event payloads without serializing an ASS document."""

    emphasized = {_word_key(word) for word in config.highlighted_words}
    for item in emphasis or []:
        emphasized.update(_word_key(word) for word in item.words)
    if config.animation == "karaoke" and cue.words:
        words: list[str] = []
        for index, word in enumerate(cue.words):
            next_start = (
                cue.words[index + 1].start_seconds
                if index + 1 < len(cue.words)
                else word.end_seconds
            )
            duration = max(0.01, next_start - word.start_seconds)
            words.append(f"{{\\kf{max(1, round(duration * 100))}}}{ass_escape(word.text)}")
        colors = f"{{\\1c{ass_color(config.highlight_color)}\\2c{ass_color(config.text_color)}}}"
        return [
            (
                cue.start_seconds,
                cue.end_seconds,
                _with_secondary(colors + " ".join(words), cue.secondary_text),
            )
        ]
    if config.animation == "pop" and cue.words:
        events: list[tuple[float, float, str]] = []
        for active_index, active_word in enumerate(cue.words):
            parts: list[str] = []
            for index, caption_word in enumerate(cue.words):
                active = index == active_index
                highlighted = active or _word_key(caption_word.text) in emphasized
                tags = ""
                if highlighted:
                    tags += f"\\c{ass_color(config.highlight_color)}"
                if active:
                    tags += "\\fscx118\\fscy118\\t(90,180,\\fscx100\\fscy100)"
                if tags:
                    parts.append(f"{{{tags}}}{ass_escape(caption_word.text)}{{\\r}}")
                else:
                    parts.append(ass_escape(caption_word.text))
            next_start = (
                cue.words[active_index + 1].start_seconds
                if active_index + 1 < len(cue.words)
                else active_word.end_seconds
            )
            events.append(
                (
                    max(cue.start_seconds, active_word.start_seconds),
                    min(cue.end_seconds, max(next_start, active_word.start_seconds + 0.08)),
                    _with_secondary(" ".join(parts), cue.secondary_text),
                )
            )
        return events
    parts = [
        (
            f"{{\\c{ass_color(config.highlight_color)}}}{ass_escape(word.text)}{{\\r}}"
            if _word_key(word.text) in emphasized
            else ass_escape(word.text)
        )
        for word in cue.words
    ]
    return [
        (cue.start_seconds, cue.end_seconds, _with_secondary(" ".join(parts), cue.secondary_text))
    ]


def _with_secondary(primary: str, secondary: str | None) -> str:
    if not secondary:
        return primary
    return primary + r"\N" + r"{\fs42}" + ass_escape(secondary)


def ass_color(value: str) -> str:
    red, green, blue = value[1:3], value[3:5], value[5:7]
    return f"&H00{blue}{green}{red}&"


def ass_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _word_key(value: str) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", "", value.casefold())
