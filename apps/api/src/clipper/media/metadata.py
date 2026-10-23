"""Read media metadata with ffprobe, with PyAV for incompatible bundled binaries."""

import json
import subprocess
from pathlib import Path
from typing import Any

from clipper.media.errors import MediaError
from clipper.media.tools import require_tool


def media_metadata(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                require_tool("ffprobe"),
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, MediaError):
        return _pyav_metadata(path)
    if result.returncode:
        raise MediaError("Media metadata cannot be read: " + result.stderr[-300:])
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def _pyav_metadata(path: Path) -> dict[str, Any]:
    # PyAV is already required by faster-whisper. It reads the same container
    # fields; this is metadata inspection, not a successful full decode.
    import av

    try:
        with av.open(str(path)) as container:
            streams = []
            for stream in container.streams:
                info: dict[str, Any] = {"codec_type": stream.type, "index": stream.index}
                if stream.type == "video":
                    info.update(
                        width=getattr(stream.codec_context, "width", 0),
                        height=getattr(stream.codec_context, "height", 0),
                    )
                streams.append(info)
            return {
                "format": {"duration": float(container.duration or 0) / av.time_base},
                "streams": streams,
                "measurement_provider": "pyav",
            }
    except Exception as error:
        raise MediaError("Media metadata cannot be read with PyAV") from error
