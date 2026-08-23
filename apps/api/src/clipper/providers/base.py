from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript


class CancellationProbe(Protocol):
    def __call__(self) -> bool: ...


type ProgressReporter = Callable[[float], None]


class TranscriptionProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def transcribe(
        self, media: Path, cancelled: CancellationProbe, progress: ProgressReporter
    ) -> Transcript: ...


class EditorialLLMProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def select_candidates(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: CancellationProbe,
        progress: ProgressReporter,
    ) -> list[EditingPlanV1]: ...


class VisionLanguageProvider(Protocol):
    @property
    def identity(self) -> str: ...


class DiarizationProvider(Protocol):
    @property
    def identity(self) -> str: ...


class FaceTrackingProvider(Protocol):
    @property
    def identity(self) -> str: ...
