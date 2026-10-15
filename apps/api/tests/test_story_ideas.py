import json

import httpx
import pytest
from fastapi.testclient import TestClient

from clipper.api import video_generation
from clipper.main import app
from clipper.providers.ollama_story import OllamaStoryDirector, StoryIdeaOutputError

STORY = (
    "A tower of rainbow chalk cubes waits beneath a hydraulic press. The press descends "
    "slowly, cracking the top cube before collapsing the tower. Colorful fragments scatter "
    "across the metal platform as the fixed camera holds on the final pile of chalk dust."
)


def test_story_idea_repairs_title_and_narrative_in_wrong_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []
    broken = {"story": "Rainbow Chalk Crush", "hook": "A long action description. " * 20}

    def post(url: str, **kwargs: object) -> httpx.Response:
        payload = kwargs["json"]
        assert isinstance(payload, dict)
        prompts.append(payload["prompt"])
        result = (
            broken if len(prompts) == 1 else {"story": STORY, "hook": "Watch a rainbow crumble."}
        )
        return httpx.Response(
            200, json={"response": json.dumps(result)}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", post)
    result = OllamaStoryDirector("http://ollama", "text").ideate(
        "A press crushes rainbow chalk cubes.", "documentary_realism"
    )
    assert result.story == STORY
    assert result.hook == "Watch a rainbow crumble."
    assert len(prompts) == 2
    assert "COMPLETE narrative" in prompts[0]
    assert "hook: String should have at most 180 characters" in prompts[1]
    assert "story: String should have at least 30 characters" in prompts[1]


def test_invalid_story_output_is_bounded_and_has_clear_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    director = OllamaStoryDirector("http://ollama", "text")
    calls: list[str] = []

    def generate(prompt: str, _: object) -> dict[str, str]:
        calls.append(prompt)
        return {"story": "Title", "hook": "Too long " * 50}

    monkeypatch.setattr(director, "_generate", generate)
    monkeypatch.setattr(video_generation, "_director", lambda _: director)
    with TestClient(app) as client:
        response = client.post("/api/video-generation/idea", json={"idea": "Rainbow chalk press"})
    assert response.status_code == 502
    assert "invalid story format after retrying" in response.json()["detail"]
    assert "create a storyboard" in response.json()["detail"]
    assert len(calls) == 2
    with pytest.raises(StoryIdeaOutputError) as caught:
        director.ideate("Chalk press", "documentary_realism")
    assert caught.value.fields == ("hook", "story")


def test_story_connection_failure_is_reported_without_format_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    director = OllamaStoryDirector("http://ollama", "text")

    def generate(prompt: str, _: object) -> dict[str, str]:
        calls.append(prompt)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(director, "_generate", generate)
    monkeypatch.setattr(video_generation, "_director", lambda _: director)
    with TestClient(app) as client:
        response = client.post("/api/video-generation/idea", json={"idea": "Rainbow chalk press"})
    assert response.status_code == 503
    assert "Could not connect to Ollama" in response.json()["detail"]
    assert len(calls) == 1
