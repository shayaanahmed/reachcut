from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.captions.quality import inspect_ass
from clipper.config import Settings
from clipper.domain.editing_plan import ClipType, ContentMode, EditingPlanV1, TrackingConfig
from clipper.domain.transcript import Transcript
from clipper.editorial import (
    EditorialContext,
    EditorialLLMProvider,
    ModeSignals,
    infer_content_mode,
)
from clipper.editorial.quality import candidate_findings, distinct_candidates
from clipper.media import probe_media
from clipper.persistence import Clip, Project, ProjectStatus, RuntimeSetting
from clipper.projects.artifacts import ArtifactProvenance, ClipArtifactService
from clipper.projects.stages import StageRunner
from clipper.rendering import (
    RenderRequest,
    VideoRenderer,
    VisualAnalysis,
    VisualTrackingProvider,
    keyframes_for_clip,
    strategy_for_mode,
)
from clipper.rendering.informative import inspect_render
from clipper.transcription import ProgressReporter, TranscriptionProvider


class Pipeline:
    """Orchestrate project stages through domain ports and application services."""

    STAGES = (
        "probe",
        "analyze_visuals",
        "transcribe",
        "select_candidates",
        "render_previews",
        "quality_review",
    )

    def __init__(
        self,
        settings: Settings,
        transcription: TranscriptionProvider,
        editorial: EditorialLLMProvider,
        tracking: VisualTrackingProvider | None = None,
    ) -> None:
        self.settings = settings
        self.transcription = transcription
        self.editorial = editorial
        self.tracking = tracking
        self.stage_runner = StageRunner()
        self.artifacts = ClipArtifactService(
            ArtifactProvenance(transcription.identity, editorial.identity)
        )
        self.renderer = VideoRenderer()

    def run(
        self,
        session: Session,
        project_id: str,
        target_count: int = 5,
        clip_types: tuple[ClipType, ...] = (),
    ) -> None:
        project = session.get(Project, project_id)
        if not project:
            raise LookupError("project not found")
        if project.status == "cancel_requested":
            project.status = ProjectStatus.CREATED
            session.commit()
            raise InterruptedError("Project stopped")
        project.status = ProjectStatus.PROCESSING
        session.commit()
        try:
            media_info = self.stage_runner.run(
                session,
                project,
                "probe",
                self._key(project.media_sha256, "inspection-v2"),
                lambda progress: probe_media(
                    Path(project.source_path), self.settings.max_duration_seconds
                ),
            )
            project.media_info = media_info
            project.duration_seconds = float(str(media_info["duration_seconds"]))
            session.commit()
            visual_payload: dict[str, object] = {}
            tracking = self.tracking
            if tracking:
                try:
                    visual_payload = self.stage_runner.run(
                        session,
                        project,
                        "analyze_visuals",
                        self._key(project.media_sha256, tracking.identity),
                        lambda progress: tracking.analyze(
                            Path(project.source_path),
                            lambda: self._cancelled(session, project.id),
                            progress,
                        ).as_artifact(),
                    )
                except InterruptedError:
                    raise
                except Exception:
                    # Optional tracking failure leaves a stable, wider layout. Failed
                    # stage diagnostics remain available for stage-specific retry.
                    visual_payload = {"tracking_unavailable": True}
            visual_analysis = VisualAnalysis.from_artifact(visual_payload)
            transcript_payload = self.stage_runner.run(
                session,
                project,
                "transcribe",
                self._key(project.media_sha256, self.transcription.identity),
                lambda progress: self.transcription.transcribe(
                    Path(project.source_path),
                    lambda: self._cancelled(session, project.id),
                    progress,
                ).model_dump(mode="json")
                if media_info.get("has_audio", True)
                else Transcript(
                    language="und", segments=[], provider="none", model="silent-source"
                ).model_dump(mode="json"),
            )
            project.transcript = transcript_payload
            session.commit()
            transcript = Transcript.model_validate(transcript_payload)
            motion_confidence = (
                sum(point.confidence for point in visual_analysis.action_points)
                / len(visual_analysis.action_points)
                if visual_analysis.action_points
                else 0
            )
            inferred_mode = infer_content_mode(
                project.title,
                project.original_filename,
                transcript,
                ModeSignals(visual_analysis.face_coverage, motion_confidence),
            )
            editorial_context = EditorialContext(
                project.title,
                project.original_filename,
                inferred_mode,
                visual_analysis.face_coverage,
                motion_confidence,
                clip_types,
            )
            plans_payload = self.stage_runner.run(
                session,
                project,
                "select_candidates",
                self._key(
                    project.media_sha256,
                    self.transcription.identity,
                    self.editorial.identity,
                    self.tracking.identity if self.tracking else "tracking:none",
                    inferred_mode,
                    str(target_count),
                    json.dumps(transcript_payload, sort_keys=True),
                    json.dumps(visual_payload, sort_keys=True),
                    project.title,
                    project.original_filename,
                    "selection-v2",
                    *(item.value for item in clip_types),
                ),
                lambda progress: self._select_and_track(
                    transcript,
                    target_count,
                    lambda: self._cancelled(session, project.id),
                    progress,
                    editorial_context,
                    visual_analysis,
                ),
            )
            preset_row = session.get(RuntimeSetting, f"project-preset:{project.id}")
            preset = json.loads(preset_row.value) if preset_row else {}
            # Reuse stable clips. Never delete edits, exports or publication history on retry.
            existing = list(session.scalars(select(Clip).where(Clip.project_id == project.id)))
            clips: list[Clip] = []
            for plan_payload in plans_payload:
                plan = EditingPlanV1.model_validate(plan_payload)
                if plan.source.end_seconds > project.duration_seconds:
                    bounded = plan.model_dump(mode="json")
                    bounded["source"]["end_seconds"] = project.duration_seconds
                    if bounded["source"]["start_seconds"] >= project.duration_seconds:
                        continue
                    plan = EditingPlanV1.model_validate(bounded)
                payload = plan.model_dump(mode="json")
                if preset:
                    payload["caption_config"]["font_family"] = preset.get(
                        "caption_font", "Noto Sans"
                    )
                    payload["caption_config"]["highlight_color"] = preset.get("accent", "#60A5FA")
                    plan = EditingPlanV1.model_validate(payload)
                    payload = plan.model_dump(mode="json")
                selection_key = self._key(json.dumps(payload, sort_keys=True))

                def matches(
                    item: Clip,
                    expected: dict[str, object] = payload,
                    expected_key: str = selection_key,
                ) -> bool:
                    original = (
                        Path(project.source_path).parent / "clips" / item.id / "selection-key.txt"
                    )
                    return item.plan == expected or (
                        original.is_file() and original.read_text() == expected_key
                    )

                clip = next((item for item in existing if matches(item)), None)
                if clip is None:
                    clip = Clip(project_id=project.id, plan=payload)
                    session.add(clip)
                    session.flush()
                    self.artifacts.write(project, clip, plan, transcript)
                selection = (
                    Path(project.source_path).parent / "clips" / clip.id / "selection-key.txt"
                )
                selection.parent.mkdir(parents=True, exist_ok=True)
                selection.write_text(selection_key)
                clips.append(clip)
            session.commit()
            self.stage_runner.run(
                session,
                project,
                "render_previews",
                self._key(
                    "render-v3",
                    *(clip.id + json.dumps(clip.plan, sort_keys=True) for clip in clips),
                    project.media_sha256,
                ),
                lambda progress: self._render_previews(session, project, clips, progress),
                validate_cached=lambda paths: all(
                    (Path(project.source_path).parent / path).is_file() for path in paths
                ),
            )
            self.stage_runner.run(
                session,
                project,
                "quality_review",
                self._key(
                    "review-v1",
                    *(
                        clip.id
                        + json.dumps(clip.plan, sort_keys=True)
                        + str(Path(clip.preview_path).stat().st_mtime_ns)
                        if clip.preview_path
                        else clip.id
                        for clip in clips
                    ),
                ),
                lambda progress: self._review(session, project, clips, transcript),
            )
            if self._cancelled(session, project_id):
                raise InterruptedError("Project stopped")
            project.status = ProjectStatus.REVIEW
            session.commit()
        except InterruptedError:
            project.status = ProjectStatus.CREATED
            session.commit()
            raise
        except Exception:
            project.status = ProjectStatus.FAILED
            session.commit()
            raise

    def _render_previews(
        self,
        session: Session,
        project: Project,
        clips: list[Clip],
        progress: ProgressReporter,
    ) -> list[str]:
        outputs: list[str] = []
        project_root = Path(project.source_path).parent
        for index, clip in enumerate(clips):
            if self._cancelled(session, project.id):
                raise InterruptedError("Project stopped")
            root = project_root / "clips" / clip.id
            output = root / "preview.mp4"
            if (
                output.is_file()
                and output.with_suffix(".manifest.json").is_file()
                and clip.preview_path == str(output)
            ):
                outputs.append(str(output.relative_to(project_root)))
                continue
            self.renderer.render(
                RenderRequest(
                    Path(project.source_path),
                    EditingPlanV1.model_validate(clip.plan),
                    root / "captions.ass",
                    output,
                    preview=True,
                )
            )
            clip.preview_path = str(output)
            outputs.append(str(output.relative_to(project_root)))
            session.commit()
            progress((index + 1) / len(clips))
        return outputs

    def _select_and_track(
        self,
        transcript: Transcript,
        target_count: int,
        cancelled: Callable[[], bool],
        progress: ProgressReporter,
        context: EditorialContext,
        visual_analysis: VisualAnalysis,
    ) -> list[dict[str, object]]:
        if not transcript.segments:
            return self._visual_candidates(visual_analysis)
        plans = self.editorial.select_candidates(
            transcript,
            target_count,
            cancelled,
            progress,
            context,
        )
        payloads: list[dict[str, object]] = []
        for plan in distinct_candidates(plans):
            mode = context.content_mode if plan.content_mode.value == "auto" else plan.content_mode
            slices = plan.source_slices or [plan.source]
            keyframes = keyframes_for_clip(visual_analysis, mode, slices)
            payload = plan.model_dump(mode="json")
            payload.update(
                {
                    "content_mode": mode,
                    "tracking": TrackingConfig(
                        enabled=bool(keyframes),
                        strategy=strategy_for_mode(mode),
                        keyframes=keyframes,
                    ).model_dump(mode="json"),
                }
            )
            payloads.append(EditingPlanV1.model_validate(payload).model_dump(mode="json"))
        return payloads

    def _review(
        self, session: Session, project: Project, clips: list[Clip], transcript: Transcript
    ) -> dict[str, object]:
        reviews: list[dict[str, object]] = []
        for clip in clips:
            plan = EditingPlanV1.model_validate(clip.plan)
            findings = candidate_findings(plan, transcript)
            corrections: list[dict[str, object]] = []
            captions = Path(project.source_path).parent / "clips" / clip.id / "captions.ass"
            caption_findings = (
                inspect_ass(captions.read_text(), plan.timeline_duration)
                if captions.exists()
                else []
            )
            if (
                any(f["code"] == "caption_layout" for f in caption_findings)
                and clip.approval_status == "pending"
            ):
                corrected = plan.model_dump(mode="json")
                corrected["caption_config"]["font_size"] = max(
                    28, plan.caption_config.font_size - 10
                )
                corrected["caption_config"]["max_words_per_line"] = 3
                plan = EditingPlanV1.model_validate(corrected)
                clip.plan = plan.model_dump(mode="json")
                self.artifacts.write(project, clip, plan, transcript)
                if clip.preview_path:
                    Path(clip.preview_path).unlink(missing_ok=True)
                self._render_previews(session, project, [clip], lambda _: None)
                corrections.append(
                    {"attempt": 1, "action": "smaller_caption_layout", "findings": caption_findings}
                )
                caption_findings = inspect_ass(captions.read_text(), plan.timeline_duration)
            findings.extend(caption_findings)
            if clip.preview_path:
                measured = inspect_render(
                    Path(clip.preview_path),
                    plan.timeline_duration,
                    require_audio=bool((project.media_info or {}).get("has_audio", True)),
                )
                # Only decoding/stream/duration errors support a deterministic rerender.
                # One correction per clip, then surface every unresolved finding.
                if any(f["severity"] == "error" for f in measured) and not corrections:
                    Path(clip.preview_path).unlink(missing_ok=True)
                    self._render_previews(session, project, [clip], lambda _: None)
                    corrections.append({"attempt": 1, "action": "rerender", "findings": measured})
                    measured = inspect_render(
                        Path(clip.preview_path),
                        plan.timeline_duration,
                        require_audio=bool((project.media_info or {}).get("has_audio", True)),
                    )
                findings.extend(measured)
            reviews.append(
                {
                    "clip_id": clip.id,
                    "findings": findings,
                    "corrections": corrections,
                    "human_review_required": True,
                }
            )
        return {
            "version": "1",
            "clips": reviews,
            "limitations": (
                "No semantic visual review or pixel-level caption overflow "
                "detection; inspect previews."
            ),
        }

    @staticmethod
    def _visual_candidates(visual: VisualAnalysis) -> list[dict[str, object]]:
        points = sorted(
            (p for p in visual.action_points if p.confidence >= 0.15),
            key=lambda p: p.confidence,
            reverse=True,
        )
        if not points:
            raise ValueError(
                "No speech or usable visual action signals. Choose a moment "
                "manually or enable tracking."
            )
        # Motion is evidence of action, not evidence of an interesting story or sentence.
        plans: list[EditingPlanV1] = []
        for point in points[:10]:
            start = max(0.0, point.time_seconds - 5)
            end = point.time_seconds + 5
            plans.append(
                EditingPlanV1.model_validate(
                    {
                        "schema_version": "1.0",
                        "source": {"start_seconds": start, "end_seconds": end},
                        "scores": dict.fromkeys(
                            ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                        ),
                        "rationale": (
                            f"Motion signal at {point.time_seconds:.1f}s. "
                            "Requires visual review; editorial quality unverified."
                        ),
                        "hook": {
                            "text": "Visual action",
                            "start_seconds": 0,
                            "end_seconds": 2,
                            "render": False,
                        },
                        "caption_style": "clean",
                        "caption_config": {"enabled": False},
                        "content_mode": ContentMode.BROLL,
                        "emphasis": [],
                        "effects": [],
                        "cta": None,
                    }
                )
            )
        return [p.model_dump(mode="json") for p in distinct_candidates(plans, minimum_score=0)[:3]]

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    @staticmethod
    def _cancelled(session: Session, project_id: str) -> bool:
        session.expire_all()
        project = session.get(Project, project_id)
        return project is None or project.status == "cancel_requested"
