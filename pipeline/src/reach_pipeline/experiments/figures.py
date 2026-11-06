"""Figures of the validation report (docs/figures/), drawn from the experiments' results.

matplotlib is a dev dependency and imported here only. Colours follow one fixed palette
(categorical slots, a blue sequential ramp, a blue ↔ red diverging pair with grey neutral);
maps are PNG (many polygons), charts SVG; each file stays well below 1 MB.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline.context import RunContext
from reach_pipeline.experiments.settings import Settings
from reach_pipeline.stages import validate

FIG_DIR = Path("docs/figures")
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, RED, ORANGE = "#2a78d6", "#e34948", "#eb6834"
NEUTRAL, NEUTRAL_DARK = "#e4e3df", "#8a8984"
SEQUENTIAL = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # steps 250, 400, 550, 700

log = logging.getLogger(__name__)


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_2,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "text.color": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "svg.fonttype": "none",
            "svg.hashsalt": "reach",
        }
    )
    return plt


def _save(fig, name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / name
    meta = {"Date": None} if name.endswith(".svg") else {}
    fig.savefig(path, dpi=150, bbox_inches="tight", metadata=meta)
    size_kb = path.stat().st_size / 1024
    if size_kb > 1024:
        raise ValueError(f"{path} is {size_kb:.0f} KB (limit 1 MB)")
    log.info("figure %s (%.0f KB)", path, size_kb)
    return path


def _map_axes(plt, districts: gpd.GeoDataFrame):
    fig, ax = plt.subplots(figsize=(7, 6.2))
    districts.boundary.plot(ax=ax, color=NEUTRAL_DARK, linewidth=0.4)
    ax.set_axis_off()
    return fig, ax


def _legend(ax, items: list[tuple[str, str]], title: str) -> None:
    from matplotlib.patches import Patch

    ax.legend(
        handles=[Patch(facecolor=c, edgecolor="none", label=label) for label, c in items],
        title=title,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.0),
        ncol=2,
        frameon=False,
        fontsize=8,
        title_fontsize=8,
    )


def lisa_map(root: Path, cells: gpd.GeoDataFrame, districts: gpd.GeoDataFrame) -> Path:
    plt = _plt()
    lisa = pd.read_parquet(root / "v08" / "lisa.parquet")
    g = cells.merge(lisa[["cell_id", "cluster"]], on="cell_id", how="left")
    g["cluster"] = g["cluster"].fillna("no neighbour")
    groups = [
        ("high-high (deficit cluster)", RED, g["cluster"] == "high-high"),
        ("low-low (well served)", BLUE, g["cluster"] == "low-low"),
        ("outlier (high-low, low-high)", NEUTRAL_DARK, g["cluster"].isin(["high-low", "low-high"])),
        (
            "not significant / no neighbour",
            NEUTRAL,
            g["cluster"].isin(["not significant", "no neighbour"]),
        ),
    ]
    fig, ax = _map_axes(plt, districts)
    for _, colour, mask in groups:
        if mask.any():
            g[mask].plot(ax=ax, color=colour, edgecolor=SURFACE, linewidth=0.2)
    _legend(ax, [(label, c) for label, c, _ in groups], "LISA, categories in lack (p ≤ 0.05)")
    ax.set_title(
        "V8: clusters of the number of categories in lack (walking 3.39 km/h)",
        loc="left",
        fontsize=10,
    )
    out = _save(fig, "v08_lisa.png")
    plt.close(fig)
    return out


def slope_map(
    root: Path, cells: gpd.GeoDataFrame, districts: gpd.GeoDataFrame, profile: str
) -> Path:
    plt = _plt()
    per = pd.read_parquet(root / "v11" / "cells.parquet")
    per = per[per["profile_id"] == profile]
    g = cells.merge(per, on="cell_id", how="left")
    n = g["categories_changed"].fillna(0).astype(int)
    groups = [("no change", NEUTRAL, n == 0)] + [
        (
            f"{i} categor{'y' if i == 1 else 'ies'}" if i < 3 else "3 or more",
            SEQUENTIAL[i],
            (n == i) if i < 3 else (n >= 3),
        )
        for i in (1, 2, 3)
    ]
    fig, ax = _map_axes(plt, districts)
    for _, colour, mask in groups:
        if mask.any():
            g[mask].plot(ax=ax, color=colour, edgecolor=SURFACE, linewidth=0.2)
    _legend(ax, [(label, c) for label, c, _ in groups], "categories whose class changes")
    ax.set_title(f"V11: class changes without slopes ({profile})", loc="left", fontsize=10)
    out = _save(fig, "v11_slope_difference.png")
    plt.close(fig)
    return out


def sensitivity_chart(root: Path) -> Path:
    plt = _plt()
    r = json.loads((root / "v05" / RESULT).read_text(encoding="utf-8"))
    lack = pd.DataFrame(r["lack_share"]).set_index("category")
    budgets = sorted(
        [c for c in lack.columns if c.startswith("budget_")], key=lambda c: float(c[7:])
    )
    series = [(c, f"{float(c[7:]):g} min") for c in budgets]
    base_pos = next(i for i, (c, _) in enumerate(series) if float(c[7:]) > 15)
    series.insert(base_pos, ("share_lack_base", "15 min (base)"))
    colours = SEQUENTIAL[: len(series)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.6), gridspec_kw={"width_ratios": [3, 2]})
    cats = list(lack.index)
    y = np.arange(len(cats))
    for (col, label), colour in zip(series, colours, strict=True):
        ax1.scatter(
            lack[col] * 100,
            y,
            s=36,
            color=colour,
            label=label,
            zorder=3,
            edgecolor=SURFACE,
            linewidth=1,
        )
    speed = next((c for c in lack.columns if c.startswith("speed_")), None)
    if speed:
        ax1.scatter(
            lack[speed] * 100,
            y,
            s=40,
            marker="D",
            color=ORANGE,
            zorder=3,
            label="5.0 km/h, 15 min",
            edgecolor=SURFACE,
            linewidth=1,
        )
    ax1.set_yticks(y, cats)
    ax1.invert_yaxis()
    ax1.grid(axis="x", color=GRID, linewidth=0.6)
    ax1.set_xlabel("residents in lack (%)")
    ax1.set_title("Lack share by budget and speed (walking)", loc="left", fontsize=10)
    ax1.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
    sc = pd.DataFrame(r["scenarios"]).T
    order = [_scenario_label(n) for n in sc.index]
    ax2.barh(order, sc["share_resident_class_changes"].astype(float) * 100, color=BLUE, height=0.6)
    ax2.invert_yaxis()
    ax2.grid(axis="x", color=GRID, linewidth=0.6)
    ax2.set_xlabel("residents × categories changing class (%)")
    ax2.set_title("Class changes vs. base", loc="left", fontsize=10)
    for i, v in enumerate(sc["share_resident_class_changes"].astype(float) * 100):
        ax2.text(v + 0.3, i, f"{v:.1f}", va="center", fontsize=7.5, color=INK_2)
    fig.tight_layout()
    out = _save(fig, "v05_sensitivity.svg")
    plt.close(fig)
    return out


def _scenario_label(name: str) -> str:
    if name.startswith("k"):
        return f"k {name[1]} {name[2:]}"
    if name.startswith("budget_"):
        return f"budget {name[7:]} min"
    if name.startswith("speed_"):
        return "5.0 km/h" if name.endswith("500") else name[6:]
    return name


def gap_chart(root: Path) -> Path:
    plt = _plt()
    t = pd.read_csv(root / "v04" / "instances.csv")
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ns = sorted(t["n_sites"].unique())
    pos = {n: i for i, n in enumerate(ns)}
    rng = np.random.default_rng(0)
    x = t["n_sites"].map(pos) + rng.uniform(-0.15, 0.15, len(t))
    ax.scatter(
        x, t["optimality_gap"] * 100, s=28, color=BLUE, edgecolor=SURFACE, linewidth=1, zorder=3
    )
    ax.set_xticks(range(len(ns)), [str(n) for n in ns])
    ax.set_xlabel("new facilities N")
    ax.set_ylabel("greedy below optimum (%)")
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.axhline(0, color=NEUTRAL_DARK, linewidth=0.8)
    worst = t.loc[t["optimality_gap"].idxmax()]
    ax.annotate(
        f"{worst['category']}, {worst['profile_id']}: {worst['optimality_gap'] * 100:.1f} %",
        (pos[worst["n_sites"]], worst["optimality_gap"] * 100),
        xytext=(-150, -4),
        textcoords="offset points",
        fontsize=7.5,
        color=INK_2,
        arrowprops={"arrowstyle": "-", "color": NEUTRAL_DARK, "linewidth": 0.6},
    )
    ax.set_title(
        f"V4: greedy vs. exact optimum ({len(t)} instances, all solved to optimality)",
        loc="left",
        fontsize=10,
    )
    out = _save(fig, "v04_gap.svg")
    plt.close(fig)
    return out


RESULT = "result.json"


def draw(ctx: RunContext, settings: Settings) -> list[Path]:
    """All figures whose experiment results exist."""
    root = ctx.config.data_dir / settings.results_dir / ctx.run_id
    vdir = ctx.stage_dir(validate.STAGE)
    cells = gpd.read_parquet(vdir / "cells.parquet")[["cell_id", "geometry"]]
    districts = gpd.read_parquet(vdir / "districts.parquet")
    out = []
    if (root / "v08" / "lisa.parquet").exists():
        out.append(lisa_map(root, cells, districts))
    if (root / "v11" / "cells.parquet").exists():
        out.append(slope_map(root, cells, districts, settings.v11.profiles[0]))
    if (root / "v05" / RESULT).exists():
        out.append(sensitivity_chart(root))
    if (root / "v04" / "instances.csv").exists():
        out.append(gap_chart(root))
    return out
