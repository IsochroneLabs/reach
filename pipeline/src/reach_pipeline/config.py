"""Typed configuration: pydantic models for config/config.yaml and `load_config`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from reach_pipeline.errors import ConfigError


class _Model(BaseModel):
    # Unknown keys are typos, not extensions.
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdminBoundary(_Model):
    admin_level: int
    ags: str = Field(min_length=1)


class UrbanBoundary(_Model):
    landuse: list[str] = Field(min_length=1)
    closing_m: float = Field(ge=0)
    min_part_area_m2: float = Field(ge=0)


class StudyArea(_Model):
    city_name: str = Field(min_length=1)
    admin_boundary: AdminBoundary
    urban_boundary: UrbanBoundary
    routing_buffer_m: float = Field(gt=0)
    clip_bbox: tuple[float, float, float, float] | None = None

    @field_validator("clip_bbox")
    @classmethod
    def _bbox_ordered(cls, v: tuple[float, float, float, float] | None):
        if v is not None and not (v[0] < v[2] and v[1] < v[3]):
            raise ValueError("clip_bbox must be [min_lon, min_lat, max_lon, max_lat]")
        return v


class Districts(_Model):
    admin_level: int | None = None


class TimeBudgets(_Model):
    facilities: float = Field(gt=0)
    transit: float = Field(gt=0)


class Profile(_Model):
    costing: Literal["pedestrian", "bicycle"]
    speed_kmh: float = Field(gt=0)
    costing_options: dict[str, Any] = Field(default_factory=dict)
    max_speed_factor: float = Field(ge=1.0)
    prefilter_margin_m: float = Field(ge=0)
    transit: bool

    @field_validator("costing_options")
    @classmethod
    def _no_speed_option(cls, v: dict[str, Any]):
        # Speed has one source of truth: speed_kmh.
        clash = {"walking_speed", "cycling_speed"} & v.keys()
        if clash:
            raise ValueError(f"set the speed via speed_kmh, not {sorted(clash)}")
        return v

    def prefilter_reach_m(self, budget_min: float) -> float:
        """Straight-line prefilter reach in metres (decision O20)."""
        metres_per_min = self.speed_kmh * 1000 / 60
        return metres_per_min * self.max_speed_factor * budget_min + self.prefilter_margin_m


class Category(_Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    k: int = Field(ge=1)
    tags: list[dict[str, str]] = Field(min_length=1)
    location: Literal["point", "access_points"]

    @field_validator("tags")
    @classmethod
    def _one_pair_per_tag(cls, v: list[dict[str, str]]):
        for tag in v:
            if len(tag) != 1 or not all(k and val for k, val in tag.items()):
                raise ValueError(f"each tag must be one non-empty key: value pair, got {tag}")
        return v


class AccessPoints(_Model):
    spacing_m: float = Field(gt=0)
    max_points: int = Field(ge=1)


class TransitClass(_Model):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    name: str = Field(alias="class", min_length=1)
    lower: int = Field(ge=0)
    upper: int | None

    @model_validator(mode="after")
    def _lower_le_upper(self):
        if self.upper is not None and self.upper < self.lower:
            raise ValueError(f"transit class {self.name}: upper < lower")
        return self


class Source(_Model):
    url: str = Field(pattern=r"^https://")
    md5_url: str | None = Field(default=None, pattern=r"^https://")
    licence: str = Field(min_length=1)


class Sources(_Model):
    osm: Source
    gtfs: Source
    zensus: Source


class Tiles(_Model):
    elevation: bool


class Validation(_Model):
    population_tolerance_pct: float = Field(ge=0)
    official_population: int | None = Field(default=None, gt=0)
    min_facilities_per_category: int = Field(ge=0)


class Config(_Model):
    data_dir: Path
    study_area: StudyArea
    districts: Districts
    time_budgets_min: TimeBudgets
    profiles: dict[str, Profile] = Field(min_length=1)
    categories: list[Category] = Field(min_length=1)
    access_points: AccessPoints
    transit_classes: list[TransitClass] = Field(min_length=1)
    sources: Sources
    tiles: Tiles
    validation: Validation

    @field_validator("categories")
    @classmethod
    def _unique_category_ids(cls, v: list[Category]):
        ids = [c.id for c in v]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate category ids: {dupes}")
        return v

    @field_validator("transit_classes")
    @classmethod
    def _transit_bounds_increasing(cls, v: list[TransitClass]):
        for prev, cur in zip(v, v[1:], strict=False):
            if prev.upper is None or cur.lower != prev.upper + 1:
                raise ValueError(
                    f"transit classes must increase without gaps: {prev.name} ends at "
                    f"{prev.upper}, {cur.name} starts at {cur.lower}"
                )
        if v[-1].upper is not None:
            raise ValueError("the last transit class must be open-ended (upper: null)")
        return v

    @model_validator(mode="after")
    def _buffer_covers_reach(self):
        # Routing buffer >= largest prefilter reach of all profiles (O20).
        budget = self.time_budgets_min.facilities
        reach = {name: p.prefilter_reach_m(budget) for name, p in self.profiles.items()}
        name, largest = max(reach.items(), key=lambda item: item[1])
        if self.study_area.routing_buffer_m < largest:
            raise ValueError(
                f"study_area.routing_buffer_m ({self.study_area.routing_buffer_m:.0f} m) is "
                f"smaller than the prefilter reach of profile {name} ({largest:.0f} m)"
            )
        return self


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    path = path.resolve()
    if path in seen:
        raise ConfigError(f"circular 'extends' in {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    parent = data.pop("extends", None)
    if parent is None:
        return data
    return _deep_merge(_read_yaml(path.parent / parent, (*seen, path)), data)


def load_config(path: str | Path) -> Config:
    """Load and validate a config file; an `extends: <file>` key merges it over that file."""
    path = Path(path)
    data = _read_yaml(path)
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        lines = [f"invalid config {path}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            lines.append(f"  {loc}: {err['msg']}")
        raise ConfigError("\n".join(lines)) from exc
