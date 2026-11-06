"""V11 with vs. without slopes: counts on the production tiles (with elevation) vs. a one-off
elevation-free tile set built from the same clipped PBF.

Steps (Docker CLI on the host; the demo stack is not touched):
1. Build the tiles without elevation in a one-shot container of the pinned Valhalla image
   (`compose.yaml` service `valhalla`), exactly as `valhalla-build` builds the test clip
   (`additional_data.elevation` emptied), into `<results>/v11/valhalla/`.
2. Serve them from a temporary container on 127.0.0.1:`v11.port` with `config/valhalla.json`.
3. Recount the profiles of `v11` there (same blocks, targets and matrix as `count`), sampling
   the container's memory; compare with the run's counts (with slopes).
4. Golden pair (`tiles.verify.route`) on both services: time and edge grades; N11 (b): the
   wheelchair route with several `max_grade` values.
5. Remove the container and the built tiles (results and logs stay).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from reach_pipeline import scoring
from reach_pipeline.errors import ConfigError, ExternalError
from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.manifest import sha256_file
from reach_pipeline.stages import tiles, validate
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

NAME = "v11"
TITLE = "With vs. without slopes (elevation-free tiles)"

# Same build as compose.yaml `valhalla-build` with ELEVATION=false (test clip, C6).
BUILD_SCRIPT = """
conf=/tmp/valhalla.json
python3 -c "import json, sys; c = json.load(open(sys.argv[1])); \
c['additional_data']['elevation'] = ''; json.dump(c, open(sys.argv[2], 'w'))" \
/valhalla/config/valhalla.json "$conf"
rm -rf /data/valhalla/tiles
valhalla_build_tiles -c "$conf" /data/valhalla/routing.osm.pbf
valhalla_build_extract -c "$conf" -O
rm -rf /data/valhalla/tiles
peak=$(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo 0)
echo "build peak memory: $(( peak / 1048576 )) MB"
"""
SERVE_SCRIPT = (
    "cp /valhalla/config/valhalla.json /data/valhalla/valhalla.effective.json && "
    "exec valhalla_service /data/valhalla/valhalla.effective.json {threads}"
)
_UNITS = {
    "B": 1 / 1024**2,
    "KIB": 1 / 1024,
    "MIB": 1.0,
    "GIB": 1024.0,
    "KB": 1e-3,
    "MB": 1.0,
    "GB": 1e3,
}


def valhalla_image(repo: Path) -> str:
    """Image of the `valhalla` service in compose.yaml (pinned tag)."""
    compose = yaml.safe_load((repo / "compose.yaml").read_text(encoding="utf-8"))
    return compose["services"]["valhalla"]["image"]


def parse_mem_mb(text: str) -> float:
    """MB of a `docker stats` MemUsage value such as `1.21GiB / 7.6GiB`."""
    m = re.match(r"\s*([\d.]+)\s*([KMG]?i?B)", text, re.IGNORECASE)
    if not m:
        return float("nan")
    return float(m.group(1)) * _UNITS[m.group(2).upper()]


def _docker(*args: str, capture: bool = True, check: bool = True) -> str:
    proc = subprocess.run(["docker", *args], capture_output=capture, text=True, check=False)
    if check and proc.returncode != 0:
        raise ExternalError(f"docker {args[0]} failed ({proc.returncode}): {proc.stderr[-800:]}")
    return proc.stdout


def _port_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


class MemorySampler(threading.Thread):
    """Samples a container's memory (`docker stats`) until stopped; keeps the maximum."""

    def __init__(self, container: str, every_s: float) -> None:
        super().__init__(daemon=True)
        self.container, self.every_s = container, every_s
        self.samples: list[float] = []
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            out = _docker(
                "stats", "--no-stream", "--format", "{{.MemUsage}}", self.container, check=False
            )
            if out.strip():
                self.samples.append(parse_mem_mb(out))
            self._stop_event.wait(self.every_s)

    def stop(self) -> dict[str, float | int]:
        self._stop_event.set()
        self.join(timeout=30)
        good = [s for s in self.samples if s == s]
        return {
            "samples": len(good),
            "peak_mb": round(max(good), 1) if good else None,
            "last_mb": round(good[-1], 1) if good else None,
        }


async def golden(url: str, e: Experiment) -> dict[str, Any]:
    """Golden pair: pedestrian time and grades, and wheelchair times per `max_grade`."""
    cfg = e.cfg
    a, b = cfg.tiles.verify.route
    locs = [{"lon": a[0], "lat": a[1]}, {"lon": b[0], "lat": b[1]}]
    wheel = next(
        (
            p
            for pid, p in cfg.profiles.items()
            if pid in e.settings.v11.profiles and p.costing_options.get("type") == "wheelchair"
        ),
        None,
    )
    walk = cfg.profiles[e.settings.v11.profiles[0]]
    out: dict[str, Any] = {}
    async with ValhallaClient(cfg.valhalla, url=url) as client:
        for name, profile in (("walking", walk), ("wheelchair", wheel)):
            if profile is None:
                continue
            route = await client.post(
                "route",
                {
                    "locations": locs,
                    "costing": profile.costing,
                    "costing_options": costing_options(profile),
                    "units": "kilometers",
                },
            )
            trip = route["trip"]
            attrs = await client.post(
                "trace_attributes",
                {
                    "encoded_polyline": trip["legs"][0]["shape"],
                    "costing": profile.costing,
                    "shape_match": "edge_walk",
                    "filters": {"attributes": tiles.GRADE_ATTRIBUTES, "action": "include"},
                },
            )
            edges = attrs.get("edges", [])
            out[name] = {
                "time_s": round(trip["summary"]["time"], 1),
                "length_m": round(trip["summary"]["length"] * 1000, 1),
                "max_upward_grade": max((x.get("max_upward_grade", 0) for x in edges), default=0),
                "max_abs_weighted_grade": max(
                    (abs(x.get("weighted_grade", 0)) for x in edges), default=0
                ),
            }
        if wheel is not None:
            grades = {}
            for value in e.settings.v11.max_grade_values:
                opts = costing_options(wheel)
                if value is not None:
                    opts[wheel.costing] = {**opts[wheel.costing], "max_grade": value}
                r = await client.post(
                    "route",
                    {
                        "locations": locs,
                        "costing": wheel.costing,
                        "costing_options": opts,
                        "units": "kilometers",
                    },
                )
                s = r["trip"]["summary"]
                grades["unset" if value is None else f"{value:g}"] = {
                    "time_s": round(s["time"], 1),
                    "length_m": round(s["length"] * 1000, 1),
                }
            out["wheelchair_max_grade"] = grades
    return out


def _wait_ready(url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/status", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise ExternalError(f"temporary Valhalla at {url} did not become ready in {timeout_s} s")


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v11
    repo = Path.cwd()
    config_dir = (repo / e.ctx.config_path).resolve().parent
    if not (config_dir / "valhalla.json").exists():
        raise ConfigError(f"{config_dir}/valhalla.json not found (run from the repository root)")
    if not _port_free(s.port):
        raise ConfigError(f"port {s.port} is in use; set another v11.port")
    image = valhalla_image(repo)
    vdir = (e.out / "valhalla").resolve()
    shutil.rmtree(vdir, ignore_errors=True)
    vdir.mkdir(parents=True)
    pbf = e.ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF
    shutil.copyfile(pbf, vdir / "routing.osm.pbf")
    mounts = ["-v", f"{config_dir}:/valhalla/config:ro", "-v", f"{vdir}:/data/valhalla"]
    _docker("rm", "-f", s.container_name, f"{s.container_name}-build", check=False)

    started = time.perf_counter()
    log = _docker(
        "run",
        "--rm",
        "--name",
        f"{s.container_name}-build",
        *mounts,
        "--entrypoint",
        "sh",
        image,
        "-euc",
        BUILD_SCRIPT,
    )
    build_s = round(time.perf_counter() - started, 1)
    (e.out / "build.log").write_text(log[-20000:], encoding="utf-8")
    peak = re.search(r"build peak memory: (\d+) MB", log)
    tar = vdir / "valhalla_tiles.tar"
    if not tar.exists():
        raise ExternalError(f"tile build wrote no {tar}; see {e.out / 'build.log'}")
    build = {
        "runtime_s": build_s,
        "peak_mb": int(peak.group(1)) if peak else None,
        "tiles_mb": round(tar.stat().st_size / 1024**2, 1),
        "image": image,
        "pbf_sha256": sha256_file(pbf),
    }
    (vdir / "routing.osm.pbf").unlink()

    url = f"http://127.0.0.1:{s.port}"
    sampler = MemorySampler(s.container_name, s.memory_sample_s)
    try:
        _docker(
            "run",
            "-d",
            "--name",
            s.container_name,
            "-p",
            f"127.0.0.1:{s.port}:8002",
            *mounts,
            "--entrypoint",
            "sh",
            image,
            "-euc",
            SERVE_SCRIPT.format(threads=s.threads),
        )
        _wait_ready(url, s.start_timeout_s)
        sampler.start()
        data = common.load_count_data(e.ctx)
        budget = e.cfg.time_budgets_min.facilities
        flat, _, stats = asyncio.run(common.recount(e.cfg, data, s.profiles, budget, url=url))
        memory = sampler.stop()
        golden_flat = asyncio.run(golden(url, e))
    finally:
        if sampler.is_alive():
            sampler.stop()
        _docker("rm", "-f", s.container_name, check=False)
        shutil.rmtree(vdir, ignore_errors=True)
    removed = not _docker(
        "ps", "-a", "-q", "--filter", f"name=^{s.container_name}$", check=False
    ).strip()
    golden_slope = asyncio.run(golden(os.environ.get("VALHALLA_URL") or e.cfg.valhalla.url, e))

    flat.to_parquet(e.out / "access_counts_flat.parquet", index=False)
    base = e.access[e.access["profile_id"].isin(s.profiles)]
    k = e.k()
    cells = e.cells
    table = common.compare(base, flat, cells, k)  # base = with slopes, alt = flat
    e.write_table("classes.csv", table)
    dd = (
        common.district_deficits(base, cells, k)
        .merge(
            common.district_deficits(flat, cells, k),
            on=["profile_id", "category", "district_id"],
            suffixes=("_slope", "_flat"),
        )
        .merge(e.districts[["district_id", "name"]], on="district_id")
    )
    dd["deficit_change"] = (dd["deficit_sum_flat"] - dd["deficit_sum_slope"]).round(1)
    e.write_table("districts.csv", dd)
    # Per cell: categories whose class differs (walking profile) for the difference map.
    m = base.merge(flat, on=["cell_id", "category", "profile_id"], suffixes=("_slope", "_flat"))
    m["better_flat"] = m["count_flat"] > m["count_slope"]
    m["class_changed"] = scoring.classify(
        m["count_slope"].to_numpy(), k.reindex(m["category"]).to_numpy()
    ) != scoring.classify(m["count_flat"].to_numpy(), k.reindex(m["category"]).to_numpy())
    per_cell = (
        m.groupby(["profile_id", "cell_id"])
        .agg(
            categories_changed=("class_changed", "sum"),
            count_slope=("count_slope", "sum"),
            count_flat=("count_flat", "sum"),
        )
        .reset_index()
    )
    per_cell.to_parquet(e.out / "cells.parquet", index=False)
    tot = table.groupby("profile_id")[["residents_changed", "residents_worse", "residents"]].sum()
    by_district = (
        dd.groupby(["profile_id", "name"])["deficit_change"]
        .sum()
        .reset_index()
        .sort_values("deficit_change")
    )
    e.notes.append(
        "'worse' in classes.csv means a worse class without slopes; with flat tiles counts only "
        "grow where slopes slowed a route, so residents_worse should be close to zero."
    )
    return {
        "status": "done",
        "build": build,
        "service": {
            "port": s.port,
            "threads": s.threads,
            "memory": memory,
            "container_removed": removed,
        },
        "recount": stats,
        "profiles": {
            pid: {
                "share_resident_class_changes": round(
                    float(r["residents_changed"] / r["residents"]), 4
                ),
                "residents_better_class_flat": int(r["residents_changed"] - r["residents_worse"]),
                "residents_worse_class_flat": int(r["residents_worse"]),
            }
            for pid, r in tot.iterrows()
        },
        "per_category": common.records(
            table[
                [
                    "profile_id",
                    "category",
                    "share_residents_changed",
                    "share_lack_base",
                    "share_lack_alt",
                    "deficit_base",
                    "deficit_alt",
                    "count_diff_mean",
                ]
            ]
        ),
        "districts_largest_deficit_drop_flat": common.records(by_district.head(10)),
        "golden_pair": {"with_slopes": golden_slope, "flat": golden_flat},
    }
