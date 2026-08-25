FROM node:22.22.2-bookworm-slim@sha256:868499d55378719bffa87b0ed1f099591823c029b543043c09c2483468e93201 AS console-builder

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate
WORKDIR /build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/console/package.json frontend/console/package.json
COPY sdk/typescript/package.json sdk/typescript/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/console frontend/console
COPY sdk/typescript sdk/typescript
RUN pnpm --filter @scenara/console build

FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04@sha256:9175fa92f96de35a8cfb9493f0dfcf9435c7a597e9d95ad41d2cae382a95e3f9

ARG SCENARA_VERSION=0.3.0-dev.31
ARG SCENARA_SOURCE_COMMIT=unknown
LABEL org.opencontainers.image.title="Scenara" \
      org.opencontainers.image.version="${SCENARA_VERSION}" \
      org.opencontainers.image.revision="${SCENARA_SOURCE_COMMIT}" \
      org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv postgresql-client ffmpeg libglib2.0-0 libgl1 curl ca-certificates \
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
