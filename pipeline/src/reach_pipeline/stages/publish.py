"""publish: copy the run into PostGIS and switch the `current` views (arch. §7, §8).

1. If `DATABASE_URL_ADMIN` is set, `migrate` first (roles, meta schema; idempotent).
2. As `pipeline_write` (`DATABASE_URL_PIPELINE`): upsert `meta.runs` (status `running`).
3. One transaction: (re)create schema `run_<id>` from `infra/db/run_schema.sql`, COPY all
   tables, `meta.data_sources`, refresh `district_scores`.
4. One transaction: `CREATE OR REPLACE VIEW current.<name>` for every relation of the run
   schema, `meta.runs.status = 'published'`. Readers see the old or the new run, never a mix.
   Re-publishing the run `current` already points at does 3 and 4 in one transaction.

The only stage that writes to PostGIS besides `cleanup` (AGENTS.md rule 6, arch. §7).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import psycopg
import shapely

from reach_pipeline import db
from reach_pipeline.config import Config, pipeline_sections, section_digest
from reach_pipeline.context import RunContext
from reach_pipeline.errors import ConfigError, ExternalError, StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import (
    acquire,
    count,
    housing,
    recommend,
    score,
    validate,
    validate_results,
)
from reach_pipeline.valhalla.client import costing_options

STAGE = "publish"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): all pipeline sections, because `meta.runs.config_hash` records their
# digest (re-publishing takes ~1 s); `api` is not one of them.
CONFIG_SECTIONS = pipeline_sections()
PREVIOUS = validate_results.STAGE
URL_ENV, ADMIN_URL_ENV = "DATABASE_URL_PIPELINE", "DATABASE_URL_ADMIN"
DATA_SOURCES = "data_sources.parquet"
MULTI_LAYERS = ("districts", "urban_boundary")

log = logging.getLogger(__name__)


def _paths(ctx: RunContext) -> dict[str, Path]:
    v, c = ctx.stage_dir(validate.STAGE), ctx.stage_dir(count.STAGE)
    return {
        "cells": v / "cells.parquet",
        "districts": v / "districts.parquet",
        "urban_boundary": v / "urban_boundary.parquet",
        "facilities": v / "facilities.parquet",
        "facility_points": v / "facility_points.parquet",
        "stops": c / count.STOPS,
        "access_counts": c / count.ACCESS,
        "reachable": c / count.REACHABLE,
        "transit_supply": c / count.TRANSIT,
        "thresholds": ctx.stage_dir(score.STAGE) / score.THRESHOLDS,
        "housing_cells": ctx.stage_dir(housing.STAGE) / housing.CELLS,
        "housing_counts": ctx.stage_dir(housing.STAGE) / housing.COUNTS,
        "housing_reachable": ctx.stage_dir(housing.STAGE) / housing.REACHABLE,
        "recommendations": ctx.stage_dir(recommend.STAGE) / recommend.RECOMMENDATIONS,
        "recommendation_catchments": ctx.stage_dir(recommend.STAGE) / recommend.REC_CATCHMENTS,
        "report_inputs": v / validate.REPORT_JSON,
        "report_results": ctx.stage_dir(validate_results.STAGE) / validate_results.REPORT_JSON,
        "data_sources": ctx.stage_dir(acquire.STAGE) / DATA_SOURCES,
    }


def _multi(geoms: gpd.GeoSeries) -> gpd.GeoSeries:
    """Polygon → MultiPolygon (the contract types these columns as MultiPolygon)."""
    values = [
        shapely.MultiPolygon([g]) if isinstance(g, shapely.Polygon) else g for g in geoms.values
    ]
    return gpd.GeoSeries(values, index=geoms.index, crs=geoms.crs)


def _geo(path: Path, columns: list[str]) -> pd.DataFrame:
    """Columns of a GeoParquet layer with its geometry as hex EWKB in column `geom`."""
    layer = gpd.read_parquet(path)
    geoms = _multi(layer.geometry) if path.stem in MULTI_LAYERS else layer.geometry
    return pd.DataFrame(layer[columns]).assign(geom=db.ewkb(geoms))


def facilities_frame(path: Path) -> pd.DataFrame:
    """`facilities`: point (`geom`), informative `tags` (JSON) and the area outline (`area_geom`,
    hex EWKB, empty for points)."""
    layer = gpd.read_parquet(path)
    area = layer.set_geometry("area_geometry").geometry
    frame = _geo(path, ["facility_id", "category", "name", "tags"])
    # to_csv writes None as an empty field, which COPY reads as NULL
    return frame.assign(area_geom=db.ewkb(area))


def profiles_frame(cfg: Config) -> pd.DataFrame:
    """`profiles`: costing options exactly as sent to Valhalla (incl. the speed option)."""
    return pd.DataFrame(
        [
            {
                "profile_id": pid,
                "costing": p.costing,
                "costing_options": json.dumps(costing_options(p)[p.costing], sort_keys=True),
                "speed_kmh": p.speed_kmh,
                "time_budget_min": cfg.time_budgets_min.facilities,
            }
            for pid, p in cfg.profiles.items()
        ]
    )


def recommendations_frame(path: Path) -> pd.DataFrame:
    """`recommendations`: zone polygon (`geom`) and centre (`point_geom`) as hex EWKB."""
    layer = gpd.read_parquet(path)
    return pd.DataFrame(layer[recommend.REC_COLUMNS]).assign(
        geom=db.ewkb(layer.geometry),
        point_geom=db.ewkb(layer.set_geometry("point_geom").geometry),
    )


def housing_cells_frame(path: Path) -> pd.DataFrame:
    """`housing_cells`: cell polygon (`geom`) and centre (`origin_geom`) as hex EWKB."""
    layer = gpd.read_parquet(path)
    return pd.DataFrame(layer[["cell_id", "district_id"]]).assign(
        geom=db.ewkb(layer.geometry),
        origin_geom=db.ewkb(layer.set_geometry("origin_geom").geometry),
    )


def report_frame(*reports: dict[str, Any]) -> pd.DataFrame:
    """`validation_report` rows from report parts 1 and 2."""
    rows = [c for r in reports for c in r["checks"]]
    return pd.DataFrame(rows, columns=["check", "stage", "status", "value", "message"])


def tables(ctx: RunContext) -> dict[str, pd.DataFrame]:
    """All tables of the run schema, in load order (cells and profiles before their FKs)."""
    p = _paths(ctx)
    cells = gpd.read_parquet(p["cells"])
    part1 = json.loads(p["report_inputs"].read_text(encoding="utf-8"))
    part2 = json.loads(p["report_results"].read_text(encoding="utf-8"))
    return {
        "cells": pd.DataFrame(cells[["cell_id", "population", "district_id"]]).assign(
            geom=db.ewkb(cells.geometry),
            origin_geom=db.ewkb(cells.set_geometry("origin_geom").geometry),
        ),
        "districts": _geo(p["districts"], ["district_id", "name", "admin_level"]),
        "urban_boundary": _geo(p["urban_boundary"], ["part_id", "name"]),
        "facilities": facilities_frame(p["facilities"]),
        "facility_points": _geo(p["facility_points"], ["facility_id", "point_id", "kind"]),
        "stops": _geo(p["stops"], ["stop_id", "name", "weekday_departures"]),
        "profiles": profiles_frame(ctx.config),
        "access_counts": pd.read_parquet(p["access_counts"]),
        "reachable": pd.read_parquet(p["reachable"]),
        "transit_supply": pd.read_parquet(p["transit_supply"]),
        "thresholds": pd.read_parquet(p["thresholds"]),
        "housing_cells": housing_cells_frame(p["housing_cells"]),
        "housing_counts": pd.read_parquet(p["housing_counts"]),
        "housing_reachable": pd.read_parquet(p["housing_reachable"]),
        "recommendations": recommendations_frame(p["recommendations"]),
        "recommendation_catchments": pd.read_parquet(p["recommendation_catchments"]),
        "validation_report": report_frame(part1, part2),
    }


def run_row(ctx: RunContext) -> dict[str, Any]:
    """`meta.runs` values of this run (status is set by the SQL)."""
    p = _paths(ctx)
    s = json.loads(p["report_inputs"].read_text(encoding="utf-8"))["summary"]
    acquired = read_manifest(ctx.stage_dir(acquire.STAGE))
    started = acquired.started_at if acquired else datetime.now(UTC)
    return {
        "run_id": ctx.run_id,
        "started_at": started,
        "osm_snapshot": s.get("osm_snapshot"),
        "gtfs_valid_from": s.get("gtfs_valid_from"),
        "gtfs_valid_to": s.get("gtfs_valid_to"),
        "reference_weekday": s.get("reference_weekday"),
        # Digest of the pipeline sections (without `api`), the same one recorded as input.
        "config_hash": section_digest(ctx.config, CONFIG_SECTIONS),
    }


def upsert_run(conn: psycopg.Connection, row: dict[str, Any]) -> None:
    """Insert the run as `running`; a re-publish keeps the status of a published run."""
    with conn.transaction():
        conn.execute(
            "INSERT INTO meta.runs (run_id, started_at, status, osm_snapshot, gtfs_valid_from, "
            "gtfs_valid_to, reference_weekday, config_hash) VALUES (%(run_id)s, "
            "%(started_at)s, 'running', %(osm_snapshot)s, %(gtfs_valid_from)s, "
            "%(gtfs_valid_to)s, %(reference_weekday)s, %(config_hash)s) "
            "ON CONFLICT (run_id) DO UPDATE SET started_at = EXCLUDED.started_at, "
            "osm_snapshot = EXCLUDED.osm_snapshot, gtfs_valid_from = EXCLUDED.gtfs_valid_from, "
            "gtfs_valid_to = EXCLUDED.gtfs_valid_to, "
            "reference_weekday = EXCLUDED.reference_weekday, "
            "config_hash = EXCLUDED.config_hash, "
            "status = CASE WHEN meta.runs.status = 'published' THEN 'published' "
            "ELSE 'running' END",
            row,
        )


def load_sources(conn: psycopg.Connection, run_id: str, path: Path) -> int:
    """Replace this run's `meta.data_sources` rows (provenance from acquire)."""
    cols = ["run_id", "source", "url", "retrieved_at", "checksum", "licence"]
    frame = pd.read_parquet(path, columns=cols).assign(run_id=run_id)
    conn.execute("DELETE FROM meta.data_sources WHERE run_id = %s", [run_id])
    return db.copy_frame(conn, "data_sources", frame, schema="meta")


def publish(
    conn: psycopg.Connection,
    run_id: str,
    template: str,
    data: dict[str, pd.DataFrame],
    sources: Path | None = None,
) -> dict[str, int]:
    """Load the run schema, then switch `current` (one transaction if it is already current)."""
    schema = db.schema_name(run_id)
    replace_current = db.current_schema(conn) == schema

    def load() -> dict[str, int]:
        with conn.transaction():
            rows = db.load_run(conn, schema, template, data)
            if sources is not None:
                rows["meta.data_sources"] = load_sources(conn, run_id, sources)
        return rows

    if replace_current:
        log.info("%s is current: load and switch in one transaction", schema)
        with conn.transaction():
            rows = load()
            db.switch_current(conn, schema, run_id)
    else:
        rows = load()
        db.switch_current(conn, schema, run_id)
    return rows


def mark_failed(conn: psycopg.Connection, run_id: str) -> None:
    """Best effort; a run that is already published keeps its status."""
    try:
        conn.execute(
            "UPDATE meta.runs SET status = 'failed', finished_at = now() "
            "WHERE run_id = %s AND status <> 'published'",
            [run_id],
        )
    except psycopg.Error as exc:
        log.warning("could not mark run %s as failed: %s", run_id, exc)


def migrate_if_admin(cfg: Config) -> None:
    """Run `migrate` when the admin connection string is configured (local stack, server)."""
    if not os.environ.get(ADMIN_URL_ENV):
        log.info("%s not set: migrations are not checked", ADMIN_URL_ENV)
        return
    with db.connect(db.env_url(ADMIN_URL_ENV), cfg.database) as conn:
        applied = db.migrate(conn, cfg.database.sql_dir, db.role_passwords())
    log.info("migrate: %s", f"applied {applied}" if applied else "up to date")


def run(ctx: RunContext) -> Manifest:
    """Publish this run into PostGIS and make it `current`."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    cfg = ctx.config
    stage_dir = ctx.stage_dir(STAGE)
    sql_dir = cfg.database.sql_dir
    paths = _paths(ctx)
    sql_files = [sql_dir / db.ROLES_SQL, sql_dir / db.RUN_SCHEMA_SQL, *db.migrations(sql_dir)]
    inputs = [
        config_input(ctx.config, CONFIG_SECTIONS),
        *file_inputs([*paths.values(), *sql_files]),
    ]
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    url = db.env_url(URL_ENV)
    started_at = datetime.now(UTC)
    with measure() as m:
        migrate_if_admin(cfg)
        data = tables(ctx)
        template = (sql_dir / db.RUN_SCHEMA_SQL).read_text(encoding="utf-8")
        with db.connect(url, cfg.database) as conn:
            if not conn.execute("SELECT to_regclass('meta.runs')").fetchone()[0]:
                raise ConfigError(
                    "meta.runs does not exist: run `make migrate` (or set DATABASE_URL_ADMIN)"
                )
            upsert_run(conn, run_row(ctx))
            try:
                rows = publish(conn, ctx.run_id, template, data, paths["data_sources"])
            except psycopg.OperationalError as exc:
                mark_failed(conn, ctx.run_id)
                raise ExternalError(f"publish failed: {exc}") from exc
            except psycopg.Error as exc:
                mark_failed(conn, ctx.run_id)
                raise StageValidationError(f"publish failed: {exc}") from exc
            current = db.current_schema(conn)
    log.info("published %s, current → %s: %s", ctx.run_id, current, rows)

    stage_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=[
            FileOutput(path=f"postgis:{db.schema_name(ctx.run_id)}.{t}", rows=n)
            for t, n in rows.items()
        ],
        message=f"schema {db.schema_name(ctx.run_id)} published; current → {current}",
    )
    write_manifest(manifest, stage_dir)
    return manifest
