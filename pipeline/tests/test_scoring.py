"""Scoring rules (methodology §3–4): thresholds table, classes, deficits, transit classes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from reach_pipeline import scoring
from reach_pipeline.config import load_config

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def thr() -> pd.DataFrame:
    return scoring.thresholds(load_config(REPO / "config" / "config.yaml"))


def test_thresholds_table(thr: pd.DataFrame) -> None:
    cfg = load_config(REPO / "config" / "config.yaml")
    assert list(thr.columns) == scoring.THRESHOLD_COLUMNS
    cats = thr[thr["class"].isna()]
    assert dict(zip(cats["category"], cats["k"], strict=True)) == {
        c.id: c.k for c in cfg.categories
    }
    assert cats[["lower", "upper"]].isna().all().all()
    transit = thr[thr["category"] == "transit"]
    assert list(transit["class"]) == ["lack", "insufficient", "medium", "high"]
    assert transit["k"].isna().all()
    assert pd.isna(transit["upper"].iloc[-1])
    assert str(thr["k"].dtype) == "Int64"


def test_classes_and_deficits() -> None:
    count = np.array([0, 1, 2, 3, 0, 1, 5])
    k = np.array([2, 2, 2, 2, 1, 1, 1], dtype=float)
    pop = np.full(len(count), 10.0)
    assert list(scoring.classify(count, k)) == [
        "lack",
        "insufficient",
        "sufficient",
        "sufficient",
        "lack",
        "sufficient",
        "sufficient",
    ]
    assert list(scoring.deficit(pop, count, k)) == [10.0, 5.0, 0.0, 0.0, 10.0, 0.0, 0.0]


def test_transit_class_bounds_inclusive(thr: pd.DataFrame) -> None:
    departures = np.array([0, 1, 150, 151, 1000, 1001, 50_000])
    assert list(scoring.transit_class(departures, thr)) == [
        "lack",
        "insufficient",
        "insufficient",
        "medium",
        "medium",
        "high",
        "high",
    ]
