"""Config loading: the repo config is valid; every invalid case fails with a clear message."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from reach_pipeline.config import config_files, load_config
from reach_pipeline.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config" / "config.yaml"


@pytest.fixture
def base() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict[str, Any], name: str = "config.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_repo_config_loads() -> None:
    cfg = load_config(CONFIG)
    assert {c.id for c in cfg.categories} >= {"grocery", "pharmacy", "school"}
    assert cfg.profiles["walking_339"].prefilter_reach_m(15) == pytest.approx(847.5)
    assert cfg.profiles["cycling_15"].prefilter_reach_m(15) == pytest.approx(3750)


def test_test_clip_extends_repo_config() -> None:
    cfg = load_config(REPO / "config" / "test_clip.yaml")
    assert cfg.tiles.elevation is False
    assert cfg.study_area.clip_bbox is not None
    # untouched keys come from config.yaml
    assert cfg.study_area.routing_buffer_m == load_config(CONFIG).study_area.routing_buffer_m


def _set(data: dict[str, Any], dotted: str, value: Any) -> dict[str, Any]:
    data = copy.deepcopy(data)
    *parents, last = dotted.split(".")
    node: Any = data
    for key in parents:
        node = node[int(key)] if isinstance(node, list) else node[key]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return data


@pytest.mark.parametrize(
    ("dotted", "value", "expected"),
    [
        ("profiles.walking_339.speed_kmh", 0, "profiles.walking_339.speed_kmh"),
        ("profiles.cycling_15.speed_kmh", -15, "profiles.cycling_15.speed_kmh"),
        ("categories.0.k", 0, "categories.0.k"),
        ("categories.1.id", "grocery", "duplicate category ids: ['grocery']"),
        ("categories.0.tags", [], "categories.0.tags"),
        ("categories.0.tags", [{"shop": ""}], "non-empty key: value pair"),
        ("transit_classes.2.lower", 100, "increase without gaps"),
        ("transit_classes.3.upper", 5000, "open-ended"),
        (
            "study_area.routing_buffer_m",
            3000,
            "smaller than the prefilter reach of profile cycling_15",
        ),
        ("profiles.cycling_15.max_speed_factor", 1.2, "cycling_15 (4500 m)"),
        ("profiles.walking_339.costing_options", {"walking_speed": 5}, "via speed_kmh"),
        ("profiles.walking_339.costing", "auto", "profiles.walking_339.costing"),
        ("study_area.clip_bbox", [9.1, 48.5, 9.0, 48.6], "min_lon, min_lat"),
        ("sources.osm.url", "http://example.org/x.pbf", "sources.osm.url"),
        ("study_area.unknown_key", 1, "study_area.unknown_key"),
        ("districts.admin_levels", [9, 9], "admin_levels must be unique"),
        ("districts.admin_levels", [], "districts.admin_levels"),
        ("reference_day.weekday", "tue", "reference_day.weekday"),
        ("reference_day.school_holidays.0.to", "2026-07-01", "'to' before 'from'"),
        ("reference_day.public_holidays", ["2030-01-01"], "outside the covered range"),
        ("download.retries", -1, "download.retries"),
        ("validation.min_scored_share", 1.5, "validation.min_scored_share"),
        ("access_points.walkable_highways", [], "access_points.walkable_highways"),
        ("valhalla.url", "localhost:8002", "valhalla.url"),
        ("valhalla.concurrency", 0, "valhalla.concurrency"),
        ("valhalla.max_matrix_pairs", 0, "valhalla.max_matrix_pairs"),
        ("count.block_size_m", 0, "count.block_size_m"),
        ("count.evidence.band_edges", [0.5, 0.2], "band_edges must increase"),
        ("count.evidence.widen_factor", 0.5, "count.evidence.widen_factor"),
        ("tiles.verify.max_detour_factor", 0.9, "tiles.verify.max_detour_factor"),
        ("tiles.verify.costing", "auto", "tiles.verify.costing"),
    ],
)
def test_invalid_config_fails_clearly(
    tmp_path: Path, base: dict[str, Any], dotted: str, value: Any, expected: str
) -> None:
    path = _write(tmp_path, _set(base, dotted, value))
    with pytest.raises(ConfigError, match="invalid config") as exc:
        load_config(path)
    assert expected in str(exc.value)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("profiles: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(path)


def test_circular_extends(tmp_path: Path) -> None:
    _write(tmp_path, {"extends": "b.yaml"}, "a.yaml")
    _write(tmp_path, {"extends": "a.yaml"}, "b.yaml")
    with pytest.raises(ConfigError, match="circular"):
        load_config(tmp_path / "a.yaml")


def test_config_dir_is_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read config file"):
        load_config(tmp_path)


def test_extends_must_be_file_name(tmp_path: Path) -> None:
    path = _write(tmp_path, {"extends": ["config.yaml"]})
    with pytest.raises(ConfigError, match="'extends' must be a file name"):
        load_config(path)


def test_config_files_lists_extends_chain() -> None:
    clip = REPO / "config" / "test_clip.yaml"
    assert [p.name for p in config_files(clip)] == ["test_clip.yaml", "config.yaml"]


def test_buffer_check_includes_transit_budget(base: dict[str, Any], tmp_path: Path) -> None:
    # 5 km/h for 60 min on foot to stops = 5000 m > 4000 m buffer
    data = _set(base, "time_budgets_min.transit", 60)
    with pytest.raises(ConfigError, match="walking_500 \\(5000 m\\)"):
        load_config(_write(tmp_path, data))


def test_holiday_lookup() -> None:
    ref = load_config(CONFIG).reference_day
    assert ref.is_holiday(date(2026, 12, 25))  # public holiday
    assert ref.is_holiday(date(2026, 10, 27))  # Herbstferien
    assert not ref.is_holiday(date(2026, 11, 3))
