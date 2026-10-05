"""Editorial highlight selection public API."""

from clipper.editorial.contracts import EditorialLLMProvider
from clipper.editorial.highlights import TranscriptChunk, diverse_top_plans, semantic_windows
from clipper.editorial.recommendations import PublishRecommendation, recommend_for_publishing

__all__ = [
    "EditorialLLMProvider",
    "PublishRecommendation",
    "TranscriptChunk",
    "diverse_top_plans",
    "recommend_for_publishing",
    "semantic_windows",
]
