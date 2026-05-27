FROM docker:24-cli AS docker

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Bring the Docker CLI + compose plugin in from the official alpine image
# rather than pulling Debian's older 'docker.io' (which lacks `docker compose`).
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/libexec/docker/cli-plugins/docker-compose \
                  /usr/libexec/docker/cli-plugins/docker-compose

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[runtime]"

COPY . .

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
