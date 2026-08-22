import io
from pathlib import Path

import pytest

from clipper.services.media import MediaError, safe_filename, store_upload


def test_filename_drops_traversal() -> None:
    assert safe_filename("../../private/evil name.mp4") == "evil_name.mp4"
    assert safe_filename("..\\..\\evil.mkv") == "evil.mkv"


def test_upload_rejects_bad_signature_and_cleans_up(tmp_path: Path) -> None:
    target = tmp_path / "project" / "payload.mp4"
    with pytest.raises(MediaError, match="signature"):
        store_upload(io.BytesIO(b"not a video"), target, 100)
    assert not target.exists()


def test_upload_enforces_streaming_limit(tmp_path: Path) -> None:
    target = tmp_path / "project" / "payload.mp4"
    with pytest.raises(MediaError, match="exceeds"):
        store_upload(io.BytesIO(b"\x00\x00\x00\x18ftypisom" + b"x" * 100), target, 20)
