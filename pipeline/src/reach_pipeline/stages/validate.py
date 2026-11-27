"""validate: turn the raw inputs into cleaned layers (GeoParquet, EPSG:25832) and check them.

OSM without the full PBF in Python: 1. `tags-filter` admin boundaries from the regional PBF;
2. city, districts and routing area; 3. `extract -p` the routing area → `routing.osm.pbf` (input
of the tile build); 4. `tags-filter` the label candidates from it and build the labelled
destinations (`labels`, meth. §3.1); 5. `tags-filter` the destination types, walkable ways and
addressed objects → destinations per type (with campus sites from `config/campus.yaml`) and the
address index. Then Zensus origin cells, GTFS stops, one reference date per trip window and the
departures per stop in each window (reliability, meth. §4).
Writes validation report part 1 (`report_inputs.json` + `.md`); any failed check fails the stage
after the report is written.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import pandas as pd
import shapely

from reach_pipeline import boundary, destinations, gtfs, labels, osm, transit, zensus
from reach_pipeline import campus as campus_mod
from reach_pipeline.config import DestinationLabels
from reach_pipeline.context import RUN_ID_FORMAT, RunContext
from reach_pipeline.errors import StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import acquire

STAGE = "validate"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): boundaries, Zensus, GTFS reference dates and the input checks.
CONFIG_SECTIONS = (
    "access_points",
    "address_cells",
    "calendar",
    "destination_labels",
    "destination_merge_m",
    "destination_types",
    "districts",
    "sources",
    "study_area",
    "travel_times",
    "trip_windows",
    "validation",
)
PREVIOUS = acquire.STAGE
METRIC_CRS = "EPSG:25832"
ROUTING_PBF = "routing.osm.pbf"
REPORT_JSON, REPORT_MD = "report_inputs.json", "report_inputs.md"
# Summary entries shown as their own tables in the Markdown report.
_TABLES = (
    "excluded_by_district",
    "reference_dates",
    "active_services",
    "destination_labels",
    "destinations",
    "campus_match_m",
)

log = logging.getLogger(__name__)


@dataclass
class Check:
    """One row of the validation report (data contract `validation_report`)."""

    check: str
    status: Literal["ok", "warn", "fail"]
    value: float | None
    message: str
    stage: str = STAGE


@dataclass
class Inputs:
    pbf: Path
    zensus_csv: Path
    gtfs_dir: Path
    gtfs_files: list[Path]


def _inputs(ctx: RunContext) -> Inputs:
    src = ctx.config.sources
    gtfs_files = [acquire.raw_path(ctx.raw_dir, "gtfs", m) for m in src.gtfs.members]
    return Inputs(
        pbf=acquire.raw_path(ctx.raw_dir, "osm", src.osm.url),
        zensus_csv=acquire.raw_path(ctx.raw_dir, "zensus", src.zensus.members[0]),
        gtfs_dir=ctx.raw_dir / "gtfs",
        gtfs_files=gtfs_files,
    )


class _Steps:
    """Runtime and peak RSS (so far) per step, for the log and the report."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    @contextmanager
    def __call__(self, name: str) -> Iterator[None]:
        with measure() as m:
            yield
        self.rows.append({"step": name, "runtime_s": m.runtime_s, "peak_rss_mb": m.peak_rss_mb})
        log.info("%s: %.1f s, peak RSS so far %.0f MB", name, m.runtime_s, m.peak_rss_mb)


def _bbox(geom: shapely.Geometry, crs: str) -> tuple[float, float, float, float]:
    return tuple(gpd.GeoSeries([geom], crs=METRIC_CRS).to_crs(crs).total_bounds)


def _sql_list(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def reference_dates(
    ctx: RunContext, gtfs_dir: Path
) -> tuple[date, date, dict[str, date | None], dict[str, int], pd.DataFrame]:
    """Feed validity, the reference date of every trip window (None if the feed has none) and
    the active services per reference date, plus the departures per stop in each window."""
    cfg = ctx.config
    cal, dates = gtfs.read_calendar(gtfs_dir)
    valid_from, valid_to = gtfs.feed_validity(gtfs_dir, cal, dates)
    run_day = datetime.strptime(ctx.run_id, RUN_ID_FORMAT).date()
    refs: dict[str, date | None] = {}
    services: dict[str, int] = {}
    deps: list[pd.DataFrame] = []
    span = cfg.travel_times.reliability_window_min * 60
    for name, window in cfg.trip_windows.items():
        try:
            day = gtfs.reference_date(
                valid_from, valid_to, cal, dates, window.weekday, cfg.calendar, run_day
            )
        except StageValidationError as exc:
            log.error("trip window %s: %s", name, exc)
            refs[name] = None
            continue
        refs[name] = day
        today = gtfs.active_service_ids(cal, dates, day)
        before = gtfs.active_service_ids(cal, dates, day - timedelta(days=1))
        services[str(day)] = len(today)
        hh, mm = (int(x) for x in window.time.split(":"))
        t = hh * 3600 + mm * 60
        start, end = (t - span, t) if window.mode == "arrive_by" else (t, t + span)
        d = transit.departures_in_window(gtfs_dir, today, before, start, end)
        deps.append(d.assign(trip_window=name))
    departures = (
        pd.concat(deps, ignore_index=True)
        if deps
        else pd.DataFrame(columns=["stop_id", "departures", "trip_window"])
    )
    return valid_from, valid_to, refs, services, departures


def build_layers(ctx: RunContext, inp: Inputs, stage_dir: Path, step: _Steps) -> dict[str, Any]:
    """All cleaned layers plus the values the checks need."""
    cfg = ctx.config
    work = stage_dir / "osm"
    work.mkdir(parents=True, exist_ok=True)

    with step("osm pass 1: admin boundaries"):
        admin_pbf = osm.tags_filter(inp.pbf, work / "admin.osm.pbf", ["r/boundary=administrative"])
        admin_exp = osm.export(admin_pbf, work / "admin.geojsonseq", ["polygon"])
        admin = osm.read_export(admin_exp, where="boundary = 'administrative'")
        ab = cfg.study_area.admin_boundary
        city = boundary.admin_boundary(admin, ab.admin_level, ab.ags)
        study = city
        if cfg.study_area.clip_bbox is not None:
            clip = gpd.GeoSeries([shapely.box(*cfg.study_area.clip_bbox)], crs="EPSG:4326")
            study = city.intersection(clip.to_crs(METRIC_CRS).iloc[0])

    with step("routing area, districts"):
        routing = boundary.routing_area(study, cfg.study_area.routing_buffer_m)
        polygon = work / "routing_area.geojson"
        routing.to_crs("EPSG:4326").to_file(polygon, driver="GeoJSON")
        districts = boundary.districts(admin, city, cfg.districts.admin_levels)
        gap, overlap = boundary.coverage(districts, city)

    with step("osm pass 2: clip to routing area"):
        osm.extract_polygon(inp.pbf, stage_dir / ROUTING_PBF, polygon)
        snapshot = osm.replication_timestamp(inp.pbf)

    label_layer = None
    if cfg.destination_labels is not None:
        with step("osm pass 3: destination labels"):
            label_layer = build_labels(stage_dir / ROUTING_PBF, work, cfg.destination_labels)

    with step("osm pass 4: destinations and addresses"):
        area = routing.geometry.iloc[0]
        campus = campus_mod.load_campus(ctx.config_path)
        sel = osm.tags_filter(
            stage_dir / ROUTING_PBF,
            work / "destinations.osm.pbf",
            [*destinations.osm_expressions(cfg), *campus_mod.OSM_EXPRESSIONS],
        )
        exp = osm.export(sel, work / "destinations.geojsonseq", ["point", "linestring", "polygon"])
        features = labels.unique_features(osm.read_export(exp))
        dest = destinations.build(features, campus, cfg, area)
        addr = destinations.addresses(features, area, cfg)
        uni = features[campus_mod.university_mask(features)]
        is_campus = dest["osm_id"].str.startswith("campus:")
        campus_match = dict(
            zip(
                dest.loc[is_campus, "destination_id"],
                campus_mod.match_osm(dest[is_campus], uni).round(0),
                strict=True,
            )
        )

    with step("zensus cells"):
        grid = zensus.read_grid(
            inp.zensus_csv, _bbox(study.buffer(zensus.CELL_SIZE_M), "EPSG:3035")
        )
        cells = zensus.cell_geometries(grid)
        origins, excluded_by_district, residents_touching = boundary.scoring_scope(
            cells, study, districts
        )
        homes = addr[addr["residential"] & addr.within(study)]
        extra = zensus.cell_geometries(zensus.address_cells(grid, homes.geometry))
        extra = extra[extra.set_geometry("origin_geom").within(study)]
        origins = gpd.GeoDataFrame(pd.concat([origins, extra], ignore_index=True), crs=METRIC_CRS)
        origins.insert(2, "populated", origins["population"] > 0)
        joined = gpd.sjoin(
            origins.set_geometry("origin_geom")[["cell_id", "origin_geom"]],
            districts[["district_id", "geometry"]],
            predicate="within",
            how="left",
        ).drop_duplicates("cell_id")
        origins.insert(3, "district_id", joined["district_id"].to_numpy())

    with step("gtfs stops, reference dates, departures"):
        stops = gtfs.read_stops(inp.gtfs_dir / "stops.txt")
        stops = stops[stops.within(area)].reset_index(drop=True)
        valid_from, valid_to, refs, services, departures = reference_dates(ctx, inp.gtfs_dir)
        departures = departures[departures["stop_id"].isin(stops["stop_id"])]

    residents = int(origins["population"].sum())
    layers = {
        "cells": origins,
        "stops": stops,
        "districts": districts,
        "routing_area": routing,
        "destinations": dest,
        "addresses": addr,
        "stop_departures": departures.reset_index(drop=True),
    }
    if label_layer is not None:
        layers["destination_labels"] = label_layer
    return {
        "layers": layers,
        "scope": study,
        "city_area_km2": city.area / 1e6,
        "district_gap": gap,
        "district_overlap": overlap,
        "osm_snapshot": snapshot,
        "residents_touching": residents_touching,
        "residents_scored": residents,
        "residents_excluded": residents_touching - residents,
        "excluded_by_district": excluded_by_district,
        "gtfs_valid_from": valid_from,
        "gtfs_valid_to": valid_to,
        "reference_dates": refs,
        "active_services": services,
        "campus": campus,
        "campus_match_m": campus_match,
        "destination_counts": destinations.counts(dest, cfg),
    }


def build_labels(pbf: Path, work: Path, cfg: DestinationLabels) -> gpd.GeoDataFrame:
    """Labelled destinations from the routing-area PBF (one row per destination and label)."""
    sel = osm.tags_filter(pbf, work / "labels.osm.pbf", labels.osm_expressions(cfg))
    exp = osm.export(sel, work / "labels.geojsonseq", ["point", "linestring", "polygon"])
    features = labels.unique_features(osm.read_export(exp))
    return labels.cluster(labels.label_features(features, cfg), features, cfg)


def label_check(dest: gpd.GeoDataFrame, cfg: DestinationLabels) -> Check:
    """V10 (meth. §10): supermarkets must carry a group; configured labels without enough
    destinations are not offered and reported."""
    groups = dest[dest["label_kind"] == "group"]
    offered = dest.loc[dest["offered"], labels.LABEL_KEYS].drop_duplicates()
    missing = labels.missing_categories(dest, cfg)
    small_brands = sorted(
        set(dest.loc[(dest["label_kind"] == "brand") & ~dest["offered"], "label"])
    )
    absent_brands = sorted(
        set(cfg.grocery.brands) - set(dest.loc[dest["label_kind"] == "brand", "label"])
    )
    not_offered = {
        k: v
        for k, v in {
            **missing,
            "brand below min stores": small_brands,
            "brand absent": absent_brands,
        }.items()
        if v
    }
    if groups.empty:
        return Check("destination_labels", "fail", 0, "no supermarket in the routing area")
    message = f"{len(offered)} labels offered, {len(dest)} labelled destinations; " + (
        f"not offered: {not_offered}" if not_offered else "every configured label offered"
    )
    return Check("destination_labels", "warn" if not_offered else "ok", len(offered), message)


def checks(ctx: RunContext, r: dict[str, Any]) -> list[Check]:
    """Plausibility checks of report part 1 (arch. §7 "validate inputs", meth. §10 V3)."""
    cfg = ctx.config
    layers: dict[str, gpd.GeoDataFrame] = r["layers"]
    out: list[Check] = []

    bad_crs = [
        f"{n}.{col}"
        for n, g in layers.items()
        for col in g.columns[g.dtypes == "geometry"]
        if g[col].crs is None or g[col].crs.to_string() != METRIC_CRS
    ]
    out.append(
        Check(
            "crs",
            "fail" if bad_crs else "ok",
            None,
            f"not {METRIC_CRS}: {bad_crs}" if bad_crs else f"all layers {METRIC_CRS}",
        )
    )
    empty = [n for n, g in layers.items() if g.empty]
    out.append(
        Check(
            "non_empty",
            "fail" if empty else "ok",
            None,
            f"empty layers: {empty}" if empty else "all layers non-empty",
        )
    )

    tol = cfg.districts.coverage_tolerance_pct
    gap, overlap = r["district_gap"] * 100, r["district_overlap"] * 100
    out.append(
        Check(
            "district_coverage",
            "ok" if gap <= tol and overlap <= tol else "fail",
            max(gap, overlap),
            f"admin levels {cfg.districts.admin_levels}: {len(layers['districts'])} districts, "
            f"gap {gap:.3f} %, overlap {overlap:.3f} % of the city (tolerance {tol} %)",
        )
    )

    official = cfg.validation.official_population
    total = r["residents_scored"]
    if official is None:
        out.append(
            Check(
                "population_total",
                "warn",
                total,
                f"{total} residents in origin cells; no official total configured",
            )
        )
    else:
        dev = (total - official) / official * 100
        ok = abs(dev) <= cfg.validation.population_tolerance_pct
        out.append(
            Check(
                "population_total",
                "ok" if ok else "fail",
                round(dev, 2),
                f"Zensus grid {total} vs. official {official}: {dev:+.2f} % "
                f"(tolerance ± {cfg.validation.population_tolerance_pct} %)",
            )
        )

    share = r["residents_scored"] / r["residents_touching"] if r["residents_touching"] else 0.0
    minimum_share = cfg.validation.min_scored_share
    top = ", ".join(f"{k} {v}" for k, v in list(r["excluded_by_district"].items())[:3])
    out.append(
        Check(
            "origin_coverage",
            "ok" if share >= minimum_share else "fail",
            round(share, 4),
            f"{r['residents_scored']} of {r['residents_touching']} residents in cells touching "
            f"the study area (city or clip) are in origin cells ({share:.2%}, minimum "
            f"{minimum_share:.0%}); {r['residents_excluded']} excluded"
            + (f", most in {top}" if top else ""),
        )
    )

    cells = layers["cells"]
    outside = int((~cells.set_geometry("origin_geom").within(r["scope"])).sum())
    no_district = int(cells["district_id"].isna().sum())
    status = "fail" if outside else ("warn" if no_district else "ok")
    out.append(
        Check(
            "cells_inside_boundary",
            status,
            outside,
            f"{len(cells)} origin cells, {outside} origins outside the city, "
            f"{no_district} without district",
        )
    )

    refs: dict[str, date | None] = r["reference_dates"]
    vf, vt = r["gtfs_valid_from"], r["gtfs_valid_to"]
    missing = sorted(n for n, d in refs.items() if d is None)
    found = ", ".join(f"{n} {d}" for n, d in refs.items() if d is not None)
    out.append(
        Check(
            "gtfs_trip_windows",
            "fail" if missing else "ok",
            len(refs) - len(missing),
            (
                f"no reference date in the feed validity {vf}..{vt} for {missing}"
                if missing
                else f"feed validity {vf}..{vt}: {found}"
            ),
        )
    )
    covered = cfg.calendar.covered
    outside_cal = sorted(n for n, d in refs.items() if d is not None and d not in covered)
    if outside_cal:
        out.append(
            Check(
                "holiday_calendar",
                "fail",
                None,
                f"reference dates of {outside_cal} outside the holiday lists ({covered.start}.."
                f"{covered.end}); extend `calendar` in config.yaml",
            )
        )
    elif vt > covered.end:
        out.append(
            Check(
                "holiday_calendar",
                "warn",
                None,
                f"feed valid until {vt}, holiday lists end {covered.end}",
            )
        )
    else:
        out.append(
            Check(
                "holiday_calendar",
                "ok",
                None,
                f"holiday lists cover {covered.start}..{covered.end}",
            )
        )
    if "destination_labels" in layers:
        out.append(label_check(layers["destination_labels"], cfg.destination_labels))
    out += destination_checks(r)
    return out


def destination_checks(r: dict[str, Any]) -> list[Check]:
    """V3 (meth. §10): every destination type has destinations, campus points lie near a
    university feature, the address index and the departures per window are not empty."""
    layers = r["layers"]
    cfg_counts = r["destination_counts"]
    none = sorted(t for t, n in cfg_counts.items() if n == 0)
    out = [
        Check(
            "destinations",
            "fail" if none else "ok",
            sum(cfg_counts.values()),
            (f"no destinations for {none}" if none else "every destination type has destinations")
            + f"; {len(layers['destinations'])} points",
        )
    ]
    radius = r["campus"].match_radius_m
    far = {k: v for k, v in r["campus_match_m"].items() if v > radius}
    out.append(
        Check(
            "campus_match",
            "warn" if far else "ok",
            len(far),
            (
                f"campus points farther than {radius:.0f} m from a university feature: {far}"
                if far
                else f"every campus point within {radius:.0f} m of a university feature"
            ),
        )
    )
    n_addr = len(layers["addresses"])
    out.append(
        Check(
            "addresses",
            "ok" if n_addr else "fail",
            n_addr,
            f"{n_addr} addresses (street + house number) in the routing area",
        )
    )
    dep = layers["stop_departures"]
    windows = set(r["reference_dates"]) - {n for n, d in r["reference_dates"].items() if d is None}
    empty = sorted(windows - set(dep["trip_window"]))
    out.append(
        Check(
            "stop_departures",
            "fail" if empty else "ok",
            int(dep["departures"].sum()) if len(dep) else 0,
            (
                f"no departures in the windows {empty}"
                if empty
                else "departures per window: "
                + ", ".join(
                    f"{w} {n}" for w, n in dep.groupby("trip_window")["departures"].sum().items()
                )
            ),
        )
    )
    return out


def _summary(ctx: RunContext, r: dict[str, Any]) -> dict[str, Any]:
    layers = r["layers"]
    return {
        "city": ctx.config.study_area.city_name,
        "osm_snapshot": r["osm_snapshot"],
        "city_area_km2": round(r["city_area_km2"], 2),
        "routing_area_km2": round(layers["routing_area"].area.sum() / 1e6, 2),
        "districts": len(layers["districts"]),
        "origin_cells": len(layers["cells"]),
        "address_cells": int((~layers["cells"]["populated"]).sum()),
        "residents_touching_city": r["residents_touching"],
        "residents_scored": r["residents_scored"],
        "residents_excluded": r["residents_excluded"],
        "scored_share": round(r["residents_scored"] / max(r["residents_touching"], 1), 4),
        "excluded_by_district": r["excluded_by_district"],
        "stops": len(layers["stops"]),
        "gtfs_valid_from": str(r["gtfs_valid_from"]),
        "gtfs_valid_to": str(r["gtfs_valid_to"]),
        "reference_dates": {n: (str(d) if d else None) for n, d in r["reference_dates"].items()},
        "active_services": r["active_services"],
        "destination_labels": (
            labels.counts(layers["destination_labels"]).to_dict("records")
            if "destination_labels" in layers
            else []
        ),
        "addresses": len(layers["addresses"]),
        "destinations": r["destination_counts"],
        "campus_match_m": r["campus_match_m"],
    }


def _markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Validation report part 1 — inputs ({report['run_id']})",
        "",
        f"Status: **{report['status']}** · generated {report['generated_at']}",
        "",
        "## Summary",
        "",
        "| Item | Value |",
        "|---|---|",
    ]
    for key, value in s.items():
        if key not in _TABLES:
            lines.append(f"| {key} | {value} |")
    lines += ["", "| Trip window | Reference date | Active services |", "|---|---|---|"]
    lines += [
        f"| {n} | {d or 'none'} | {s['active_services'].get(d, 0) if d else 0} |"
        for n, d in s["reference_dates"].items()
    ]
    lines += [
        "",
        "| District (excluded residents: cell centre outside the city) | Residents |",
        "|---|---|",
    ]
    lines += [f"| {d} | {n} |" for d, n in s["excluded_by_district"].items()] or ["| none | 0 |"]
    if s.get("destination_labels"):
        lines += [
            "",
            "| Type | Kind | Label (V10) | Destinations | Features | Offered |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {x['destination_type']} | {x['label_kind']} | {x['label']} | {x['destinations']} "
            f"| {x['features']} | {'yes' if x['offered'] else 'no'} |"
            for x in s["destination_labels"]
        ]
    lines += ["", "| Destination type (V3) | Destinations |", "|---|---|"]
    lines += [f"| {t} | {n} |" for t, n in s.get("destinations", {}).items()]
    lines += ["", "| Campus point | Distance to a university feature (m) |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s.get("campus_match_m", {}).items()]
    lines += ["", "## Checks", "", "| Check | Status | Value | Message |", "|---|---|---|---|"]
    lines += [
        f"| {c['check']} | {c['status']} | {'' if c['value'] is None else c['value']} "
        f"| {c['message']} |"
        for c in report["checks"]
    ]
    lines += [
        "",
        "## Runtime and peak memory",
        "",
        "| Stage | Runtime (s) | Peak RSS (MB) |",
        "|---|---|---|",
    ]
    lines += [f"| {x['stage']} | {x['runtime_s']} | {x['peak_rss_mb']} |" for x in report["stages"]]
    lines += ["", "| Step (validate) | Runtime (s) | Peak RSS so far (MB) |", "|---|---|---|"]
    lines += [f"| {x['step']} | {x['runtime_s']} | {x['peak_rss_mb']} |" for x in report["steps"]]
    return "\n".join(lines) + "\n"


def run(ctx: RunContext) -> Manifest:
    """Check the acquire manifest, build and check all layers, write them and the report."""
    previous_stage = require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    stage_dir = ctx.stage_dir(STAGE)
    inp = _inputs(ctx)
    raw = [inp.pbf, inp.zensus_csv, *inp.gtfs_files]
    missing = [str(p) for p in raw if not p.exists()]
    if missing:
        raise StageValidationError(f"raw files missing (run acquire): {missing}")
    inputs = [config_input(ctx.config, CONFIG_SECTIONS), *file_inputs(raw)]
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    step = _Steps()
    with measure() as m:
        result = build_layers(ctx, inp, stage_dir, step)
        report_checks = checks(ctx, result)
        outputs = [FileOutput(path=str(stage_dir / ROUTING_PBF))]
        for name, layer in result["layers"].items():
            path = stage_dir / f"{name}.parquet"
            layer.to_parquet(path, index=False)
            outputs.append(FileOutput(path=str(path), rows=len(layer)))

    failed = [c.check for c in report_checks if c.status == "fail"]
    report = {
        "run_id": ctx.run_id,
        "stage": STAGE,
        "status": "fail" if failed else "ok",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": _summary(ctx, result),
        "checks": [asdict(c) for c in report_checks],
        "stages": [
            {
                "stage": PREVIOUS,
                "runtime_s": previous_stage.runtime_s,
                "peak_rss_mb": previous_stage.peak_rss_mb,
            },
            {"stage": STAGE, "runtime_s": m.runtime_s, "peak_rss_mb": m.peak_rss_mb},
        ],
        "steps": step.rows,
    }
    (stage_dir / REPORT_JSON).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (stage_dir / REPORT_MD).write_text(_markdown(report), encoding="utf-8")
    outputs += [FileOutput(path=str(stage_dir / n)) for n in (REPORT_JSON, REPORT_MD)]
    for c in report_checks:
        (log.error if c.status == "fail" else log.warning if c.status == "warn" else log.info)(
            "check %s: %s — %s", c.check, c.status, c.message
        )
    if failed:
        raise StageValidationError(f"input validation failed: {failed} (see {REPORT_MD})")

    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=outputs,
        message=(
            f"{report['summary']['origin_cells']} origin cells, "
            f"{report['summary']['residents_scored']} residents "
            f"({report['summary']['scored_share']:.2%}), "
            f"{report['summary']['stops']} stops, reference dates "
            f"{report['summary']['reference_dates']}"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
