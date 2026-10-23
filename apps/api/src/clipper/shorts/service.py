"""Durable informative-short jobs with approval, stable segments and scoped caches."""

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.captions.quality import inspect_ass
from clipper.domain.transcript import Transcript
from clipper.generation import StoryPlan
from clipper.persistence.models import Clip, InformativeShort, Project, RuntimeSetting, StoryVideo
from clipper.projects.story_videos import StoryVideoCreate, StoryVideoService
from clipper.providers.ollama_images import OllamaImageProvider
from clipper.providers.studio_narrative import EDITORIAL_VERSION, audience_terms, copy_issues
from clipper.rendering.episode_art import render_art_thumbnail, render_episode_art
from clipper.rendering.frames import VERSION as FRAME_VERSION
from clipper.rendering.frames import (
    add_original_music,
    render_frame,
    render_frame_video,
    validate_frame_layout,
)
from clipper.rendering.informative import (
    assemble_sections,
    audio_duration,
    inspect_render,
    render_section,
)
from clipper.rendering.series import render_source_card, render_thumbnail, silent_audio
from clipper.rendering.template_assets import template_artwork
from clipper.shorts.alignment import align_display_script
from clipper.shorts.contracts import (
    Evidence,
    NarrationProvider,
    Script,
    ShortSettings,
    fingerprint,
    script_issues,
    speech_input,
)
from clipper.shorts.frames import sequence_by_id
from clipper.shorts.series import EpisodeSnapshot
from clipper.shorts.video_review import FinalVideoAssessment, refine_copy


class ShortService:
    def __init__(
        self,
        root: Path,
        narration: NarrationProvider,
        timeout: float = 600,
        aligner: Callable[[Path, str], Transcript] | None = None,
        video_service: StoryVideoService | None = None,
        image_provider: Callable[[Session], OllamaImageProvider] | None = None,
        visual_reviewer: Callable[[Session, Path, str], list[str]] | None = None,
        final_reviewer: Callable[
            [Session, Path, EpisodeSnapshot, list[dict[str, Any]]], FinalVideoAssessment
        ]
        | None = None,
        image_model: Callable[[Session, str], str] | None = None,
    ) -> None:
        self.root, self.narration, self.timeout = root, narration, timeout
        self.aligner = aligner
        self.video_service = video_service
        self.image_provider = image_provider
        self.image_model = image_model
        self.visual_reviewer = visual_reviewer
        self.final_reviewer = final_reviewer

    def effective_image_model(self, session: Session, configured: str) -> str:
        return self.image_model(session, configured) if self.image_model else configured

    def get(self, session: Session, short_id: str) -> InformativeShort:
        short = session.get(InformativeShort, short_id)
        if not short:
            raise LookupError("Created video not found")
        return short

    @staticmethod
    def approval_hash(short: InformativeShort) -> str:
        return fingerprint(
            {
                "script": short.script,
                "sources": short.sources,
                "language": short.settings.get("language", "en"),
            }
        )

    def save_script(self, session: Session, short: InformativeShort, script: Script) -> None:
        self.editable(short)
        short.script = script.model_dump(mode="json")
        short.approved_hash = None
        short.output_path = None
        short.status = "draft"
        short.phase = "Script changed; review sources and approve again"
        session.commit()

    @staticmethod
    def editable(short: InformativeShort) -> None:
        if short.status in {"queued", "producing", "generating", "cancel_requested"}:
            raise ValueError("Stop production before editing this video")

    def delete(self, session: Session, short: InformativeShort) -> None:
        """Remove this local draft/render; separately published project copies stay intact."""
        import shutil

        self.editable(short)
        directory = self.root / short.id
        if directory.is_symlink() or directory.resolve().parent != self.root.resolve():
            raise ValueError("Invalid video storage directory")
        if directory.exists():
            shutil.rmtree(directory)
        session.delete(short)
        session.commit()

    def approve_script(self, session: Session, short: InformativeShort) -> None:
        self.editable(short)
        self.studio_quality(short)
        script = Script.model_validate(short.script)
        issues = script_issues(
            script,
            [Evidence.model_validate(s) for s in short.sources],
            require_claims="series_episode" not in short.artifacts,
        )
        if "series_episode" in short.artifacts:
            snapshot = EpisodeSnapshot.model_validate(short.artifacts["series_episode"])
            for visual in snapshot.plan.visuals:
                entry = short.artifacts.get(visual.section_id, {})
                if visual.kind == "recording" and (
                    not isinstance(entry, dict) or not entry.get("asset")
                ):
                    raise ValueError(
                        f"Attach a screenshot or recording for {visual.heading} before approval"
                    )
        if issues and "creation" not in short.artifacts:
            raise ValueError(
                "Resolve script evidence issues before approval: " + issues[0]["message"]
            )
        short.approved_hash = self.approval_hash(short)
        short.phase = "Script approved; add narration and visual assets or start production"
        session.commit()

    @staticmethod
    def studio_quality(short: InformativeShort) -> None:
        if not short.artifacts.get("studio"):
            return
        snapshot = EpisodeSnapshot.model_validate(short.artifacts["series_episode"])
        if snapshot.plan.editorial_version != EDITORIAL_VERSION:
            raise ValueError(
                "Regenerate this older storyboard to apply the new story and layout review."
            )
        issues = copy_issues(
            [section.text for section in Script.model_validate(short.script).sections],
            include_repetition=False,
        )
        sequence = snapshot.style.frame_sequence or sequence_by_id(snapshot.style.id)
        repository = urlsplit(snapshot.brief.source_url)
        proper_names = (
            (repository.path.rstrip("/").rsplit("/", 1)[-1],)
            if repository.hostname == "github.com"
            else ()
        )
        captions = [v.frame.caption.casefold() for v in snapshot.plan.visuals if v.frame]
        if len(set(captions)) != len(captions):
            issues.append("Each scene needs a distinct caption that advances the story.")
        for visual in snapshot.plan.visuals:
            if visual.frame:
                issues += validate_frame_layout(visual.frame, sequence)
                frame = visual.frame
                jargon = audience_terms(
                    " ".join(
                        [
                            frame.caption,
                            frame.title,
                            frame.eyebrow,
                            *[item.title + " " + item.body for item in frame.items],
                        ]
                    ),
                    proper_names=proper_names,
                )
                if jargon:
                    issues.append("Simplify the screen copy: " + ", ".join(jargon))
        if issues:
            raise ValueError(
                "Resolve video quality issues before production: " + "; ".join(issues)[:600]
            )

    def enqueue(self, session: Session, short: InformativeShort) -> None:
        if short.status in {"queued", "producing", "generating"}:
            return
        if short.approved_hash != self.approval_hash(short):
            raise ValueError("Approve the current script and evidence before production")
        self.studio_quality(short)
        # Only free local providers are registered. A nonzero saved budget is not
        # permission for a hypothetical hosted adapter to spend money.
        short.status, short.phase, short.error = "queued", "Waiting for production", None
        session.commit()

    def _save_artifacts(
        self, session: Session, short: InformativeShort, artifacts: dict[str, Any]
    ) -> None:
        short.artifacts = json.loads(json.dumps(artifacts))
        session.commit()

    def _cancelled(self, session: Session, short: InformativeShort) -> bool:
        session.refresh(short, attribute_names=["status"])
        return short.status == "cancel_requested"

    def produce(self, session: Session, short: InformativeShort) -> None:
        config = ShortSettings.model_validate(short.settings)
        if "creation" in short.artifacts and config.narration_mode == "none":
            self.start_generation(session, short)
            return
        script = Script.model_validate(short.script)
        if short.approved_hash != self.approval_hash(short):
            raise ValueError("Script approval expired")
        artifacts: dict[str, Any] = json.loads(json.dumps(short.artifacts))
        short.status, short.error = "producing", None
        session.commit()
        root = self.root / short.id
        root.mkdir(parents=True, exist_ok=True)
        scenes: list[Path] = []
        timeline: list[dict[str, Any]] = []
        total = 0.0
        try:
            if "series_episode" in artifacts:
                self.prepare_episode_assets(session, short, artifacts)
            for index, section in enumerate(script.sections):
                if self._cancelled(session, short):
                    raise InterruptedError("Production stopped. Saved sections can be reused.")
                short.phase = f"Preparing section {index + 1} of {len(script.sections)}"
                session.commit()
                entry = artifacts.setdefault(section.id, {})
                text = speech_input(section.text, config.pronunciations)
                visual = (
                    next(
                        (
                            v
                            for v in EpisodeSnapshot.model_validate(
                                artifacts["series_episode"]
                            ).plan.visuals
                            if v.section_id == section.id
                        ),
                        None,
                    )
                    if "series_episode" in artifacts
                    else None
                )
                frame = visual.frame if visual else None
                key = self.voice_key(text, config)
                if frame and config.narration_mode == "none":
                    key = fingerprint({"voice": key, "duration": frame.duration_seconds})
                upload = entry.get("uploaded_audio")
                if upload and entry.get("uploaded_script_hash") != fingerprint(section.text):
                    raise ValueError(f"Replace narration for changed section: {section.heading}")
                audio = Path(upload) if upload else root / f"{section.id}-{key}.wav"
                silent = "series_episode" in artifacts and config.narration_mode == "none"
                if silent and not upload and not audio.is_file():
                    words = sum(max(1, len(s.text.split())) for s in script.sections)
                    silent_audio(
                        audio,
                        frame.duration_seconds
                        if frame
                        else config.duration * max(1, len(section.text.split())) / words + 0.01,
                    )
                if not upload and not audio.is_file():
                    generation = entry.get("generation") if entry.get("voice_key") == key else None
                    if not generation:
                        if entry.get("submission") == "uncertain":
                            raise ValueError(
                                "Interrupted Voicebox submission: reconcile its generation ID "
                                "from Voicebox history before retrying"
                            )
                        attempts = (
                            int(entry.get("attempts", 0)) if entry.get("voice_key") == key else 0
                        )
                        if attempts >= config.max_attempts:
                            raise ValueError(
                                "Narration retry budget exhausted; upload "
                                "audio or reconcile history"
                            )
                        validator = getattr(self.narration, "validate", None)
                        if validator:
                            validator(config)
                        entry.update(voice_key=key, submission="uncertain", attempts=attempts + 1)
                        self._save_artifacts(session, short, artifacts)
                        generation = self.narration.submit(text, config)
                        entry.update(generation=generation, submission="accepted")
                        self._save_artifacts(session, short, artifacts)
                    deadline = time.monotonic() + self.timeout
                    while True:
                        if self._cancelled(session, short):
                            entry["cancel_requested"] = True
                            self._save_artifacts(session, short, artifacts)
                            try:
                                confirmed = self.narration.cancel(str(generation))
                            except RuntimeError:
                                confirmed = False
                            entry["cancel_confirmed"] = confirmed
                            self._save_artifacts(session, short, artifacts)
                            raise InterruptedError(
                                "ReachCut stopped; Voicebox cancellation "
                                + ("confirmed" if confirmed else "not yet confirmed")
                            )
                        status = self.narration.status(str(generation))
                        if status == "completed":
                            break
                        if status in {"cancelled", "failed"}:
                            raise ValueError(
                                "Narration did not complete; reconcile Voicebox history"
                            )
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "Voicebox is still processing; retry resumes the same generation"
                            )
                        time.sleep(1)
                    pending = audio.with_suffix(".pending.wav")
                    pending.write_bytes(self.narration.audio(str(generation)))
                    audio_duration(pending)
                    pending.replace(audio)
                duration = audio_duration(audio)
                if frame:
                    duration = max(duration, frame.duration_seconds)
                aligned_cues = None
                if self.aligner and not silent and not frame:
                    try:
                        alignment_key = fingerprint(
                            {
                                "audio": str(audio),
                                "text": section.text,
                                "language": config.language,
                                "provider": "whisper-alignment-v1",
                            }
                        )
                        if entry.get("alignment_key") == alignment_key and entry.get("alignment"):
                            aligned = Transcript.model_validate(entry["alignment"])
                        else:
                            aligned = self.aligner(audio, config.language)
                            entry.update(
                                alignment_key=alignment_key,
                                alignment=aligned.model_dump(mode="json"),
                            )
                        aligned_cues = align_display_script(section.text, aligned, duration)
                        entry["alignment_notice"] = None
                    except (ValueError, RuntimeError) as error:
                        entry["alignment_notice"] = str(error)[:300]
                entry.update(
                    audio=str(audio),
                    duration=duration,
                    display_text=section.text,
                    speech_input=text,
                    provenance="uploaded" if upload else "silent preview" if silent else "voicebox",
                    voice_key=key,
                )
                self._save_artifacts(session, short, artifacts)
                total += duration
                if total > (60 if frame else config.duration + 3) or total > 60.5:
                    raise ValueError(
                        "Narration exceeds requested duration. Shorten and reapprove the script "
                        "or upload shorter narration; speech was not truncated."
                    )
                asset = entry.get("asset")
                if not asset and (
                    section.visual in {"screenshot", "recording", "map"}
                    or not config.allow_explanation_cards
                ):
                    raise ValueError(
                        f"Add the required visual for '{section.heading}', or choose an "
                        "explanation visual and explicitly allow explanation cards."
                    )
                render_key = fingerprint(
                    {
                        "audio": self._audio_hash(audio),
                        "asset": entry.get("asset_hash"),
                        "text": section.text,
                        "heading": section.heading,
                        "font": config.caption_font,
                        "renderer": FRAME_VERSION if frame else "3",
                        "frame": frame.model_dump() if frame else None,
                        "motion": entry.get("motion", False),
                        "alignment": entry.get("alignment"),
                        "attribution": entry.get("attribution", ""),
                        "style": config.style,
                        "series_style": artifacts.get("series_episode", {}).get("style"),
                    }
                )
                scene = root / f"{section.id}-{render_key}.mp4"
                if not scene.is_file():
                    if frame and entry.get("frame_generated"):
                        snapshot = EpisodeSnapshot.model_validate(artifacts["series_episode"])
                        render_frame_video(
                            frame,
                            (snapshot.style.frame_sequence or sequence_by_id(snapshot.style.id)),
                            audio,
                            scene,
                            duration,
                            Path(entry["artwork"]) if entry.get("artwork") else None,
                            snapshot.brief.subject,
                            lambda: self._cancelled(session, short),
                        )
                    else:
                        render_section(
                            audio,
                            scene,
                            section.heading,
                            section.text,
                            duration,
                            config.caption_font,
                            Path(asset) if asset else None,
                            entry.get("asset_kind") == "recording",
                            aligned_cues,
                            str(entry.get("attribution", "")),
                            config.style,
                            artifacts.get("series_episode", {})
                            .get("style", {})
                            .get("caption_style", "clean"),
                            config.accent,
                            bool(entry.get("motion", False)),
                            not (silent and not upload),
                        )
                entry.update(scene=str(scene), render_key=render_key)
                self._save_artifacts(session, short, artifacts)
                scenes.append(scene)
                timeline.append(
                    {
                        "section": section.id,
                        "start": total - duration,
                        "end": total,
                        "caption_timing": (
                            "Designed scene caption; narration is separate"
                            if frame and entry.get("frame_generated")
                            else "measured ASR words matched to display script"
                            if aligned_cues
                            else "approximate phrases within measured narration section"
                        ),
                    }
                )
            if total < 29.5:
                raise ValueError(
                    "Narration is shorter than 30 seconds. Extend and reapprove the script."
                )
            if self._cancelled(session, short):
                raise InterruptedError("Production stopped")
            short.phase = "Assembling video and checking rendered media"
            session.commit()
            output = root / f"master-{fingerprint([str(p) for p in scenes])}.mp4"
            if not output.is_file():
                assemble_sections(scenes, output)
            if artifacts.get("studio"):
                with_music = output.with_name(output.stem + "-music.mp4")
                if not with_music.is_file():
                    add_original_music(output, with_music, total)
                output = with_music
            findings = inspect_render(output, total)
            if "series_episode" in artifacts and config.narration_mode == "none":
                findings = [f for f in findings if f.get("code") != "silence"]
                if artifacts.get("studio") and not any(
                    isinstance(value, dict) and value.get("uploaded_audio")
                    for value in artifacts.values()
                ):
                    findings.append(
                        {
                            "severity": "warning",
                            "code": "music_only",
                            "start": 0,
                            "message": (
                                "Music-only cut. Add VoiceBox narration for a spoken version."
                            ),
                            "basis": "narration_settings",
                        }
                    )
            for scene, timing in zip(scenes, timeline, strict=True):
                for finding in inspect_ass(
                    scene.with_suffix(".ass").read_text(), timing["end"] - timing["start"]
                ):
                    finding["start"] = float(str(finding["start"])) + timing["start"]
                    findings.append(finding)
            if self._cancelled(session, short):
                raise InterruptedError("Production stopped; finished artifacts kept for recovery")
            if artifacts.get("studio", {}).get("final_review_required"):
                short.output_path = str(output)
                session.commit()
                output = self.refine_final_video(
                    session, short, artifacts, output, scenes, timeline, total
                )
                report = artifacts["final_video_review"]
                if report["status"] != "passed":
                    findings.append(
                        {
                            "severity": "error",
                            "code": "ai_final_review",
                            "start": 0,
                            "message": report["assessment"]["summary"],
                            "basis": "local_vision_review",
                        }
                    )
                findings.extend(inspect_render(output, total))
            findings += [
                {
                    "severity": "warning",
                    "code": "human_review",
                    "start": 0,
                    "message": (
                        "Check factual accuracy, visual relevance, pronunciation "
                        "and approximate phrase captions."
                    ),
                    "basis": "capability_limit",
                }
            ]
            short.findings = findings
            short.usage = {
                "estimated_cost_usd": 0,
                "actual_cost_usd": 0,
                "estimated_seconds": None,
                "actual_duration_seconds": total,
                "timeline": timeline,
                "provider": "local",
            }
            short.output_path = str(output)
            short.status = "failed" if any(f["severity"] == "error" for f in findings) else "review"
            short.phase = (
                "AI reviewed and refined the final cut; ready for your approval"
                if artifacts.get("final_video_review", {}).get("status") == "passed"
                else "Final review found issues; inspect the video before continuing"
                if artifacts.get("studio", {}).get("final_review_required")
                else "Review the video before approving export and publishing"
            )
            session.commit()
        except InterruptedError as error:
            short.status, short.error, short.phase = "cancelled", str(error), "Production stopped"
            session.commit()
        except Exception as error:
            short.status, short.error = "failed", str(error)[:1000]
            short.phase = "Production needs attention; completed sections are saved"
            session.commit()
            raise

    def refine_final_video(
        self,
        session: Session,
        short: InformativeShort,
        artifacts: dict[str, Any],
        output: Path,
        scenes: list[Path],
        timeline: list[dict[str, Any]],
        total: float,
    ) -> Path:
        snapshot = EpisodeSnapshot.model_validate(artifacts["series_episode"])
        history: list[dict[str, Any]] = []
        for attempt in range(3):
            if self._cancelled(session, short):
                raise InterruptedError("Final video review stopped")
            short.phase = f"AI is reviewing the rendered video (pass {attempt + 1} of 3)"
            session.commit()
            try:
                if not self.final_reviewer:
                    raise ValueError("Configure a vision model to review the finished video")
                assessment = self.final_reviewer(session, output, snapshot, timeline)
            except Exception as error:
                artifacts["final_video_review"] = {
                    "status": "unavailable",
                    "error": str(error)[:500],
                    "history": history,
                    "output_hash": self._audio_hash(output),
                }
                self._save_artifacts(session, short, artifacts)
                raise ValueError(
                    "Final AI video review could not complete: " + str(error)[:400]
                ) from error
            if self._cancelled(session, short):
                raise InterruptedError("Final video review stopped")
            history.append({"pass": attempt + 1, "assessment": assessment.model_dump()})
            artifacts["final_video_review"] = {
                "status": "passed" if assessment.passed else "needs_refinement",
                "assessment": assessment.model_dump(),
                "history": history,
                "output_hash": self._audio_hash(output),
                "basis": "Two sampled frames per scene from the final video, script and timings",
            }
            self._save_artifacts(session, short, artifacts)
            if assessment.passed or attempt == 2:
                return output
            changed: set[int] = set()
            for fix in assessment.refinements:
                index = fix.scene - 1
                if index >= len(snapshot.plan.script.sections):
                    continue
                section_id = snapshot.plan.script.sections[index].id
                visual = next(v for v in snapshot.plan.visuals if v.section_id == section_id)
                if not visual.frame:
                    continue
                try:
                    candidate = refine_copy(visual.frame, fix)
                    sequence = snapshot.style.frame_sequence or sequence_by_id(snapshot.style.id)
                    if validate_frame_layout(candidate, sequence):
                        continue
                except ValueError:
                    continue
                visual.frame = candidate
                visual.heading, visual.body = candidate.title, candidate.caption
                changed.add(index)
            if not changed:
                return output
            short.phase = "AI is refining scene readability and rendering a new cut"
            session.commit()
            sequence = snapshot.style.frame_sequence or sequence_by_id(snapshot.style.id)
            for index in sorted(changed):
                if self._cancelled(session, short):
                    raise InterruptedError("Final refinement stopped")
                section_id = snapshot.plan.script.sections[index].id
                visual = next(v for v in snapshot.plan.visuals if v.section_id == section_id)
                assert visual.frame is not None
                entry = artifacts[section_id]
                duration = float(timeline[index]["end"]) - float(timeline[index]["start"])
                key = fingerprint(
                    {"frame": visual.frame.model_dump(), "scene": str(scenes[index])}
                )[:24]
                refined = output.parent / f"{section_id}-refined-{key}.mp4"
                render_frame_video(
                    visual.frame,
                    sequence,
                    Path(entry["audio"]),
                    refined,
                    duration,
                    Path(entry["artwork"]) if entry.get("artwork") else None,
                    snapshot.brief.subject,
                    lambda: self._cancelled(session, short),
                )
                scenes[index] = refined
                entry["scene"] = str(refined)
            assembled = output.parent / f"refined-{fingerprint([str(p) for p in scenes])[:24]}.mp4"
            assemble_sections(scenes, assembled)
            with_music = assembled.with_name(assembled.stem + "-music.mp4")
            add_original_music(assembled, with_music, total)
            output = with_music
            artifacts["series_episode"] = snapshot.model_dump(mode="json")
            short.output_path = str(output)
            self._save_artifacts(session, short, artifacts)
        return output

    def prepare_episode_assets(
        self, session: Session, short: InformativeShort, artifacts: dict[str, Any]
    ) -> None:
        snapshot = EpisodeSnapshot.model_validate(artifacts["series_episode"])
        root = self.root / short.id
        root.mkdir(parents=True, exist_ok=True)
        for visual in snapshot.plan.visuals:
            if self._cancelled(session, short):
                raise InterruptedError("Artwork generation stopped. Saved scenes can be reused.")
            entry = artifacts.setdefault(visual.section_id, {})
            if (
                entry.get("asset")
                and Path(entry["asset"]).is_file()
                and (
                    not entry.get("frame_generated") or entry.get("frame_version") == FRAME_VERSION
                )
            ):
                continue
            if visual.frame:
                self.prepare_frame_asset(session, short, artifacts, snapshot, visual)
                continue
            source_title = next(
                (
                    source.title
                    for source in snapshot.brief.sources
                    if source.id == visual.source_id
                ),
                "",
            )
            key = fingerprint(
                {"series": snapshot.series.model_dump(), "visual": visual.model_dump()}
            )[:20]
            image = root / f"visual-{key}.png"
            artwork = None
            synthetic = False
            if visual.kind == "illustration":
                if snapshot.style.design and snapshot.style.design.reuse_background:
                    artwork = template_artwork(
                        self.root.parent / "template-artwork", snapshot.style
                    )
                    synthetic = bool(artwork)
                elif snapshot.series.artwork_mode == "ollama" or snapshot.style.design:
                    if not self.image_provider:
                        raise ValueError("Ollama artwork provider is not configured")
                    if not visual.art_prompt.strip():
                        raise ValueError("Rebuild the storyboard to include illustration prompts")
                    short.phase = f"Creating Ollama artwork: {visual.heading}"
                    session.commit()
                    art_prompt = visual.art_prompt
                    if snapshot.style.design:
                        art_prompt += " Visual treatment: " + snapshot.style.design.visual_direction
                        art_prompt += (
                            " Palette: "
                            + snapshot.style.design.background
                            + ", "
                            + snapshot.style.design.accent
                        )
                    art_key = fingerprint(
                        {
                            "prompt": art_prompt,
                            "model": self.effective_image_model(
                                session, snapshot.series.image_model
                            ),
                            "renderer": "ollama-image-v1",
                        }
                    )[:20]
                    artwork = root / f"art-{art_key}.png"
                    self.image_provider(session).generate(
                        self.effective_image_model(session, snapshot.series.image_model),
                        art_prompt,
                        artwork,
                        lambda: self._cancelled(session, short),
                    )
                    synthetic = True
                render_episode_art(
                    snapshot.series,
                    visual,
                    image,
                    artwork,
                    layout=snapshot.style.layout,
                    weight=snapshot.style.design.weight if snapshot.style.design else 800,
                    uppercase=snapshot.style.design.uppercase if snapshot.style.design else False,
                )
            else:
                render_source_card(snapshot.series, visual, source_title, image)
            entry.update(
                asset=str(image),
                asset_kind="image",
                asset_hash=self._audio_hash(image),
                rights="Original editorial layout; review facts and artwork before publishing",
                provenance="Ollama illustration"
                if synthetic
                else "Source-grounded storyboard card",
                synthetic=synthetic,
                artwork=str(artwork) if artwork else None,
                motion=visual.kind == "illustration",
            )
            self._save_artifacts(session, short, artifacts)
        thumbnail = root / (
            "thumbnail-"
            + fingerprint(snapshot.plan.headline + snapshot.series.model_dump_json())[:20]
            + ".png"
        )
        artwork_path = next(
            (
                entry.get("artwork")
                for entry in artifacts.values()
                if isinstance(entry, dict) and entry.get("artwork")
            ),
            None,
        )
        if artwork_path:
            thumbnail = thumbnail.with_name(thumbnail.stem + "-art.png")
            render_art_thumbnail(
                snapshot.series,
                snapshot.brief.subject,
                snapshot.plan.headline,
                Path(artwork_path),
                thumbnail,
            )
        else:
            render_thumbnail(
                snapshot.series, snapshot.brief.subject, snapshot.plan.headline, thumbnail
            )
        artifacts["_series_thumbnail"] = {
            "asset": str(thumbnail),
            "headline": snapshot.plan.headline,
        }
        self._save_artifacts(session, short, artifacts)

    def prepare_frame_asset(
        self,
        session: Session,
        short: InformativeShort,
        artifacts: dict[str, Any],
        snapshot: EpisodeSnapshot,
        visual: Any,
    ) -> None:
        root = self.root / short.id
        artwork = None
        if visual.frame.template == "photo":
            if not self.image_provider:
                raise ValueError("Ollama image provider is not configured")
            if not visual.art_prompt.strip():
                raise ValueError(
                    "Rebuild the storyboard to include this scene's illustration prompt"
                )
            prompt = visual.art_prompt + (
                " Show only the specific story subject described above. No unrelated people "
                "or generic portraits. Physical editorial photography only. "
                "No words, text, letters, logos, "
                "captions, watermarks or interface. Portrait 9:16, uncluttered composition "
                "with negative space."
            )
            for attempt in range(2):
                art_key = fingerprint(
                    {
                        "prompt": prompt,
                        "model": self.effective_image_model(session, snapshot.series.image_model),
                    }
                )[:24]
                artwork = root / f"art-{art_key}.png"
                short.phase = f"Creating local Ollama illustration: {visual.heading}"
                session.commit()
                self.image_provider(session).generate(
                    self.effective_image_model(session, snapshot.series.image_model),
                    prompt,
                    artwork,
                    lambda: self._cancelled(session, short),
                )
                if not self.visual_reviewer:
                    break
                short.phase = "Checking illustration relevance with local Ollama vision"
                session.commit()
                issues = self.visual_reviewer(session, artwork, visual.art_prompt)
                if not issues:
                    break
                if attempt:
                    raise ValueError(
                        "Generated illustration failed visual review: "
                        + "; ".join(issues)[:500]
                        + ". Retry production to replace it; completed scenes are saved."
                    )
                prompt += " Correct these visual defects: " + "; ".join(issues)
        key = fingerprint(
            {
                "frame": visual.frame.model_dump(),
                "sequence": snapshot.style.model_dump(),
                "version": FRAME_VERSION,
            }
        )[:24]
        image = root / f"frame-{key}.png"
        render_frame(
            visual.frame,
            (snapshot.style.frame_sequence or sequence_by_id(snapshot.style.id)),
            image,
            artwork,
            snapshot.brief.subject,
        )
        artifacts.setdefault(visual.section_id, {}).update(
            asset=str(image),
            asset_kind="image",
            asset_hash=self._audio_hash(image),
            artwork=str(artwork) if artwork else None,
            frame_generated=True,
            frame_version=FRAME_VERSION,
            synthetic=True,
            rights="Original scene composition and local Ollama illustration",
            provenance="Ollama storyboard / ReachCut frame",
            artwork_reviewed=bool(artwork and self.visual_reviewer),
            motion=True,
        )
        self._save_artifacts(session, short, artifacts)

    def start_generation(self, session: Session, short: InformativeShort) -> None:
        if short.approved_hash != self.approval_hash(short):
            raise ValueError("Script approval expired")
        if not self.video_service:
            raise ValueError("Local video generation is unavailable")
        artifacts = json.loads(json.dumps(short.artifacts))
        creation = artifacts["creation"]
        if creation.get("video_id"):
            video = self.video_service.get(session, creation["video_id"])
            if video.status in {"failed", "cancelled"}:
                self.video_service.requeue(session, video.id)
        else:
            if session.scalar(
                select(StoryVideo.id)
                .where(
                    StoryVideo.status.in_(["queued", "rendering", "finishing", "cancel_requested"])
                )
                .limit(1)
            ):
                short.phase = "Waiting for the current local video job; your short is queued"
                session.commit()
                return
            plan = StoryPlan.model_validate(creation["plan"])
            # Keep the narration script for optional Voicebox; render ambience first.
            visual_plan = plan.model_copy(
                update={
                    "scenes": [scene.model_copy(update={"narration": ""}) for scene in plan.scenes]
                }
            )

            def link_video(video: StoryVideo) -> None:
                creation["video_id"] = video.id
                short.artifacts = artifacts
                short.status = "generating"

            video = self.video_service.create(
                session,
                StoryVideoCreate(
                    story=short.topic,
                    template=creation["template"],
                    aspect_ratio="9:16",
                    quality="draft",
                    plan=visual_plan,
                ),
                on_created=link_video,
            )
            creation["video_id"] = video.id
        short.artifacts = artifacts
        short.status, short.error = "generating", None
        short.phase = "Generating original scenes with the local video renderer"
        session.commit()
        self.sync_generation(session, short)

    def sync_generation(self, session: Session, short: InformativeShort) -> None:
        if short.status != "generating" or not self.video_service:
            return
        creation = short.artifacts.get("creation", {})
        if not isinstance(creation, dict) or not creation.get("video_id"):
            return
        video = self.video_service.get(session, creation["video_id"])
        short.phase = video.phase
        if video.status in {"failed", "cancelled"}:
            short.status, short.error = video.status, video.error
        elif video.status == "complete" and video.output_path:
            artifacts = json.loads(json.dumps(short.artifacts))
            for scene in video.scenes:
                if scene.output_path:
                    artifacts.setdefault(f"scene_{scene.scene_index}", {}).update(
                        asset=scene.output_path,
                        asset_kind="recording",
                        asset_hash=self._audio_hash(Path(scene.output_path)),
                        synthetic=True,
                        rights="Generated locally",
                        provenance="Local AI video generation",
                    )
            short.artifacts = artifacts
            short.output_path = video.output_path
            short.usage = {
                "actual_duration_seconds": video.target_duration_seconds,
                "actual_cost_usd": 0,
                "provider": "local",
            }
            short.findings = [
                {
                    "severity": "warning",
                    "start": 0,
                    "message": "Review generated visuals and factual accuracy before publishing.",
                    "basis": "human_review",
                }
            ]
            short.status, short.phase = "review", "Video ready; review or add optional voice-over"
        session.commit()

    def approve_video(self, session: Session, short: InformativeShort) -> str:
        if short.status != "review" or not short.output_path:
            raise ValueError("Produce and review this video before approval")
        studio = short.artifacts.get("studio")
        if isinstance(studio, dict) and studio.get("final_review_required"):
            report = short.artifacts.get("final_video_review")
            if not isinstance(report, dict):
                raise ValueError("Complete the final AI review before publishing")
            if report.get("status") != "passed" or report.get("output_hash") != self._audio_hash(
                Path(short.output_path)
            ):
                raise ValueError(
                    "Complete the final AI review for this exact video before publishing"
                )
        self.studio_quality(short)
        if short.approved_hash != self.approval_hash(short):
            raise ValueError("Script approval expired")
        if any(f.get("severity") == "error" for f in short.findings):
            raise ValueError("Resolve export errors first")
        # Each approved revision gets an immutable publishing source and clip.
        # Old exports and account history remain attached to their original version.
        project_id, clip_id = str(uuid4()), str(uuid4())
        source = self.root.parent / "projects" / project_id / "source" / "source.mp4"
        clip_root = source.parent / "clips" / clip_id
        clip_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(short.output_path, source)
        shutil.copy2(short.output_path, clip_root / "final.mp4")
        shutil.copy2(short.output_path, clip_root / "preview.mp4")
        project = Project(
            id=project_id,
            title=short.topic[:200],
            original_filename="informative-short.mp4",
            source_path=str(source),
            media_sha256=self._audio_hash(source),
            authorization_confirmed_at=datetime.now(UTC),
            status="review",
            duration_seconds=float(str(short.usage["actual_duration_seconds"])),
        )
        session.add(project)
        session.flush()
        clip = Clip(id=clip_id, project_id=project.id, plan={})
        session.add(clip)
        short.publication_project_id = project.id
        from clipper.domain.editing_plan import EditingPlanV1

        plan = EditingPlanV1.model_validate(
            {
                "schema_version": "1.0",
                "source": {"start_seconds": 0, "end_seconds": project.duration_seconds},
                "scores": dict.fromkeys(
                    ["overall", "hook", "clarity", "payoff", "visual_interest"], 0
                ),
                "rationale": "Human-approved informative short. Scores are not evaluated.",
                "hook": {"text": short.topic[:100], "start_seconds": 0, "end_seconds": 2},
                "caption_style": "clean",
                "emphasis": [],
                "effects": [],
                "cta": None,
            }
        )
        if "series_episode" in short.artifacts:
            snapshot = EpisodeSnapshot.model_validate(short.artifacts["series_episode"])
            thumbnail = clip_root / "thumbnail.png"
            render_thumbnail(
                snapshot.series, snapshot.brief.subject, snapshot.plan.headline, thumbnail
            )
            from clipper.domain.editing_plan import ThumbnailConfig, ThumbnailTemplate

            plan.thumbnail = ThumbnailConfig(
                template=ThumbnailTemplate.MINIMAL, headline=snapshot.plan.headline, generated=True
            )
        clip.plan = plan.model_dump(mode="json")
        clip.final_path, clip.preview_path, clip.approval_status = (
            str(clip_root / "final.mp4"),
            str(clip_root / "preview.mp4"),
            "approved",
        )
        session.flush()
        session.add(
            RuntimeSetting(
                key=f"informative-revision:{project.id}",
                value=json.dumps(
                    {
                        "short_id": short.id,
                        "topic": short.topic,
                        "settings": short.settings,
                        "script": short.script,
                        "sources": short.sources,
                    }
                ),
            )
        )
        short.status, short.phase = "approved", "Ready to export or publish"
        session.commit()
        path = f"/projects/{project.id}/clips/{clip.id}/publish"
        destinations = ShortSettings.model_validate(short.settings).destinations
        return path + (
            "?" + urlencode({"destinations": ",".join(destinations)}) if destinations else ""
        )

    @staticmethod
    def voice_key(text: str, config: ShortSettings) -> str:
        return fingerprint(
            {
                "speech": text,
                "narration_mode": config.narration_mode,
                "silent_duration": config.duration if config.narration_mode == "none" else None,
                "profile": config.profile_id,
                "engine": config.engine,
                "model": config.model_size,
                "delivery": config.delivery,
                "language": config.language,
                "provider": "voicebox-http-v1",
                "version": 1,
            }
        )

    @staticmethod
    def _audio_hash(path: Path) -> str:
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()

    def create(
        self,
        session: Session,
        topic: str,
        config: ShortSettings,
        request_key: str,
        *,
        commit: bool = True,
    ) -> InformativeShort:
        existing = session.scalar(
            select(InformativeShort).where(InformativeShort.request_key == request_key)
        )
        if existing:
            if existing.topic != topic or existing.settings != config.model_dump(mode="json"):
                raise ValueError("Request key was already used for different video inputs")
            return existing
        short = InformativeShort(
            id=str(uuid4()),
            request_key=request_key,
            topic=topic,
            settings=config.model_dump(mode="json"),
        )
        session.add(short)
        if commit:
            session.commit()
        else:
            session.flush()
        return short
