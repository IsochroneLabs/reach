"""FastAPI application (arch. §9): health, reference data, address search, fit and cell detail
(`routes.py`, S1.10). The live route for *Check* follows with F4.5.

`create_app(deps)` takes prepared dependencies (tests pass a fake database); without them the
lifespan builds them from the environment (`DATABASE_URL_API`, `VALHALLA_URL`, `REACH_CONFIG`,
`BUILD_SHA`). CORS admits only the frontend origins of `api.cors_origins` (D4).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from reach_api import __version__
from reach_api.db import PostgresDatabase
from reach_api.deps import Deps
from reach_api.routes import router
from reach_api.settings import Config, Env, label_names, load_config, personas
from reach_api.store import NotPublished
from reach_api.valhalla import NoRouteError, ValhallaClient, ValhallaError, ValhallaTimeout

log = logging.getLogger(__name__)
GET_HEAD = ["GET", "HEAD"]


def _require(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"environment variable {name} is not set (see .env.example)")
    return value


def create_app(deps: Deps | None = None) -> FastAPI:
    env = Env()
    config: Config = deps.config if deps is not None else load_config(env.reach_config)
    build_sha = deps.build_sha if deps is not None else env.build_sha

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if deps is not None:
            app.state.deps = deps
            yield
            return
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        dsn = _require("DATABASE_URL_API", env.database_url_api)
        valhalla_url = _require("VALHALLA_URL", env.valhalla_url)
        db = PostgresDatabase(dsn, config.api.db_pool)
        valhalla = ValhallaClient(valhalla_url, config.api.valhalla)
        await db.open()
        app.state.deps = Deps(
            config=config,
            db=db,
            valhalla=valhalla,
            build_sha=build_sha,
            label_names=label_names(env.reach_config),
            personas=personas(env.reach_config),
        )
        log.info("API ready: config %s, build %s", env.reach_config, build_sha)
        try:
            yield
        finally:
            await valhalla.aclose()
            await db.close()

    app = FastAPI(title="reach API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_methods=["GET", "HEAD", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.api_route("/api/health", methods=GET_HEAD)
    def health() -> dict[str, str]:
        """Liveness check (Compose healthcheck, smoke test); never touches the database."""
        return {"status": "ok", "version": __version__, "build_sha": build_sha}

    app.include_router(router)

    @app.exception_handler(NotPublished)
    async def _not_published(request: Request, exc: NotPublished) -> JSONResponse:
        return JSONResponse({"detail": "no data published yet"}, status_code=503)

    @app.exception_handler(NoRouteError)
    async def _no_route(request: Request, exc: NoRouteError) -> JSONResponse:
        return JSONResponse({"detail": f"no route from this point: {exc}"}, status_code=422)

    @app.exception_handler(ValhallaTimeout)
    async def _valhalla_timeout(request: Request, exc: ValhallaTimeout) -> JSONResponse:
        log.warning("%s", exc)
        return JSONResponse({"detail": "routing took too long, try again"}, status_code=504)

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
