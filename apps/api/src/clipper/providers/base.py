from typing import Protocol

from clipper.editorial import EditorialLLMProvider
from clipper.transcription import CancellationProbe, ProgressReporter, TranscriptionProvider

__all__ = [
    "CancellationProbe",
    "EditorialLLMProvider",
    "ProgressReporter",
    "TranscriptionProvider",
]


class VisionLanguageProvider(Protocol):
    @property
    def identity(self) -> str: ...


class DiarizationProvider(Protocol):
    @property
    def identity(self) -> str: ...


class FaceTrackingProvider(Protocol):
    @property
    def identity(self) -> str: ...
