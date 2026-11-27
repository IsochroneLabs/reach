"""Typed configuration: pydantic models for config/config.yaml and `load_config`."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import date
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


class StudyArea(_Model):
    city_name: str = Field(min_length=1)
    admin_boundary: AdminBoundary
    routing_buffer_m: float = Field(gt=0)
    clip_bbox: tuple[float, float, float, float] | None = None

    @field_validator("clip_bbox")
    @classmethod
    def _bbox_ordered(cls, v: tuple[float, float, float, float] | None):
        if v is not None and not (v[0] < v[2] and v[1] < v[3]):
            raise ValueError("clip_bbox must be [min_lon, min_lat, max_lon, max_lat]")
        return v


class Districts(_Model):
    admin_levels: list[int] = Field(min_length=1)
    coverage_tolerance_pct: float = Field(ge=0)

    @field_validator("admin_levels")
    @classmethod
    def _unique_levels(cls, v: list[int]):
        if len(set(v)) != len(v):
            raise ValueError(f"admin_levels must be unique, got {v}")
        return v


class RoutingProfile(_Model):
    """One routing profile (arch. §6.1); transit profiles follow with T1."""

    engine: Literal["valhalla"]
    costing: Literal["pedestrian", "bicycle"]
    speed_kmh: float = Field(gt=0)
    costing_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("costing_options")
    @classmethod
    def _no_speed_option(cls, v: dict[str, Any]):
        # Speed has one source of truth: speed_kmh.
        clash = {"walking_speed", "cycling_speed"} & v.keys()
        if clash:
            raise ValueError(f"set the speed via speed_kmh, not {sorted(clash)}")
        return v


Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class TripWindow(_Model):
    """Weekday, local time, depart at / arrive by, and direction (meth. §5)."""

    weekday: Weekday
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    mode: Literal["depart_at", "arrive_by"]
    direction: Literal["to", "back"]


class DateRange(_Model):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    start: date = Field(alias="from")
    end: date = Field(alias="to")

    @model_validator(mode="after")
    def _ordered(self):
        if self.end < self.start:
            raise ValueError(f"date range {self.start} to {self.end}: 'to' before 'from'")
        return self

    def __contains__(self, day: date) -> bool:
        return self.start <= day <= self.end


class Calendar(_Model):
    """Holidays used to pick the reference date of each trip window (meth. §5)."""

    covered: DateRange
    public_holidays: list[date]
    school_holidays: list[DateRange]

    @model_validator(mode="after")
    def _inside_covered(self):
        outside = [str(d) for d in self.public_holidays if d not in self.covered]
        outside += [
            f"{r.start}..{r.end}"
            for r in self.school_holidays
            if r.start not in self.covered or r.end not in self.covered
        ]
        if outside:
            raise ValueError(f"holidays outside the covered range: {outside}")
        return self

    def is_holiday(self, day: date) -> bool:
        return day in self.public_holidays or any(day in r for r in self.school_holidays)


class Label(_Model):
    en: str = Field(min_length=1)
    de: str = Field(min_length=1)


def _check_tag_pairs(v: list[dict[str, str]]) -> list[dict[str, str]]:
    for tag in v:
        if len(tag) != 1 or not all(k and val for k, val in tag.items()):
            raise ValueError(f"each tag must be one non-empty key: value pair, got {tag}")
    return v


class DestinationType(_Model):
    """One destination type (meth. §3, docs/osm_tagging.md)."""

    label: Label
    # "osm": features matching `tags`; "campus": sites from config/campus.yaml.
    source: Literal["osm", "campus"] = "osm"
    tags: list[dict[str, str]] = Field(default_factory=list)
    # Conditions on the matched features, each one `key: value`; `;`-separated OSM values match
    # if any part matches. `require`: at least one must hold (empty = no restriction);
    # `exclude`: a feature matching any of them is dropped.
    require: list[dict[str, str]] = Field(default_factory=list)
    exclude: list[dict[str, str]] = Field(default_factory=list)
    location: Literal["point", "access_points"] | None = None
    # Nearest destinations stored per cell; null = all.
    nearest_k: int | None = Field(ge=1)
    trip_window: str
    fine_time_min: float = Field(gt=0)
    trips_per_week: float = Field(ge=0)

    @field_validator("tags", "require", "exclude")
    @classmethod
    def _one_pair_per_tag(cls, v: list[dict[str, str]]):
        return _check_tag_pairs(v)

    @model_validator(mode="after")
    def _source_fields(self):
        if self.source == "osm" and (not self.tags or self.location is None):
            raise ValueError("source osm needs tags and a location")
        if self.source == "campus" and (self.tags or self.location is not None):
            raise ValueError("source campus takes no tags or location (config/campus.yaml)")
        return self


class AccessPoints(_Model):
    spacing_m: float = Field(gt=0)
    max_points: int = Field(ge=1)
    walkable_highways: list[str] = Field(min_length=1)
    # Tolerance (m) of the park outline kept for display only (never used for routing).
    outline_simplify_m: float = Field(default=2.0, gt=0)


class Source(_Model):
    url: str = Field(pattern=r"^https://")
    md5_url: str | None = Field(default=None, pattern=r"^https://")
    licence: str = Field(min_length=1)
    # Zip archives: members unpacked next to the archive (DuckDB does not read inside zips).
    members: list[str] = Field(default_factory=list)


class Sources(_Model):
    osm: Source
    gtfs: Source
    zensus: Source
    # Optional (second cut, meth. §8).
    zensus_rent: Source | None = None


class Download(_Model):
    retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)
    timeout_s: float = Field(gt=0)


LonLat = tuple[float, float]


class TilesVerify(_Model):
    route: tuple[LonLat, LonLat]
    costing: Literal["pedestrian", "bicycle"]
    max_detour_factor: float = Field(ge=1.0)


class Tiles(_Model):
    elevation: bool
    verify: TilesVerify


class Valhalla(_Model):
    # null = only $VALHALLA_URL (.env); no fallback to a guessed local port (notes N5).
    url: str | None = Field(default=None, pattern=r"^https?://")
    concurrency: int = Field(ge=1)
    timeout_s: float = Field(gt=0)
    retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)
    max_matrix_pairs: int = Field(ge=1)


class TravelTimes(_Model):
    """Travel-time stage (S1.8, arch. §6.3)."""

    block_size_m: float = Field(gt=0)
    search_radius_m: float = Field(gt=0)


class ShareLimits(_Model):
    """A share (0..1) that warns below `warn_below` and fails below `fail_below`."""

    warn_below: float = Field(ge=0, le=1)
    fail_below: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _fail_not_above_warn(self):
        if self.fail_below > self.warn_below:
            raise ValueError("fail_below must be <= warn_below")
        return self


class Validation(_Model):
    population_tolerance_pct: float = Field(ge=0)
    official_population: int | None = Field(default=None, gt=0)
    min_scored_share: float = Field(ge=0, le=1)
    min_destinations_per_type: int = Field(ge=0)
    bike_not_slower_than_walk: ShareLimits


class Database(_Model):
    # Folder with roles.sql, migrations/ and run_schema.sql (relative to the working directory).
    sql_dir: Path
    connect_retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)


class Cleanup(_Model):
    keep_published_runs: int = Field(ge=1)


class Listings(_Model):
    """Daily listings job (arch. O24); off until the permission of the source is recorded."""

    enabled: bool
    source: Literal["wg_gesucht"]
    base_url: str = Field(pattern=r"^https://")
    search_paths: dict[Literal["wg_room", "studio", "flat"], str] = Field(min_length=1)
    max_search_pages: int = Field(ge=1)
    request_interval_s: float = Field(ge=10)
    timeout_s: float = Field(gt=0)
    user_agent: str = Field(min_length=1)
    retention_days: int = Field(ge=0)
    keep_snapshots: int = Field(ge=1)
    description_max_chars: int = Field(ge=0)
    title_max_chars: int = Field(ge=1)

    @field_validator("search_paths")
    @classmethod
    def _paged(cls, v: dict[str, str]):
        bad = sorted(k for k, path in v.items() if "{page}" not in path or not path.startswith("/"))
        if bad:
            raise ValueError(f"search paths need a leading / and a {{page}} placeholder: {bad}")
        return v


class Config(_Model):
    data_dir: Path
    study_area: StudyArea
    districts: Districts
    routing_profiles: dict[str, RoutingProfile] = Field(min_length=1)
    trip_windows: dict[str, TripWindow] = Field(min_length=1)
    calendar: Calendar
    destination_types: dict[str, DestinationType] = Field(min_length=1)
    access_points: AccessPoints
    sources: Sources
    download: Download
    tiles: Tiles
    valhalla: Valhalla
    travel_times: TravelTimes
    validation: Validation
    database: Database
    cleanup: Cleanup
    listings: Listings | None = None
    # Read and validated by reach_api.settings; kept as is here.
    api: dict[str, Any] = Field(default_factory=dict)

    @field_validator("routing_profiles", "trip_windows", "destination_types")
    @classmethod
    def _snake_case_ids(cls, v: dict[str, Any]):
        bad = sorted(k for k in v if not _ID_RE.match(k))
        if bad:
            raise ValueError(f"ids must be lower snake_case, got {bad}")
        return v

    @model_validator(mode="after")
    def _trip_windows_exist(self):
        unknown = sorted(
            f"{name}: {d.trip_window}"
            for name, d in self.destination_types.items()
            if d.trip_window not in self.trip_windows
        )
        if unknown:
            raise ValueError(f"destination_types: unknown trip windows {unknown}")
        return self


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path, seen: tuple[Path, ...] = ()) -> tuple[dict[str, Any], list[Path]]:
    """Merged data of `path` and its `extends` chain, plus the files read (child first)."""
    if path.resolve() in seen:
        raise ConfigError(f"circular 'extends' in {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    parent = data.pop("extends", None)
    if parent is None:
        return data, [path]
    if not isinstance(parent, str):
        raise ConfigError(f"{path}: 'extends' must be a file name, got {parent!r}")
    base, files = _read_yaml(path.parent / parent, (*seen, path.resolve()))
    return _deep_merge(base, data), [path, *files]


# Read by reach_api only; no pipeline stage depends on it (P5).
API_SECTION = "api"


def pipeline_sections() -> tuple[str, ...]:
    """Top-level config sections the pipeline uses: every field except `api`."""
    return tuple(name for name in Config.model_fields if name != API_SECTION)


def section_digest(cfg: Config, sections: Iterable[str]) -> str:
    """SHA-256 of the given top-level sections of the merged config (canonical JSON).

    A stage records the digest of the sections it uses, so a change elsewhere (e.g. in `api`)
    does not re-run it.
    """
    names = sorted(set(sections))
    unknown = sorted(set(names) - Config.model_fields.keys())
    if unknown:
        raise ConfigError(f"unknown config sections {unknown}")
    data = cfg.model_dump(mode="json", include=set(names))
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def config_files(path: str | Path) -> list[Path]:
    """All files a config is built from (the file and its `extends` chain), e.g. for checksums."""
    return _read_yaml(Path(path))[1]


def load_config(path: str | Path) -> Config:
    """Load and validate a config file; an `extends: <file>` key merges it over that file."""
    path = Path(path)
    data, _ = _read_yaml(path)
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        lines = [f"invalid config {path}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            lines.append(f"  {loc}: {err['msg']}")
        raise ConfigError("\n".join(lines)) from exc
