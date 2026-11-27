"""Destination labels on a hand-made OSM fixture (needs the osmium-tool binary, see README)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, box

from reach_pipeline import labels
from reach_pipeline.config import DestinationLabels, load_config
from reach_pipeline.stages import validate

REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "labels.osm"


@pytest.fixture(scope="module")
def cfg() -> DestinationLabels:
    loaded = load_config(REPO / "config" / "config.yaml").destination_labels
    assert loaded is not None
    return loaded


@pytest.fixture(scope="module")
def dest(cfg: DestinationLabels, tmp_path_factory: pytest.TempPathFactory) -> gpd.GeoDataFrame:
    return validate.build_labels(FIXTURE, tmp_path_factory.mktemp("labels"), cfg)


def _labels(dest: gpd.GeoDataFrame, kind: str) -> dict[str, int]:
    sel = dest[dest["label_kind"] == kind]
    return sel.groupby("label").size().to_dict()


def test_supermarket_brands_and_groups(dest: gpd.GeoDataFrame) -> None:
    assert _labels(dest, "brand") == {"rewe": 2}  # by brand:wikidata and by name
    assert _labels(dest, "group") == {
        "full_range": 2,
        "international": 1,
        "organic": 1,
        "other": 1,  # access=customers does not drop a shop
    }


def test_sport_categories_and_clustering(dest: gpd.GeoDataFrame) -> None:
    sport = dest[dest["destination_type"] == "sport"]
    assert _labels(sport, "category") == {
        "athletics": 1,  # leisure=track without sport: leisure decides
        "basketball": 1,  # sport=soccer;basketball carries two labels
        "fitness": 1,  # two gyms 300 m apart inside one sports centre
        "football": 1,
        "swimming": 1,  # the public pool; the garden pool is dropped
        "tennis": 2,  # two courts 44 m apart are one place, the far court another
    }
    gym = sport[sport["label"] == "fitness"].iloc[0]
    assert gym["n_features"] == 2 and gym["name"] == "Gym Nord"
    assert "climbing" not in set(sport["label"])  # access=private
    tennis = sport[sport["label"] == "tennis"].sort_values("n_features")
    assert list(tennis["n_features"]) == [1, 2]
    assert sorted(tennis.iloc[1]["osm_ids"].split(";")) == ["w201", "w202"]


def test_hobby_and_religion(dest: gpd.GeoDataFrame) -> None:
    assert _labels(dest, "category").get("music") == 1
    assert _labels(dest, "religion") == {"christian": 1, "unknown": 1}


def test_layer_schema(dest: gpd.GeoDataFrame) -> None:
    assert list(dest.columns) == labels.COLUMNS
    assert dest.crs.to_string() == labels.METRIC_CRS
    assert dest["destination_id"].is_unique
    assert set(dest.geometry.geom_type) == {"Point"}
    assert dest["destination_id"].str.startswith("grocery:rewe:").sum() == 2


def test_offered_needs_min_stores(dest: gpd.GeoDataFrame, cfg: DestinationLabels) -> None:
    single = dest[dest["label_kind"] != "brand"].copy()
    rewe = dest[dest["label_kind"] == "brand"].head(1)
    trimmed = labels.cluster(
        gpd.GeoDataFrame(
            {
                "osm_id": ["n1"],
                "destination_type": ["grocery"],
                "label_kind": ["brand"],
                "label": ["rewe"],
                "name": ["REWE"],
                "leisure": [""],
            },
            geometry=rewe.geometry.to_numpy(),
            crs=dest.crs,
        ),
        dest.iloc[:0],
        cfg,
    )
    assert not trimmed["offered"].any()  # one store < brand_min_stores (2)
    assert single["offered"].all()


def test_label_check(dest: gpd.GeoDataFrame, cfg: DestinationLabels) -> None:
    check = validate.label_check(dest, cfg)
    assert check.status == "warn"  # most sport categories have no place in the fixture
    assert "ice_sports" in check.message and "brand absent" in check.message
    no_shops = validate.label_check(dest[dest["destination_type"] != "grocery"], cfg)
    assert no_shops.status == "fail"


def test_components_chain() -> None:
    comp = labels._components(5, np.array([0, 1, 3]), np.array([1, 2, 4]))
    assert list(comp) == [0, 0, 0, 3, 3]


def test_empty_inputs(cfg: DestinationLabels) -> None:
    empty = gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs=labels.METRIC_CRS)
    out = labels.cluster(labels.label_features(empty, cfg), empty, cfg)
    assert out.empty and list(out.columns) == labels.COLUMNS


def test_unique_features_keeps_polygon() -> None:
    feats = gpd.GeoDataFrame(
        {"osm_id": ["w1", "w1", "n2"]},
        geometry=[box(0, 0, 10, 10).exterior, box(0, 0, 10, 10), Point(50, 50)],
        crs=labels.METRIC_CRS,
    )
    out = labels.unique_features(feats)
    assert list(out["osm_id"]) == ["w1", "n2"]
    assert out.geometry.iloc[0].geom_type == "Polygon"
