"""Versioned, provider-independent informative video artifacts."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Strict):
    id: str = Field(min_length=1, max_length=80)
    url: str = Field(pattern=r"^https://", max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    retrieved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    text: str = Field(min_length=20, max_length=20000)
    published_at: str | None = None
    kind: Literal["primary", "research", "historical", "other"] = "other"


class Claim(Strict):
    text: str = Field(min_length=1, max_length=2000)
    source_id: str
    quote: str = Field(min_length=10, max_length=2000)
    status: Literal["supported", "interpretation", "disputed", "unresolved"] = "unresolved"


class Section(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    text: str = Field(min_length=1, max_length=2000)
    heading: str = Field(min_length=1, max_length=100)
    claims: list[Claim] = Field(default_factory=list, max_length=20)
    visual: Literal["explanation", "screenshot", "recording", "diagram", "timeline", "map"] = (
        "explanation"
    )


class Script(Strict):
    version: Literal["1"] = "1"
    sections: list[Section] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_ids(self) -> "Script":
        if len({s.id for s in self.sections}) != len(self.sections):
            raise ValueError("Script section IDs must be unique")
        return self


class ShortSettings(Strict):
    category: Literal["tech", "psychology", "history"] = "tech"
    style: Literal["demo", "explainer", "timeline"] = "demo"
    language: str = Field(default="en", min_length=2, max_length=20)
    duration: int = Field(default=45, ge=30, le=60)
    narration_mode: Literal["none", "voicebox"] = "voicebox"
    profile_id: str = Field(default="", max_length=100)
    engine: str = Field(default="qwen", max_length=50)
    model_size: str = Field(default="1.7B", max_length=20)
    delivery: str = Field(default="", max_length=500)
    pronunciations: dict[str, str] = Field(default_factory=dict)
    audience: str = Field(default="General audience", max_length=500)
    tone: str = Field(default="Clear and factual", max_length=500)
    caption_font: str = Field(default="Noto Sans", min_length=1, max_length=80)
    accent: str = Field(default="#60A5FA", pattern=r"^#[0-9a-fA-F]{6}$")
    destinations: list[str] = Field(default_factory=list)
    allow_explanation_cards: bool = False
    max_attempts: int = Field(default=2, ge=1, le=3)
    spend_limit_usd: float = Field(default=0, ge=0, le=100)


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def script_issues(
    script: Script, sources: list[Evidence], *, require_claims: bool = True
) -> list[dict[str, str]]:
    """Quoted evidence is traceable, not an automatic verdict of truth."""
    lookup = {s.id: s for s in sources}
    issues: list[dict[str, str]] = []
    for section in script.sections:
        if require_claims and not section.claims:
            issues.append({"section": section.id, "message": "No claim evidence linked"})
        for claim in section.claims:
            source = lookup.get(claim.source_id)
            if not source or " ".join(claim.quote.split()) not in " ".join(source.text.split()):
                issues.append({"section": section.id, "message": "Evidence quote not in source"})
            if claim.status != "supported":
                issues.append({"section": section.id, "message": f"Claim is {claim.status}"})
    return issues


def speech_input(text: str, pronunciations: dict[str, str]) -> str:
    import re

    for term in sorted(pronunciations, key=len, reverse=True):
        if term:
            replacement = pronunciations[term]
            text = re.sub(
                r"(?<!\w)" + re.escape(term) + r"(?!\w)", replacement.replace("\\", "\\\\"), text
            )
    return text


class ResearchProvider(Protocol):
    def retrieve(self, urls: list[str]) -> list[Evidence]: ...


class ScriptProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def draft(self, topic: str, settings: ShortSettings, sources: list[Evidence]) -> Script: ...


class NarrationProvider(Protocol):
    def capabilities(self) -> dict[str, object]: ...
    def submit(self, text: str, settings: ShortSettings) -> str: ...
    def status(self, generation_id: str) -> str: ...
    def audio(self, generation_id: str) -> bytes: ...
    def cancel(self, generation_id: str) -> bool: ...
