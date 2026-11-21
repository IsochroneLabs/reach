"""Read-only access to `current` and `meta` as role `app_read` (arch. §8, AGENTS.md rule 6).

Geometries are stored in EPSG:25832 and transformed to EPSG:4326 in SQL (`ST_Transform`) at this
boundary only. `Database` is the interface the routes use; tests replace it with a fake. Read
queries for the fit and the cell detail follow in S1.10.
"""

from __future__ import annotations

from typing import Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from reach_api.settings import DbPool

# Run schema that `current.cells` reads from (same lookup as reach_pipeline.db.current_schema),
# mapped back to its run id.
_RUN_ID = """
SELECT r.run_id FROM meta.runs r
WHERE 'run_' || lower(r.run_id) = (
    SELECT DISTINCT tn.nspname FROM pg_rewrite rw
    JOIN pg_class v ON v.oid = rw.ev_class
    JOIN pg_namespace vn ON vn.oid = v.relnamespace
    JOIN pg_depend d ON d.objid = rw.oid AND d.classid = 'pg_rewrite'::regclass
    JOIN pg_class t ON t.oid = d.refobjid AND t.oid <> v.oid
    JOIN pg_namespace tn ON tn.oid = t.relnamespace
    WHERE vn.nspname = 'current' AND v.relname = 'cells')
"""


class Database(Protocol):
    async def run_id(self) -> str | None: ...


class PostgresDatabase:
    """`Database` on an async psycopg pool."""

    def __init__(self, dsn: str, pool: DbPool) -> None:
        self.pool = AsyncConnectionPool(
            dsn,
            min_size=pool.min_size,
            max_size=pool.max_size,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )

    async def open(self) -> None:
        await self.pool.open()

    async def close(self) -> None:
        await self.pool.close()

    async def run_id(self) -> str | None:
        """Run id `current` points at, or None before the first publish."""
        async with self.pool.connection() as conn:
            cur = await conn.execute(_RUN_ID)
            row = await cur.fetchone()
        return row["run_id"] if row else None
