from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_video_generation import sample_plan

from clipper.api import video_generation
from clipper.api.schemas import ProjectResponse
from clipper.generation import StoryPlan
from clipper.main import app
from clipper.persistence import Base, get_session
from clipper.persistence.models import StoryDraft
from clipper.projects.story_queue import StoryQueue
from clipper.projects.story_videos import StoryVideoCreate, StoryVideoService


def request(draft_id: str | None = None) -> StoryVideoCreate:
    return StoryVideoCreate(
        story="A clockmaker discovers a mechanical bird that can rewind time.",
        template="cinematic_story",
        aspect_ratio="9:16",
        quality="draft",
        plan=StoryPlan.model_validate(sample_plan()),
        draft_id=draft_id,
    )


def test_queue_survives_reload_consumes_only_started_story_and_blocks_overlap(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = StoryVideoService(tmp_path / "stories", Mock(identity="local"), Mock())
    queue = StoryQueue()
    with Session(engine) as session:
        first = queue.save(session, request().story, {"story": request().story})
        second = queue.save(session, "Another story with enough detail to direct.", {})
        first_id, second_id = first.id, second.id
    with Session(engine) as session:
        assert [item.id for item in queue.list(session)] == [first_id, second_id]
        video = service.create(session, request(first_id))
        assert session.get(StoryDraft, first_id) is None
        assert [item.id for item in queue.list(session)] == [second_id]
        with pytest.raises(ValueError, match="already processing"):
            service.create(session, request(second_id))
        assert session.get(StoryDraft, second_id) is not None
        video.status = "failed"
        session.commit()
        with pytest.raises(ValueError, match="already processed"):
            service.create(session, request(first_id))
        assert service.rename(session, video.id, "A new title").plan["title"] == "A new title"
        queue.delete(session, second_id)
        assert queue.list(session) == []


def test_finished_short_reuses_publishing_copy_and_delete_preserves_master(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    service = StoryVideoService(tmp_path / "stories", Mock(identity="local"), Mock())
    with Session(engine) as session:
        video = service.create(session, request())
        with pytest.raises(LookupError, match="not ready"):
            service.prepare_publishing(session, video.id, tmp_path / "projects")
        master = tmp_path / "stories" / video.id / "video.mp4"
        master.parent.mkdir(parents=True)
        master.write_bytes(b"finished-master")
        video.status = "complete"
        video.output_path = str(master)
        session.commit()
        clip = service.prepare_publishing(session, video.id, tmp_path / "projects")
        repeated = service.prepare_publishing(session, video.id, tmp_path / "projects")
        assert repeated.id == clip.id
        assert Path(clip.final_path or "").read_bytes() == b"finished-master"
        assert clip.approval_status == "approved"
        assert ProjectResponse.model_validate(clip.project).clips[0].final_path is not None
        service.delete(session, video.id)
        assert not master.exists()
        assert Path(clip.final_path or "").read_bytes() == b"finished-master"


def test_queue_api_crud_and_builtin_auto_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    director = Mock()
    director._generate.return_value = {
        "template": "anime_story",
        "reason": "Dynamic animated chase",
    }
    monkeypatch.setattr(video_generation, "_director", lambda _: director)
    monkeypatch.setattr(video_generation.template_library, "list", lambda: [])
    with Session(engine) as session:
        app.dependency_overrides[get_session] = lambda: session
        try:
            client = TestClient(app)
            body = {"story": request().story, "template": None, "quality": "1080p"}
            created = client.post("/api/video-generation/drafts", json=body)
            assert created.status_code == 201
            draft_id = created.json()["id"]
            assert (
                client.get("/api/video-generation/drafts").json()[0]["settings"]["quality"]
                == "1080p"
            )
            updated = client.put(
                f"/api/video-generation/drafts/{draft_id}", json={**body, "template": "anime_story"}
            )
            assert updated.json()["settings"]["template"] == "anime_story"
            matched = client.post(
                "/api/video-generation/match-format", json={"story": request().story}
            )
            assert matched.json() == {
                "template": "anime_story",
                "reference_template_id": None,
                "reason": "Dynamic animated chase",
            }
            assert client.delete(f"/api/video-generation/drafts/{draft_id}").status_code == 204
            assert client.get("/api/video-generation/drafts").json() == []
            assert (
                client.put(f"/api/video-generation/drafts/{draft_id}", json=body).status_code == 404
            )
        finally:
            app.dependency_overrides.clear()


def test_optional_visual_style_preserves_reference_format(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    blueprint = {
        "format": "Doorbell camera",
        "camera": "Fixed wide shot",
        "pacing": "Continuous",
        "visual_style": "Infrared footage",
    }
    monkeypatch.setattr(
        video_generation.template_library, "guidance", lambda _: json.dumps(blueprint)
    )
    original = json.loads(video_generation._guidance("reference", "anime_story", False))
    override = json.loads(video_generation._guidance("reference", "anime_story", True))
    assert original == blueprint
    assert override["format"] == original["format"]
    assert override["camera"] == original["camera"]
    assert override["pacing"] == original["pacing"]
    assert "anime" in override["visual_style"]


def test_auto_format_can_reject_unrelated_saved_video(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    director = Mock()
    director._generate.return_value = {
        "template": "animated_adventure",
        "reference_template_id": None,
        "reason": "An emotional robot story needs consistent animation",
    }
    saved = SimpleNamespace(
        id="a" * 32,
        status="ready",
        blueprint=SimpleNamespace(
            base_template="documentary_realism",
            format="CCTV",
            visual_style="Grainy monochrome surveillance footage",
            suitable_for="Fixed-camera security events",
        ),
    )
    monkeypatch.setattr(video_generation, "_director", lambda _: director)
    monkeypatch.setattr(video_generation.template_library, "list", lambda: [saved])
    from clipper.api.schemas import StoryFormatMatchRequest

    result = video_generation.match_format(
        StoryFormatMatchRequest(
            story="A small friendly robot brings a birthday cake to a lonely child."
        ),
        Mock(),
    )
    assert result.template == "animated_adventure"
    assert result.reference_template_id is None
    prompt = director._generate.call_args.args[0]
    assert '"built_in_formats"' in prompt and '"saved_video_formats"' in prompt
