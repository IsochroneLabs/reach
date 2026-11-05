"""PostGIS access for `migrate`, `publish` and `cleanup` (arch. §8, docs/data_contract.md).

Plain psycopg on autocommit connections; every write happens inside an explicit
`conn.transaction()`. SQL lives in `infra/db/` (`database.sql_dir`): `roles.sql`, numbered
`migrations/NNNN_*.sql` and `run_schema.sql`, the template of one run schema.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg
import shapely
from psycopg import sql

from reach_pipeline.config import Database
from reach_pipeline.errors import ConfigError, ExternalError

ROLES_SQL, RUN_SCHEMA_SQL, MIGRATIONS_DIR = "roles.sql", "run_schema.sql", "migrations"
CURRENT = "current"
# Role → environment variable holding its password (.env.example).
ROLE_PASSWORDS = {
    "pipeline_write": "PIPELINE_WRITE_PASSWORD",
    "app_read": "APP_READ_PASSWORD",
    "supervisor_read": "SUPERVISOR_READ_PASSWORD",
}
SRID = 25832
_MIGRATION_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_RUN_SCHEMA_RE = re.compile(r"^run_(\d{8}t\d{6}z)$")

log = logging.getLogger(__name__)


def env_url(name: str) -> str:
    """Connection string from the environment (.env); fails clearly if it is missing."""
    url = os.environ.get(name, "").strip()
    if not url:
        raise ConfigError(f"environment variable {name} is not set (see .env.example)")
    return url


def connect(url: str, cfg: Database) -> psycopg.Connection:
    """Autocommit connection; retries with backoff, then ExternalError (exit code 3)."""
    for attempt in range(cfg.connect_retries + 1):
        try:
            return psycopg.connect(url, autocommit=True)
        except psycopg.OperationalError as exc:
            if attempt == cfg.connect_retries:
                raise ExternalError(f"cannot connect to the database: {exc}") from exc
            wait = cfg.backoff_s * 2**attempt
            log.warning("database not reachable (%s), retry in %.0f s", exc, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def schema_name(run_id: str) -> str:
    """`20261116T030000Z` → `run_20261116t030000z` (same as RunContext.db_schema)."""
    return f"run_{run_id.lower()}"


def run_id_of(schema: str) -> str | None:
    """Inverse of `schema_name`; None for other schemas."""
    m = _RUN_SCHEMA_RE.match(schema)
    return m.group(1).upper() if m else None


# --- migrate ---------------------------------------------------------------------------------


def migrations(sql_dir: Path) -> list[Path]:
    """Numbered migration files in order; fails on duplicate numbers or bad names."""
    files = sorted((sql_dir / MIGRATIONS_DIR).glob("*.sql"))
    bad = [f.name for f in files if not _MIGRATION_RE.match(f.name)]
    if bad:
        raise ConfigError(f"migration file names must be NNNN_name.sql: {bad}")
    numbers = [f.name[:4] for f in files]
    if len(set(numbers)) != len(numbers):
        raise ConfigError(f"duplicate migration numbers in {sql_dir / MIGRATIONS_DIR}")
    return files


def migrate(conn: psycopg.Connection, sql_dir: Path, passwords: dict[str, str]) -> list[str]:
    """Apply roles.sql, set the given role passwords, apply pending migrations (superuser).

    Idempotent: roles.sql runs every time; each migration runs once, in its own transaction,
    recorded in `meta.schema_migrations`. Returns the migrations applied now.
    """
    with conn.transaction():
        conn.execute((sql_dir / ROLES_SQL).read_text(encoding="utf-8"))
        for role, password in passwords.items():
            conn.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
        conn.execute(
            "CREATE SCHEMA IF NOT EXISTS meta; "
            "CREATE TABLE IF NOT EXISTS meta.schema_migrations ("
            "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
    done = {r[0] for r in conn.execute("SELECT version FROM meta.schema_migrations")}
    applied = []
    for path in migrations(sql_dir):
        version = path.stem
        if version in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO meta.schema_migrations (version) VALUES (%s)", [version])
        log.info("applied migration %s", version)
        applied.append(version)
    return applied


def role_passwords() -> dict[str, str]:
    """Passwords of the roles from the environment; roles without a variable are left as is."""
    return {role: os.environ[var] for role, var in ROLE_PASSWORDS.items() if os.environ.get(var)}


# --- publish ---------------------------------------------------------------------------------


def ewkb(geoms: gpd.GeoSeries) -> pd.Series:
    """Hex EWKB with SRID, the text form PostGIS accepts in COPY."""
    if geoms.crs is None or geoms.crs.to_epsg() != SRID:
        raise ValueError(f"geometries must be EPSG:{SRID}, got {geoms.crs}")
    values = shapely.to_wkb(shapely.set_srid(geoms.values, SRID), hex=True, include_srid=True)
    return pd.Series(values, index=geoms.index)


def copy_frame(
    conn: psycopg.Connection, table: str, frame: pd.DataFrame, schema: str | None = None
) -> int:
    """COPY a frame (columns = table columns, geometries as hex EWKB) into `[schema.]table`."""
    buf = io.StringIO()
    frame.to_csv(buf, index=False, header=False, na_rep="")
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in frame.columns)
    stmt = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT csv)").format(
        sql.Identifier(schema, table) if schema else sql.Identifier(table), cols
    )
    with conn.cursor() as cur, cur.copy(stmt) as copy:
        copy.write(buf.getvalue())
    return len(frame)


def relations(conn: psycopg.Connection, schema: str) -> list[str]:
    """Tables, views and materialized views of a schema, sorted by name."""
    rows = conn.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind IN ('r', 'v', 'm') ORDER BY c.relname",
        [schema],
    )
    return [r[0] for r in rows]


def current_schema(conn: psycopg.Connection) -> str | None:
    """Run schema the `current.cells` view reads from, or None before the first publish."""
    row = conn.execute(
        "SELECT DISTINCT tn.nspname FROM pg_rewrite r "
        "JOIN pg_class v ON v.oid = r.ev_class "
        "JOIN pg_namespace vn ON vn.oid = v.relnamespace "
        "JOIN pg_depend d ON d.objid = r.oid AND d.classid = 'pg_rewrite'::regclass "
        "JOIN pg_class t ON t.oid = d.refobjid AND t.oid <> v.oid "
        "JOIN pg_namespace tn ON tn.oid = t.relnamespace "
        "WHERE vn.nspname = %s AND v.relname = 'cells'",
        [CURRENT],
    ).fetchone()
    return row[0] if row else None


def load_run(
    conn: psycopg.Connection, schema: str, template: str, tables: dict[str, pd.DataFrame]
) -> dict[str, int]:
    """(Re)create `schema` from the template and COPY the tables, in one transaction."""
    rows = {}
    with conn.transaction():
        ident = sql.Identifier(schema)
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(ident))
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(ident))
        conn.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(ident))
        conn.execute(template)
        for table, frame in tables.items():
            rows[table] = copy_frame(conn, table, frame)
        conn.execute("REFRESH MATERIALIZED VIEW district_scores")
        for table in tables:
            conn.execute(sql.SQL("ANALYZE {}.{}").format(ident, sql.Identifier(table)))
    return rows


def switch_current(conn: psycopg.Connection, schema: str, run_id: str) -> list[str]:
    """Point every `current.<name>` view at `schema` and mark the run published, atomically."""
    names = relations(conn, schema)
    with conn.transaction():
        for name in names:
            conn.execute(
                sql.SQL("CREATE OR REPLACE VIEW {}.{} AS SELECT * FROM {}.{}").format(
                    sql.Identifier(CURRENT),
                    sql.Identifier(name),
                    sql.Identifier(schema),
                    sql.Identifier(name),
                )
            )
        conn.execute(
            "UPDATE meta.runs SET status = 'published', finished_at = now() WHERE run_id = %s",
            [run_id],
        )
    return names


# --- cleanup ---------------------------------------------------------------------------------


def published_runs(conn: psycopg.Connection) -> list[str]:
    """Run ids with status `published`, newest first."""
    rows = conn.execute(
        "SELECT run_id FROM meta.runs WHERE status = 'published' ORDER BY run_id DESC"
    )
    return [r[0] for r in rows]


def run_schemas(conn: psycopg.Connection) -> list[str]:
    """Existing `run_<id>` schemas, sorted."""
    rows = conn.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'run\\_%' ORDER BY 1")
    return [r[0] for r in rows if run_id_of(r[0])]


def drop_run(conn: psycopg.Connection, run_id: str) -> None:
    """Drop a run schema and its meta rows (data_sources cascade), in one transaction."""
    with conn.transaction():
        conn.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name(run_id)))
        )
        conn.execute("DELETE FROM meta.runs WHERE run_id = %s", [run_id])
