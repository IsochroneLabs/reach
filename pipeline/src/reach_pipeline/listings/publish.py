"""publish_listings: load the latest listing snapshot into `lst_<id>` and point the views
`listings.*` at it in one transaction; keep the last `listings.keep_snapshots` schemas (O24).

With `publish` the only writer to PostGIS (AGENTS.md rule 6). Usage:
`uv run python -m reach_pipeline.listings.publish` with DATABASE_URL_PIPELINE set.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg
from psycopg import sql

from reach_pipeline import db
from reach_pipeline.config import Config, load_config
from reach_pipeline.errors import StageValidationError
from reach_pipeline.listings.crawl import SNAPSHOTS

log = logging.getLogger(__name__)

SCHEMA = "listings"
TEMPLATE = "listings_schema.sql"
_SNAPSHOT_RE = re.compile(r"^lst_(\d{8}t\d{6}z)$")
COLUMNS = [
    "listing_id", "source", "source_url", "kind", "title", "rent_total_eur", "rent_cold_eur",
    "utilities_eur", "other_costs_eur", "deposit_eur", "transfer_fee_eur", "size_m2",
    "flat_size_m2", "rooms", "household_size", "flatmates_women", "flatmates_men",
    "flatmates_diverse", "flatmates_age_min", "flatmates_age_max", "looking_for_gender",
    "looking_for_age_min", "looking_for_age_max", "wg_types", "languages", "smoking",
    "available_from", "available_to", "furnished", "features", "district", "postcode",
    "address_text", "geocode_precision", "cell_id", "geom", "image_urls", "description_excerpt",
    "online_since", "first_seen", "last_seen", "fetched_at", "parse_warnings",
]  # fmt: skip
_ARRAYS = ("wg_types", "languages", "features", "image_urls", "parse_warnings")
_INTS = (
    "rent_total_eur", "rent_cold_eur", "utilities_eur", "other_costs_eur", "deposit_eur",
    "transfer_fee_eur", "household_size", "flatmates_women", "flatmates_men",
    "flatmates_diverse", "flatmates_age_min", "flatmates_age_max", "looking_for_age_min",
    "looking_for_age_max",
)  # fmt: skip


def _pg_array(values) -> str | None:
    if values is None or (isinstance(values, float) and pd.isna(values)):
        return None
    items = [str(v).replace("\\", "\\\\").replace('"', '\\"') for v in list(values)]
    return "{" + ",".join(f'"{v}"' for v in items) + "}"


def table(snapshot: gpd.GeoDataFrame) -> pd.DataFrame:
    """Rows for `lst_<id>.listings`: contract columns only, arrays and geometry as COPY text."""
    s = snapshot[snapshot["listing_id"].notna() & snapshot["kind"].notna()].copy()
    s = s.drop_duplicates("listing_id")
    s["parse_warnings"] = s.get("warnings")
    has_geom = s.geometry.notna() & ~s.geometry.is_empty
    s["geom"] = None
    if has_geom.any():
        s.loc[has_geom, "geom"] = db.ewkb(s.loc[has_geom].geometry)
    for col in _ARRAYS:
        s[col] = s[col].map(_pg_array) if col in s else None
    for col in _INTS:
        s[col] = (
            pd.to_numeric(s[col], errors="coerce").round().astype("Int64") if col in s else None
        )
    for col in COLUMNS:
        if col not in s:
            s[col] = None
    return pd.DataFrame(s[COLUMNS])


def snapshot_schemas(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'lst\\_%'")
    return sorted(r[0] for r in rows if _SNAPSHOT_RE.match(r[0]))


def switch_views(conn: psycopg.Connection, schema: str) -> None:
    with conn.transaction():
        for name in db.relations(conn, schema):
            conn.execute(
                sql.SQL("CREATE OR REPLACE VIEW {}.{} AS SELECT * FROM {}.{}").format(
                    sql.Identifier(SCHEMA),
                    sql.Identifier(name),
                    sql.Identifier(schema),
                    sql.Identifier(name),
                )
            )


def publish(cfg: Config, sql_dir: Path, conn: psycopg.Connection) -> str:
    snaps = sorted((cfg.data_dir / SNAPSHOTS).glob("*/listings.parquet"))
    if not snaps:
        raise StageValidationError("publish_listings: no snapshot; run the crawl first")
    path = snaps[-1]
    snapshot_id = path.parent.name
    rows = table(gpd.read_parquet(path))
    if rows.empty:
        raise StageValidationError(f"publish_listings: snapshot {snapshot_id} has no listings")
    schema = f"lst_{snapshot_id.lower()}"
    template = (sql_dir / TEMPLATE).read_text(encoding="utf-8")
    n = db.load_run(conn, schema, template, {"listings": rows})
    switch_views(conn, schema)
    keep = cfg.listings.keep_snapshots if cfg.listings else 3
    for old in snapshot_schemas(conn)[:-keep]:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(old)))
        log.info("publish_listings: dropped %s", old)
    log.info("publish_listings: %s with %d listings is live", schema, n["listings"])
    return schema


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="reach_pipeline.listings.publish")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--sql-dir", default="infra/db")
    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    try:
        with db.connect(db.env_url("DATABASE_URL_PIPELINE"), cfg.database) as conn:
            publish(cfg, Path(args.sql_dir), conn)
    except StageValidationError as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
