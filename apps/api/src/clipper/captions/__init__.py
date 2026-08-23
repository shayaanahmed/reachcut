"""Caption domain public API.

Text grouping, animation event generation, and subtitle serialization are kept
separate so callers can test or replace one concern without invoking FFmpeg.
"""

from clipper.captions.ass import serialize_ass
from clipper.captions.formats import serialize_srt, serialize_vtt, subtitle_timestamp
from clipper.captions.models import CaptionCue
from clipper.captions.text import phrase_cues

__all__ = [
    "CaptionCue",
    "phrase_cues",
    "serialize_ass",
    "serialize_srt",
    "serialize_vtt",
    "subtitle_timestamp",
]
