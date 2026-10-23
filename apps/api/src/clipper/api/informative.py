"""Informative workflow endpoints; provider calls remain server-side."""

import hashlib
import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from clipper.api.dependencies import runtime_settings_service, story_video_service
from clipper.config import settings
from clipper.domain.transcript import Transcript
from clipper.media.errors import MediaError
from clipper.persistence import get_session
from clipper.persistence.models import ChannelPreset, InformativeShort
from clipper.providers.final_video_review import review_final_video
from clipper.providers.ollama_images import OllamaImageProvider
from clipper.providers.short_research import OllamaShortScriptProvider, SourceResearchProvider
from clipper.providers.studio_visual_review import review_artwork
from clipper.providers.trends import AgentReachTrendProvider
from clipper.providers.voicebox import VoiceboxError, VoiceboxNarrationProvider
from clipper.rendering.informative import audio_duration
from clipper.shorts.contracts import (
    Evidence,
    Script,
    ShortSettings,
    fingerprint,
    script_issues,
)
from clipper.shorts.service import ShortService


class WorkflowRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except LookupError as error:
                raise HTTPException(404, str(error)) from error
            except (ValueError, MediaError) as error:
                raise HTTPException(422, str(error)) from error
            except (VoiceboxError, httpx.HTTPError) as error:
                raise HTTPException(
                    502, "Provider unavailable. Check Settings and the service connection."
                ) from error

        return handler


router = APIRouter(route_class=WorkflowRoute)
voicebox = VoiceboxNarrationProvider(settings.voicebox_base_url)


def align_audio(path: Path, language: str) -> Transcript:
    from clipper.persistence import SessionLocal
    from clipper.providers.whisper import FasterWhisperProvider

    with SessionLocal() as session:
        model = runtime_settings_service.get(session).transcription_model
    provider = FasterWhisperProvider(
        model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        language_hint=language,
    )
    return provider.transcribe(path, lambda: False, lambda _: None)


short_service = ShortService(
    settings.data_dir / "informative-shorts",
    voicebox,
    settings.voicebox_timeout_seconds,
    aligner=align_audio,
    video_service=story_video_service,
    image_model=lambda session, configured: runtime_settings_service.get(session).task_models.get(
        "image_generation", configured
    )
    or configured,
    image_provider=lambda session: OllamaImageProvider(
        runtime_settings_service.get(session).ollama_base_url
    ),
    final_reviewer=lambda session, path, snapshot, timeline: review_final_video(
        runtime_settings_service.get(session).ollama_base_url,
        runtime_settings_service.get(session).model_for("visual_review"),
        path,
        snapshot,
        timeline,
    ),
    visual_reviewer=lambda session, path, subject: review_artwork(
        runtime_settings_service.get(session).ollama_base_url,
        runtime_settings_service.get(session).model_for("visual_review"),
        path,
        subject,
    ),
)
research = SourceResearchProvider(
    tuple(settings.research_allowed_hosts.split(",")), settings.research_search_url
)
trends = AgentReachTrendProvider(
    settings.agent_reach_command,
    settings.agent_reach_search_command,
    settings.research_search_url,
)


class CreateShort(BaseModel):
    topic: str = Field(min_length=3, max_length=4000)
    settings: ShortSettings = Field(default_factory=ShortSettings)
    request_key: str = Field(min_length=8, max_length=100)


class SourceRequest(BaseModel):
    urls: list[str] = Field(max_length=10)


class PresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    settings: ShortSettings


class ReconcileRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=100)


class VisualMetadata(BaseModel):
    attribution: str = Field(default="", max_length=2000)
    rights: str = Field(default="unknown", max_length=2000)
    provenance: str = Field(default="User supplied", max_length=2000)
    synthetic: bool = False


def serialize(short: InformativeShort) -> dict[str, Any]:
    script = Script.model_validate(short.script) if short.script else None
    sources = [Evidence.model_validate(s) for s in short.sources]
    artifacts = json.loads(json.dumps(short.artifacts))
    for entry in artifacts.values():
        if isinstance(entry, dict):
            for key in ("audio", "scene", "asset", "uploaded_audio"):
                if key in entry:
                    entry[key] = True
    return {
        "id": short.id,
        "topic": short.topic,
        "settings": short.settings,
        "sources": short.sources,
        "script": short.script,
        "status": short.status,
        "phase": short.phase,
        "error": short.error,
        "artifacts": artifacts,
        "approved": short.approved_hash == short_service.approval_hash(short),
        "findings": short.findings,
        "final_review": artifacts.get("final_video_review"),
        "usage": short.usage,
        "has_output": bool(short.output_path),
        "publication_project_id": short.publication_project_id,
        "script_issues": (
            script_issues(script, sources, require_claims="series_episode" not in short.artifacts)
            if script and "creation" not in short.artifacts
            else []
        ),
    }


@router.get("/shorts/providers")
def provider_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    runtime = runtime_settings_service.get(session)
    try:
        narration = voicebox.capabilities()
    except Exception as error:
        narration = {"connected": False, "error": str(error), "engines": [], "profiles": []}
    return {
        "narration": narration,
        "research": {
            "provider": "bounded HTTPS source retrieval",
            "search_configured": bool(settings.research_search_url),
            "allowed_hosts": research.allowed_hosts,
            "limitation": (
                "Source excerpts and claim quotes require human factual review; "
                "retrieval is not verification."
            ),
        },
        "scripting": {"provider": "ollama", "model": runtime.model_for("scripting")},
        "visuals": {"provider": "user assets or explicitly approved explanation cards"},
        "review": {
            "checks": ["full decode", "duration", "streams", "silence"],
            "human_checks": ["facts", "framing", "pronunciation", "phrase caption timing"],
        },
        "budget": {
            "registered_providers": "free local only",
            "cost_usd": 0,
            "estimated_seconds": None,
        },
    }


@router.delete("/shorts/{short_id}", status_code=204)
def delete_short(short_id: str, session: Session = Depends(get_session)) -> Response:
    short_service.delete(session, short_service.get(session, short_id))
    return Response(status_code=204)


@router.get("/shorts/topics")
def topics(category: str = "tech") -> list[dict[str, object]]:
    return research.suggestions(category)


@router.get("/channel-presets")
def presets(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [
        {"id": p.id, "name": p.name, "settings": p.settings}
        for p in session.scalars(select(ChannelPreset))
    ]


@router.post("/channel-presets")
def create_preset(
    request: PresetRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    preset = ChannelPreset(name=request.name, settings=request.settings.model_dump(mode="json"))
    session.add(preset)
    session.commit()
    return {"id": preset.id, "name": preset.name, "settings": preset.settings}


@router.put("/channel-presets/{preset_id}")
def update_preset(
    preset_id: str, request: PresetRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    preset = session.get(ChannelPreset, preset_id)
    if not preset:
        raise HTTPException(404, "Channel preset not found")
    preset.name, preset.settings = request.name, request.settings.model_dump(mode="json")
    session.commit()
    return {"id": preset.id, "name": preset.name, "settings": preset.settings}


@router.get("/shorts")
def list_shorts(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    shorts = list(
        session.scalars(select(InformativeShort).order_by(InformativeShort.created_at.desc()))
    )
    for short in shorts:
        short_service.sync_generation(session, short)
    return [serialize(short) for short in shorts]


@router.post("/shorts")
def create_short(request: CreateShort, session: Session = Depends(get_session)) -> dict[str, Any]:
    return serialize(
        short_service.create(session, request.topic, request.settings, request.request_key)
    )


@router.get("/shorts/{short_id}")
def read_short(short_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.sync_generation(session, short)
    return serialize(short)


@router.put("/shorts/{short_id}/settings")
def save_settings(
    short_id: str, config: ShortSettings, session: Session = Depends(get_session)
) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.editable(short)
    short.settings = config.model_dump(mode="json")
    short.approved_hash, short.output_path, short.status = None, None, "draft"
    session.commit()
    return serialize(short)


@router.post("/shorts/{short_id}/sources")
def retrieve_sources(
    short_id: str, request: SourceRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.editable(short)
    sources = research.retrieve(request.urls)
    short.sources = [s.model_dump(mode="json") for s in sources]
    short.approved_hash, short.output_path, short.status = None, None, "draft"
    session.commit()
    return serialize(short)


@router.post("/shorts/{short_id}/script/draft")
def draft_script(short_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.editable(short)
    runtime = runtime_settings_service.get(session)
    provider = OllamaShortScriptProvider(runtime.ollama_base_url, runtime.model_for("scripting"))
    script = provider.draft(
        short.topic,
        ShortSettings.model_validate(short.settings),
        [Evidence.model_validate(s) for s in short.sources],
    )
    short_service.save_script(session, short, script)
    return serialize(short)


@router.put("/shorts/{short_id}/script")
def save_script(
    short_id: str, script: Script, session: Session = Depends(get_session)
) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.save_script(session, short, script)
    return serialize(short)


@router.post("/shorts/{short_id}/script/approve")
def approve_script(short_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.approve_script(session, short)
    return serialize(short)


@router.post("/shorts/{short_id}/produce")
def produce(short_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    short_service.enqueue(session, short)
    return serialize(short)


@router.post("/shorts/{short_id}/cancel")
def cancel(short_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    creation = short.artifacts.get("creation", {})
    if (
        isinstance(creation, dict)
        and creation.get("video_id")
        and short.status in {"queued", "producing", "generating"}
    ):
        story_video_service.stop(session, creation["video_id"])
        short.status, short.phase = "cancelled", "Generation stopped; saved scenes kept"
        session.commit()
        return serialize(short)
    if short.status in {"queued", "producing", "generating"}:
        short.status = (
            "cancel_requested" if short.status in {"producing", "generating"} else "cancelled"
        )
        session.commit()
    return serialize(short)


@router.post("/shorts/{short_id}/approve")
def approve_video(short_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    return {
        "publishing_path": short_service.approve_video(
            session, short_service.get(session, short_id)
        )
    }


def section_entry(
    session: Session, short_id: str, section_id: str
) -> tuple[InformativeShort, dict[str, Any]]:
    short = short_service.get(session, short_id)
    short_service.editable(short)
    if section_id not in {s.id for s in Script.model_validate(short.script).sections}:
        raise ValueError("Script section not found")
    return short, json.loads(json.dumps(short.artifacts))


@router.post("/shorts/{short_id}/sections/{section_id}/reconcile")
def reconcile(
    short_id: str,
    section_id: str,
    request: ReconcileRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    short, artifacts = section_entry(session, short_id, section_id)
    voicebox.status(request.generation_id)
    # Confirm association using the actual upstream record, not just a known ID.
    record = voicebox._request("GET", f"/history/{quote(request.generation_id, safe='')}").json()
    section = next(s for s in Script.model_validate(short.script).sections if s.id == section_id)
    from clipper.shorts.contracts import speech_input

    config = ShortSettings.model_validate(short.settings)
    if record.get("text") != speech_input(section.text, config.pronunciations) or (
        record.get("profile_id") != config.profile_id
        or record.get("engine") != config.engine
        or record.get("language") != config.language
    ):
        raise ValueError("Generation does not match this section and voice")
    artifacts.setdefault(section_id, {}).update(
        generation=request.generation_id,
        submission="accepted",
        voice_key=short_service.voice_key(
            speech_input(section.text, config.pronunciations), config
        ),
    )
    short.artifacts = artifacts
    session.commit()
    return serialize(short)


@router.post("/shorts/{short_id}/sections/{section_id}/regenerate")
def regenerate(
    short_id: str, section_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    short, artifacts = section_entry(session, short_id, section_id)
    entry = artifacts.get(section_id, {})
    if entry.get("generation") and voicebox.status(entry["generation"]) not in {
        "completed",
        "cancelled",
        "failed",
    }:
        raise ValueError("Wait for the existing Voicebox generation or confirm cancellation first")
    if entry.get("submission") == "uncertain":
        raise ValueError("Reconcile the interrupted Voicebox request first")
    for name in ("audio", "scene"):
        if entry.get(name):
            Path(entry[name]).unlink(missing_ok=True)
    for name in ("generation", "submission", "uploaded_audio", "uploaded_script_hash"):
        entry.pop(name, None)
    artifacts[section_id] = entry
    short.artifacts, short.output_path, short.status = artifacts, None, "draft"
    session.commit()
    return serialize(short)


@router.post("/shorts/{short_id}/sections/{section_id}/upload")
def upload_section(
    short_id: str,
    section_id: str,
    kind: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    short, artifacts = section_entry(session, short_id, section_id)
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {
        "audio": {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff"},
        "image": {".png", ".jpg", ".jpeg", ".webp"},
        "recording": {".mp4", ".mov", ".webm"},
    }
    if kind not in allowed or suffix not in allowed[kind]:
        raise ValueError("Choose a supported audio, screenshot or recording file")
    root = short_service.root / short.id
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"upload-{uuid4()}{suffix}"
    digest = hashlib.sha256()
    size = 0
    try:
        with output.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 200 * 1024 * 1024:
                    raise ValueError("Upload limit is 200 MB per asset")
                digest.update(chunk)
                target.write(chunk)
        if not size:
            raise ValueError("Upload is empty")
        entry = artifacts.setdefault(section_id, {})
        if kind == "audio":
            duration = audio_duration(output)
            section = next(
                s for s in Script.model_validate(short.script).sections if s.id == section_id
            )
            entry.update(
                uploaded_audio=str(output),
                uploaded_script_hash=fingerprint(section.text),
                duration=duration,
            )
        else:
            from clipper.media.video_validation import valid_generated_video
            from clipper.rendering.story_video import StoryVideoFinisher

            finisher = StoryVideoFinisher()
            if not (
                finisher.valid_frame(output)
                if kind == "image"
                else valid_generated_video(output, require_audio=False)
            ):
                raise ValueError("Visual asset cannot be decoded")
            entry.update(
                asset=str(output),
                asset_hash=digest.hexdigest(),
                asset_kind=kind,
                frame_generated=False,
                rights="unknown",
                provenance="User supplied",
                attribution="",
                synthetic=False,
            )
        short.artifacts, short.output_path, short.status = artifacts, None, "draft"
        session.commit()
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return serialize(short)


@router.put("/shorts/{short_id}/sections/{section_id}/provenance")
def save_provenance(
    short_id: str, section_id: str, request: VisualMetadata, session: Session = Depends(get_session)
) -> dict[str, Any]:
    short, artifacts = section_entry(session, short_id, section_id)
    artifacts.setdefault(section_id, {}).update(request.model_dump())
    short.artifacts = artifacts
    short.output_path, short.status = None, "draft"
    session.commit()
    return serialize(short)


@router.post("/shorts/{short_id}/preview")
def preview(short_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    short = short_service.get(session, short_id)
    short_service.editable(short)
    config = ShortSettings.model_validate(short.settings)
    artifacts = json.loads(json.dumps(short.artifacts))
    key = fingerprint(config.model_dump())
    prior = artifacts.get("_preview", {})
    if prior.get("key") == key:
        if prior.get("generation"):
            return {"generation": prior["generation"]}
        raise ValueError(
            "Preview submission interrupted; inspect Voicebox history before repeating"
        )
    voicebox.validate(config)
    artifacts["_preview"] = {"key": key, "submission": "uncertain"}
    short_service._save_artifacts(session, short, artifacts)
    generation = voicebox.submit("Welcome. Here is a clear explanation of today's topic.", config)
    artifacts["_preview"]["generation"] = generation
    short_service._save_artifacts(session, short, artifacts)
    return {"generation": generation}


@router.get("/shorts/{short_id}/preview/{generation_id}")
def preview_audio(
    short_id: str, generation_id: str, session: Session = Depends(get_session)
) -> FileResponse:
    short = short_service.get(session, short_id)
    preview = short.artifacts.get("_preview", {})
    if not isinstance(preview, dict) or preview.get("generation") != generation_id:
        raise HTTPException(404, "Preview not found")
    if voicebox.status(generation_id) != "completed":
        raise HTTPException(409, "Preview is still generating; try playing it again shortly")
    path = short_service.root / short.id / f"preview-{fingerprint(generation_id)}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(voicebox.audio(generation_id))
    return FileResponse(path, media_type="audio/wav")


@router.get("/shorts/{short_id}/video")
def video(short_id: str, session: Session = Depends(get_session)) -> FileResponse:
    short = short_service.get(session, short_id)
    if not short.output_path or not Path(short.output_path).is_file():
        raise HTTPException(404, "Produce a video first")
    return FileResponse(short.output_path, media_type="video/mp4", filename="informative-short.mp4")


@router.get("/shorts/{short_id}/provenance")
def provenance(short_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    short = short_service.get(session, short_id)
    return {
        "sources": short.sources,
        "script": short.script,
        "assets": serialize(short)["artifacts"],
        "findings": short.findings,
        "final_review": serialize(short).get("final_review"),
        "usage": short.usage,
    }
