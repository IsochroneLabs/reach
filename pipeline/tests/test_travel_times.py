"""Travel-time stage on small synthetic inputs (no engine: a fake Valhalla, a fake OTP)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
from shapely.geometry import Point

from reach_pipeline import otp
from reach_pipeline.config import load_config
from reach_pipeline.stages import travel_times as tt
from reach_pipeline.stages import validate_results as vr
from reach_pipeline.valhalla.client import ValhallaClient

REPO = Path(__file__).resolve().parents[2]
CRS = "EPSG:25832"
X0, Y0 = 500_000, 5_375_000


def _cfg():
    return load_config(REPO / "config" / "config.yaml")


def _inputs() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    origins = gpd.GeoDataFrame(
        {"cell_id": ["c1", "c2"]}, geometry=[Point(X0, Y0), Point(X0 + 2000, Y0)], crs=CRS
    )
    rows = [
        ("grocery:n1", "grocery", "grocery:n1", X0 + 100, Y0),
        ("grocery:n2", "grocery", "grocery:n2", X0 + 1900, Y0),
        ("park:w1", "park", "park:w1", X0 + 500, Y0),
        ("park:w1", "park", "park:w1#1", X0 + 600, Y0),
        ("nightlife:n3", "nightlife", "nightlife:n3", X0 + 1000, Y0),
        ("campus_site:tal", "campus_site", "campus_site:tal", X0 + 3000, Y0),
        ("grocery:edeka:n1", "grocery", "grocery:edeka:n1", X0 + 100, Y0),
    ]
    points = gpd.GeoDataFrame(
        {
            "destination_id": [r[0] for r in rows],
            "destination_type": [r[1] for r in rows],
            "point_id": [r[2] for r in rows],
        },
        geometry=[Point(r[3], r[4]) for r in rows],
        crs=CRS,
    )
    return origins, points


def test_pairs_windows_and_candidates() -> None:
    cfg = _cfg()
    origins, points = _inputs()
    base, tpairs = tt.select_pairs(origins, points, cfg)
    # every destination is within k of both cells (few destinations)
    assert len(base) == 2 * 6
    assert set(base.merge(tpairs, on=["cell_id", "destination_id"])["cell_id"]) == {"c1", "c2"}
    w = tt.windows_of(points, cfg)
    assert w["nightlife:n3"] == "night_return" and w["campus_site:tal"] == "morning_lecture"


def test_valhalla_blocks_directions_and_park_minimum() -> None:
    cfg = _cfg()
    origins, points = _inputs()
    base, _ = tt.select_pairs(origins, points, cfg)
    w = tt.windows_of(points, cfg)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((len(body["sources"]), len(body["targets"])))
        # time = longitude difference × 1e5: the nearer park access point gives the minimum
        d = [
            [round(abs(t["lon"] - src["lon"]) * 1e5) for t in body["targets"]]
            for src in body["sources"]
        ]
        return httpx.Response(200, json={"sources_to_targets": {"durations": d}})

    async def go() -> pd.DataFrame:
        async with ValhallaClient(cfg.valhalla, "http://v", httpx.MockTransport(handler)) as c:
            return await tt._valhalla_mode(
                c, base, origins, points, w, {"night_return"}, "walk", cfg
            )

    out = asyncio.run(go())
    assert len(out) == len(base) and out["time_s"].notna().all()
    # the night window routes from the destination: one source (the bar), cells as targets
    assert (1, 1) in seen
    park = out[(out["destination_id"] == "park:w1") & (out["cell_id"] == "c1")]["time_s"].item()
    lon = tt._lonlat(points.geometry)[:, 0]
    c1 = tt._lonlat(origins.geometry)[0, 0]
    assert park == round(abs(lon[2] - c1) * 1e5)  # the 500 m point, not the 600 m one


def test_otp_dedupes_points_and_caps_by_walk() -> None:
    cfg = _cfg().model_copy()
    origins, points = _inputs()
    _, tpairs = tt.select_pairs(origins, points, cfg)
    w = tt.windows_of(points, cfg)
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "otp" / "depart_at_night.json").read_text()
    )["response"]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=fixture)

    refs = {k: pd.Timestamp("2026-11-28").date() for k in cfg.trip_windows}

    async def go() -> pd.DataFrame:
        async with otp.OtpClient(cfg.otp, "http://o", httpx.MockTransport(handler)) as c:
            return await tt._otp_mode(c, tpairs, origins, points, w, refs, "transit", cfg)

    tr = asyncio.run(go())
    assert len(tr) == len(tpairs)
    # grocery:n1 and grocery:edeka:n1 share a point: one query per cell for both
    assert calls["n"] == len(tpairs) - 2
    # the recorded answer is for 00:30; other windows give odd times, so fix the time here
    tr = tr.assign(time_s=1000.0)
    walk = tr[["cell_id", "destination_id"]].assign(time_s=60.0)
    capped = tt.cap_by_walk(tr, walk)
    assert capped["walk_only"].all() and capped["first_stop"].isna().all()
    final = tt.finish(capped)
    assert list(final.columns) == tt.COLUMNS and str(final["time_s"].dtype) == "Int32"


def test_result_checks() -> None:
    cfg = _cfg()
    pairs = pd.DataFrame({"cell_id": ["c1"], "destination_id": ["campus_site:tal"]})
    cells = pd.DataFrame({"cell_id": ["c1", "c2"], "populated": [True, False]})
    rows = [
        ("walk", 900, None, False),
        ("bike", 300, None, False),
        ("transit", 600, [60, 120, 360, 60], False),
    ]
    times = pd.DataFrame(
        [
            {
                "cell_id": "c1",
                "destination_id": "campus_site:tal",
                "mode": m,
                "trip_window": "morning_lecture",
                "time_s": t,
                "access_s": legs[0] if legs else np.nan,
                "wait_s": legs[1] if legs else np.nan,
                "in_vehicle_s": legs[2] if legs else np.nan,
                "egress_s": legs[3] if legs else np.nan,
                "walk_only": wo,
            }
            for m, t, legs, wo in rows
        ]
    )
    dist = pd.Series([3000.0], index=pd.MultiIndex.from_frame(pairs))
    status = {c.check: c.status for c in vr.checks(times, pairs, cells, dist, cfg)}
    assert set(status.values()) == {"ok"}, status
    fast = times.assign(time_s=[900, 300, 60])  # 3 km in 1 min by bus
    status = {c.check: c.status for c in vr.checks(fast, pairs, cells, dist, cfg)}
    assert status["transit_speed"] == "fail" and status["transit_legs_add_up"] == "warn"
