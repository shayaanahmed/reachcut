import textwrap

from clipper.captions.animation import animated_events, ass_color, ass_escape
from clipper.captions.models import CaptionCue
from clipper.domain.editing_plan import CTA, CaptionConfig, Effect, EffectType, Emphasis, Hook


def serialize_ass(
    cues: list[CaptionCue],
    config: CaptionConfig,
    emphasis: list[Emphasis] | None = None,
    hook: Hook | None = None,
    cta: CTA | None = None,
    effects: list[Effect] | None = None,
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
            f"Style: Hook,{font},64,&H00FFFFFF,&H00FFFFFF,&H00111111,&H98000000,"
            "-1,0,0,0,100,100,0,0,3,3,0,8,90,90,170,1",
            f"Style: CTA,{font},58,&H00FFFFFF,&H00FFFFFF,&H00111111,&H98000000,"
            "-1,0,0,0,100,100,0,0,3,3,0,2,90,90,170,1",
            f"Style: Card,{font},54,&H00FFFFFF,&H00FFFFFF,&H00111111,&H98000000,"
            "-1,0,0,0,100,100,0,0,3,3,0,5,90,90,120,1",
            f"Style: Speaker,{font},38,&H00FFFFFF,&H00FFFFFF,&H00111111,&H98000000,"
            "-1,0,0,0,100,100,0,0,3,2,0,7,54,54,100,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    events = (
        [
            _ass_event(start, end, text)
            for cue in cues
            for start, end, text in animated_events(cue, config, emphasis)
        ]
        if config.enabled
        else []
    )
    if hook and hook.render:
        wrapped = r"\N".join(ass_escape(line) for line in textwrap.wrap(hook.text, width=30))
        events.insert(0, _ass_event(hook.start_seconds, hook.end_seconds, wrapped, "Hook"))
    if cta and cta.render:
        wrapped = r"\N".join(ass_escape(line) for line in textwrap.wrap(cta.text, width=32))
        events.append(_ass_event(cta.start_seconds, cta.end_seconds, wrapped, "CTA"))
    for effect in effects or []:
        if effect.type not in {
            EffectType.QUESTION_CARD,
            EffectType.QUOTE_CARD,
            EffectType.SPEAKER_LABEL,
        }:
            continue
        text = str(effect.parameters.get("text", "")).strip()
        if not text:
            continue
        duration = float(effect.parameters.get("duration_seconds", 2.5))
        style = "Speaker" if effect.type is EffectType.SPEAKER_LABEL else "Card"
        events.append(
            _ass_event(
                effect.time_seconds,
                effect.time_seconds + duration,
                r"\N".join(ass_escape(line) for line in textwrap.wrap(text, width=34)),
                style,
            )
        )
    return header + "\n" + "\n".join(events) + "\n"


def _ass_event(start: float, end: float, text: str, style: str = "Caption") -> str:
    return f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},{style},,0,0,0,,{text}"


def _ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"
