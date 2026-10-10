"""Editorial highlight selection public API."""

from clipper.editorial.clip_types import ClipTypeSuggestion, suggest_clip_types
from clipper.editorial.contracts import EditorialContext, EditorialLLMProvider
from clipper.editorial.highlights import TranscriptChunk, diverse_top_plans, semantic_windows
from clipper.editorial.modes import ModeSignals, infer_content_mode
from clipper.editorial.recommendations import PublishRecommendation, recommend_for_publishing

__all__ = [
    "ClipTypeSuggestion",
    "EditorialContext",
    "EditorialLLMProvider",
    "ModeSignals",
    "PublishRecommendation",
    "TranscriptChunk",
    "diverse_top_plans",
    "infer_content_mode",
    "recommend_for_publishing",
    "semantic_windows",
    "suggest_clip_types",
]
