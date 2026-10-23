"""HTML imports preserve scene data, survive restarts and reject executable input."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clipper.config import settings
from clipper.main import app
from clipper.projects.frame_import import import_frame_html
from clipper.rendering.html_frames import ROOT, frame_document
from clipper.shorts.frame_import import parse_frame_html
from clipper.shorts.frames import design_catalogue, frame_library, frame_sequences


def document(*, name: str = "A new collection", markup: str = "<div>Sample claim</div>") -> str:
    template = dict(
        name=name,
        s="--bg:#fff;--fg:#111",
        desc="A complete story",
        scenes=[
            dict(n=f"Scene {i}", d=4.5, c="A [caption]", v="Sample narration", g=markup)
            for i in range(5)
        ],
    )
    return (
        f"<style>.st{{position:relative}}</style><script>const T={json.dumps([template])};</script>"
    )


@pytest.fixture(autouse=True)
def isolated_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def test_supplied_sequences_replace_the_old_active_catalogue() -> None:
    parsed = parse_frame_html((ROOT / "full-sequences.html").read_text())
    assert len(frame_library()) == len(parsed["frames"]) == 25
    assert len(frame_sequences()) == len(parsed["sequences"]) == 5
    assert {f.id for f in frame_library()} == {f["id"] for f in parsed["frames"]}
    assert not {"kinetic-poster", "before-after", "shortcut-keycaps"} & {
        f.id for f in frame_library()
    }
    assert [s.durations for s in frame_sequences()] == [s["durations"] for s in parsed["sequences"]]
    assert "how are you building" in parsed["frames"][0]["markup"]


def test_upload_persists_and_reimport_does_not_duplicate() -> None:
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(
                "/api/short-studio/frames/import",
                files={"file": ("frames.html", document().encode(), "text/html")},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"frames": 5, "sequences": 1}
        frames = client.get("/api/short-studio/frames").json()
        assert len(frames) == 30
        sequence = client.get("/api/short-studio/sequences").json()[-1]
        player = client.get(
            f"/api/short-studio/frames/{sequence['frames'][0]}/player",
            params={"sequence_id": sequence["id"]},
        )
        assert player.status_code == 200
        assert "Sample claim" in player.text
        assert "default-src 'none'" in player.headers["content-security-policy"]
    # Read from disk again, as a new API process does, without a process-local cache.
    saved = json.loads((settings.data_dir / "frame-library.json").read_text())
    assert len(saved["frames"]) == 5
    assert len(design_catalogue()) == 30


@pytest.mark.parametrize(
    "source",
    [
        "<html>No frame data</html>",
        "<style>.st{}</style><script>const T=[doSomething()];</script>",
        document(markup='<div onclick="alert(1)">Click</div>'),
        document(markup="<script>alert(1)</script>"),
        document(markup='<img src="https://example.com/track">'),
        document().replace(".st{position:relative}", '@import "https://example.com/x.css";'),
        document().replace('"<div>Sample claim</div>"', "`<div>${runCode()}</div>`"),
    ],
)
def test_invalid_import_leaves_existing_library_unchanged(source: str) -> None:
    import_frame_html(document())
    before = (settings.data_dir / "frame-library.json").read_bytes()
    with TestClient(app) as client:
        response = client.post(
            "/api/short-studio/frames/import",
            files={"file": ("bad.html", source.encode(), "text/html")},
        )
    assert response.status_code == 422, response.text
    assert (settings.data_dir / "frame-library.json").read_bytes() == before


def test_upload_limits_and_utf8_errors() -> None:
    with TestClient(app) as client:
        for filename, raw in [
            ("bad.txt", b"x"),
            ("bad.html", b"\xff"),
            ("big.html", b"x" * (2 * 1024 * 1024 + 1)),
        ]:
            response = client.post(
                "/api/short-studio/frames/import", files={"file": (filename, raw, "text/html")}
            )
            assert response.status_code == 422
    assert len(frame_library()) == 25


def test_changed_css_has_a_new_identity_and_uses_imported_bindings() -> None:
    source = document()
    first = parse_frame_html(source)
    second = parse_frame_html(source.replace("position:relative", "position:absolute"))
    assert first["frames"][0]["id"] != second["frames"][0]["id"]
    import_frame_html(source)
    frame = frame_library()[-5]
    page = frame_document(frame.sample, frame_sequences()[-1])
    assert "data-copy" in page
    assert ".st{position:relative}" in page


def test_chat_copy_grows_beyond_the_reference_typing_indicator() -> None:
    from clipper.rendering.html_frames import HTMLFramePainter

    sequence = frame_sequences()[0]
    frame = next(f for f in frame_library() if f.id == sequence.frames[0]).sample.model_copy(
        update={"title": "Read Web Pages", "eyebrow": "No Login Needed"}
    )
    with HTMLFramePainter(frame, sequence) as painter:
        assert painter.issues() == []
        bubble_width = (
            painter.page.locator(".bb")
            .nth(1)
            .evaluate("(node) => node.getBoundingClientRect().width")
        )
        assert bubble_width > 100


def test_repository_card_separates_replaced_owner_and_repository_labels() -> None:
    from clipper.rendering.html_frames import HTMLFramePainter

    sequence = frame_sequences()[0]
    frame = next(f for f in frame_library() if f.id == sequence.frames[1]).sample.model_copy(
        update={"title": "Agent-Reach", "eyebrow": "Access Web Content"}
    )
    with HTMLFramePainter(frame, sequence) as painter:
        assert painter.issues() == []
        separated = painter.page.locator(".card .mono").evaluate("""node => {
          const a=node.children[0].getBoundingClientRect();
          const b=node.children[1].getBoundingClientRect();
          return b.left > a.right+1 || b.top >= a.bottom;
        }""")
        assert separated
