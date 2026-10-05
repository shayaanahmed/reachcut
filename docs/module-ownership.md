# Module ownership and change routing

Each directory owns one feature or adapter. Public imports are exposed from the
package `__init__.py`; underscore-prefixed helpers and unexported functions are
implementation details. The old `clipper.services.*` and `clipper.db` modules are
compatibility imports only and should not receive new logic.

Repository-wide contribution rules are defined in `AGENTS.md`. Executable checks
in `apps/api/tests/test_architecture.py` prevent pure domain modules from acquiring
framework, persistence, or subprocess dependencies and keep the web page as a
small composition root.

## Backend modules

| Change                                                 | Owning module                                                                   | Public interface                                                        |
| ------------------------------------------------------ | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Upload signatures, safe names, streaming limits        | `clipper/media/ingestion.py`                                                    | `store_upload`, `safe_filename`, `StoredUpload`                         |
| Public URL validation                                  | `clipper/media/url_policy.py`                                                   | `validate_public_media_url`                                             |
| yt-dlp process adapter                                 | `clipper/providers/yt_dlp.py`                                                   | `YtDlpDownloader`                                                       |
| FFprobe validation                                     | `clipper/media/probe.py`                                                        | `MediaProbe`, `ProbeResult`                                             |
| Transcript data and provider contract                  | `clipper/transcription/`                                                        | `Transcript`, `TranscriptionProvider`                                   |
| Urdu or another language hint/prompt                   | `clipper/transcription/languages.py`                                            | `language_settings`, `TranscriptionLanguage`                            |
| Transcript windows, ranking diversity                  | `clipper/editorial/highlights.py`                                               | `semantic_windows`, `diverse_top_plans`                                 |
| Editorial model integration contract                   | `clipper/editorial/contracts.py`                                                | `EditorialLLMProvider`                                                  |
| Publish-potential scoring                              | `clipper/editorial/recommendations.py`                                          | `recommend_for_publishing`, `PublishRecommendation`                     |
| Topic/category trend and source discovery              | `clipper/discovery/`                                                            | `DiscoveryService`, typed discovery results                             |
| Google Trends and YouTube discovery adapter            | `clipper/providers/trend_discovery.py`                                          | `GoogleYouTubeDiscoveryProvider`                                        |
| Phrase construction and punctuation                    | `clipper/captions/text.py`                                                      | `phrase_cues`                                                           |
| Subtitle appearance and ASS document style             | `clipper/captions/ass.py`                                                       | `serialize_ass`                                                         |
| Word animation and highlighting                        | `clipper/captions/animation.py`                                                 | `animated_events`                                                       |
| SRT/VTT serialization                                  | `clipper/captions/formats.py`                                                   | `serialize_srt`, `serialize_vtt`                                        |
| Full-screen crop or blurred-background composition     | `clipper/rendering/framing.py`                                                  | `build_video_filter`                                                    |
| FFmpeg argument construction                           | `clipper/rendering/ffmpeg.py`                                                   | `build_ffmpeg_command`, `FfmpegCommand`                                 |
| FFmpeg process execution, preview/final manifests      | `clipper/rendering/service.py`                                                  | `VideoRenderer`, `RenderRequest`                                        |
| Crop tracking/smoothing                                | `clipper/rendering/tracking.py`                                                 | `smooth_crop_path`, `CropPoint`                                         |
| Clip caption/plan/provenance artifacts                 | `clipper/projects/artifacts.py`                                                 | `ClipArtifactService`                                                   |
| Clip approval, styling, preview and final workflows    | `clipper/projects/clips.py`                                                     | `ClipService`, `ClipStyleUpdate`                                        |
| Publication upload and metric snapshot workflows       | `clipper/projects/publications.py`                                              | `PublicationService`, `AutomaticPublicationCreate`, `MetricCreate`      |
| Publishing and metrics adapter contracts               | `clipper/publishing/`                                                           | `PublishingAdapter`, `MetricsAdapter`, `CredentialStore`, typed results |
| Social OAuth, API uploads, and encrypted token storage | `clipper/providers/{social_oauth,youtube,tiktok,meta,x,credentials}.py`         | OAuth clients, publishing adapters, and `EncryptedCredentialStore`      |
| Publishing account connection workflow                 | `clipper/projects/publishing_connections.py`                                    | `PublishingConnectionService`                                           |
| Social-account setup and publishing defaults           | `clipper/projects/social_accounts.py`                                           | `SocialAccountService`, `SocialAccountCreate`, `SocialAccountUpdate`    |
| Resumable project stages                               | `clipper/projects/stages.py`                                                    | `StageRunner.run`                                                       |
| End-to-end analysis orchestration                      | `clipper/projects/pipeline.py`                                                  | `Pipeline.run`                                                          |
| Database tables and sessions                           | `clipper/persistence/`                                                          | exported models, `get_session`, `SessionLocal`                          |
| HTTP request/response shapes                           | `clipper/api/schemas.py`                                                        | Pydantic request/response models                                        |
| HTTP endpoints                                         | `clipper/api/{health,discovery,projects,clips,publications,social_accounts}.py` | resource routers assembled by `api/routes.py`                           |

## Web modules

| Change                                        | Owning module                                         |
| --------------------------------------------- | ----------------------------------------------------- |
| Project upload/list/process requests          | `apps/web/features/projects/api.ts`                   |
| Clip approval/style/render requests           | `apps/web/features/clips/api.ts`                      |
| Runtime API response validation               | `apps/web/lib/contracts.ts`                           |
| Project polling and UI actions                | `apps/web/features/projects/use-project-workbench.ts` |
| Project upload form                           | `apps/web/features/projects/project-upload.tsx`       |
| Stage progress presentation                   | `apps/web/features/projects/project-progress.tsx`     |
| Project card/list presentation                | `apps/web/features/projects/project-{card,list}.tsx`  |
| Clip presentation and actions                 | `apps/web/features/clips/clip-card.tsx`               |
| Caption/framing controls                      | `apps/web/features/clips/clip-style-editor.tsx`       |
| Publication assistant and project performance | `apps/web/features/publishing/`                       |
| Trend discovery and source selection          | `apps/web/features/discovery/`                        |

## Practical examples

- Subtitle appearance → `captions/ass.py`
- Subtitle phrase breaks or punctuation → `captions/text.py`
- Word animation → `captions/animation.py`
- Urdu transcription → `transcription/languages.py`
- Full-screen framing → `rendering/framing.py`
- Preview/final encoding → `rendering/ffmpeg.py` and `rendering/service.py`
- Highlight selection → `editorial/highlights.py` or the provider in `providers/ollama.py`
- Publishing recommendation → `editorial/recommendations.py`
- Topic/category trends and source search → `discovery/` plus `providers/trend_discovery.py`
- Project/clip state workflow → `projects/`
- Publication tracking and provider/manual metrics → `projects/publications.py`
- Account setup and metadata defaults → `projects/social_accounts.py`
- API response compatibility → `api/schemas.py`
- React caption controls → `features/clips/clip-style-editor.tsx`

## Testing rule

Pure policy tests live next to the backend test suite and avoid invoking model or
media processes. Application-service tests inject or construct deterministic
adapters. Route tests assert stable HTTP behavior. Web component tests cover moved
presentation logic, while API-client tests assert transport and contract parsing.
