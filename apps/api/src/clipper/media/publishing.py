import shutil
import subprocess
from pathlib import Path

from clipper.media.errors import MediaError
from clipper.media.tools import require_tool


def prepare_full_video(source: Path, final: Path) -> None:
    """Keep an MP4 master as-is, or convert another container without cropping or trimming."""
    final.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".mp4":
        shutil.copy2(source, final)
        return
    result = subprocess.run(
        [
            require_tool("ffmpeg"),
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(final),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=3600,
    )
    if result.returncode:
        raise MediaError(f"Could not prepare full video: {result.stderr[-1000:]}")
