# Architecture and phased plan

## Boundaries

The Next.js client is a review surface. FastAPI is the control plane and owns authorization confirmation, input validation, projects, jobs, stage transitions, provider selection, artifacts, approvals, and exports. SQLite is the default durable store; SQLAlchemy models avoid SQLite-only data types so PostgreSQL can be added later. Large immutable artifacts live under the configured data directory.

Model and media integrations sit behind typed providers. Pipeline services depend on those interfaces, not model names. Every candidate becomes an `EditingPlanV1`; only validated plans may reach FFmpeg or, later, Remotion. Subprocesses receive argument arrays and never use a shell.

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

An authorized local upload is signature-checked and copied to a project-owned directory, probed, transcribed with word timestamps, chunked, scored by a local Qwen model through Ollama, converted to validated plans, reviewed, approved, and rendered to a 9:16 MP4 plus SRT, VTT, and plan/manifest JSON. Tests replace heavyweight providers with deterministic fakes; production does not silently replace missing local models.

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

- Model provider: implement the relevant protocol in `clipper.providers.base`, add configuration and a health check, then register it in the application composition root.
- Editing template: add a versioned JSON/Zod configuration. Templates may reference only registered assets/effects; they cannot execute code.
- Publishing adapter: implement draft/schedule validation and OAuth token storage. Require an approved clip and a separate explicit publish action. If an official API is unavailable, export a package.

