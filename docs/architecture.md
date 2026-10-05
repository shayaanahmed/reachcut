# Architecture

## Dependency rule

The API and web UI are delivery adapters. Project application services coordinate
feature modules. Feature modules contain pure policy wherever possible, while
SQLAlchemy, model providers, and subprocess execution remain adapters at the edge.
Publication tracking is coordinated by the project application layer: a
publication links one rendered clip to one platform post, while immutable metric
snapshots retain performance history. Provider adapters own OAuth/token and upload
HTTP calls; the project service requires explicit approval and records provider IDs,
processing state, and the final provider-returned post URL. Metrics use a separate
provider adapter: YouTube statistics sync into immutable snapshots, while other
platform adapters can add analytics without changing publication workflows.
Reusable social-account records contain public identity, metadata defaults, and a
connection state. Encrypted OAuth credentials remain outside SQLite under the private
data directory. Publications use a separate immutable account link so old
records remain valid when an account is renamed or archived, without altering an
existing publications table during local schema creation.

```text
Next.js page -> feature components/hooks -> feature API clients -> HTTP contracts
                                                               |
FastAPI routes -> project/clip services -> caption/editorial/render/transcription ports
                    |                         |
                    +-> persistence adapter   +-> provider + FFmpeg adapters
```

Dependencies point inward: captions, editorial, transcription, and pure rendering
command construction do not import FastAPI or SQLAlchemy. Rendering does not build
caption text, and caption modules never execute FFmpeg. Provider adapters implement
the transcription/editorial protocols. The project pipeline is the composition
boundary for these capabilities.

See [module ownership](module-ownership.md) for public interfaces and change routing.

## Boundaries

The Next.js client is a review surface. FastAPI is the control plane and owns authorization confirmation, input validation, projects, jobs, stage transitions, provider selection, artifacts, approvals, and exports. SQLite is the default durable store; SQLAlchemy models avoid SQLite-only data types so PostgreSQL can be added later. Large immutable artifacts live under the configured data directory.

Model and media integrations sit behind typed providers. Project services depend on those interfaces, not model names. Every candidate becomes an `EditingPlanV1`; only validated plans may reach FFmpeg or, later, Remotion. Subprocesses receive argument arrays and never use a shell.

Topic discovery follows the same boundary: the pure `discovery` module owns typed
topic, category, trend, and source results, while the Google Trends/YouTube network
adapter lives in `providers`. A discovered source enters the existing authorized URL-import workflow;
discovery never bypasses media-rights confirmation. Publish-potential recommendations
are deterministic editorial guidance based on candidate signals and never guarantee
views or revenue.

```text
Next.js review UI
       │ HTTP/SSE (planned for progress)
FastAPI control plane ── SQLite
       │
resumable stage runner
  ├── faster-whisper transcription
  ├── Ollama / llama.cpp editorial endpoint
  ├── optional VLM / diarization / tracking providers
  └── FFprobe + deterministic FFmpeg renderer
       │
private data/artifact directory
```

## Smallest complete vertical slice

An authorized local upload or allowlisted URL import is signature-checked and stored in a project-owned directory, probed, transcribed with word timestamps, chunked, scored by a local Qwen model through Ollama, converted to validated plans, reviewed, approved, and rendered to a 9:16 MP4 plus SRT, VTT, and plan/manifest JSON. The URL adapter invokes yt-dlp with a fixed argument vector and never through a shell. Tests replace heavyweight providers with deterministic fakes; production does not silently replace missing local models.

## Stages and resumability

Stages are persisted as independent rows with `pending`, `running`, `succeeded`, `failed`, or `cancelled` state, attempt count, progress, timing, structured error data, and a cache key. A stage runner reuses a successful matching cache key and leaves artifacts available for diagnosis. Jobs are single-concurrency by default. Cancellation is checked between stages and by long-running providers.

## Phases

1. **Local MVP:** upload, probe, transcription, editorial candidates, plan validation, center-crop rendering, captions, review/approval, durable exports.
2. **Polish:** MediaPipe tracking, crop keyframe editor, Remotion data-driven templates, hooks/CTAs, reduced-resolution previews, controlled audio assets.
3. **Multimodal:** sampled candidate windows, replaceable Qwen3-VL provider, visual reranking, reactions, scene-aware edits, multi-speaker layouts.
4. **Automation:** hardened worker process, watch folders, batches, schedules, optional OAuth publishing adapters, hardware-specific tuning.

## Hardware profiles

`cpu_low_memory` uses Whisper Small INT8, sequential providers, a 540p proxy, and libx264. Apple profiles select Metal-capable model endpoints and VideoToolbox when detected; NVIDIA profiles select CUDA/CTranslate2 and NVENC. Detection is advisory and every selection remains overridable. See `clipper.services.hardware`.

## Extension contracts

- Transcription provider: implement `clipper.transcription.TranscriptionProvider`, add configuration and a health check, then register it in `clipper.api.dependencies`.
- Editorial provider: implement `clipper.editorial.EditorialLLMProvider` and register it in `clipper.api.dependencies`.
- Editing template: add a versioned JSON/Zod configuration. Templates may reference only registered assets/effects; they cannot execute code.
- Publishing adapter: implement `clipper.publishing.PublishingAdapter`, keep network calls in `providers/`, and orchestrate approval, credentials, processing-state refresh, and publication persistence in `projects/`. Current adapters cover YouTube, TikTok, Instagram Reels, Facebook Reels, and X.
