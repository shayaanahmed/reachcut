from __future__ import annotations

import json
import subprocess
from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1
from clipper.services.media import MediaError, require_tool


def render_vertical(
    source: Path, plan: EditingPlanV1, subtitles: Path, output: Path, preview: bool = True
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = (360, 640) if preview else (1080, 1920)
    duration = plan.source.end_seconds - plan.source.start_seconds
    escaped_subtitles = str(subtitles).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"subtitles='{escaped_subtitles}':force_style='Alignment=2,MarginV=120,FontSize=18,"
        "Outline=2,PrimaryColour=&H00FFFFFF'"
    )
    command = [
        require_tool("ffmpeg"),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-ss",
        f"{plan.source.start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "25" if preview else "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=3600)
    if result.returncode != 0:
        raise MediaError(f"FFmpeg render failed: {result.stderr[-1000:]}")
    manifest = {
        "schema_version": "1.0",
        "output": output.name,
        "source_start_seconds": plan.source.start_seconds,
        "source_end_seconds": plan.source.end_seconds,
        "dimensions": {"width": width, "height": height},
        "video_codec": "libx264",
        "audio_codec": "aac",
        "command": ["<ffmpeg>", *command[1:-1], output.name],
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
