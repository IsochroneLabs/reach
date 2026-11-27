"""Campus areas and buildings, Mensas, university sports, programmes (meth. §3, §3.2, notes N31).

`config/campus.yaml` (next to the config file) holds the hand-made parts: campus **areas** (Tal,
Morgenstelle, …: display groups and the default mix), Mensas, university sports and the Alma
matching rules. Two generated, reviewed files next to it hold the rest (`reach_pipeline.programmes
build`): `campus_buildings.csv` (teaching buildings = the routed `campus_site` destinations) and
`programmes.csv` (Alma programmes → buildings with shares). Points are [lon, lat]; `destinations`
turns them into destinations in EPSG:25832, and `match_osm` reports how far each one is from an OSM
feature of the university (V3).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from reach_pipeline.errors import ConfigError

METRIC_CRS = "EPSG:25832"
CAMPUS_FILE = "campus.yaml"
BUILDINGS_FILE = "campus_buildings.csv"
PROGRAMMES_FILE = "programmes.csv"
# section → destination type of config.yaml (source: campus); buildings are the campus sites.
SECTION_TYPE = {
    "buildings": "campus_site",
    "mensas": "mensa",
    "university_sports": "university_sports",
}
# OSM features that confirm a campus point (V3): university grounds and buildings, canteens.
OSM_EXPRESSIONS = [
    "nwr/amenity=university,college,canteen",
    "nwr/building=university",
    "nwr/leisure=sports_centre",
]
# degree as Alma writes it → label shown to the student
DEGREE_LABELS = dict[str, dict[str, str]]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Place(_Model):
    name: str = Field(min_length=1)
    point: tuple[float, float]


class Building(Place):
    """A teaching building (official buildings closer than `cluster_radius_m` merged)."""

    address: str = ""
    area: str = Field(min_length=1)
    hours: float = Field(ge=0)  # weekly session hours of all programmes that count it


class Programme(_Model):
    """An Alma programme (degree + subject as major) and the buildings of its sessions."""

    degree: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    basis: str = Field(pattern=r"^(compulsory|all|override)$")
    buildings: list[str] = Field(min_length=1)
    shares: list[float] | None = None  # None = equal weights
    courses: int = Field(default=0, ge=0)
    hours: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _shares(self):
        bad = self.shares is not None and (
            len(self.shares) != len(self.buildings) or abs(sum(self.shares) - 1) > 0.01
        )
        if bad:
            raise ValueError("shares: one per building, adding up to 1")
        return self


class AlmaMatch(_Model):
    """Rules that turn Alma courses into programme × building hours (`programmes build`, N31)."""

    # official building (title in config/university_buildings.csv) → regexes on Alma's building
    # name (notes N30)
    building_addresses: dict[str, list[str]] = Field(min_length=1)
    max_session_h: float = Field(gt=0)
    degrees: DEGREE_LABELS = Field(min_length=1)  # offered degrees → {en, de}
    elective_modules: list[str] = Field(min_length=1)  # regexes on module names
    min_compulsory_h: float = Field(ge=0)
    cluster_radius_m: float = Field(gt=0)
    min_share: float = Field(ge=0, lt=1)


class Campus(_Model):
    match_radius_m: float = Field(gt=0)
    areas: dict[str, Place] = Field(min_length=1)
    mensas: dict[str, Place] = Field(default_factory=dict)
    university_sports: dict[str, Place] = Field(default_factory=dict)
    default_mix: dict[str, float] = Field(min_length=1)  # area → share without a programme
    alma: AlmaMatch | None = None
    # official building title → [lon, lat] where the OSM address index has no such address (N30)
    building_points: dict[str, tuple[float, float]] = Field(default_factory=dict)
    # programme id → buildings for programmes Alma does not show (basis "override", N31)
    programme_overrides: dict[str, Programme] = Field(default_factory=dict)
    # generated (campus_buildings.csv, programmes.csv); empty while they are being built
    buildings: dict[str, Building] = Field(default_factory=dict)
    programmes: dict[str, Programme] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _known(self):
        unknown = sorted(set(self.default_mix) - set(self.areas))
        if unknown:
            raise ValueError(f"default_mix names unknown areas: {unknown}")
        if abs(sum(self.default_mix.values()) - 1) > 1e-6:
            raise ValueError("default_mix shares must add up to 1")
        if self.buildings:
            named = {b for p in self.programmes.values() for b in p.buildings}
            missing = sorted(named - set(self.buildings))
            if missing:
                raise ValueError(f"programmes name unknown buildings: {missing}")
            areas = sorted({b.area for b in self.buildings.values()} - set(self.areas))
            if areas:
                raise ValueError(f"buildings name unknown areas: {areas}")
        return self

    def default_shares(self) -> dict[str, float]:
        """Building → share without a programme: the area's `default_mix` share, split over the
        area's buildings by their session hours (notes N31)."""
        b = pd.DataFrame(
            [(k, v.area, v.hours) for k, v in self.buildings.items()],
            columns=["id", "area", "hours"],
        )
        b = b[b["area"].isin(list(self.default_mix))]
        b["share"] = (
            b["area"].map(self.default_mix)
            * b["hours"]
            / b.groupby("area")["hours"].transform("sum")
        )
        return {k: float(v) for k, v in zip(b["id"], b["share"], strict=True) if v > 0}


def _split(value: object, cast=str) -> list:
    return [cast(x) for x in str(value).split("|")] if isinstance(value, str) and value else []


def _generated(directory: Path, overrides: dict[str, Programme]) -> dict[str, object]:
    bpath, ppath = directory / BUILDINGS_FILE, directory / PROGRAMMES_FILE
    if not bpath.exists() or not ppath.exists():
        raise ConfigError(
            f"{bpath.name} or {ppath.name} missing in {directory}; "
            "run `uv run python -m reach_pipeline.programmes build` (notes N31)"
        )
    b = pd.read_csv(bpath, keep_default_na=False)
    p = pd.read_csv(ppath, keep_default_na=False)
    buildings = {
        r.building_id: Building(
            name=r.name, point=(r.lon, r.lat), address=r.address, area=r.area, hours=r.hours
        )
        for r in b.itertuples()
    }
    programmes = {
        r.programme: Programme(
            degree=r.degree,
            subject=r.subject,
            basis=r.basis,
            buildings=_split(r.buildings),
            shares=_split(r.shares, float) or None,
            courses=int(r.courses),
            hours=float(r.hours),
        )
        for r in p.itertuples()
    }
    return {"buildings": buildings, "programmes": programmes | overrides}


def load_campus(config_path: str | Path, generated: bool = True) -> Campus:
    """`campus.yaml` next to the config file, with the generated buildings and programmes unless
    `generated` is False (used while building them)."""
    path = Path(config_path).parent / CAMPUS_FILE
    if not path.exists():
        raise ConfigError(f"{path} not found")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        base = Campus.model_validate(raw)
        if not generated:
            return base
        return Campus.model_validate(raw | _generated(path.parent, base.programme_overrides))
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def destinations(campus: Campus) -> gpd.GeoDataFrame:
    """One destination per teaching building, Mensa and university sports place."""
    rows = [
        (f"{dtype}:{key}", dtype, place.name, key, place.point)
        for section, dtype in SECTION_TYPE.items()
        for key, place in getattr(campus, section).items()
    ]
    ids, types, names, keys, points = zip(*rows, strict=True)
    xy = np.array(points, dtype=float)
    return gpd.GeoDataFrame(
        {
            "destination_id": ids,
            "destination_type": types,
            "name": names,
            "osm_id": [f"campus:{k}" for k in keys],
        },
        geometry=gpd.points_from_xy(xy[:, 0], xy[:, 1]),
        crs="EPSG:4326",
    ).to_crs(METRIC_CRS)


def university_mask(features: gpd.GeoDataFrame) -> pd.Series:
    """Features of `OSM_EXPRESSIONS` (any of them)."""

    def col(key: str) -> pd.Series:
        if key not in features.columns:
            return pd.Series("", index=features.index)
        return features[key].fillna("").astype(str)

    return (
        col("amenity").isin(["university", "college", "canteen"])
        | (col("building") == "university")
        | (col("leisure") == "sports_centre")
    )


def match_osm(dest: gpd.GeoDataFrame, features: gpd.GeoDataFrame) -> np.ndarray:
    """Distance (m) from each campus destination to the nearest university OSM feature (inf if
    there is none)."""
    if features.empty:
        return np.full(len(dest), np.inf)
    (idx, _), dist = features.sindex.nearest(dest.geometry, return_distance=True, return_all=False)
    out = np.full(len(dest), np.inf)
    out[idx] = dist
    return out
