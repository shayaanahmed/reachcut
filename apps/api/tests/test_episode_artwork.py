"""Native Ollama images and reusable, source-grounded everyday explanations."""

import base64
import io
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image
from retired_style_fixtures import starter_styles

from clipper.providers.ollama_images import OllamaImageProvider
from clipper.rendering.episode_art import render_episode_art
from clipper.shorts.series import (
    ContentSeries,
    SeriesConfig,
)


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (768, 1360), "#347868").save(buffer, format="PNG")
    return buffer.getvalue()


def test_native_images_stream_verify_cache_and_keep_provenance(tmp_path: Path) -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        payload = json.loads(request.content)
        if request.url.path == "/api/show":
            assert payload["model"] == "local-image-model"
            return httpx.Response(200, json={"capabilities": ["image"]})
        assert payload["prompt"] == "A concrete everyday situation"
        assert payload["stream"] and payload["width"] == 768
        return httpx.Response(
            200,
            text=json.dumps({"completed": 1, "total": 4})
            + "\n"
            + json.dumps({"done": True, "image": base64.b64encode(image_bytes()).decode()}),
        )

    provider = OllamaImageProvider("http://ollama", transport=httpx.MockTransport(respond))
    output = tmp_path / "scene.png"
    for _ in range(2):
        assert (
            provider.generate(
                "local-image-model", "A concrete everyday situation", output, lambda: False
            )
            == output
        )
    assert requests == ["/api/show", "/api/generate"]
    assert Image.open(output).size == (768, 1360)
    provenance = json.loads(output.with_suffix(".json").read_text())
    assert provenance["model"] == "local-image-model" and provenance["illustrative"]
    assert "image" not in provenance


@pytest.mark.parametrize("failure", ["vision", "missing", "no_image", "corrupt", "error"])
def test_native_images_report_actionable_errors_and_leave_no_cached_image(
    tmp_path: Path,
    failure: str,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(
                404 if failure == "missing" else 200,
                json={"capabilities": ["vision" if failure == "vision" else "image"]},
            )
        payload = {"done": True}
        if failure == "corrupt":
            payload["image"] = "invalid-base64"
        if failure == "error":
            payload["error"] = "Model memory exhausted"
        return httpx.Response(200, text=json.dumps(payload))

    provider = OllamaImageProvider("http://ollama", transport=httpx.MockTransport(respond))
    with pytest.raises(ValueError):
        provider.generate("test-model", "prompt", tmp_path / "scene.png", lambda: False)
    assert not list(tmp_path.glob("*.png"))


def test_cancelled_image_does_not_submit_to_ollama(tmp_path: Path) -> None:
    transport = Mock(side_effect=AssertionError("Cancelled work must not call Ollama"))
    provider = OllamaImageProvider("http://ollama", transport=httpx.MockTransport(transport))
    with pytest.raises(InterruptedError):
        provider.generate("image", "prompt", tmp_path / "scene.png", lambda: True)
    assert not transport.called


@pytest.mark.parametrize(
    "family", ["Bricolage Grotesque", "Anton", "Space Grotesk", "Syne", "Fraunces"]
)
def test_all_selectable_fonts_render_with_bundled_files(tmp_path: Path, family: str) -> None:
    from clipper.shorts.series import EpisodeVisual

    series = ContentSeries(
        **SeriesConfig(
            name="Everyday discoveries",
            purpose="Explain useful ideas clearly",
            headline_font=family,
        ).model_dump(),
        styles=starter_styles(),
    )
    visual = EpisodeVisual(
        section_id="hook",
        kind="illustration",
        role="hook",
        heading="Your next idea starts here",
        body="Make something useful.",
    )
    path = render_episode_art(series, visual, tmp_path / "font.png")
    assert Image.open(path).size == (1080, 1920)
