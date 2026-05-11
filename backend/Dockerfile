# =============================================================================
# T-S0-01: Backend Dockerfile (FastAPI)
# =============================================================================
# Multi-stage build:
#   1. base: Python 3.13 slim + system deps (psycopg, git for worktree manager)
#   2. deps: pip install requirements.txt
#   3. runtime: app コピー + non-root user
# =============================================================================

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        libpq-dev \
        gcc \
        bubblewrap \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app


FROM base AS deps

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt


FROM deps AS runtime

# non-root user で起動
RUN groupadd --system bf && useradd --system --create-home --gid bf bf

COPY --chown=bf:bf . /app

USER bf

EXPOSE 8001

# Healthcheck は docker-compose 側で定義
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
