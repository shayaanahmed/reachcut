import base64
import json
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from clipper.api import template_library as routes
from clipper.api import video_generation
from clipper.generation.reference_templates import ReferenceTemplate, TemplateBlueprint
from clipper.main import app
from clipper.media import MediaError
from clipper.media.template_frames import sample_template_frames
from clipper.projects.template_library import TemplateLibrary
from clipper.providers.ollama_story import OllamaStoryDirector
from clipper.providers.ollama_templates import OllamaTemplateClassifier, match_template


def blueprint() -> TemplateBlueprint:
    return TemplateBlueprint(
        name="Doorbell surprise",
        base_template="documentary_realism",
        format="Doorbell camera",
        tags=["doorbell", "comedy", "animals"],
        visual_style="Photorealistic infrared nighttime doorbell camera footage",
        camera="Fixed wide angle camera at the front door",
        pacing="One continuous action; timing inferred from sampled frames",
        story_structure="Animal approaches, steals a snack, then reacts to being discovered",
        caption_style="No visible captions",
        suitable_for="Unexpected visitors and animal comedy with a surprise payoff",
    )


@pytest.fixture
def video_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "fixture.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 8, (128, 128))
    assert writer.isOpened()
    for index in range(16):
        writer.write(np.full((128, 128, 3), index * 12, dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def test_gallery_includes_all_four_user_references(tmp_path: Path) -> None:
    items = TemplateLibrary(tmp_path).list()
    assert len(items) == 346
    assert len({item.id for item in items}) == len(items)
    for suffix in ("15fd63fbf6", "48fd4d0dfc", "397bbab206", "ed9c6312ea"):
        assert any(
            item.source_url and f"shorts-{suffix}-min.mp4" in item.source_url for item in items
        )
    assert all(item.status == "pending" and item.blueprint is None for item in items)


def test_frames_are_chronological_and_duration_is_measured(
    tmp_path: Path, video_bytes: bytes
) -> None:
    path = tmp_path / "sample.mp4"
    path.write_bytes(video_bytes)
    frames, duration = sample_template_frames(path)
    assert len(frames) == 8
    assert duration == 2
    brightness = [float(cv2.imdecode(np.frombuffer(frame, np.uint8), 1).mean()) for frame in frames]
    assert brightness == sorted(brightness)


def test_classification_is_durable_and_retryable(
    tmp_path: Path, video_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = TemplateLibrary(tmp_path / "library")
    item = library.upload(video_bytes, "My animal clip")
    classifier = OllamaTemplateClassifier("http://ollama", "vision")

    def fail(*_: object) -> TemplateBlueprint:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(classifier, "classify", fail)
    failed = library.classify(item.id, classifier)
    assert failed.status == "failed"
    assert library.video_path(item.id).read_bytes() == video_bytes
    with pytest.raises(MediaError, match="Classify"):
        library.guidance(item.id)
    monkeypatch.setattr(classifier, "classify", lambda *_: blueprint())
    ready = library.classify(item.id, classifier)
    restored = TemplateLibrary(library.root).get(item.id)
    assert ready.status == restored.status == "ready"
    assert restored.analysis_model == "vision"
    assert restored.blueprint == blueprint()
    assert json.loads(library.guidance(item.id))["format"] == "Doorbell camera"


def test_import_rejects_unapproved_hosts_and_paths(tmp_path: Path) -> None:
    library = TemplateLibrary(tmp_path)
    for url in [
        "https://127.0.0.1/internal.mp4",
        "https://media.viewmax.io.evil.example/static/prompt-library/shorts/a.mp4",
        "https://media.viewmax.io/users/private.mp4",
    ]:
        with pytest.raises(MediaError, match="Viewmax"):
            library.import_source(url, "Bad URL")
    with pytest.raises(MediaError, match="Invalid template"):
        library.video_path("../../etc/passwd")
    with pytest.raises(MediaError, match="valid MP4"):
        library.upload(b"not video", "Bad upload")


def test_classifier_sends_images_and_validates_blueprint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"message": {"content": blueprint().model_dump_json()}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    result = OllamaTemplateClassifier("http://ollama", "vision").classify([b"frame"], 8)
    assert result.format == "Doorbell camera"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "vision"
    assert payload["messages"][0]["images"] == [base64.b64encode(b"frame").decode()]


def test_matching_only_considers_ready_templates_and_rejects_unknown_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    director = OllamaStoryDirector("http://ollama", "text")
    ready = ReferenceTemplate(id="a" * 32, name="Ready", status="ready", blueprint=blueprint())
    pending = ReferenceTemplate(id="b" * 32, name="Pending")
    prompts: list[str] = []

    def choose(prompt: str, _: object) -> dict[str, str]:
        prompts.append(prompt)
        return {
            "template_id": ready.id,
            "reason": "Animal comedy fits the doorbell surprise format",
        }

    monkeypatch.setattr(director, "_generate", choose)
    assert (
        match_template(director, "A raccoon steals pizza", [pending, ready]).template_id == ready.id
    )
    assert pending.id not in prompts[0]
    assert len(prompts) == 1
    monkeypatch.setattr(
        director,
        "_generate",
        lambda *_: {
            "template_id": pending.id,
            "reason": "An unavailable template was selected",
        },
    )
    with pytest.raises(ValueError, match="outside"):
        match_template(director, "Animal comedy", [pending, ready])
    with pytest.raises(ValueError, match="at least one"):
        match_template(director, "Animal comedy", [pending])


def test_library_routes_upload_classify_preview_and_pass_guidance_to_planner(
    tmp_path: Path,
    video_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = TemplateLibrary(tmp_path / "library")
    monkeypatch.setattr(routes, "library", library)
    monkeypatch.setattr(video_generation, "template_library", library)
    monkeypatch.setattr(OllamaTemplateClassifier, "classify", lambda *_: blueprint())
    with TestClient(app) as client:
        response = client.post(
            "/api/video-generation/template-library/upload",
            files={"video": ("animal.mp4", video_bytes, "video/mp4")},
        )
        assert response.status_code == 200
        item = response.json()
        before = client.post(
            "/api/video-generation/plan",
            json={
                "story": "A raccoon is caught stealing pizza from a porch.",
                "reference_template_id": item["id"],
            },
        )
        assert before.status_code == 422
        result = client.post(f"/api/video-generation/template-library/{item['id']}/classify")
        assert result.json()["status"] == "ready"
        preview = client.get(result.json()["video_url"])
        assert preview.content == video_bytes
        poster = client.get(result.json()["poster_url"])
        assert poster.status_code == 200
        assert poster.headers["content-type"] == "image/jpeg"
        requests = []

        def plan(_: object, request: object) -> object:
            requests.append(request)
            raise ValueError("Stop before rendering")

        monkeypatch.setattr(OllamaStoryDirector, "plan", plan)
        client.post(
            "/api/video-generation/plan",
            json={
                "story": "A raccoon is caught stealing pizza from a porch.",
                "reference_template_id": item["id"],
            },
        )
        assert json.loads(requests[0].template_guidance)["camera"] == blueprint().camera


def test_classifier_repairs_invalid_model_output_once(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, object]] = []

    def post(url: str, **kwargs: object) -> httpx.Response:
        payload = kwargs["json"]
        assert isinstance(payload, dict)
        requests.append(payload)
        result = blueprint().model_dump()
        if len(requests) == 1:
            result["camera"] = ""
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(result)}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    assert (
        OllamaTemplateClassifier("http://ollama", "vision").classify([b"frame"], 8) == blueprint()
    )
    assert len(requests) == 2
    assert "Retry invalid fields: camera" in requests[1]["messages"][0]["content"]  # type: ignore[index]


def test_large_library_compares_batch_winners_and_bounds_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    director = OllamaStoryDirector("http://ollama", "text")
    items = [
        ReferenceTemplate(
            id=f"{index:032x}", name=f"Clip {index}", status="ready", blueprint=blueprint()
        )
        for index in range(41)
    ]
    sizes: list[int] = []

    def choose(prompt: str, _: object) -> dict[str, str]:
        candidates = json.loads(prompt.split("CATALOGUE: ", 1)[1])
        sizes.append(len(candidates))
        return {"template_id": max(item["id"] for item in candidates), "reason": "Relevant " * 100}

    monkeypatch.setattr(director, "_generate", choose)
    result = match_template(director, "Animal comedy", items)
    assert result.template_id == items[-1].id
    assert len(result.reason) <= 500
    assert sizes == [20, 20, 1, 3]
