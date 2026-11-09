"""Typed configuration: pydantic models for config/config.yaml and `load_config`."""

from __future__ import annotations

import hashlib
import json
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
    admin_levels: list[int] = Field(min_length=1)
    coverage_tolerance_pct: float = Field(ge=0)

    @field_validator("admin_levels")
    @classmethod
    def _unique_levels(cls, v: list[int]):
        if len(set(v)) != len(v):
            raise ValueError(f"admin_levels must be unique, got {v}")
        return v


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


# `thresholds.category` uses this id for the transit classes (data contract).
TRANSIT_CATEGORY = "transit"


class Category(_Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    k: int = Field(ge=1)
    tags: list[dict[str, str]] = Field(min_length=1)
    location: Literal["point", "access_points"]

    @field_validator("id")
    @classmethod
    def _not_transit(cls, v: str):
        if v == TRANSIT_CATEGORY:
            raise ValueError(f"category id {v!r} is reserved for the transit classes")
        return v

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
    walkable_highways: list[str] = Field(min_length=1)


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


Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class ReferenceDay(_Model):
    weekday: Weekday
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
    # Zip archives: members unpacked next to the archive (DuckDB does not read inside zips).
    members: list[str] = Field(default_factory=list)


class Sources(_Model):
    osm: Source
    gtfs: Source
    zensus: Source


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
    # null = only $VALHALLA_URL (.env); no fallback to a guessed local port (notes N9).
    url: str | None = Field(default=None, pattern=r"^https?://")
    concurrency: int = Field(ge=1)
    timeout_s: float = Field(gt=0)
    retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)
    max_matrix_pairs: int = Field(ge=1)


class Evidence(_Model):
    widen_factor: float = Field(ge=1.0)
    widen_m: float = Field(ge=0)
    band_edges: list[float] = Field(min_length=2)
    sample_points: dict[str, LonLat] = Field(min_length=1)

    @field_validator("band_edges")
    @classmethod
    def _increasing_fractions(cls, v: list[float]):
        if any(b <= a for a, b in zip(v, v[1:], strict=False)) or v[0] < 0 or v[-1] > 1:
            raise ValueError(f"band_edges must increase within 0..1, got {v}")
        return v


class Count(_Model):
    block_size_m: float = Field(gt=0)
    evidence: Evidence


class RecommendOverride(_Model):
    """Per-profile replacement of a `recommend` value (only the keys set here differ)."""

    # Coarser candidate grid for this profile; a multiple of recommend.candidate_spacing_m.
    candidate_spacing_m: int = Field(ge=100)


class Recommend(_Model):
    """Recommender (methodology §5, arch. §6.4): candidates, catchments, greedy selection."""

    # Profiles the recommender runs for; empty = no recommendations in this run.
    profiles: list[str]
    top_n: int = Field(ge=1)
    min_gain: float = Field(ge=0)
    candidate_spacing_m: int = Field(ge=100)
    group_size_m: float = Field(gt=0)
    exclude_tags: list[dict[str, str]]
    # boundary=protected_area polygons excluded only with one of these protect_class values.
    exclude_protect_classes: list[str]
    # Profile id -> overrides (e.g. a coarser candidate grid for the heavy cycling matrix).
    profile_overrides: dict[str, RecommendOverride] = {}

    def spacing_m(self, profile_id: str) -> int:
        """Candidate spacing for the profile (override, else `candidate_spacing_m`)."""
        override = self.profile_overrides.get(profile_id)
        return override.candidate_spacing_m if override else self.candidate_spacing_m

    @field_validator("candidate_spacing_m")
    @classmethod
    def _on_the_grid(cls, v: int):
        if v % 100:
            raise ValueError(f"candidate_spacing_m must be a multiple of 100 (grid), got {v}")
        return v

    @field_validator("profiles")
    @classmethod
    def _unique_profiles(cls, v: list[str]):
        if len(set(v)) != len(v):
            raise ValueError(f"recommend.profiles must be unique, got {v}")
        return v

    @model_validator(mode="after")
    def _overrides_on_the_grid(self):
        for pid, o in self.profile_overrides.items():
            if o.candidate_spacing_m % self.candidate_spacing_m:
                raise ValueError(
                    f"recommend.profile_overrides.{pid}.candidate_spacing_m must be a multiple "
                    f"of candidate_spacing_m ({self.candidate_spacing_m}), got "
                    f"{o.candidate_spacing_m}"
                )
        return self

    @field_validator("exclude_tags")
    @classmethod
    def _one_pair_per_tag(cls, v: list[dict[str, str]]):
        if any(len(tag) != 1 for tag in v):
            raise ValueError("each exclude_tags entry must be exactly one key: value pair")
        return v


class Monotonic(_Model):
    """Expected order of two profiles: counts (and departures) of `higher` >= those of `lower`."""

    higher: str
    lower: str
    # Share of cells (0..1) with at least one violation above which the check warns / fails;
    # fail_above null = the check never fails (different costings, no guarantee).
    warn_above: float = Field(ge=0, le=1)
    fail_above: float | None = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _fail_not_below_warn(self):
        if self.fail_above is not None and self.fail_above < self.warn_above:
            raise ValueError(f"{self.higher} >= {self.lower}: fail_above < warn_above")
        return self


class RouteCheck(_Model):
    """Sample of reachable cell × facility pairs whose matrix time is compared with /route."""

    pairs_per_profile: int = Field(ge=0)
    # Share of the sample drawn from pairs with time_s >= near_budget_share × budget, where a
    # deviation can change the count.
    near_budget_share: float = Field(ge=0, le=1)
    warn_max_abs_s: float = Field(ge=0)


class FalseNegativeCheck(_Model):
    """Sample of cell × facility pairs within the prefilter reach that are not in `reachable`;
    a /route time within the budget is a false negative (notes N9)."""

    pairs_per_category: int = Field(ge=0)
    # Share of false negatives among the sampled pairs (0..1, all profiles and categories)
    # above which the check warns / fails.
    warn_above: float = Field(ge=0, le=1)
    fail_above: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _fail_not_below_warn(self):
        if self.fail_above < self.warn_above:
            raise ValueError("fail_above must be >= warn_above")
        return self


class BudgetFlips(_Model):
    """Pairs on which matrix and /route lie on different sides of the budget (methodology V10),
    from the samples of `route_check` and `false_negatives`; warns only."""

    # Share of routed pairs (0..1) per profile and direction above which the check warns.
    warn_above: float = Field(ge=0, le=1)


class ResultsValidation(_Model):
    monotonic: list[Monotonic] = Field(default_factory=list)
    route_check: RouteCheck
    false_negatives: FalseNegativeCheck
    budget_flips: BudgetFlips


class Validation(_Model):
    population_tolerance_pct: float = Field(ge=0)
    official_population: int | None = Field(default=None, gt=0)
    min_scored_share: float = Field(ge=0, le=1)
    min_facilities_per_category: int = Field(ge=0)
    results: ResultsValidation


class Database(_Model):
    # Folder with roles.sql, migrations/ and run_schema.sql (relative to the working directory).
    sql_dir: Path
    connect_retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)


class Cleanup(_Model):
    keep_published_runs: int = Field(ge=1)


class Config(_Model):
    data_dir: Path
    study_area: StudyArea
    districts: Districts
    time_budgets_min: TimeBudgets
    profiles: dict[str, Profile] = Field(min_length=1)
    categories: list[Category] = Field(min_length=1)
    access_points: AccessPoints
    transit_classes: list[TransitClass] = Field(min_length=1)
    reference_day: ReferenceDay
    sources: Sources
    download: Download
    tiles: Tiles
    valhalla: Valhalla
    count: Count
    recommend: Recommend
    validation: Validation
    database: Database
    cleanup: Cleanup
    # Read and validated by reach_api.settings; kept as is here.
    api: dict[str, Any] = Field(default_factory=dict)

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
    def _monotonic_profiles_exist(self):
        for pair in self.validation.results.monotonic:
            unknown = sorted({pair.higher, pair.lower} - self.profiles.keys())
            if unknown:
                raise ValueError(f"validation.results.monotonic: unknown profiles {unknown}")
        return self

    @model_validator(mode="after")
    def _recommend_profiles_exist(self):
        unknown = sorted(set(self.recommend.profiles) - self.profiles.keys())
        if unknown:
            raise ValueError(f"recommend.profiles: unknown profiles {unknown}")
        return self

    @model_validator(mode="after")
    def _buffer_covers_reach(self):
        # Routing buffer >= largest prefilter reach of all profiles and their budgets (O20).
        budgets = self.time_budgets_min
        reach = {
            name: p.prefilter_reach_m(
                max(budgets.facilities, budgets.transit) if p.transit else budgets.facilities
            )
            for name, p in self.profiles.items()
        }
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
