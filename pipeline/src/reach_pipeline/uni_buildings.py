"""University buildings from the official address list → campus sites (notes N30).

The university publishes every building on "Adressenliste" with a link to its page on one of four
site maps (Karte A Morgenstelle, B Wilhelmstraße – Talkliniken, C Sand – Außenbereiche, D Altstadt).
Each page names the building, its institutes and its address. We fetch the list and the pages once
(polite: `rate_limit_s` between requests, identifying user agent, raw pages kept and reused),
locate each address in our own OSM address index (no geocoder) and assign the nearest campus site.
The result is the reviewed file `config/university_buildings.csv`, which `alma shares` uses to
map the building Alma prints after a room to a site (via `alma.building_addresses`).

Usage: `uv run python -m reach_pipeline.uni_buildings crawl|build [--run-id <run with validate>]`.
"""

from __future__ import annotations

import argparse
import gzip
import html
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import geopandas as gpd
import httpx
import pandas as pd

from reach_pipeline.campus import Campus, load_campus
from reach_pipeline.config import UniBuildings, load_config
from reach_pipeline.errors import ExternalError, StageValidationError

log = logging.getLogger(__name__)

RAW = Path("raw") / "uni_buildings"
OUT_NAME = "university_buildings.csv"
COLUMNS = ["address", "title", "sheet", "institutes", "lon", "lat", "site", "site_m", "located"]
SHEETS = {"a": "Morgenstelle", "b": "Wilhelmstraße – Talkliniken", "c": "Sand – Außenbereiche",
          "d": "Altstadt"}  # fmt: skip
_LINK = re.compile(
    r'<a href="(/universitaet/standort-und-anfahrt/lageplaene/karte-([a-d])-[^/"]+/[^"]+)"[^>]*>'
    r"(.*?)</a>",
    re.S,
)
_TAG = re.compile(r"<[^>]+>")
_ADDRESS = re.compile(r"^(.+?)\s+(\d+)\s*([a-z])?(?:\s*(?:/|-|–|bis|und)\s*\S+)*\s*$")
_POSTCODE = re.compile(r"^7207\d Tübingen$")
_STOP = ("Informationen zur Barrierefreiheit", "Nr. ", "Übersichtsplan", "Anfahrt")


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", fragment))).strip()


def parse_list(page: str) -> pd.DataFrame:
    """Entries of the address list: link path, map sheet (a–d) and the listed title."""
    rows = [
        {"path": path, "sheet": sheet, "title": _clean(title)}
        for path, sheet, title in _LINK.findall(page)
    ]
    out = pd.DataFrame(rows, columns=["path", "sheet", "title"]).drop_duplicates("path")
    if out.empty:
        raise StageValidationError("uni_buildings: the address list has no building links")
    return out.reset_index(drop=True)


def parse_page(page: str) -> dict[str, str | None]:
    """Address and institutes of one building page: the lines after the title up to the postcode
    line are institutes, the line before the postcode is the street address. Some pages have no
    postcode block; then `address` is None and the list title gives it."""
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    lines = [ln.strip() for ln in html.unescape(_TAG.sub("\n", body)).splitlines() if ln.strip()]
    # the map overview ends with "Karte D: Altstadt"; on Altstadt pages it is also in the menu
    starts = [i + 1 for i, ln in enumerate(lines) if ln == "Karte D: Altstadt"]
    if not starts:
        raise StageValidationError("uni_buildings: page without the map overview")
    for start in reversed(starts):  # the content overview is the last one
        block = lines[start + 1 : start + 40]
        stop = next((i for i, ln in enumerate(block) if ln.startswith(_STOP)), len(block))
        for i, ln in enumerate(block[:stop]):
            if _POSTCODE.match(ln):
                address = block[i - 1] if i else None
                return {"address": address, "institutes": "; ".join(block[: max(i - 1, 0)])}
    block = lines[starts[-1] + 1 : starts[-1] + 40]
    stop = next((i for i, ln in enumerate(block) if ln.startswith(_STOP)), len(block))
    return {"address": None, "institutes": "; ".join(block[:stop])}


def title_address(title: str) -> str:
    """The part of a list title with a house number: `Alte Aula – Münzgasse 30` → `Münzgasse 30`."""
    parts = [p.strip() for p in re.split(r"\s+–\s+", title)]
    return next((p for p in parts if re.search(r"\s\d", p)), parts[0])


def _key(street: str, number: str) -> str:
    s = street.lower().replace("straße", "str").replace("str.", "str").replace("-", " ")
    return f"{re.sub(r'\s+', ' ', s).strip()} {number.lower()}"


def address_key(address: str) -> str | None:
    """`Liebermeisterstraße 12 bis 16` → `liebermeisterstr 12`; None without a house number."""
    m = _ADDRESS.match(address.strip())
    return _key(m.group(1), m.group(2) + (m.group(3) or "")) if m else None


def candidates(address: str, title: str) -> list[str]:
    """Address keys to try: each part of the page address (`Wilhelmstraße 9 / Nauklerstraße 2`,
    `Gmelinstraße 6, Eingang …`, `… (Altes Oberschulamt)`), then each part of the list title."""
    out = []
    for text in (address, title):
        text = re.sub(r"\([^)]*\)", " ", text)
        for part in re.split(r"\s+/\s+|,|\s+–\s+|\s+und\s+(?=\D)", text):
            part = re.sub(r"^(Eckgebäude|Gebäude)\s+", "", part.strip())
            key = address_key(part) if part else None
            if key and key not in out:
                out.append(key)
    return out


def locate(buildings: pd.DataFrame, addresses: gpd.GeoDataFrame, campus: Campus) -> pd.DataFrame:
    """Coordinates from the OSM address index (EPSG:25832), else from `building_points` in
    campus.yaml; the nearest campus site and its distance. `located` = `osm`, `campus.yaml` or
    `missing`."""
    tue = addresses[addresses["city"].astype(str).str.contains("Tübingen", na=False)]
    first = tue["housenumber"].astype(str).str.extract(r"^(\d+\s*[a-z]?)", expand=False)
    keys = [
        _key(st, n.replace(" ", "")) if isinstance(n, str) else None
        for st, n in zip(tue["street"], first, strict=True)
    ]
    index: dict[str, object] = {}
    for k, g in zip(keys, tue.geometry, strict=True):
        if k and k not in index:
            index[k] = g
    manual = gpd.GeoSeries.from_xy(
        [p[0] for p in campus.building_points.values()],
        [p[1] for p in campus.building_points.values()],
        index=list(campus.building_points),
        crs=4326,
    ).to_crs(addresses.crs)
    out = buildings.copy()
    geoms, how = [], []
    for address, title in zip(out["address"], out["title"], strict=True):
        hit = next((index[k] for k in candidates(address, title) if k in index), None)
        if title in manual.index:
            geoms.append(manual[title])
            how.append("campus.yaml")
        elif hit is not None:
            geoms.append(hit)
            how.append("osm")
        else:
            geoms.append(None)
            how.append("missing")
    pts = gpd.GeoSeries(geoms, crs=addresses.crs)
    sites = gpd.GeoSeries.from_xy(
        [p.point[0] for p in campus.areas.values()],
        [p.point[1] for p in campus.areas.values()],
        index=list(campus.areas),
        crs=4326,
    ).to_crs(addresses.crs)
    out["located"] = how
    dist = pd.DataFrame({s: pts.distance(g) for s, g in sites.items()})
    found = pts.notna().to_numpy()
    out["site"] = dist.fillna(float("inf")).idxmin(axis=1).where(found)
    out["site_m"] = dist.min(axis=1).round().astype("Int64").where(found)
    ll = pts.to_crs(4326)
    out["lon"] = ll.x.round(5).where(found)
    out["lat"] = ll.y.round(5).where(found)
    return out[COLUMNS]


def _get(client: httpx.Client, cfg: UniBuildings, url: str) -> str:
    for attempt in range(cfg.retries + 1):
        try:
            r = client.get(url)
            r.raise_for_status()
            return r.text
        except httpx.TransportError as exc:
            if attempt == cfg.retries:
                raise ExternalError(f"uni_buildings: GET {url} failed: {exc}") from exc
            time.sleep(cfg.backoff_s * 2**attempt)
    raise AssertionError("unreachable")


def crawl(cfg: UniBuildings, raw_dir: Path) -> pd.DataFrame:
    """The list and every building page (pages on disk are reused)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": cfg.user_agent}
    with httpx.Client(headers=headers, timeout=cfg.timeout_s, follow_redirects=True) as client:
        list_path = raw_dir / "list.html.gz"
        if not list_path.exists():
            list_path.write_bytes(gzip.compress(_get(client, cfg, cfg.list_url).encode()))
            time.sleep(cfg.rate_limit_s)
        entries = parse_list(gzip.decompress(list_path.read_bytes()).decode())
        rows = []
        for e in entries.itertuples():
            slug = e.path.strip("/").split("/")[-1]
            path = raw_dir / f"{e.sheet}-{slug}.html.gz"
            if not path.exists():
                page = _get(client, cfg, urljoin(cfg.list_url, e.path))
                parse_page(page)  # fail loudly before storing a wrong page
                path.write_bytes(gzip.compress(page.encode()))
                log.info("uni_buildings: %s", e.title)
                time.sleep(cfg.rate_limit_s)
            info = parse_page(gzip.decompress(path.read_bytes()).decode())
            info["address"] = info["address"] or title_address(e.title)
            rows.append({"title": e.title, "sheet": e.sheet, **info})
    out = pd.DataFrame(rows).drop_duplicates("address", ignore_index=True)
    log.info("uni_buildings: %d entries, %d distinct addresses", len(entries), len(out))
    return out


def load(path: Path) -> pd.DataFrame:
    """The reviewed building table (`config/university_buildings.csv`)."""
    return pd.read_csv(path, dtype={"site_m": "Int64"}, keep_default_na=False, na_values=[""])


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="reach_pipeline.uni_buildings")
    ap.add_argument("action", choices=["crawl", "build"])
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--run-id", help="run whose validate/addresses.parquet locates the addresses")
    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    if cfg.uni_buildings is None:
        log.error("config has no uni_buildings section")
        return 2
    raw_dir = cfg.data_dir / RAW
    try:
        buildings = crawl(cfg.uni_buildings, raw_dir)
        if args.action == "build":
            runs = sorted((cfg.data_dir / "runs").glob("*/validate/addresses.parquet"))
            if args.run_id:
                runs = [cfg.data_dir / "runs" / args.run_id / "validate" / "addresses.parquet"]
            if not runs or not runs[-1].exists():
                raise StageValidationError("uni_buildings: no validate/addresses.parquet")
            campus = load_campus(Path(args.config), generated=False)
            table = locate(buildings, gpd.read_parquet(runs[-1]), campus)
            out = Path(args.config).parent / OUT_NAME
            table.to_csv(out, index=False)
            log.info(
                "uni_buildings: %s written, sites %s, missing %d",
                out,
                table["site"].value_counts().to_dict(),
                int((table["located"] == "missing").sum()),
            )
    except (ExternalError, StageValidationError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
