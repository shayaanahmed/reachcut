import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from clipper.media.errors import MediaError

ALLOWED_SIGNATURES = {
    b"\x00\x00\x00": "iso-bmff",
    b"\x1aE\xdf\xa3": "matroska",
    b"RIFF": "riff",
    b"OggS": "ogg",
}


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


def inspect_stored_media(path: Path, max_bytes: int) -> StoredUpload:
    """Validate and fingerprint media written by an external ingestion adapter."""

    size = path.stat().st_size
    if size > max_bytes:
        raise MediaError(f"download exceeds {max_bytes} byte limit")
    digest = hashlib.sha256()
    header = b""
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            if len(header) < 16:
                header += chunk[: 16 - len(header)]
            digest.update(chunk)
    detect_container(header)
    return StoredUpload(path=path, sha256=digest.hexdigest(), bytes_written=size)
