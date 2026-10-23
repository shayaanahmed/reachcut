"""Reusable purpose-first editorial layouts with bundled, licensed typography."""

from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, ImageOps

from clipper.shorts.series import ContentSeries, EpisodeVisual

FONTS = Path(__file__).parent / "fonts"
FONT_FILES = {
    "Bricolage Grotesque": "BricolageGrotesque.ttf",
    "Anton": "Anton.ttf",
    "Space Grotesk": "SpaceGrotesk.ttf",
    "Syne": "Syne.ttf",
    "Fraunces": "Fraunces.ttf",
}


def _font(
    size: int, *, mono: bool = False, weight: int = 800, family: str = "Bricolage Grotesque"
) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(
        str(FONTS / ("JetBrainsMono.ttf" if mono else FONT_FILES[family])), size
    )
    if family != "Anton" or mono:
        axes = font.get_variation_axes()
        values: list[float] = []
        for axis in axes:
            name = (axis["name"] or b"").decode().lower()
            value = weight if "weight" in name else (axis["default"] or 0)
            values.append(float(min(axis["maximum"] or value, max(axis["minimum"] or 0, value))))
        font.set_variation_by_axes(values)
    return font


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(lines[-1] + " " + word) <= width:
            lines[-1] += " " + word
        else:
            # Break long unspaced strings as well, so repository names cannot overflow.
            fragment = ""
            for character in word:
                if fragment and font.getlength(fragment + character) > width:
                    lines.append(fragment)
                    fragment = ""
                fragment += character
            lines.append(fragment)
    return lines or [""]


def render_episode_art(
    series: ContentSeries,
    visual: EpisodeVisual,
    output: Path,
    artwork: Path | None = None,
    *,
    layout: str = "poster",
    weight: int = 800,
    uppercase: bool = False,
    scene_label: str = "",
) -> Path:
    if output.is_file():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    design = series.thumbnail
    canvas = Image.new("RGB", (1080, 1920), design.background)
    if artwork:
        with Image.open(artwork) as source:
            windows = {
                "editorial": (70, 650, 940, 550),
                "kinetic": (0, 720, 1080, 500),
                "cards": (90, 650, 900, 560),
                "split": (0, 650, 1080, 570),
                "spotlight": (70, 650, 940, 560),
            }
            if layout in windows:
                x, y, width, height = windows[layout]
                # Portrait artwork puts the subject low, below reserved headline space.
                # Keep that focal object above the separate copy panel.
                canvas.paste(
                    ImageOps.fit(source.convert("RGB"), (width, height), centering=(0.5, 0.9)),
                    (x, y),
                )
            else:
                canvas = ImageOps.fit(source.convert("RGB"), canvas.size)
        if layout not in windows:
            overlay = Image.new("RGBA", canvas.size)
            shade = ImageDraw.Draw(overlay)
            rgb = tuple(int(design.background[i : i + 2], 16) for i in (1, 3, 5))
            for y in range(1920):
                alpha = int(220 * max(0, 1 - y / 1350))
                shade.line((0, y, 1080, y), fill=(*rgb, alpha))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    if layout == "cards":
        draw.rounded_rectangle((52, 625, 1028, 1240), radius=36, outline=design.accent, width=5)
        draw.ellipse((850, 670, 970, 790), outline=design.accent, width=8)
    if layout == "editorial":
        draw.line((76, 210, 1004, 210), fill=design.accent, width=3)
    if not artwork:
        draw.rounded_rectangle((70, 820, 1010, 1400), radius=70, fill=design.accent)
        draw.ellipse((380, 940, 700, 1260), fill=design.background)
        draw.line((450, 1100, 630, 1100), fill=design.foreground, width=18)
        draw.polygon([(620, 1050), (675, 1100), (620, 1150)], fill=design.foreground)
    draw.rounded_rectangle((72, 115, 1008, 184), radius=24, fill=design.accent)
    badge = (design.label or series.name)[:38]
    draw.text((96, 128), badge, font=_font(28, mono=True, weight=650), fill=design.background)
    for size in range(148 if layout == "kinetic" else 124, 53, -2):
        headline_font = _font(size, family=series.headline_font, weight=weight)
        lines = _wrap(visual.heading.upper() if uppercase else visual.heading, headline_font, 920)
        if len(lines) <= 3:
            break
    y = 245
    for line in lines[:3]:
        draw.text(
            (76, y),
            line,
            font=headline_font,
            fill=design.foreground,
            stroke_width=1,
            stroke_fill=design.foreground,
        )
        y += int(size * 1.05)
    # Fixed lower panel prevents body copy from competing with the image or captions.
    draw.rounded_rectangle((70, 1230, 1010, 1530), radius=36, fill=design.background)
    label = (
        scene_label
        or {
            "hook": "IMAGINE THIS",
            "purpose": "MEET THE IDEA",
            "example": "FOR EXAMPLE",
            "how": "HOW IT WORKS",
            "outcome": "WHAT YOU COULD DO",
            "cta": "TRY IT",
        }[visual.role]
    )
    draw.text((100, 1255), label, font=_font(25, mono=True, weight=650), fill=design.accent)
    body_font = _font(42, weight=600)
    for i, line in enumerate(_wrap(visual.body, body_font, 875)[:4]):
        draw.text((100, 1310 + i * 48), line, font=body_font, fill=design.foreground)
    if artwork:
        draw.text(
            (78, 1560),
            "AI ILLUSTRATION",
            font=_font(22, mono=True, weight=600),
            fill=design.foreground,
            stroke_width=1,
            stroke_fill=design.background,
        )
    pending = output.with_name(uuid4().hex + ".png")
    try:
        canvas.save(pending)
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
    return output


def render_art_thumbnail(
    series: ContentSeries,
    subject: str,
    headline: str,
    artwork: Path,
    output: Path,
) -> Path:
    """Reuse the niche identity and first scene's illustration for the episode cover."""
    if output.is_file():
        return output
    design = series.thumbnail
    canvas = Image.new("RGB", (1280, 720), design.background)
    with Image.open(artwork) as image:
        canvas.paste(ImageOps.fit(image.convert("RGB"), (570, 720)), (710, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((40, 65, 52, 650), fill=design.accent)
    draw.text(
        (82, 70), (design.label or series.name)[:30], font=_font(24, mono=True), fill=design.accent
    )
    title = (
        design.headline_template.replace("{subject}", subject)
        .replace("{series}", series.name)
        .replace("{headline}", headline)
    )
    for size in range(86, 25, -2):
        font = _font(size, family=series.headline_font)
        lines = _wrap(title, font, 580)
        if len(lines) <= 4:
            break
    for i, line in enumerate(lines[:4]):
        draw.text((82, 205 + i * (size + 5)), line, font=font, fill=design.foreground)
    pending = output.with_name(uuid4().hex + ".png")
    try:
        canvas.save(pending)
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
    return output
