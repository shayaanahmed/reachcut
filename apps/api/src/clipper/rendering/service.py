import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1
from clipper.media import MediaError, require_tool
from clipper.rendering.ffmpeg import build_ffmpeg_command

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RenderRequest:
    source: Path
    plan: EditingPlanV1
    subtitles: Path
    output: Path
    preview: bool = True


class VideoRenderer:
    """Public rendering service; process execution is replaceable in tests."""

    def __init__(self, runner: ProcessRunner = subprocess.run) -> None:
        self._runner = runner

    def render(self, request: RenderRequest) -> dict[str, object]:
        request.output.parent.mkdir(parents=True, exist_ok=True)
        command = build_ffmpeg_command(
            require_tool("ffmpeg"),
            request.source,
            request.plan,
            request.subtitles,
            request.output,
            preview=request.preview,
        )
        result = self._runner(
            list(command.arguments),
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,
        )
        if result.returncode != 0:
            raise MediaError(f"FFmpeg render failed: {result.stderr[-1000:]}")
        manifest = self._manifest(request, command.arguments, command.width, command.height)
        request.output.with_suffix(".manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        return manifest

    @staticmethod
    def _manifest(
        request: RenderRequest, arguments: Sequence[str], width: int, height: int
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "output": request.output.name,
            "source_start_seconds": request.plan.source.start_seconds,
            "source_end_seconds": request.plan.source.end_seconds,
            "dimensions": {"width": width, "height": height},
            "frame_style": request.plan.frame_style,
            "video_codec": "libx264",
            "audio_codec": "aac",
            "command": ["<ffmpeg>", *arguments[1:-1], request.output.name],
        }
