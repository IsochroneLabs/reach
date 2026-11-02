"""Golden travel times: cell → facility pairs on the test clip against a local Valhalla.

Run with the test clip tiles served (`make refresh REACH_CONFIG=config/test_clip.yaml`), then
`uv run pytest -m integration`. The pairs lie along almost straight streets in the old town;
the expected time is the map distance ÷ the profile speed. The map distance is the straight line
between cell origin and facility (EPSG:25832, rounded to metres); the pairs are listed with map
links in the P3 PR for a manual check. The straight line is a lower bound, so Valhalla may be up
to `SLACK` slower (street geometry, crossings) and slightly faster (the snap distance is not
counted, arch. §6.3).
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import httpx
import numpy as np
import pytest

from reach_pipeline.config import load_config
from reach_pipeline.valhalla.client import ValhallaClient, costing_options, resolve_url

pytestmark = pytest.mark.integration

CONFIG = Path(__file__).resolve().parents[2] / "config" / "test_clip.yaml"
FAST, SLACK = 0.95, 1.20

# (name, profile, origin [lon, lat] = cell origin, target [lon, lat] = facility, map distance m)
PAIRS = [
    (
        "CRS3035RES100mN2823100E4251100 -> Wildermuth-Gymnasium (school, w328584407)",
        "walking_339",
        (9.05484, 48.51775),
        (9.04832, 48.51565),
        535,
    ),
    (
        "CRS3035RES100mN2823200E4250800 -> doctor Katrin Klingler (n14100617591)",
        "walking_339",
        (9.05076, 48.51862),
        (9.05458, 48.52024),
        335,
    ),
    (
        "CRS3035RES100mN2822900E4251400 -> EDEKA Schöck over the Eberhardsbrücke (n129986942)",
        "walking_339",
        (9.05893, 48.51599),
        (9.05669, 48.52220),
        710,
    ),
    (
        "same pair at 5.0 km/h",
        "walking_500",
        (9.05893, 48.51599),
        (9.05669, 48.52220),
        710,
    ),
    (
        "CRS3035RES100mN2823600E4251300 -> doctors Barthlen et al. (n2392727756)",
        "walking_339",
        (9.05746, 48.52227),
        (9.05818, 48.51708),
        579,
    ),
]


@pytest.fixture(scope="module", autouse=True)
def clip_tiles_served() -> None:
    """The expected times assume the clip tiles (no elevation, C6); slopes change walking times
    (notes N5), so fail clearly if Valhalla serves another tile set."""
    cfg = load_config(CONFIG)
    tar = Path(cfg.data_dir) / "valhalla" / "valhalla_tiles.tar"
    try:
        status = httpx.get(f"{resolve_url(cfg.valhalla)}/status", timeout=10).json()
    except httpx.HTTPError as exc:
        pytest.fail(f"Valhalla not reachable ({exc}); run `make refresh REACH_CONFIG={CONFIG}`")
    if not tar.exists() or int(tar.stat().st_mtime) != status.get("tileset_last_modified"):
        pytest.fail(
            "Valhalla does not serve the test clip tiles; "
            "run `make up REACH_CONFIG=config/test_clip.yaml`"
        )


async def _time(profile_id: str, origin: tuple, target: tuple) -> float:
    cfg = load_config(CONFIG)
    profile = cfg.profiles[profile_id]
    async with ValhallaClient(cfg.valhalla) as client:
        times = await client.matrix(
            np.array([origin]), np.array([target]), profile.costing, costing_options(profile)
        )
    return float(times[0, 0])


@pytest.mark.parametrize(("name", "profile_id", "origin", "target", "map_m"), PAIRS)
def test_golden_pair(name: str, profile_id: str, origin: tuple, target: tuple, map_m: float):
    speed_ms = load_config(CONFIG).profiles[profile_id].speed_kmh / 3.6
    expected_s = map_m / speed_ms
    actual_s = asyncio.run(_time(profile_id, origin, target))
    assert not math.isnan(actual_s), f"{name}: unreachable"
    assert FAST * expected_s <= actual_s <= SLACK * expected_s, (
        f"{name}: {actual_s:.0f} s, expected {expected_s:.0f} s "
        f"({FAST}–{SLACK} × {map_m} m at {speed_ms * 3.6} km/h)"
    )
