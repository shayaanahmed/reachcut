from __future__ import annotations

import json
from typing import Any

import httpx

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.providers.base import CancellationProbe


class OllamaEditorialProvider:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}"

    def select_candidates(
        self, transcript: Transcript, target_count: int, cancelled: CancellationProbe
    ) -> list[EditingPlanV1]:
        if cancelled():
            raise InterruptedError("editorial selection cancelled")
        chunks = self._chunks(transcript)
        shortlists: list[dict[str, Any]] = []
        for chunk in chunks:
            if cancelled():
                raise InterruptedError("editorial selection cancelled")
            shortlists.extend(self._generate(self._chunk_prompt(chunk)))
        reranked = self._generate(self._rerank_prompt(shortlists, target_count))
        plans = [EditingPlanV1.model_validate(item) for item in reranked]
        if len(plans) < target_count:
            raise ValueError(
                f"editorial model returned {len(plans)} candidates; need {target_count}"
            )
        return plans[:target_count]

    def _generate(self, prompt: str) -> list[dict[str, Any]]:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        raw = json.loads(response.json()["response"])
        items = raw.get("candidates")
        if not isinstance(items, list):
            raise ValueError("editorial model response must contain a candidates array")
        return items

    @staticmethod
    def _chunks(transcript: Transcript, max_chars: int = 14_000) -> list[str]:
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
            "emphasis, effects, and CTA timestamps are relative to the excerpt. Prefer coherent "
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
