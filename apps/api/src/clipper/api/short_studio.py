"""Simple creation endpoints and a global library of reusable scene frames."""

import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from clipper.api.dependencies import runtime_settings_service
from clipper.api.informative import WorkflowRoute, short_service
from clipper.persistence import get_session
from clipper.projects.frame_import import import_frame_html
from clipper.projects.short_studio import StudioJob, create_job, get_brief, get_job, run_job
from clipper.providers.github_repository import GitHubRepositoryProvider
from clipper.rendering.frames import VERSION, render_frame
from clipper.rendering.html_frames import frame_document
from clipper.shorts.contracts import fingerprint
from clipper.shorts.frames import (
    FrameDefinition,
    FrameSequence,
    FrameTheme,
    frame_library,
    frame_sequences,
    sequence_by_id,
)
from clipper.shorts.studio import IdeaRequest, StoryboardRequest, StudioBrief

_sample_lock = threading.Lock()

router = APIRouter(prefix="/short-studio", route_class=WorkflowRoute)


def schedule(
    session: Session, request: IdeaRequest | StoryboardRequest, tasks: BackgroundTasks
) -> StudioJob:
    job, needed = create_job(session, request)
    if needed:
        runtime = runtime_settings_service.get(session)
        tasks.add_task(
            run_job,
            job.id,
            runtime.ollama_base_url,
            runtime.model_for("research" if isinstance(request, IdeaRequest) else "scripting"),
            short_service,
            scripting_model=runtime.model_for("scripting"),
        )
    return job


@router.post("/ideas")
def ideas(
    request: IdeaRequest, tasks: BackgroundTasks, session: Session = Depends(get_session)
) -> StudioJob:
    if request.category == "github":
        owner, repo = GitHubRepositoryProvider.identity(request.repo_url)
        request.repo_url = f"https://github.com/{owner}/{repo}"
    return schedule(session, request, tasks)


@router.post("/storyboards")
def storyboards(
    request: StoryboardRequest, tasks: BackgroundTasks, session: Session = Depends(get_session)
) -> StudioJob:
    brief = get_brief(session, request.brief_id)
    if request.auto_produce and not brief.storyboard:
        raise ValueError("Review a saved storyboard before creating the video")
    if brief.storyboard:
        if request.storyline_id != brief.storyboard_storyline_id:
            raise ValueError("Use the storyline saved with this storyboard")
        if len(sequence_by_id(request.sequence_id).frames) != len(brief.storyboard):
            raise ValueError("Choose a template matching the storyboard scene count")
    if not any(s.id == request.storyline_id for s in brief.storylines):
        raise ValueError("Select a saved storyline")
    if not any(sequence.id == request.sequence_id for sequence in frame_sequences()):
        raise ValueError("Choose a sequence from the current frame library")
    if request.frames and len(request.frames) != len(sequence_by_id(request.sequence_id).frames):
        raise ValueError("Choose one frame for each scene in the selected sequence")
    if request.frames and not all(f in {d.id for d in frame_library()} for f in request.frames):
        raise ValueError("Choose frames from the current library")
    if request.frames and "story-poll" in request.frames[:-1]:
        raise ValueError("Use the story poll for the closing question")
    if request.source_short_id:
        source = short_service.get(session, request.source_short_id)
        short_service.editable(source)
        studio = source.artifacts.get("studio", {})
        if not isinstance(studio, dict):
            raise ValueError("This video has no editable studio frames")
        if (studio.get("brief_id"), studio.get("storyline_id")) != (
            request.brief_id,
            request.storyline_id,
        ):
            raise ValueError("The original video belongs to another storyline")
    return schedule(session, request, tasks)


@router.get("/jobs/{job_id}")
def job(job_id: str, session: Session = Depends(get_session)) -> StudioJob:
    return get_job(session, job_id)


@router.get("/briefs/{brief_id}")
def brief(brief_id: str, session: Session = Depends(get_session)) -> StudioBrief:
    return get_brief(session, brief_id)


@router.get("/frames")
def frames() -> list[FrameDefinition]:
    return frame_library()


@router.get("/sequences")
def sequences() -> list[FrameSequence]:
    return frame_sequences()


@router.post("/frames/import")
async def import_frames(file: UploadFile) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith((".html", ".htm")):
        raise ValueError("Choose an HTML file")
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("HTML files must be smaller than 2 MB")
    try:
        document = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("HTML files must use UTF-8 encoding") from error
    return import_frame_html(document)


@router.get("/frames/{frame_id}/preview")
def frame_preview(frame_id: str, sequence_id: str | None = None) -> FileResponse:
    sequence = sequence_by_id(sequence_id) if sequence_id else frame_sequences()[0]
    definition = next((f for f in frame_library() if f.id == frame_id), None)
    if not definition:
        raise LookupError("Frame not found")
    key = fingerprint(
        {"version": VERSION, "frame": definition.model_dump(), "sequence": sequence.model_dump()}
    )[:24]
    output: Path = short_service.root.parent / "frame-previews" / (key + ".png")
    if not output.is_file():
        render_frame(definition.sample, sequence, output, sample=True)
    return FileResponse(output, media_type="image/png")


@router.get("/frames/{frame_id}/player", response_class=HTMLResponse)
def frame_player(
    frame_id: str, sequence_id: str | None = None, theme: FrameTheme | None = None
) -> HTMLResponse:
    sequence = sequence_by_id(sequence_id) if sequence_id else frame_sequences()[0]
    if theme:
        sequence = sequence.model_copy(update={"theme": theme})
    definition = next((f for f in frame_library() if f.id == frame_id), None)
    if not definition:
        raise LookupError("Frame not found")
    return HTMLResponse(
        frame_document(definition.sample, sequence, sample=True),
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"
            ),
        },
    )


@router.get("/sequences/{sequence_id}/sample.mp4")
def sequence_sample(sequence_id: str, theme: FrameTheme | None = None) -> FileResponse:
    from clipper.rendering.frames import add_original_music, render_frame_video
    from clipper.rendering.informative import assemble_sections
    from clipper.rendering.series import silent_audio

    sequence = sequence_by_id(sequence_id) if sequence_id else frame_sequences()[0]
    if theme:
        sequence = sequence.model_copy(update={"theme": theme})
    key = fingerprint(
        {
            "version": VERSION,
            "sequence": sequence.model_dump(),
            "frames": [f.model_dump() for f in frame_library()],
        }
    )[:24]
    root = short_service.root.parent / "frame-samples" / key
    output = root / "sample.mp4"
    # One process-wide lock prevents duplicate ffmpeg work for simultaneous previews.
    with _sample_lock:
        if not output.is_file():
            root.mkdir(parents=True, exist_ok=True)
            definitions = {f.id: f for f in frame_library()}
            audio = root / "silence.wav"
            silent_audio(audio, 2)
            scenes = []
            for i, kind in enumerate(sequence.frames):
                section = root / f"scene-{i}.mp4"
                if not section.is_file():
                    render_frame_video(
                        definitions[kind].sample,
                        sequence,
                        audio,
                        section,
                        2,
                        footer="ReachCut / sample layout",
                        sample=True,
                    )
                scenes.append(section)
            combined = assemble_sections(scenes, root / "combined.mp4")
            add_original_music(combined, output, 12)
    return FileResponse(output, media_type="video/mp4")
