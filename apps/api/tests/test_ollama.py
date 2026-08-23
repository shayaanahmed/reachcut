import json
from pathlib import Path
from typing import Any

import pytest

from clipper.domain.editing_plan import TimeRange
from clipper.providers.ollama import (
    CandidateOption,
    EditorialCandidate,
    EditorialOutputError,
    OllamaEditorialProvider,
)


def candidate(candidate_id: str = "c0000", score: int = 80) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "scores": {
            "overall": score,
            "hook": score,
            "clarity": score,
            "payoff": score,
            "visual_interest": score,
        },
        "rationale": "A self-contained idea with a clear payoff.",
        "hook_text": "A useful opening",
        "caption_style": "clean",
    }


def test_rejects_malformed_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"response": '{"answer":"prose"}', "done_reason": "stop"}

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: Response())
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")
    with pytest.raises(EditorialOutputError, match="after 2 attempts"):
        provider.generate_structured("test prompt")


def test_uses_small_json_schema_and_disables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "response": json.dumps({"candidates": [candidate()]}),
                "done_reason": "stop",
            }

    def post(*args: object, **kwargs: object) -> Response:
        requests.append(kwargs["json"])  # type: ignore[arg-type]
        return Response()

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")
    candidates = provider.generate_structured("test prompt")

    assert len(candidates) == 1
    assert requests[0]["think"] is False
    schema = requests[0]["format"]
    assert isinstance(schema, dict)
    assert "effects" not in json.dumps(schema)
    assert "emphasis" not in json.dumps(schema)


def test_keeps_supplied_candidate_id_and_discards_invented_id() -> None:
    valid, errors = OllamaEditorialProvider.validate_candidates(
        {"candidates": [candidate("c0001"), candidate("c9999")]},
        allowed_ids={"c0001", "c0002"},
    )

    assert valid == [candidate("c0001")]
    assert "not present in the supplied options" in errors[0]


def test_rejects_duplicate_candidate_id() -> None:
    valid, errors = OllamaEditorialProvider.validate_candidates(
        {"candidates": [candidate("c0001"), candidate("c0001")]}
    )

    assert valid == [candidate("c0001")]
    assert "duplicated" in errors[0]


def test_builds_render_plan_with_deterministic_relative_timestamps() -> None:
    editorial = EditorialCandidate.model_validate(candidate())
    option = CandidateOption(
        candidate_id="c0000",
        source=TimeRange(start_seconds=300, end_seconds=360),
        text="Licensed synthetic fixture text.",
    )

    plan = OllamaEditorialProvider.create_editing_plan(editorial, option)

    assert plan.source.start_seconds == 300
    assert plan.source.end_seconds == 360
    assert plan.hook is not None
    assert plan.hook.start_seconds == 0
    assert plan.hook.end_seconds == 3.5
    assert plan.emphasis == []
    assert plan.effects == []
    assert plan.cta is None


def test_reuses_valid_cached_chunk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "response": json.dumps({"candidates": [candidate()]}),
                "done_reason": "stop",
            }

    def post(*args: object, **kwargs: object) -> Response:
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen", cache_dir=tmp_path)

    assert provider.generate_structured("same prompt") == [candidate()]
    assert provider.generate_structured("same prompt") == [candidate()]
    assert calls == 1
