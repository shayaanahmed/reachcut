from clipper.captions.models import CaptionCue


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
            f"{subtitle_timestamp(cue.end_seconds)}\n{_display_text(cue)}"
            for index, cue in enumerate(cues, 1)
        )
        + "\n"
    )


def serialize_vtt(cues: list[CaptionCue]) -> str:
    body = "\n\n".join(
        f"{subtitle_timestamp(cue.start_seconds, True)} --> "
        f"{subtitle_timestamp(cue.end_seconds, True)}\n{_display_text(cue)}"
        for cue in cues
    )
    return f"WEBVTT\n\n{body}\n"


def _display_text(cue: CaptionCue) -> str:
    return f"{cue.text}\n{cue.secondary_text}" if cue.secondary_text else cue.text
