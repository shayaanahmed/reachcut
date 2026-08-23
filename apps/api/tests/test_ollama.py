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


def test_normalizes_unambiguous_absolute_nested_timestamps(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    absolute = make_plan(start=300, end=360).model_dump(mode="json")
    absolute["hook"] = {
        "text": "Absolute hook",
        "start_seconds": 300,
        "end_seconds": 303,
    }
    absolute["emphasis"] = [
        {
            "words": ["important"],
            "style": "primary",
            "start_seconds": 310,
            "end_seconds": 311,
        }
    ]
    absolute["effects"] = [{"time_seconds": 320, "type": "punch_zoom", "parameters": {}}]
    absolute["cta"] = {
        "text": "Keep watching",
        "start_seconds": 355,
        "end_seconds": 359,
    }

    valid, errors = OllamaEditorialProvider._validated_candidates({"candidates": [absolute]})

    assert errors == []
    assert valid[0]["hook"]["start_seconds"] == 0
    assert valid[0]["hook"]["end_seconds"] == 3
    assert valid[0]["emphasis"][0]["start_seconds"] == 10
    assert valid[0]["effects"][0]["time_seconds"] == 20
    assert valid[0]["cta"]["start_seconds"] == 55


def test_does_not_normalize_ambiguous_out_of_range_timestamp(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    unsafe = make_plan(start=300, end=360).model_dump(mode="json")
    unsafe["hook"] = {
        "text": "Outside source",
        "start_seconds": 299,
        "end_seconds": 303,
    }

    valid, errors = OllamaEditorialProvider._validated_candidates({"candidates": [unsafe]})

    assert valid == []
    assert "relative timestamp exceeds selected source duration" in errors[0]
