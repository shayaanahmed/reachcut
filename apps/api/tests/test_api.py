from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import clipper.api.clips as clip_routes
import clipper.api.projects as project_routes
from clipper.config import settings
from clipper.main import app
from clipper.persistence import Base, Clip, Project, Publication, get_session, now_utc
from clipper.projects import ClipService, ProjectService


def test_health_exposes_local_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["editorial_provider"].startswith("ollama:")


def test_upload_requires_rights_confirmation() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/projects/upload",
            data={"title": "Unauthorized fixture", "authorization_confirmed": "false"},
            files={"media": ("fixture.mp4", b"\x00\x00\x00\x18ftypisom", "video/mp4")},
        )
    assert response.status_code == 422
    assert "authorization" in response.json()["detail"]


def test_secondary_media_requires_rights_confirmation() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/clips/missing/secondary-media",
            data={
                "kind": "gameplay",
                "placement": "bottom",
                "authorization_confirmed": "false",
            },
            files={"media": ("game.mp4", b"fixture", "video/mp4")},
        )

    assert response.status_code == 422
    assert "authorization" in response.json()["detail"]


def test_configured_web_port_can_start_processing_through_cors() -> None:
    origin = f"http://localhost:{settings.web_port}"
    with TestClient(app) as client:
        response = client.options(
            "/api/projects/project-id/process",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_project_routes_support_create_read_update_and_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        project_routes,
        "project_service",
        ProjectService(tmp_path / "projects"),
    )

    monkeypatch.setattr(
        project_routes,
        "validate_public_media_url",
        lambda url, _: url,
    )
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/projects/upload",
                data={"title": "First name", "authorization_confirmed": "true", "language": ""},
                files={"media": ("fixture.mp4", b"\x00\x00\x00\x18ftypisom", "video/mp4")},
            )
            assert created.status_code == 201
            project_id = created.json()["id"]
            assert created.json()["storage_bytes"] == len(b"\x00\x00\x00\x18ftypisom")

            assert client.get(f"/api/projects/{project_id}").status_code == 200
            updated = client.put(
                f"/api/projects/{project_id}",
                json={"title": "Renamed project"},
            )
            assert updated.status_code == 200
            assert updated.json()["title"] == "Renamed project"

            assert created.json()["status"] == "queued"
            assert created.json()["job"]["status"] == "queued"
            assert client.delete(f"/api/projects/{project_id}").status_code == 409
            assert client.post(f"/api/projects/{project_id}/cancel").json()["status"] == "cancelled"
            deleted = client.delete(f"/api/projects/{project_id}")
            assert deleted.status_code == 204
            assert client.get(f"/api/projects/{project_id}").status_code == 404
            assert not (tmp_path / "projects" / project_id).exists()

            imported = client.post(
                "/api/projects/import-url",
                json={
                    "title": "URL project",
                    "url": "https://youtube.com/watch?v=abc",
                    "authorization_confirmed": True,
                },
            )
            assert imported.status_code == 201
            assert imported.json()["status"] == "queued"
            assert imported.json()["job"]["source_url"] == "https://youtube.com/watch?v=abc"
            assert imported.json()["storage_bytes"] == 0
            assert not (tmp_path / "projects" / imported.json()["id"]).exists()
            imported_id = imported.json()["id"]
            assert client.post(f"/api/projects/{imported_id}/cancel").status_code == 202
            assert client.post(f"/api/projects/{imported_id}/retry").status_code == 202
            assert client.get(f"/api/projects/{imported_id}").json()["status"] == "queued"
    finally:
        app.dependency_overrides.clear()


def test_delete_clip_removes_its_record_publications_and_owned_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_plan,  # type: ignore[no-untyped-def]
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    projects_root = tmp_path / "projects"
    source = projects_root / "project-1" / "source" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    clip_root = source.parent / "clips" / "clip-1"
    (clip_root / "assets" / "asset-1").mkdir(parents=True)
    preview = clip_root / "preview.mp4"
    final = clip_root / "final.mp4"
    preview.write_bytes(b"preview")
    final.write_bytes(b"final")
    (clip_root / "assets" / "asset-1" / "game.mp4").write_bytes(b"asset")

    with Session(engine) as session:
        project = Project(
            id="project-1",
            title="Fixture",
            original_filename=source.name,
            source_path=str(source),
            media_sha256="a" * 64,
            authorization_confirmed_at=now_utc(),
            status="review",
        )
        clip = Clip(
            id="clip-1",
            project=project,
            plan=make_plan().model_dump(mode="json"),
            preview_path=str(preview),
            final_path=str(final),
        )
        Publication(id="publication-1", clip=clip, platform="youtube")
        session.add(project)
        session.commit()

    def session_override() -> Generator[Session]:
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        clip_routes,
        "clip_service",
        ClipService(None, None, projects_root=projects_root),  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            deleted = client.delete("/api/clips/clip-1")
            assert deleted.status_code == 200
            assert deleted.json()["clips"] == []
            assert deleted.json()["storage_bytes"] == len(b"source")
        with Session(engine) as session:
            assert session.get(Clip, "clip-1") is None
            assert session.get(Publication, "publication-1") is None
        assert not clip_root.exists()
        assert source.exists()
    finally:
        app.dependency_overrides.clear()
