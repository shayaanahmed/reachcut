# Module ownership and change routing

Each directory owns one feature or adapter. Public imports are exposed from the
package `__init__.py`; underscore-prefixed helpers and unexported functions are
implementation details. The old `clipper.services.*` and `clipper.db` modules are
compatibility imports only and should not receive new logic.

## Backend modules

| Change | Owning module | Public interface |
| --- | --- | --- |
| Upload signatures, safe names, streaming limits | `clipper/media/ingestion.py` | `store_upload`, `safe_filename`, `StoredUpload` |
| FFprobe validation | `clipper/media/probe.py` | `MediaProbe`, `ProbeResult` |
| Transcript data and provider contract | `clipper/transcription/` | `Transcript`, `TranscriptionProvider` |
| Urdu or another language hint/prompt | `clipper/transcription/languages.py` | `language_settings`, `TranscriptionLanguage` |
| Transcript windows, ranking diversity | `clipper/editorial/highlights.py` | `semantic_windows`, `diverse_top_plans` |
| Editorial model integration contract | `clipper/editorial/contracts.py` | `EditorialLLMProvider` |
| Phrase construction and punctuation | `clipper/captions/text.py` | `phrase_cues` |
| Subtitle appearance and ASS document style | `clipper/captions/ass.py` | `serialize_ass` |
| Word animation and highlighting | `clipper/captions/animation.py` | `animated_events` |
| SRT/VTT serialization | `clipper/captions/formats.py` | `serialize_srt`, `serialize_vtt` |
| Full-screen crop or blurred-background composition | `clipper/rendering/framing.py` | `build_video_filter` |
| FFmpeg argument construction | `clipper/rendering/ffmpeg.py` | `build_ffmpeg_command`, `FfmpegCommand` |
| FFmpeg process execution, preview/final manifests | `clipper/rendering/service.py` | `VideoRenderer`, `RenderRequest` |
| Crop tracking/smoothing | `clipper/rendering/tracking.py` | `smooth_crop_path`, `CropPoint` |
| Clip caption/plan/provenance artifacts | `clipper/projects/artifacts.py` | `ClipArtifactService` |
| Clip approval, styling, preview and final workflows | `clipper/projects/clips.py` | `ClipService`, `ClipStyleUpdate` |
| Resumable project stages | `clipper/projects/stages.py` | `StageRunner.run` |
| End-to-end analysis orchestration | `clipper/projects/pipeline.py` | `Pipeline.run` |
| Database tables and sessions | `clipper/persistence/` | exported models, `get_session`, `SessionLocal` |
| HTTP request/response shapes | `clipper/api/schemas.py` | Pydantic request/response models |
| HTTP endpoints | `clipper/api/{health,projects,clips}.py` | resource routers assembled by `api/routes.py` |

## Web modules

| Change | Owning module |
| --- | --- |
| Project upload/list/process requests | `apps/web/features/projects/api.ts` |
| Clip approval/style/render requests | `apps/web/features/clips/api.ts` |
| Runtime API response validation | `apps/web/lib/contracts.ts` |
| Project polling and UI actions | `apps/web/features/projects/use-project-workbench.ts` |
| Project upload form | `apps/web/features/projects/project-upload.tsx` |
| Stage progress presentation | `apps/web/features/projects/project-progress.tsx` |
| Project card/list presentation | `apps/web/features/projects/project-{card,list}.tsx` |
| Clip presentation and actions | `apps/web/features/clips/clip-card.tsx` |
| Caption/framing controls | `apps/web/features/clips/clip-style-editor.tsx` |

## Practical examples

- Subtitle appearance → `captions/ass.py`
- Subtitle phrase breaks or punctuation → `captions/text.py`
- Word animation → `captions/animation.py`
- Urdu transcription → `transcription/languages.py`
- Full-screen framing → `rendering/framing.py`
- Preview/final encoding → `rendering/ffmpeg.py` and `rendering/service.py`
- Highlight selection → `editorial/highlights.py` or the provider in `providers/ollama.py`
- Project/clip state workflow → `projects/`
- API response compatibility → `api/schemas.py`
- React caption controls → `features/clips/clip-style-editor.tsx`

## Testing rule

Pure policy tests live next to the backend test suite and avoid invoking model or
media processes. Application-service tests inject or construct deterministic
adapters. Route tests assert stable HTTP behavior. Web component tests cover moved
presentation logic, while API-client tests assert transport and contract parsing.
