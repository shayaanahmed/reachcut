import json
from dataclasses import dataclass
from pathlib import Path

from clipper.captions import phrase_cues, serialize_ass, serialize_srt, serialize_vtt
from clipper.domain.editing_plan import EditingPlanV1
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
        words = relative_words(transcript, plan.source.start_seconds, plan.source.end_seconds)
        cues = phrase_cues(words, max_words=plan.caption_config.max_words_per_line)
        (root / "captions.srt").write_text(serialize_srt(cues))
        (root / "captions.vtt").write_text(serialize_vtt(cues))
        (root / "captions.ass").write_text(
            serialize_ass(cues, plan.caption_config, plan.emphasis), encoding="utf-8"
        )
        provenance = {
            "transcription": self._provenance.transcription,
            "editorial": self._provenance.editorial,
            "media_sha256": project.media_sha256,
            "assets": [],
        }
        (root / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        return root


def relative_words(transcript: Transcript, start: float, end: float) -> list[Word]:
    """Select clip words and translate their timings to the clip timeline."""

    words: list[Word] = []
    for segment in transcript.segments:
        for word in segment.words:
            if word.end_seconds > start and word.start_seconds < end:
                words.append(
                    word.model_copy(
                        update={
                            "start_seconds": max(0, word.start_seconds - start),
                            "end_seconds": min(end - start, word.end_seconds - start),
                        }
                    )
                )
    return words
