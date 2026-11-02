"""FastAPI application. Placeholder until P5: only the health endpoint exists."""

from fastapi import FastAPI

from reach_api import __version__

app = FastAPI(title="reach API", version=__version__)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness check used by the Compose healthcheck."""
    return {"status": "ok", "version": __version__}
