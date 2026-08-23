# Clipper

Clipper is a local-first application for turning media you are authorized to repurpose into reviewable vertical clips. The core pipeline uses local models and local FFmpeg processes; it does not require a cloud-model account and never publishes automatically.

The current vertical slice provides secure upload, media probing, durable stage state, provider-based `faster-whisper` transcription, Ollama/Qwen editorial selection, schema-validated editing plans, deterministic 9:16 FFmpeg rendering, customizable animated subtitles, and a small review UI. Human approval is required before final rendering. Exports preserve the complete source frame over a soft 9:16 background by default; center-crop remains available per clip.

For Urdu and other non-English media, select the spoken language before analysis. The default `large-v3-turbo` Whisper model substantially improves multilingual recognition, while ASS/libass captions preserve Unicode/RTL shaping. Caption position, font, size, colors, highlighted words, line length, and pop/karaoke animation can be reviewed and changed on each generated clip.

> Importing a publicly accessible URL does **not** grant permission to republish it. Only process media you own, license, or have explicit authorization to repurpose.

## Prerequisites

- Python 3.13 (Python 3.12 is also supported; Python 3.14 is excluded for native ML compatibility)
- `uv`
- Node.js 22 LTS or newer and `pnpm`
- FFmpeg and ffprobe 7 or newer
- Ollama with a suitable instruction model, such as `qwen3:8b-q4_K_M`

## Development

### Docker Compose

The fully containerized CPU setup needs only Docker Desktop or Docker Engine with Compose:

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.ollama.yaml --profile setup run --rm model-init
docker compose --profile setup run --rm whisper-model-init
docker compose -f compose.yaml -f compose.ollama.yaml up --build -d
```

Open [http://localhost:3000](http://localhost:3000). The first command explicitly downloads the configured editorial model into a persistent Docker volume. Whisper downloads its configured model on the first transcription and caches it in a separate volume. Application projects and exports persist in `clipper-data`.

```bash
docker compose -f compose.yaml -f compose.ollama.yaml logs -f
docker compose -f compose.yaml -f compose.ollama.yaml down
```

On Apple Silicon, run Ollama natively to retain Metal acceleration, then use `docker compose up --build -d`; the API container reaches it through `host.docker.internal`. For an NVIDIA-backed Ollama container, append `-f compose.nvidia.yaml`. See [docs/docker.md](docs/docker.md) for volume backups, model changes, troubleshooting, and security notes.

### Native development

```bash
cp .env.example .env
uv sync --project apps/api --extra dev
pnpm install
pnpm dev
```

`pnpm dev` starts the API on port 8000 and web client on port 3000. Run `pnpm doctor` before processing media. Model downloads are explicit user actions; see [docs/models.md](docs/models.md).

```bash
pnpm check
pnpm test
```

The data directory contains the SQLite database, private source media, stage artifacts, and exports. Back it up to preserve completed work. See [docs/architecture.md](docs/architecture.md), [docs/module-ownership.md](docs/module-ownership.md), [docs/security.md](docs/security.md), and [docs/troubleshooting.md](docs/troubleshooting.md).

## Scope

This repository intentionally focuses on the local clipping workflow. Publishing remains an adapter boundary and has no browser automation. Phase-two Remotion templates, face tracking, VLM reranking, and publishing adapters are described in the architecture plan but are not claimed as complete.
