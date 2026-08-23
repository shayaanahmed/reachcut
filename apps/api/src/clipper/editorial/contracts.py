from typing import Protocol

from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Transcript
from clipper.transcription.contracts import CancellationProbe, ProgressReporter


class EditorialLLMProvider(Protocol):
    """Port for selecting ranked highlights from a transcript."""

    @property
    def identity(self) -> str: ...

    def select_candidates(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: CancellationProbe,
        progress: ProgressReporter,
    ) -> list[EditingPlanV1]: ...
