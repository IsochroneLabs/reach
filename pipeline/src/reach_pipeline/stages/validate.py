"""validate: turn the raw inputs into cleaned layers (GeoParquet, EPSG:25832) and check them.

OSM in two passes (no full PBF in Python): 1. `tags-filter` admin boundaries + built-up land use
from the regional PBF; 2. city, urban boundary and routing area; 3. `extract -p` the routing area
→ `routing.osm.pbf` (input of the tile build); 4. facilities and walkable ways from the clipped
PBF. Then Zensus cells, GTFS stops and the reference weekday. Writes validation report part 1
(`report_inputs.json` + `.md`); any failed check fails the stage after the report is written.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import shapely

from reach_pipeline import boundary, facilities, gtfs, osm, zensus
from reach_pipeline.config import Config
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
# manifest.config_input): boundaries, facilities, Zensus, GTFS and the input checks.
CONFIG_SECTIONS = (
    "access_points",
    "categories",
    "districts",
    "facility_tags",
    "reference_day",
    "sources",
    "study_area",
    "validation",
)
PREVIOUS = acquire.STAGE
METRIC_CRS = "EPSG:25832"
ROUTING_PBF = "routing.osm.pbf"
REPORT_JSON, REPORT_MD = "report_inputs.json", "report_inputs.md"

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


def build_layers(ctx: RunContext, inp: Inputs, stage_dir: Path, step: _Steps) -> dict[str, Any]:
    """All cleaned layers plus the values the checks need."""
    cfg = ctx.config
    work = stage_dir / "osm"
    work.mkdir(parents=True, exist_ok=True)
    ub = cfg.study_area.urban_boundary

    with step("osm pass 1: admin boundaries + land use"):
        exprs = ["r/boundary=administrative", f"wr/landuse={','.join(ub.landuse)}"]
        pass1 = osm.tags_filter(inp.pbf, work / "admin_landuse.osm.pbf", exprs)
        exp1 = osm.export(pass1, work / "admin_landuse.geojsonseq", ["polygon"])
        admin = osm.read_export(exp1, where="boundary = 'administrative'")
        ab = cfg.study_area.admin_boundary
        city = boundary.admin_boundary(admin, ab.admin_level, ab.ags)
        study = city
        if cfg.study_area.clip_bbox is not None:
            clip = gpd.GeoSeries([shapely.box(*cfg.study_area.clip_bbox)], crs="EPSG:4326")
            study = city.intersection(clip.to_crs(METRIC_CRS).iloc[0])
        landuse = osm.read_export(
            exp1, bbox=_bbox(study, "EPSG:4326"), where=f"landuse IN ({_sql_list(ub.landuse)})"
        )

    with step("urban boundary, routing area, districts"):
        urban = boundary.urban_boundary(landuse.geometry, study, ub)
        if urban.empty:
            raise StageValidationError("urban boundary is empty (no built-up land use found)")
        routing = boundary.routing_area(study, cfg.study_area.routing_buffer_m)
        polygon = work / "routing_area.geojson"
        routing.to_crs("EPSG:4326").to_file(polygon, driver="GeoJSON")
        districts = boundary.districts(admin, city, cfg.districts.admin_levels)
        gap, overlap = boundary.coverage(districts, city)

    with step("osm pass 2: clip to routing area"):
        clipped = osm.extract_polygon(inp.pbf, stage_dir / ROUTING_PBF, polygon)
        snapshot = osm.replication_timestamp(inp.pbf)

    with step("osm pass 2: facilities and walkable ways"):
        tags = [t for c in cfg.categories for t in c.tags]
        walkable = cfg.access_points.walkable_highways
        exprs = [*osm.tag_expressions(tags), f"w/highway={','.join(walkable)}"]
        feat_pbf = osm.tags_filter(clipped, work / "facilities.osm.pbf", exprs)
        feats = osm.read_export(
            osm.export(feat_pbf, work / "facilities.geojsonseq", ["point", "polygon"])
        )
        ways = osm.read_export(
            osm.export(feat_pbf, work / "ways.geojsonseq", ["linestring"]),
            where=f"highway IN ({_sql_list(walkable)})",
        )
        fac, points = facilities.build(
            feats, ways.geometry, cfg.categories, cfg.access_points, cfg.facility_tags
        )
        # Informative statistics on the features inside the city (not the routing buffer).
        in_city = feats.representative_point().within(study).to_numpy(dtype=bool)
        city_feats = feats[in_city]
        excluded_by_filter = facilities.exclusion_stats(city_feats, cfg.categories)
        subtypes = cfg.validation.facility_subtypes
        subtype_total, subtype_missing = (
            facilities.subtype_gap(city_feats, subtypes.base, subtypes.type_keys)
            if subtypes
            else (0, [])
        )
        area = routing.geometry.iloc[0]
        # Only routing points inside the routing area (the graph ends there); a facility stays
        # if at least one of its points is inside.
        points = points[points.within(area)].reset_index(drop=True)
        fac = fac[fac["facility_id"].isin(points["facility_id"])].reset_index(drop=True)

    with step("zensus cells"):
        grid = zensus.read_grid(
            inp.zensus_csv, _bbox(study.buffer(zensus.CELL_SIZE_M), "EPSG:3035")
        )
        cells = zensus.cell_geometries(grid)
        scored, excluded_by_district, residents_touching = boundary.scoring_scope(
            cells, study, districts
        )
        urban_union = shapely.union_all(urban.geometry.values)
        in_urban = scored.set_geometry("origin_geom").within(urban_union).to_numpy()
        joined = gpd.sjoin(
            scored.set_geometry("origin_geom")[["cell_id", "origin_geom"]],
            districts[["district_id", "geometry"]],
            predicate="within",
            how="left",
        ).drop_duplicates("cell_id")
        scored.insert(2, "district_id", joined["district_id"].to_numpy())

    with step("gtfs stops and reference weekday"):
        stops = gtfs.read_stops(inp.gtfs_dir / "stops.txt")
        stops = stops[stops.within(area)].reset_index(drop=True)
        cal, dates = gtfs.read_calendar(inp.gtfs_dir)
        valid_from, valid_to = gtfs.feed_validity(inp.gtfs_dir, cal, dates)
        run_day = datetime.strptime(ctx.run_id, RUN_ID_FORMAT).date()
        try:
            ref_day: date | None = gtfs.reference_weekday(
                valid_from, valid_to, cal, dates, cfg.reference_day, run_day
            )
            services = len(gtfs.active_service_ids(cal, dates, ref_day))
        except StageValidationError as exc:
            log.error("%s", exc)
            ref_day, services = None, 0

    return {
        "layers": {
            "cells": scored,
            "facilities": fac,
            "facility_points": points,
            "stops": stops,
            "districts": districts,
            "urban_boundary": urban,
            "routing_area": routing,
        },
        "scope": study,
        "excluded_by_filter": excluded_by_filter,
        "subtype_total": subtype_total,
        "subtype_missing": subtype_missing,
        "city_area_km2": city.area / 1e6,
        "district_gap": gap,
        "district_overlap": overlap,
        "osm_snapshot": snapshot,
        "residents_touching": residents_touching,
        "residents_scored": int(scored["population"].sum()),
        "residents_excluded": residents_touching - int(scored["population"].sum()),
        "excluded_by_district": excluded_by_district,
        "residents_outside_urban": int(scored.loc[~in_urban, "population"].sum()),
        "gtfs_valid_from": valid_from,
        "gtfs_valid_to": valid_to,
        "reference_weekday": ref_day,
        "active_services": services,
    }


def checks(ctx: RunContext, r: dict[str, Any]) -> list[Check]:
    """Core plausibility checks of report part 1 (arch. §7 "validate inputs")."""
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
                f"{total} residents scored; no official total configured",
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
            "scored_share",
            "ok" if share >= minimum_share else "fail",
            round(share, 4),
            f"{r['residents_scored']} of {r['residents_touching']} residents in cells touching "
            f"the scope (city or clip) are scored ({share:.2%}, minimum {minimum_share:.0%}); "
            f"{r['residents_excluded']} excluded" + (f", most in {top}" if top else ""),
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
            f"{len(cells)} scored cells, {outside} origins outside the city, "
            f"{no_district} without district",
        )
    )

    counts = layers["facilities"]["category"].value_counts()
    minimum = cfg.validation.min_facilities_per_category
    low = {c.id: int(counts.get(c.id, 0)) for c in cfg.categories if counts.get(c.id, 0) < minimum}
    out.append(
        Check(
            "facilities_per_category",
            "fail" if low else "ok",
            None,
            f"below {minimum}: {low}"
            if low
            else ", ".join(f"{c.id} {int(counts.get(c.id, 0))}" for c in cfg.categories),
        )
    )

    out += facility_checks(cfg, r)

    ref = r["reference_weekday"]
    vf, vt = r["gtfs_valid_from"], r["gtfs_valid_to"]
    if ref is None:
        out.append(
            Check(
                "gtfs_reference_day",
                "fail",
                None,
                f"no regular {cfg.reference_day.weekday} in the feed validity {vf}..{vt}",
            )
        )
    else:
        out.append(
            Check(
                "gtfs_reference_day",
                "ok",
                r["active_services"],
                f"{ref} inside feed validity {vf}..{vt}, {r['active_services']} active services",
            )
        )
    covered = cfg.reference_day.covered
    if ref is not None and ref not in covered:
        out.append(
            Check(
                "holiday_calendar",
                "fail",
                None,
                f"reference day {ref} outside the holiday lists ({covered.start}.."
                f"{covered.end}); extend reference_day in config.yaml",
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
    return out


def facility_checks(cfg: Config, r: dict[str, Any]) -> list[Check]:
    """`facilities_excluded_by_access` (informative) and `facility_subtypes_complete`."""
    out: list[Check] = []
    by_filter: dict[str, dict[str, int]] = r["excluded_by_filter"]
    if by_filter:
        total = sum(v["excluded"] for v in by_filter.values())
        detail = "; ".join(
            f"{cat}: " + ", ".join(f"{cond} {n}" for cond, n in v.items() if cond != "excluded")
            for cat, v in by_filter.items()
        )
        out.append(
            Check(
                "facilities_excluded_by_access",
                "ok",
                total,
                f"{total} features in the city dropped by category `exclude` conditions "
                f"({detail}; one feature can match several)",
            )
        )
    subtypes = cfg.validation.facility_subtypes
    if subtypes:
        ((key, value),) = subtypes.base.items()
        total, missing = r["subtype_total"], r["subtype_missing"]
        pct = 100 * (total - len(missing)) / total if total else 100.0
        shown = ", ".join(missing[:10]) + (" …" if len(missing) > 10 else "")
        out.append(
            Check(
                "facility_subtypes_complete",
                "ok" if pct >= subtypes.min_typed_pct else "warn",
                round(pct, 1),
                f"{total - len(missing)} of {total} {key}={value} features in the city carry one "
                f"of {subtypes.type_keys} ({pct:.1f} %, gate {subtypes.min_typed_pct:g} %)"
                + (f"; without: {shown}" if missing else ""),
            )
        )
    return out


def _summary(ctx: RunContext, r: dict[str, Any]) -> dict[str, Any]:
    layers = r["layers"]
    counts = layers["facilities"]["category"].value_counts()
    return {
        "city": ctx.config.study_area.city_name,
        "osm_snapshot": r["osm_snapshot"],
        "urban_boundary_parts": len(layers["urban_boundary"]),
        "urban_area_km2": round(layers["urban_boundary"].area.sum() / 1e6, 2),
        "city_area_km2": round(r["city_area_km2"], 2),
        "routing_area_km2": round(layers["routing_area"].area.sum() / 1e6, 2),
        "districts": len(layers["districts"]),
        "cells_scored": len(layers["cells"]),
        "residents_touching_city": r["residents_touching"],
        "residents_scored": r["residents_scored"],
        "residents_excluded": r["residents_excluded"],
        "scored_share": round(r["residents_scored"] / max(r["residents_touching"], 1), 4),
        "residents_outside_urban_boundary": r["residents_outside_urban"],
        "excluded_by_district": r["excluded_by_district"],
        "facilities": {c.id: int(counts.get(c.id, 0)) for c in ctx.config.categories},
        "facility_points": len(layers["facility_points"]),
        "facilities_without_type": r["subtype_missing"],
        "stops": len(layers["stops"]),
        "gtfs_valid_from": str(r["gtfs_valid_from"]),
        "gtfs_valid_to": str(r["gtfs_valid_to"]),
        "reference_weekday": str(r["reference_weekday"]) if r["reference_weekday"] else None,
        "active_services": r["active_services"],
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
        if key not in ("facilities", "excluded_by_district"):
            lines.append(f"| {key} | {value} |")
    lines += ["", "| Category | Facilities |", "|---|---|"]
    lines += [f"| {c} | {n} |" for c, n in s["facilities"].items()]
    lines += [
        "",
        "| District (excluded residents: cell centre outside the city) | Residents |",
        "|---|---|",
    ]
    lines += [f"| {d} | {n} |" for d, n in s["excluded_by_district"].items()] or ["| none | 0 |"]
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
            f"{report['summary']['cells_scored']} cells, "
            f"{report['summary']['residents_scored']} residents scored "
            f"({report['summary']['scored_share']:.2%}), "
            f"{report['summary']['stops']} stops, reference day "
            f"{report['summary']['reference_weekday']}"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
