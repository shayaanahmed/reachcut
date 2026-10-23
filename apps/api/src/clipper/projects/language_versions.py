"""Localize independent clips; originals and publications are never modified."""

from pathlib import Path

from sqlalchemy.orm import Session

from clipper.domain.editing_plan import EditingPlanV1, SecondaryMediaKind, TranslationMode
from clipper.domain.transcript import Transcript
from clipper.editorial.growth import AudienceProfile, GrowthBrief
from clipper.media.metadata import media_metadata
from clipper.persistence import Project, now_utc
from clipper.persistence.models import ClipGrowthBrief, GrowthPreparation
from clipper.projects.artifacts import timeline_words
from clipper.projects.clips import ClipService
from clipper.projects.pipeline import Pipeline
from clipper.projects.runtime_settings import RuntimeConfiguration
from clipper.projects.source_workflows import active_workflow
from clipper.projects.stages import StageRunner
from clipper.providers.localization import localize_copy
from clipper.providers.ollama_translation import OllamaCaptionTranslationProvider
from clipper.transcription import ProgressReporter


def localize_project(
    session: Session, project: Project, runtime: RuntimeConfiguration, clips: ClipService
) -> None:
    run = active_workflow(session, project.id)
    if not run or not run.target_language:
        raise ValueError(
            "Language workflow settings are missing; create a language version from its source"
        )
    language = run.target_language
    translator = OllamaCaptionTranslationProvider(
        runtime.ollama_base_url, runtime.model_for("translation"), 180
    )

    def translate(progress: ProgressReporter) -> dict[str, object]:
        for index, clip in enumerate(project.clips):
            if Pipeline._cancelled(session, project.id):
                raise InterruptedError("Project stopped")
            plan = EditingPlanV1.model_validate(clip.plan)
            if "metadata" in run.scopes:
                copy = localize_copy(
                    runtime.ollama_base_url,
                    runtime.model_for("translation"),
                    language,
                    plan.suggested_title or project.title,
                    plan.suggested_description or project.title,
                    plan.hashtags,
                )
                plan.suggested_title, plan.suggested_description, plan.hashtags = (
                    copy.title,
                    copy.description,
                    copy.hashtags or plan.hashtags,
                )
            if "subtitles" in run.scopes:
                transcript = Transcript.model_validate(project.transcript)
                words = timeline_words(transcript, plan.source_slices or [plan.source])
                if not words:
                    raise ValueError(
                        "No spoken transcript exists. Choose publishing copy only. "
                        "Text already baked into video frames is not translated by subtitles."
                    )
                text = " ".join(word.text for word in words)
                plan.caption_config.enabled = True
                plan.caption_config.source_language = transcript.language
                plan.caption_config.target_language = language
                plan.caption_config.translation_mode = TranslationMode.TRANSLATED
                plan.caption_config.translated_text = translator.translate(
                    text, transcript.language, language
                )
            # A fresh preview is needed only for media changes, never metadata-only translation.
            if "subtitles" in run.scopes:
                clips.apply_language_plan(session, clip, plan)
            else:
                clip.plan = plan.model_dump(mode="json")
            if "narration" in run.scopes:
                if not run.narration_path:
                    raise ValueError("Upload translated narration for this language version")
                audio = Path(run.narration_path)
                duration = float(media_metadata(audio).get("format", {}).get("duration", 0))
                if (
                    duration <= 0
                    or duration > plan.timeline_duration + 0.1
                    or plan.timeline_duration - duration > 2
                ):
                    raise ValueError(
                        "Translated narration must match the clip duration. "
                        "Upload audio no longer than the video, "
                        "and at most two seconds shorter."
                    )
                clean = EditingPlanV1.model_validate(clip.plan)
                clean.secondary_media = [
                    item
                    for item in clean.secondary_media
                    if item.kind != SecondaryMediaKind.VOICEOVER
                ]
                clip.plan = clean.model_dump(mode="json")
                with audio.open("rb") as stream:
                    clips.add_secondary_media(
                        session,
                        clip.id,
                        stream,
                        audio.name,
                        SecondaryMediaKind.VOICEOVER,
                        0,
                        plan.timeline_duration,
                        "audio",
                        volume_db=0,
                    )
                current = EditingPlanV1.model_validate(clip.plan)
                current.original_audio_volume = 0
                clips.apply_language_plan(session, clip, current)
            row = session.get(ClipGrowthBrief, clip.id)
            if not row:
                row = ClipGrowthBrief(clip_id=clip.id)
                session.add(row)
            row.payload = GrowthBrief(
                automatic=False, profile=AudienceProfile(language=language)
            ).model_dump(mode="json")
            job = session.get(GrowthPreparation, clip.id)
            if not job:
                job = GrowthPreparation(clip_id=clip.id)
                session.add(job)
            job.status, job.reasoning, job.updated_at = (
                "manual",
                "Language-version copy is preserved. Rerun this workflow to regenerate it.",
                now_utc(),
            )
            clip.approval_status = "pending"
            session.commit()
            progress((index + 1) / len(project.clips))
        return {"language": language, "scopes": run.scopes}

    StageRunner().run(
        session,
        project,
        "localize",
        Pipeline._key(run.id, language, runtime.model_for("translation")),
        translate,
        # Metadata preparation can reapply source-language copy during recovery.
        # Localization must therefore run again even if its prior artifact exists.
        validate_cached=lambda _: False,
    )
    title = (
        str(project.clips[0].plan.get("suggested_title") or run.source_title)
        if len(project.clips) == 1
        else run.source_title
    )
    project.title = f"{title[:160]} · {language}"
    project.status = "review"
    session.commit()
