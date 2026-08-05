FROM node:22.22.2-bookworm-slim AS console-builder

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate
WORKDIR /build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/console/package.json frontend/console/package.json
COPY sdk/typescript/package.json sdk/typescript/package.json
COPY frontend/console frontend/console
COPY sdk/typescript sdk/typescript
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @scenara/console build

FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ffmpeg libglib2.0-0 libgl1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/scenara
COPY requirements/production.lock requirements/production.lock
RUN python3 -m pip install --break-system-packages --require-hashes -r requirements/production.lock

RUN useradd --create-home --uid 10001 scenara \
    && mkdir -p /var/lib/scenara \
    && chown -R scenara:scenara /opt/scenara /var/lib/scenara

COPY --chown=scenara:scenara . .
COPY --from=console-builder --chown=scenara:scenara /build/frontend/console/dist frontend/console/dist

USER scenara
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://localhost:8000/readyz || exit 1
CMD ["python3", "-m", "uvicorn", "scenara.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
