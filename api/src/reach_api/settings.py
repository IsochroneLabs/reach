"""Settings: URLs and DSN from the environment, tunable values from `config/config.yaml`.

The API reads the `api` section plus the few pipeline keys it must share with the pipeline
(category names, transit budget, prefilter factor and margin per profile, Valhalla matrix
limit), so live
matrices use the same prefilter as the `count` stage (arch. §6.5 rule 8). Costing options and
speeds come from `current.profiles` of the published run, not from here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    """Environment variables (`.env.example`)."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url_api: str = Field(min_length=1)
    valhalla_url: str = Field(min_length=1)
    reach_config: Path = Path("config/config.yaml")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Shared(BaseModel):
    """Pipeline sections the API reads only partly."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Isochrone(_Model):
    contours_min: list[float] = Field(min_length=1, max_length=4)
    generalize_m: float = Field(ge=0)
    denoise: float = Field(ge=0, le=1)


class Cache(_Model):
    live_entries: int = Field(ge=1)
    expansion_entries: int = Field(ge=1)
    read_entries: int = Field(ge=1)


class RateLimit(_Model):
    burst: int = Field(ge=1)
    per_minute: float = Field(gt=0)
    max_clients: int = Field(ge=1)


class LiveValhalla(_Model):
    concurrency: int = Field(ge=1)
    timeout_s: float = Field(gt=0)
    retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)


class DbPool(_Model):
    min_size: int = Field(ge=0)
    max_size: int = Field(ge=1)


class Api(_Model):
    # Not read since W3 (clicks are accepted inside the city boundary, arch. §6.5 rule 12); kept
    # so the config still loads until the key is removed (notes N3).
    boundary_margin_m: float | None = Field(default=None, ge=0)
    isochrone: Isochrone
    cache: Cache
    rate_limit: RateLimit
    trusted_proxies: list[str]
    resolve_interval_s: float = Field(ge=0)
    valhalla: LiveValhalla
    live_matrix: LiveValhalla
    db_pool: DbPool


class Prefilter(_Shared):
    max_speed_factor: float = Field(ge=1.0)
    prefilter_margin_m: float = Field(ge=0)


class CategoryName(_Shared):
    id: str
    name: str


class TimeBudgets(_Shared):
    transit: float = Field(gt=0)


class ValhallaLimits(_Shared):
    max_matrix_pairs: int = Field(ge=1)


class Config(_Shared):
    api: Api
    profiles: dict[str, Prefilter]
    categories: list[CategoryName]
    time_budgets_min: TimeBudgets
    valhalla: ValhallaLimits

    def prefilter_reach_m(self, profile_id: str, speed_kmh: float, budget_min: float) -> float:
        """Straight-line prefilter reach as in the pipeline (O20, `Profile.prefilter_reach_m`).

        Speed and budget come from `current.profiles`; factor and margin from the config.
        """
        p = self.profiles[profile_id]
        return speed_kmh * 1000 / 60 * p.max_speed_factor * budget_min + p.prefilter_margin_m


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    # Same `extends` semantics as reach_pipeline.config (nested mappings merged, lists replaced).
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parent = data.pop("extends", None)
    return _deep_merge(_read_yaml(path.parent / parent), data) if parent else data


def load_config(path: str | Path) -> Config:
    """Validated API view of a config file; raises on a missing or invalid `api` section."""
    return Config.model_validate(_read_yaml(Path(path)))
