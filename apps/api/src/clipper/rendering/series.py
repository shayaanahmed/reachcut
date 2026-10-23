"""Reusable branded source cards and downloadable thumbnail designs, rendered locally."""

import subprocess
import textwrap
from pathlib import Path
from uuid import uuid4

from clipper.captions.animation import ass_color, ass_escape
from clipper.media.tools import require_tool
from clipper.rendering.informative import _filter_path
from clipper.shorts.series import ContentSeries, EpisodeVisual, ThumbnailDesign


def _lines(text: str, width: int, count: int) -> str:
    lines = [
        line
        for paragraph in text.splitlines()
        for line in (textwrap.wrap(paragraph, width=width) or [""])
    ]
    if len(lines) > count:
        lines = [*lines[: count - 1], lines[count - 1][: max(0, width - 2)] + "…"]
    return r"\N".join(ass_escape(line) for line in lines)


def _image(
    output: Path,
    width: int,
    height: int,
    design: ThumbnailDesign,
    blocks: list[tuple[str, int, int, int, int, str]],
    *,
    font: str = "Noto Sans",
) -> Path:
    if output.is_file():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    ass = output.with_name(token + ".ass")
    pending = output.with_name(token + ".png")
    font = font.replace(",", " ").replace("\n", " ").replace("\r", " ")
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding\n"
        f"Style: Text,{font},40,{ass_color(design.foreground)},&H00FFFFFF,&H00101827,"
        "&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    events = []
    for text, x, y, size, align, color in blocks:
        events.append(
            "Dialogue: 0,0:00:00.00,0:00:01.00,Text,,0,0,0,,"
            + rf"{{\an{align}\pos({x},{y})\fs{size}\c{ass_color(color)}}}"
            + text
        )
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    color = design.background.replace("#", "0x")
    accent = design.accent.replace("#", "0x")
    if design.layout == "centered":
        boxes = f"drawbox=x=45:y=45:w=iw-90:h=ih-90:color={accent}:t=5"
    elif design.layout == "terminal":
        boxes = f"drawbox=x=0:y=0:w=iw:h=90:color={accent}:t=fill"
    else:
        boxes = f"drawbox=x=45:y=100:w=14:h=ih-200:color={accent}:t=fill"
    try:
        subprocess.run(
            [
                require_tool("ffmpeg"),
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s={width}x{height}:r=1",
                "-vf",
                boxes
                + f",ass={_filter_path(ass)}:fontsdir="
                + _filter_path(Path(__file__).parent / "fonts"),
                "-frames:v",
                "1",
                "-threads",
                "1",
                str(pending),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        pending.replace(output)
    finally:
        ass.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
    return output


def render_thumbnail(series: ContentSeries, subject: str, headline: str, output: Path) -> Path:
    design = series.thumbnail
    title = (
        design.headline_template.replace("{subject}", subject)
        .replace("{series}", series.name)
        .replace("{headline}", headline or subject)
    )
    if design.layout == "centered":
        blocks = [
            (_lines(design.label or series.name, 40, 1), 640, 115, 30, 8, design.accent),
            (_lines(title, 26, 3), 640, 330, 74, 5, design.foreground),
            (_lines(subject, 52, 2), 640, 600, 32, 8, design.foreground),
        ]
    else:
        blocks = [
            (
                _lines(design.label or series.name, 40, 1),
                100,
                28 if design.layout == "terminal" else 95,
                30,
                7,
                design.foreground,
            ),
            (_lines(title, 29, 3), 100, 210, 72, 7, design.foreground),
            (_lines(subject, 56, 2), 100, 600, 30, 7, design.accent),
        ]
    return _image(output, 1280, 720, design, blocks, font=series.settings.caption_font)


def render_source_card(
    series: ContentSeries, visual: EpisodeVisual, source_title: str, output: Path
) -> Path:
    design = series.thumbnail
    body = visual.quote if visual.kind in {"source", "code"} and visual.quote else visual.body
    label = {
        "source": "SOURCE EXCERPT",
        "code": "DOCUMENTED CODE",
        "diagram": "EXPLANATION",
        "recording": "STORYBOARD • ADD YOUR RECORDING",
    }[visual.kind]
    blocks = [
        (_lines(series.name, 35, 1), 100, 100, 32, 7, design.accent),
        (_lines(visual.heading, 28, 3), 100, 245, 58, 7, design.foreground),
        (_lines(label, 45, 1), 100, 515, 25, 7, design.accent),
        (_lines(body, 40, 14), 100, 650, 36, 7, design.foreground),
        (
            _lines(source_title or "Original explanation based on the supplied subject", 55, 2),
            100,
            1530,
            24,
            7,
            design.accent,
        ),
    ]
    return _image(output, 1080, 1920, design, blocks, font=series.settings.caption_font)


def silent_audio(output: Path, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(uuid4().hex + ".wav")
    try:
        subprocess.run(
            [
                require_tool("ffmpeg"),
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                str(duration),
                str(pending),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
