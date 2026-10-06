"""Caption domain public API.

Text grouping, animation event generation, and subtitle serialization are kept
separate so callers can test or replace one concern without invoking FFmpeg.
"""

from clipper.captions.ass import serialize_ass
from clipper.captions.formats import serialize_srt, serialize_vtt, subtitle_timestamp
from clipper.captions.models import CaptionCue
from clipper.captions.presets import caption_config_for_preset, caption_preset_for_mode
from clipper.captions.text import bilingual_cues, phrase_cues, retime_text
from clipper.captions.translation import CaptionTranslationProvider

__all__ = [
    "CaptionCue",
    "CaptionTranslationProvider",
    "bilingual_cues",
    "caption_config_for_preset",
    "caption_preset_for_mode",
    "phrase_cues",
    "retime_text",
    "serialize_ass",
    "serialize_srt",
    "serialize_vtt",
    "subtitle_timestamp",
]
