"""Nearest-k routing targets on small synthetic layers (no engine, no data)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from reach_pipeline import targets
from reach_pipeline.config import load_config

CRS = "EPSG:25832"
REPO = Path(__file__).resolve().parents[2]


def _origins(xs: list[float]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"cell_id": [f"c{i}" for i in range(len(xs))]},
        geometry=[Point(x, 0) for x in xs],
        crs=CRS,
    )


def _dest(prefix: str, xs: list[float]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"destination_id": [f"{prefix}{i}" for i in range(len(xs))]},
        geometry=[Point(x, 0) for x in xs],
        crs=CRS,
    )


def test_nearest_k_exact_beyond_any_radius() -> None:
    group = targets.Group("grocery", 2, _dest("d", [10, 50, 20_000, 30_000]))
    out = targets.nearest_k(_origins([0, 25_000]), group)
    got = out.groupby("cell_id")["destination_id"].apply(sorted).to_dict()
    assert got == {"c0": ["d0", "d1"], "c1": ["d2", "d3"]}  # far ones kept when nothing is near


def test_k_none_and_k_above_size_take_all() -> None:
    dest = _dest("s", [0, 100, 200])
    assert len(targets.nearest_k(_origins([0]), targets.Group("campus", None, dest))) == 3
    assert len(targets.nearest_k(_origins([0]), targets.Group("x", 5, dest))) == 3


def test_transit_factor_widens_candidates() -> None:
    group = targets.Group("grocery", 1, _dest("d", [10, 20, 30]))
    assert len(targets.nearest_k(_origins([0]), group, factor=2)) == 2


def test_pairs_union_is_deduplicated() -> None:
    shared = _dest("d", [10, 500])
    groups = [
        targets.Group("grocery", 1, shared),
        targets.Group("grocery:brand:rewe", 2, shared.iloc[[1]].reset_index(drop=True)),
    ]
    out = targets.pairs(_origins([0]), groups)
    assert list(out.columns) == targets.PAIR_COLUMNS
    assert out.set_index("destination_id")["groups"].to_dict() == {
        "d0": "grocery",
        "d1": "grocery:brand:rewe",
    }
    both = targets.pairs(_origins([450]), groups)
    assert both.set_index("destination_id").loc["d1", "groups"] == "grocery;grocery:brand:rewe"


def test_chunks_match_one_block(monkeypatch) -> None:
    rng = np.random.default_rng(1)
    origins = _origins(list(rng.uniform(0, 5000, 50)))
    group = targets.Group("g", 3, _dest("d", list(rng.uniform(0, 5000, 40))))
    whole = targets.nearest_k(origins, group).sort_values(["cell_id", "destination_id"])
    monkeypatch.setattr(targets, "_CHUNK", 7)
    split = targets.nearest_k(origins, group).sort_values(["cell_id", "destination_id"])
    pd.testing.assert_frame_equal(whole.reset_index(drop=True), split.reset_index(drop=True))


def test_label_and_type_groups() -> None:
    cfg = load_config(REPO / "config" / "config.yaml")
    labels = gpd.GeoDataFrame(
        {
            "destination_id": ["grocery:rewe:n1", "grocery:rewe:n2", "grocery:netto:n3"],
            "destination_type": ["grocery"] * 3,
            "label_kind": ["brand"] * 3,
            "label": ["rewe", "rewe", "netto"],
            "offered": [True, True, False],
        },
        geometry=[Point(0, 0), Point(10, 0), Point(20, 0)],
        crs=CRS,
    )
    groups = targets.label_groups(labels, cfg.destination_labels.nearest_k_label)
    assert [(g.key, g.k, len(g.destinations)) for g in groups] == [("grocery:brand:rewe", 2, 2)]
    dest = labels.assign(destination_type=["grocery", "grocery", "unknown_type"])
    tgroups = targets.type_groups(dest, cfg)
    assert [(g.key, g.k) for g in tgroups] == [
        ("grocery", cfg.destination_types["grocery"].nearest_k)
    ]


def test_empty_inputs() -> None:
    assert targets.pairs(_origins([0]), []).empty
    empty = targets.Group("g", 1, _dest("d", []))
    assert targets.nearest_k(_origins([0]), empty).empty
    s = targets.summary(targets.pairs(_origins([0]), []), _origins([0]))
    assert s["pairs"] == 0 and s["origins"] == 1
