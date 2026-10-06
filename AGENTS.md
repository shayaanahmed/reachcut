# ReachCut contribution architecture

## Essential commands

```bash
pnpm dev          # Start API (8000) and web (3000)
pnpm check        # Lint, typecheck, and format
pnpm test         # Run all tests
```

## Ownership

- Media: `apps/api/src/clipper/media/`
- Transcription: `apps/api/src/clipper/transcription/`
- Editorial: `apps/api/src/clipper/editorial/`
- Providers: `apps/api/src/clipper/providers/`
- Captions: `apps/api/src/clipper/captions/`
- Rendering: `apps/api/src/clipper/rendering/`
- Projects: `apps/api/src/clipper/projects/`

## Key rules

- Pure modules don't import FastAPI, SQLAlchemy, or subprocess
- React components only present data; HTTP calls in API clients
- Never invoke subprocesses through shell - use argument arrays
