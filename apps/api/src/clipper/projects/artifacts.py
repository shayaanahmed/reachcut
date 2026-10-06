import json
from dataclasses import dataclass
from pathlib import Path

from clipper.captions import (
    bilingual_cues,
    phrase_cues,
    retime_text,
    serialize_ass,
    serialize_srt,
    serialize_vtt,
)
from clipper.domain.editing_plan import EditingPlanV1, TimeRange, TranslationMode
from clipper.domain.transcript import Transcript, Word
from clipper.persistence import Clip, Project


@dataclass(frozen=True)
class ArtifactProvenance:
    transcription: str
    editorial: str


class ClipArtifactService:
    """Create deterministic plan and caption artifacts for one clip."""

    def __init__(self, provenance: ArtifactProvenance) -> None:
        self._provenance = provenance

    def write(
        self, project: Project, clip: Clip, plan: EditingPlanV1, transcript: Transcript
    ) -> Path:
        root = Path(project.source_path).parent / "clips" / clip.id
        root.mkdir(parents=True, exist_ok=True)
        (root / "editing-plan.json").write_text(plan.model_dump_json(indent=2) + "\n")
        words = timeline_words(transcript, plan.source_slices or [plan.source])
        if plan.caption_config.text_override is not None:
            words = retime_text(words, plan.caption_config.text_override)
        cues = phrase_cues(words, max_words=plan.caption_config.max_words_per_line)
        if plan.caption_config.translated_text:
            translated_words = retime_text(words, plan.caption_config.translated_text)
            translated_cues = phrase_cues(
                translated_words, max_words=plan.caption_config.max_words_per_line
            )
            if plan.caption_config.translation_mode is TranslationMode.TRANSLATED:
                cues = translated_cues
            elif plan.caption_config.translation_mode is TranslationMode.BILINGUAL:
                cues = bilingual_cues(cues, translated_cues)
        (root / "captions.srt").write_text(serialize_srt(cues))
        (root / "captions.vtt").write_text(serialize_vtt(cues))
        (root / "captions.ass").write_text(
            serialize_ass(
                cues,
                plan.caption_config,
                plan.emphasis,
                plan.hook,
                plan.cta,
                plan.effects,
            ),
            encoding="utf-8",
        )
        provenance = {
            "transcription": self._provenance.transcription,
            "editorial": self._provenance.editorial,
            "caption_language": {
                "source": plan.caption_config.source_language or transcript.language,
                "target": plan.caption_config.target_language,
                "mode": plan.caption_config.translation_mode,
            },
            "media_sha256": project.media_sha256,
            "assets": [],
        }
        (root / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        return root


def relative_words(transcript: Transcript, start: float, end: float) -> list[Word]:
    """Select clip words and translate their timings to the clip timeline."""

    return timeline_words(transcript, [TimeRange(start_seconds=start, end_seconds=end)])


def timeline_words(transcript: Transcript, slices: list[TimeRange]) -> list[Word]:
    """Select words from ordered source slices and place them on one continuous timeline."""

    words: list[Word] = []
    offset = 0.0
    for source_slice in slices:
        duration = source_slice.end_seconds - source_slice.start_seconds
        for segment in transcript.segments:
            for word in segment.words:
                if (
                    word.end_seconds > source_slice.start_seconds
                    and word.start_seconds < source_slice.end_seconds
                ):
                    words.append(
                        word.model_copy(
                            update={
                                "start_seconds": offset
                                + max(0, word.start_seconds - source_slice.start_seconds),
                                "end_seconds": offset
                                + min(
                                    duration,
                                    word.end_seconds - source_slice.start_seconds,
                                ),
                            }
                        )
                    )
        offset += duration
    return words
