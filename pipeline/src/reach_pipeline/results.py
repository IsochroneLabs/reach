"""Checks of the results (validation report part 2): pure functions on the count/score tables.

Monotonicity, completeness, value ranges and totals (arch. §7 "validate results"); used by
`stages/validate_results.py`. Checks return `Check` rows of the `validation_report` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from reach_pipeline import scoring
from reach_pipeline.config import Config, Monotonic, RouteCheck

STAGE = "validate_results"
# nearest_min is rounded to 0.01 min by count.
_ROUND_MIN = 0.01


@dataclass
class Tables:
    cells: pd.DataFrame  # cell_id, population, district_id
    access: pd.DataFrame  # access_counts
    transit: pd.DataFrame  # transit_supply
    thresholds: pd.DataFrame
    reachable: pd.DataFrame | None = None  # cell_id, profile_id, facility_id, time_s
    facilities: pd.DataFrame | None = None  # facility_id, category


@dataclass
class Check:
    """One row of the validation report (data contract `validation_report`)."""

    check: str
    status: str  # ok | warn | fail
    value: float | None
    message: str
    stage: str = STAGE


def completeness(cfg: Config, t: Tables) -> list[Check]:
    """access_counts = cells × categories × profiles, transit_supply = cells × transit profiles."""
    cells = set(t.cells["cell_id"])
    out = []
    for name, frame, keys, profiles in (
        ("access_counts", t.access, ["cell_id", "category", "profile_id"], list(cfg.profiles)),
        (
            "transit_supply",
            t.transit,
            ["cell_id", "profile_id"],
            [p for p, prof in cfg.profiles.items() if prof.transit],
        ),
    ):
        per_cell = len(profiles) * (len(cfg.categories) if "category" in keys else 1)
        expected = len(cells) * per_cell
        problems = []
        if frame.duplicated(keys).any():
            problems.append(f"{int(frame.duplicated(keys).sum())} duplicate keys")
        if unknown := set(frame["cell_id"]) - cells:
            problems.append(f"{len(unknown)} unknown cells")
        if missing := cells - set(frame["cell_id"]):
            problems.append(f"{len(missing)} cells missing")
        if extra := set(frame["profile_id"]) - set(profiles):
            problems.append(f"unexpected profiles {sorted(extra)}")
        if "category" in keys and (
            extra := set(frame["category"]) - {c.id for c in cfg.categories}
        ):
            problems.append(f"unexpected categories {sorted(extra)}")
        if len(frame) != expected:
            problems.append(f"{len(frame)} rows, expected {expected}")
        out.append(
            Check(
                f"{name}_complete",
                "fail" if problems else "ok",
                float(len(frame)),
                "; ".join(problems) or f"{len(frame)} rows = {len(cells)} cells × {per_cell}",
            )
        )
    return out


def value_ranges(cfg: Config, t: Tables) -> list[Check]:
    """Counts ≥ 0; nearest time null exactly when nothing is reachable and within the budget."""
    b = cfg.time_budgets_min
    a, tr = t.access, t.transit
    problems = {
        "negative counts": int((a["count"] < 0).sum()),
        "nearest_min null but count > 0 (or set with count 0)": int(
            (a["nearest_min"].isna() != (a["count"] == 0)).sum()
        ),
        "nearest_min beyond the facility budget": int(
            (a["nearest_min"] > b.facilities + _ROUND_MIN).sum()
        ),
        "negative departures or stops": int(
            ((tr["departures"] < 0) | (tr["stops_count"] < 0)).sum()
        ),
        "nearest_stop_min null but stops_count > 0 (or set with no stop)": int(
            (tr["nearest_stop_min"].isna() != (tr["stops_count"] == 0)).sum()
        ),
        "departures without a stop": int(((tr["stops_count"] == 0) & (tr["departures"] > 0)).sum()),
        "nearest_stop_min beyond the transit budget": int(
            (tr["nearest_stop_min"] > b.transit + _ROUND_MIN).sum()
        ),
    }
    bad = {k: v for k, v in problems.items() if v}
    return [
        Check(
            "value_ranges",
            "fail" if bad else "ok",
            float(sum(bad.values())),
            "; ".join(f"{k}: {v} rows" for k, v in bad.items()) or "all counts and times in range",
        )
    ]


def thresholds_cover(t: Tables) -> list[Check]:
    """Every counted category has a k; the scores view would silently drop it otherwise."""
    k = scoring.category_k(t.thresholds)
    missing = sorted(set(t.access["category"]) - set(k.index))
    return [
        Check(
            "thresholds_cover_categories",
            "fail" if missing else "ok",
            float(len(missing)),
            f"categories without k: {missing}" if missing else f"k for {len(k)} categories",
        )
    ]


def reachable_matches_counts(t: Tables) -> list[Check]:
    """`reachable` joined with facilities gives exactly `access_counts.count` (the inspector
    reads the list, the map the counts; arch. §6.5 rule 8)."""
    keys = ["cell_id", "category", "profile_id"]
    derived = (
        t.reachable.merge(t.facilities[["facility_id", "category"]], on="facility_id")
        .groupby(keys)
        .size()
    )
    counted = t.access.set_index(keys)["count"]
    diff = counted - derived.reindex(counted.index, fill_value=0)
    extra = derived.index.difference(counted.index)
    # The table has no primary key (size), so its key is checked here.
    dupes = int(t.reachable.duplicated(["cell_id", "profile_id", "facility_id"]).sum())
    bad = int((diff != 0).sum()) + len(extra) + dupes
    problems = f"{bad - dupes} cell × category × profile rows differ, {dupes} duplicate pairs"
    return [
        Check(
            "reachable_matches_counts",
            "fail" if bad else "ok",
            float(bad),
            problems
            if bad
            else f"{len(t.reachable)} reachable pairs give all {len(counted)} counts",
        )
    ]


def route_sample(
    reachable: pd.DataFrame, budget_s: float, rc: RouteCheck, seed: int
) -> pd.DataFrame:
    """Pairs to compare with /route: per profile `pairs_per_profile`, a share of them close to
    the budget (deterministic for a given seed, e.g. derived from the run id)."""
    rng = np.random.default_rng(seed)
    parts = []
    for _, group in reachable.groupby("profile_id", sort=True):
        n_near = round(rc.pairs_per_profile * rc.near_budget_share)
        near = group[group["time_s"] >= rc.near_budget_share * budget_s]
        far = group.drop(near.index)
        for frame, n in ((near, n_near), (far, rc.pairs_per_profile - n_near)):
            if n and len(frame):
                idx = rng.choice(len(frame), size=min(n, len(frame)), replace=False)
                parts.append(frame.iloc[np.sort(idx)])
    cols = list(reachable.columns)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def route_check(pairs: pd.DataFrame, budget_s: float, rc: RouteCheck) -> tuple[Check, dict]:
    """Matrix time vs. /route time of the sampled pairs (`route_s`, NaN = no route).

    Known limitation, not an error: Valhalla's matrix (costmatrix) and /route search
    separately and can end on different paths of similar cost; `flips` = pairs the matrix
    counts within the budget but /route takes longer.
    """
    per_profile: dict[str, Any] = {}
    routed = pairs.dropna(subset=["route_s"])
    for pid, g in pairs.groupby("profile_id", sort=True):
        r = g.dropna(subset=["route_s"])
        d = (r["route_s"] - r["time_s"]).abs()
        per_profile[pid] = {
            "pairs": int(len(g)),
            "no_route": int(g["route_s"].isna().sum()),
            "mean_abs_s": round(float(d.mean()), 1) if len(d) else None,
            "max_abs_s": round(float(d.max()), 1) if len(d) else None,
            "flips": int((r["route_s"] > budget_s).sum()),
        }
    d_all = (routed["route_s"] - routed["time_s"]).abs()
    max_abs = float(d_all.max()) if len(d_all) else 0.0
    flips = int((routed["route_s"] > budget_s).sum())
    status = "warn" if max_abs > rc.warn_max_abs_s else "ok"
    message = (
        f"{len(pairs)} pairs ({int(pairs['route_s'].isna().sum())} without route): mean "
        f"|Δ| {d_all.mean() if len(d_all) else 0:.1f} s, max {max_abs:.0f} s "
        f"(warn > {rc.warn_max_abs_s:.0f} s), {flips} beyond the budget by /route "
        "(known limitation, see report)"
    )
    return Check("matrix_vs_route", status, round(max_abs, 1), message), per_profile


def class_rows(t: Tables) -> pd.DataFrame:
    """access_counts with population, k, class and deficit (Python mirror of `scores`)."""
    k = scoring.category_k(t.thresholds)
    a = t.access.merge(t.cells[["cell_id", "population", "district_id"]], on="cell_id")
    kk = a["category"].map(k).to_numpy(dtype=float)
    count = a["count"].to_numpy()
    pop = a["population"].to_numpy(dtype=float)
    return a.assign(k=kk, cls=scoring.classify(count, kk), deficit=scoring.deficit(pop, count, kk))


def totals(t: Tables, rows: pd.DataFrame, residents_scored: int | None) -> list[Check]:
    """Residents in the three classes = scored residents, per category × profile; every
    transit row gets a transit class."""
    total = int(t.cells["population"].sum())
    per = rows.groupby(["category", "profile_id"])["population"].sum()
    off = per[per != total]
    problems = [f"{c}/{p}: {int(v)}" for (c, p), v in off.items()]
    if residents_scored is not None and residents_scored != total:
        problems.insert(0, f"cells hold {total} residents, report part 1 says {residents_scored}")
    unclassified = int(
        pd.isna(scoring.transit_class(t.transit["departures"].to_numpy(), t.thresholds)).sum()
    )
    if unclassified:
        problems.append(f"{unclassified} transit rows without a class")
    return [
        Check(
            "class_totals",
            "fail" if problems else "ok",
            float(total),
            "; ".join(problems)
            or f"{total} residents in classes for each of {len(per)} category × profile pairs",
        )
    ]


def monotonic(pair: Monotonic, t: Tables) -> Check:
    """Share of cells where `pair.higher` reaches fewer facilities of any category (or fewer
    departures, if both profiles have transit) than `pair.lower`."""
    wide = t.access.pivot(index=["cell_id", "category"], columns="profile_id", values="count")
    worse = wide[pair.higher] < wide[pair.lower]
    bad_cells = set(worse[worse].index.get_level_values("cell_id"))
    examples = [f"{c}/{cat}" for c, cat in worse[worse].index[:5]]
    transit_pairs = 0
    if {pair.higher, pair.lower} <= set(t.transit["profile_id"]):
        tw = t.transit.pivot(index="cell_id", columns="profile_id", values="departures")
        tworse = tw[pair.higher] < tw[pair.lower]
        transit_pairs = int(tworse.sum())
        bad_cells |= set(tworse[tworse].index)
    n_cells = t.cells["cell_id"].nunique()
    share = len(bad_cells) / n_cells if n_cells else 0.0
    if pair.fail_above is not None and share > pair.fail_above:
        status = "fail"
    elif share > pair.warn_above:
        status = "warn"
    else:
        status = "ok"
    limits = f"warn > {pair.warn_above:.2%}" + (
        f", fail > {pair.fail_above:.2%}" if pair.fail_above is not None else ", never fails"
    )
    return Check(
        f"monotonic_{pair.higher}_ge_{pair.lower}",
        status,
        round(share, 6),
        f"{len(bad_cells)} of {n_cells} cells ({share:.2%}; {limits}): "
        f"{int(worse.sum())} cell × category pairs, {transit_pairs} transit rows"
        + (f"; e.g. {', '.join(examples)}" if examples else ""),
    )


def summary(t: Tables, rows: pd.DataFrame) -> dict[str, Any]:
    """Residents per class, deficit sum per profile × category; transit class shares."""
    total = float(t.cells["population"].sum()) or 1.0
    by = rows.pivot_table(
        index=["profile_id", "category"],
        columns="cls",
        values="population",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=list(scoring.CLASSES), fill_value=0)
    deficits = rows.groupby(["profile_id", "category"])["deficit"].sum()
    access: dict[str, dict[str, Any]] = {}
    for (profile, category), r in by.iterrows():
        access.setdefault(profile, {})[category] = {
            **{f"share_{c}": round(float(r[c]) / total, 4) for c in scoring.CLASSES},
            "residents_lack": int(r["lack"]),
            "deficit_sum": round(float(deficits[(profile, category)]), 1),
        }
    tr = t.transit.merge(t.cells[["cell_id", "population"]], on="cell_id")
    tr = tr.assign(cls=scoring.transit_class(tr["departures"].to_numpy(), t.thresholds))
    classes = list(t.thresholds.loc[t.thresholds["class"].notna(), "class"])
    transit = {
        profile: {
            c: round(float(g.loc[g["cls"] == c, "population"].sum()) / total, 4) for c in classes
        }
        for profile, g in tr.groupby("profile_id")
    }
    return {"residents_scored": int(total), "access": access, "transit": transit}


def samples(
    points: dict[str, tuple[float, float]], cells: pd.DataFrame, rows: pd.DataFrame
) -> list[dict[str, Any]]:
    """Values of the cell nearest to each sample point (x/y in EPSG:25832), for a manual check:
    count and class per category × profile."""
    xy = np.column_stack([cells["x"].to_numpy(), cells["y"].to_numpy()])
    out = []
    for name, (px, py) in points.items():
        i = int(np.argmin(np.hypot(xy[:, 0] - px, xy[:, 1] - py)))
        cell = cells.iloc[i]
        r = rows[rows["cell_id"] == cell["cell_id"]]
        out.append(
            {
                "sample": name,
                "cell_id": str(cell["cell_id"]),
                "district_id": None if pd.isna(cell["district_id"]) else str(cell["district_id"]),
                "population": int(cell["population"]),
                "values": {
                    f"{x.profile_id}/{x.category}": {
                        "count": int(x.count),
                        "class": str(x.cls),
                        "deficit": round(float(x.deficit), 2),
                    }
                    for x in r.itertuples(index=False)
                },
            }
        )
    return out
