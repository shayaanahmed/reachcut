"""The approved scene-based visual language: real motion, distinct compositions, readable copy."""

import math
import subprocess
import wave
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from clipper.captions.ass import serialize_ass
from clipper.domain.editing_plan import CaptionConfig
from clipper.media.tools import require_tool
from clipper.rendering.episode_art import _font, _wrap
from clipper.rendering.html_frames import HTMLFramePainter, is_html_frame, validate_html_layout
from clipper.shorts.frames import FrameContent, FrameSequence

W, H, FPS = 540, 960, 30
INK, YELLOW, GREEN = "#151426", "#FFE14D", "#C5FF75"
ASSETS = Path(__file__).parent / "assets" / "frames"
VERSION = "html-library-v3"


@lru_cache(maxsize=160)
def font(size: int, family: str, weight: int = 800) -> ImageFont.FreeTypeFont:
    # Display faces remain expressive; small labels use a legible, narrower face.
    return _font(size, family="Space Grotesk" if size <= 24 else family, weight=weight)


class FramePainter:
    def __init__(
        self,
        content: FrameContent,
        sequence: FrameSequence,
        artwork: Path | None = None,
        footer: str = "",
    ) -> None:
        self.content, self.sequence = content, sequence
        self.footer = footer
        self.layout_issues: list[str] = []
        if artwork is None and content.template == "photo":
            artwork = ASSETS / (
                "preview-phone.png" if content.template == "photo" else "preview-blocks.png"
            )
        self.art = None
        if artwork:
            with Image.open(artwork) as image:
                self.art = ImageOps.fit(
                    image.convert("RGB"), (W, H), method=Image.Resampling.LANCZOS
                )

    def measure(self, value: str, size: int) -> float:
        return font(size, self.sequence.font).getlength(value)

    def text(
        self,
        draw: ImageDraw.ImageDraw,
        x: float,
        y: float,
        value: str,
        size: int = 24,
        color: str = INK,
        anchor: str | None = None,
        width: int = 450,
    ) -> None:
        while self.measure(value, size) > width and size > 16:
            size -= 1
        if self.measure(value, size) > width:
            self.layout_issues.append(f"Text is too wide: {value}")
            return
        draw.text(
            (x, y), value, font=font(size, self.sequence.font), fill=color, anchor=anchor or "lt"
        )

    @staticmethod
    def box(
        draw: ImageDraw.ImageDraw,
        rect: tuple[float, float, float, float],
        color: str,
        radius: int = 18,
        outline: str | None = None,
    ) -> None:
        draw.rounded_rectangle(rect, radius, fill=color, outline=outline, width=2)

    def rows(self, value: str, size: int, width: int) -> list[str]:
        return _wrap(value, font(size, self.sequence.font), width) if value else []

    def block(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        value: str,
        size: int,
        color: str = INK,
        width: int = 450,
        lines: int = 2,
    ) -> None:
        while len(self.rows(value, size, width)) > lines and size > 18:
            size -= 1
        if len(self.rows(value, size, width)) > lines:
            self.layout_issues.append(f"Shorten this {lines}-line label: {value}")
            return
        for i, row in enumerate(self.rows(value, size, width)):
            self.text(draw, x, y + i * round(size * 1.15), row, size, color, width=width)

    def pill(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        label: str,
        bg: str = YELLOW,
        fg: str = INK,
        size: int = 17,
        width: int = 470,
    ) -> None:
        while self.measure(label, size) + 28 > width and size > 14:
            size -= 1
        if self.measure(label, size) + 28 > width:
            self.layout_issues.append(f"Shorten this badge: {label}")
            return
        length = min(width, round(self.measure(label, size)) + 28)
        self.box(draw, (x, y, x + length, y + size + 22), bg, 12)
        draw.text((x + 14, y + 8), label, font=font(size, self.sequence.font), fill=fg, anchor="lt")

    def illustration(self, d: ImageDraw.ImageDraw, t: float) -> None:
        """Concrete illustrations, labelled separately from recordings or tested output."""
        c, s = self.content, self.sequence
        self.box(d, (54, 350, 486, 548), INK, 18)
        if c.visual_type == "particles":
            for ring in range(2):
                for n in range(16):
                    angle = n * math.tau / 16 + t * (0.45 if ring else -0.3)
                    radius = 42 + ((t * 28 + ring * 52) % 90)
                    x = 270 + math.cos(angle) * radius
                    y = 440 + math.sin(angle) * radius * 0.55
                    d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=YELLOW if ring else GREEN)
            d.ellipse((261, 431, 279, 449), fill=s.secondary)
            x = 270 + math.sin(t * 1.3) * 125
            d.polygon([(x, 520), (x - 8, 536), (x + 8, 536)], fill="#FFFFFF")
        elif c.visual_type == "folders":
            for n in range(3):
                x = 74 + n * 139
                self.box(d, (x, 439, x + 112, 515), [s.accent, s.secondary, "#17654E"][n], 10)
                self.box(d, (x + 5, 425, x + 62, 450), YELLOW, 6)
                self.text(d, x + 56, 478, str(n + 1), 34, "#FFFFFF", "mm", width=92)
                for k in range(3):
                    y = 369 + ((t * 0.6 + k / 3) % 1) * 65
                    d.rectangle((x + 30 + k * 15, y, x + 40 + k * 15, y + 12), fill="#FFFFFF")
        elif c.visual_type in {"search", "typing"}:
            self.box(d, (74, 371, 466, 418), "#FFFFFF", 10)
            value = c.query or c.title
            shown = value[: int(t * 9) % (len(value) + 12)]
            self.text(d, 88, 387, shown + "|", 20, INK, width=365)
            for n, item in enumerate(c.items[:2]):
                y = 438 + n * 44
                if t > 0.7:
                    self.box(d, (74, y, 466, y + 35), s.accent if n else s.secondary, 8)
                    self.text(d, 87, y + 8, item.body, 18, "#FFFFFF", width=365)
        elif c.visual_type == "browser":
            for n in range(3):
                x = 74 + n * 128
                y = 382 + round(math.sin(t + n) * 7)
                self.box(d, (x, y, x + 119, y + 124), [s.accent, s.secondary, "#17654E"][n], 10)
                d.line((x + 12, y + 26, x + 103, y + 26), fill="#FFFFFF", width=3)
                self.text(d, x + 59, y + 76, str(n + 1), 34, "#FFFFFF", "mm", width=96)

    def frame(self, local: float, duration: float, progress: float = 0) -> Image.Image:
        c, s = self.content, self.sequence
        t = local * self.content.duration_seconds / max(duration, 0.1)
        p = max(0, min(local / max(duration, 0.1), 1))
        if self.art:
            scale = 1.02 + 0.055 * p
            image = self.art.resize((round(W * scale), round(H * scale)), Image.Resampling.BILINEAR)
            x: float = (image.width - W) // 2
            y: float = (image.height - H) // 2
            im = image.crop((x, y, x + W, y + H)).convert("RGBA")
        else:
            im = Image.new(
                "RGBA",
                (W, H),
                INK
                if c.template in {"layers", "headline", "flow", "terminal"}
                else s.accent
                if c.template == "reveal"
                else s.background,
            )
        if c.template == "poll":
            im = Image.alpha_composite(im, Image.new("RGBA", (W, H), (15, 12, 35, 155)))
        d = ImageDraw.Draw(im)
        if c.template == "poll" and not self.art:
            # A deliberate graphic closing frame, never an unrelated generated portrait.
            d.ellipse((300 + p * 35, 90, 690 + p * 35, 480), fill=s.accent)
            d.ellipse((-170, 500 - p * 30, 170, 840 - p * 30), fill=s.secondary)
        # A small scene label replaces repeated large headers and decorative body panels.
        self.pill(
            d,
            30,
            85,
            "ILLUSTRATIVE EXAMPLE" if c.template == "demo" else c.eyebrow.upper(),
            s.accent if c.template in {"demo", "steps"} else YELLOW,
            "#FFFFFF" if c.template in {"demo", "steps"} else INK,
        )
        enter = 1 - (1 - min(t / 0.35, 1)) ** 3
        dy = round((1 - enter) * 25)
        items = c.items
        if c.template == "headline":
            self.text(d, 32, 173, "ONE IDEA. A CLOSER LOOK.", 18, GREEN)
            words = c.title.split()
            shown = " ".join(words[: max(1, min(len(words), int(t * 4) + 1))])
            self.block(d, 32, 270 + dy, shown, 76, "#FFFFFF", 460, 4)
            line_end = 32 + round(450 * min(t / 1.4, 1))
            d.rectangle((32, 620, line_end, 628), fill=YELLOW)
            self.text(d, 32, 655, "QUESTION → DISCOVERY", 22, GREEN)
        elif c.template == "flow":
            self.block(d, 32, 170, c.title, 40, "#FFFFFF", lines=2)
            for n, item in enumerate(items):
                y = 300 + n * 130
                active = t >= n * 0.8
                if n:
                    line_end = y - 30 + round(30 * max(0, min((t - n * 0.8) / 0.4, 1)))
                    d.line((270, y - 30, 270, line_end), fill=GREEN, width=4)
                self.box(d, (40, y, 500, y + 100), "#25283A", 16, GREEN if active else "#52546A")
                self.pill(d, 56, y + 23, str(n + 1), GREEN if active else YELLOW, INK)
                self.text(d, 118, y + 15, item.title, 27, "#FFFFFF", width=365)
                self.block(d, 118, y + 54, item.body, 19, "#D2D8E5", 360, 2)
        elif c.template == "terminal":
            self.block(d, 32, 170, c.title, 40, "#FFFFFF", lines=2)
            self.box(d, (30, 285, 510, 710), "#222536", 20, "#52546A")
            for n, color in enumerate(["#FF6A70", YELLOW, GREEN]):
                x = 54 + n * 22
                d.ellipse((x, 307, x + 10, 317), fill=color)
            self.text(d, 54, 342, "ILLUSTRATIVE PROMPT", 16, GREEN)
            prompt = c.query or c.title
            shown = prompt[: max(1, int(t * 18))]
            self.block(
                d, 54, 377, "> " + shown + ("_" if int(t * 2) % 2 else ""), 24, "#FFFFFF", 428, 3
            )
            for n, item in enumerate(items):
                if t < 1.2 + n * 0.65:
                    continue
                y = 490 + n * 67
                d.rectangle((54, y + 3, 58, y + 46), fill=GREEN if n == 2 else YELLOW)
                self.text(d, 72, y, item.title, 20, GREEN, width=410)
                self.block(d, 72, y + 26, item.body, 17, "#FFFFFF", 410, 2)
        elif c.template == "photo":
            x = 390 + round(math.sin(t * 3) * 7)
            self.box(d, (x - 48, 260 + dy, x + 48, 356 + dy), s.secondary, 26)
            self.text(d, x, 301 + dy, "?", 84, "#FFFFFF", "mm")
            self.pill(d, 32, 670, c.title, s.accent, "#FFFFFF", 19)
        elif c.template == "layers":
            lift = min(max((t - 0.5) / 1.2, 0), 1)
            for n, item in enumerate(items):
                y = 280 + n * (92 + 20 * lift) + dy
                left = 42 + n * 12 * lift
                color = [s.accent, s.secondary, GREEN][n]
                self.box(d, (left, y, left + 436, y + 102), color, 22)
                self.text(
                    d, left + 22, y + 16, item.title, 29, INK if n == 2 else "#FFFFFF", width=390
                )
                self.block(
                    d,
                    round(left + 22),
                    round(y + 57),
                    item.body,
                    19,
                    INK if n == 2 else "#FFFFFF",
                    width=390,
                    lines=2,
                )
            self.block(d, 32, 650, c.title, 30, "#FFFFFF", lines=2)
        elif c.template == "reveal":
            for x, y, r in [(420, 170, 130), (80, 630, 120)]:
                d.ellipse((x - r, y - r, x + r, y + r), outline="#FFFFFF40", width=2)
            rows = self.rows(c.title, 86, 460)
            size = 86
            while (
                len(rows) > 3 or any(self.measure(word, size) > 460 for word in c.title.split())
            ) and size > 32:
                size -= 1
                rows = self.rows(c.title, size, 460)
            if any(self.measure(word, size) > 460 for word in c.title.split()):
                self.layout_issues.append("Shorten the reveal title: " + c.title)
            for n, row in enumerate(rows):
                self.text(
                    d, 270, 240 + dy + n * round(size * 1.05), row, size, "#FFFFFF", "mm", width=470
                )
            self.box(d, (30, 494, 510, 670), s.background, 24)
            self.text(d, 54, 516, self.footer or c.eyebrow, 25, INK, width=430)
            for n, item in enumerate(items[:2]):
                self.pill(
                    d,
                    54 + n * 229,
                    576,
                    item.title,
                    GREEN if n == 0 else YELLOW,
                    INK,
                    18,
                    width=210,
                )
                self.block(d, 54 + n * 229, 624, item.body, 18, INK, width=205, lines=2)
        elif c.template == "demo":
            self.block(d, 32, 170, c.title, 38, lines=2)
            self.box(d, (30, 277, 510, 730), "#FFFFFF", 26, "#DBD7EA")
            self.pill(d, 54, 300, "HOW YOU COULD USE IT", YELLOW, INK, 14)
            concrete = c.visual_type != "workflow"
            if concrete:
                self.illustration(d, t)
            for n, item in enumerate(items):
                y = (560 + n * 53) if concrete else (389 + n * 108)
                active = t > 1.8 and n == len(items) - 1
                self.box(
                    d,
                    (54, y, 486, y + (47 if concrete else 102)),
                    GREEN if active else "#F0EDF5",
                    10,
                )
                if concrete:
                    self.text(d, 70, y + 5, item.title, 14, INK, width=385)
                    self.text(d, 70, y + 24, item.body, 18, INK, width=390)
                else:
                    self.text(d, 70, y + 8, item.title, 14, INK, width=385)
                    self.block(d, 70, y + 30, item.body, 20, INK, 390, 2)
        elif c.template == "steps":
            self.block(d, 32, 173, c.title, 40, lines=2)
            for n, item in enumerate(items):
                show = max(0, min((t - n * 0.8) / 0.3, 1))
                if show <= 0:
                    continue
                y = 300 + n * 128 + round((1 - show) * 30)
                self.box(d, (30, y, 510, y + 110), "#FFFFFF", 22, "#E6DDED")
                d.ellipse((48, y + 25, 102, y + 79), fill=s.accent if n % 2 == 0 else s.secondary)
                self.text(d, 75, y + 49, f"0{n + 1}", 23, "#FFFFFF", "mm", width=50)
                self.text(d, 119, y + 17, item.title, 28, INK, width=365)
                self.block(d, 119, y + 59, item.body, 19, INK, 360, 2)
        elif c.template == "comparison":
            self.block(d, 32, 180, c.title, 40, lines=2)
            if c.visual_type != "workflow":
                self.illustration(d, t)
            for n, item in enumerate(items[:2] if c.visual_type == "workflow" else []):
                x = 30 + n * 249
                y = 330 + round(math.sin(t * 1.4 + n) * 4)
                self.box(d, (x, y, x + 231, y + 325), s.accent if n else INK, 25)
                self.text(d, x + 115, y + 70, "+" if n else "?", 76, "#FFFFFF", "mm", width=200)
                self.block(d, x + 18, y + 150, item.title, 30, "#FFFFFF", 195, 2)
                self.block(d, x + 18, round(y + 230), item.body, 20, "#FFFFFF", 195, 3)
        elif c.template == "payoff":
            self.block(d, 32, 180, c.title, 48, lines=3)
            for n, item in enumerate(items):
                y = 380 + n * 105
                slide = round((1 - max(0, min((t - n * 0.5) / 0.3, 1))) * 60)
                self.box(
                    d, (40 + slide, y, 500 + slide, y + 82), s.accent if n != 1 else s.secondary, 20
                )
                self.text(d, 62 + slide, y + 24, item.title, 32, "#FFFFFF", width=410)
        elif c.template == "poll":
            self.block(d, 40, 218, c.title, 45, "#FFFFFF", 460, 2)
            for n, item in enumerate(items[:2]):
                y = 365 + n * 110 + round(math.sin(t * 2 + n) * 3)
                self.box(d, (40, y, 500, y + 88), GREEN if n == 0 else s.secondary, 20)
                self.text(
                    d,
                    64,
                    y + 25,
                    f"{'A' if n == 0 else 'B'}   {item.title}",
                    31,
                    INK if n == 0 else "#FFFFFF",
                    width=410,
                )
            self.text(d, 270, 673, self.footer, 23, "#FFFFFF", "mm")
        self.box(d, (24, 735, 508, 850), "#151426", 22)
        # A condensed display face keeps captions big without forcing the model
        # to cut a complete thought or falling back to small body typography.
        size = 40
        rows = _wrap(c.caption, font(size, "Anton"), 414)
        while len(rows) > 2 and size > 28:
            size -= 1
            rows = _wrap(c.caption, font(size, "Anton"), 414)
        if len(rows) > 2:
            self.layout_issues.append("Shorten the main caption: " + c.caption)
            rows = []
        y = 790 - len(rows) * size * 0.59
        words = c.caption.split()
        highlight = words[-2:]
        for row in rows:
            caption_font = font(size, "Anton")
            x = (W - caption_font.getlength(row)) / 2
            for word in row.split():
                d.text(
                    (x, y),
                    word,
                    font=caption_font,
                    fill=YELLOW if word in highlight else "#FFFFFF",
                    anchor="lt",
                )
                x += caption_font.getlength(word + " ")
            y += size * 1.18
        light = c.template in {"photo", "demo", "steps", "comparison", "payoff"}
        self.text(d, 270, 914, self.footer, 14, INK if light else "#FFFFFF", "mm")
        d.rectangle((24, 937, 516, 940), fill="#A5A0B8")
        d.rectangle((24, 937, 24 + 492 * max(0, min(progress, 1)), 940), fill=YELLOW)
        return im.convert("RGB")


@contextmanager
def scene_painter(
    content: FrameContent,
    sequence: FrameSequence,
    artwork: Path | None = None,
    footer: str = "",
    *,
    sample: bool = False,
) -> Iterator[FramePainter | HTMLFramePainter]:
    if is_html_frame(content):
        with HTMLFramePainter(content, sequence, sample=sample) as painter:
            yield painter
    else:
        yield FramePainter(content, sequence, artwork, footer)


def validate_frame_layout(content: FrameContent, sequence: FrameSequence) -> list[str]:
    """Use exactly the production font metrics and layout before saving a storyboard."""
    if is_html_frame(content):
        return validate_html_layout(content.model_dump_json(), sequence.model_dump_json())
    painter = FramePainter(content, sequence)
    for time in (0.5, content.duration_seconds * 0.9):
        painter.frame(time, content.duration_seconds)
    return sorted(set(painter.layout_issues))


def render_frame(
    content: FrameContent,
    sequence: FrameSequence,
    output: Path,
    artwork: Path | None = None,
    footer: str = "",
    *,
    sample: bool = False,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not sample and (issues := validate_frame_layout(content, sequence)):
        raise ValueError("Frame text does not fit: " + "; ".join(issues))
    with scene_painter(content, sequence, artwork, footer, sample=sample) as painter:
        image = painter.frame(content.duration_seconds * 0.8, content.duration_seconds)
        image.resize((1080, 1920), Image.Resampling.LANCZOS).save(output)
    return output


def render_frame_video(
    content: FrameContent,
    sequence: FrameSequence,
    audio: Path,
    output: Path,
    duration: float,
    artwork: Path | None = None,
    footer: str = "",
    cancelled: Callable[[], bool] = lambda: False,
    *,
    sample: bool = False,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(output.stem + ".pending.mp4")
    if not sample and (issues := validate_frame_layout(content, sequence)):
        raise ValueError("Frame text does not fit: " + "; ".join(issues))
    with scene_painter(content, sequence, artwork, footer, sample=sample) as painter:
        args = [
            require_tool("ffmpeg"),
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "540x960",
            "-r",
            str(FPS),
            "-i",
            "pipe:0",
            "-i",
            str(audio),
            "-vf",
            "scale=1080:1920:flags=lanczos",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-af",
            "apad",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            str(pending),
        ]
        try:
            with output.with_suffix(".render.log").open("w+") as log:
                process = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log
                )
                try:
                    assert process.stdin
                    for number in range(math.ceil(duration * FPS)):
                        if number % FPS == 0 and cancelled():
                            raise InterruptedError("Frame rendering stopped")
                        process.stdin.write(
                            painter.frame(
                                number / FPS, duration, number / max(duration * FPS, 1)
                            ).tobytes()
                        )
                    process.stdin.close()
                    if process.wait(timeout=120):
                        log.seek(0)
                        raise ValueError("Frame rendering failed: " + log.read()[-700:])
                except BaseException:
                    process.kill()
                    process.wait(timeout=30)
                    raise
            # The caption is drawn in its designed position; no duplicate narration overlay.
            output.with_suffix(".ass").write_text(serialize_ass([], CaptionConfig()))
            pending.replace(output)
            return output
        finally:
            pending.unlink(missing_ok=True)


def add_original_music(source: Path, output: Path, duration: float) -> Path:
    """A quiet original synth bed; voice remains the primary audio when present."""
    rate = 22050
    n = math.ceil(duration * rate)
    time = np.arange(n) / rate
    signal = np.zeros(n)
    for beat in np.arange(0, duration, 0.5):
        start = round(beat * rate)
        count = min(round(0.15 * rate), n - start)
        tt = np.arange(count) / rate
        signal[start : start + count] += (
            0.12 * np.sin(2 * np.pi * (52 * tt + 5 * (1 - np.exp(-tt * 35)))) * np.exp(-tt * 28)
        )
    for i, start_time in enumerate(np.arange(0, duration, 2)):
        start = round(start_time * rate)
        count = min(2 * rate, n - start)
        tt = np.arange(count) / rate
        freq = [130.81, 155.56, 196, 174.61][i % 4]
        signal[start : start + count] += 0.025 * np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 1.5)
    signal *= np.minimum(np.clip(time / 0.2, 0, 1), np.clip((duration - time) / 0.4, 0, 1))
    track = output.with_suffix(".wav")
    with wave.open(str(track), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes((signal * 32767).astype("<i2").tobytes())
    pending = output.with_name(output.stem + ".pending.mp4")
    try:
        subprocess.run(
            [
                require_tool("ffmpeg"),
                "-y",
                "-nostdin",
                "-i",
                str(source),
                "-i",
                str(track),
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=first:normalize=0,"
                "loudnorm=I=-16:TP=-1.5:LRA=9[a]",
                "-map",
                "0:v:0",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(pending),
            ],
            capture_output=True,
            check=True,
            timeout=180,
        )
        pending.replace(output)
        return output
    finally:
        pending.unlink(missing_ok=True)
