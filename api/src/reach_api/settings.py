"""Settings: URLs, DSN and build SHA from the environment; tunable values from the `api` section
of `config/config.yaml` (arch. §9). The pipeline sections are validated by reach_pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    """Environment variables (`.env.example`). The URLs are checked when the app starts, so the
    app object can be imported without them (tests, OpenAPI export)."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url_api: str | None = None
    valhalla_url: str | None = None
    reach_config: Path = Path("config/config.yaml")
    # Commit SHA of the image, set at build time (infra/api.Dockerfile); "dev" locally.
    build_sha: str = "dev"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Cache(_Model):
    fit_entries: int = Field(ge=1)


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


class Fit(_Model):
    """Parameters of s = 1 / (1 + (T / (a·t))^p) (methodology §6, settled 27 Nov 2026)."""

    a: float = Field(gt=0)
    p: float = Field(gt=0)


class AddressSearch(_Model):
    limit: int = Field(ge=1, le=50)
    min_chars: int = Field(ge=1)


class Api(_Model):
    cors_origins: list[str]
    cache: Cache
    rate_limit: RateLimit
    trusted_proxies: list[str]
    resolve_interval_s: float = Field(ge=0)
    valhalla: LiveValhalla
    db_pool: DbPool
    fit: Fit
    address_search: AddressSearch
    # Seconds between checks whether `current` moved to another run (then the model reloads).
    model_refresh_s: float = Field(ge=0)


class Config(BaseModel):
    """The API view of a config file: only `api`; other sections are ignored here."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    api: Api


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


def label_names(path: str | Path) -> dict[str, dict[str, str]]:
    """Display names of brands, groups and categories (`grocery:edeka` → {en, de}) from the
    `destination_labels` section; religions are named by their OSM value."""
    cfg = _read_yaml(Path(path)).get("destination_labels") or {}

    def both(label: Any, key: str) -> dict[str, str]:
        if isinstance(label, dict):
            return {"en": label.get("en", key), "de": label.get("de", label.get("en", key))}
        return {"en": str(label or key), "de": str(label or key)}

    out = {}
    g = cfg.get("grocery") or {}
    for section in ("brands", "groups"):
        for key, v in (g.get(section) or {}).items():
            out[f"grocery:{key}"] = both(v.get("label"), key)
    for dtype in ("sport", "hobby"):
        for key, v in ((cfg.get(dtype) or {}).get("categories") or {}).items():
            out[f"{dtype}:{key}"] = both(v.get("label"), key)
    return out


def personas(path: str | Path) -> dict[str, Any]:
    """`personas.yaml` next to the config file (raw)."""
    file = Path(path).parent / "personas.yaml"
    if not file.exists():
        return {}
    return yaml.safe_load(file.read_text(encoding="utf-8")) or {}
