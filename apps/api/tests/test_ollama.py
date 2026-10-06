import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from clipper.domain.editing_plan import TimeRange
from clipper.domain.transcript import Segment, Transcript
from clipper.editorial import EditorialContext
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
        "suggested_title": "The Useful Idea You Should Know",
        "hashtags": ["#UsefulTips", "#LearnSomething", "#VideoClip"],
        "caption_style": "clean",
        "cta_text": "Follow for more",
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
    assert r"\s" not in json.dumps(schema)


def test_surfaces_ollama_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "http://127.0.0.1:11434/api/generate")
    response = httpx.Response(
        400,
        request=request,
        json={"error": "Failed to initialize samplers: failed to parse grammar"},
    )
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: response)
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")

    with pytest.raises(EditorialOutputError, match="failed to parse grammar"):
        provider.generate_structured("test prompt")


def test_retries_truncated_json_with_larger_generation_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return self.payload

    responses = iter(
        [
            Response({"response": '{"candidates":[', "done_reason": "length"}),
            Response(
                {
                    "response": json.dumps({"candidates": [candidate()]}),
                    "done_reason": "stop",
                }
            ),
        ]
    )

    def post(*args: object, **kwargs: object) -> Response:
        requests.append(kwargs["json"])  # type: ignore[arg-type]
        return next(responses)

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")

    assert provider.generate_structured("test prompt") == [candidate()]
    assert requests[0]["options"] == {
        "temperature": 0.1,
        "num_ctx": 8_192,
        "num_predict": 2_048,
    }
    assert requests[1]["options"] == {
        "temperature": 0.1,
        "num_ctx": 16_384,
        "num_predict": 4_096,
    }
    assert "previous response was truncated" in requests[1]["prompt"]


def test_recovers_complete_candidate_from_truncated_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "response": (
                    '{"candidates":[' + json.dumps(candidate()) + ',{"candidate_id":"c0001"'
                ),
                "done_reason": "length",
            }

    def post(*args: object, **kwargs: object) -> Response:
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr("httpx.post", post)
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")

    assert provider.generate_structured("test prompt") == [candidate()]
    assert calls == 1


def test_short_batch_requests_only_available_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

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
    option = CandidateOption(
        candidate_id="c0000",
        source=TimeRange(start_seconds=0, end_seconds=60),
        text="One available transcript window.",
    )

    assert provider.rank_options([option]) == [candidate()]
    assert "Rank exactly 1 of the supplied transcript options" in requests[0]["prompt"]
    assert "suggested_title" in requests[0]["prompt"]
    assert "3-6 distinct, relevant, ready-to-paste hashtags" in requests[0]["prompt"]


def test_batch_prompt_uses_project_context_without_changing_boundaries() -> None:
    option = CandidateOption(
        candidate_id="c0000",
        source=TimeRange(start_seconds=15, end_seconds=45),
        text="He explains why it matters.",
    )

    prompt = OllamaEditorialProvider._batch_prompt(
        [option], EditorialContext("Interview with Ada", "ada-interview.mp4")
    )

    assert "Interview with Ada" in prompt
    assert "ada-interview.mp4" in prompt
    assert "do not invent unsupported facts" in prompt
    assert "Do not generate or change timestamps" in prompt
    assert "For goal=views" in prompt
    assert "For goal=revenue" in prompt


def test_short_video_returns_available_highlights_instead_of_requiring_five(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")
    requested_minimums: list[int] = []

    def generate(
        prompt: str,
        minimum_candidates: int = 1,
        allowed_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        requested_minimums.append(minimum_candidates)
        return [candidate(next(iter(allowed_ids or {"c0000"})))]

    monkeypatch.setattr(provider, "generate_structured", generate)
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=0,
                text="A complete short highlight.",
                start_seconds=0,
                end_seconds=60,
                words=[],
            )
        ],
    )

    plans = provider.select_candidates(transcript, 5, lambda: False, lambda progress: None)

    assert len(plans) == 1
    assert requested_minimums == [1, 1]


def test_repeated_length_failures_use_deterministic_highlight_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")

    def fail_generation(
        prompt: str,
        minimum_candidates: int = 1,
        allowed_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        raise EditorialOutputError(
            "fixture truncation",
            reason="length",
            validation="response field was not valid JSON",
        )

    monkeypatch.setattr(provider, "generate_structured", fail_generation)
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=0,
                text="A complete short highlight with a natural ending.",
                start_seconds=0,
                end_seconds=60,
                words=[],
            )
        ],
    )

    plans = provider.select_candidates(transcript, 5, lambda: False, lambda progress: None)

    assert len(plans) == 1
    assert plans[0].source == TimeRange(start_seconds=0, end_seconds=30)
    assert "Ollama output was truncated" in plans[0].rationale


def test_non_length_contract_failures_are_not_silently_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OllamaEditorialProvider("http://127.0.0.1:11434", "qwen")

    def fail_generation(
        prompt: str,
        minimum_candidates: int = 1,
        allowed_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        raise EditorialOutputError("invalid IDs", reason="stop", validation="invented ID")

    monkeypatch.setattr(provider, "generate_structured", fail_generation)
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=0,
                text="A complete short highlight.",
                start_seconds=0,
                end_seconds=60,
                words=[],
            )
        ],
    )

    with pytest.raises(EditorialOutputError, match="invalid IDs"):
        provider.select_candidates(transcript, 5, lambda: False, lambda progress: None)


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


def test_rejects_duplicate_hashtags() -> None:
    duplicate_hashtags = candidate()
    duplicate_hashtags["hashtags"] = ["#UsefulTips", "#usefultips", "#VideoClip"]

    valid, errors = OllamaEditorialProvider.validate_candidates(
        {"candidates": [duplicate_hashtags]}
    )

    assert valid == []
    assert "hashtags must be distinct" in errors[0]


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
    assert plan.hook.render is True
    assert plan.optimization_goal == "views"
    assert plan.frame_style == "center_crop"
    assert plan.suggested_title == "The Useful Idea You Should Know"
    assert plan.hashtags == ["#UsefulTips", "#LearnSomething", "#VideoClip"]
    assert plan.emphasis == []
    assert plan.effects[0].type == "punch_zoom"
    assert plan.cta is not None
    assert plan.cta.text == "Follow for more"
    assert plan.cta.render is True


def test_candidate_windows_include_views_and_revenue_versions() -> None:
    transcript = Transcript(
        language="en",
        provider="fixture",
        model="fixture",
        segments=[
            Segment(
                id=index,
                text=f"Complete thought {index}.",
                start_seconds=index * 10,
                end_seconds=(index + 1) * 10,
                words=[],
            )
            for index in range(12)
        ],
    )

    options = OllamaEditorialProvider._candidate_options(transcript)

    assert {option.optimization_goal for option in options} == {"views", "revenue"}
    assert all(
        15 <= option.source.end_seconds - option.source.start_seconds <= 40
        for option in options
        if option.optimization_goal == "views"
    )
    assert all(
        61 <= option.source.end_seconds - option.source.start_seconds <= 90
        for option in options
        if option.optimization_goal == "revenue"
    )


def test_auto_curation_removes_internal_filler_repetition_and_dead_air() -> None:
    segments = [
        Segment(id=0, text="A useful point", start_seconds=0, end_seconds=5, words=[]),
        Segment(id=1, text="um like", start_seconds=5, end_seconds=7, words=[]),
        Segment(id=2, text="A useful point", start_seconds=7, end_seconds=12, words=[]),
        Segment(id=3, text="The payoff", start_seconds=12, end_seconds=18, words=[]),
        Segment(id=4, text="Final thought", start_seconds=18, end_seconds=22, words=[]),
    ]

    slices = OllamaEditorialProvider._curated_slices(segments)

    assert slices == (
        TimeRange(start_seconds=0, end_seconds=5),
        TimeRange(start_seconds=12, end_seconds=22),
    )


def test_goal_mix_keeps_one_candidate_for_each_available_version() -> None:
    options = {
        "c0000": CandidateOption(
            "c0000", TimeRange(start_seconds=0, end_seconds=30), "Views.", "views"
        ),
        "c0001": CandidateOption(
            "c0001", TimeRange(start_seconds=0, end_seconds=70), "Revenue.", "revenue"
        ),
        "c0002": CandidateOption(
            "c0002", TimeRange(start_seconds=30, end_seconds=60), "Views two.", "views"
        ),
    }

    selected = OllamaEditorialProvider._ensure_goal_mix(
        [candidate("c0000", 95), candidate("c0002", 94)],
        [candidate("c0000", 95), candidate("c0002", 94), candidate("c0001", 80)],
        options,
        2,
    )

    assert {options[item["candidate_id"]].optimization_goal for item in selected} == {
        "views",
        "revenue",
    }


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
