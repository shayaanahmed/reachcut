import json
from collections.abc import Callable

import pytest

from clipper.domain.editing_plan import EditingPlanV1
from clipper.providers.ollama import EditorialOutputError, OllamaEditorialProvider


def test_rejects_malformed_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"response": '{"answer":"prose"}', "done_reason": "stop"}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")
    with pytest.raises(EditorialOutputError, match="after 2 attempts"):
        provider._generate("test prompt")


def test_uses_json_schema_and_disables_thinking(
    monkeypatch: pytest.MonkeyPatch,
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    requests: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            envelope = {"candidates": [make_plan().model_dump(mode="json")]}
            return {"response": json.dumps(envelope), "done_reason": "stop"}

    def post(*args: object, **kwargs: object) -> Response:
        requests.append(kwargs["json"])  # type: ignore[arg-type]
        return Response()

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")
    candidates = provider._generate("test prompt")

    assert len(candidates) == 1
    assert requests[0]["think"] is False
    assert isinstance(requests[0]["format"], dict)


def test_keeps_valid_candidates_and_discards_unsafe_timestamps(
    monkeypatch: pytest.MonkeyPatch,
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    valid = make_plan().model_dump(mode="json")
    invalid = make_plan().model_dump(mode="json")
    invalid["hook"] = {"text": "Outside clip", "start_seconds": 0, "end_seconds": 99}

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "response": json.dumps({"candidates": [valid, invalid]}),
                "done_reason": "stop",
            }

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")

    candidates = provider._generate("test prompt")

    assert candidates == [valid]
