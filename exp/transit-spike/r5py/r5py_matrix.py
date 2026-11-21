"""T1 spike: transit travel-time matrices with r5py, with runtime and peak-memory logging.

Runs inside the spike image (r5py/Dockerfile). Modes:
  depart  - one matrix for departures in [departure, departure + window), given percentiles.
  arrive  - arrive-by emulation: one matrix per departure minute in [arrive - lookback, arrive),
            result = arrive - latest departure minute whose trip arrives in time.
  legs    - DetailedItineraries for the first N origin x destination pairs (legs, for reasons).
Inputs are CSV files with columns id, lon, lat (EPSG:4326).
"""

import argparse
import datetime as dt
import json
import logging
import pathlib
import resource
import sys
import time

import geopandas as gpd
import pandas as pd

log = logging.getLogger("r5py_spike")


def points(path: str) -> gpd.GeoDataFrame:
    df = pd.read_csv(path)
    return gpd.GeoDataFrame(
        {"id": df["id"].astype(str)}, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326"
    )


def cgroup_peak_mb() -> float | None:
    p = pathlib.Path("/sys/fs/cgroup/memory.peak")
    return round(int(p.read_text()) / 2**20, 1) if p.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", required=True)
    ap.add_argument("--gtfs", required=True)
    ap.add_argument("--origins", required=True)
    ap.add_argument("--destinations", required=True)
    ap.add_argument("--mode", choices=["depart", "arrive", "legs"], default="depart")
    ap.add_argument("--time", required=True, help="local ISO time, e.g. 2026-11-24T12:00")
    ap.add_argument("--window-min", type=int, default=10)
    ap.add_argument("--lookback-min", type=int, default=60)
    ap.add_argument("--percentiles", default="50")
    ap.add_argument("--access", default="WALK", help="WALK or BICYCLE")
    ap.add_argument("--max-pairs", type=int, default=500)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import r5py  # imported late: starts the JVM

    stats: dict = {"args": vars(a), "r5py": r5py.__version__}
    t0 = time.perf_counter()
    network = r5py.TransportNetwork(a.osm, [a.gtfs])
    stats["network_build_s"] = round(time.perf_counter() - t0, 1)
    origins, destinations = points(a.origins), points(a.destinations)
    stats["origins"], stats["destinations"] = len(origins), len(destinations)
    when = dt.datetime.fromisoformat(a.time)
    common = dict(
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        access_modes=[getattr(r5py.TransportMode, a.access)],
        egress_modes=[r5py.TransportMode.WALK],
        speed_walking=5.0,
        speed_cycling=15.0,
        max_time=dt.timedelta(minutes=90),
    )
    t1 = time.perf_counter()
    if a.mode == "depart":
        percentiles = [int(p) for p in a.percentiles.split(",")]
        result = r5py.TravelTimeMatrix(
            network, origins=origins, destinations=destinations, departure=when,
            departure_time_window=dt.timedelta(minutes=a.window_min), percentiles=percentiles,
            **common,
        )
        result = pd.DataFrame(result)
    elif a.mode == "arrive":
        best = None
        for k in range(a.lookback_min, 0, -1):
            dep = when - dt.timedelta(minutes=k)
            m = pd.DataFrame(r5py.TravelTimeMatrix(
                network, origins=origins, destinations=destinations, departure=dep,
                departure_time_window=dt.timedelta(minutes=1), **common,
            ))
            ok = m["travel_time"].notna() & (m["travel_time"] <= k)
            m = m.loc[ok, ["from_id", "to_id"]].assign(time_to_arrival_min=k)
            # later departures overwrite earlier ones: keep the latest feasible departure
            best = m if best is None else pd.concat([best, m]).drop_duplicates(
                ["from_id", "to_id"], keep="last")
        result = best
    else:
        pairs = origins.merge(destinations, how="cross", suffixes=("_o", "_d")).head(a.max_pairs)
        o = gpd.GeoDataFrame({"id": [f"o{i}" for i in range(len(pairs))]}, geometry=pairs.geometry_o.values, crs="EPSG:4326")
        d = gpd.GeoDataFrame({"id": [f"d{i}" for i in range(len(pairs))]}, geometry=pairs.geometry_d.values, crs="EPSG:4326")
        result = pd.DataFrame(r5py.DetailedItineraries(
            network, origins=o, destinations=d, departure=when,
            departure_time_window=dt.timedelta(minutes=a.window_min), **common,
        ))
        stats["pairs"] = len(pairs)
    stats["compute_s"] = round(time.perf_counter() - t1, 1)
    stats["rows"] = int(len(result))
    if "travel_time" in result:
        stats["reachable_share"] = round(float(result["travel_time"].notna().mean()), 4)
    result.drop(columns=[c for c in ("geometry",) if c in result], errors="ignore").to_parquet(a.out)
    stats["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    stats["cgroup_peak_mb"] = cgroup_peak_mb()
    log.info("stats %s", json.dumps(stats, default=str))
    pathlib.Path(a.out).with_suffix(".json").write_text(json.dumps(stats, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
