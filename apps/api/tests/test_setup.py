import httpx
import pytest
from fastapi.testclient import TestClient

import clipper.api.setup as setup_routes
from clipper.main import app
from clipper.services.setup import OllamaSetupService


def test_setup_service_finds_configured_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.7"})
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen3:8b-q4_K_M", "size": 5_200_000_000}]},
        )

    service = OllamaSetupService(
        "http://ollama.test",
        "qwen3:8b-q4_K_M",
        transport=httpx.MockTransport(handler),
    )

    result = service.status()

    assert result.available is True
    assert result.version == "0.12.7"
    assert result.model_installed is True
    assert result.model_size_bytes == 5_200_000_000


def test_setup_service_pulls_and_verifies_model() -> None:
    pulled = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal pulled
        if request.url.path == "/api/pull":
            assert request.method == "POST"
            assert b'"stream":false' in request.content
            pulled = True
            return httpx.Response(200, json={"status": "success"})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.7"})
        return httpx.Response(
            200,
            json={"models": [{"model": "qwen3:8b-q4_K_M"}]} if pulled else {"models": []},
        )

    service = OllamaSetupService(
        "http://ollama.test",
        "qwen3:8b-q4_K_M",
        transport=httpx.MockTransport(handler),
    )

    assert service.pull_model().model_installed is True


def test_setup_endpoint_reports_missing_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    monkeypatch.setattr(
        setup_routes,
        "setup_service",
        OllamaSetupService("http://ollama.test", "qwen3:8b", transport=transport),
    )
    monkeypatch.setattr(setup_routes.shutil, "which", lambda _: "/bundled/tool")

    with TestClient(app) as client:
        response = client.get("/api/setup/status")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["ollama_available"] is False
    assert response.json()["ollama_install_url"] == "https://ollama.com/download"
