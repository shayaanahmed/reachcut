from __future__ import annotations

from dataclasses import dataclass

from clipper.domain.editing_plan import ClipType
from clipper.domain.transcript import Transcript


@dataclass(frozen=True)
class ClipTypeSuggestion:
    clip_type: ClipType
    score: int
    reason: str


def suggest_clip_types(transcript: Transcript) -> list[ClipTypeSuggestion]:
    """Suggest editorial directions from transcript language without calling a provider."""

    text = " ".join(segment.text for segment in transcript.segments).casefold()
    signals: tuple[tuple[ClipType, tuple[str, ...], str], ...] = (
        (ClipType.FUNNY, ("laugh", "funny", "joke", "hilarious", "haha"), "Humorous language"),
        (ClipType.ADVICE, ("should", "advice", "recommend", "tip", "lesson"), "Actionable advice"),
        (ClipType.INSIGHT, ("realize", "insight", "because", "truth", "learned"), "Clear insight"),
        (ClipType.STORY, ("when i", "then", "story", "happened", "remember"), "Narrative moments"),
        (
            ClipType.DEBATE,
            ("disagree", "however", "but", "argument", "wrong"),
            "Contrasting viewpoints",
        ),
        (
            ClipType.EDUCATIONAL,
            ("how to", "step", "explain", "means", "example"),
            "Explanatory material",
        ),
        (ClipType.EMOTIONAL, ("felt", "love", "fear", "proud", "difficult"), "Emotional moments"),
        (
            ClipType.PROMOTIONAL,
            ("product", "customer", "buy", "launch", "offer"),
            "Product or offer moments",
        ),
    )
    suggestions = [
        ClipTypeSuggestion(
            clip_type=clip_type,
            score=min(98, 52 + sum(text.count(keyword) for keyword in keywords) * 9),
            reason=reason,
        )
        for clip_type, keywords, reason in signals
        if any(keyword in text for keyword in keywords)
    ]
    suggestions.append(
        ClipTypeSuggestion(
            clip_type=ClipType.HIGHLIGHT,
            score=70 if transcript.segments else 0,
            reason="Strong general-purpose moments",
        )
    )
    return sorted(suggestions, key=lambda item: item.score, reverse=True)[:6]
