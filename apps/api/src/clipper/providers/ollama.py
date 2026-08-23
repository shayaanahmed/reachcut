from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from clipper.domain.editing_plan import EditingPlanV1, Hook, Scores, TimeRange
from clipper.domain.transcript import Transcript
from clipper.transcription import CancellationProbe, ProgressReporter


class EditorialCandidate(BaseModel):
    """Semantic ranking returned by the LLM; no media timing lives here."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    candidate_id: str = Field(pattern=r"^c[0-9]{4}$")
    scores: Scores
    rationale: str = Field(min_length=1, max_length=240)
    hook_text: str = Field(min_length=1, max_length=100)
    caption_style: Literal["clean", "kinetic_highlight", "karaoke"] = "clean"


class CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[EditorialCandidate] = Field(min_length=1, max_length=5)


@dataclass(frozen=True)
class CandidateOption:
    candidate_id: str
    source: TimeRange
    text: str


class EditorialOutputError(ValueError):
    """The local editorial model returned data outside the editorial contract."""


class OllamaEditorialProvider:
    CONTRACT_VERSION = "editorial-ranking-4"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 600,
        cache_dir: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.cache_dir = cache_dir

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}:{self.CONTRACT_VERSION}"

    def select_candidates(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: CancellationProbe,
        progress: ProgressReporter,
    ) -> list[EditingPlanV1]:
        if cancelled():
            raise InterruptedError("editorial selection cancelled")
        options = self._candidate_options(transcript)
        batches = self._candidate_batches(options)
        if not batches:
            raise EditorialOutputError("transcript contained no suitable candidate windows")
        options_by_id = {option.candidate_id: option for option in options}
        shortlists: list[dict[str, Any]] = []
        progress(0.02)
        for index, batch in enumerate(batches):
            if cancelled():
                raise InterruptedError("editorial selection cancelled")
            shortlists.extend(
                self.generate_structured(
                    self._batch_prompt(batch),
                    allowed_ids={option.candidate_id for option in batch},
                )
            )
            progress(0.82 * (index + 1) / len(batches))
        shortlist_limit = max(target_count * 3, 15)
        shortlists = sorted(
            shortlists,
            key=lambda item: int(item.get("scores", {}).get("overall", 0)),
            reverse=True,
        )[:shortlist_limit]
        reranked = self.generate_structured(
            self._rerank_prompt(shortlists, target_count),
            minimum_candidates=target_count,
            allowed_ids={item["candidate_id"] for item in shortlists},
        )
        progress(0.98)
        plans = [
            self.create_editing_plan(
                EditorialCandidate.model_validate(item), options_by_id[item["candidate_id"]]
            )
            for item in reranked
        ]
        if len(plans) < target_count:
            raise EditorialOutputError(
                f"editorial model returned {len(plans)} candidates; need {target_count}"
            )
        return plans[:target_count]

    def rank_options(self, options: list[CandidateOption]) -> list[dict[str, Any]]:
        """Rank supplied options through the provider's validated public contract."""

        return self.generate_structured(
            self._batch_prompt(options), allowed_ids={option.candidate_id for option in options}
        )

    def generate_structured(
        self,
        prompt: str,
        minimum_candidates: int = 1,
        allowed_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        cached = self._read_cache(prompt, minimum_candidates, allowed_ids)
        if cached is not None:
            return cached
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
                    valid, validation_errors = self.validate_candidates(decoded, allowed_ids)
                    if len(valid) >= minimum_candidates:
                        self._write_cache(prompt, valid)
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
                    "\nYour previous response was rejected by the editorial ranking contract: "
                    f"{detail}. Copy only candidate IDs supplied in the options."
                )
                continue
            done_reason = payload.get("done_reason", "unknown")
            raise EditorialOutputError(
                "editorial model failed the structured-output contract after 2 attempts "
                f"(reason={done_reason}; validation={detail})"
            )
        raise AssertionError("unreachable editorial retry state")

    @staticmethod
    def validate_candidates(
        decoded: Any, allowed_ids: set[str] | None = None
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not isinstance(decoded, dict) or set(decoded) != {"candidates"}:
            return [], ["root must be an object containing only candidates"]
        items = decoded["candidates"]
        if not isinstance(items, list):
            return [], ["candidates must be an array"]
        valid: list[dict[str, Any]] = []
        errors: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(items[:5]):
            try:
                candidate = EditorialCandidate.model_validate(item)
                if allowed_ids is not None and candidate.candidate_id not in allowed_ids:
                    raise ValueError("candidate_id was not present in the supplied options")
                if candidate.candidate_id in seen:
                    raise ValueError("candidate_id was duplicated")
                seen.add(candidate.candidate_id)
                valid.append(candidate.model_dump(mode="json"))
            except (ValidationError, ValueError) as error:
                if isinstance(error, ValidationError):
                    issue = error.errors(include_url=False)[0]
                    location = ".".join(str(part) for part in issue["loc"])
                    errors.append(f"candidate {index + 1} {location}: {issue['msg']}")
                else:
                    errors.append(f"candidate {index + 1}: {error}")
        return valid, errors

    def _cache_path(self, prompt: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(
            f"{self.CONTRACT_VERSION}\0{self.model}\0{prompt}".encode()
        ).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(
        self, prompt: str, minimum_candidates: int, allowed_ids: set[str] | None
    ) -> list[dict[str, Any]] | None:
        path = self._cache_path(prompt)
        if path is None or not path.is_file():
            return None
        try:
            decoded = json.loads(path.read_text())
            valid, _ = self.validate_candidates({"candidates": decoded}, allowed_ids)
        except (OSError, json.JSONDecodeError):
            return None
        return valid if len(valid) >= minimum_candidates else None

    def _write_cache(self, prompt: str, candidates: list[dict[str, Any]]) -> None:
        path = self._cache_path(prompt)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(candidates, indent=2) + "\n")

    @staticmethod
    def create_editing_plan(
        candidate: EditorialCandidate, option: CandidateOption
    ) -> EditingPlanV1:
        duration = option.source.end_seconds - option.source.start_seconds
        return EditingPlanV1(
            source=option.source,
            scores=candidate.scores,
            rationale=candidate.rationale,
            hook=Hook(
                text=candidate.hook_text,
                start_seconds=0,
                end_seconds=min(3.5, duration),
            ),
            caption_style=candidate.caption_style,
            emphasis=[],
            effects=[],
            cta=None,
        )

    @staticmethod
    def _candidate_options(transcript: Transcript) -> list[CandidateOption]:
        """Create stable 45-75 second windows before invoking the LLM."""
        segments = transcript.segments
        if not segments:
            return []
        options: list[CandidateOption] = []
        anchor = segments[0].start_seconds
        final_end = segments[-1].end_seconds
        start_index = 0
        while anchor + 20 <= final_end:
            while start_index + 1 < len(segments) and segments[start_index].end_seconds <= anchor:
                start_index += 1
            start_segment = segments[start_index]
            target_end = start_segment.start_seconds + 60
            maximum_end = start_segment.start_seconds + 75
            end_index = start_index
            natural_end: int | None = None
            while end_index < len(segments):
                segment = segments[end_index]
                if segment.end_seconds >= target_end and segment.text.rstrip().endswith(
                    (".", "?", "!", "؟", "۔")  # noqa: RUF001 - Urdu punctuation
                ):
                    natural_end = end_index
                    break
                if segment.end_seconds >= maximum_end:
                    break
                end_index += 1
            chosen_end = (
                natural_end if natural_end is not None else min(end_index, len(segments) - 1)
            )
            end_segment = segments[chosen_end]
            duration = end_segment.end_seconds - start_segment.start_seconds
            if 20 <= duration <= 180:
                options.append(
                    CandidateOption(
                        candidate_id=f"c{len(options):04d}",
                        source=TimeRange(
                            start_seconds=start_segment.start_seconds,
                            end_seconds=end_segment.end_seconds,
                        ),
                        text=" ".join(
                            segment.text for segment in segments[start_index : chosen_end + 1]
                        ),
                    )
                )
            anchor += 45
        return options

    @staticmethod
    def _candidate_batches(
        options: list[CandidateOption], max_chars: int = 8_000
    ) -> list[list[CandidateOption]]:
        batches: list[list[CandidateOption]] = []
        current: list[CandidateOption] = []
        size = 0
        for option in options:
            rendered_size = len(option.text) + 40
            if current and size + rendered_size > max_chars:
                batches.append(current)
                current, size = [], 0
            current.append(option)
            size += rendered_size
        if current:
            batches.append(current)
        return batches

    @staticmethod
    def _batch_prompt(options: list[CandidateOption]) -> str:
        rendered = "\n".join(f"[{option.candidate_id}] {option.text}" for option in options)
        return (
            "Rank exactly 3 of the supplied transcript options. Return only JSON as "
            '{"candidates":[EditorialCandidate,...]}. Copy candidate_id exactly and return scores, '
            "rationale, hook_text, and caption_style. Do not generate or change timestamps, "
            "boundaries, effects, or rendering instructions. Prefer coherent ideas with strong "
            "openings and natural endings. Scores are editorial heuristics. Use schema_version "
            "1.0. Options:\n" + rendered
        )

    @staticmethod
    def _rerank_prompt(items: list[dict[str, Any]], target_count: int) -> str:
        return (
            f"Choose {target_count} meaningfully different candidates from the following. "
            "Preserve candidate_id and EditorialCandidate structure. Return only "
            '{"candidates":[...]}; do not invent IDs, transcript moments, or render timings. '
            "Candidates:\n" + json.dumps(items, separators=(",", ":"))
        )
