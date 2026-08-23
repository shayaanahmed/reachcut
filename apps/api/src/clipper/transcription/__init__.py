"""Transcription contracts, models, and language-specific configuration."""

from clipper.domain.transcript import Segment, Transcript, Word
from clipper.transcription.contracts import (
    CancellationProbe,
    ProgressReporter,
    TranscriptionProvider,
)
from clipper.transcription.languages import TranscriptionLanguage, language_settings

__all__ = [
    "CancellationProbe",
    "ProgressReporter",
    "Segment",
    "Transcript",
    "TranscriptionLanguage",
    "TranscriptionProvider",
    "Word",
    "language_settings",
]
