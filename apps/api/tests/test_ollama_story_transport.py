"""GPT-OSS answers must come from the chat answer channel as complete JSON."""

import json
from typing import Any

import httpx
import pytest

from clipper.providers.ollama_story import OllamaStoryDirector
from clipper.providers.studio_editor import OllamaStudioEditor
from clipper.providers.studio_narrative import EditorialReview
from clipper.shorts.contracts import Evidence


def test_gpt_oss_uses_chat_and_grounds_the_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, **kwargs: Any) -> httpx.Response:
        requests.append((url, kwargs["json"]))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "message": {"content": '{"issues": []}', "thinking": "Private reasoning"},
                "done_reason": "stop",
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    output = OllamaStoryDirector("http://ollama", "gpt-oss:20b")._generate(
        "Check the story", EditorialReview
    )
    assert output == {"issues": []}
    url, body = requests[0]
    assert url == "http://ollama/api/chat"
    assert body["think"] == "low"
    assert "prompt" not in body
    assert body["messages"][1] == {"role": "user", "content": "Check the story"}
    assert json.dumps(EditorialReview.model_json_schema()) in body["messages"][0]["content"]
    assert "No Markdown" in body["messages"][0]["content"]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"response": "", "done": False}, "empty answer"),
        ({"message": {"content": "", "thinking": "Only reasoning"}}, "empty answer"),
        ({"message": {"content": '```json5csharp{",\\n"storylines":[]}'}}, "invalid JSON"),
        ({"message": {"content": '{"issues":[]}'}, "done_reason": "length"}, "token limit"),
        ({"message": {"content": "[]"}}, "non-object JSON"),
        ({"error": "model runner stopped"}, "model runner stopped"),
    ],
)
def test_bad_answers_report_the_actual_transport_failure(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any], error: str
) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(200, request=httpx.Request("POST", url), json=payload),
    )
    with pytest.raises(ValueError, match=error):
        OllamaStoryDirector("http://ollama", "gpt-oss:20b")._generate("Check", EditorialReview)


def test_qwen_receives_the_task_and_schema_as_chat_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def post(url: str, **kwargs: Any) -> httpx.Response:
        assert url.endswith("/api/chat")
        body = kwargs["json"]
        assert body["think"] is False
        assert body["messages"][1] == {"role": "user", "content": "Check"}
        assert json.dumps(EditorialReview.model_json_schema()) in body["messages"][0]["content"]
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"message": {"content": '{"issues": []}'}}
        )

    monkeypatch.setattr(httpx, "post", post)
    assert OllamaStoryDirector("http://ollama", "qwen3:8b")._generate("Check", EditorialReview) == {
        "issues": []
    }


def test_other_models_keep_the_completion_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(url: str, **kwargs: Any) -> httpx.Response:
        assert url.endswith("/api/generate")
        assert kwargs["json"]["prompt"] == "Check"
        assert kwargs["json"]["think"] is False
        assert json.dumps(EditorialReview.model_json_schema()) in kwargs["json"]["system"]
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"response": '{"issues": []}'}
        )

    monkeypatch.setattr(httpx, "post", post)
    assert OllamaStoryDirector("http://ollama", "llama3:8b")._generate(
        "Check", EditorialReview
    ) == {"issues": []}


def test_storyline_failure_preserves_the_useful_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = OllamaStudioEditor("http://ollama", "gpt-oss:20b")
    calls = 0

    def generate(*args: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise ValueError("Ollama returned an empty answer instead of JSON")

    monkeypatch.setattr(editor.director, "_generate", generate)
    source = Evidence(
        id="docs",
        url="https://example.com/docs",
        title="Docs",
        text=(
            "This tool sorts photographs into dated folders "
            "and previews changes before applying them."
        ),
    )
    with pytest.raises(ValueError, match="after two attempts: Ollama returned an empty answer"):
        editor.ideas("github", "example/photos", [source])
    assert calls == 2
