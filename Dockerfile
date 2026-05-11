# syntax=docker/dockerfile:1.6

# ----------------------------------------------------------------------------
# Stage 1: Frontend-Build (Vue 3 + Vite + Tailwind 4)
# ----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /work

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
# Build ohne strict type-check (vue-tsc wird im Build-Stage geskippt fuer Robustheit;
# tsc-Check passiert im Dev-Loop). Bei Bedarf: npm run build (mit type-check).
RUN npm run build:nocheck

RUN test -f dist/index.html || (echo "frontend build produced no dist/index.html" >&2 && exit 1)

# ----------------------------------------------------------------------------
# Stage 2: Python-Runtime (FastAPI + paramiko + cryptography)
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Tools: curl fuer healthcheck, openssh-client fuer optionale ssh-Diagnose,
# tini als PID 1, ca-certificates fuer https.
# Docker-CLI (statisch) damit der Container ueber den gemounteten /var/run/docker.sock
# `docker ps` auf dem Self-Host ausfuehren kann.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tini openssh-client gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install -e .

COPY config.example.yaml /app/config.example.yaml

# SPA aus Stage 1
COPY --from=frontend-build /work/dist /app/frontend_dist

EXPOSE 7843

ENV COCKPIT_CONFIG=/etc/cockpit/config.yaml \
    PYTHONPATH=/app/src \
    ADMIN_DB_PATH=/data/cockpit.db

HEALTHCHECK --interval=30s --timeout=4s --start-period=8s --retries=3 \
  CMD curl -fsS http://localhost:7843/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "cockpit.main:app", "--host", "0.0.0.0", "--port", "7843", "--workers", "1"]
