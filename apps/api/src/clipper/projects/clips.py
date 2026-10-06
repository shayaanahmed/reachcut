from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from shutil import rmtree
from typing import BinaryIO, Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from clipper.captions import CaptionTranslationProvider
from clipper.domain.editing_plan import (
    CTA,
    CaptionConfig,
    ContentMode,
    EditingPlanV1,
    Effect,
    EnhancementLevel,
    Hook,
    SecondaryMedia,
    SecondaryMediaKind,
    TimeRange,
    TrackingConfig,
    TrackingStrategy,
    TransitionStyle,
    TranslationMode,
)
from clipper.domain.transcript import Transcript
from clipper.media import safe_filename, store_upload
from clipper.persistence import Clip, Project
from clipper.projects.artifacts import ClipArtifactService, timeline_words
from clipper.rendering import (
    RenderRequest,
    VideoRenderer,
    VisualTrackingProvider,
    keyframes_for_clip,
    strategy_for_mode,
)


class ClipNotFoundError(LookupError):
    pass


class ClipStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClipStyleUpdate:
    caption_config: CaptionConfig
    frame_style: Literal["blurred_background", "center_crop"]
    crop_focus_x: float = 0.5
    crop_focus_y: float = 0.5
    source_slices: tuple[TimeRange, ...] | None = None
    hook_text: str | None = None
    hook_render: bool | None = None
    content_mode: ContentMode = ContentMode.AUTO
    enhancement_level: EnhancementLevel = EnhancementLevel.CLEAN
    tracking_enabled: bool | None = None
    tracking_strategy: TrackingStrategy | None = None
    transition_style: TransitionStyle = TransitionStyle.CUT
    transition_duration_seconds: float = 0.2
    cta_text: str | None = None
    cta_render: bool | None = None
    cta_style: Literal["follow", "comment", "part_two", "profile", "product", "campaign"] = "follow"
    effects: tuple[Effect, ...] | None = None
    audio_track_index: int = 0


class ClipService:
    """Manage clip approval, enhancements, assets, previews, and final renders."""

    def __init__(
        self,
        artifacts: ClipArtifactService,
        renderer: VideoRenderer,
        translation: CaptionTranslationProvider | None = None,
        tracking: VisualTrackingProvider | None = None,
        max_secondary_media_bytes: int = 2 * 1024**3,
    ) -> None:
        self._artifacts = artifacts
        self._renderer = renderer
        self._translation = translation
        self._tracking = tracking
        self._max_secondary_media_bytes = max_secondary_media_bytes

    def set_approval(self, session: Session, clip_id: str, approved: bool) -> str:
        clip = self._clip(session, clip_id)
        clip.approval_status = "approved" if approved else "rejected"
        session.commit()
        return clip.project_id

    def update_style(self, session: Session, clip_id: str, update: ClipStyleUpdate) -> str:
        clip, project, transcript = self._editable_clip(session, clip_id)
        previous_plan = EditingPlanV1.model_validate(clip.plan)
        source_slices = list(update.source_slices or previous_plan.source_slices)
        source = previous_plan.source
        serialized_slices = previous_plan.source_slices
        if update.source_slices:
            if any(
                current.end_seconds > following.start_seconds
                for current, following in pairwise(update.source_slices)
            ):
                raise ClipStateError("source slices must be ordered and non-overlapping")
            if project.duration_seconds is not None and any(
                source_slice.end_seconds > project.duration_seconds
                for source_slice in update.source_slices
            ):
                raise ClipStateError("source slice exceeds project duration")
            source = TimeRange(
                start_seconds=update.source_slices[0].start_seconds,
                end_seconds=update.source_slices[-1].end_seconds,
            )
            serialized_slices = source_slices if len(source_slices) > 1 else []
        duration = sum(
            item.end_seconds - item.start_seconds for item in (source_slices or [source])
        )
        hook = previous_plan.hook
        if hook or update.hook_text or update.hook_render:
            hook = Hook(
                text=(update.hook_text or (hook.text if hook else "Opening context")).strip(),
                start_seconds=0,
                end_seconds=min(3.5, duration),
                render=(
                    update.hook_render
                    if update.hook_render is not None
                    else (hook.render if hook else False)
                ),
            )
        cta = previous_plan.cta
        if cta or update.cta_text or update.cta_render:
            cta_duration = min(4, max(duration / 4, 1))
            cta = CTA(
                text=(update.cta_text or (cta.text if cta else "Follow for more")).strip(),
                start_seconds=max(0, duration - cta_duration),
                end_seconds=duration,
                render=(
                    update.cta_render
                    if update.cta_render is not None
                    else (cta.render if cta else False)
                ),
                style=update.cta_style,
            )
        tracking = previous_plan.tracking.model_copy(
            update={
                "enabled": (
                    update.tracking_enabled
                    if update.tracking_enabled is not None
                    else previous_plan.tracking.enabled
                ),
                "strategy": update.tracking_strategy or previous_plan.tracking.strategy,
            }
        )
        payload = previous_plan.model_dump(mode="json")
        payload.update(
            {
                "source": source.model_dump(mode="json"),
                "source_slices": [item.model_dump(mode="json") for item in serialized_slices],
                "caption_config": update.caption_config.model_dump(mode="json"),
                "frame_style": update.frame_style,
                "crop_focus_x": update.crop_focus_x,
                "crop_focus_y": update.crop_focus_y,
                "content_mode": update.content_mode,
                "enhancement_level": update.enhancement_level,
                "tracking": tracking.model_dump(mode="json"),
                "transition_style": update.transition_style,
                "transition_duration_seconds": update.transition_duration_seconds,
                "audio_track_index": update.audio_track_index,
                "caption_style": (
                    "karaoke"
                    if update.caption_config.animation == "karaoke"
                    else "kinetic_highlight"
                ),
                "hook": hook.model_dump(mode="json") if hook else None,
                "cta": cta.model_dump(mode="json") if cta else None,
                "effects": (
                    [effect.model_dump(mode="json") for effect in update.effects]
                    if update.effects is not None
                    else payload["effects"]
                ),
            }
        )
        plan = EditingPlanV1.model_validate(payload)
        return self._replace_plan(session, project, clip, transcript, previous_plan, plan)

    def translate_captions(
        self,
        session: Session,
        clip_id: str,
        target_language: str,
        mode: TranslationMode,
    ) -> str:
        if self._translation is None:
            raise ClipStateError("caption translation provider is not configured")
        clip, project, transcript = self._editable_clip(session, clip_id)
        previous_plan = EditingPlanV1.model_validate(clip.plan)
        words = timeline_words(transcript, previous_plan.source_slices or [previous_plan.source])
        source_text = previous_plan.caption_config.text_override or " ".join(
            word.text for word in words
        )
        if not source_text.strip():
            raise ClipStateError("clip contains no caption text to translate")
        translated = self._translation.translate(
            source_text,
            previous_plan.caption_config.source_language or transcript.language,
            target_language,
        )
        caption_config = previous_plan.caption_config.model_copy(
            update={
                "source_language": transcript.language,
                "target_language": target_language,
                "translation_mode": mode,
                "translated_text": translated,
            }
        )
        payload = previous_plan.model_dump(mode="json")
        payload["caption_config"] = caption_config.model_dump(mode="json")
        plan = EditingPlanV1.model_validate(payload)
        return self._replace_plan(session, project, clip, transcript, previous_plan, plan)

    def analyze_tracking(self, session: Session, clip_id: str) -> str:
        if self._tracking is None:
            raise ClipStateError("visual tracking provider is not configured")
        clip, project, transcript = self._editable_clip(session, clip_id)
        previous_plan = EditingPlanV1.model_validate(clip.plan)
        try:
            analysis = self._tracking.analyze(
                Path(project.source_path),
                lambda: False,
                lambda progress: None,
            )
        except InterruptedError:
            raise
        except Exception as error:
            raise ClipStateError("visual tracking could not analyze this source") from error
        mode = previous_plan.content_mode
        keyframes = keyframes_for_clip(
            analysis,
            mode,
            previous_plan.source_slices or [previous_plan.source],
        )
        payload = previous_plan.model_dump(mode="json")
        payload["tracking"] = TrackingConfig(
            enabled=bool(keyframes),
            strategy=strategy_for_mode(mode),
            keyframes=keyframes,
        ).model_dump(mode="json")
        plan = EditingPlanV1.model_validate(payload)
        return self._replace_plan(session, project, clip, transcript, previous_plan, plan)

    def add_secondary_media(
        self,
        session: Session,
        clip_id: str,
        stream: BinaryIO,
        original_filename: str,
        kind: SecondaryMediaKind,
        start_seconds: float | None,
        end_seconds: float | None,
        placement: Literal["bottom", "pip", "fullscreen", "audio"],
    ) -> str:
        clip, project, transcript = self._editable_clip(session, clip_id)
        previous_plan = EditingPlanV1.model_validate(clip.plan)
        asset_id = str(uuid4())
        filename = safe_filename(original_filename)
        root = self._clip_root(project, clip)
        target = root / "assets" / asset_id / filename
        store_upload(stream, target, self._max_secondary_media_bytes)
        media = SecondaryMedia(
            asset_id=asset_id,
            filename=filename,
            kind=kind,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            muted=kind not in {SecondaryMediaKind.SOUND_EFFECT, SecondaryMediaKind.MUSIC},
            loop=kind in {SecondaryMediaKind.GAMEPLAY, SecondaryMediaKind.MUSIC},
            placement=placement,
        )
        payload = previous_plan.model_dump(mode="json")
        payload["secondary_media"] = [
            *payload["secondary_media"],
            media.model_dump(mode="json"),
        ]
        if kind is SecondaryMediaKind.GAMEPLAY:
            payload["content_mode"] = ContentMode.GAMEPLAY
        elif kind is SecondaryMediaKind.REACTION:
            payload["content_mode"] = ContentMode.REACTION
        elif kind is SecondaryMediaKind.BROLL:
            payload["content_mode"] = ContentMode.BROLL
        try:
            plan = EditingPlanV1.model_validate(payload)
            return self._replace_plan(session, project, clip, transcript, previous_plan, plan)
        except Exception:
            rmtree(target.parent, ignore_errors=True)
            raise

    def remove_secondary_media(self, session: Session, clip_id: str, asset_id: str) -> str:
        clip, project, transcript = self._editable_clip(session, clip_id)
        previous_plan = EditingPlanV1.model_validate(clip.plan)
        if not any(item.asset_id == asset_id for item in previous_plan.secondary_media):
            raise ClipStateError("secondary media asset is not attached to this clip")
        payload = previous_plan.model_dump(mode="json")
        payload["secondary_media"] = [
            item for item in payload["secondary_media"] if item["asset_id"] != asset_id
        ]
        plan = EditingPlanV1.model_validate(payload)
        project_id = self._replace_plan(session, project, clip, transcript, previous_plan, plan)
        asset_root = self._clip_root(project, clip) / "assets" / asset_id
        rmtree(asset_root, ignore_errors=True)
        return project_id

    def render_final(self, session: Session, clip_id: str) -> Path:
        clip = self._clip(session, clip_id)
        if clip.approval_status != "approved":
            raise ClipStateError("clip must be explicitly approved before render")
        project = session.get(Project, clip.project_id)
        if not project:
            raise ClipNotFoundError("project not found")
        root = self._clip_root(project, clip)
        output = root / "final.mp4"
        plan = EditingPlanV1.model_validate(clip.plan)
        if not (root / "captions.ass").exists() and project.transcript:
            self._artifacts.write(
                project, clip, plan, Transcript.model_validate(project.transcript)
            )
        subtitles = root / "captions.ass"
        if not subtitles.exists():
            subtitles = root / "captions.srt"
        self._renderer.render(
            RenderRequest(
                Path(project.source_path),
                plan,
                subtitles,
                output,
                preview=False,
                asset_paths=self._asset_paths(project, clip, plan),
            )
        )
        clip.final_path = str(output)
        session.commit()
        return output

    def _replace_plan(
        self,
        session: Session,
        project: Project,
        clip: Clip,
        transcript: Transcript,
        previous_plan: EditingPlanV1,
        plan: EditingPlanV1,
    ) -> str:
        root = self._artifacts.write(project, clip, plan, transcript)
        pending_preview = root / "preview.pending.mp4"
        pending_manifest = pending_preview.with_suffix(".manifest.json")
        try:
            self._renderer.render(
                RenderRequest(
                    Path(project.source_path),
                    plan,
                    root / "captions.ass",
                    pending_preview,
                    preview=True,
                    asset_paths=self._asset_paths(project, clip, plan),
                )
            )
        except Exception:
            pending_preview.unlink(missing_ok=True)
            pending_manifest.unlink(missing_ok=True)
            self._artifacts.write(project, clip, previous_plan, transcript)
            raise
        pending_preview.replace(root / "preview.mp4")
        pending_manifest.replace(root / "preview.manifest.json")
        clip.plan = plan.model_dump(mode="json")
        clip.preview_path = str(root / "preview.mp4")
        clip.final_path = None
        session.commit()
        return clip.project_id

    @staticmethod
    def _asset_paths(project: Project, clip: Clip, plan: EditingPlanV1) -> dict[str, Path]:
        root = ClipService._clip_root(project, clip) / "assets"
        paths: dict[str, Path] = {}
        for item in plan.secondary_media:
            expected_parent = (root / item.asset_id).resolve()
            path = (expected_parent / item.filename).resolve()
            if path.parent != expected_parent or not path.is_file():
                raise ClipStateError(f"secondary media asset {item.asset_id} is unavailable")
            paths[item.asset_id] = path
        return paths

    @staticmethod
    def _clip_root(project: Project, clip: Clip) -> Path:
        return Path(project.source_path).parent / "clips" / clip.id

    @staticmethod
    def _clip(session: Session, clip_id: str) -> Clip:
        clip = session.get(Clip, clip_id)
        if not clip:
            raise ClipNotFoundError("clip not found")
        return clip

    def _editable_clip(self, session: Session, clip_id: str) -> tuple[Clip, Project, Transcript]:
        clip = self._clip(session, clip_id)
        project = session.get(Project, clip.project_id)
        if not project or not project.transcript:
            raise ClipStateError("project transcript is not available")
        return clip, project, Transcript.model_validate(project.transcript)
