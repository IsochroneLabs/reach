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
    assert set(cfg.routing_profiles) == {"walk", "bike", "transit", "bike_transit"}
    assert cfg.routing_profiles["bike_transit"].access == "BICYCLE_PARKING"
    assert cfg.destination_types["sport"].source == "labels"
    assert cfg.trip_windows["morning_lecture"].mode == "arrive_by"
    assert cfg.trip_windows["night_return"].direction == "back"
    assert cfg.destination_types["campus_site"].source == "campus"
    assert cfg.destination_types["grocery"].tags == [{"shop": "supermarket"}]
    assert cfg.sources.zensus_rent is not None
    labels = cfg.destination_labels
    assert labels is not None
    assert labels.grocery.fallback == "other"
    assert "organic" in labels.grocery.groups
    assert labels.sport.categories["tennis"].sport == ["tennis"]
    assert "chess" in labels.hobby.categories


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
        ("routing_profiles.walk.speed_kmh", 0, "routing_profiles.walk.speed_kmh"),
        ("routing_profiles.bike.speed_kmh", -15, "routing_profiles.bike.speed_kmh"),
        ("routing_profiles.walk.costing", "auto", "routing_profiles.walk.costing"),
        ("routing_profiles.walk.engine", "r5", "routing_profiles.walk.engine"),
        ("routing_profiles.walk.engine", "otp", "otp profiles need an access mode"),
        ("routing_profiles.walk.costing_options", {"walking_speed": 5}, "via speed_kmh"),
        (
            "routing_profiles",
            {"Walk": {"engine": "valhalla", "costing": "pedestrian", "speed_kmh": 5}},
            "lower snake_case",
        ),
        ("trip_windows.midday.time", "25:00", "trip_windows.midday.time"),
        ("trip_windows.midday.time", "8:10", "trip_windows.midday.time"),
        ("trip_windows.midday.weekday", "tue", "trip_windows.midday.weekday"),
        ("trip_windows.midday.mode", "leave_at", "trip_windows.midday.mode"),
        ("trip_windows.midday.direction", "home", "trip_windows.midday.direction"),
        ("destination_types.grocery.trip_window", "brunch", "unknown trip windows"),
        ("destination_types.grocery.tags", [], "source osm needs tags and a location"),
        ("destination_types.grocery.tags", [{"shop": ""}], "non-empty key: value pair"),
        ("destination_types.grocery.location", "polygon", "destination_types.grocery.location"),
        ("destination_types.grocery.nearest_k", 0, "destination_types.grocery.nearest_k"),
        ("destination_types.grocery.fine_time_min", 0, "destination_types.grocery.fine_time"),
        ("destination_types.grocery.trips_per_week", -1, "destination_types.grocery.trips"),
        ("destination_types.mensa.tags", [{"amenity": "canteen"}], "source campus takes no"),
        ("destination_types.park.exclude", [{"access": "a", "x": "b"}], "non-empty key: value"),
        ("destination_types.library.require", [{"": "x"}], "non-empty key: value pair"),
        ("study_area.clip_bbox", [9.1, 48.5, 9.0, 48.6], "min_lon, min_lat"),
        ("study_area.unknown_key", 1, "study_area.unknown_key"),
        ("sources.osm.url", "http://example.org/x.pbf", "sources.osm.url"),
        ("cleanup.keep_published_runs", 0, "cleanup.keep_published_runs"),
        ("districts.admin_levels", [9, 9], "admin_levels must be unique"),
        ("districts.admin_levels", [], "districts.admin_levels"),
        ("calendar.school_holidays.0.to", "2026-07-01", "'to' before 'from'"),
        ("calendar.public_holidays", ["2030-01-01"], "outside the covered range"),
        ("download.retries", -1, "download.retries"),
        ("validation.min_scored_share", 1.5, "validation.min_scored_share"),
        ("validation.bike_not_slower_than_walk.fail_below", 0.99, "fail_below must be <="),
        ("access_points.walkable_highways", [], "access_points.walkable_highways"),
        ("valhalla.url", "localhost:8002", "valhalla.url"),
        ("valhalla.concurrency", 0, "valhalla.concurrency"),
        ("valhalla.max_matrix_pairs", 0, "valhalla.max_matrix_pairs"),
        ("travel_times.block_size_m", 0, "travel_times.block_size_m"),
        ("tiles.verify.max_detour_factor", 0.9, "tiles.verify.max_detour_factor"),
        ("tiles.verify.costing", "auto", "tiles.verify.costing"),
        ("destination_labels.cluster_radius_m", 0, "destination_labels.cluster_radius_m"),
        ("destination_labels.grocery.fallback", "bio", "fallback group 'bio' is not a group"),
        ("destination_labels.grocery.groups.discount.brands", ["spar"], "unknown brands"),
        (
            "destination_labels.grocery.groups.local.name_patterns",
            ["(laden"],
            "invalid name pattern",
        ),
        ("destination_labels.grocery.groups.other.tags", [{"shop": "x"}], "must have no rules"),
        ("destination_labels.sport.categories.tennis.sport", ["soccer"], "in both football and"),
        ("destination_labels.sport.categories.golf.leisure", ["golf_park"], "missing from sport"),
        ("destination_labels.hobby.categories.chess.tags", [], "needs sport values, leisure"),
        (
            "destination_labels.hobby.categories",
            {"Chess": {"label": {"en": "C", "de": "S"}, "tags": [{"sport": "chess"}]}},
            "lower snake_case",
        ),
    ],
)
def test_invalid_config_fails_clearly(
    tmp_path: Path, base: dict[str, Any], dotted: str, value: Any, expected: str
) -> None:
    path = _write(tmp_path, _set(base, dotted, value))
    with pytest.raises(ConfigError, match="invalid config") as exc:
        load_config(path)
    assert expected in str(exc.value)


def test_destination_labels_are_optional(tmp_path: Path, base: dict[str, Any]) -> None:
    data = copy.deepcopy(base)
    del data["destination_labels"]
    assert load_config(_write(tmp_path, data)).destination_labels is None


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


def test_holiday_lookup() -> None:
    cal = load_config(CONFIG).calendar
    assert cal.is_holiday(date(2026, 12, 25))  # public holiday
    assert cal.is_holiday(date(2026, 10, 27))  # Herbstferien
    assert not cal.is_holiday(date(2026, 11, 3))


def test_listings_section_is_paged_and_polite():
    """The listings job is on since Juju's decision of 27 Nov 2026 (notes N20), at a low rate."""
    cfg = load_config(CONFIG)
    assert cfg.listings is not None
    assert all("{page}" in p for p in cfg.listings.search_paths.values())
    assert cfg.listings.request_interval_s >= 10
