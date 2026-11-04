"""Data-contract test against a disposable PostGIS (marker `db`; CI job `db-contract`).

Needs `REACH_TEST_DATABASE_URL`: a superuser connection string to a PostGIS server, e.g.
`postgresql://postgres:<password>@localhost:5432/postgres`. Every test module run creates a
fresh database `reach_test_<random>` on that server, applies roles + migrations, publishes tiny
hand-made runs as `pipeline_write` and drops the database afterwards. Roles are cluster-wide:
existing roles are reused and their passwords are not changed.

Checks: column names and types of every table and view (docs/data_contract.md), `scores`,
`transit_scores` and `district_scores` against hand-computed values, role privileges, the
atomic switch of `current`, and dropping old runs.
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

from reach_pipeline import db, scoring
from reach_pipeline.config import Database, load_config
from reach_pipeline.stages import cleanup, publish

pytestmark = pytest.mark.db

REPO = Path(__file__).resolve().parents[2]
SQL_DIR = REPO / "infra" / "db"
DB_CFG = Database(sql_dir=SQL_DIR, connect_retries=0, backoff_s=0)
RUN_A, RUN_B, RUN_C, RUN_D = (f"2026010{d}T000000Z" for d in range(1, 5))

POLY, POINT, MULTI = (f"geometry({t},25832)" for t in ("Polygon", "Point", "MultiPolygon"))
DOUBLE = "double precision"
ACCESS_COLS = [
    ("cell_id", "text"),
    ("category", "text"),
    ("profile_id", "text"),
    ("count", "integer"),
    ("nearest_min", DOUBLE),
]
# docs/data_contract.md, "Schema run_<id> and views current.*" (recommendations follow in P7).
CONTRACT = {
    "cells": [
        ("cell_id", "text"),
        ("population", "integer"),
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
    "urban_boundary": [("part_id", "integer"), ("name", "text"), ("geom", MULTI)],
    "facilities": [
        ("facility_id", "text"),
        ("category", "text"),
        ("name", "text"),
        ("geom", POINT),
    ],
    "facility_points": [
        ("facility_id", "text"),
        ("point_id", "integer"),
        ("kind", "text"),
        ("geom", POINT),
    ],
    "stops": [
        ("stop_id", "text"),
        ("name", "text"),
        ("weekday_departures", "integer"),
        ("geom", POINT),
    ],
    "profiles": [
        ("profile_id", "text"),
        ("costing", "text"),
        ("costing_options", "jsonb"),
        ("speed_kmh", DOUBLE),
        ("time_budget_min", DOUBLE),
    ],
    "access_counts": ACCESS_COLS,
    "transit_supply": [
        ("cell_id", "text"),
        ("profile_id", "text"),
        ("departures", "integer"),
        ("stops_count", "integer"),
        ("nearest_stop_min", DOUBLE),
    ],
    "thresholds": [
        ("category", "text"),
        ("k", "integer"),
        ("class", "text"),
        ("lower", "integer"),
        ("upper", "integer"),
    ],
    "validation_report": [
        ("check", "text"),
        ("stage", "text"),
        ("status", "text"),
        ("value", DOUBLE),
        ("message", "text"),
    ],
    "scores": [*ACCESS_COLS, ("class", "text"), ("deficit", DOUBLE)],
    "transit_scores": [("cell_id", "text"), ("profile_id", "text"), ("class", "text")],
    "district_scores": [
        ("district_id", "text"),
        ("category", "text"),
        ("profile_id", "text"),
        ("share_lack", DOUBLE),
        ("share_insufficient", DOUBLE),
        ("share_sufficient", DOUBLE),
        ("deficit_sum", DOUBLE),
        ("residents_lack", "integer"),
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


def run_tables(grocery_a: int = 0) -> dict[str, pd.DataFrame]:
    """Tiny run: cells a–d (10/20/30/40 residents; d has no district), grocery k=2,
    pharmacy k=1, profiles walk (transit) and bike."""
    cfg = load_config(REPO / "config" / "config.yaml")
    cells = ["a", "b", "c", "d"]
    squares = [_square(500_000 + 100 * i, 5_400_000) for i in range(4)]
    counts = {
        ("walk", "grocery"): [grocery_a, 1, 2, 3],
        ("walk", "pharmacy"): [1, 0, 5, 0],
        ("bike", "grocery"): [2, 2, 2, 2],
        ("bike", "pharmacy"): [1, 1, 1, 1],
    }
    access = pd.DataFrame(
        [
            {
                "cell_id": cell,
                "category": cat,
                "profile_id": prof,
                "count": n,
                "nearest_min": None if n == 0 else 4.5,
            }
            for (prof, cat), values in counts.items()
            for cell, n in zip(cells, values, strict=True)
        ]
    )
    thr = scoring.thresholds(cfg)
    thr = thr[thr["category"].isin(["grocery", "pharmacy", "transit"])]
    district = shapely.MultiPolygon([_square(500_000, 5_400_000, 200)])
    point = shapely.Point(500_050, 5_400_050)
    return {
        "cells": pd.DataFrame(
            {
                "cell_id": cells,
                "population": [10, 20, 30, 40],
                "district_id": ["d1", "d1", "d2", None],
                "geom": _geo(squares),
                "origin_geom": _geo([s.centroid for s in squares]),
            }
        ),
        "districts": pd.DataFrame(
            {
                "district_id": ["d1", "d2"],
                "name": ["One", "Two"],
                "admin_level": [11, 11],
                "geom": _geo([district, district]),
            }
        ),
        "urban_boundary": pd.DataFrame({"part_id": [1], "name": [None], "geom": _geo([district])}),
        "facilities": pd.DataFrame(
            {
                "facility_id": ["n1"],
                "category": ["grocery"],
                "name": ["Shop"],
                "geom": _geo([point]),
            }
        ),
        "facility_points": pd.DataFrame(
            {"facility_id": ["n1"], "point_id": [0], "kind": ["node"], "geom": _geo([point])}
        ),
        "stops": pd.DataFrame(
            {
                "stop_id": ["s1"],
                "name": ["Stop"],
                "weekday_departures": [12],
                "geom": _geo([point]),
            }
        ),
        "profiles": pd.DataFrame(
            {
                "profile_id": ["walk", "bike"],
                "costing": ["pedestrian", "bicycle"],
                "costing_options": ['{"walking_speed": 3.39}', '{"cycling_speed": 15.0}'],
                "speed_kmh": [3.39, 15.0],
                "time_budget_min": [15.0, 15.0],
            }
        ),
        "access_counts": access,
        "transit_supply": pd.DataFrame(
            {
                "cell_id": cells,
                "profile_id": "walk",
                "departures": [0, 150, 1000, 1001],
                "stops_count": [0, 1, 3, 4],
                "nearest_stop_min": [None, 9.0, 2.0, 1.0],
            }
        ),
        "thresholds": thr,
        "validation_report": pd.DataFrame(
            {
                "check": ["crs", "monotonic_x"],
                "stage": ["validate", "validate_results"],
                "status": ["ok", "warn"],
                "value": [None, 0.003],
                "message": ["all layers EPSG:25832", "5 of 1699 cells"],
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


def test_scores_match_hand_computation(published: str) -> None:
    rows = _rows(
        published,
        "SELECT cell_id, category, class, deficit FROM current.scores "
        "WHERE profile_id = 'walk' ORDER BY category, cell_id",
    )
    assert rows == [
        # grocery, k = 2: counts 0, 1, 2, 3; residents 10, 20, 30, 40
        ("a", "grocery", "lack", 10.0),
        ("b", "grocery", "insufficient", 10.0),
        ("c", "grocery", "sufficient", 0.0),
        ("d", "grocery", "sufficient", 0.0),
        # pharmacy, k = 1: counts 1, 0, 5, 0
        ("a", "pharmacy", "sufficient", 0.0),
        ("b", "pharmacy", "lack", 20.0),
        ("c", "pharmacy", "sufficient", 0.0),
        ("d", "pharmacy", "lack", 40.0),
    ]


def test_scores_view_equals_python_rules(published: str) -> None:
    rows = _rows(published, "SELECT count, category, class, deficit FROM current.scores")
    frame = pd.DataFrame(rows, columns=["count", "category", "class", "deficit"])
    k = frame["category"].map({"grocery": 2, "pharmacy": 1}).to_numpy(dtype=float)
    assert list(scoring.classify(frame["count"].to_numpy(), k)) == list(frame["class"])


def test_transit_scores(published: str) -> None:
    rows = _rows(published, "SELECT cell_id, class FROM current.transit_scores ORDER BY cell_id")
    assert rows == [("a", "lack"), ("b", "insufficient"), ("c", "medium"), ("d", "high")]


def test_district_scores(published: str) -> None:
    rows = _rows(
        published,
        "SELECT district_id, share_lack, share_insufficient, share_sufficient, deficit_sum, "
        "residents_lack FROM current.district_scores "
        "WHERE category = 'grocery' AND profile_id = 'walk' ORDER BY district_id",
    )
    # d1 = cells a (10, lack) + b (20, insufficient); d2 = c (30, sufficient); d has no district
    assert rows == [
        ("d1", pytest.approx(1 / 3), pytest.approx(2 / 3), 0.0, 20.0, 10),
        ("d2", 0.0, 0.0, 1.0, 0.0, 0),
    ]


def test_meta_and_validation_report(published: str) -> None:
    (run,) = _rows(published, "SELECT run_id, status, finished_at IS NOT NULL FROM meta.runs")
    assert run == (RUN_A, "published", True)
    rows = _rows(published, 'SELECT stage, "check", status FROM current.validation_report')
    assert sorted(rows) == [("validate", "crs", "ok"), ("validate_results", "monotonic_x", "warn")]


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
    _publish(published, RUN_B, grocery_a=2)
    with _as(published, "app_read") as conn:
        assert db.current_schema(conn) == db.schema_name(RUN_B)
    rows = _rows(
        published,
        "SELECT class FROM current.scores WHERE cell_id = 'a' AND category = 'grocery' "
        "AND profile_id = 'walk'",
    )
    assert rows == [("sufficient",)]
    # every current view reads from the new run
    with _as(published, "supervisor_read") as conn:
        for rel in CONTRACT:
            assert (
                conn.execute(f"SELECT count(*) FROM current.{rel}").fetchone()
                == conn.execute(f"SELECT count(*) FROM {db.schema_name(RUN_B)}.{rel}").fetchone()
            )
    # re-publishing the current run replaces it in one transaction
    _publish(published, RUN_B, grocery_a=0)
    assert _rows(
        published,
        "SELECT class FROM current.scores WHERE cell_id = 'a' AND category = 'grocery' "
        "AND profile_id = 'walk'",
    ) == [("lack",)]


def test_failed_switch_leaves_current_untouched(
    published: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _rows(published, "SELECT count(*) FROM current.scores")
    with _as(published, "pipeline_write") as conn:
        current = db.current_schema(conn)
    real = db.relations
    # a relation that does not exist makes the switch fail after some views were replaced
    monkeypatch.setattr(db, "relations", lambda conn, schema: [*real(conn, schema), "zz_missing"])
    with pytest.raises(psycopg.errors.UndefinedTable):
        _publish(published, RUN_C, grocery_a=3)
    monkeypatch.undo()
    with _as(published, "app_read") as conn:
        assert db.current_schema(conn) == current
        status = conn.execute("SELECT status FROM meta.runs WHERE run_id = %s", [RUN_C])
        assert status.fetchone() == ("running",)
    assert _rows(published, "SELECT count(*) FROM current.scores") == before


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
