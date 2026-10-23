"""Final review inspects rendered media, refines conservatively, and gates publishing."""

import base64
import copy
import shutil
from pathlib import Path
from unittest.mock import Mock

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_short_studio import client, start_ideas, start_storyboard

from clipper.api.informative import short_service
from clipper.media.review_samples import review_samples
from clipper.projects import short_studio as jobs
from clipper.providers.final_video_review import review_final_video
from clipper.shorts.frames import FrameContent
from clipper.shorts.series import EpisodeSnapshot
from clipper.shorts.video_review import CopyRefinement, FinalVideoAssessment, refine_copy

__all__ = ["client"]


def assessment(passed: bool, **extra: object) -> FinalVideoAssessment:
    return FinalVideoAssessment.model_validate(
        dict(
            publishable=passed,
            summary="A clear, coherent cut" if passed else "Shorten scene 2 copy",
            hook_score=80,
            clarity_score=80,
            pacing_score=80,
            shareability_score=75,
            **extra,
        )
    )


def test_samples_come_from_each_scene_in_the_actual_video(tmp_path: Path) -> None:
    video = tmp_path / "cut.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (90, 160))
    for i in range(40):
        writer.write(np.full((160, 90, 3), 30 if i < 20 else 220, dtype=np.uint8))
    writer.release()
    samples = review_samples(video, [(0, 2), (2, 4)])
    assert len(samples) == 2
    assert all(base64.b64decode(image).startswith(b"\xff\xd8") for image in samples)
    assert samples[0] != samples[1]


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("You could find photos", "find photos"),
        ("Do not delete photos", "delete photos"),
        ("Keep your photos", "Delete your photos"),
    ],
)
def test_refinements_cannot_invent_copy_or_remove_qualifiers(
    original: str, replacement: str
) -> None:
    frame = FrameContent(template="example", caption=original, title="Photos", eyebrow="Guide")
    with pytest.raises(ValueError):
        refine_copy(frame, CopyRefinement(scene=1, field="caption", text=replacement))


@pytest.mark.parametrize("passed", [True, False])
def test_refinement_rerenders_and_reviews_the_new_cut_before_passing(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, passed: bool
) -> None:
    import clipper.shorts.service as module

    monkeypatch.setattr(module, "validate_frame_layout", lambda *args: [])
    detail = start_storyboard(client, start_ideas(client)["brief"])
    with jobs.SessionLocal() as session:
        short = short_service.get(session, detail["short"]["id"])
        artifacts = copy.deepcopy(short.artifacts)
        snapshot = EpisodeSnapshot.model_validate(artifacts["series_episode"])
        snapshot.plan.visuals[1].frame.caption = "Your photos, sorted by date"
        narration = [section.text for section in snapshot.plan.script.sections]
        artifacts["series_episode"] = snapshot.model_dump(mode="json")
        scenes = []
        timeline = []
        for i, section in enumerate(snapshot.plan.script.sections):
            path = tmp_path / f"scene-{i}.mp4"
            path.write_bytes(b"original scene")
            scenes.append(path)
            artifacts[section.id] = {"audio": str(tmp_path / "audio.wav")}
            timeline.append(dict(start=i * 6, end=(i + 1) * 6))
        output = tmp_path / "master.mp4"
        output.write_bytes(b"original cut")
        review = Mock(
            side_effect=[
                assessment(
                    False, refinements=[dict(scene=2, field="caption", text="sorted by date")]
                ),
                assessment(passed),
            ]
        )
        monkeypatch.setattr(short_service, "final_reviewer", review)
        render = Mock(
            side_effect=lambda frame, sequence, audio, path, *args: path.write_bytes(
                frame.caption.encode()
            )
        )
        monkeypatch.setattr(module, "render_frame_video", render)
        monkeypatch.setattr(
            module, "assemble_sections", lambda scenes, path: path.write_bytes(b"refined cut")
        )
        monkeypatch.setattr(
            module, "add_original_music", lambda source, target, total: shutil.copy2(source, target)
        )
        final = short_service.refine_final_video(
            session, short, artifacts, output, scenes, timeline, 30
        )
        assert final != output and review.call_count == 2 and render.call_count == 1
        assert review.call_args_list[-1].args[1] == final
        assert artifacts["final_video_review"]["status"] == (
            "passed" if passed else "needs_refinement"
        )
        assert artifacts["final_video_review"]["output_hash"] == short_service._audio_hash(final)
        changed = EpisodeSnapshot.model_validate(artifacts["series_episode"])
        assert [s.text for s in changed.plan.script.sections] == narration
        assert changed.plan.visuals[1].frame.caption == "sorted by date"


def test_missing_vision_review_blocks_publishing_and_preserves_the_video(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = start_storyboard(client, start_ideas(client)["brief"])
    output = tmp_path / "video.mp4"
    output.write_bytes(b"video")
    with jobs.SessionLocal() as session:
        short = short_service.get(session, detail["short"]["id"])
        artifacts = copy.deepcopy(short.artifacts)
        monkeypatch.setattr(short_service, "final_reviewer", None)
        with pytest.raises(ValueError, match="could not complete"):
            short_service.refine_final_video(session, short, artifacts, output, [], [], 30)
        assert output.exists()
        assert artifacts["final_video_review"]["status"] == "unavailable"
        short.status, short.output_path = "review", str(output)
        short.artifacts = {**artifacts, "studio": {"final_review_required": True}}
        with pytest.raises(ValueError, match="final AI review"):
            short_service.approve_video(session, short)
        short.artifacts = {
            **short.artifacts,
            "final_video_review": {"status": "passed", "output_hash": "old-cut"},
        }
        with pytest.raises(ValueError, match="exact video"):
            short_service.approve_video(session, short)


def test_provider_receives_video_samples_and_returns_typed_assessment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = start_storyboard(client, start_ideas(client)["brief"])
    snapshot = EpisodeSnapshot.model_validate(detail["episode"])
    monkeypatch.setattr(
        "clipper.providers.final_video_review.review_samples", lambda *args: ["jpeg-sample"]
    )

    def post(url: str, **kwargs: object) -> httpx.Response:
        body = kwargs["json"]
        assert url.endswith("/api/chat")
        assert body["messages"][0]["images"] == ["jpeg-sample"]
        assert "not claim to have listened" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"message": {"content": assessment(True).model_dump_json()}},
        )

    monkeypatch.setattr(httpx, "post", post)
    result = review_final_video(
        "http://ollama", "vision", Path("video.mp4"), snapshot, [dict(start=0, end=30)]
    )
    assert result.passed
