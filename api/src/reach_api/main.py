"""FastAPI application (arch. §9): read endpoints from `current`, live endpoints via Valhalla.

`create_app(deps)` takes prepared dependencies (tests pass a fake database); without them the
lifespan builds them from the environment (`DATABASE_URL_API`, `VALHALLA_URL`, `REACH_CONFIG`).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from reach_api import __version__
from reach_api.db import PostgresDatabase
from reach_api.deps import Deps
from reach_api.routes import live, read
from reach_api.settings import Env, load_config
from reach_api.valhalla import NoRouteError, ValhallaClient, ValhallaError

log = logging.getLogger(__name__)


def create_app(deps: Deps | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if deps is not None:
            app.state.deps = deps
            yield
            return
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        env = Env()
        config = load_config(env.reach_config)
        db = PostgresDatabase(env.database_url_api, config.api.db_pool)
        valhalla = ValhallaClient(
            env.valhalla_url, config.api.valhalla, config.valhalla.max_matrix_pairs
        )
        await db.open()
        app.state.deps = Deps(config=config, db=db, valhalla=valhalla)
        log.info("API ready: config %s, Valhalla %s", env.reach_config, env.valhalla_url)
        try:
            yield
        finally:
            await valhalla.aclose()
            await db.close()

    app = FastAPI(title="reach API", version=__version__, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """Liveness check used by the Compose healthcheck."""
        return {"status": "ok", "version": __version__}

    app.include_router(read.router)
    app.include_router(live.router)

    @app.exception_handler(NoRouteError)
    async def _no_route(request: Request, exc: NoRouteError) -> JSONResponse:
        return JSONResponse({"detail": f"no route from this point: {exc}"}, status_code=422)

    @app.exception_handler(ValhallaError)
    async def _valhalla_down(request: Request, exc: ValhallaError) -> JSONResponse:
        log.error("%s", exc)
        return JSONResponse({"detail": "routing service unavailable"}, status_code=502)

    @app.exception_handler(psycopg.OperationalError)
    @app.exception_handler(PoolTimeout)
    async def _db_down(request: Request, exc: Exception) -> JSONResponse:
        log.error("database unavailable: %s", exc)
        return JSONResponse({"detail": "database unavailable"}, status_code=503)

    return app


app = create_app()
