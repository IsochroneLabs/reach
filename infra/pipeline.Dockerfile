# Pipeline image (arch. §7): package reach-pipeline with its locked dependencies and osmium-tool,
# no dev dependencies. Build from the repository root:
#   docker build -f infra/pipeline.Dockerfile --build-arg BUILD_SHA=<sha> .
# Run: docker compose --profile pipeline run --rm pipeline <stage> (config/ and data/ are
# mounted by compose.yaml). Same uv/Python base as infra/api.Dockerfile, amd64 + arm64.
FROM ghcr.io/astral-sh/uv:0.13.6-python3.12-trixie-slim

# osmium filters and clips the OSM extract (reach_pipeline.osm); version from Debian trixie.
RUN apt-get update \
    && apt-get install -y --no-install-recommends osmium-tool \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH=/venv/bin:$PATH \
    REACH_CONFIG=config/config.yaml

WORKDIR /app

# Dependencies first, so source changes do not reinstall them; only reach-pipeline is installed.
COPY pyproject.toml uv.lock .python-version ./
COPY api/pyproject.toml api/pyproject.toml
COPY pipeline/pyproject.toml pipeline/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reach-pipeline --no-install-workspace

COPY pipeline/src pipeline/src
COPY config config
COPY infra/db infra/db
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reach-pipeline

RUN useradd --system --create-home reach && mkdir -p /app/data && chown reach /app/data
USER reach

ARG BUILD_SHA=dev
ENV BUILD_SHA=$BUILD_SHA

ENTRYPOINT ["python", "-m", "reach_pipeline"]
CMD ["run"]
