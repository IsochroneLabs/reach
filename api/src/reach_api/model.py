"""In-memory view of the published run for the fit (arch. §9, meth. §6).

`Model.build` turns `current.travel_times` into one array per **term** (a destination type such
as `mensa`, a label such as `grocery:edeka` or `sport:tennis`, or one campus site
`campus_site/tal`): the shortest time per cell and mode over the term's destinations, plus the
destination that gives it. `POST /api/fit` then needs only array minima over the student's modes,
so the whole city is scored in milliseconds. The model is rebuilt when `current` moves to another
run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MODES = ("walk", "bike", "transit", "bike_transit")
CAMPUS = "campus_site"


@dataclass
class Term:
    """Best time per cell (rows) and mode (columns), the destination and its departure."""

    minutes: np.ndarray  # float32 (n_cells, n_modes), NaN = no time
    destination: np.ndarray  # object (n_cells, n_modes), destination_id or None
    departure: np.ndarray  # object (n_cells, n_modes), HH:MM (transit) or None


@dataclass
class Model:
    run_id: str
    cell_ids: np.ndarray
    cell_index: dict[str, int]
    district: np.ndarray  # district_id per cell (object, None = no district)
    populated: np.ndarray  # bool
    point: np.ndarray  # (n_cells, 2) lon/lat
    district_names: dict[str, str]
    types: pd.DataFrame  # current.destination_types, indexed by destination_type
    labels: pd.DataFrame  # offered labels: destination_type, label_kind, label, destinations
    label_names: dict[str, dict[str, str]]
    sites: pd.DataFrame  # current.campus_sites, indexed by site_id
    programmes: pd.DataFrame  # current.programmes, indexed by programme
    names: dict[str, str]  # destination_id → name
    terms: dict[str, Term] = field(default_factory=dict)
    modes: list[str] = field(default_factory=list)

    def term_of(self, destination_id: str, destination_type: str) -> str:
        parts = destination_id.split(":")
        if destination_type == CAMPUS:
            return f"{CAMPUS}/{parts[1]}"
        if len(parts) >= 3:
            return f"{destination_type}:{parts[1]}"
        return destination_type

    @classmethod
    def build(
        cls,
        run_id: str,
        cells: pd.DataFrame,
        districts: pd.DataFrame,
        types: pd.DataFrame,
        labels: pd.DataFrame,
        label_names: dict[str, dict[str, str]],
        sites: pd.DataFrame,
        programmes: pd.DataFrame,
        destinations: pd.DataFrame,
        times: pd.DataFrame,
    ) -> Model:
        """`times`: cell_id, destination_id, mode, time_s, departure (current.travel_times).
        `destinations`: destination_id, destination_type, name (types and labels)."""
        ids = cells["cell_id"].to_numpy()
        model = cls(
            run_id=run_id,
            cell_ids=ids,
            cell_index={c: i for i, c in enumerate(ids)},
            district=cells["district_id"].to_numpy(dtype=object),
            populated=cells["populated"].to_numpy(dtype=bool),
            point=cells[["lon", "lat"]].to_numpy(dtype=float),
            district_names=dict(zip(districts["district_id"], districts["name"], strict=True)),
            types=types.set_index("destination_type"),
            labels=labels,
            label_names=label_names,
            sites=sites.set_index("site_id"),
            programmes=programmes.set_index("programme"),
            names=dict(zip(destinations["destination_id"], destinations["name"], strict=True)),
        )
        dtype = destinations.set_index("destination_id")["destination_type"]
        t = times.dropna(subset=["time_s"]).copy()
        t["dtype"] = t["destination_id"].map(dtype)
        t = t.dropna(subset=["dtype"])
        t["term"] = [
            model.term_of(d, ty) for d, ty in zip(t["destination_id"], t["dtype"], strict=True)
        ]
        t["ci"] = t["cell_id"].map(model.cell_index)
        t = t.dropna(subset=["ci"])
        model.modes = [m for m in MODES if m in set(t["mode"])]
        t["mi"] = t["mode"].map({m: i for i, m in enumerate(MODES)})
        best = t.sort_values("time_s", kind="stable").drop_duplicates(["term", "ci", "mi"])
        n = len(ids)
        for term, g in best.groupby("term", sort=False):
            minutes = np.full((n, len(MODES)), np.nan, dtype=np.float32)
            dest = np.full((n, len(MODES)), None, dtype=object)
            dep = np.full((n, len(MODES)), None, dtype=object)
            ci, mi = g["ci"].to_numpy(int), g["mi"].to_numpy(int)
            minutes[ci, mi] = g["time_s"].to_numpy(float) / 60
            dest[ci, mi] = g["destination_id"].to_numpy(object)
            dep[ci, mi] = g["departure"].to_numpy(object)
            model.terms[term] = Term(minutes, dest, dep)
        return model

    # --- profile keys ------------------------------------------------------------------------

    def is_container(self, destination_type: str) -> bool:
        return (
            destination_type in self.types.index
            and self.types.at[destination_type, "source"] == "labels"
        )

    def key_info(self, key: str) -> dict[str, Any] | None:
        """Profile key (`grocery`, `sport:tennis`) → type, window, defaults; None if unknown."""
        dtype, _, category = key.partition(":")
        if dtype not in self.types.index:
            return None
        if category:
            if key not in self.terms:
                return None
        elif self.is_container(dtype):
            return None
        row = self.types.loc[dtype]
        return {
            "type": dtype,
            "category": category or None,
            "trip_window": row["trip_window"],
            "fine_time_min": float(row["fine_time_min"]),
            "trips_per_week": 0.0 if category else float(row["trips_per_week"]),
        }

    def mode_columns(self, modes: list[str]) -> list[int]:
        return [MODES.index(m) for m in modes if m in MODES]
