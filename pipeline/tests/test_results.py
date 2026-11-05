"""Result checks (validation report part 2) on a tiny hand-made run: 3 cells, 2 profiles."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from reach_pipeline import results, scoring
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
