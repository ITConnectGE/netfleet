# syntax=docker/dockerfile:1.7

# ----- Base -----
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ----- Dependency layer -----
FROM base AS deps
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[runtime]"

# ----- Dev (with hot-reload tools) -----
FROM base AS dev
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[runtime,dev]"
COPY . .
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ----- Production -----
FROM deps AS prod
COPY . .
RUN chmod +x /app/docker-entrypoint.sh && \
    useradd --create-home --shell /bin/bash netfleet && \
    chown -R netfleet:netfleet /app
USER netfleet
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
