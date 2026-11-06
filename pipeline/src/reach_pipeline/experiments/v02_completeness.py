"""V2 OSM completeness for childcare and schools vs. the city's own lists.

Reference (decision by Rico, 6 Nov 2026): the city of Tübingen publishes its Kitas (all
operators) and schools as HTML pages only, without a download or a stated licence. They are
fetched once, politely (`v02.request_interval_s`), and only name, address and operator are kept
in `<data_dir>/reference/` (git-ignored, not redistributed); later runs reuse the files.
No geocoding service: a reference entry is placed on the OSM address point with the same street
and house number (the run's clipped PBF). Matching: an OSM facility of the category within
`match_radius_m` of that point, or with a similar name (token Jaccard ≥ `name_min_jaccard`).
Recall = reference entries with a match; precision = OSM facilities inside the city with a match.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
import shapely

from reach_pipeline import osm
from reach_pipeline.errors import ExternalError
from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.stages import validate

NAME = "v02"
TITLE = "OSM completeness (childcare, schools) vs. the city's lists"
FILES = {"childcare": "tuebingen_childcare.csv", "school": "tuebingen_schools.csv"}
PROVENANCE = "tuebingen_reference.json"
_TAG = re.compile(r"<[^>]+>")
_PLZ = re.compile(r"^(\d{5})\s+(.+)$")
_DETAIL = re.compile(r'href="(/[0-9/]+einrichtung\d+\.html)"')
_KITA = re.compile(r'href="(/kindertageseinrichtungen/\d+)"')
# Words that say what a facility is, not which one: ignored in the name comparison.
GENERIC = {
    "kindergarten",
    "kita",
    "kindertagesstätte",
    "kindertageseinrichtung",
    "kinderhaus",
    "kinderkrippe",
    "krippe",
    "schule",
    "grundschule",
    "standort",
    "e",
    "v",
    "ev",
    "der",
    "die",
    "das",
    "am",
    "an",
    "im",
    "in",
    "auf",
    "und",
    "st",
    "tübingen",
    "städtischer",
    "städtische",
}

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- parsing (pure functions)
def text_lines(fragment: str) -> list[str]:
    """Visible text lines of an HTML fragment (tags as line breaks)."""
    text = _TAG.sub("\n", fragment)
    return [html.unescape(t).strip() for t in text.split("\n") if html.unescape(t).strip()]


def parse_detail(page: str) -> dict[str, str | None]:
    """Name (h1), street, postcode, place and operator (`Träger:`) of a city detail page."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>(.*)", page, re.S)
    if not m:
        return {"name": None, "street": None, "postcode": None, "place": None, "operator": None}
    name = " ".join(text_lines(m.group(1)))
    lines = text_lines(m.group(2))[:12]
    street = postcode = place = None
    for prev, line in zip([None, *lines], lines, strict=False):
        plz = _PLZ.match(line)
        if plz:
            street, postcode, place = prev, plz.group(1), plz.group(2)
            break
    op = re.search(r"Träger:\s*([^<\n]+)", page)
    return {
        "name": name,
        "street": street,
        "postcode": postcode,
        "place": place,
        "operator": html.unescape(op.group(1)).strip() if op else None,
    }


def normalise_street(street: str) -> str:
    s = street.lower().replace("ß", "ss")
    s = re.sub(r"strasse\b|str\.?(?=\s|$)", "str", s)
    return re.sub(r"[^a-z0-9äöü]", "", s)


def split_address(street_line: str) -> tuple[str, str] | None:
    """('normalised street', 'house number') of a line such as `Schwärzlocher Täle 3/1`."""
    m = re.match(r"^(.*?)\s+(\d+\s*[a-zA-Z]?(?:\s*[/-]\s*\d+[a-zA-Z]?)?)$", street_line.strip())
    if not m:
        return None
    return normalise_street(m.group(1)), re.sub(r"\s", "", m.group(2)).lower()


def name_tokens(name: object) -> set[str]:
    if not isinstance(name, str):  # None or NaN (OSM objects without a name)
        return set()
    words = re.findall(r"[a-zäöüß0-9]+", name.lower())
    return {w for w in words if w not in GENERIC and len(w) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# ---------------------------------------------------------------- fetching (one-off)
class _Fetcher:
    def __init__(self, e: Experiment) -> None:
        s = e.settings.v02
        self.s = s
        self.client = httpx.Client(
            base_url=s.base_url,
            timeout=s.timeout_s,
            headers={"User-Agent": s.user_agent},
            follow_redirects=True,
        )
        self.pages = 0
        self._last = 0.0

    def get(self, path: str) -> str:
        wait = self._last + self.s.request_interval_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.client.get(path)
        except httpx.HTTPError as exc:
            raise ExternalError(f"GET {self.s.base_url}{path} failed: {exc}") from exc
        finally:
            self._last = time.monotonic()
        self.pages += 1
        if resp.status_code != 200:
            raise ExternalError(f"GET {self.s.base_url}{path} answered {resp.status_code}")
        return resp.text


def fetch_childcare(f: _Fetcher) -> pd.DataFrame:
    links = sorted(set(_KITA.findall(f.get(f.s.childcare_list))))
    rows = [{**parse_detail(f.get(p)), "source_path": p} for p in links]
    return pd.DataFrame(rows)


def fetch_schools(f: _Fetcher) -> pd.DataFrame:
    """Detail pages linked from the school lists or from their sub-lists (one level)."""
    details: set[str] = set()
    for root in f.s.school_lists:
        page = f.get(root)
        details |= set(_DETAIL.findall(page))
        prefix = root.removesuffix(".html")
        for sub in sorted(set(re.findall(rf'href="({re.escape(prefix)}/\d+\.html)"', page))):
            details |= set(_DETAIL.findall(f.get(sub)))
    rows = [{**parse_detail(f.get(p)), "source_path": p} for p in sorted(details)]
    return pd.DataFrame(rows)


def reference_lists(e: Experiment) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """The cached lists, fetched first if missing."""
    ref = e.reference_dir
    prov_path = ref / PROVENANCE
    if all((ref / n).exists() for n in FILES.values()) and prov_path.exists():
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        prov["cached"] = True
        return {c: pd.read_csv(ref / n, dtype=str) for c, n in FILES.items()}, prov
    log.info(
        "fetching the city's Kita and school pages (once, %s s apart)",
        e.settings.v02.request_interval_s,
    )
    f = _Fetcher(e)
    started = time.monotonic()
    lists = {"childcare": fetch_childcare(f), "school": fetch_schools(f)}
    for cat, frame in lists.items():
        frame.to_csv(ref / FILES[cat], index=False)
    prov = {
        "source": e.settings.v02.base_url,
        "paths": [e.settings.v02.childcare_list, *e.settings.v02.school_lists],
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pages_fetched": f.pages,
        "runtime_s": round(time.monotonic() - started, 1),
        "entries": {c: len(v) for c, v in lists.items()},
        "licence": "none stated (city web pages); used for validation only, not redistributed",
        "cached": False,
    }
    prov_path.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    return {c: pd.read_csv(ref / n, dtype=str) for c, n in FILES.items()}, prov


# ---------------------------------------------------------------- matching
def address_points(e: Experiment) -> pd.DataFrame:
    """OSM objects with street and house number (centroids, EPSG:25832) of the clipped PBF."""
    work = e.out / "osm"
    work.mkdir(exist_ok=True)
    pbf = e.ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF
    filtered = osm.tags_filter(pbf, work / "addresses.osm.pbf", ["nwr/addr:housenumber"])
    pts = osm.read_export(osm.export(filtered, work / "addresses.geojsonseq", ["point", "polygon"]))
    pts = pts.dropna(subset=["addr:street", "addr:housenumber"])
    return pd.DataFrame(
        {
            "street": pts["addr:street"].map(normalise_street),
            "number": pts["addr:housenumber"].str.replace(r"\s", "", regex=True).str.lower(),
            "x": pts.geometry.centroid.x.to_numpy(),
            "y": pts.geometry.centroid.y.to_numpy(),
        }
    )


def locate(ref: pd.DataFrame, addresses: pd.DataFrame) -> pd.DataFrame:
    """Reference rows plus x, y of the matching address point (exact number, else the number
    without suffix); NaN when the address is not in OSM."""
    keys = ref["street"].fillna("").map(split_address)
    ref = ref.assign(
        street_key=[k[0] if k else None for k in keys],
        number=[k[1] if k else None for k in keys],
    )
    ref["number_base"] = ref["number"].str.extract(r"^(\d+)", expand=False)
    exact = addresses.groupby(["street", "number"])[["x", "y"]].mean()
    addresses = addresses.assign(base=addresses["number"].str.extract(r"^(\d+)", expand=False))
    base = addresses.groupby(["street", "base"])[["x", "y"]].mean()
    xy = exact.reindex(pd.MultiIndex.from_arrays([ref["street_key"], ref["number"]]))
    xy_base = base.reindex(pd.MultiIndex.from_arrays([ref["street_key"], ref["number_base"]]))
    ref["x"] = xy["x"].to_numpy()
    ref["y"] = xy["y"].to_numpy()
    missing = ref["x"].isna().to_numpy()
    ref.loc[missing, "x"] = xy_base["x"].to_numpy()[missing]
    ref.loc[missing, "y"] = xy_base["y"].to_numpy()[missing]
    return ref


def match(
    ref: pd.DataFrame, fac: gpd.GeoDataFrame, radius_m: float, min_jaccard: float
) -> pd.DataFrame:
    """All (reference, facility) pairs that match by distance or by name."""
    f_xy = common.xy(fac.geometry)
    f_tok = [name_tokens(n) for n in fac["name"]]
    rows = []
    for i, r in enumerate(ref.itertuples()):
        tok = name_tokens(r.name)
        d = (
            np.hypot(f_xy[:, 0] - r.x, f_xy[:, 1] - r.y)
            if not pd.isna(r.x)
            else np.full(len(fac), np.inf)
        )
        sim = np.array([jaccard(tok, t) for t in f_tok])
        for j in np.flatnonzero((d <= radius_m) | (sim >= min_jaccard)):
            rows.append(
                {
                    "ref": i,
                    "facility": int(j),
                    "distance_m": round(float(d[j]), 1),
                    "name_jaccard": round(float(sim[j]), 3),
                }
            )
    return pd.DataFrame(rows, columns=["ref", "facility", "distance_m", "name_jaccard"])


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v02
    lists, provenance = reference_lists(e)
    addresses = address_points(e)
    city = e.districts.geometry.union_all()
    out: dict[str, Any] = {"status": "done", "reference": provenance, "categories": {}}
    for cat, ref in lists.items():
        ref = locate(ref.reset_index(drop=True), addresses)
        fac = e.facilities[e.facilities["category"] == cat]
        fac = fac[shapely.within(fac.geometry.values, city)].reset_index(drop=True)
        pairs = match(ref, fac, s.match_radius_m, s.name_min_jaccard)
        ref["matched"] = ref.index.isin(pairs["ref"])
        fac = fac.assign(matched=fac.index.isin(pairs["facility"]))
        ref.drop(columns=["x", "y"]).to_csv(e.out / f"{cat}_reference.csv", index=False)
        fac.drop(columns="geometry").to_csv(e.out / f"{cat}_osm.csv", index=False)
        located = ref["x"].notna()
        out["categories"][cat] = {
            "reference_entries": int(len(ref)),
            "reference_located": int(located.sum()),
            "osm_in_city": int(len(fac)),
            "recall": round(float(ref["matched"].mean()), 4) if len(ref) else None,
            "recall_located_only": (
                round(float(ref.loc[located, "matched"].mean()), 4) if located.any() else None
            ),
            "precision": round(float(fac["matched"].mean()), 4) if len(fac) else None,
            "matched_by_distance_only": int(
                (
                    (pairs["distance_m"] <= s.match_radius_m)
                    & (pairs["name_jaccard"] < s.name_min_jaccard)
                ).sum()
            ),
            "reference_unmatched": ref.loc[~ref["matched"], "name"].tolist(),
            "osm_unmatched": fac.loc[~fac["matched"], "name"].fillna("(no name)").tolist(),
        }
    return out
