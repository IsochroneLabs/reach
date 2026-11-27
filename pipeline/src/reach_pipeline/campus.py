"""Campus sites, Mensas, university sports and programmes (`config/campus.yaml`, meth. §3, §3.2).

The file sits next to the config file (`campus.yaml` in the same directory). Points are
approximate [lon, lat]; `destinations` turns them into destinations in EPSG:25832, and
`match_osm` reports how far each one is from an OSM feature of the university (V3).
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
# campus.yaml section → destination type of config.yaml (source: campus).
SECTION_TYPE = {"sites": "campus_site", "mensas": "mensa", "university_sports": "university_sports"}
# OSM features that confirm a campus point (V3): university grounds and buildings, canteens.
OSM_EXPRESSIONS = [
    "nwr/amenity=university,college,canteen",
    "nwr/building=university",
    "nwr/leisure=sports_centre",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Place(_Model):
    name: str = Field(min_length=1)
    point: tuple[float, float]


class Programme(_Model):
    label: dict[str, str]
    sites: list[str] = Field(min_length=1)
    # Optional share of each site in the campus time (Alma session hours, notes N24); None = equal.
    shares: list[float] | None = None

    @model_validator(mode="after")
    def _shares(self):
        bad = self.shares is not None and (
            len(self.shares) != len(self.sites) or abs(sum(self.shares) - 1) > 0.01
        )
        if bad:
            raise ValueError("shares: one per site, adding up to 1")
        return self


class AlmaMatch(_Model):
    """Patterns that turn Alma sessions into programme × site hours (F3.3)."""

    building_sites: dict[str, list[str]] = Field(min_length=1)  # site → building regexes
    programme_numbers: dict[str, list[str]] = Field(min_length=1)  # programme → number regexes
    max_session_h: float = Field(gt=0)


class Campus(_Model):
    match_radius_m: float = Field(gt=0)
    sites: dict[str, Place] = Field(min_length=1)
    mensas: dict[str, Place] = Field(default_factory=dict)
    university_sports: dict[str, Place] = Field(default_factory=dict)
    default_mix: dict[str, float] = Field(min_length=1)
    programmes: dict[str, Programme] = Field(min_length=1)
    alma: AlmaMatch | None = None

    @model_validator(mode="after")
    def _known_sites(self):
        named = {s for p in self.programmes.values() for s in p.sites} | set(self.default_mix)
        unknown = sorted(named - set(self.sites))
        if unknown:
            raise ValueError(f"programmes or default_mix name unknown sites: {unknown}")
        if abs(sum(self.default_mix.values()) - 1) > 1e-6:
            raise ValueError("default_mix shares must add up to 1")
        return self


def load_campus(config_path: str | Path) -> Campus:
    """`campus.yaml` next to the config file (a config that `extends` another uses the base's)."""
    path = Path(config_path).parent / CAMPUS_FILE
    if not path.exists():
        raise ConfigError(f"{path} not found")
    try:
        return Campus.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def destinations(campus: Campus) -> gpd.GeoDataFrame:
    """One destination per site, Mensa and university sports place."""
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
