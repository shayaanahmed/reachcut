from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import clipper.api.projects as project_routes
from clipper.config import settings
from clipper.main import app
from clipper.media import StoredUpload
from clipper.persistence import Base, get_session
from clipper.projects import ProjectService


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

    class FakeDownloader:
        def download(self, _: str, target: Path, __: int) -> StoredUpload:
            target.mkdir(parents=True)
            source = target / "source.mp4"
            source.write_bytes(b"\x00\x00\x00\x18ftypisom")
            return StoredUpload(source, "b" * 64, source.stat().st_size)

    monkeypatch.setattr(project_routes, "media_downloader", FakeDownloader())
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
                data={"title": "First name", "authorization_confirmed": "true"},
                files={"media": ("fixture.mp4", b"\x00\x00\x00\x18ftypisom", "video/mp4")},
            )
            assert created.status_code == 201
            project_id = created.json()["id"]

            assert client.get(f"/api/projects/{project_id}").status_code == 200
            updated = client.put(
                f"/api/projects/{project_id}",
                json={"title": "Renamed project"},
            )
            assert updated.status_code == 200
            assert updated.json()["title"] == "Renamed project"

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
            assert imported.json()["original_filename"] == "source.mp4"
    finally:
        app.dependency_overrides.clear()
