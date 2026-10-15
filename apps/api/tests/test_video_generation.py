import json
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from clipper.generation import SceneGenerationRequest, StoryPlan
from clipper.main import app
from clipper.media import MediaError
from clipper.providers.ltx_desktop import LtxDesktopVideoProvider, dimensions_for
from clipper.rendering.story_video import StoryVideoFinisher


def sample_plan() -> dict[str, object]:
    return {
        "title": "The clockwork bird",
        "logline": "A clockmaker uses a tiny rewind to recover a child's photograph.",
        "visual_style": "cinematic animated feature with expressive characters",
        "negative_prompt": "identity drift, wardrobe changes, flicker, text, logos, anatomy errors",
        "characters": [
            {
                "id": "mara",
                "name": "Mara",
                "role": "clockmaker",
                "appearance_anchor": (
                    "young adult with an oval face, brown eyes, and short black curls"
                ),
                "wardrobe_anchor": "mustard coat, navy trousers, brown leather boots",
                "voice_anchor": "warm, quiet alto with deliberate pacing",
            }
        ],
        "scenes": [
            {
                "index": 1,
                "title": "Discovery",
                "story_beat": "Mara discovers the mechanical bird in her workshop.",
                "narration": "Some seconds ask to be lived twice.",
                "visual_prompt": (
                    "Mara lifts a tiny brass bird from a ticking workbench while dawn "
                    "enters the room."
                ),
                "character_ids": ["mara"],
                "camera_motion": "dolly_in",
                "duration_seconds": 5,
                "seed": 4201,
            }
        ],
    }


def test_storyboard_rejects_scene_character_missing_from_bible() -> None:
    payload = sample_plan()
    payload["scenes"][0]["character_ids"] = ["stranger"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown characters"):
        StoryPlan.model_validate(payload)


def test_local_dimensions_keep_portrait_final_at_1080p() -> None:
    assert dimensions_for("9:16", "1080p") == (1080, 1920)
    assert dimensions_for("16:9", "draft") == (960, 544)


def test_ltx_provider_bridges_engine_paths_across_docker(tmp_path: Path) -> None:
    shared = tmp_path / "container-data"
    shared.mkdir()
    remote = Path("/host/project/ltx-data")
    (shared / "reachcut-engine.json").write_text(
        json.dumps({"data_dir": str(remote)}), encoding="utf-8"
    )
    engine_output = shared / "outputs" / "scene.mp4"
    engine_output.parent.mkdir()
    engine_output.write_bytes(b"video")
    provider = LtxDesktopVideoProvider("http://engine", data_dir=shared)

    assert provider._resolve_engine_path(str(remote / "outputs" / "scene.mp4")) == engine_output

    reference = tmp_path / "reference.png"
    reference.write_bytes(b"image")
    staged = provider._stage_input(reference)
    assert staged is not None
    assert staged.parent == remote / "reachcut-inputs"
    assert (shared / staged.relative_to(remote)).read_bytes() == b"image"


def test_ltx_provider_uses_supported_fast_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = tmp_path / "generated.mp4"
    generated.write_bytes(b"video")
    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"status": "complete", "video_path": str(generated)},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    provider = LtxDesktopVideoProvider("http://engine", video_validator=lambda *_: True)
    provider.generate_scene(
        SceneGenerationRequest(
            prompt="A cinematic astronaut discovers a robot in the red Martian dust.",
            negative_prompt="text, logos, flicker",
            aspect_ratio="9:16",
            quality="draft",
            duration_seconds=5,
            camera_motion="none",
            seed=12345,
        ),
        tmp_path / "scene.mp4",
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "fast"


def test_ltx_provider_preserves_validation_detail() -> None:
    response = httpx.Response(
        422,
        json={"detail": "Unsupported local video generation pipeline"},
        request=httpx.Request("POST", "http://engine/api/generate"),
    )

    with pytest.raises(MediaError, match="Unsupported local video generation pipeline"):
        LtxDesktopVideoProvider._raise_for_status(response, operation="generate the scene")


def test_finisher_uses_argument_array_for_scene_continuity(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        Path(arguments[-1]).write_bytes(b"frame")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    output = tmp_path / "last.jpg"
    StoryVideoFinisher(runner=runner, tool_locator=lambda _: "/usr/bin/ffmpeg").extract_last_frame(
        tmp_path / "scene.mp4", output
    )
    assert commands[0][0] == "/usr/bin/ffmpeg"
    assert commands[0][-1] == str(output.with_name("last.pending.jpg"))
    assert output.read_bytes() == b"frame"
    assert not output.with_name("last.pending.jpg").exists()


def test_templates_endpoint_exposes_character_story_styles() -> None:
    with TestClient(app) as client:
        response = client.get("/api/video-generation/templates")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} >= {
        "cinematic_story",
        "animated_adventure",
        "anime_story",
    }


def test_render_prompt_keeps_seed_out_of_scene_prose() -> None:
    from clipper.projects.story_videos import StoryVideoService

    raw = sample_plan()
    raw["scenes"][0]["visual_prompt"] += " Seed: 12345"  # type: ignore[index]
    raw["scenes"][0]["narration"] = ""  # type: ignore[index]
    prompt = StoryVideoService._scene_prompt(StoryPlan.model_validate(raw), 1)
    assert "Seed: 12345" not in prompt
    assert "narrator says" not in prompt
    assert "natural ambience" in prompt


def test_ltx_bridge_recovers_missing_manifest_and_stages_continuity(tmp_path: Path) -> None:
    shared = tmp_path / "container-data"
    media = shared / "outputs" / "scene.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video")
    provider = LtxDesktopVideoProvider("http://engine", data_dir=shared)
    remote = Path("/Users/renderer/ltx-data")
    assert provider._resolve_engine_path(str(remote / "outputs" / media.name)) == media
    reference = tmp_path / "last-frame.jpg"
    reference.write_bytes(b"image")
    staged = provider._stage_input(reference)
    assert staged is not None
    assert staged.parent == remote / "reachcut-inputs"
    assert (shared / staged.relative_to(remote)).read_bytes() == b"image"


def test_ltx_bridge_rejects_escaped_or_unrelated_missing_media(tmp_path: Path) -> None:
    shared = tmp_path / "container-data"
    shared.mkdir()
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"private")
    (shared / "outputs").symlink_to(tmp_path, target_is_directory=True)
    provider = LtxDesktopVideoProvider("http://engine", data_dir=shared)
    for remote in ["/host/ltx-data/outputs/private.mp4", "/host/unrelated/private.mp4"]:
        with pytest.raises(MediaError, match="missing media file"):
            provider._resolve_engine_path(remote)


def test_ltx_retries_incomplete_transport_then_reuses_receipt_without_new_gpu_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "engine.mp4"
    source.write_bytes(b"finished")
    calls = []
    monkeypatch.setattr("clipper.providers.ltx_desktop.time.sleep", lambda _: None)

    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(
            200,
            json={"status": "complete", "video_path": str(source)},
            request=httpx.Request("POST", url),
        )

    checks = []

    def validate(path, _):
        checks.append(path)
        # Simulate a bind mount initially exposing only the MP4 header.
        return len(checks) > 1

    monkeypatch.setattr("clipper.providers.ltx_desktop.httpx.post", post)
    provider = LtxDesktopVideoProvider("http://engine", video_validator=validate)
    request = SceneGenerationRequest(
        prompt="A clockmaker lifts a brass bird",
        negative_prompt="flicker",
        aspect_ratio="9:16",
        quality="draft",
        duration_seconds=5,
        camera_motion="static",
        seed=1,
    )
    output = tmp_path / "scene.pending.mp4"
    provider.generate_scene(request, output)
    assert output.read_bytes() == b"finished"
    output.unlink()
    provider.generate_scene(request, output)
    assert calls == ["http://engine/api/generate"]
    assert output.read_bytes() == b"finished"


def test_ltx_generation_conflict_is_recoverable() -> None:
    from clipper.generation import VideoGenerationBusyError

    response = httpx.Response(
        409,
        json={"detail": {"code": "HTTP_409", "message": "Generation already in progress"}},
        request=httpx.Request("POST", "http://engine/api/generate"),
    )
    with pytest.raises(VideoGenerationBusyError, match="continue automatically"):
        LtxDesktopVideoProvider._raise_for_status(response, operation="generate the scene")


@pytest.mark.parametrize("matching_id", [True, False])
def test_ltx_receipt_recovers_only_its_own_completed_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, matching_id: bool
) -> None:
    import hashlib
    from dataclasses import asdict

    source = tmp_path / "saved.mp4"
    source.write_bytes(b"saved-render")
    fresh = tmp_path / "fresh.mp4"
    fresh.write_bytes(b"fresh-render")
    output = tmp_path / "scene.pending.mp4"
    request = SceneGenerationRequest(
        prompt="A clockmaker lifts a brass bird",
        negative_prompt="flicker",
        aspect_ratio="9:16",
        quality="draft",
        duration_seconds=5,
        camera_motion="static",
        seed=1,
    )
    signature = hashlib.sha256(
        json.dumps(asdict(request), default=str, sort_keys=True).encode()
    ).hexdigest()
    output.with_suffix(".ltx.json").write_text(
        json.dumps({"signature": signature, "generation_id": "owned-generation"})
    )
    post_calls = []

    def post(url, **kwargs):
        post_calls.append(url)
        return httpx.Response(
            200,
            json={"status": "complete", "video_path": str(fresh)},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("clipper.providers.ltx_desktop.httpx.post", post)
    provider = LtxDesktopVideoProvider("http://engine", video_validator=lambda *_: True)
    monkeypatch.setattr(
        provider,
        "generation_progress",
        lambda: {
            "status": "complete",
            "id": "owned-generation" if matching_id else "another-generation",
            "result": str(source),
        },
    )
    provider.generate_scene(request, output)
    assert output.read_bytes() == (b"saved-render" if matching_id else b"fresh-render")
    assert len(post_calls) == (0 if matching_id else 1)


def test_missing_character_references_are_recovered_for_visible_characters() -> None:
    raw = sample_plan()
    raw["scenes"][0]["character_ids"] = []
    plan = StoryPlan.model_validate(raw)
    assert plan.scenes[0].character_ids == ["mara"]
    from clipper.projects.story_videos import StoryVideoService

    prompt = StoryVideoService._scene_prompt(plan, 1)
    assert "young adult with an oval face" in prompt
    assert "mustard coat" in prompt
    assert "Use this same medium for every character" in prompt


def test_object_closeup_does_not_inject_offscreen_characters() -> None:
    raw = sample_plan()
    raw["scenes"][0].update(
        {
            "character_ids": [],
            "story_beat": "A brass gear turns on an empty bench.",
            "visual_prompt": (
                "An extreme closeup of a brass gear turning on an empty workbench in warm daylight."
            ),
        }
    )
    assert StoryPlan.model_validate(raw).scenes[0].character_ids == []


def test_scene_prompt_carries_prop_and_previous_end_state() -> None:
    raw = sample_plan()
    raw["continuity_notes"] = "The same brass bird stays on the same wooden bench."
    first = raw["scenes"][0]
    first["ending_frame"] = "Mara holds the brass bird above the wooden bench."
    raw["scenes"].append({**first, "index": 2, "opening_frame": "", "seed": 4202})
    from clipper.projects.story_videos import StoryVideoService

    prompt = StoryVideoService._scene_prompt(StoryPlan.model_validate(raw), 2)
    assert "OPENING STATE: Mara holds the brass bird above the wooden bench." in prompt
    assert "same brass bird stays on the same wooden bench" in prompt
    assert "no teleporting" in prompt


def test_editorial_trim_preserves_native_duration_and_updates_final_timing() -> None:
    raw = sample_plan()
    raw["scenes"][0].update({"trim_start_seconds": 2.5, "playback_speed": 1.25})
    plan = StoryPlan.model_validate(raw)
    assert plan.scenes[0].duration_seconds == 5
    assert plan.duration_seconds == 5
    assert plan.output_duration_seconds == 2
    raw["scenes"][0]["trim_end_seconds"] = 2
    with pytest.raises(ValidationError, match="edit window"):
        StoryPlan.model_validate(raw)
