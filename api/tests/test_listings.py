"""Listing endpoints on canned rows and the hand-made model of test_fit.py (no database)."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from reach_api import listings as lst
from reach_api.main import create_app

from .conftest import FakeDatabase, make_deps
from .test_fit import PROFILE, _model

ROW = {
    "listing_id": "wg_gesucht:90000001",
    "source_url": "https://www.wg-gesucht.de/wg-zimmer-in-Tuebingen-Innenstadt.90000001.html",
    "kind": "wg_room",
    "title": "Room",
    "rent_total_eur": 450,
    "size_m2": 14.0,
    "cell_id": "A",
    "lon": 9.05,
    "lat": 48.52,
    "first_seen": "2026-11-27",
}


class ListingDb(FakeDatabase):
    def __init__(self, published: bool) -> None:
        super().__init__()
        self.published = published

    async def fetch(self, query: str, params: Any = None) -> list[dict[str, Any]]:
        if query == lst.Q_EXISTS:
            return [{"ok": self.published}]
        if query == lst.Q_LISTINGS:
            return [
                ROW,
                dict(ROW, listing_id="wg_gesucht:90000002", cell_id="B", rent_total_eur=380),
            ]
        return []


def _client(published: bool) -> TestClient:
    deps = make_deps(ListingDb(published))
    deps.models._model = _model()
    deps.models._checked = time.monotonic() + 3600
    client = TestClient(create_app(deps))
    client.__enter__()
    return client


def test_listings_and_fit_sorted_by_cell_fit() -> None:
    c = _client(True)
    items = c.get("/api/listings").json()
    assert len(items) == 2 and items[0]["point"] == [9.05, 48.52] and items[0]["approximate"]
    fit = c.post("/api/listings/fit", json=PROFILE).json()
    assert [x["cell_id"] for x in fit] == ["A", "B"] and fit[0]["fit"] == 90
    assert c.post("/api/listings/fit", json=dict(PROFILE, modes=["bike"])).status_code == 422


def test_no_snapshot_is_an_empty_list() -> None:
    c = _client(False)
    assert c.get("/api/listings").json() == []
    assert c.post("/api/listings/fit", json=PROFILE).json() == []
