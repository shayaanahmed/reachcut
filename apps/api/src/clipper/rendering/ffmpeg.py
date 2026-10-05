from dataclasses import dataclass
from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1
from clipper.rendering.framing import build_video_filter


@dataclass(frozen=True)
class FfmpegCommand:
    """An executable argument vector and its stable render metadata."""

    arguments: tuple[str, ...]
    width: int
    height: int
    duration_seconds: float


def build_ffmpeg_command(
    executable: str,
    source: Path,
    plan: EditingPlanV1,
    subtitles: Path,
    output: Path,
    *,
    preview: bool,
) -> FfmpegCommand:
    """Build a shell-free FFmpeg command without running a process."""

    width, height = (360, 640) if preview else (1080, 1920)
    duration = plan.source.end_seconds - plan.source.start_seconds
    video_filter = build_video_filter(plan, subtitles, width, height)
    arguments = (
        executable,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-ss",
        f"{plan.source.start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-filter_complex",
        video_filter,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.2",
        "-tag:v",
        "avc1",
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
    )
    return FfmpegCommand(arguments, width, height, duration)
