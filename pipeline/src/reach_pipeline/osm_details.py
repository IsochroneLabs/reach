"""OSM details of the destinations for the app (notes N29): opening hours, website, wheelchair.

Read from the OSM exports `validate` writes (`validate/osm/*.geojsonseq`, all tags kept) and
joined to the destinations by OSM id, so `publish` can add them without routing again. Values
are kept as tagged (`opening_hours` syntax of the OSM wiki); the app shows them as text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from reach_pipeline.opening_hours import open_at

DETAIL_COLUMNS = ["destination_id", "opening_hours", "website", "wheelchair"]
OUT_COLUMNS = [*DETAIL_COLUMNS, "open_in_window"]
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_TYPE = {"node": "n", "way": "w", "relation": "r"}
_KEYS = ("opening_hours", "website", "contact:website", "wheelchair")
_MAX = 255


def read(paths: Iterable[Path]) -> pd.DataFrame:
    """One row per OSM feature that has any of the detail tags: osm_id (`n123`), the tags."""
    rows: dict[str, dict[str, str | None]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not any(f'"{k}"' in line for k in _KEYS):
                    continue
                props = json.loads(line.strip("\x1e\n"))["properties"]
                prefix = _TYPE.get(props.get("@type", ""))
                if prefix is None or "@id" not in props:
                    continue
                website = props.get("website") or props.get("contact:website")
                if website and not re.match(r"^https?://", website):
                    website = None
                rows[f"{prefix}{props['@id']}"] = {
                    "opening_hours": (props.get("opening_hours") or None),
                    "website": website,
                    "wheelchair": props.get("wheelchair") or None,
                }
    out = pd.DataFrame.from_dict(rows, orient="index", columns=DETAIL_COLUMNS[1:])
    out.index.name = "osm_id"
    for col in out.columns:
        out[col] = out[col].str.slice(0, _MAX)
    return out.reset_index()


def window_times(cfg) -> dict[str, tuple[int, int]]:
    """Destination type → (weekday 0 = Monday, minute of the day) of its trip window."""
    out = {}
    for dtype, t in cfg.destination_types.items():
        w = cfg.trip_windows[t.trip_window]
        h, m = (int(x) for x in w.time.split(":"))
        out[dtype] = (WEEKDAYS.index(w.weekday), h * 60 + m)
    return out


def for_destinations(
    destinations: pd.DataFrame,
    labels: pd.DataFrame | None,
    details: pd.DataFrame,
    windows: dict[str, tuple[int, int]] | None = None,
) -> pd.DataFrame:
    """`destination_details` rows: destinations by `osm_id`, labels by their first OSM id with
    details (`osm_ids` may list several features of one place), and whether the place is open
    at the time of its type's trip window (None = unknown)."""
    if details.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)
    by_id = details.set_index("osm_id")
    cols = ["destination_id", "destination_type", "osm_id"]
    pairs = [destinations[cols]]
    if labels is not None and len(labels):
        lab = labels[["destination_id", "destination_type", "osm_ids"]].assign(
            osm_id=labels["osm_ids"].astype(str).str.split(r"[,; ]+")
        )
        pairs.append(lab.explode("osm_id")[cols])
    ids = pd.concat(pairs, ignore_index=True)
    ids = ids[ids["osm_id"].isin(by_id.index)]
    out = ids.join(by_id, on="osm_id").drop_duplicates("destination_id").reset_index(drop=True)
    windows = windows or {}
    out["open_in_window"] = [
        open_at(oh, *windows[t]) if t in windows and isinstance(oh, str) else None
        for oh, t in zip(out["opening_hours"], out["destination_type"], strict=True)
    ]
    out["open_in_window"] = out["open_in_window"].astype("boolean")
    return out[OUT_COLUMNS]
