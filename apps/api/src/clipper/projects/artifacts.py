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


class ArtifactPathError(ValueError):
    pass


def resolve_clip_artifact(
    projects_root: Path,
    project: Project,
    clip: Clip,
    stored_path: str,
    expected_filename: str,
) -> Path:
    """Resolve a persisted clip artifact only when it is the expected owned file."""

    projects_root = projects_root.resolve()
    expected_project_root = projects_root / project.id
    if expected_project_root.parent != projects_root:
        raise ArtifactPathError("project identifier is not an owned directory name")

    expected_source_dir = expected_project_root / "source"
    source_path = Path(project.source_path)
    try:
        resolved_source_dir = expected_source_dir.resolve(strict=True)
        resolved_source = source_path.resolve(strict=True)
    except OSError as error:
        raise ArtifactPathError("project source path is unavailable") from error
    if (
        resolved_source_dir != expected_source_dir
        or resolved_source.parent != expected_source_dir
        or not resolved_source.is_file()
    ):
        raise ArtifactPathError("project source path is outside its owned directory")

    expected = expected_source_dir / "clips" / clip.id / expected_filename
    candidate = Path(stored_path)
    if candidate.is_symlink():
        raise ArtifactPathError("clip artifact cannot be a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ArtifactPathError("clip artifact is unavailable") from error
    if resolved != expected or not resolved.is_file():
        raise ArtifactPathError("clip artifact is outside its owned directory")
    return resolved


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
