from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.providers.base import CancellationProbe, ProgressReporter


class CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[EditingPlanV1] = Field(min_length=1, max_length=25)


class EditorialOutputError(ValueError):
    """The local editorial model returned data outside the rendering contract."""


class OllamaEditorialProvider:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}"

    def select_candidates(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: CancellationProbe,
        progress: ProgressReporter,
    ) -> list[EditingPlanV1]:
        if cancelled():
            raise InterruptedError("editorial selection cancelled")
        chunks = self._chunks(transcript)
        if not chunks:
            raise EditorialOutputError("transcript contained no editorial text")
        shortlists: list[dict[str, Any]] = []
        progress(0.02)
        for index, chunk in enumerate(chunks):
            if cancelled():
                raise InterruptedError("editorial selection cancelled")
            shortlists.extend(self._generate(self._chunk_prompt(chunk)))
            progress(0.82 * (index + 1) / len(chunks))
        shortlist_limit = max(target_count * 3, 15)
        shortlists = sorted(
            shortlists,
            key=lambda item: int(item.get("scores", {}).get("overall", 0)),
            reverse=True,
        )[:shortlist_limit]
        reranked = self._generate(
            self._rerank_prompt(shortlists, target_count), minimum_candidates=target_count
        )
        progress(0.98)
        plans = [EditingPlanV1.model_validate(item) for item in reranked]
        if len(plans) < target_count:
            raise ValueError(
                f"editorial model returned {len(plans)} candidates; need {target_count}"
            )
        return plans[:target_count]

    def _generate(self, prompt: str, minimum_candidates: int = 1) -> list[dict[str, Any]]:
        validation_hint = ""
        for attempt in range(2):
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt + validation_hint,
                    "stream": False,
                    "think": False,
                    "format": CandidateEnvelope.model_json_schema(),
                    "options": {"temperature": 0.1, "num_ctx": 8_192, "num_predict": 2_048},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("response")
            if not isinstance(content, str):
                detail = "response field was not a string"
            else:
                try:
                    decoded = json.loads(content)
                    valid, validation_errors = self._validated_candidates(decoded)
                    if len(valid) >= minimum_candidates:
                        return valid
                    detail = (
                        f"only {len(valid)} of {minimum_candidates} required candidates were valid"
                    )
                    if validation_errors:
                        detail += f"; {'; '.join(validation_errors[:3])}"
                except json.JSONDecodeError:
                    detail = "response field was not valid JSON"
            if attempt == 0:
                validation_hint = (
                    "\nYour previous response was rejected by the JSON contract: "
                    f"{detail}. Return a corrected object matching the supplied schema exactly."
                )
                continue
            done_reason = payload.get("done_reason", "unknown")
            raise EditorialOutputError(
                "editorial model failed the structured-output contract after 2 attempts "
                f"(reason={done_reason}; validation={detail})"
            )
        raise AssertionError("unreachable editorial retry state")

    @staticmethod
    def _validated_candidates(decoded: Any) -> tuple[list[dict[str, Any]], list[str]]:
        if not isinstance(decoded, dict) or set(decoded) != {"candidates"}:
            return [], ["root must be an object containing only candidates"]
        items = decoded["candidates"]
        if not isinstance(items, list):
            return [], ["candidates must be an array"]
        valid: list[dict[str, Any]] = []
        errors: list[str] = []
        for index, item in enumerate(items[:25]):
            try:
                plan = EditingPlanV1.model_validate(
                    OllamaEditorialProvider._normalize_relative_timestamps(item)
                )
                valid.append(plan.model_dump(mode="json"))
            except ValidationError as error:
                issue = error.errors(include_url=False)[0]
                location = ".".join(str(part) for part in issue["loc"])
                errors.append(f"candidate {index + 1} {location}: {issue['msg']}")
        return valid, errors

    @staticmethod
    def _normalize_relative_timestamps(item: Any) -> Any:
        """Repair only unambiguous absolute-to-relative timestamp mistakes.

        Source boundaries are absolute media timestamps. Nested hook, emphasis,
        effect, and CTA timestamps are relative to the selected clip. Local models
        sometimes copy absolute transcript timestamps into every field despite the
        prompt. Values wholly inside the source interval can be converted safely;
        anything ambiguous is left unchanged for strict schema validation to reject.
        """
        if not isinstance(item, dict):
            return item
        source = item.get("source")
        if not isinstance(source, dict):
            return item
        source_start = source.get("start_seconds")
        source_end = source.get("end_seconds")
        if not isinstance(source_start, int | float) or not isinstance(source_end, int | float):
            return item
        if source_start < 0 or source_end <= source_start:
            return item

        normalized = dict(item)
        duration = source_end - source_start

        def normalize_range(value: Any) -> Any:
            if not isinstance(value, dict):
                return value
            start = value.get("start_seconds")
            end = value.get("end_seconds")
            if not isinstance(start, int | float) or not isinstance(end, int | float):
                return value
            if 0 <= start < end <= duration:
                return value
            if source_start <= start < end <= source_end:
                return {
                    **value,
                    "start_seconds": start - source_start,
                    "end_seconds": end - source_start,
                }
            return value

        for name in ("hook", "cta"):
            if name in normalized:
                normalized[name] = normalize_range(normalized[name])
        emphasis = normalized.get("emphasis")
        if isinstance(emphasis, list):
            normalized["emphasis"] = [normalize_range(value) for value in emphasis]
        effects = normalized.get("effects")
        if isinstance(effects, list):
            normalized_effects: list[Any] = []
            for effect in effects:
                if not isinstance(effect, dict):
                    normalized_effects.append(effect)
                    continue
                time = effect.get("time_seconds")
                if (
                    isinstance(time, int | float)
                    and time > duration
                    and source_start <= time <= source_end
                ):
                    effect = {**effect, "time_seconds": time - source_start}
                normalized_effects.append(effect)
            normalized["effects"] = normalized_effects
        return normalized

    @staticmethod
    def _chunks(transcript: Transcript, max_chars: int = 8_000) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        size = 0
        for segment in transcript.segments:
            line = f"[{segment.start_seconds:.2f}-{segment.end_seconds:.2f}] {segment.text}"
            if current and size + len(line) > max_chars:
                chunks.append("\n".join(current))
                current, size = [], 0
            current.append(line)
            size += len(line)
        if current:
            chunks.append("\n".join(current))
        return chunks

    @staticmethod
    def _chunk_prompt(chunk: str) -> str:
        return (
            "Find up to 5 self-contained 20-180 second excerpts. Return only JSON as "
            '{"candidates":[EditingPlanV1,...]}. Timestamps in source are absolute; hook, '
            "emphasis, effects, and CTA timestamps are relative to the excerpt: the clip always "
            "starts at 0.0, so never copy an absolute source timestamp into those nested fields. "
            "For example, source 300-360 has a hook at 0-3, not 300-303. Prefer coherent "
            "ideas with strong openings and natural endings. Scores are editorial heuristics. "
            "Use schema_version 1.0, caption_style clean, no effects unless clearly justified, "
            "and include a concise rationale. Transcript:\n" + chunk
        )

    @staticmethod
    def _rerank_prompt(items: list[dict[str, Any]], target_count: int) -> str:
        return (
            f"Choose {target_count} meaningfully different, non-overlapping candidates from the "
            "following. Preserve the EditingPlanV1 object structure, improve invalid boundaries, "
            'and return only {"candidates":[...]}. Do not invent transcript moments. Candidates:\n'
            + json.dumps(items, separators=(",", ":"))
        )
