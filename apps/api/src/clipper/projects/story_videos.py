from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from clipper.domain.editing_plan import EditingPlanV1
from clipper.generation import (
    AspectRatio,
    GenerationQuality,
    SceneGenerationRequest,
    StoryPlan,
    VideoGenerationBusyError,
    VideoGenerationProvider,
    VideoTemplateId,
)
from clipper.persistence import Clip, Project, StoryVideo, StoryVideoScene, now_utc
from clipper.persistence.models import StoryDraft
from clipper.rendering.story_video import StoryVideoFinisher


class StoryVideoNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class StoryVideoCreate:
    story: str
    template: VideoTemplateId
    aspect_ratio: AspectRatio
    quality: GenerationQuality
    plan: StoryPlan
    reference_image: Path | None = None
    draft_id: str | None = None


class StoryVideoService:
    def __init__(
        self,
        root: Path,
        provider: VideoGenerationProvider,
        finisher: StoryVideoFinisher,
    ) -> None:
        self._creation_lock = Lock()
        self._root = root
        self._provider = provider
        self._finisher = finisher

    def list(self, session: Session) -> list[StoryVideo]:
        query = (
            select(StoryVideo)
            .options(selectinload(StoryVideo.scenes))
            .order_by(StoryVideo.created_at.desc())
        )
        return list(session.scalars(query).unique())

    def get(self, session: Session, video_id: str) -> StoryVideo:
        video = session.scalar(
            select(StoryVideo)
            .where(StoryVideo.id == video_id)
            .execution_options(populate_existing=True)
            .options(selectinload(StoryVideo.scenes))
        )
        if not video:
            raise StoryVideoNotFoundError("story video not found")
        return video

    def create(
        self,
        session: Session,
        request: StoryVideoCreate,
        *,
        on_created: Callable[[StoryVideo], None] | None = None,
    ) -> StoryVideo:
        """Create a job and optionally link its parent within the same transaction."""
        with self._creation_lock:
            self._ensure_idle(session)
            draft = None
            if request.draft_id:
                draft = session.get(StoryDraft, request.draft_id)
                if not draft:
                    raise ValueError("Queued story was already processed or removed")
            video = self._create(session, request)
            if draft:
                session.delete(draft)
            if on_created:
                on_created(video)
            session.commit()
            return self.get(session, video.id)

    def _ensure_idle(self, session: Session) -> None:
        active = session.scalar(
            select(StoryVideo.id).where(
                StoryVideo.status.in_(["queued", "rendering", "finishing", "cancel_requested"])
            )
        )
        if active:
            raise ValueError(
                "A short is already processing. Wait for it to finish before starting another."
            )

    def _create(self, session: Session, request: StoryVideoCreate) -> StoryVideo:
        video = StoryVideo(
            story=request.story,
            template=request.template,
            aspect_ratio=request.aspect_ratio,
            quality=request.quality,
            target_duration_seconds=math.ceil(request.plan.output_duration_seconds),
            status="queued",
            phase="Waiting for the local renderer",
            progress=0,
            plan=request.plan.model_dump(mode="json"),
            provider=self._provider.identity,
        )
        for scene in request.plan.scenes:
            video.scenes.append(
                StoryVideoScene(
                    scene_index=scene.index,
                    title=scene.title,
                    prompt=scene.visual_prompt,
                    narration=scene.narration,
                    duration_seconds=scene.duration_seconds,
                    seed=scene.seed,
                    status="queued",
                    reference_image_path=(
                        str(request.reference_image.resolve())
                        if scene.index == 1 and request.reference_image
                        else None
                    ),
                )
            )
        session.add(video)
        session.flush()
        return video

    def render(self, session: Session, video_id: str) -> StoryVideo:
        video = self.get(session, video_id)
        if video.status == "cancel_requested":
            return self._finish_stop(session, video)
        if video.status != "queued" and video.status not in {"rendering", "finishing"}:
            return video
        plan = StoryPlan.model_validate(video.plan)
        job_root = self._root.resolve() / video.id
        video.status = "rendering"
        video.phase = "Checking saved scene checkpoints"
        video.error = None
        session.commit()

        continuity_frame: Path | None = None
        outputs: list[Path] = []
        total = len(video.scenes)
        active_scene_id: str | None = None
        step = "checking saved scenes"
        try:
            for row, scene in zip(video.scenes, plan.scenes, strict=True):
                self._check_stop(session, video)
                active_scene_id = row.id
                output = job_root / "scenes" / f"scene-{scene.index:02}.mp4"
                pending = output.with_name(f"{output.stem}.pending.mp4")
                frame = job_root / "continuity" / f"scene-{scene.index:02}-last.jpg"
                step = "validating the saved video"
                valid = self._finisher.validate_video(output, scene.duration_seconds)
                if not valid and self._finisher.validate_video(pending, scene.duration_seconds):
                    pending.replace(output)
                    valid = True
                if not valid:
                    # Never trust a nonempty file alone: an interrupted MP4 can be 48 bytes.
                    frame.unlink(missing_ok=True)
                    row.status = "rendering"
                    row.progress = 0.05
                    row.error = None
                    step = "rendering"
                    video.phase = f"Rendering scene {scene.index} of {total}: {scene.title}"
                    video.progress = max(video.progress, len(outputs) / (total + 1))
                    session.commit()
                    explicit_reference = (
                        Path(row.reference_image_path) if row.reference_image_path else None
                    )
                    self._provider.generate_scene(
                        SceneGenerationRequest(
                            prompt=self._scene_prompt(plan, scene.index),
                            negative_prompt=plan.negative_prompt,
                            aspect_ratio=video.aspect_ratio,  # type: ignore[arg-type]
                            quality=video.quality,  # type: ignore[arg-type]
                            duration_seconds=scene.duration_seconds,
                            camera_motion=scene.camera_motion,
                            seed=scene.seed,
                            reference_image=explicit_reference or continuity_frame,
                        ),
                        pending,
                    )
                    self._check_stop(session, video)
                    step = "validating the rendered video"
                    if not self._finisher.validate_video(pending, scene.duration_seconds):
                        raise ValueError(
                            "The rendered scene MP4 is incomplete. "
                            "Retry will recover its LTX output before rendering again."
                        )
                    pending.replace(output)
                if row.status == "complete" and (
                    scene.index == total or self._finisher.valid_frame(frame)
                ):
                    continuity_frame = frame if scene.index < total else continuity_frame
                    outputs.append(output)
                    continue
                # Commit the render independently of continuity extraction.
                row.output_path = str(output)
                row.status = "rendered"
                row.progress = 0.9
                row.error = None
                video.phase = f"Preparing continuity for scene {scene.index} of {total}"
                video.progress = max(video.progress, (len(outputs) + 0.9) / (total + 1))
                session.commit()
                step = "extracting the continuity frame"
                if scene.index < total:
                    if not self._finisher.valid_frame(frame):
                        self._finisher.extract_last_frame(output, frame)
                    continuity_frame = frame
                row.status = "complete"
                row.progress = 1
                row.error = None
                outputs.append(output)
                video.progress = max(video.progress, len(outputs) / (total + 1))
                session.commit()

            self._check_stop(session, video)
            active_scene_id = None
            step = "finishing the final MP4"
            video.status = "finishing"
            video.phase = "Stitching saved scenes and mastering the final MP4"
            session.commit()
            master = job_root / "video.mp4"
            recipe = {
                "version": 1,
                "hook": plan.hook_caption,
                "ending": plan.end_caption,
                "clips": [
                    {
                        "name": path.name,
                        "bytes": path.stat().st_size,
                        "modified": path.stat().st_mtime_ns,
                        "start": float(scene.trim_start_seconds),
                        "end": float(scene.trim_end_seconds or scene.duration_seconds),
                        "speed": float(scene.playback_speed),
                        "crop": scene.crop.model_dump(mode="json") if scene.crop else None,
                    }
                    for path, scene in zip(outputs, plan.scenes, strict=True)
                ],
            }
            signature = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
            export_receipt = job_root / "export-checkpoint.json"
            try:
                saved_signature = json.loads(export_receipt.read_text()).get("signature")
            except (OSError, ValueError, AttributeError):
                saved_signature = None
            if saved_signature != signature or not self._finisher.validate_video(
                master, plan.output_duration_seconds
            ):
                master = self._finisher.stitch(outputs, master, plan=plan)
                pending_receipt = export_receipt.with_suffix(".pending.json")
                pending_receipt.write_text(json.dumps({"signature": signature}))
                pending_receipt.replace(export_receipt)
            self._check_stop(session, video)
            video.output_path = str(master)
            video.status = "complete"
            video.phase = "Ready"
            video.progress = 1
            session.commit()
        except InterruptedError:
            session.rollback()
            return self._finish_stop(session, self.get(session, video_id))
        except VideoGenerationBusyError:
            session.rollback()
            video = self.get(session, video_id)
            if video.status == "cancel_requested":
                return self._finish_stop(session, video)
            active = next((item for item in video.scenes if item.id == active_scene_id), None)
            if active:
                active.status = "queued"
                active.error = None
            video.status = "queued"
            video.phase = (
                "Waiting for LTX; this short will resume automatically. Saved scenes kept."
            )
            video.error = None
            session.commit()
            return video
        except Exception as error:
            session.rollback()
            video = self.get(session, video_id)
            if video.status == "cancel_requested":
                return self._finish_stop(session, video)
            active = next((item for item in video.scenes if item.id == active_scene_id), None)
            if active:
                active.status = "failed"
                active.error = str(error)[:2_000]
            video.status = "failed"
            video.phase = (
                f"Scene {active.scene_index} stopped while {step}"
                if active
                else f"Stopped while {step}"
            )
            video.error = str(error)[:2_000]
            session.commit()
            raise
        return self.get(session, video_id)

    def stop(self, session: Session, video_id: str) -> StoryVideo:
        video = self.get(session, video_id)
        if video.status == "queued":
            return self._finish_stop(session, video)
        if video.status in {"rendering", "finishing", "cancel_requested"}:
            video.status = "cancel_requested"
            video.phase = "Stopping after the current operation; saved scenes kept"
            session.commit()
        return video

    @staticmethod
    def _check_stop(session: Session, video: StoryVideo) -> None:
        session.refresh(video, attribute_names=["status"])
        if video.status == "cancel_requested":
            raise InterruptedError("Story generation stopped")

    @staticmethod
    def _finish_stop(session: Session, video: StoryVideo) -> StoryVideo:
        video.status = "cancelled"
        video.phase = "Stopped; saved scenes kept. Resume or delete this project."
        video.error = None
        for scene in video.scenes:
            if scene.status == "rendering":
                scene.status = "queued"
                scene.error = None
        session.commit()
        return video

    def requeue(self, session: Session, video_id: str) -> StoryVideo:
        with self._creation_lock:
            video = self.get(session, video_id)
            if video.status not in {"failed", "queued", "cancelled"}:
                raise ValueError("Only queued, stopped or failed jobs can be resumed")
            if video.status == "queued":
                return video
            self._ensure_idle(session)
            video.status = "queued"
            completed = sum(scene.status == "complete" for scene in video.scenes)
            next_scene = next((scene for scene in video.scenes if scene.status != "complete"), None)
            video.phase = (
                f"Resume queued at scene {next_scene.scene_index}; "
                f"{completed} completed scenes saved"
                if next_scene
                else "Resume queued for final stitching; all scenes saved"
            )
            video.error = None
            for scene in video.scenes:
                if scene.status == "failed":
                    scene.status = "queued"
                    scene.error = None
            session.commit()
            return self.get(session, video_id)

    def rename(self, session: Session, video_id: str, title: str) -> StoryVideo:
        video = self.get(session, video_id)
        if not title.strip():
            raise ValueError("Title cannot be empty")
        if video.status in {"queued", "rendering", "finishing", "cancel_requested"}:
            raise ValueError("Wait for the render to finish before editing the short")
        video.plan = {**video.plan, "title": title.strip()}
        session.commit()
        return self.get(session, video_id)

    def prepare_publishing(self, session: Session, video_id: str, projects_root: Path) -> Clip:
        """Copy a completed master into the existing project publishing workflow."""
        with self._creation_lock:
            return self._prepare_publishing(session, video_id, projects_root)

    def _prepare_publishing(self, session: Session, video_id: str, projects_root: Path) -> Clip:
        video = self.get(session, video_id)
        master = self.resolve(session, video_id)
        project_id = str(uuid5(NAMESPACE_URL, f"reachcut:short:{video.id}"))
        clip_id = str(uuid5(NAMESPACE_URL, f"reachcut:short-clip:{video.id}"))
        existing = session.get(Clip, clip_id)
        if existing:
            return existing
        source = projects_root / project_id / "source" / "story.mp4"
        final = source.parent / "clips" / clip_id / "final.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(master, source)
        shutil.copy2(master, final)
        plan = EditingPlanV1.model_validate(
            {
                "source": {"start_seconds": 0, "end_seconds": video.target_duration_seconds},
                "scores": dict.fromkeys(
                    ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                ),
                "rationale": "AI generated story master prepared for publishing.",
                "suggested_title": str(video.plan["title"])[:100],
                "clip_type": "story",
                "caption_config": {"enabled": False},
            }
        )
        with source.open("rb") as source_file:
            digest = hashlib.file_digest(source_file, "sha256").hexdigest()
        project = session.get(Project, project_id)
        if not project:
            project = Project(
                id=project_id,
                title=str(video.plan["title"]),
                original_filename="story.mp4",
                source_path=str(source),
                media_sha256=digest,
                authorization_confirmed_at=now_utc(),
                status="complete",
                duration_seconds=video.target_duration_seconds,
            )
            session.add(project)
        clip = Clip(
            id=clip_id,
            project=project,
            plan=plan.model_dump(mode="json"),
            approval_status="approved",
            final_path=str(final),
        )
        session.add(clip)
        session.commit()
        return clip

    def delete(self, session: Session, video_id: str) -> None:
        video = self.get(session, video_id)
        if video.status in {"queued", "rendering", "finishing", "cancel_requested"}:
            raise ValueError("Active story videos cannot be deleted")
        job_root = (self._root.resolve() / video.id).resolve()
        if job_root.parent != self._root.resolve():
            raise ValueError("Invalid story video path")
        session.delete(video)
        session.commit()
        shutil.rmtree(job_root, ignore_errors=True)

    def resolve(self, session: Session, video_id: str) -> Path:
        video = self.get(session, video_id)
        if video.status != "complete" or not video.output_path:
            raise StoryVideoNotFoundError("story video is not ready")
        expected = self._root.resolve() / video.id / "video.mp4"
        try:
            resolved = Path(video.output_path).resolve(strict=True)
        except OSError as error:
            raise StoryVideoNotFoundError("story video file not found") from error
        if resolved != expected or not resolved.is_file():
            raise StoryVideoNotFoundError("story video file not found")
        return resolved

    @staticmethod
    def _scene_prompt(plan: StoryPlan, scene_index: int) -> str:
        scene = plan.scenes[scene_index - 1]
        characters = {character.id: character for character in plan.characters}
        anchors = " ".join(
            f"{characters[item].name}: {characters[item].appearance_anchor}; "
            f"wearing {characters[item].wardrobe_anchor}."
            for item in scene.character_ids
        )
        audio = (
            f' Synchronized audio: a consistent narrator says, "{scene.narration}".'
            if scene.narration
            else " Synchronized audio: natural ambience and story-appropriate sound design."
        )
        visual = re.sub(
            r"\s*(?:the\s+)?seed\s*(?:is|:|=)\s*\d+\s*[.!]?\s*$",
            "",
            scene.visual_prompt,
            flags=re.IGNORECASE,
        ).strip()
        previous = plan.scenes[scene_index - 2] if scene_index > 1 else None
        opening = scene.opening_frame or (previous.ending_frame if previous else "")
        previous_end = (previous.ending_frame or previous.story_beat) if previous else "First shot"
        return (
            f"VISUAL MEDIUM: {plan.visual_style}. "
            "Use this same medium for every character and prop. "
            f"LOCKED CHARACTER IDENTITIES: {anchors} "
            f"WORLD AND PROP CONTINUITY: {plan.continuity_notes} "
            "The supplied image is the first frame: preserve its character faces, "
            "body proportions, "
            "clothing, props, lighting and layout. Continue motion from that composition. "
            f"PREVIOUS END STATE: {previous_end}. "
            f"OPENING STATE: {opening}. "
            f"ONE SHOT ACTION: {visual}. "
            f"END FRAME: {scene.ending_frame}. "
            "Show the action completing on screen. No cuts within this shot, no teleporting, "
            "no new character designs, no style changes or morphing props."
            + audio
            + (" No dialogue or spoken words." if not scene.narration else "")
        )
