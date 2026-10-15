from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from clipper.media.tools import require_tool


def valid_generated_video(
    video: Path,
    expected_duration: float | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    tool_locator: Callable[[str], str] = require_tool,
) -> bool:
    """Check the container, required streams, duration, and full media decoding."""
    if not video.is_file() or video.stat().st_size == 0:
        return False
    probe = runner(
        [
            tool_locator("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type:format=duration",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if probe.returncode:
        return False
    try:
        metadata = json.loads(probe.stdout)
        duration = float(metadata["format"]["duration"])
        streams = {item["codec_type"] for item in metadata["streams"]}
    except (ValueError, KeyError, TypeError):
        return False
    if not {"video", "audio"}.issubset(streams) or duration <= 0:
        return False
    if expected_duration is not None and abs(duration - expected_duration) > 0.25:
        return False
    decode = runner(
        [
            tool_locator("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-xerror",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return decode.returncode == 0
