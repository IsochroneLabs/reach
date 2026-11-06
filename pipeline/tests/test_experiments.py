"""Validation experiments (reach_pipeline.experiments): pure functions, no network."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely

from reach_pipeline import recommend as rec
from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.experiments import cli, common, settings
from reach_pipeline.experiments import v02_completeness as v02
from reach_pipeline.experiments import v03_backtest as v03
from reach_pipeline.experiments import v04_exact as v04
from reach_pipeline.experiments import v05_sensitivity as v05
from reach_pipeline.experiments import v06_origin as v06
from reach_pipeline.experiments import v08_spatial as v08
from reach_pipeline.experiments import v11_slopes as v11

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures" / "experiments"
K = pd.Series({"grocery": 2, "pharmacy": 1})


def _cells() -> pd.DataFrame:
    return pd.DataFrame(
        {"cell_id": ["a", "b", "c"], "population": [10, 20, 30], "district_id": ["d1", "d1", "d2"]}
    )


def _access(counts: dict[tuple[str, str], int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"cell_id": c, "category": cat, "profile_id": "p", "count": n}
            for (c, cat), n in counts.items()
        ]
    )


def test_settings_file_is_valid_and_uses_known_profiles() -> None:
    s = settings.load_settings(REPO / "config" / "experiments.yaml")
    cfg = load_config(REPO / "config" / "config.yaml")
    assert s.profiles_used() <= cfg.profiles.keys()
    assert all(cfg.profiles[p].costing != "bicycle" for p in s.profiles_used())


def test_compare_counts_class_changes_and_worse() -> None:
    base = _access(
        {
            ("a", "grocery"): 2,
            ("b", "grocery"): 1,
            ("c", "grocery"): 0,
            ("a", "pharmacy"): 1,
            ("b", "pharmacy"): 0,
            ("c", "pharmacy"): 3,
        }
    )
    alt = _access(
        {
            ("a", "grocery"): 1,
            ("b", "grocery"): 1,
            ("c", "grocery"): 2,
            ("a", "pharmacy"): 1,
            ("b", "pharmacy"): 1,
            ("c", "pharmacy"): 3,
        }
    )
    out = common.compare(base, alt, _cells(), K).set_index("category")
    # grocery: a sufficient → insufficient (worse), c lack → sufficient; pharmacy: b lack → ok.
    assert out.loc["grocery", "residents_changed"] == 40
    assert out.loc["grocery", "residents_worse"] == 10
    assert out.loc["pharmacy", "residents_changed"] == 20
    assert out.loc["grocery", "share_lack_base"] == pytest.approx(0.5)
    assert out.loc["grocery", "share_lack_alt"] == 0
    # Deficit: grocery base 0 + 20*0.5 + 30 = 40, alt 10*0.5 + 20*0.5 + 0 = 15.
    assert out.loc["grocery", "deficit_base"] == 40
    assert out.loc["grocery", "deficit_alt"] == 15


def test_compare_with_shifted_k() -> None:
    base = _access(
        {
            ("a", "grocery"): 2,
            ("b", "grocery"): 1,
            ("c", "grocery"): 0,
            ("a", "pharmacy"): 1,
            ("b", "pharmacy"): 0,
            ("c", "pharmacy"): 3,
        }
    )
    out = common.compare(base, base, _cells(), K, K + 1).set_index("category")
    assert out.loc["grocery", "residents_changed"] == 10  # a: 2 of k=3 → insufficient
    assert out.loc["pharmacy", "residents_changed"] == 10  # a: 1 of k=2 → insufficient


def test_counts_within_smaller_budget() -> None:
    reachable = pd.DataFrame(
        {
            "cell_id": ["a", "a", "b"],
            "profile_id": "p",
            "facility_id": ["f1", "f2", "f1"],
            "time_s": [100, 700, 500],
        }
    )
    fac = pd.DataFrame({"facility_id": ["f1", "f2"], "category": ["grocery", "grocery"]})
    out = common.counts_within(reachable, fac, np.array(["a", "b"]), ["grocery"], "p", 600)
    assert out.set_index("cell_id")["count"].to_dict() == {"a": 1, "b": 1}


def test_spearman_and_ranking_agreement() -> None:
    a = pd.Series([1, 2, 3, 4], index=list("wxyz"))
    assert common.spearman(a, a * 10) == 1.0
    assert common.spearman(a, -a) == -1.0
    d = pd.DataFrame(
        {
            "profile_id": "p",
            "category": "g",
            "district_id": list("wxyz"),
            "deficit_sum": [4, 3, 2, 1],
        }
    )
    out = common.ranking_agreement(d, d.assign(deficit_sum=[3, 4, 2, 1]), top=2)
    assert out.loc[0, "top2_overlap"] == 2
    assert out.loc[0, "spearman"] == pytest.approx(0.8)


def test_near_count() -> None:
    xy = pd.DataFrame({"x": [0, 300, 2000], "y": [0, 0, 0]}, index=["z1", "z2", "z3"])
    assert v05.near_count(xy, {"z1", "z3"}, {"z2"}, 500) == 1
    assert v05.near_count(xy, {"z1"}, set(), 500) == 0


def test_hit_rates() -> None:
    picks = np.array([[0, 0], [1000, 0]])
    removed = np.array([[100, 0], [5000, 0], [5100, 0]])
    assert v03.hit_rates(picks, removed, 250) == (0.5, pytest.approx(1 / 3))
    assert v03.hit_rates(picks[:0], removed, 250) == (0.0, 0.0)


def test_created_only_counts_keep_exactly_the_created_deficit() -> None:
    from reach_pipeline import scoring

    k, pop = 2, np.array([10.0, 10.0, 10.0, 10.0])
    before, after = np.array([3, 2, 1, 1]), np.array([1, 2, 0, 1])
    a = v03.created_only_counts(before, after, k)
    created = scoring.deficit(pop, after, k) - scoring.deficit(pop, before, k)
    assert scoring.deficit(pop, a, k).tolist() == created.tolist() == [5.0, 0.0, 5.0, 0.0]


def test_exact_beats_greedy_on_a_trap_instance() -> None:
    # Candidate 0 covers the middle (largest single gain), candidates 1 and 2 the two halves:
    # greedy takes 0 first and then one half; the optimum for N = 2 is both halves.
    cover = np.array([[0, 1, 1, 1, 1, 0], [1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1]], dtype=bool)
    pop = np.array([3, 2, 2, 2, 2, 3], dtype=float)
    counts = np.zeros(6, dtype=int)
    g = [p.candidate for p in rec.greedy(cover, pop, counts, 1, 2, 0.0)]
    assert g[0] == 0
    ex = v04.solve_exact(cover, pop, counts, 1, 2, 10)
    assert ex["status"] == "Optimal"
    assert sorted(ex["picks"]) == [1, 2]
    assert ex["gain"] == 14
    assert v04.covered_gain(cover, pop, counts, 1, g) == 11


def test_reduce_instance_drops_sufficient_cells_and_useless_candidates() -> None:
    cover = np.array([[1, 0], [0, 1]], dtype=bool)
    red, p, a, cand = v04.reduce_instance(cover, np.array([5.0, 7.0]), np.array([2, 0]), 2)
    assert cand.tolist() == [1]
    assert red.shape == (1, 1) and p.tolist() == [7.0] and a.tolist() == [0]


def _grid(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xy = np.array([[i * 100, j * 100] for i in range(n) for j in range(n)], dtype=float)
    i, j = v08.distance_neighbours(xy, 150)
    return xy, i, j


def test_global_moran_clustered_and_checkerboard() -> None:
    xy, i, j = _grid(8)
    clustered = (xy[:, 0] < 400).astype(float)
    rng = np.random.default_rng(1)
    pos = v08.global_moran(clustered, i, j, 199, rng)
    assert pos["I"] > 0.5 and pos["p"] <= 0.01
    # Rook neighbours on a checkerboard are all of the other colour: strongly negative.
    ri, rj = v08.distance_neighbours(xy, 100)
    board = ((xy[:, 0] + xy[:, 1]) / 100 % 2).astype(float)
    assert v08.global_moran(board, ri, rj, 199, rng)["I"] == pytest.approx(-1.0)


def test_local_moran_marks_the_high_cluster() -> None:
    xy, i, j = _grid(8)
    x = ((xy[:, 0] < 300) & (xy[:, 1] < 300)).astype(float)
    out = v08.local_moran(x, i, j, 199, np.random.default_rng(2))
    corner = (xy[:, 0] == 100) & (xy[:, 1] == 100)
    assert out.loc[corner, "quadrant"].item() == 1
    assert out.loc[corner, "p"].item() <= 0.05
    assert len(out) == len(x)


def test_touching_neighbours() -> None:
    boxes = np.array([shapely.box(0, 0, 1, 1), shapely.box(1, 0, 2, 1), shapely.box(5, 5, 6, 6)])
    i, j = v08.touching_neighbours(boxes)
    assert sorted(zip(i.tolist(), j.tolist(), strict=True)) == [(0, 1), (1, 0)]


def test_building_origins_medoid_and_fallback() -> None:
    crs = "EPSG:25832"
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["a", "b"],
            "origin_geom": gpd.GeoSeries([shapely.Point(50, 50), shapely.Point(150, 50)], crs=crs),
        },
        geometry=[shapely.box(0, 0, 100, 100), shapely.box(100, 0, 200, 100)],
        crs=crs,
    )
    # Cell a: a big house at the left, a small one at the right: the weighted centroid is
    # near the big one, which becomes the origin. Cell b has no building.
    buildings = gpd.GeoDataFrame(
        {"building": ["house", "house"]},
        geometry=[shapely.box(5, 40, 35, 70), shapely.box(85, 40, 90, 45)],
        crs=crs,
    )
    origin, from_building = v06.building_origins(cells, buildings)
    assert from_building.tolist() == [True, False]
    assert shapely.box(5, 40, 35, 70).contains(shapely.Point(origin[0]))
    assert origin[1].tolist() == [150, 50]


def test_residential_filter() -> None:
    crs = "EPSG:25832"
    b = gpd.GeoDataFrame(
        {"building": ["house", "yes", "yes", "garage"]},
        geometry=[
            shapely.box(0, 0, 1, 1),
            shapely.box(10, 10, 11, 11),
            shapely.box(50, 50, 51, 51),
            shapely.box(2, 2, 3, 3),
        ],
        crs=crs,
    )
    landuse = gpd.GeoSeries([shapely.box(5, 5, 20, 20)], crs=crs)
    kept = v06.residential(b, landuse, ["house"])
    assert kept["building"].tolist() == ["house", "yes"]


def test_parse_city_pages() -> None:
    kita = v02.parse_detail((FIXTURES / "kita.html").read_text(encoding="utf-8"))
    assert kita == {
        "name": "Kinderhaus Beispiel",
        "street": "Neckarhalde 3/1",
        "postcode": "72070",
        "place": "Tübingen",
        "operator": "Beispiel e.V.",
    }
    school_page = (FIXTURES / "school.html").read_text(encoding="utf-8")
    school = v02.parse_detail(school_page)
    assert (school["name"], school["street"], school["operator"]) == (
        "Grundschule Beispiel",
        "Sengentalstraße 16",
        None,
    )
    assert v02._DETAIL.findall('<a href="/26689/26693einrichtung1172.html">') == [
        "/26689/26693einrichtung1172.html"
    ]


def test_address_normalisation_and_names() -> None:
    assert v02.split_address("Sengentalstraße 16") == ("sengentalstr", "16")
    assert v02.split_address("Hauptstr. 12 a") == ("hauptstr", "12a")
    assert v02.split_address("Am Markt") is None
    assert v02.normalise_street("Wilhelm-Straße") == v02.normalise_street("Wilhelmstr.")
    assert v02.name_tokens(float("nan")) == set()
    a, b = v02.name_tokens("Ev. Kinderhaus Sonne Lustnau"), v02.name_tokens("Kita Lustnau")
    assert v02.jaccard(a, b) == 0.5


def test_locate_and_match() -> None:
    ref = pd.DataFrame(
        {"name": ["Kita Sonne", "Kita Mond"], "street": ["Hauptstraße 5", "Nirgendwo 1"]}
    )
    addresses = pd.DataFrame(
        {
            "street": ["hauptstr", "hauptstr"],
            "number": ["5a", "7"],
            "x": [100.0, 300.0],
            "y": [0.0, 0.0],
        }
    )
    located = v02.locate(ref, addresses)
    assert located.loc[0, "x"] == 100  # number without suffix
    assert np.isnan(located.loc[1, "x"])
    fac = gpd.GeoDataFrame(
        {"name": ["Sonnenschein", "Kita Mond", None]},
        geometry=[shapely.Point(150, 0), shapely.Point(9e3, 0), shapely.Point(5e3, 0)],
        crs="EPSG:25832",
    )
    pairs = v02.match(located, fac, 100, 0.5)
    assert sorted(zip(pairs["ref"], pairs["facility"], strict=True)) == [(0, 0), (1, 1)]


def test_docker_memory_parsing_and_image() -> None:
    assert v11.parse_mem_mb("1.21GiB / 7.6GiB") == pytest.approx(1239.04)
    assert v11.parse_mem_mb("512MiB / 2GiB") == 512
    assert np.isnan(v11.parse_mem_mb("--"))
    assert v11.valhalla_image(REPO).startswith("ghcr.io/valhalla/valhalla:")


def test_manual_experiment_and_summary(tmp_path: Path) -> None:
    cfg = load_config(REPO / "config" / "config.yaml").model_copy(update={"data_dir": tmp_path})
    ctx = RunContext(
        config=cfg, config_path=REPO / "config" / "config.yaml", run_id="20261106T142630Z"
    )
    s = settings.load_settings(REPO / "config" / "experiments.yaml")
    out = cli.run_one(ctx, s, "v07")
    assert out["status"] == "manual"
    path = tmp_path / s.results_dir / ctx.run_id / "v07" / cli.RESULT
    assert json.loads(path.read_text())["experiment"] == "V07"
    text = cli.summary(ctx, s).read_text()
    assert "| V07 | Plausibility with local knowledge | manual |" in text
    assert "| V01 | – | not run |" in text
