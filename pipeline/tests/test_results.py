"""Result checks (validation report part 2) on a tiny hand-made run: 3 cells, 2 profiles."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from reach_pipeline import recommend, results, scoring
from reach_pipeline.config import Config, Monotonic, load_config

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    """Repo config reduced to two categories and two profiles (walk with transit, bike)."""
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["categories"] = [c for c in data["categories"] if c["id"] in ("grocery", "pharmacy")]
    data["profiles"] = {
        "walk": data["profiles"]["walking_339"],
        "fast": data["profiles"]["walking_500"],
    }
    data["validation"]["results"]["monotonic"] = [
        {"higher": "fast", "lower": "walk", "warn_above": 0, "fail_above": 0.5}
    ]
    data["recommend"].update(profiles=["walk"], profile_overrides={}, min_gain=1)
    data["housing"]["profiles"] = []
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config(path)


def _tables(cfg: Config) -> results.Tables:
    cells = pd.DataFrame(
        {"cell_id": ["a", "b", "c"], "population": [10, 20, 30], "district_id": ["d1", "d1", None]}
    )
    rows = []
    counts = {"walk": [0, 1, 2], "fast": [1, 2, 3]}
    for profile, values in counts.items():
        for cat in ("grocery", "pharmacy"):
            for cell, n in zip(cells["cell_id"], values, strict=True):
                rows.append(
                    {
                        "cell_id": cell,
                        "category": cat,
                        "profile_id": profile,
                        "count": n,
                        "nearest_min": None if n == 0 else 5.0,
                    }
                )
    access = pd.DataFrame(rows).astype({"count": "int32", "nearest_min": "float64"})
    transit = pd.DataFrame(
        {
            "cell_id": ["a", "b", "c"] * 2,
            "profile_id": ["walk"] * 3 + ["fast"] * 3,
            "departures": [0, 100, 2000, 0, 150, 2500],
            "stops_count": [0, 1, 3, 0, 2, 4],
            "nearest_stop_min": [None, 4.0, 1.0, None, 3.0, 0.5],
        }
    )
    return results.Tables(
        cells=cells, access=access, transit=transit, thresholds=scoring.thresholds(cfg)
    )


def _status(checks: list[results.Check]) -> dict[str, str]:
    return {c.check: c.status for c in checks}


def test_clean_run_passes(cfg: Config) -> None:
    t = _tables(cfg)
    rows = results.class_rows(t)
    checks = (
        results.completeness(cfg, t)
        + results.value_ranges(cfg, t)
        + results.thresholds_cover(t)
        + results.totals(t, rows, 60)
        + [results.monotonic(p, t) for p in cfg.validation.results.monotonic]
    )
    assert set(_status(checks).values()) == {"ok"}, checks


def test_summary_shares_and_deficits(cfg: Config) -> None:
    t = _tables(cfg)
    s = results.summary(t, results.class_rows(t))
    grocery = s["access"]["walk"]["grocery"]  # k = 2: counts 0, 1, 2 for 10, 20, 30 residents
    assert grocery["share_lack"] == pytest.approx(10 / 60, abs=1e-4)
    assert grocery["share_insufficient"] == pytest.approx(20 / 60, abs=1e-4)
    assert grocery["share_sufficient"] == pytest.approx(30 / 60, abs=1e-4)
    assert grocery["residents_lack"] == 10
    assert grocery["deficit_sum"] == 10 * 1 + 20 * 0.5
    assert s["transit"]["walk"] == {
        "lack": 0.1667,
        "insufficient": 0.3333,
        "medium": 0,
        "high": 0.5,
    }


def test_incomplete_grid_fails(cfg: Config) -> None:
    t = _tables(cfg)
    t.access = t.access.iloc[1:]
    t.transit = pd.concat([t.transit, t.transit.iloc[:1]])
    status = _status(results.completeness(cfg, t))
    assert status == {"access_counts_complete": "fail", "transit_supply_complete": "fail"}


def test_value_ranges(cfg: Config) -> None:
    t = _tables(cfg)
    t.access.loc[0, "nearest_min"] = 3.0  # count 0 with a time
    t.access.loc[1, "nearest_min"] = cfg.time_budgets_min.facilities + 1
    t.transit.loc[0, "departures"] = 5  # departures without a stop
    (check,) = results.value_ranges(cfg, t)
    assert check.status == "fail" and check.value == 3
    assert "departures without a stop: 1" in check.message


def test_totals_compare_with_report_part1(cfg: Config) -> None:
    t = _tables(cfg)
    (check,) = results.totals(t, results.class_rows(t), 61)
    assert check.status == "fail" and "report part 1 says 61" in check.message


def test_missing_threshold_fails(cfg: Config) -> None:
    t = _tables(cfg)
    t.thresholds = t.thresholds[t.thresholds["category"] != "pharmacy"]
    (check,) = results.thresholds_cover(t)
    assert check.status == "fail" and "pharmacy" in check.message


@pytest.mark.parametrize(
    ("fail_above", "bad_cells", "expected"),
    [(0.5, 1, "warn"), (0.5, 2, "fail"), (None, 3, "warn"), (0.5, 0, "ok")],
)
def test_monotonic_shares(cfg: Config, fail_above: float | None, bad_cells: int, expected: str):
    t = _tables(cfg)
    # walk counts 0, 1, 2; make "fast" smaller in the first `bad_cells` cells (grocery only)
    mask = (t.access["profile_id"] == "fast") & (t.access["category"] == "grocery")
    fast = t.access[mask].index[:bad_cells]
    t.access.loc[fast, "count"] = -1
    pair = Monotonic(higher="fast", lower="walk", warn_above=0, fail_above=fail_above)
    check = results.monotonic(pair, t)
    assert check.status == expected
    assert check.value == pytest.approx(bad_cells / 3, abs=1e-6)


def test_monotonic_counts_transit(cfg: Config) -> None:
    t = _tables(cfg)
    t.transit.loc[5, "departures"] = 10  # fast < walk in cell c
    check = results.monotonic(cfg.validation.results.monotonic[0], t)
    assert check.status == "warn" and "1 transit rows" in check.message


def test_samples_pick_nearest_cell(cfg: Config) -> None:
    t = _tables(cfg)
    cells = t.cells.assign(x=[0.0, 100.0, 200.0], y=[0.0, 0.0, 0.0])
    (sample,) = results.samples({"here": (90.0, 5.0)}, cells, results.class_rows(t))
    assert sample["cell_id"] == "b" and sample["population"] == 20
    assert sample["values"]["walk/grocery"] == {
        "count": 1,
        "class": "insufficient",
        "deficit": 10.0,
    }


def _with_reachable(t: results.Tables) -> results.Tables:
    """Facilities g1–g3 (grocery, g1 also pharmacy, p1–p2 pharmacy) matching the counts."""
    t.facilities = pd.DataFrame(
        {
            "facility_id": ["g1", "g2", "g3", "g1", "p1", "p2"],
            "category": ["grocery", "grocery", "grocery", "pharmacy", "pharmacy", "pharmacy"],
        }
    )
    order = {"grocery": ["g1", "g2", "g3"], "pharmacy": ["g1", "p1", "p2"]}
    pairs = set()
    for r in t.access.itertuples():
        for fid in order[r.category][: r.count]:
            pairs.add((r.cell_id, r.profile_id, fid))
    # grocery and pharmacy counts are equal per cell, and g1 is in both: consistent pairs
    t.reachable = pd.DataFrame(
        sorted(pairs), columns=["cell_id", "profile_id", "facility_id"]
    ).assign(time_s=600)
    return t


def test_reachable_matches_counts(cfg: Config) -> None:
    t = _with_reachable(_tables(cfg))
    assert _status(results.reachable_matches_counts(t)) == {"reachable_matches_counts": "ok"}
    t.reachable = t.reachable.iloc[1:]  # one pair missing → that count differs
    (check,) = results.reachable_matches_counts(t)
    assert check.status == "fail" and check.value >= 1
    t = _with_reachable(_tables(cfg))
    t.reachable = pd.concat([t.reachable, t.reachable.iloc[:1]])  # duplicate key (no PK in DB)
    (check,) = results.reachable_matches_counts(t)
    assert check.status == "fail" and "1 duplicate pairs" in check.message


def test_route_sample_is_deterministic_and_near_the_budget(cfg: Config) -> None:
    rc = cfg.validation.results.route_check.model_copy(
        update={"pairs_per_profile": 4, "near_budget_share": 0.5}
    )
    reachable = pd.DataFrame(
        {
            "cell_id": [f"c{i}" for i in range(20)],
            "profile_id": ["walk"] * 20,
            "facility_id": "f",
            "time_s": [100 * (i % 10) for i in range(20)],  # 0 … 900 s
        }
    )
    a = results.route_sample(reachable, 900, rc, seed=1)
    assert a.equals(results.route_sample(reachable, 900, rc, seed=1))
    assert len(a) == 4 and (a["time_s"] >= 450).sum() == 2


def test_route_check_reports_deviation_and_flips(cfg: Config) -> None:
    rc = cfg.validation.results.route_check  # warn above 60 s
    pairs = pd.DataFrame(
        {
            "cell_id": ["a", "b", "c", "d"],
            "profile_id": ["walk", "walk", "fast", "fast"],
            "facility_id": "f",
            "time_s": [600, 890, 300, 500],
            "route_s": [601.0, 905.0, 300.0, float("nan")],
        }
    )
    check, per_profile = results.route_check(pairs, 900, rc)
    assert check.status == "ok" and check.value == 15.0
    assert per_profile["walk"] == {
        "pairs": 2,
        "no_route": 0,
        "mean_abs_s": 8.0,
        "max_abs_s": 15.0,
        "flips": 1,
    }
    assert per_profile["fast"]["no_route"] == 1
    pairs.loc[0, "route_s"] = 700.0
    assert results.route_check(pairs, 900, rc)[0].status == "warn"


def test_false_negative_candidates_are_within_reach_and_not_reachable() -> None:
    import numpy as np

    origins = np.array([[0.0, 0.0], [1000.0, 0.0]])
    # f1 has two routing points (one near each cell), f2 is a shop and a pharmacy, f3 is far
    points = np.array([[100.0, 0.0], [1100.0, 0.0], [0.0, 500.0], [5000.0, 0.0]])
    facilities = pd.DataFrame(
        {
            "facility_id": ["f1", "f2", "f2", "f3"],
            "category": ["parks", "grocery", "pharmacy", "grocery"],
        }
    )
    reachable = pd.DataFrame({"cell_id": ["a"], "facility_id": ["f1"]})
    got = results.false_negative_candidates(
        origins,
        np.array(["a", "b"]),
        points,
        np.array(["f1", "f1", "f2", "f3"]),
        facilities,
        reachable,
        reach_m=850,
    )
    got = got.sort_values(["cell_id", "facility_id", "category"]).reset_index(drop=True)
    assert got[["cell_id", "facility_id", "category"]].values.tolist() == [
        ["a", "f2", "grocery"],
        ["a", "f2", "pharmacy"],
        ["b", "f1", "parks"],  # (a, f1) is reachable; f2 is 1,118 m from b; f3 beyond reach
    ]
    assert got["distance_m"].round(1).tolist() == [500.0, 500.0, 100.0]  # nearest point


def test_false_negative_sample_is_deterministic_per_category() -> None:
    import numpy as np

    candidates = pd.DataFrame(
        {
            "cell_id": [f"c{i}" for i in range(30)],
            "facility_id": "f",
            "category": ["grocery"] * 25 + ["parks"] * 5,
            "distance_m": 100.0,
        }
    )
    a = results.false_negative_sample(candidates, 10, np.random.default_rng(3))
    b = results.false_negative_sample(candidates, 10, np.random.default_rng(3))
    assert a.equals(b)
    assert a["category"].value_counts().to_dict() == {"grocery": 10, "parks": 5}


def test_false_negative_check_warns_then_fails_above_threshold(cfg: Config) -> None:
    fc = cfg.validation.results.false_negatives.model_copy(
        update={"warn_above": 0.0, "fail_above": 0.3}
    )
    pairs = pd.DataFrame(
        {
            "profile_id": ["walk"] * 4,
            "category": ["grocery", "grocery", "parks", "parks"],
            "cell_id": ["a", "b", "c", "d"],
            "facility_id": ["f1", "f2", "f3", "f4"],
            "distance_m": [500.0, 700.0, 600.0, 650.0],
            "route_s": [984.0, 901.0, float("nan"), 1200.0],
        }
    )
    check, detail = results.false_negative_check(pairs, 900, fc)
    assert check.check == "false_negatives" and check.status == "ok" and check.value == 0
    assert detail["profiles"]["walk"]["parks"] == {
        "pairs": 2,
        "no_route": 1,
        "false_negatives": 0,
        "rate": 0.0,
    }
    pairs.loc[1, "route_s"] = 900.0  # within the budget (≤) by /route: missed
    check, detail = results.false_negative_check(pairs, 900, fc)
    assert check.status == "warn" and check.value == 0.25
    assert detail["examples"][0]["facility_id"] == "f2"
    pairs.loc[3, "route_s"] = 800.0
    assert results.false_negative_check(pairs, 900, fc)[0].status == "fail"  # 50 % > 30 %


def test_budget_flips_per_profile_and_direction(cfg: Config) -> None:
    bf = cfg.validation.results.budget_flips.model_copy(update={"warn_above": 0.05})
    route = {
        "profiles": {
            "walk": {"pairs": 25, "no_route": 5, "flips": 1},
            "bike": {"pairs": 25, "no_route": 0, "flips": 0},
        }
    }
    missed = {
        "profiles": {
            "walk": {
                "grocery": {"pairs": 20, "no_route": 0, "false_negatives": 0},
                "parks": {"pairs": 20, "no_route": 0, "false_negatives": 0},
            },
            "bike": {"grocery": {"pairs": 20, "no_route": 4, "false_negatives": 1}},
        }
    }
    check, detail = results.budget_flips(route, missed, bf)
    assert check.check == "budget_flips" and check.status == "warn" and check.value == 0.0625
    assert detail["profiles"]["walk"] == {
        "within_to_beyond": {"routed": 20, "flips": 1, "rate": 0.05},  # not above 5 %
        "beyond_to_within": {"routed": 40, "flips": 0, "rate": 0.0},
    }
    assert "bike beyond_to_within 6.2%" in check.message and "walk" not in check.message
    route["profiles"]["walk"]["no_route"] = 25  # no routed pair: rate 0, never a division by 0
    missed["profiles"]["bike"]["grocery"]["false_negatives"] = 0
    check, _ = results.budget_flips(route, missed, bf)
    assert check.status == "ok" and check.value == 0.0


def _with_recommendations(cfg: Config) -> results.Tables:
    """Tables plus one greedy recommendation per category for `walk` (catchment: cells a, b)."""
    t = _tables(cfg)
    pop = t.cells["population"].to_numpy()
    cover = np.array([[True, True, False]])
    rows, rc = [], []
    for c in cfg.categories:
        a = t.access[(t.access["profile_id"] == "walk") & (t.access["category"] == c.id)]
        counts = a.set_index("cell_id")["count"].reindex(t.cells["cell_id"]).to_numpy()
        for p in recommend.greedy(cover, pop, counts, c.k, 5, 1):
            rows.append(
                {
                    "category": c.id,
                    "profile_id": "walk",
                    "rank": p.rank,
                    "candidate_id": "z1",
                    "population_gain": p.population_gain,
                    "residents_gaining_access": p.residents_gaining_access,
                    "residents_to_sufficient": p.residents_to_sufficient,
                    "catchment_residents": p.catchment_residents,
                    "catchment_cells": p.catchment_cells,
                }
            )
    rc = pd.DataFrame(
        {"candidate_id": "z1", "profile_id": "walk", "cell_id": ["a", "b"], "time_s": [60, 600]}
    )
    t.recommendations, t.recommendation_catchments = pd.DataFrame(rows), rc
    return t


def test_recommendations_consistent(cfg: Config) -> None:
    t = _with_recommendations(cfg)
    assert len(t.recommendations) >= 1
    assert results.recommendations_consistent(cfg, t).status == "ok"
    bad = _with_recommendations(cfg)
    bad.recommendations.loc[0, "population_gain"] += 5
    check = results.recommendations_consistent(cfg, bad)
    assert check.status == "fail" and "replay" in check.message
    bad = _with_recommendations(cfg)
    bad.recommendations["profile_id"] = "fast"  # not in recommend.profiles, catchment missing
    assert results.recommendations_consistent(cfg, bad).status == "fail"
    bad = _with_recommendations(cfg)
    bad.recommendations["rank"] = 2
    assert "ranks" in results.recommendations_consistent(cfg, bad).message


def _with_housing(cfg: Config) -> tuple[Config, results.Tables]:
    cfg = cfg.model_copy(update={"housing": cfg.housing.model_copy(update={"profiles": ["walk"]})})
    t = _tables(cfg)
    ids = ["h1", "h2"]
    t.housing_cells = pd.DataFrame({"cell_id": ids})
    t.housing_counts = pd.DataFrame(
        [
            {"cell_id": i, "category": c, "profile_id": "walk", "count": n, "nearest_min": None}
            for i in ids
            for n, c in enumerate(("grocery", "pharmacy"))
        ]
    ).astype({"count": "int32", "nearest_min": "float64"})
    t.housing_reachable = pd.DataFrame(
        {"cell_id": ["h2"], "profile_id": ["walk"], "facility_id": ["f1"], "time_s": [60]}
    )
    return cfg, t


def test_housing_consistent(cfg: Config) -> None:
    cfg, t = _with_housing(cfg)
    assert results.housing_consistent(cfg, t).status == "ok"

    _, bad = _with_housing(cfg)
    bad.housing_cells = pd.DataFrame({"cell_id": ["h1", "a"]})  # `a` is a resident cell
    bad.housing_counts["cell_id"] = bad.housing_counts["cell_id"].replace("h2", "a")
    assert "resident cells" in results.housing_consistent(cfg, bad).message

    _, bad = _with_housing(cfg)
    bad.housing_counts = bad.housing_counts.iloc[:-1]
    assert "expected" in results.housing_consistent(cfg, bad).message

    _, bad = _with_housing(cfg)
    bad.housing_counts["profile_id"] = "fast"
    assert "housing.profiles" in results.housing_consistent(cfg, bad).message

    _, bad = _with_housing(cfg)
    bad.housing_reachable["cell_id"] = "zz"
    assert results.housing_consistent(cfg, bad).status == "fail"

    _, bad = _with_housing(cfg)
    bad.housing_cells = None
    assert results.housing_consistent(cfg, bad).message == "housing outputs missing"
