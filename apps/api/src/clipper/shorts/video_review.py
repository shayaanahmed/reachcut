"""Typed final-cut assessments and conservative automatic copy refinements."""

import re

from pydantic import Field

from clipper.shorts.contracts import Strict
from clipper.shorts.frames import FrameContent


class VideoIssue(Strict):
    scene: int = Field(ge=1, le=6)
    severity: str = Field(pattern="^(blocking|suggestion)$")
    message: str = Field(min_length=1, max_length=400)


class CopyRefinement(Strict):
    scene: int = Field(ge=1, le=6)
    field: str = Field(pattern="^(caption|title|eyebrow)$")
    text: str = Field(min_length=1, max_length=90)


class FinalVideoAssessment(Strict):
    publishable: bool
    summary: str = Field(min_length=1, max_length=700)
    hook_score: int = Field(ge=0, le=100)
    clarity_score: int = Field(ge=0, le=100)
    pacing_score: int = Field(ge=0, le=100)
    shareability_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    issues: list[VideoIssue] = Field(default_factory=list, max_length=8)
    refinements: list[CopyRefinement] = Field(default_factory=list, max_length=6)

    @property
    def passed(self) -> bool:
        return self.publishable and not any(i.severity == "blocking" for i in self.issues)


def refine_copy(frame: FrameContent, fix: CopyRefinement) -> FrameContent:
    """Only shorten an existing phrase; preserve factual wording and qualifiers."""
    original = str(getattr(frame, fix.field))
    text = fix.text.strip()
    if text not in original or len(text) >= len(original):
        raise ValueError("Automatic refinements must shorten an existing phrase")
    qualifiers = re.findall(
        r"\b(?:not|never|without|cannot|can't|could|may|might|only|if|unless)\b", original, re.I
    )
    if any(word.casefold() not in text.casefold().split() for word in qualifiers):
        raise ValueError("Automatic refinements must preserve factual qualifiers")
    return FrameContent.model_validate({**frame.model_dump(), fix.field: text})
