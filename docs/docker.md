# Docker Compose

## Stack layout

`compose.yaml` runs the FastAPI control plane and Next.js review client. It connects the API to an Ollama instance on the host by default, which is the preferred arrangement on Apple Silicon because Docker Desktop cannot pass Metal through to a Linux container.

`compose.ollama.yaml` adds a pinned Ollama container and switches the API to the Compose service address. This is the easiest fully containerized CPU setup. `compose.nvidia.yaml` grants that Ollama service all configured NVIDIA GPUs. The transcription image is currently CPU-oriented; do not assume that adding the NVIDIA override also enables CUDA faster-whisper.

## Fully containerized startup

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.ollama.yaml --profile setup run --rm model-init
docker compose -f compose.yaml -f compose.ollama.yaml up --build -d
docker compose -f compose.yaml -f compose.ollama.yaml ps
```

The setup job is deliberately separate: model weights are large, and starting the UI must never silently trigger a network download. Change `CLIPPER_EDITORIAL_MODEL` in `.env`, rerun the setup command, and recreate the API to switch models.

To use NVIDIA for Ollama:

```bash
docker compose -f compose.yaml -f compose.ollama.yaml -f compose.nvidia.yaml up --build -d
```

This requires a working NVIDIA Container Toolkit installation on the host.

## Apple Silicon with native Ollama

Install and start Ollama on macOS, pull the configured model, then containerize only the application:

```bash
ollama pull qwen3:8b-q4_K_M
docker compose up --build -d
```

The API uses `http://host.docker.internal:11434`. Override `CLIPPER_DOCKER_EDITORIAL_BASE_URL` in `.env` for another trusted endpoint. The separate variable prevents Docker-specific addressing from changing native development.

Large media uploads go directly from the browser to the FastAPI port instead of passing through Next.js, whose rewrite proxy buffers request bodies and defaults to 10 MB. If you change `CLIPPER_API_PORT`, also update `CLIPPER_BROWSER_API_URL` and rebuild the web image.

## Storage and backups

- `clipper-data`: SQLite database, uploaded source media, stage artifacts, previews, and exports.
- `whisper-models`: faster-whisper/Hugging Face cache.
- `ollama-models`: Ollama weights when the Ollama override is enabled.

`docker compose down` preserves named volumes. Do not add `--volumes` unless you intentionally want to remove all local projects and downloaded models. Back up application data without copying a live SQLite database:

```bash
docker compose stop api
docker run --rm -v clipper_clipper-data:/source:ro -v "$PWD/backups:/backup" alpine:3.22 tar -czf /backup/clipper-data.tgz -C /source .
docker compose start api
```

Treat backups as sensitive media. Store them encrypted and restrict filesystem permissions.

## Operations

```bash
docker compose -f compose.yaml -f compose.ollama.yaml logs -f api web ollama
docker compose exec api ffmpeg -version
docker compose exec api python -c "from clipper.services.hardware import detect_profile; print(detect_profile().to_dict())"
docker compose -f compose.yaml -f compose.ollama.yaml exec ollama ollama list
```

The API and web containers run as unprivileged users, use health checks, and enable `no-new-privileges`. The web filesystem is read-only. The API writes only to its data/model volumes and a bounded temporary filesystem. Ports bind to the host for a single-user workstation; do not expose them to an untrusted network without authentication and TLS.

## Rebuilds and upgrades

The Dockerfiles use exact Python, Node.js, uv, pnpm, and Ollama versions. Application packages remain locked by `uv.lock` and `pnpm-lock.yaml`. Review upstream release notes and vulnerability scans before changing base-image tags, then run:

```bash
docker compose build --pull --no-cache
docker compose config --quiet
```

If the web container stays unhealthy, inspect `docker compose logs web`. If analysis fails with a missing Ollama model, rerun the explicit model setup job. If transcription is killed for memory pressure, set `CLIPPER_WHISPER_MODEL=small`, keep one job at a time, and increase Docker Desktop's memory allocation.
