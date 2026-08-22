from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

ALLOWED_SIGNATURES = {
    b"\x00\x00\x00": "iso-bmff",
    b"\x1aE\xdf\xa3": "matroska",
    b"RIFF": "riff",
    b"OggS": "ogg",
}


class MediaError(ValueError):
    pass


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    sha256: str
    bytes_written: int


def safe_filename(name: str) -> str:
    leaf = Path(name.replace("\\", "/")).name
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", leaf).strip("._")
    return normalized[:180] or "source.mp4"


def detect_container(header: bytes) -> str:
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "iso-bmff"
    for signature, container in ALLOWED_SIGNATURES.items():
        if header.startswith(signature) and signature != b"\x00\x00\x00":
            return container
    raise MediaError("unsupported or invalid media file signature")


def store_upload(stream: BinaryIO, target: Path, max_bytes: int) -> StoredUpload:
    target.parent.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    total = 0
    header = b""
    try:
        with target.open("xb") as output:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise MediaError(f"upload exceeds {max_bytes} byte limit")
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                digest.update(chunk)
                output.write(chunk)
        detect_container(header)
    except Exception:
        target.unlink(missing_ok=True)
        if target.parent.exists():
            shutil.rmtree(target.parent)
        raise
    return StoredUpload(path=target, sha256=digest.hexdigest(), bytes_written=total)


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise MediaError(f"{name} is required but was not found on PATH; run pnpm doctor")
    return executable


def probe_media(path: Path, max_duration_seconds: float) -> dict[str, object]:
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
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise MediaError(f"ffprobe rejected media: {result.stderr[-500:]}")
    payload = json.loads(result.stdout)
    duration = float(payload.get("format", {}).get("duration", 0))
    if duration <= 0 or duration > max_duration_seconds:
        raise MediaError(f"media duration must be between 0 and {max_duration_seconds} seconds")
    if not any(stream.get("codec_type") == "video" for stream in payload.get("streams", [])):
        raise MediaError("media has no video stream")
    return {"duration_seconds": duration, "probe": payload}
