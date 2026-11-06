"""Typed `config/experiments.yaml` (validation experiments, methodology §6)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from reach_pipeline.errors import ConfigError

DEFAULT_PATH = "config/experiments.yaml"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class V01(_Model):
    profiles: list[str] = Field(min_length=1)
    sample_cells: int = Field(ge=1)
    generalize_m: float = Field(ge=0)
    denoise: float = Field(ge=0, le=1)
    barrier_tags: list[dict[str, str]]


class V02(_Model):
    base_url: str = Field(pattern=r"^https://")
    childcare_list: str
    school_lists: list[str]
    request_interval_s: float = Field(ge=0)
    timeout_s: float = Field(gt=0)
    user_agent: str = Field(min_length=1)
    match_radius_m: float = Field(gt=0)
    name_min_jaccard: float = Field(gt=0, le=1)


class V03(_Model):
    profile: str
    categories: list[str] = Field(min_length=1)
    remove_share: float = Field(gt=0, lt=1)
    repetitions: int = Field(ge=1)
    hit_radius_m: list[float] = Field(min_length=1)


class V04(_Model):
    profiles: list[str] = Field(min_length=1)
    n_sites: list[int] = Field(min_length=1)
    time_limit_s: float = Field(gt=0)


class V05(_Model):
    base_profile: str
    k_shifts: list[int]
    budgets_from_reachable: list[float]
    budgets_recount: list[float]
    top_districts: int = Field(ge=1)
    near_radius_m: float = Field(gt=0)


class V06(_Model):
    profiles: list[str] = Field(min_length=1)
    residential_buildings: list[str] = Field(min_length=1)


class V08(_Model):
    profile: str
    neighbour_distance_m: float = Field(gt=0)
    permutations: int = Field(ge=99)
    significance: float = Field(gt=0, lt=1)


class V10(_Model):
    profiles: list[str] = Field(min_length=1)
    pairs_per_profile: int = Field(ge=1)
    near_budget_share: float = Field(ge=0, le=1)
    false_negative_pairs_per_category: int = Field(ge=1)


class V11(_Model):
    profiles: list[str] = Field(min_length=1)
    port: int = Field(ge=1024, le=65535)
    container_name: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    threads: int = Field(ge=1)
    start_timeout_s: float = Field(gt=0)
    memory_sample_s: float = Field(gt=0)
    max_grade_values: list[float | None] = Field(min_length=1)


class Settings(_Model):
    seed: int
    results_dir: str
    reference_dir: str
    v01: V01
    v02: V02
    v03: V03
    v04: V04
    v05: V05
    v06: V06
    v08: V08
    v10: V10
    v11: V11

    def profiles_used(self) -> set[str]:
        return {
            *self.v01.profiles,
            self.v03.profile,
            *self.v04.profiles,
            self.v05.base_profile,
            *self.v06.profiles,
            self.v08.profile,
            *self.v10.profiles,
            *self.v11.profiles,
        }


def load_settings(path: str | Path = DEFAULT_PATH) -> Settings:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Settings.model_validate(data)
    except FileNotFoundError as exc:
        raise ConfigError(f"experiments config not found: {path}") from exc
    except (yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(f"invalid experiments config {path}: {exc}") from exc
