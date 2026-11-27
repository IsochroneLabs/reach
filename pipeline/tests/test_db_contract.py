"""Data-contract test against a disposable PostGIS (marker `db`; CI job `db-contract`).

Needs `REACH_TEST_DATABASE_URL`: a superuser connection string to a PostGIS server, e.g.
`postgresql://postgres:<password>@localhost:5432/postgres`. Every test module run creates a
fresh database `reach_test_<random>` on that server, applies roles + migrations, publishes tiny
hand-made runs as `pipeline_write` and drops the database afterwards. Roles are cluster-wide:
existing roles are reused and their passwords are not changed.

Checks: column names and types of every table and view (docs/data_contract.md), role
privileges, the atomic switch of `current`, and dropping old runs.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg
import pytest
import shapely
from psycopg import sql

from reach_pipeline import db
from reach_pipeline.config import Database
from reach_pipeline.stages import cleanup, publish

pytestmark = pytest.mark.db

REPO = Path(__file__).resolve().parents[2]
SQL_DIR = REPO / "infra" / "db"
DB_CFG = Database(sql_dir=SQL_DIR, connect_retries=0, backoff_s=0)
RUN_A, RUN_B, RUN_C, RUN_D = (f"2026010{d}T000000Z" for d in range(1, 5))

POLY, POINT, MULTI = (f"geometry({t},25832)" for t in ("Polygon", "Point", "MultiPolygon"))
# docs/data_contract.md, "Schema run_<id> and views current.*" (v1.1.0, S1.4).
CONTRACT = {
    "cells": [
        ("cell_id", "text"),
        ("population", "integer"),
        ("populated", "boolean"),
        ("district_id", "text"),
        ("geom", POLY),
        ("origin_geom", POINT),
    ],
    "districts": [
        ("district_id", "text"),
        ("name", "text"),
        ("admin_level", "smallint"),
        ("geom", MULTI),
    ],
    "destination_types": [
        ("destination_type", "text"),
        ("label_en", "text"),
        ("label_de", "text"),
        ("source", "text"),
        ("trip_window", "text"),
        ("fine_time_min", "real"),
        ("trips_per_week", "real"),
        ("nearest_k", "smallint"),
    ],
    "destinations": [
        ("destination_id", "text"),
        ("destination_type", "text"),
        ("name", "text"),
        ("osm_id", "text"),
        ("geom", POINT),
    ],
    "destination_labels": [
        ("destination_id", "text"),
        ("destination_type", "text"),
        ("label_kind", "text"),
        ("label", "text"),
        ("name", "text"),
        ("n_features", "integer"),
        ("osm_ids", "text"),
        ("offered", "boolean"),
        ("geom", POINT),
    ],
    "campus_sites": [
        ("site_id", "text"),
        ("name", "text"),
        ("default_share", "real"),
        ("geom", POINT),
    ],
    "programmes": [
        ("programme", "text"),
        ("label_en", "text"),
        ("label_de", "text"),
        ("sites", "text[]"),
    ],
    "addresses": [
        ("address_id", "integer"),
        ("label", "text"),
        ("street", "text"),
        ("housenumber", "text"),
        ("postcode", "text"),
        ("city", "text"),
        ("residential", "boolean"),
        ("cell_id", "text"),
        ("geom", POINT),
    ],
    "stops": [("stop_id", "text"), ("name", "text"), ("geom", POINT)],
    "trip_windows": [
        ("trip_window", "text"),
        ("weekday", "text"),
        ("time", "text"),
        ("kind", "text"),
        ("direction", "text"),
        ("reference_date", "date"),
    ],
    "stop_departures": [("stop_id", "text"), ("trip_window", "text"), ("departures", "integer")],
    "travel_times": [
        ("cell_id", "text"),
        ("destination_id", "text"),
        ("mode", "text"),
        ("trip_window", "text"),
        ("time_s", "integer"),
        ("access_s", "integer"),
        ("wait_s", "integer"),
        ("in_vehicle_s", "integer"),
        ("egress_s", "integer"),
        ("transfers", "smallint"),
        ("first_stop", "text"),
        ("first_route", "text"),
        ("departure", "text"),
        ("walk_only", "boolean"),
    ],
    "validation_report": [
        ("check", "text"),
        ("stage", "text"),
        ("status", "text"),
        ("value", "double precision"),
        ("message", "text"),
    ],
}
META = {
    "runs": [
        ("run_id", "text"),
        ("started_at", "timestamp with time zone"),
        ("finished_at", "timestamp with time zone"),
        ("status", "text"),
        ("osm_snapshot", "timestamp with time zone"),
        ("gtfs_valid_from", "date"),
        ("gtfs_valid_to", "date"),
        ("reference_weekday", "date"),
        ("config_hash", "text"),
    ],
    "data_sources": [
        ("run_id", "text"),
        ("source", "text"),
        ("url", "text"),
        ("retrieved_at", "timestamp with time zone"),
        ("checksum", "text"),
        ("licence", "text"),
    ],
}


# --- fixtures --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_url() -> Iterator[str]:
    admin = os.environ.get("REACH_TEST_DATABASE_URL")
    if not admin:
        pytest.fail("set REACH_TEST_DATABASE_URL to a superuser URL of a disposable PostGIS")
    name = f"reach_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(admin, dbname=name)
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            assert db.migrate(conn, SQL_DIR, {}) == ["0001_meta"]
            assert db.migrate(conn, SQL_DIR, {}) == []  # idempotent
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


def _as(url: str, role: str) -> psycopg.Connection:
    """Superuser connection that acts as `role` (privileges and ownership of that role)."""
    conn = psycopg.connect(url, autocommit=True)
    conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    return conn


def _square(x: float, y: float, size: float = 100) -> shapely.Polygon:
    return shapely.box(x, y, x + size, y + size)


def _geo(values: list) -> pd.Series:
    return db.ewkb(gpd.GeoSeries(values, crs="EPSG:25832"))


def run_tables(population_a: int = 10) -> dict[str, pd.DataFrame]:
    """Tiny run: cells a–d (d has no district), two districts, one stop, two checks."""
    squares = [_square(500_000 + 100 * i, 5_400_000) for i in range(4)]
    return {
        "cells": pd.DataFrame(
            {
                "cell_id": ["a", "b", "c", "d"],
                "population": [population_a, 20, 30, 40],
                "populated": [population_a > 0, True, True, True],
                "district_id": ["r1", "r1", "r2", None],
                "geom": _geo(squares),
                "origin_geom": _geo([s.centroid for s in squares]),
            }
        ),
        "districts": pd.DataFrame(
            {
                "district_id": ["r1", "r2"],
                "name": ["West", "East"],
                "admin_level": [11, 9],
                "geom": _geo(
                    [
                        shapely.MultiPolygon([_square(500_000, 5_400_000, 200)]),
                        shapely.MultiPolygon([_square(500_200, 5_400_000, 200)]),
                    ]
                ),
            }
        ),
        "destination_types": pd.DataFrame(
            {
                "destination_type": ["grocery"],
                "label_en": ["Supermarket"],
                "label_de": ["Supermarkt"],
                "source": ["osm"],
                "trip_window": ["evening"],
                "fine_time_min": [10.0],
                "trips_per_week": [2.0],
                "nearest_k": [3],
            }
        ),
        "destinations": pd.DataFrame(
            {
                "destination_id": ["grocery:n1"],
                "destination_type": ["grocery"],
                "name": ["Markt"],
                "osm_id": ["n1"],
                "geom": _geo([shapely.Point(500_150, 5_400_050)]),
            }
        ),
        "campus_sites": pd.DataFrame(
            {
                "site_id": ["tal"],
                "name": ["Tal"],
                "default_share": [0.5],
                "geom": _geo([shapely.Point(500_250, 5_400_050)]),
            }
        ),
        "programmes": pd.DataFrame(
            {"programme": ["law"], "label_en": ["Law"], "label_de": ["Jura"], "sites": ["{tal}"]}
        ),
        "addresses": pd.DataFrame(
            {
                "address_id": [1],
                "label": ["Wilhelmstraße 5, 72074 Tübingen"],
                "street": ["Wilhelmstraße"],
                "housenumber": ["5"],
                "postcode": ["72074"],
                "city": ["Tübingen"],
                "residential": [True],
                "cell_id": ["a"],
                "geom": _geo([shapely.Point(500_050, 5_400_050)]),
            }
        ),
        "stops": pd.DataFrame(
            {
                "stop_id": ["s1"],
                "name": ["Hauptbahnhof"],
                "geom": _geo([shapely.Point(500_050, 5_400_050)]),
            }
        ),
        "trip_windows": pd.DataFrame(
            {
                "trip_window": ["evening"],
                "weekday": ["tuesday"],
                "time": ["18:00"],
                "kind": ["depart_at"],
                "direction": ["to"],
                "reference_date": ["2026-01-06"],
            }
        ),
        "stop_departures": pd.DataFrame(
            {"stop_id": ["s1"], "trip_window": ["evening"], "departures": [12]}
        ),
        "travel_times": pd.DataFrame(
            {
                "cell_id": ["a", "a"],
                "destination_id": ["grocery:n1", "grocery:n1"],
                "mode": ["walk", "transit"],
                "trip_window": ["evening", "evening"],
                "time_s": [120, 300],
                "access_s": [None, 60],
                "wait_s": [None, 60],
                "in_vehicle_s": [None, 120],
                "egress_s": [None, 60],
                "transfers": [None, 0],
                "first_stop": [None, "Hauptbahnhof"],
                "first_route": [None, "5"],
                "departure": [None, "18:02"],
                "walk_only": [False, False],
            }
        )
        .astype({c: "Int32" for c in ("access_s", "wait_s", "in_vehicle_s", "egress_s")})
        .astype({"transfers": "Int16"}),
        "destination_labels": pd.DataFrame(
            {
                "destination_id": ["grocery:edeka:n1"],
                "destination_type": ["grocery"],
                "label_kind": ["brand"],
                "label": ["edeka"],
                "name": ["Markt"],
                "n_features": [1],
                "osm_ids": ["n1"],
                "offered": [True],
                "geom": _geo([shapely.Point(500_150, 5_400_050)]),
            }
        ),
        "validation_report": pd.DataFrame(
            {
                "check": ["crs", "population_total"],
                "stage": ["validate", "validate"],
                "status": ["ok", "warn"],
                "value": [None, 0.003],
                "message": ["all layers EPSG:25832", "no official total configured"],
            }
        ),
    }


def _publish(url: str, run_id: str, **kwargs: int) -> None:
    template = (SQL_DIR / db.RUN_SCHEMA_SQL).read_text(encoding="utf-8")
    with _as(url, "pipeline_write") as conn:
        publish.upsert_run(
            conn,
            {
                "run_id": run_id,
                "started_at": "2026-01-01T00:00:00Z",
                "osm_snapshot": "2025-12-31T21:00:00Z",
                "gtfs_valid_from": "2025-12-01",
                "gtfs_valid_to": "2026-06-01",
                "reference_weekday": "2026-01-06",
                "config_hash": "abc",
            },
        )
        publish.publish(conn, run_id, template, run_tables(**kwargs))


@pytest.fixture(scope="module")
def published(db_url: str) -> str:
    _publish(db_url, RUN_A)
    return db_url


def _rows(url: str, query: str, role: str = "app_read") -> list[tuple]:
    with _as(url, role) as conn:
        return conn.execute(query).fetchall()


# --- tests -----------------------------------------------------------------------------------


def _columns(conn: psycopg.Connection, schema: str, rel: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
        "JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped "
        "ORDER BY a.attnum",
        [schema, rel],
    )
    return [(name, typ.replace(", ", ",")) for name, typ in rows]


def test_schema_matches_contract(published: str) -> None:
    with _as(published, "supervisor_read") as conn:
        run_schema = db.schema_name(RUN_A)
        assert set(db.relations(conn, run_schema)) == set(CONTRACT)
        assert set(db.relations(conn, db.CURRENT)) == set(CONTRACT)
        for rel, cols in CONTRACT.items():
            assert _columns(conn, run_schema, rel) == cols, rel
            assert _columns(conn, db.CURRENT, rel) == cols, f"current.{rel}"
        for rel, cols in META.items():
            assert _columns(conn, "meta", rel) == cols, f"meta.{rel}"


def test_meta_and_validation_report(published: str) -> None:
    (run,) = _rows(published, "SELECT run_id, status, finished_at IS NOT NULL FROM meta.runs")
    assert run == (RUN_A, "published", True)
    rows = _rows(published, 'SELECT stage, "check", status FROM current.validation_report')
    assert sorted(rows) == [("validate", "crs", "ok"), ("validate", "population_total", "warn")]


def test_privileges(published: str) -> None:
    run_cells = f"SELECT count(*) FROM {db.schema_name(RUN_A)}.cells"
    assert _rows(published, "SELECT count(*) FROM current.cells") == [(4,)]
    assert _rows(published, run_cells, role="supervisor_read") == [(4,)]
    for role, stmt in [
        ("app_read", run_cells),  # the API reads current only
        ("app_read", "CREATE SCHEMA x"),
        (
            "app_read",
            "INSERT INTO meta.runs (run_id, started_at, status, config_hash) "
            "VALUES ('20260101T000000Z', now(), 'running', 'x')",
        ),
        ("supervisor_read", "DELETE FROM meta.runs"),
        ("supervisor_read", f"DROP TABLE {db.schema_name(RUN_A)}.cells"),
        ("pipeline_write", "CREATE TABLE public.x (i int)"),
    ]:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), _as(published, role) as conn:
            conn.execute(stmt)


def test_republish_switches_current(published: str) -> None:
    _publish(published, RUN_B, population_a=11)
    with _as(published, "app_read") as conn:
        assert db.current_schema(conn) == db.schema_name(RUN_B)
    query = "SELECT population FROM current.cells WHERE cell_id = 'a'"
    assert _rows(published, query) == [(11,)]
    # every current view reads from the new run
    with _as(published, "supervisor_read") as conn:
        for rel in CONTRACT:
            assert (
                conn.execute(f"SELECT count(*) FROM current.{rel}").fetchone()
                == conn.execute(f"SELECT count(*) FROM {db.schema_name(RUN_B)}.{rel}").fetchone()
            )
    # re-publishing the current run replaces it in one transaction
    _publish(published, RUN_B, population_a=12)
    assert _rows(published, query) == [(12,)]


def test_switch_drops_views_the_run_does_not_have(published: str) -> None:
    # e.g. switching back to a run published before a table existed
    with _as(published, "pipeline_write") as conn:
        schema = db.current_schema(conn)
        conn.execute(f"CREATE VIEW current.zz_old AS SELECT * FROM {schema}.cells")
        db.switch_current(conn, schema, db.run_id_of(schema))
        assert "zz_old" not in db.relations(conn, db.CURRENT)
        assert set(db.relations(conn, db.CURRENT)) == set(db.relations(conn, schema))


def test_failed_switch_leaves_current_untouched(
    published: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _rows(published, "SELECT sum(population) FROM current.cells")
    with _as(published, "pipeline_write") as conn:
        current = db.current_schema(conn)
    real = db.relations
    # a relation that does not exist makes the switch fail after some views were replaced
    monkeypatch.setattr(db, "relations", lambda conn, schema: [*real(conn, schema), "zz_missing"])
    with pytest.raises(psycopg.errors.UndefinedTable):
        _publish(published, RUN_C, population_a=13)
    monkeypatch.undo()
    with _as(published, "app_read") as conn:
        assert db.current_schema(conn) == current
        status = conn.execute("SELECT status FROM meta.runs WHERE run_id = %s", [RUN_C])
        assert status.fetchone() == ("running",)
    assert _rows(published, "SELECT sum(population) FROM current.cells") == before


def test_cleanup_drops_old_runs(published: str) -> None:
    _publish(published, RUN_C)
    _publish(published, RUN_D)
    with _as(published, "pipeline_write") as conn:
        published_runs = db.published_runs(conn)
        assert published_runs == [RUN_D, RUN_C, RUN_B, RUN_A]
        current = db.run_id_of(db.current_schema(conn))
        plan = cleanup.plan(published_runs, set(published_runs), set(), 3, {current})
        assert plan.drop_db == [RUN_A]
        for run_id in plan.drop_db:
            db.drop_run(conn, run_id)
        assert [db.run_id_of(s) for s in db.run_schemas(conn)] == [RUN_B, RUN_C, RUN_D]
        assert db.published_runs(conn) == [RUN_D, RUN_C, RUN_B]
        assert db.current_schema(conn) == db.schema_name(RUN_D)
