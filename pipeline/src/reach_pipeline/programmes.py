"""Alma programmes → teaching buildings weighted by compulsory session hours (meth. §3.2, N31).

Inputs (all offline, from the polite crawls):

- sessions of the reference week (`alma.py`): course, parallel group, time, Alma building;
- per course its modules and programmes (`alma_courses.py`);
- the university's official buildings with their nearest area (`uni_buildings.py`).

Steps (pure functions, vectorised):

1. **Course hours per building:** session hours of a course in the reference week per official
   building, divided by the number of its parallel groups (a student attends one group).
2. **Module code → programme:** module short texts carry codes (`82|410|H`), the programme table
   carries names ("Bachelor", "Economics and Business Administration", "Hauptfach"). A code is
   the programme whose set of courses overlaps its own most (Jaccard over all courses).
3. **Compulsory:** a course is compulsory for a programme if one of its modules for that programme
   has a name that is not elective (`alma.elective_modules`, e.g. "Elective Studies",
   "Wahlpflichtmodul", "Profilbereich").
4. **Programme hours per building:** compulsory hours; a programme with fewer than
   `min_compulsory_h` compulsory hours (many masters) uses all its courses and says so.
5. **Buildings → destinations:** official buildings closer than `cluster_radius_m` form one
   destination; shares below `min_share` are dropped and the rest renormalised.

Usage: `uv run python -m reach_pipeline.programmes build` → `config/campus_buildings.csv` and
`config/programmes.csv` (reviewed and committed like `config/university_buildings.csv`).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from reach_pipeline import alma, alma_courses, uni_buildings
from reach_pipeline.campus import METRIC_CRS, Campus, load_campus
from reach_pipeline.config import load_config
from reach_pipeline.errors import ExternalError, StageValidationError

log = logging.getLogger(__name__)

BUILDINGS_FILE = "campus_buildings.csv"
PROGRAMMES_FILE = "programmes.csv"
BUILDING_COLUMNS = ["building_id", "name", "address", "area", "lon", "lat", "hours"]
PROGRAMME_COLUMNS = [
    "programme",
    "degree",
    "subject",
    "basis",
    "courses",
    "hours",
    "buildings",
    "shares",
]
MAJOR = {"H": "Hauptfach", "N": "Nebenfach"}


def slug(text: str) -> str:
    """ASCII id: "Bachelor Wirtschaftsinformatik" → "bachelor-wirtschaftsinformatik"."""
    t = text.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    t = t.replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


# --- 1. course hours per building ----------------------------------------------------------------


def course_hours(sessions: pd.DataFrame, campus: Campus, semester: str) -> pd.DataFrame:
    """Weekly hours per course and official building, per parallel group (unit_id, title, hours)."""
    s = sessions[
        (sessions["semester"] == semester) & (sessions["room"] != "") & (sessions["unit_id"] != "")
    ].copy()
    s["hours"] = alma._hours(s["start"], s["end"])
    s = s[(s["hours"] > 0) & (s["hours"] <= campus.alma.max_session_h)]
    groups = s.groupby("unit_id")["group"].nunique().clip(lower=1)
    s["title"] = alma.address_of(s["building"], campus)
    s = s.dropna(subset=["title"])
    out = s.groupby(["unit_id", "title"], as_index=False)["hours"].sum()
    out["hours"] = out["hours"] / out["unit_id"].map(groups)
    return out


def display_names(sessions: pd.DataFrame, campus: Campus) -> pd.Series:
    """Official title → name for the app: the title if it names the building ("Hölderlinstraße 5 –
    Kupferbau"), else the building name Alma uses most, with the address ("WiWi Sem Mohl
    (Mohlstraße 36)")."""
    s = sessions[sessions["building"] != ""].copy()
    s["title"] = alma.address_of(s["building"], campus)
    top = s.dropna(subset=["title"]).groupby("title")["building"].agg(lambda b: b.mode().iat[0])
    named = top.index.str.contains(" – ")
    return pd.Series(np.where(named, top.index, top + " (" + top.index + ")"), index=top.index)


# --- 2. module code → programme ------------------------------------------------------------------


def programme_names(progs: pd.DataFrame, degrees: list[str]) -> pd.DataFrame:
    """Programme rows of offered degrees as majors, with the programme id (one per degree and
    subject; PO versions and first/second degree merged)."""
    p = progs[progs["degree"].isin(degrees) & (progs["major"] == MAJOR["H"])].copy()
    p["programme"] = (p["degree"] + " " + p["subject"]).map(slug)
    return p.drop_duplicates(["unit_id", "programme"])


def code_names(mods: pd.DataFrame, progs: pd.DataFrame) -> pd.Series:
    """Module code `degree|subject|major` → programme name `degree|subject|major` with the largest
    overlap of courses (Jaccard ≥ 0.3); unmatched codes are left out."""
    codes = alma_courses.split_code(mods["code"]).assign(unit_id=mods["unit_id"]).dropna()
    codes["key"] = codes["degree_code"] + "|" + codes["subject_code"] + "|" + codes["major_code"]
    codes["major"] = codes["major_code"].map(MAJOR)
    a = codes[["unit_id", "key", "major"]].drop_duplicates(["unit_id", "key"])
    names = progs.assign(name=progs["degree"] + "|" + progs["subject"] + "|" + progs["major"])
    b = names[["unit_id", "name", "major"]].drop_duplicates(["unit_id", "name"])
    pairs = a.merge(b, on=["unit_id", "major"])
    both = pairs.groupby(["key", "name"]).size().rename("both").reset_index()
    both["n_key"] = both["key"].map(a.groupby("key").size())
    both["n_name"] = both["name"].map(b.groupby("name").size())
    both["jaccard"] = both["both"] / (both["n_key"] + both["n_name"] - both["both"])
    best = both.sort_values("jaccard", ascending=False).drop_duplicates("key")
    best = best[best["jaccard"] >= 0.3]
    return best.set_index("key")["name"]


# --- 3. compulsory ------------------------------------------------------------------------------


def compulsory(mods: pd.DataFrame, names: pd.Series, elective: list[str]) -> pd.DataFrame:
    """(unit_id, name, compulsory): per course and programme name, True if one of its modules for
    that programme is not elective."""
    codes = alma_courses.split_code(mods["code"])
    key = codes["degree_code"] + "|" + codes["subject_code"] + "|" + codes["major_code"]
    m = mods.assign(name=key.map(names)).dropna(subset=["name"])
    m["compulsory"] = ~m["name_module"].str.contains("|".join(elective), case=False, regex=True)
    return m.groupby(["unit_id", "name"], as_index=False)["compulsory"].any()


# --- 4. programme hours per building -----------------------------------------------------------


def programme_hours(
    hours: pd.DataFrame,
    progs: pd.DataFrame,
    comp: pd.DataFrame,
    min_compulsory_h: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hours per programme and official building, and per programme its basis and course count.

    `progs` are the offered programme rows (`programme_names`), `comp` the compulsory flags."""
    p = progs.assign(name=progs["degree"] + "|" + progs["subject"] + "|" + progs["major"])
    p = p.merge(comp, on=["unit_id", "name"], how="left")
    p["compulsory"] = p["compulsory"].astype("boolean").fillna(False).astype(bool)
    rows = p[["unit_id", "programme", "compulsory"]].merge(hours, on="unit_id")
    comp_h = rows[rows["compulsory"]].groupby("programme")["hours"].sum()
    rows["basis"] = np.where(
        rows["programme"].map(comp_h).fillna(0) >= min_compulsory_h, "compulsory", "all"
    )
    used = rows[(rows["basis"] == "all") | rows["compulsory"]]
    per = used.groupby(["programme", "title"], as_index=False)["hours"].sum()
    meta = used.groupby("programme").agg(
        basis=("basis", "first"), courses=("unit_id", "nunique"), hours=("hours", "sum")
    )
    labels = p.drop_duplicates("programme").set_index("programme")[["degree", "subject"]]
    return per, meta.join(labels)


# --- 5. buildings → destinations ----------------------------------------------------------------


def clusters(table: pd.DataFrame, radius_m: float) -> pd.Series:
    """Official building title → cluster number (buildings closer than `radius_m` share one)."""
    located = table.dropna(subset=["lon", "lat"])
    pts = gpd.GeoSeries(gpd.points_from_xy(located["lon"], located["lat"]), crs="EPSG:4326").to_crs(
        METRIC_CRS
    )
    blobs = shapely.get_parts(shapely.union_all(pts.buffer(radius_m / 2).to_numpy()))
    tree = shapely.STRtree(blobs)
    return pd.Series(tree.query(pts.to_numpy(), predicate="within")[1], index=located["title"])


def destinations(
    per: pd.DataFrame,
    meta: pd.DataFrame,
    table: pd.DataFrame,
    campus: Campus,
    radius_m: float,
    min_share: float,
    names: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`campus_buildings.csv` and `programmes.csv` rows."""
    cluster = clusters(table, radius_m)
    t = table.set_index("title")
    per = per.assign(cluster=per["title"].map(cluster)).dropna(subset=["cluster"])
    # the cluster is named after its building with the most hours over all programmes
    by_title = per.groupby(["cluster", "title"])["hours"].sum().reset_index()
    main = by_title.sort_values("hours", ascending=False).drop_duplicates("cluster")
    main = main.set_index("cluster")["title"]
    per["building"] = per["cluster"].map(main)

    share = per.groupby(["programme", "building"])["hours"].sum().reset_index()
    share["share"] = share["hours"] / share.groupby("programme")["hours"].transform("sum")
    share = share[share["share"] >= min_share].copy()
    share["share"] = share["share"] / share.groupby("programme")["share"].transform("sum")
    share = share.sort_values(["programme", "share"], ascending=[True, False])
    share["building_id"] = share["building"].map(slug)

    used = share.groupby("building")["hours"].sum()
    b = pd.DataFrame({"title": used.index, "hours": used.round(1).to_numpy()})
    b["building_id"] = b["title"].map(slug)
    b["name"] = b["title"].map(names).fillna(b["title"])
    b["address"] = b["title"].map(t["address"])
    b["area"] = b["title"].map(t["site"])
    b["lon"] = b["title"].map(t["lon"]).round(6)
    b["lat"] = b["title"].map(t["lat"]).round(6)
    if b["building_id"].duplicated().any():
        raise StageValidationError("programmes: two buildings share an id")

    agg = share.groupby("programme").agg(
        buildings=("building_id", "|".join),
        shares=("share", lambda s: "|".join(f"{x:.3f}" for x in s)),
    )
    progs = meta.join(agg, how="inner").reset_index()
    progs["hours"] = progs["hours"].round(1)
    missing = sorted(set(campus.default_mix) - set(b["area"]))
    if missing:
        raise StageValidationError(f"programmes: default_mix areas without a building: {missing}")
    return (
        b[BUILDING_COLUMNS].sort_values("hours", ascending=False, ignore_index=True),
        progs[PROGRAMME_COLUMNS].sort_values("programme", ignore_index=True),
    )


def build(cfg_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = load_config(cfg_path)
    campus = load_campus(cfg_path, generated=False)
    if cfg.alma is None or campus.alma is None:
        raise StageValidationError("programmes: config or campus.yaml has no alma section")
    a = campus.alma
    sem_dir = cfg.data_dir / "raw" / "alma" / cfg.alma.semester_key
    sessions = alma.sessions_of(sorted(sem_dir.glob("*.html.gz")))
    mods, progs = alma_courses.load_courses(sem_dir / "courses")
    n_open = progs.loc[progs["open"], "unit_id"].nunique()
    mods, progs = mods[~mods["open"]], progs[~progs["open"]]
    mods = mods.rename(columns={"name": "name_module"})
    table = uni_buildings.load(cfg_path.parent / uni_buildings.OUT_NAME)
    hours = course_hours(sessions, campus, cfg.alma.semester)
    offered = programme_names(progs, list(a.degrees))
    names = code_names(mods, progs)
    comp = compulsory(mods, names, a.elective_modules)
    per, meta = programme_hours(hours, offered, comp, a.min_compulsory_h)
    names = display_names(sessions, campus)
    b, p = destinations(per, meta, table, campus, a.cluster_radius_m, a.min_share, names)
    log.info(
        "programmes: %d courses with hours (%d open to everyone, left out), %d codes matched, "
        "%d programmes (%d compulsory), %d buildings",
        hours["unit_id"].nunique(),
        n_open,
        len(names),
        len(p),
        int((p["basis"] == "compulsory").sum()),
        len(b),
    )
    return b, p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="reach_pipeline.programmes")
    ap.add_argument("action", choices=["build"])
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args(argv)
    path = Path(args.config)
    try:
        b, p = build(path)
    except (ExternalError, StageValidationError) as exc:
        log.error("%s", exc)
        return 1
    b.to_csv(path.parent / BUILDINGS_FILE, index=False)
    p.to_csv(path.parent / PROGRAMMES_FILE, index=False)
    log.info("wrote %s and %s", path.parent / BUILDINGS_FILE, path.parent / PROGRAMMES_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
