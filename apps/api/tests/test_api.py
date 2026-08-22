from fastapi.testclient import TestClient

from clipper.main import app


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
