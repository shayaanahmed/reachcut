# Clipper contribution architecture

These instructions apply to every human or coding agent changing this repository.
Read `docs/architecture.md` and `docs/module-ownership.md` before editing.

## Required workflow

1. Identify the owning feature module before changing code.
2. Preserve API responses, persisted data, generated artifacts, and rendering behavior unless
   the request explicitly requires a breaking change.
3. Keep the change within one focused module whenever possible. If more than one module must
   change, explain the dependency and keep the public interface between them small.
4. Add or update a focused test for every responsibility moved or behavior changed.
5. Run formatting, linting, type checking, tests, and the relevant production build.

## Ownership

- Media ingestion and validation: `apps/api/src/clipper/media/`
- Transcription and language support: `apps/api/src/clipper/transcription/`
- Editorial highlight policy: `apps/api/src/clipper/editorial/`
- Model adapters, including Ollama and Whisper: `apps/api/src/clipper/providers/`
- Caption text and serialization: `apps/api/src/clipper/captions/`
- Caption word animation: `apps/api/src/clipper/captions/animation.py`
- Framing, composition, and FFmpeg: `apps/api/src/clipper/rendering/`
- Project/clip workflows and artifacts: `apps/api/src/clipper/projects/`
- SQLAlchemy persistence: `apps/api/src/clipper/persistence/`
- FastAPI contracts and routes: `apps/api/src/clipper/api/`
- Web project features: `apps/web/features/projects/`
- Web clip features: `apps/web/features/clips/`
- Shared web transport/contracts only: `apps/web/lib/`

## Dependency rules

- Pure caption, editorial, transcription, and rendering-policy modules must not import
  FastAPI, SQLAlchemy, persistence models, or subprocess execution.
- FastAPI routes translate HTTP only; workflows belong in `projects/` services.
- SQLAlchemy access stays in persistence adapters or project application services, never in
  pure feature policy.
- Caption text construction, animation generation, ASS serialization, framing filters,
  FFmpeg command construction, and process execution remain separate responsibilities.
- React components present data. Polling and mutations belong in hooks; HTTP calls belong in
  feature API clients.
- New code must import public package interfaces. Do not call underscore-prefixed methods
  across module boundaries.
- `clipper.services.*`, `clipper.db`, and `apps/web/lib/api.ts` are compatibility surfaces;
  do not add new behavior there.
- Use typed configuration/request objects instead of unstructured dictionaries where
  practical.
- Never invoke media subprocesses through a shell. Build argument vectors separately from
  execution.

`apps/api/tests/test_architecture.py` enforces the most important dependency boundaries.
Update that test only when an intentional architectural decision is also documented.

## Validation commands

```bash
pnpm check
pnpm test
pnpm --dir apps/web build
```

For rendering changes, also run `scripts/smoke_render.py` with the repository fixture.
