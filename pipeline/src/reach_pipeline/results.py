"""Checks of the results (validation report part 2): pure functions on the count/score tables.

Monotonicity, completeness, value ranges and totals (arch. §7 "validate results"); used by
`stages/validate_results.py`. Checks return `Check` rows of the `validation_report` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely

from reach_pipeline import recommend, scoring
from reach_pipeline.config import BudgetFlips, Config, FalseNegativeCheck, Monotonic, RouteCheck

STAGE = "validate_results"
# nearest_min is rounded to 0.01 min by count.
_ROUND_MIN = 0.01
# population_gain is rounded to 0.01 residents by recommend.
_ROUND_GAIN = 0.011


@dataclass
class Tables:
    cells: pd.DataFrame  # cell_id, population, district_id
    access: pd.DataFrame  # access_counts
    transit: pd.DataFrame  # transit_supply
    thresholds: pd.DataFrame
    reachable: pd.DataFrame | None = None  # cell_id, profile_id, facility_id, time_s
    facilities: pd.DataFrame | None = None  # facility_id, category
    recommendations: pd.DataFrame | None = None  # recommend stage (without geometries)
    recommendation_catchments: pd.DataFrame | None = None  # candidate_id, profile_id, cell_id


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
    no_route = int(pairs["route_s"].isna().sum())
    # Pairs come from `reachable`, so the matrix found a path: many pairs without a route mean
    # the comparison itself is not meaningful.
    status = "warn" if max_abs > rc.warn_max_abs_s or no_route * 2 > len(pairs) else "ok"
    message = (
        f"{len(pairs)} pairs ({no_route} without route): mean "
        f"|Δ| {d_all.mean() if len(d_all) else 0:.1f} s, max {max_abs:.0f} s "
        f"(warn > {rc.warn_max_abs_s:.0f} s), {flips} beyond the budget by /route "
        "(known limitation, see report)"
    )
    return Check("matrix_vs_route", status, round(max_abs, 1), message), per_profile


def false_negative_candidates(
    origins_xy: np.ndarray,
    cell_ids: np.ndarray,
    points_xy: np.ndarray,
    point_facility: np.ndarray,
    facilities: pd.DataFrame,
    reachable: pd.DataFrame,
    reach_m: float,
) -> pd.DataFrame:
    """Cell × facility pairs of one profile that the count matrix had as targets but did not
    find within the budget: a routing point lies within `reach_m` (straight line, the count
    prefilter) of the cell origin and the pair is not in `reachable` (rows of this profile).

    Returns `cell_id`, `facility_id`, `category` (one row per category of the facility) and
    `distance_m` (straight line to the nearest routing point), all in EPSG:25832.
    """
    cols = ["cell_id", "facility_id", "category", "distance_m"]
    if len(origins_xy) == 0 or len(points_xy) == 0:
        return pd.DataFrame(columns=cols)
    tree = shapely.STRtree(shapely.points(points_xy))
    o_idx, p_idx = tree.query(shapely.points(origins_xy), predicate="dwithin", distance=reach_m)
    fac_codes, uniques = pd.factorize(point_facility)
    fac_ids = pd.Index(uniques)
    pairs = pd.DataFrame(
        {
            "cell": o_idx.astype(np.int32),
            "fac": fac_codes[p_idx].astype(np.int32),
            "distance_m": np.hypot(*(origins_xy[o_idx] - points_xy[p_idx]).T),
        }
    )
    pairs = pairs.groupby(["cell", "fac"], sort=False, as_index=False)["distance_m"].min()
    cell_pos = pd.Series(np.arange(len(cell_ids)), index=cell_ids)
    found = pd.DataFrame(
        {
            "cell": cell_pos.reindex(reachable["cell_id"]).to_numpy(),
            "fac": fac_ids.get_indexer(reachable["facility_id"]),
            "hit": True,
        }
    ).dropna()
    found = found.astype({"cell": np.int32, "fac": np.int32})
    pairs = pairs.merge(found, on=["cell", "fac"], how="left")
    pairs = pairs[pairs["hit"].isna()]
    out = pd.DataFrame(
        {
            "cell_id": cell_ids[pairs["cell"].to_numpy()],
            "facility_id": np.asarray(fac_ids)[pairs["fac"].to_numpy()],
            "distance_m": pairs["distance_m"].to_numpy(),
        }
    )
    return out.merge(facilities[["facility_id", "category"]], on="facility_id")[cols]


def false_negative_sample(
    candidates: pd.DataFrame, per_category: int, rng: np.random.Generator
) -> pd.DataFrame:
    """Up to `per_category` random candidate pairs per category (sorted, deterministic for a
    given generator state)."""
    parts = []
    for _, group in candidates.groupby("category", sort=True):
        if per_category and len(group):
            idx = rng.choice(len(group), size=min(per_category, len(group)), replace=False)
            parts.append(group.iloc[np.sort(idx)])
    return pd.concat(parts, ignore_index=True) if parts else candidates.iloc[:0]


def false_negative_check(
    pairs: pd.DataFrame, budget_s: float, fc: FalseNegativeCheck
) -> tuple[Check, dict[str, Any]]:
    """Share of sampled non-reachable pairs that /route reaches within the budget (`route_s`,
    NaN = no route; columns `profile_id`, `category`, `cell_id`, `facility_id`, `distance_m`).

    Warns above `fc.warn_above`, fails above `fc.fail_above` (share of the whole sample);
    per profile and category the sample size, routes and false negatives are reported.
    """
    missed = pairs["route_s"].le(budget_s)  # NaN (no route) compares False
    per_profile: dict[str, Any] = {}
    for (pid, cat), g in pairs.groupby(["profile_id", "category"], sort=True):
        m = missed.loc[g.index]
        per_profile.setdefault(pid, {})[cat] = {
            "pairs": int(len(g)),
            "no_route": int(g["route_s"].isna().sum()),
            "false_negatives": int(m.sum()),
            "rate": round(float(m.mean()), 4) if len(g) else 0.0,
        }
    n, k = len(pairs), int(missed.sum())
    rate = k / n if n else 0.0
    status = "fail" if rate > fc.fail_above else "warn" if rate > fc.warn_above else "ok"
    examples = pairs[missed].sort_values("route_s").head(20)
    message = (
        f"{n} sampled pairs within the prefilter reach not in reachable: {k} reach the "
        f"facility within the budget by /route ({rate:.1%}; warn > {fc.warn_above:.1%}, "
        f"fail > {fc.fail_above:.1%})"
    )
    detail = {
        "budget_s": budget_s,
        "pairs": n,
        "false_negatives": k,
        "rate": round(rate, 4),
        "profiles": per_profile,
        "examples": [
            {
                "profile_id": r.profile_id,
                "category": r.category,
                "cell_id": r.cell_id,
                "facility_id": r.facility_id,
                "distance_m": round(float(r.distance_m), 1),
                "route_s": round(float(r.route_s), 1),
            }
            for r in examples.itertuples()
        ],
    }
    return Check("false_negatives", status, round(rate, 4), message), detail


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


def budget_flips(
    route: dict[str, Any], missed: dict[str, Any], bf: BudgetFlips
) -> tuple[Check, dict[str, Any]]:
    """Share of sampled pairs on which matrix and /route lie on different sides of the budget,
    per profile and direction (methodology V10), from the details of `route_check` (pairs in
    `reachable`: matrix within, /route beyond) and `false_negative_check` (pairs not in
    `reachable`: matrix beyond, /route within). Rates are over pairs with a route; the two
    samples differ (near the budget vs. uniform within the prefilter reach), so the directions
    are not comparable with each other. Known limitation: warns, never fails.
    """
    per_profile: dict[str, Any] = {}
    for pid in sorted(set(route["profiles"]) | set(missed["profiles"])):
        r = route["profiles"].get(pid, {"pairs": 0, "no_route": 0, "flips": 0})
        cats = missed["profiles"].get(pid, {}).values()
        m_routed = sum(v["pairs"] - v["no_route"] for v in cats)
        m_flips = sum(v["false_negatives"] for v in cats)
        r_routed = r["pairs"] - r["no_route"]
        per_profile[pid] = {
            "within_to_beyond": {
                "routed": r_routed,
                "flips": r["flips"],
                "rate": round(r["flips"] / r_routed, 4) if r_routed else 0.0,
            },
            "beyond_to_within": {
                "routed": m_routed,
                "flips": m_flips,
                "rate": round(m_flips / m_routed, 4) if m_routed else 0.0,
            },
        }
    rates = [d["rate"] for v in per_profile.values() for d in v.values()]
    worst = max(rates, default=0.0)
    above = [
        f"{pid} {direction} {d['rate']:.1%}"
        for pid, v in per_profile.items()
        for direction, d in v.items()
        if d["rate"] > bf.warn_above
    ]
    message = (
        f"highest flip rate {worst:.1%} (warn > {bf.warn_above:.1%})"
        + (f": {', '.join(above)}" if above else "")
        + "; matrix within/route beyond from the route_check sample, matrix beyond/route "
        "within from the false_negatives sample (known limitation, see report)"
    )
    check = Check("budget_flips", "warn" if above else "ok", round(worst, 4), message)
    return check, {"warn_above": bf.warn_above, "profiles": per_profile}


def recommendations_consistent(cfg: Config, t: Tables) -> Check:
    """Recommendations (methodology §5) agree with the counts and their stored catchments:
    ranks 1..n ≤ `top_n` per category × profile, only `recommend.profiles`, each zone once,
    gains ≥ `min_gain`, and gain, residents gaining access and residents reaching "sufficient"
    recomputed by adding the picks one after the other to `access_counts`."""
    recs, rc = t.recommendations, t.recommendation_catchments
    r = cfg.recommend
    if recs is None or rc is None:
        return Check("recommendations_consistent", "fail", None, "recommend outputs missing")
    k = {c.id: c.k for c in cfg.categories}
    pop = t.cells.set_index("cell_id")["population"]
    problems: list[str] = []
    if extra := sorted(set(recs["profile_id"]) - set(r.profiles)):
        problems.append(f"profiles not in recommend.profiles: {extra}")
    if (recs["population_gain"] < r.min_gain).any():
        problems.append(f"gains below min_gain {r.min_gain}")
    for (cat, pid), group in recs.groupby(["category", "profile_id"]):
        group = group.sort_values("rank")
        name = f"{cat}/{pid}"
        if group["rank"].tolist() != list(range(1, len(group) + 1)) or len(group) > r.top_n:
            problems.append(f"{name}: ranks {group['rank'].tolist()}")
            continue
        if not group["candidate_id"].is_unique:
            problems.append(f"{name}: a zone is recommended twice")
        mine = rc[rc["profile_id"] == pid]
        cells = [mine.loc[mine["candidate_id"] == c, "cell_id"] for c in group["candidate_id"]]
        if [len(c) for c in cells] != group["catchment_cells"].tolist() or [
            int(pop.reindex(c).sum()) for c in cells
        ] != group["catchment_residents"].tolist():
            problems.append(f"{name}: catchment cells or residents differ from the catchments")
            continue
        a = t.access[(t.access["category"] == cat) & (t.access["profile_id"] == pid)]
        a = a.set_index("cell_id")["count"].reindex(pop.index, fill_value=0)
        index = [pop.index.get_indexer(c) for c in cells]
        stored = list(
            zip(
                group["population_gain"],
                group["residents_gaining_access"],
                group["residents_to_sufficient"],
                strict=True,
            )
        )
        replayed = recommend.replay(index, pop.to_numpy(), a.to_numpy(), k[cat])
        if any(
            abs(g - rg) > _ROUND_GAIN or (ga, ts) != (rga, rts)
            for (g, ga, ts), (rg, rga, rts) in zip(stored, replayed, strict=True)
        ):
            problems.append(f"{name}: gains differ from a replay on access_counts")
    n = len(recs)
    return Check(
        "recommendations_consistent",
        "fail" if problems else "ok",
        float(n),
        "; ".join(problems[:5])
        if problems
        else f"{n} recommendations for {sorted(set(recs['profile_id']))} agree with the counts "
        "and their catchments",
    )
