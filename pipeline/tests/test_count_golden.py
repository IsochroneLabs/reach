"""Golden examples of notes N9: facilities reported as missed by the count, replayed from the
recorded count block requests (Valhalla 3.9.1, costmatrix, Tübingen tiles with elevation).

The block matrix gives the same time as /route (±1 s), so the count decides like /route: uphill
the three facilities take more than 15 minutes at 3.39 km/h and are not counted, at 5.0 km/h
they are. The route length ÷ speed (740–894 s, the numbers in N9) is within the budget: the
difference is Valhalla's slope model for walking (notes N5), not the matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest
import respx

from reach_pipeline import count
from reach_pipeline.config import load_config
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "valhalla" / "n9_block_examples.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
# Expected decision per profile: counted within the 15-minute budget?
COUNTED = {"walking_339": False, "walking_500": True}


def _lonlat(locations: list[dict[str, float]]) -> np.ndarray:
    return np.array([[p["lon"], p["lat"]] for p in locations])


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['facility_id']}-{c['profile_id']}")
async def test_n9_example_is_counted_like_route(
    case: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VALHALLA_URL", raising=False)
    cfg = load_config(REPO / "config" / "config.yaml")
    vcfg = cfg.valhalla.model_copy(update={"url": "http://valhalla.test"})
    profile = cfg.profiles[case["profile_id"]]
    budget_s = cfg.time_budgets_min.facilities * 60

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["sources"] == case["request"]["sources"]  # the recorded count request
        assert body["targets"] == case["request"]["targets"]
        assert body["costing_options"] == costing_options(profile)
        return httpx.Response(200, json={"sources_to_targets": {"durations": case["durations"]}})

    async with ValhallaClient(vcfg) as client:
        with respx.mock(base_url="http://valhalla.test") as router:
            router.post("/sources_to_targets").mock(side_effect=answer)
            times = await client.matrix(
                _lonlat(case["request"]["sources"]),
                _lonlat(case["request"]["targets"]),
                profile.costing,
                costing_options(profile),
            )
    links = pd.DataFrame(
        {"target": case["targets"], "facility_id": case["facility_id"], "category": "x"}
    )
    reachable = count.reachable_block(times, links, budget_s)
    counted = bool((reachable["source"] == case["source"]).any())

    route_s = min(r["time_s"] for r in case["routes"])
    assert abs(np.nanmin(times[case["source"], case["targets"]]) - route_s) <= 1
    assert counted == (route_s <= budget_s) == COUNTED[case["profile_id"]]
    # Without the slope model (length ÷ speed) every example would be within the budget.
    flat_s = min(r["length_m"] for r in case["routes"]) / (profile.speed_kmh / 3.6)
    assert flat_s <= budget_s < route_s or counted
