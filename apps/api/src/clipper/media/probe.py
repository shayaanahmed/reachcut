import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clipper.media.errors import MediaError
from clipper.media.tools import require_tool

ProbeRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float
    payload: dict[str, object]

    def as_artifact(self) -> dict[str, object]:
        streams = self.payload.get("streams", [])
        streams = streams if isinstance(streams, list) else []
        video = next(
            (s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), {}
        )
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        return {
            "duration_seconds": self.duration_seconds,
            "probe": self.payload,
            "inspection_version": "1",
            "width": width,
            "height": height,
            "orientation": "portrait" if height > width else "landscape",
            "has_audio": any(
                isinstance(s, dict) and s.get("codec_type") == "audio" for s in streams
            ),
        }


class MediaProbe:
    """Validate media metadata while isolating ffprobe process execution."""

    def __init__(self, runner: ProbeRunner = subprocess.run) -> None:
        self._runner = runner

    def inspect(self, path: Path, max_duration_seconds: float) -> ProbeResult:
        command = [
            require_tool("ffprobe"),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ]
        try:
            result = self._runner(command, check=False, capture_output=True, text=True, timeout=120)
        except OSError:
            from clipper.media.metadata import media_metadata

            fallback_payload = media_metadata(path)
            result = subprocess.CompletedProcess(command, 0, json.dumps(fallback_payload), "")
        if result.returncode != 0:
            raise MediaError(f"ffprobe rejected media: {result.stderr[-500:]}")
        payload: dict[str, object] = json.loads(result.stdout)
        raw_format = payload.get("format", {})
        media_format = raw_format if isinstance(raw_format, dict) else {}
        duration = float(media_format.get("duration", 0))
        if duration <= 0 or duration > max_duration_seconds:
            raise MediaError(f"media duration must be between 0 and {max_duration_seconds} seconds")
        raw_streams = payload.get("streams", [])
        streams = raw_streams if isinstance(raw_streams, list) else []
        if not any(
            isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
        ):
            raise MediaError("media has no video stream")
        return ProbeResult(duration, payload)


def probe_media(path: Path, max_duration_seconds: float) -> dict[str, object]:
    """Compatibility function returning the existing artifact shape."""

    return MediaProbe().inspect(path, max_duration_seconds).as_artifact()
