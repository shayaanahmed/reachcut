from clipper.captions.animation import animated_events, ass_color
from clipper.captions.models import CaptionCue
from clipper.domain.editing_plan import CaptionConfig, Emphasis


def serialize_ass(
    cues: list[CaptionCue], config: CaptionConfig, emphasis: list[Emphasis] | None = None
) -> str:
    """Serialize Unicode ASS; shaping remains delegated to libass/FriBidi."""

    alignment = {"bottom": 2, "middle": 5, "top": 8}[config.position]
    margin_v = {"bottom": 210, "middle": 80, "top": 180}[config.position]
    font = config.font_family.replace(",", " ").replace("\n", " ").strip()
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding",
            f"Style: Caption,{font},{config.font_size},{ass_color(config.text_color)},"
            f"{ass_color(config.highlight_color)},{ass_color(config.outline_color)},"
            f"&H70000000,-1,0,0,0,100,100,0,0,1,5,1,{alignment},72,72,{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    events = [
        _ass_event(start, end, text)
        for cue in cues
        for start, end, text in animated_events(cue, config, emphasis)
    ]
    return header + "\n" + "\n".join(events) + "\n"


def _ass_event(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Caption,,0,0,0,,{text}"


def _ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"
