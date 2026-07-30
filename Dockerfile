FROM node:22.22.2-bookworm-slim AS console-builder

RUN corepack enable && corepack prepare pnpm@10.32.1 --activate
WORKDIR /build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/console/package.json frontend/console/package.json
COPY sdk/typescript/package.json sdk/typescript/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/console frontend/console
COPY sdk/typescript sdk/typescript
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

COPY . .
COPY --from=console-builder /build/frontend/console/dist frontend/console/dist
RUN useradd --create-home --uid 10001 scenara \
    && mkdir -p /var/lib/scenara \
    && chown -R scenara:scenara /opt/scenara /var/lib/scenara

USER scenara
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "scenara.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
