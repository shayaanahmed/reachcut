from collections.abc import Iterator
from pathlib import Path
from typing import Any

from clipper.domain.transcript import Segment, Transcript, Word
from clipper.providers.base import CancellationProbe


class FasterWhisperProvider:
    def __init__(self, model_name: str, device: str = "cpu", compute_type: str = "int8") -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model: Any | None = None

    @property
    def identity(self) -> str:
        return f"faster-whisper:{self.model_name}:{self.device}:{self.compute_type}"

    def _load(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, media: Path, cancelled: CancellationProbe) -> Transcript:
        raw_segments, info = self._load().transcribe(
            str(media), word_timestamps=True, vad_filter=True, beam_size=5
        )
        segments: list[Segment] = []
        for index, item in enumerate(self._checked(raw_segments, cancelled)):
            words = [
                Word(
                    text=word.word.strip(),
                    start_seconds=word.start,
                    end_seconds=word.end,
                    probability=word.probability,
                )
                for word in (item.words or [])
            ]
            segments.append(
                Segment(
                    id=index,
                    text=item.text.strip(),
                    start_seconds=item.start,
                    end_seconds=item.end,
                    words=words,
                )
            )
        return Transcript(
            language=info.language,
            language_probability=info.language_probability,
            segments=segments,
            provider="faster-whisper",
            model=self.model_name,
        )

    @staticmethod
    def _checked(items: Iterator[Any], cancelled: CancellationProbe) -> Iterator[Any]:
        for item in items:
            if cancelled():
                raise InterruptedError("transcription cancelled")
            yield item
