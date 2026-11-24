# API image (arch. §9): package reach-api with its locked dependencies, no dev dependencies.
# Build from the repository root: docker build -f infra/api.Dockerfile --build-arg BUILD_SHA=<sha> .
# Same uv/Python base as infra/pipeline.Dockerfile, amd64 + arm64.
FROM ghcr.io/astral-sh/uv:0.13.6-python3.12-trixie-slim

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH=/venv/bin:$PATH \
    REACH_CONFIG=config/config.yaml

WORKDIR /app

# Dependencies first, so source changes do not reinstall them. The workspace needs every
# member's pyproject.toml to resolve the lockfile; only reach-api is installed.
COPY pyproject.toml uv.lock .python-version ./
COPY api/pyproject.toml api/pyproject.toml
COPY pipeline/pyproject.toml pipeline/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reach-api --no-install-workspace

COPY api/src api/src
COPY config config
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package reach-api

RUN useradd --system --no-create-home reach
USER reach

# Commit SHA shown by /api/health (deploy.yml passes it; "dev" for local builds).
ARG BUILD_SHA=dev
ENV BUILD_SHA=$BUILD_SHA

EXPOSE 8000
# X-Forwarded-For is evaluated by the app (trusted proxies from config), not by uvicorn.
CMD ["uvicorn", "reach_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
