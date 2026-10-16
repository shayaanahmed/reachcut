from __future__ import annotations

import subprocess
from pathlib import Path

from clipper.media.errors import MediaError
from clipper.media.tools import require_tool


def encode_instagram_video(source: Path, output: Path) -> None:
    """Make a conservative H.264/AAC copy for Reels rejected by Meta's uploader."""
    command = [
        require_tool("ffmpeg"),
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-vf",
        "scale=720:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        "fps=30,setsar=1,setpts=PTS-STARTPTS",
        "-c:v",
        "libx264",
        "-threads",
        "2",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-profile:v",
        "baseline",
        "-level:v",
        "3.1",
        "-pix_fmt",
        "yuv420p",
        "-bf",
        "0",
        "-g",
        "60",
        "-sc_threshold",
        "0",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-af",
        "aresample=async=1:first_pts=0",
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
        "-use_editlist",
        "0",
        str(output),
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError("Could not prepare the Instagram compatibility video") from error
    if result.returncode or not output.is_file() or output.stat().st_size == 0:
        raise MediaError(f"Instagram compatibility encoding failed: {result.stderr[-500:]}")
