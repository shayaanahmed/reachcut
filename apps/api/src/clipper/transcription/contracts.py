from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from clipper.domain.transcript import Transcript


class CancellationProbe(Protocol):
    def __call__(self) -> bool: ...


type ProgressReporter = Callable[[float], None]


class TranscriptionProvider(Protocol):
    """Port implemented by local or remote speech-to-text adapters."""

    @property
    def identity(self) -> str: ...

    def transcribe(
        self, media: Path, cancelled: CancellationProbe, progress: ProgressReporter
    ) -> Transcript: ...
