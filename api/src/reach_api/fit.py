"""The fit, weekly travel time, areas and reasons (methodology §6, §7; data contract v1.1.0).

Per term the best of the student's modes; s = 1 / (1 + (T / (a·t))^p); fit = 100 · Σ w·s / Σ w;
campus = mean of the site times weighted by campus days, else the programme's sites, else the
default mix; grocery with favourites = the nearest of the chosen labels; sport and hobby
categories are their own terms and never count in the weekly time. Vectorised over all cells.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from reach_api.model import CAMPUS, MODES, Model


class ProfileError(ValueError):
    """The profile names something the published run does not know (HTTP 422)."""


@dataclass
class TermResult:
    key: str
    trip_window: str
    weight: float
    fine: float
    trips: float
    minutes: np.ndarray  # (n_cells,) float, NaN = unreachable
    mode: np.ndarray  # (n_cells,) mode index, -1 = none
    destination: np.ndarray  # (n_cells,) object
    departure: np.ndarray  # (n_cells,) object


def score(minutes: np.ndarray, fine: float, a: float, p: float) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        s = 1 / (1 + (minutes / (a * fine)) ** p)
    return np.where(np.isnan(minutes), 0.0, s)


def validate(model: Model, profile: dict[str, Any]) -> None:
    modes = profile.get("modes") or []
    unknown = sorted(set(modes) - set(model.modes))
    if not modes or unknown:
        raise ProfileError(
            f"modes: at least one of {model.modes}" + (f", unknown {unknown}" if unknown else "")
        )
    for key, v in (profile.get("destinations") or {}).items():
        if model.key_info(key) is None:
            raise ProfileError(f"destinations.{key}: unknown destination type or category")
        if v.get("importance") not in (0, 1, 2, 3):
            raise ProfileError(f"destinations.{key}.importance: 0–3")
    for label in (profile.get("labels") or {}).get("grocery") or []:
        if f"grocery:{label}" not in model.terms:
            raise ProfileError(f"labels.grocery: unknown supermarket {label}")
    prog = profile.get("programme")
    if prog and prog not in model.programmes.index:
        raise ProfileError(f"programme: unknown programme {prog}")
    for site in profile.get("campus_days") or {}:
        if site not in model.sites.index:
            raise ProfileError(f"campus_days: unknown campus site {site}")


def campus_weights(model: Model, profile: dict[str, Any]) -> list[tuple[str, float]]:
    days = {k: float(v) for k, v in (profile.get("campus_days") or {}).items() if v}
    if days:
        return list(days.items())
    prog = profile.get("programme")
    if prog:
        return [(s, 1.0) for s in model.programmes.at[prog, "sites"]]
    share = model.sites["default_share"]
    return [(s, float(w)) for s, w in share[share > 0].items()]


def _best(model: Model, terms: list[str], cols: list[int]) -> tuple[np.ndarray, ...]:
    """Minimum over the terms and the mode columns: minutes, mode index, destination, departure."""
    n = len(model.cell_ids)
    best = np.full(n, np.nan)
    mode = np.full(n, -1)
    dest = np.full(n, None, dtype=object)
    dep = np.full(n, None, dtype=object)
    rows = np.arange(n)
    for term in terms:
        t = model.terms.get(term)
        if t is None:
            continue
        sub = t.minutes[:, cols]
        filled = np.where(np.isnan(sub), np.inf, sub)
        j = filled.argmin(axis=1)
        m = filled[rows, j]
        better = np.isfinite(m) & (np.isnan(best) | (m < best))
        best = np.where(better, m, best)
        col = np.array(cols)[j]
        mode = np.where(better, col, mode)
        dest = np.where(better, t.destination[rows, col], dest)
        dep = np.where(better, t.departure[rows, col], dep)
    return best, mode, dest, dep


def term_results(model: Model, profile: dict[str, Any]) -> list[TermResult]:
    cols = model.mode_columns(profile["modes"])
    out = []
    for key, v in (profile.get("destinations") or {}).items():
        if not v.get("importance"):
            continue
        info = model.key_info(key)
        fine = float(v.get("fine_time_min") or info["fine_time_min"])
        trips = 0.0 if info["category"] else float(v.get("trips_per_week", info["trips_per_week"]))
        if key == CAMPUS:
            total, wsum = np.zeros(len(model.cell_ids)), np.zeros(len(model.cell_ids))
            parts = []
            for site, w in campus_weights(model, profile):
                b = _best(model, [f"{CAMPUS}/{site}"], cols)
                ok = ~np.isnan(b[0])
                total += np.where(ok, w * np.nan_to_num(b[0]), 0)
                wsum += np.where(ok, w, 0)
                parts.append(b)
            with np.errstate(invalid="ignore", divide="ignore"):
                minutes = np.where(wsum > 0, total / wsum, np.nan)
            stack = np.vstack([np.where(np.isnan(p[0]), np.inf, p[0]) for p in parts])
            k = stack.argmin(axis=0)
            rows = np.arange(len(model.cell_ids))
            mode = np.vstack([p[1] for p in parts])[k, rows]
            dest = np.vstack([p[2] for p in parts])[k, rows]
            dep = np.vstack([p[3] for p in parts])[k, rows]
        else:
            favs = (profile.get("labels") or {}).get("grocery") or []
            terms = [f"grocery:{f}" for f in favs] if key == "grocery" and favs else [key]
            minutes, mode, dest, dep = _best(model, terms, cols)
        out.append(
            TermResult(
                key,
                info["trip_window"],
                float(v["importance"]),
                fine,
                trips,
                minutes,
                mode,
                dest,
                dep,
            )
        )
    return out


def fit_arrays(
    results: list[TermResult], a: float, p: float
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Fit (0–100, NaN if no weight) and weekly minutes per cell, plus each term's score."""
    n = len(results[0].minutes) if results else 0
    wsum = sum(r.weight for r in results)
    scores = [score(r.minutes, r.fine, a, p) for r in results]
    if not wsum:
        return np.full(n, np.nan), np.full(n, np.nan), scores
    points = sum(r.weight * s for r, s in zip(results, scores, strict=True))
    weekly = sum(r.trips * 2 * np.nan_to_num(r.minutes) for r in results)
    return 100 * points / wsum, np.asarray(weekly, dtype=float), scores


def _mode(i: int) -> str | None:
    return MODES[i] if i >= 0 else None


def _minutes(x: float) -> int | None:
    return None if np.isnan(x) else int(round(x))


def reasons(
    model: Model, results: list[TermResult], scores: list[np.ndarray], ci: int
) -> list[dict]:
    """2–4 reasons for one cell (strengths s ≥ 0.75, one weakness s < 0.6, night reliability)."""

    def reason(kind: str, r: TermResult, value: Any = None) -> dict:
        dest = r.destination[ci]
        out = {
            "kind": kind,
            "destination_type": r.key,
            "name": None if r.key == CAMPUS or dest is None else model.names.get(dest) or None,
            "minutes": _minutes(r.minutes[ci]),
            "mode": _mode(int(r.mode[ci])),
            "trip_window": r.trip_window,
        }
        if value is not None:
            out["value"] = value
        return out

    scored = [(r, float(s[ci])) for r, s in zip(results, scores, strict=True)]
    strengths = sorted(
        (x for x in scored if x[1] >= 0.75),
        key=lambda x: (-x[0].weight, np.nan_to_num(x[0].minutes[ci])),
    )[:2]
    weak = sorted((x for x in scored if x[1] < 0.6), key=lambda x: -x[0].weight * (1 - x[1]))[:1]
    out = [reason("strength", r) for r, _ in strengths] + [reason("weakness", r) for r, _ in weak]
    for r, _ in scored:
        if r.trip_window == "night_return" and _mode(int(r.mode[ci])) == "transit":
            dep = r.departure[ci]
            if dep:
                out.append(reason("reliability", r, dep))
            break
    if len(out) < 2:
        used = {x["destination_type"] for x in out}
        rest = sorted((x for x in scored if x[0].key not in used), key=lambda x: -x[1])
        if rest:
            r, s = rest[0]
            out.append(reason("strength" if s >= 0.5 else "weakness", r))
    return out[:4]


def fit_parts(results: list[TermResult], scores: list[np.ndarray], ci: int) -> list[dict]:
    points = sum(r.weight * float(s[ci]) for r, s in zip(results, scores, strict=True))
    return [
        {
            "destination_type": r.key,
            "minutes": _minutes(r.minutes[ci]),
            "mode": _mode(int(r.mode[ci])),
            "score": round(float(s[ci]), 2),
            "weight": r.weight,
            "share": (r.weight * float(s[ci]) / points) if points else 0.0,
        }
        for r, s in zip(results, scores, strict=True)
    ]


def fit_response(model: Model, profile: dict[str, Any], a: float, p: float) -> dict[str, Any]:
    """Body of POST /api/fit."""
    validate(model, profile)
    results = term_results(model, profile)
    fit, weekly, scores = fit_arrays(results, a, p)
    cells = {
        cid: [
            None if np.isnan(f) else int(round(f)),
            None if np.isnan(w) else int(round(w)),
            int(pop),
        ]
        for cid, f, w, pop in zip(model.cell_ids, fit, weekly, model.populated, strict=True)
    }
    areas = []
    ok = model.populated & ~np.isnan(fit)
    for district in sorted({d for d in model.district[ok] if d is not None}):
        idx = np.flatnonzero(ok & (model.district == district))
        best = idx[np.argmax(fit[idx])]
        areas.append(
            {
                "area_id": district,
                "name": model.district_names.get(district, district),
                "fit": int(round(float(np.median(fit[idx])))),
                "best_cell_id": str(model.cell_ids[best]),
                "best_cell_fit": int(round(float(fit[best]))),
                "weekly_min": int(round(float(np.median(weekly[idx])))),
                "reasons": reasons(model, results, scores, int(best)),
            }
        )
    areas.sort(key=lambda x: (-x["fit"], -x["best_cell_fit"]))
    return {"run_id": model.run_id, "areas": areas, "cells": cells}


def cell_summary(
    model: Model, profile: dict[str, Any], cell_id: str, a: float, p: float
) -> dict[str, Any]:
    """Fit, weekly time, reasons and parts of one cell (the trips come from the database)."""
    validate(model, profile)
    ci = model.cell_index[cell_id]
    results = term_results(model, profile)
    fit, weekly, scores = fit_arrays(results, a, p)
    return {
        "fit": None if np.isnan(fit[ci]) else int(round(float(fit[ci]))),
        "weekly_min": None if np.isnan(weekly[ci]) else int(round(float(weekly[ci]))),
        "reasons": reasons(model, results, scores, ci),
        "fit_parts": fit_parts(results, scores, ci),
        "targets": targets(model, profile, results, ci),
    }


def targets(
    model: Model, profile: dict[str, Any], results: list[TermResult], ci: int
) -> dict[str, list[str]]:
    """Destinations listed in the cell detail per profile key: every weighted campus site, else
    each destination that is the best of the key's terms in some mode."""
    out: dict[str, list[str]] = {}
    for r in results:
        if r.key == CAMPUS:
            out[r.key] = [f"{CAMPUS}:{s}" for s, _ in campus_weights(model, profile)]
            continue
        favs = (profile.get("labels") or {}).get("grocery") or []
        terms = [f"grocery:{f}" for f in favs] if r.key == "grocery" and favs else [r.key]
        found = {d for t in terms if t in model.terms for d in model.terms[t].destination[ci] if d}
        out[r.key] = sorted(found)
    return out
