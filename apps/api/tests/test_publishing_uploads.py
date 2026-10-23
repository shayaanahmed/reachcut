import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import clipper.api.clips as clip_routes
import clipper.api.projects as project_routes
from clipper.config import settings
from clipper.main import app
from clipper.media import MediaError
from clipper.persistence import Base, Project, get_session
from clipper.projects import ProjectService, publishing_uploads
from clipper.projects.artifacts import ArtifactProvenance, ClipArtifactService
from clipper.projects.clips import ClipService
from clipper.rendering import VideoRenderer

VIDEO = b"\x00\x00\x00\x18ftypisom" + b"finished video"


@pytest.fixture
def upload_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(project_routes, "project_service", ProjectService(tmp_path / "projects"))
    monkeypatch.setattr(
        publishing_uploads,
        "probe_media",
        lambda *_: {"duration_seconds": 42, "width": 1920, "height": 1080},
    )
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            yield client
        with Session(engine) as session:
            # Rejected uploads must leave neither records nor owned files behind.
            if not list((tmp_path / "projects").glob("*")):
                assert session.scalar(select(Project)) is None
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_finished_upload_uses_existing_publishing_artifacts(upload_client: TestClient) -> None:
    response = upload_client.post(
        "/api/projects/upload-for-publishing",
        data={"title": " My finished video ", "authorization_confirmed": "true"},
        files={"media": ("finished.mp4", VIDEO, "video/mp4")},
    )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["title"] == "My finished video"
    assert project["status"] == "complete"
    assert project["job"] is None
    assert project["stages"] == []
    assert project["duration_seconds"] == 42
    assert len(project["clips"]) == 1
    clip = project["clips"][0]
    assert clip["approval_status"] == "approved"
    assert clip["plan"]["caption_config"]["enabled"] is False
    assert clip["plan"]["source"] == {"start_seconds": 0, "end_seconds": 42}
    assert clip["publications"] == []
    assert upload_client.get(f"/api/clips/{clip['id']}/final").content == VIDEO
    assert upload_client.get(f"/api/projects/{project['id']}").status_code == 200
    tracked = upload_client.post(
        f"/api/clips/{clip['id']}/publications",
        json={
            "platform": "youtube",
            "status": "published",
            "post_url": "https://www.youtube.com/shorts/uploaded-video",
            "title": "My finished video",
            "description": "Uploaded master",
        },
    )
    assert tracked.status_code == 200, tracked.text
    assert tracked.json()["clips"][0]["publications"][0]["status"] == "published"
    assert upload_client.delete(f"/api/projects/{project['id']}").status_code == 204


@pytest.mark.parametrize(
    ("title", "authorized", "filename", "content", "status"),
    [
        ("Video", "false", "video.mp4", VIDEO, 422),
        ("   ", "true", "video.mp4", VIDEO, 422),
        ("Video", "true", "video.webm", VIDEO, 415),
        ("Video", "true", "video.mp4", b"not a video", 415),
        ("Video", "true", "video.mp4", b"\x1aE\xdf\xa3disguised webm", 415),
    ],
)
def test_rejected_uploads(
    upload_client: TestClient,
    title: str,
    authorized: str,
    filename: str,
    content: bytes,
    status: int,
) -> None:
    response = upload_client.post(
        "/api/projects/upload-for-publishing",
        data={"title": title, "authorization_confirmed": authorized},
        files={"media": (filename, content, "video/mp4")},
    )
    assert response.status_code == status


def test_failed_probe_cleans_up_upload(
    upload_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(*_: object) -> dict[str, object]:
        raise MediaError("media has no video stream")

    monkeypatch.setattr(publishing_uploads, "probe_media", reject)
    response = upload_client.post(
        "/api/projects/upload-for-publishing",
        data={"title": "Video", "authorization_confirmed": "true"},
        files={"media": ("video.mp4", VIDEO, "video/mp4")},
    )
    assert response.status_code == 415
    assert "no video" in response.json()["detail"]


def test_upload_size_limit(upload_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    response = upload_client.post(
        "/api/projects/upload-for-publishing",
        data={"title": "Video", "authorization_confirmed": "true"},
        files={"media": ("video.mp4", VIDEO, "video/mp4")},
    )
    assert response.status_code == 415
    assert "byte limit" in response.json()["detail"]


def test_uploaded_video_can_save_studio_edits_through_api(
    upload_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def render(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        Path(arguments[-1]).write_bytes(VIDEO)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(
        clip_routes,
        "clip_service",
        ClipService(ClipArtifactService(ArtifactProvenance("none", "none")), VideoRenderer(render)),
    )
    response = upload_client.post(
        "/api/projects/upload-for-publishing",
        data={"title": "Edit me", "authorization_confirmed": "true"},
        files={"media": ("clip.mp4", VIDEO, "video/mp4")},
    )
    clip = response.json()["clips"][0]
    edited = upload_client.put(
        f"/api/clips/{clip['id']}/style",
        json={
            "caption_config": clip["plan"]["caption_config"],
            "frame_style": "center_crop",
            "source_slices": [{"start_seconds": 2, "end_seconds": 12}],
            "watermark": {
                "text": "@MyBrand",
                "position": "top_left",
                "opacity": 0.5,
                "font_size": 40,
            },
            "original_audio_volume": 0.2,
        },
    )
    assert edited.status_code == 200, edited.text
    saved = edited.json()["clips"][0]
    assert saved["final_path"] is None
    assert saved["plan"]["watermark"]["text"] == "@MyBrand"
    assert saved["plan"]["original_audio_volume"] == 0.2
    assert upload_client.get(f"/api/clips/{clip['id']}/preview").status_code == 200
    assert upload_client.post(f"/api/clips/{clip['id']}/render").status_code == 201


def test_publishing_upload_can_queue_either_pipeline(upload_client: TestClient) -> None:
    project = upload_client.post(
        "/api/projects/upload-for-publishing",
        data={"title": "Finished video", "authorization_confirmed": "true"},
        files={"media": ("finished.mp4", VIDEO, "video/mp4")},
    ).json()
    project_url = f"/api/projects/{project['id']}"
    response = upload_client.post(f"{project_url}/process", json={"processing_mode": "metadata"})
    assert response.status_code == 202
    assert upload_client.get(project_url).json()["job"]["processing_mode"] == "metadata"
    assert upload_client.post(f"{project_url}/cancel").status_code == 202
    assert upload_client.post(f"{project_url}/retry").status_code == 202
    assert upload_client.get(project_url).json()["job"]["processing_mode"] == "metadata"
    assert upload_client.post(f"{project_url}/cancel").status_code == 202
    assert (
        upload_client.post(f"{project_url}/process", json={"processing_mode": "clips"}).status_code
        == 202
    )
    assert upload_client.get(project_url).json()["job"]["processing_mode"] == "clips"
    assert (
        upload_client.post(
            f"{project_url}/process", json={"processing_mode": "invalid"}
        ).status_code
        == 422
    )
