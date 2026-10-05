import io
from pathlib import Path

import pytest

from clipper.media import MediaError, safe_filename, store_upload, validate_public_media_url


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


def test_url_import_accepts_allowlisted_public_hosts() -> None:
    def resolve(*_: object) -> list[tuple[object, ...]]:
        return [(2, 1, 6, "", ("142.250.185.206", 443))]

    assert (
        validate_public_media_url(
            " https://www.youtube.com/watch?v=abc#fragment ",
            ("youtube.com",),
            resolve,
        )
        == "https://www.youtube.com/watch?v=abc"
    )


@pytest.mark.parametrize(
    ("url", "address"),
    [
        ("https://youtube.com.attacker.example/video", "142.250.185.206"),
        ("https://youtube.com/video", "127.0.0.1"),
    ],
)
def test_url_import_rejects_untrusted_or_private_targets(url: str, address: str) -> None:
    def resolve(*_: object) -> list[tuple[object, ...]]:
        return [(2, 1, 6, "", (address, 443))]

    with pytest.raises(MediaError):
        validate_public_media_url(url, ("youtube.com",), resolve)
