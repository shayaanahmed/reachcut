from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from clipper.api import informative
from clipper.main import app
from clipper.persistence import get_session
from clipper.persistence.models import Base, Project, StoryVideo, now_utc
from clipper.shorts.contracts import Evidence


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Base.metadata.create_all(engine)  # repeatable additive migration

    def override() -> Generator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    monkeypatch.setattr(informative.short_service, "root", tmp_path)
    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_complete_draft_approval_and_compatibility_routes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = Evidence(
        id="source",
        url="https://docs.python.org/3/",
        title="Python docs",
        text="Lists can be changed using their append method.",
    )
    monkeypatch.setattr(informative.research, "retrieve", lambda _: [evidence])
    response = client.post(
        "/api/shorts", json={"topic": "Python lists", "request_key": "stable-key"}
    )
    assert response.status_code == 200
    short_id = response.json()["id"]
    assert (
        client.post(
            "/api/shorts", json={"topic": "Python lists", "request_key": "stable-key"}
        ).json()["id"]
        == short_id
    )
    assert (
        client.post(
            "/api/shorts", json={"topic": "Changed topic", "request_key": "stable-key"}
        ).status_code
        == 422
    )
    assert client.post(f"/api/shorts/{short_id}/produce").status_code == 422
    assert client.post(f"/api/shorts/{short_id}/approve").status_code == 422
    assert (
        client.post(f"/api/shorts/{short_id}/sources", json={"urls": [evidence.url]}).status_code
        == 200
    )
    script = {
        "version": "1",
        "sections": [
            {
                "id": "opening",
                "heading": "Lists",
                "text": "Explain Python lists.",
                "visual": "explanation",
                "claims": [
                    {
                        "text": "Lists are mutable",
                        "source_id": "source",
                        "quote": evidence.text,
                        "status": "supported",
                    }
                ],
            }
        ],
    }
    assert client.put(f"/api/shorts/{short_id}/script", json=script).status_code == 200
    assert client.post(f"/api/shorts/{short_id}/script/approve").json()["approved"] is True
    assert client.post(f"/api/shorts/{short_id}/produce").json()["status"] == "queued"
    assert client.put(f"/api/shorts/{short_id}/script", json=script).status_code == 422
    assert client.post(f"/api/shorts/{short_id}/cancel").json()["status"] == "cancelled"
    script["sections"][0]["text"] = "A substantive script edit."
    assert client.put(f"/api/shorts/{short_id}/script", json=script).json()["approved"] is False
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/video-generation").status_code == 200


def test_preset_defaults_and_invalid_provider_output(client: TestClient) -> None:
    preset = client.post(
        "/api/channel-presets", json={"name": "Urdu channel", "settings": {"language": "ur"}}
    )
    assert preset.status_code == 200
    data = preset.json()
    assert data["settings"]["duration"] == 45 and data["settings"]["spend_limit_usd"] == 0
    assert client.get("/api/channel-presets").json()[0]["id"] == data["id"]
    assert (
        client.post(
            "/api/shorts",
            json={"topic": "History", "request_key": "key-12345", "settings": {"duration": 90}},
        ).status_code
        == 422
    )
    short = client.post("/api/shorts", json={"topic": "History", "request_key": "key-12345"}).json()
    assert (
        client.put(
            f"/api/shorts/{short['id']}/script", json={"version": "bad", "sections": []}
        ).status_code
        == 422
    )


def test_additive_schema_keeps_existing_projects_and_legacy_stories(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        # Simulate the older application's exact existing project/story tables.
        Project.__table__.create(connection)
        StoryVideo.__table__.create(connection)
    with Session(engine) as session:
        session.add(
            Project(
                id="legacy-project",
                title="Existing source",
                original_filename="old.mp4",
                source_path="/fixture/old.mp4",
                media_sha256="a" * 64,
                authorization_confirmed_at=now_utc(),
            )
        )
        session.add(
            StoryVideo(
                id="legacy-story",
                story="Old story",
                template="cinematic",
                aspect_ratio="9:16",
                quality="draft",
                target_duration_seconds=30,
                plan={},
                status="complete",
            )
        )
        session.commit()
    Base.metadata.create_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert session.get(Project, "legacy-project").title == "Existing source"
        assert session.get(StoryVideo, "legacy-story").story == "Old story"


def test_source_upload_inherits_channel_language(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import clipper.api.projects as project_routes

    monkeypatch.setattr(project_routes.settings, "data_dir", tmp_path)
    preset = client.post(
        "/api/channel-presets",
        json={
            "name": "Urdu",
            "settings": {"language": "ur-en", "caption_font": "Noto Nastaliq Urdu"},
        },
    ).json()
    response = client.post(
        "/api/projects/upload",
        data={
            "title": "Source with preset",
            "authorization_confirmed": "true",
            "preset_id": preset["id"],
        },
        files={"media": ("source.mp4", b"\x00\x00\x00\x18ftypisom" + b"fixture" * 10, "video/mp4")},
    )
    assert response.status_code == 201
    sessions = app.dependency_overrides[get_session]()
    session = next(sessions)
    try:
        assert session.get(Project, response.json()["id"]).job.language == "ur-en"
    finally:
        sessions.close()
