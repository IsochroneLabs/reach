"""Scoring rules of methodology §3–4, shared by `score` and `validate_results`.

The database derives classes and deficits at read time (`scores`, `transit_scores` views in
`infra/db/run_schema.sql`); the pipeline only stores thresholds. The Python versions below are
used for the validation report (totals) and must give the same result as the views (tested in
`tests/test_db_contract.py`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from reach_pipeline.config import TRANSIT_CATEGORY, Config

CLASSES = ("lack", "insufficient", "sufficient")
THRESHOLD_COLUMNS = ["category", "k", "class", "lower", "upper"]


def thresholds(cfg: Config) -> pd.DataFrame:
    """`thresholds` table: one row per category (k) and per transit class (bounds)."""
    rows = [
        {"category": c.id, "k": c.k, "class": None, "lower": None, "upper": None}
        for c in cfg.categories
    ]
    rows += [
        {
            "category": TRANSIT_CATEGORY,
            "k": None,
            "class": t.name,
            "lower": t.lower,
            "upper": t.upper,
        }
        for t in cfg.transit_classes
    ]
    frame = pd.DataFrame(rows, columns=THRESHOLD_COLUMNS)
    for col in ("k", "lower", "upper"):
        frame[col] = frame[col].astype("Int64")
    frame["class"] = frame["class"].astype("string")
    return frame


def category_k(thr: pd.DataFrame) -> pd.Series:
    """k per category (index = category id)."""
    rows = thr[thr["class"].isna()]
    return rows.set_index("category")["k"].astype(np.int64)


def classify(count: np.ndarray, k: np.ndarray) -> np.ndarray:
    """lack (A = 0), insufficient (0 < A < k), sufficient (A >= k)."""
    return np.select([count == 0, count < k], ["lack", "insufficient"], "sufficient")


def deficit(population: np.ndarray, count: np.ndarray, k: np.ndarray) -> np.ndarray:
    """U = P * max(0, 1 - A / k)."""
    return population * np.maximum(0.0, 1.0 - count / k)


def transit_class(departures: np.ndarray, thr: pd.DataFrame) -> np.ndarray:
    """Transit class of each departure sum (bounds inclusive, upper null = open-ended)."""
    rows = thr[thr["category"] == TRANSIT_CATEGORY].sort_values("lower")
    out = np.full(len(departures), None, dtype=object)
    for name, lower, upper in zip(rows["class"], rows["lower"], rows["upper"], strict=True):
        top = np.inf if pd.isna(upper) else upper
        out[(departures >= lower) & (departures <= top)] = name
    return out
