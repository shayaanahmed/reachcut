"""Compatibility imports for the caption domain.

New code should import from :mod:`clipper.captions`.
"""

from clipper.captions import (
    CaptionCue,
    phrase_cues,
    serialize_ass,
    serialize_srt,
    serialize_vtt,
    subtitle_timestamp,
)

__all__ = [
    "CaptionCue",
    "phrase_cues",
    "serialize_ass",
    "serialize_srt",
    "serialize_vtt",
    "subtitle_timestamp",
]
