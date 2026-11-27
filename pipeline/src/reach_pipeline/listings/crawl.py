"""Daily WG-Gesucht crawl (F4.4, architecture O24, notes N20): search pages → new ads → parse →
geocode against the run's addresses → Zensus cell → `data/listings/<snapshot_id>/listings.parquet`.

Polite: one request at a time, `listings.request_interval_s` apart, identifying user agent; ads
already in the previous snapshot are not fetched again (their row is carried over with a new
`last_seen`). Raw pages stay in memory and are never written (data contract, Listings). Stops
on a captcha or an unexpected page and exits non-zero.

Usage: `uv run python -m reach_pipeline.listings.crawl [--max-pages N] [--config …]`.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd

from reach_pipeline.config import Config, Listings, load_config
from reach_pipeline.errors import ExternalError, StageValidationError
from reach_pipeline.listings.parse import SearchHit, parse_ad, parse_search
from reach_pipeline.zensus import cell_ids

log = logging.getLogger(__name__)

CRS = "EPSG:25832"
SNAPSHOTS = "listings"
_BLOCKED = re.compile(r"captcha|Sicherheitsabfrage|Zugriff verweigert|Access denied", re.I)


class Fetcher:
    """GET with the polite interval between any two requests; stops on a block page."""

    def __init__(self, cfg: Listings, client: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.client = client or httpx.Client(
            base_url=cfg.base_url,
            headers={"User-Agent": cfg.user_agent},
            timeout=cfg.timeout_s,
            follow_redirects=True,
        )
        self._last = 0.0
        self.requests = 0

    def get(self, url: str) -> str:
        wait = self.cfg.request_interval_s - (time.monotonic() - self._last)
        if self._last and wait > 0:
            time.sleep(wait)
        try:
            r = self.client.get(url)
        except httpx.TransportError as exc:
            raise ExternalError(f"listings: GET {url} failed: {exc}") from exc
        finally:
            self._last = time.monotonic()
            self.requests += 1
        if r.status_code in (403, 429) or _BLOCKED.search(r.text[:20000] if r.text else ""):
            raise ExternalError(f"listings: blocked at {url} (HTTP {r.status_code}); stopping")
        if r.status_code != 200:
            raise ExternalError(f"listings: GET {url} → HTTP {r.status_code}")
        return r.text


def search(fetcher: Fetcher, cfg: Listings, max_pages: int) -> list[SearchHit]:
    """Ads on the search pages of every kind; a kind stops at the first page without new ads."""
    hits: dict[str, SearchHit] = {}
    for kind, path in cfg.search_paths.items():
        for page in range(max_pages):
            found = parse_search(fetcher.get(path.format(page=page)), cfg.base_url)
            new = [h for h in found if h.listing_id not in hits]
            log.info("listings %s page %d: %d ads (%d new)", kind, page, len(found), len(new))
            if not found and page == 0:
                raise StageValidationError(f"listings: no ads on the first {kind} page (layout?)")
            hits.update((h.listing_id, h) for h in new)
            if not new:
                break
    return list(hits.values())


# --- geocoding (F4.5, against validate/addresses.parquet) ----------------------------------------

_STREET_ABBR = (("straße", "str"), ("strasse", "str"), ("str.", "str"))


def norm_street(text: str | None) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    t = text.lower().strip()
    for a, b in _STREET_ABBR:
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9äöüß]+", "", t) or None


def split_address(text: str | None) -> tuple[str | None, str | None]:
    """`Wilhelmstraße 5a` → (`wilhelmstr`, `5a`); no number → (street, None)."""
    if not isinstance(text, str) or not text:
        return None, None
    m = re.match(r"^\s*(.*?)\s+(\d+\s*[a-zA-Z]?)\s*$", text)
    if not m:
        return norm_street(text), None
    return norm_street(m.group(1)), m.group(2).replace(" ", "").lower()


def geocode(listings: pd.DataFrame, addresses: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Point and precision per listing: exact house number → `house`, street mean → `street`,
    else the ad's own map marker → `marker` (approximate), else none."""
    a = addresses.assign(
        _s=addresses["street"].map(norm_street),
        _h=addresses["housenumber"].astype(str).str.replace(" ", "").str.lower(),
        _x=addresses.geometry.x,
        _y=addresses.geometry.y,
    )
    house = a.groupby(["_s", "_h"])[["_x", "_y"]].mean()
    street = a.groupby("_s")[["_x", "_y"]].mean()
    parts = listings["address_text"].map(split_address)
    s = parts.str[0]
    h = parts.str[1]
    xy = pd.DataFrame(index=listings.index, columns=["x", "y"], dtype=float)
    precision = pd.Series(pd.NA, index=listings.index, dtype="object")
    hk = pd.MultiIndex.from_arrays([s, h])
    hit = hk.isin(house.index)
    xy.loc[hit, ["x", "y"]] = house.loc[hk[hit]].to_numpy()
    precision[hit] = "house"
    st = ~hit & s.isin(street.index).to_numpy()
    xy.loc[st, ["x", "y"]] = street.loc[s[st]].to_numpy()
    precision[st] = "street"
    marker = precision.isna() & listings["source_lat"].notna()
    if marker.any():
        pts = gpd.GeoSeries(
            gpd.points_from_xy(
                listings.loc[marker, "source_lon"], listings.loc[marker, "source_lat"]
            ),
            crs="EPSG:4326",
        ).to_crs(CRS)
        xy.loc[marker, "x"] = pts.x.to_numpy()
        xy.loc[marker, "y"] = pts.y.to_numpy()
        precision[marker] = "marker"
    geom = gpd.points_from_xy(xy["x"], xy["y"])
    out = gpd.GeoDataFrame(listings.assign(geocode_precision=precision), geometry=geom, crs=CRS)
    out.loc[precision.isna(), "geometry"] = None
    return out


def assign_cells(listings: gpd.GeoDataFrame, cells: pd.DataFrame) -> pd.Series:
    """Zensus cell of each point; points outside the run's cells get none."""
    ok = listings.geometry.notna() & ~listings.geometry.is_empty
    ids = pd.Series(pd.NA, index=listings.index, dtype="object")
    if ok.any():
        ids[ok] = cell_ids(listings.loc[ok].geometry)["cell_id"].to_numpy()
    return ids.where(ids.isin(set(cells["cell_id"])))


# --- snapshot -----------------------------------------------------------------------------------


def latest_run(cfg: Config) -> Path:
    runs = sorted(p for p in (cfg.data_dir / "runs").glob("*/validate/addresses.parquet"))
    if not runs:
        raise StageValidationError(
            "listings: no validate/addresses.parquet; run the pipeline first"
        )
    return runs[-1].parent


def previous_snapshot(root: Path) -> pd.DataFrame | None:
    snaps = sorted(root.glob("*/listings.parquet"))
    return pd.read_parquet(snaps[-1]) if snaps else None


def run(cfg: Config, max_pages: int | None = None, client: httpx.Client | None = None) -> Path:
    lc = cfg.listings
    if lc is None:
        raise StageValidationError("config has no listings section")
    now = datetime.now(UTC).replace(microsecond=0)
    snapshot_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = cfg.data_dir / SNAPSHOTS
    previous = previous_snapshot(root)
    fetcher = Fetcher(lc, client)
    t0 = time.perf_counter()
    hits = search(fetcher, lc, max_pages or lc.max_search_pages)
    known = set(previous["listing_id"]) if previous is not None else set()
    rows = []
    for hit in hits:
        if hit.listing_id in known:
            continue
        fetched = datetime.now(UTC)
        ad = parse_ad(
            fetcher.get(hit.url),
            hit.url,
            fetched,
            description_max_chars=lc.description_max_chars,
            title_max_chars=lc.title_max_chars,
        )
        rows.append(asdict(ad) | {"first_seen": now.isoformat()})
    fresh = pd.DataFrame(rows)
    seen = {h.listing_id for h in hits}
    kept = pd.DataFrame()
    if previous is not None:
        prev = previous.drop(columns=["geometry", "cell_id", "geocode_precision"], errors="ignore")
        still = prev["listing_id"].isin(seen)
        cutoff = (now - timedelta(days=lc.retention_days)).isoformat()
        kept = prev[still | (prev["last_seen"] >= cutoff)]
    table = pd.concat([kept, fresh], ignore_index=True)
    table.loc[table["listing_id"].isin(seen), "last_seen"] = now.isoformat()
    table = table[table["errors"].map(lambda e: "not_an_ad" not in list(e))]
    vdir = latest_run(cfg)
    addresses = gpd.read_parquet(vdir / "addresses.parquet")
    cells = pd.read_parquet(vdir / "cells.parquet", columns=["cell_id"])
    geo = geocode(table.reset_index(drop=True), addresses)
    geo["cell_id"] = assign_cells(geo, cells)
    out_dir = root / snapshot_id
    out_dir.mkdir(parents=True, exist_ok=True)
    geo.to_parquet(out_dir / "listings.parquet", index=False)
    log.info(
        "listings %s: %d ads (%d new, %d requests, %.0f s); precision %s; with cell %d",
        snapshot_id,
        len(geo),
        len(fresh),
        fetcher.requests,
        time.perf_counter() - t0,
        geo["geocode_precision"].value_counts(dropna=False).to_dict(),
        int(geo["cell_id"].notna().sum()),
    )
    return out_dir


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(prog="reach_pipeline.listings.crawl")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--max-pages", type=int, default=None, help="search pages per kind")
    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    if cfg.listings is None or not cfg.listings.enabled:
        log.error("listings.enabled is false in the config; nothing to do")
        return 2
    try:
        run(cfg, args.max_pages)
    except (ExternalError, StageValidationError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
