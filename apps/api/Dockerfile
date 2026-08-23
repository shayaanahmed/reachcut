FROM python:3.13.15-slim-trixie AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.5
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13.15-slim-trixie AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates ffmpeg fonts-noto-core \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 clipper \
    && useradd --uid 10001 --gid clipper --no-create-home --shell /usr/sbin/nologin clipper \
    && install --directory --owner=clipper --group=clipper /app /data /models/huggingface

WORKDIR /app
COPY --from=build --chown=clipper:clipper /app/.venv ./.venv
COPY --from=build --chown=clipper:clipper /app/src ./src

USER 10001:10001
EXPOSE 8000
VOLUME ["/data", "/models/huggingface"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

CMD ["uvicorn", "clipper.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
