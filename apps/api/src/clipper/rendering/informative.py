"""Deterministic narration-led assembly and actual decode/audio inspection."""

import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from clipper.captions.ass import serialize_ass
from clipper.captions.models import CaptionCue
from clipper.domain.editing_plan import CaptionConfig
from clipper.media.errors import MediaError
from clipper.media.metadata import media_metadata
from clipper.media.tools import require_tool


def audio_duration(path: Path) -> float:
    payload = media_metadata(path)
    if not any(s.get("codec_type") == "audio" for s in payload.get("streams", [])):
        raise ValueError("Narration file has no audio stream")
    duration = float(payload["format"]["duration"])
    if not 0.1 <= duration <= 90:
        raise ValueError("Each narration section must be between 0.1 and 90 seconds")
    return duration


def _run(args: list[str], timeout: int = 600) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    if result.returncode:
        raise ValueError("Media processing failed: " + result.stderr[-800:])


def render_section(
    audio: Path,
    output: Path,
    heading: str,
    text: str,
    duration: float,
    font: str,
    asset: Path | None = None,
    recording: bool = False,
    aligned_cues: list[CaptionCue] | None = None,
    attribution: str = "",
    style: str = "demo",
    caption_style: str = "clean",
    accent: str = "#60A5FA",
    motion: bool = False,
    normalize_audio: bool = True,
    frame_rate: int = 25,
) -> Path:
    if frame_rate not in {24, 25, 30, 60}:
        raise ValueError("Unsupported frame rate")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Section bounds come from measured audio; phrase timing is explicitly approximate.
    phrases = textwrap.wrap(text, width=38, break_long_words=False) or [text]
    cues = [
        CaptionCue(i * duration / len(phrases), (i + 1) * duration / len(phrases), phrase)
        for i, phrase in enumerate(phrases)
    ]
    cues = aligned_cues or cues
    captions = output.with_suffix(".ass")
    captions.write_text(
        serialize_ass(
            cues,
            CaptionConfig(
                font_family=font,
                font_size={"bold": 58, "minimal": 36}.get(caption_style, 48),
                animation="none" if caption_style == "minimal" else "pop",
                highlight_color=accent,
                position="bottom",
            ),
        )
    )
    pending = output.with_name(output.stem + ".pending.mp4")
    background = {"explainer": "0x182118", "timeline": "0x281B14"}.get(style, "0x101827")
    args = [require_tool("ffmpeg"), "-v", "error", "-nostdin", "-y"]
    if asset:
        args += ["-stream_loop", "-1"] if recording else ["-loop", "1"]
        args += ["-i", str(asset)]
    else:
        args += [
            "-f",
            "lavfi",
            "-i",
            f"color=c={background}:s=1080x1920:r={frame_rate}",
        ]
        card = output.with_suffix(".card.ass")
        # Cards are explicitly identified explanatory graphics, not evidence screenshots.
        card.write_text(
            serialize_ass(
                [
                    CaptionCue(
                        0, duration, " ".join(textwrap.wrap(heading, width=22)) + " — Explanation"
                    )
                ],
                CaptionConfig(font_family=font, font_size=64, position="middle"),
            )
        )
    args += ["-i", str(audio)]
    filters = [
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x101827",
        "setsar=1",
    ]
    if motion and asset and not recording:
        filters.append(
            "zoompan=z='min(1.025,1+on*0.00008)':x='iw/2-iw/zoom/2':"
            f"y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps={frame_rate}"
        )
    if not asset:
        filters.append(f"ass={_filter_path(card)}")
    if attribution:
        credit = output.with_suffix(".credits.ass")
        credit.write_text(
            serialize_ass(
                [CaptionCue(0, duration, attribution[:500])],
                CaptionConfig(font_family=font, font_size=28, position="top", animation="none"),
            )
        )
        filters.append(f"ass={_filter_path(credit)}")
    fonts = Path(__file__).parent / "fonts"
    filters.append(f"ass={_filter_path(captions)}:fontsdir={_filter_path(fonts)}")
    args += [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        ",".join(filters),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11" if normalize_audio else "anull",
        "-t",
        str(duration),
        "-r",
        str(frame_rate),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(pending),
    ]
    _run(args)
    pending.replace(output)
    return output


def _filter_path(path: Path) -> str:
    return "'" + str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''") + "'"


def assemble_sections(scenes: list[Path], output: Path) -> Path:
    pending = output.with_name(output.stem + ".pending.mp4")
    args = [require_tool("ffmpeg"), "-v", "error", "-nostdin", "-y"]
    for scene in scenes:
        args += ["-i", str(scene)]
    inputs = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(scenes)))
    args += [
        "-filter_complex",
        inputs + f"concat=n={len(scenes)}:v=1:a=1[v][a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(pending),
    ]
    _run(args)
    pending.replace(output)
    return output


def inspect_render(
    path: Path, expected_duration: float, *, require_audio: bool = True
) -> list[dict[str, Any]]:
    """Decode the rendered file and measure audio; never claim semantic visual review."""
    findings: list[dict[str, Any]] = []
    try:
        payload = media_metadata(path)
    except MediaError:
        return [
            {
                "severity": "error",
                "code": "invalid_output",
                "start": 0,
                "message": "Rendered output cannot be read",
                "basis": "rendered_media",
            }
        ]
    video: dict[str, Any] = next((s for s in payload["streams"] if s["codec_type"] == "video"), {})
    audio: dict[str, Any] = next((s for s in payload["streams"] if s["codec_type"] == "audio"), {})
    if (
        not video
        or (require_audio and not audio)
        or video.get("width", 0) * 16 != video.get("height", 0) * 9
    ):
        findings.append(
            {
                "severity": "error",
                "code": "output_streams",
                "start": 0,
                "message": "Expected 9:16 video and audio",
                "basis": "rendered_metadata",
            }
        )
    duration = float(payload["format"]["duration"])
    if abs(duration - expected_duration) > 0.5:
        findings.append(
            {
                "severity": "error",
                "code": "duration",
                "start": 0,
                "message": "Output duration differs from narration",
                "basis": "rendered_metadata",
            }
        )
    decoded = subprocess.run(
        [
            require_tool("ffmpeg"),
            "-v",
            "info",
            "-nostdin",
            "-xerror",
            "-i",
            str(path),
            "-af",
            "volumedetect,silencedetect=n=-45dB:d=2",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if decoded.returncode:
        findings.append(
            {
                "severity": "error",
                "code": "decode",
                "start": 0,
                "message": "Rendered media failed full decode",
                "basis": "rendered_media",
            }
        )
    for silence in re.finditer(r"silence_start: ([0-9.]+)", decoded.stderr):
        findings.append(
            {
                "severity": "warning",
                "code": "silence",
                "start": float(silence[1]),
                "message": "At least two seconds of silence; listen before approval",
                "basis": "rendered_audio",
            }
        )
    return findings
