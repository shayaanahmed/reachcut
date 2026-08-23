from collections.abc import Iterator
from pathlib import Path
from typing import Any

from clipper.domain.transcript import Segment, Transcript, Word
from clipper.transcription import CancellationProbe, ProgressReporter, language_settings


class FasterWhisperProvider:
    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        compute_type: str = "int8",
        language_hint: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language_hint = language_hint
        self._model: Any | None = None

    @property
    def identity(self) -> str:
        language = self.language_hint or "auto"
        return f"faster-whisper:{self.model_name}:{self.device}:{self.compute_type}:{language}"

    def _load(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            try:
                self._model = WhisperModel(
                    self.model_name, device=self.device, compute_type=self.compute_type
                )
            except Exception as error:
                detail = str(error)
                if "Hub" in detail or "snapshot folder" in detail:
                    raise RuntimeError(
                        f"Whisper model '{self.model_name}' is not available in the local cache. "
                        "For Docker, run `pnpm docker:whisper-model`, then retry analysis."
                    ) from error
                raise
        return self._model

    def transcribe(
        self, media: Path, cancelled: CancellationProbe, progress: ProgressReporter
    ) -> Transcript:
        progress(0.01)
        language = language_settings(self.language_hint)
        raw_segments, info = self._load().transcribe(
            str(media),
            language=language.code,
            task="transcribe",
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 350},
            beam_size=8,
            best_of=8,
            patience=1.2,
            condition_on_previous_text=True,
            initial_prompt=language.initial_prompt,
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
            if info.duration > 0:
                progress(min(item.end / info.duration, 0.99))
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
