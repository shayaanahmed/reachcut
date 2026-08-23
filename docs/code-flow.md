# Complete code flow

This guide traces the running application from the browser through FastAPI, SQLite,
Whisper, Ollama, caption generation, and FFmpeg. It describes the code that exists now;
planned VLM, diarization, tracking, publishing, and Remotion stages are not part of the
current runtime flow.

If you have worked in TypeScript, Java, C#, or a similar typed language, the most useful
Python mappings are:

- A Python `Protocol` is an interface. Implementations do not need to declare that they
  implement it; matching the required methods is sufficient.
- A Pydantic `BaseModel` is a typed DTO plus runtime validation and serialization.
- A frozen `dataclass` is a small immutable value object.
- `str | None` is a nullable string.
- A FastAPI route decorator is a controller-route annotation.
- A SQLAlchemy `Session` is an ORM unit of work. `commit()` persists its current changes.
- A `with` statement is deterministic resource management, similar to `using` in C# or
  try-with-resources in Java.
- A `lambda` is an inline callback. The pipeline passes lambdas into the stage runner so
  the runner can wrap execution with persistence, progress, and error handling.

## Runtime overview

```text
Browser
  -> React components
  -> useProjectWorkbench hook
  -> feature API client
  -> Next.js /api rewrite, or direct upload URL
  -> FastAPI route
  -> project/clip application service
  -> pure domain contract
  -> provider or media adapter
  -> SQLite plus files in CLIPPER_DATA_DIR
```

The main analysis path is:

```text
upload
  -> store and hash source media
  -> create Project row
  -> user clicks Analyze
  -> enqueue run_pipeline
  -> probe
  -> transcribe
  -> select_candidates
  -> write plan and caption artifacts
  -> render_previews
  -> review
  -> optional style update and preview replacement
  -> explicit approval
  -> final render
  -> download
```

## 1. Process startup and dependency construction

The native development command starts `uvicorn clipper.main:app`. The important startup
chain is:

1. [`clipper/main.py`](../apps/api/src/clipper/main.py) creates the `FastAPI` application.
2. Importing [`clipper/api/routes.py`](../apps/api/src/clipper/api/routes.py) assembles the
   health, project, and clip routers under `/api`.
3. Importing the route modules imports
   [`clipper/api/dependencies.py`](../apps/api/src/clipper/api/dependencies.py), which is the
   composition root for concrete providers and application services.
4. [`clipper/config.py`](../apps/api/src/clipper/config.py) executes `settings = Settings()`.
   Pydantic Settings reads `.env`, maps `CLIPPER_*` names to fields, converts strings to
   their declared Python types, validates constraints, and applies defaults for missing
   values.
5. [`clipper/persistence/session.py`](../apps/api/src/clipper/persistence/session.py) creates
   the data directory, SQLAlchemy engine, and `SessionLocal` session factory.
6. `dependencies.py` constructs one shared `OllamaEditorialProvider`, a health-reporting
   `FasterWhisperProvider`, the initial `Pipeline`, and `ClipService`.
7. When FastAPI's lifespan starts, `create_schema()` calls
   `Base.metadata.create_all(engine)` to create missing database tables.

### Dependency functions and objects

| Symbol                                   | Responsibility                                                                                                               |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `build_transcription_provider(language)` | Constructs Faster Whisper from the environment-selected model, device, precision, and optional request language.             |
| `transcription_provider`                 | Startup instance used for health identity and for constructing the initial pipeline.                                         |
| `editorial_provider`                     | Shared Ollama adapter configured with URL, model, timeout, token budgets, cache directory, and retry budgets.                |
| `pipeline`                               | Initial pipeline used to supply the artifact and renderer dependencies to `ClipService`.                                     |
| `clip_service`                           | Handles approval, style changes, preview replacement, and final rendering.                                                   |
| `pipeline_lock`                          | Allows only one analysis pipeline at a time in this API process.                                                             |
| `run_pipeline(project_id, language)`     | Background-task boundary. Opens a fresh session, constructs a language-specific Whisper provider and pipeline, then runs it. |
| `find_project(session, project_id)`      | Loads one project with its stages and clips eagerly populated for an API response.                                           |

Provider instances are constructed when the Python module is imported. Changing `.env`
therefore requires restarting the API process.

## 2. Web application composition

[`apps/web/app/page.tsx`](../apps/web/app/page.tsx) is the browser entry point. `Home()`
does not perform HTTP requests itself. It calls `useProjectWorkbench()` and passes the
returned state/actions to presentation components.

### React component chain

| Function/component | Responsibility                                                                                                   |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `Home()`           | Composes the upload panel, error display, and project list.                                                      |
| `ProjectUpload`    | Builds the upload `FormData`, including title, media, and rights confirmation. React calls its `action` handler. |
| `ProjectList`      | Maps project DTOs to `ProjectCard` components.                                                                   |
| `ProjectCard`      | Shows project status, language selection, Analyze/Re-analyze, stage progress, and clip cards.                    |
| `ProjectProgress`  | Converts the four persisted stage states into an aggregate percentage and per-stage display.                     |
| `ClipCard`         | Shows preview video, editorial score/rationale, approval actions, final-render action, and download link.        |
| `ClipStyleEditor`  | Collects caption and framing changes and passes the HTML form back to the workbench hook.                        |

### `useProjectWorkbench()` state and actions

[`features/projects/use-project-workbench.ts`](../apps/web/features/projects/use-project-workbench.ts)
owns browser behavior:

- The first `useEffect` calls `listProjects()` once after mounting.
- The second `useEffect` checks whether any project has status `processing`. If so, it calls
  `listProjects()` every 1.5 seconds. The API does not push progress; the UI polls it.
- `withBusy(operation, fallback)` centralizes busy state and UI error handling.
- `upload(data)` calls `uploadProject()`, then prepends the returned project to local state.
- `process(id)` calls `processProject()` and optimistically changes the local project status
  to `processing`; polling then supplies real stage updates.
- `styleUpdate(form)` translates browser form strings into the typed caption/framing DTO.
- `saveStyle(clipId, form)` calls `updateClipStyle()` and replaces the returned project in
  local state.
- `approve(clipId, approved)` calls `setApproval()` and replaces the returned project.
- `render(clipId)` calls `renderClip()`, then reloads all projects so `final_path` appears.

### Web transport and runtime validation

Feature HTTP calls live in:

- [`features/projects/api.ts`](../apps/web/features/projects/api.ts)
- [`features/clips/api.ts`](../apps/web/features/clips/api.ts)

`uploadProject()` uses `UPLOAD_API_URL`, which defaults to the API server directly. Other
requests use `API_URL`, which defaults to `/api`. In development and Docker,
[`next.config.ts`](../apps/web/next.config.ts) rewrites `/api/*` to `API_INTERNAL_URL`.

Every project response is parsed through the Zod `projectSchema` in
[`lib/contracts.ts`](../apps/web/lib/contracts.ts). A response that has HTTP 200 but violates
the expected shape still becomes a browser error instead of silently reaching components.

## 3. HTTP route map

[`clipper/api/routes.py`](../apps/api/src/clipper/api/routes.py) gives every route an `/api`
prefix. [`clipper/api/schemas.py`](../apps/api/src/clipper/api/schemas.py) defines request and
response DTOs. `ConfigDict(from_attributes=True)` lets Pydantic serialize SQLAlchemy objects
using their attributes.

| HTTP endpoint                     | Route function        | Delegates to / result                                                                           |
| --------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------- |
| `GET /api/health`                 | `health()`            | Reports FFmpeg/ffprobe availability and provider identities. It does not run a model inference. |
| `GET /api/projects`               | `projects()`          | Queries all projects with stages and clips, newest first.                                       |
| `GET /api/projects/{id}`          | `project()`           | Calls `project_or_404()` and returns one complete project DTO.                                  |
| `POST /api/projects/upload`       | `upload_project()`    | Validates authorization, stores media, creates a `Project`, and returns it.                     |
| `POST /api/projects/{id}/process` | `process_project()`   | Sets status to `processing` and schedules `run_pipeline()` as a FastAPI background task.        |
| `POST /api/projects/{id}/cancel`  | `cancel_project()`    | Writes `cancel_requested`; long stages check it through a cancellation callback.                |
| `PUT /api/clips/{id}/approval`    | `approve_clip()`      | Calls `ClipService.set_approval()` and returns the parent project.                              |
| `PUT /api/clips/{id}/style`       | `update_clip_style()` | Validates the request, calls `ClipService.update_style()`, and returns the parent project.      |
| `GET /api/clips/{id}/preview`     | `clip_preview()`      | Verifies the stored preview path exists and streams it with `FileResponse`.                     |
| `POST /api/clips/{id}/render`     | `render_clip()`       | Calls `ClipService.render_final()`; approval is mandatory.                                      |
| `GET /api/clips/{id}/final`       | `clip_final()`        | Verifies the stored final path exists and streams the MP4.                                      |

FastAPI injects a SQLAlchemy session into routes through `Depends(get_session)`. The
`get_session()` generator opens the session for the request and closes it afterward.

## 4. Upload flow

The complete upload call chain is:

```text
ProjectUpload form
  -> useProjectWorkbench.upload
  -> uploadProject(FormData)
  -> POST /api/projects/upload
  -> upload_project
  -> safe_filename
  -> store_upload
  -> detect_container
  -> create Project ORM object
  -> session.add + session.commit
  -> find_project
  -> ProjectResponse
  -> projectSchema.parse
  -> React state
```

### Route behavior

`upload_project()` in [`api/projects.py`](../apps/api/src/clipper/api/projects.py):

1. FastAPI validates title length and parses the multipart fields.
2. The explicit `authorization_confirmed` flag must be true.
3. `uuid4()` creates the project ID before any database insert.
4. `safe_filename()` removes path components and replaces unsafe filename characters.
5. The destination becomes
   `CLIPPER_DATA_DIR/projects/<project-id>/source/<safe-filename>`.
6. `store_upload()` writes the input in 1 MiB chunks, enforces the byte limit, calculates
   SHA-256 during the same pass, and captures the first bytes for signature checking.
7. `detect_container()` accepts known MP4/ISO-BMFF, Matroska, RIFF, or Ogg signatures. It
   does not trust the browser MIME type or filename extension.
8. If writing or validation fails, `store_upload()` removes the partial file and its newly
   created source directory.
9. A `Project` row records the ID, title, safe original filename, source path, SHA-256, and
   authorization time. Its initial status is `created`.

Uploading stores the file but does not invoke FFprobe, Whisper, Ollama, or FFmpeg.

## 5. Starting and supervising analysis

When the user clicks Analyze:

1. `ProjectCard` calls `onProcess(project.id)`.
2. `useProjectWorkbench.process()` reads the selected language and calls
   `processProject(id, language)`.
3. The API client sends `{ "language": "ur" }`, for example. Empty selection becomes
   `null`, meaning auto-detect.
4. `process_project()` rejects a project already marked `processing`, otherwise commits
   the new status and registers `run_pipeline()` with `BackgroundTasks`.
5. FastAPI returns HTTP 202 before model processing finishes.
6. After the response, `run_pipeline()` waits for `pipeline_lock`, opens a fresh database
   session, creates a Whisper provider containing this request's language hint, constructs
   a pipeline, and calls `Pipeline.run()`.

This is an in-process background job, not a separate durable worker. Restarting the API can
interrupt active work, although completed stage artifacts remain reusable.

### Cancellation

`cancel_project()` writes the string `cancel_requested`. The pipeline passes
`Pipeline._cancelled()` into Whisper and Ollama:

- `_cancelled()` expires ORM state, reloads the project, and returns true when the project
  disappeared or its status is `cancel_requested`.
- Whisper checks between yielded transcript segments.
- Ollama selection checks before starting and between candidate batches.
- An `InterruptedError` makes `StageRunner` mark the active stage `cancelled` and makes
  `Pipeline.run()` return the project to `created`.
- FFprobe, `StageRunner`, and preview/final FFmpeg rendering do not currently consult the
  cancellation callback. In particular, cancellation requested during preview rendering
  may not be observed before the pipeline reaches `review`. The reliable cancellation
  points in the current code are Whisper segment iteration and Ollama batch boundaries.

## 6. `Pipeline.run()` stage orchestration

[`projects/pipeline.py`](../apps/api/src/clipper/projects/pipeline.py) is the central
application workflow. It depends on the `TranscriptionProvider` and
`EditorialLLMProvider` protocols, not on Whisper or Ollama classes directly.

`Pipeline.run(session, project_id, target_count=5)` performs:

1. Load the project and set status `processing`.
2. Run the `probe` stage.
3. Run the `transcribe` stage.
4. Run the `select_candidates` stage.
5. Replace the project's `Clip` rows and write clip artifacts.
6. Run the `render_previews` stage.
7. Set project status `review`.

An `InterruptedError` returns the project to `created`. Any other exception marks the
project `failed` and is re-raised to `run_pipeline()`, which logs it.

### How `StageRunner.run()` wraps every stage

[`projects/stages.py`](../apps/api/src/clipper/projects/stages.py) owns resumability:

1. Find the `StageRun` row by project ID and stage name.
2. If its status is `succeeded`, its cache key matches, and its JSON artifact exists, load
   and return the artifact without calling the operation.
3. Otherwise create or update the row, set `running`, increment `attempts`, clear the old
   error, and commit.
4. Create `report_progress(value)`, which clamps progress to `0..0.99`, prevents progress
   from moving backward, and commits changes in increments of at least one percentage point.
5. Call the operation callback supplied by `Pipeline.run()`.
6. Serialize its result to `stages/<stage-name>.json`.
7. Mark the row `succeeded`, set progress to `1`, and commit.
8. On cancellation or error, store a structured error category/message and commit the final
   stage state before re-raising.

Cache keys include inputs that determine each stage result:

| Stage               | Cache-key inputs                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| `probe`             | Media SHA-256.                                                                                        |
| `transcribe`        | Media SHA-256 plus transcription provider identity, including model, device, precision, and language. |
| `select_candidates` | Media SHA-256, transcription identity, editorial model/contract identity, and requested count.        |
| `render_previews`   | Generated clip IDs plus media SHA-256.                                                                |

## 7. Probe stage

The pipeline callback calls `probe_media(source_path, max_duration_seconds)`:

1. `MediaProbe.inspect()` calls `require_tool("ffprobe")` to resolve an executable.
2. It builds a list of arguments. No shell command string is constructed.
3. `subprocess.run()` executes ffprobe with JSON output and a 120-second timeout.
4. The function rejects a failed command, invalid duration, over-limit duration, or media
   without a video stream.
5. `ProbeResult.as_artifact()` returns duration plus the original ffprobe payload.
6. The pipeline stores that payload in `Project.media_info` and the duration in
   `Project.duration_seconds`.

## 8. Transcription stage

The interface is `TranscriptionProvider` in
[`transcription/contracts.py`](../apps/api/src/clipper/transcription/contracts.py). Its
concrete adapter is `FasterWhisperProvider` in
[`providers/whisper.py`](../apps/api/src/clipper/providers/whisper.py).

### Function flow

1. `FasterWhisperProvider.identity` produces a stable string containing provider, model,
   device, compute type, and language. The pipeline uses it for provenance and cache keys.
2. `transcribe()` reports initial progress and calls `language_settings(language_hint)`.
3. `language_settings("ur")` supplies an Urdu code and native-script initial prompt. Other
   supported two-letter choices pass through without a special prompt. `None` requests
   Whisper auto-detection.
4. `_load()` lazily imports and constructs `WhisperModel`. API startup therefore does not
   load large model weights.
5. The provider requests transcription, word timestamps, VAD filtering, and the configured
   language/prompt.
6. Faster Whisper returns a lazy segment iterator. `_checked()` wraps it and checks
   cancellation before yielding each segment.
7. `transcribe()` converts external Whisper objects into strict domain `Word` and `Segment`
   Pydantic models, updates progress from media timestamps, and returns a `Transcript`.
8. The pipeline serializes the transcript with `model_dump(mode="json")`, persists it in the
   stage artifact and `Project.transcript`, then reconstructs a validated `Transcript` before
   calling editorial code.

## 9. Editorial/highlight-selection stage

The interface is `EditorialLLMProvider` in
[`editorial/contracts.py`](../apps/api/src/clipper/editorial/contracts.py). The implementation
is `OllamaEditorialProvider` in
[`providers/ollama.py`](../apps/api/src/clipper/providers/ollama.py).

The model is not allowed to invent source timestamps. Python constructs candidate windows,
the model ranks their stable IDs, and Python maps selected IDs back to the original windows.

### `select_candidates()` flow

1. Check cancellation.
2. `_candidate_options(transcript)` walks sentence segments and creates overlapping source
   windows. Anchors move forward by 45 seconds, target about 60 seconds, prefer a natural
   sentence ending by 75 seconds, and receive IDs such as `c0000`.
3. `_candidate_batches(options)` groups windows under approximately 8,000 transcript
   characters per prompt.
4. For each batch, `_batch_prompt()` asks for up to three ranked `EditorialCandidate`
   objects and explicitly forbids changing timestamps or IDs.
5. `generate_structured()` calls Ollama's `/api/generate` endpoint with `stream=false`,
   `think=false`, low temperature, the Pydantic JSON schema, and configured context/output
   budgets.
6. `validate_candidates()` rejects an incorrect envelope, unknown fields, bad scores,
   malformed IDs, IDs absent from the prompt, or duplicate IDs. It accepts at most five.
7. If the response is invalid or truncated, `generate_structured()` retries once with larger
   configured budgets and a compact corrective instruction.
8. `recover_truncated_candidates()` can scan incomplete JSON and retain fully encoded,
   valid candidate objects.
9. After batch ranking, `select_candidates()` keeps a high-scoring shortlist and asks the
   model to rerank it into meaningfully different final candidates.
10. If both attempts end because of output length, `fallback_candidates()` or
    `fallback_rerank()` uses deterministic ranking. Other provider/contract errors fail the
    stage rather than silently substituting a model.
11. `create_editing_plan()` combines validated editorial judgments with the Python-owned
    `TimeRange` to create `EditingPlanV1` objects.

### Editorial response cache

Before contacting Ollama, `generate_structured()` calls `_read_cache()`. `_cache_path()`
hashes the editorial contract version, selected model, and exact prompt. Valid results are
written under `CLIPPER_DATA_DIR/cache/editorial`. Cached content is revalidated against the
current allowed candidate IDs before reuse.

### Editing-plan validation

[`domain/editing_plan.py`](../apps/api/src/clipper/domain/editing_plan.py) is the trusted
boundary between model judgment and rendering:

- All models forbid extra fields.
- Scores must be integers from 0 to 100.
- Source ranges must be ordered and non-negative.
- Caption colors, sizes, positions, animation modes, and line limits are constrained.
- Hook, emphasis, CTA, and effect timestamps must fit inside the selected clip duration.
- Zoom and sound-effect parameters are clamped to safe ranges.

Only an `EditingPlanV1` that passes these validators reaches artifact generation or FFmpeg.

## 10. Creating clips and caption artifacts

After editorial selection succeeds, `Pipeline.run()`:

1. Deletes the project's previous `Clip` rows.
2. Validates each returned plan again.
3. Creates and flushes a `Clip` row so SQLAlchemy assigns its UUID.
4. Calls `ClipArtifactService.write(project, clip, plan, transcript)`.

`ClipArtifactService.write()` in
[`projects/artifacts.py`](../apps/api/src/clipper/projects/artifacts.py):

1. Creates the clip artifact directory.
2. Writes `editing-plan.json`.
3. `relative_words()` selects transcript words intersecting the source time range and
   translates absolute source timestamps into clip-relative timestamps.
4. `phrase_cues()` groups words by word count, character count, and pauses longer than
   0.45 seconds. `_join_words()` normalizes Unicode and fixes punctuation spacing.
5. `serialize_srt()` writes broadly compatible subtitles.
6. `serialize_vtt()` writes WebVTT subtitles.
7. `serialize_ass()` writes styled ASS subtitles. It calls `animated_events()` to implement
   static highlights, active-word pop animation, or karaoke timing.
8. `provenance.json` records transcription/editorial identities and source media SHA-256.

The LLM does not build caption lines, animation tags, or subtitle files.

## 11. Preview rendering

`Pipeline._render_previews()` loops over the newly created clips:

1. Build a `RenderRequest` using the source media, validated plan, `captions.ass`, output
   path, and `preview=True`.
2. Call `VideoRenderer.render()`.
3. Save the output path into `Clip.preview_path` and commit after each clip.
4. Report aggregate preview progress.

`VideoRenderer.render()` in
[`rendering/service.py`](../apps/api/src/clipper/rendering/service.py):

1. Ensures the output directory exists.
2. Resolves FFmpeg with `require_tool("ffmpeg")`.
3. Calls `build_ffmpeg_command()` to construct a typed, shell-free argument vector.
4. Executes `subprocess.run()` with a one-hour timeout.
5. Converts nonzero exit status into `MediaError` containing the tail of stderr.
6. Writes a render manifest beside the MP4.

`build_ffmpeg_command()` in
[`rendering/ffmpeg.py`](../apps/api/src/clipper/rendering/ffmpeg.py) chooses:

- Preview: 360x640, CRF 25.
- Final: 1080x1920, CRF 20.
- Video: libx264 using `veryfast` preset.
- Audio: optional input audio mapped to AAC at 160 kbit/s.
- Source segment: `-ss` plus selected plan duration.

`build_video_filter()` in
[`rendering/framing.py`](../apps/api/src/clipper/rendering/framing.py) creates either:

- `center_crop`: scale up and crop to fill 9:16.
- `blurred_background`: fill the canvas with a blurred/darkened copy and center the complete
  foreground frame over it.

Both paths burn ASS/SRT subtitles into the output. Rendering constructs an argument list and
never invokes a shell.

## 12. Review and style-update flow

When analysis finishes, `Pipeline.run()` sets the project to `review`. Browser polling loads
the clips and `ClipCard` requests each preview through `GET /api/clips/{id}/preview`.

When the user applies caption/framing changes:

```text
ClipStyleEditor
  -> useProjectWorkbench.saveStyle
  -> styleUpdate(form)
  -> updateClipStyle API client
  -> PUT /api/clips/{id}/style
  -> update_clip_style route
  -> ClipService.update_style
  -> update EditingPlanV1
  -> rewrite captions and plan artifacts
  -> render preview.pending.mp4
  -> atomically replace preview.mp4
  -> clear final_path
  -> return parent Project
```

Important behavior inside `ClipService.update_style()`:

1. `_clip()` loads the clip or raises `ClipNotFoundError`.
2. The project must still contain its transcript.
3. `EditingPlanV1.model_validate(clip.plan)` reconstructs the previous validated plan.
4. `model_copy(update=...)` produces a new plan without mutating the previous object.
5. Caption artifacts are rewritten from the persisted transcript.
6. A new preview renders to `preview.pending.mp4`.
7. If rendering fails, pending outputs are deleted and artifacts are restored from the old
   plan; the database is left unchanged.
8. On success, `Path.replace()` swaps pending preview/manifest files into their stable names.
9. The new plan and preview path are committed, while `final_path` is cleared because an old
   final render would no longer match the current style.

## 13. Approval, final render, and download

Approval and rendering are separate user actions.

### Approval

`setApproval()` sends `{ approved: true|false }` to `approve_clip()`, which calls
`ClipService.set_approval()`. The service writes `approved` or `rejected`, commits, and
returns the parent project ID. Approval itself does not render media.

### Final render

`renderClip()` sends `POST /api/clips/{id}/render`:

1. `render_clip()` calls `ClipService.render_final()`.
2. `_clip()` ensures the clip exists.
3. The service rejects every clip whose `approval_status` is not exactly `approved`.
4. It loads the parent project and reconstructs the validated editing plan.
5. If ASS captions are missing but a transcript exists, it regenerates artifacts.
6. It prefers `captions.ass`, falling back to SRT only if ASS is unavailable.
7. It calls `VideoRenderer.render()` with `preview=False`, producing 1080x1920 `final.mp4`
   and `final.manifest.json`.
8. It stores `Clip.final_path` and commits.
9. The browser reloads projects, sees `final_path`, and displays the download link.
10. `GET /api/clips/{id}/final` returns the MP4 with `FileResponse`.

There is no automatic publication step.

## 14. Persistence model and state changes

[`persistence/models.py`](../apps/api/src/clipper/persistence/models.py) contains three tables:

### `Project`

Owns source metadata, current workflow status, ffprobe output, full transcript JSON, stage
rows, and clip rows.

Typical status progression:

```text
created -> processing -> review
                    \-> failed
processing -> cancel_requested -> created
```

`cancel_requested` is an operational string consumed by cancellation checks; the declared
`ProjectStatus` enum lists the stable resting statuses.

### `StageRun`

Stores one row per named project stage with status, progress, attempt count, cache key,
structured error, and timing. The database state drives the progress UI; the JSON stage
artifact drives result reuse.

### `Clip`

Stores a validated plan as JSON, approval state, preview path, and final path. It belongs to
one project. Deleting a project cascades to its stages and clips.

## 15. Files written to the data directory

With the default layout, the current implementation writes:

```text
data/
  clipper.db
  cache/
    editorial/
      <prompt-hash>.json
  projects/
    <project-id>/
      source/
        <uploaded-media>
        stages/
          probe.json
          transcribe.json
          select_candidates.json
          render_previews.json
        clips/
          <clip-id>/
            editing-plan.json
            captions.srt
            captions.vtt
            captions.ass
            provenance.json
            preview.mp4
            preview.manifest.json
            final.mp4
            final.manifest.json
```

The exact root comes from `CLIPPER_DATA_DIR`; SQLite can be moved independently with
`CLIPPER_DATABASE_URL`.

## 16. Error translation

Errors cross boundaries deliberately:

- Media modules raise `MediaError` for invalid media, missing tools, ffprobe failures, and
  FFmpeg failures.
- Provider output problems raise `EditorialOutputError`.
- Project services raise `ClipNotFoundError` and `ClipStateError`.
- API routes translate known application errors into HTTP 404, 409, 415, or 422 responses.
- Unexpected pipeline errors are recorded on the active stage, mark the project `failed`,
  and are logged by `run_pipeline()`.
- Web API clients turn non-success responses into JavaScript `Error` values; the workbench
  hook converts them into user-visible error state.

## 17. Code present but not wired into the current runtime

Some modules define future-facing or compatibility behavior but are not called by the flow
above:

- [`editorial/highlights.py`](../apps/api/src/clipper/editorial/highlights.py) provides
  `semantic_windows()` and `diverse_top_plans()`. The active Ollama adapter currently uses
  its own `_candidate_options()` and reranking flow instead.
- [`rendering/tracking.py`](../apps/api/src/clipper/rendering/tracking.py) provides
  `smooth_crop_path()`, but no detector generates `CropPoint` values and the FFmpeg filter
  graph does not consume a crop path yet.
- [`providers/base.py`](../apps/api/src/clipper/providers/base.py) declares placeholder
  `VisionLanguageProvider`, `DiarizationProvider`, and `FaceTrackingProvider` protocols.
  No concrete adapters are registered for them.
- [`services/hardware.py`](../apps/api/src/clipper/services/hardware.py) can detect a
  suggested hardware profile, but startup currently uses the explicit `.env` device,
  precision, and FFmpeg settings rather than calling `detect_profile()`.
- `services/render.py:render_vertical()` is a legacy convenience wrapper. Active workflows
  construct `RenderRequest` and call `VideoRenderer` directly.

These files are useful extension points, but reading them as part of today's call graph
would imply behavior that the application does not currently execute.

## 18. Public interfaces and compatibility files

Package `__init__.py` files expose public interfaces so callers do not depend on private
implementation helpers. The active dependency direction is:

```text
API routes
  -> project services
  -> caption/editorial/transcription/rendering contracts
  -> provider, persistence, and subprocess adapters
```

Files under `clipper/services/`, plus `clipper/db.py` and `apps/web/lib/api.ts`, are
compatibility import surfaces. They forward to the feature-owned modules and should not
receive new behavior.

## 19. Suggested reading order

For a first pass through the source, follow the runtime rather than reading directories
alphabetically:

1. [`apps/web/app/page.tsx`](../apps/web/app/page.tsx)
2. [`apps/web/features/projects/use-project-workbench.ts`](../apps/web/features/projects/use-project-workbench.ts)
3. [`apps/web/features/projects/api.ts`](../apps/web/features/projects/api.ts)
4. [`apps/api/src/clipper/main.py`](../apps/api/src/clipper/main.py)
5. [`apps/api/src/clipper/api/projects.py`](../apps/api/src/clipper/api/projects.py)
6. [`apps/api/src/clipper/api/dependencies.py`](../apps/api/src/clipper/api/dependencies.py)
7. [`apps/api/src/clipper/projects/pipeline.py`](../apps/api/src/clipper/projects/pipeline.py)
8. [`apps/api/src/clipper/projects/stages.py`](../apps/api/src/clipper/projects/stages.py)
9. [`apps/api/src/clipper/providers/whisper.py`](../apps/api/src/clipper/providers/whisper.py)
10. [`apps/api/src/clipper/providers/ollama.py`](../apps/api/src/clipper/providers/ollama.py)
11. [`apps/api/src/clipper/domain/editing_plan.py`](../apps/api/src/clipper/domain/editing_plan.py)
12. [`apps/api/src/clipper/projects/artifacts.py`](../apps/api/src/clipper/projects/artifacts.py)
13. [`apps/api/src/clipper/rendering/service.py`](../apps/api/src/clipper/rendering/service.py)
14. [`apps/api/src/clipper/projects/clips.py`](../apps/api/src/clipper/projects/clips.py)

Use [`module-ownership.md`](module-ownership.md) afterward to decide where a future change
belongs.
