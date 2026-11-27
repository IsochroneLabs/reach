"""OSM details of destinations for the app (notes N29)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from reach_pipeline import osm_details
from reach_pipeline.config import load_config

REPO = Path(__file__).resolve().parents[2]


def _seq(path: Path, features: list[dict]) -> None:
    path.write_text(
        "".join("\x1e" + json.dumps({"type": "Feature", "properties": f}) + "\n" for f in features),
        encoding="utf-8",
    )


def test_details_join_types_and_labels_and_window(tmp_path: Path) -> None:
    _seq(
        tmp_path / "destinations.geojsonseq",
        [
            {"@type": "node", "@id": 1, "opening_hours": "Mo-Sa 07:00-20:00", "website": "x.de"},
            {"@type": "way", "@id": 2, "opening_hours": "Fr-Sa 22:00-03:00", "wheelchair": "no"},
            {"@type": "node", "@id": 3, "shop": "bakery"},
        ],
    )
    _seq(
        tmp_path / "labels.geojsonseq",
        [{"@type": "node", "@id": 4, "contact:website": "https://club.de"}],
    )
    det = osm_details.read([tmp_path / "destinations.geojsonseq", tmp_path / "labels.geojsonseq"])
    assert set(det["osm_id"]) == {"n1", "w2", "n4"}
    assert pd.isna(det.set_index("osm_id").at["n1", "website"])  # not an http(s) URL
    dest = pd.DataFrame(
        {
            "destination_id": ["grocery:n1", "nightlife:w2", "grocery:n3"],
            "destination_type": ["grocery", "nightlife", "grocery"],
            "osm_id": ["n1", "w2", "n3"],
        }
    )
    labels = pd.DataFrame(
        {"destination_id": ["sport:climbing:n4"], "destination_type": ["sport"], "osm_ids": ["n4"]}
    )
    windows = osm_details.window_times(load_config(REPO / "config" / "config.yaml"))
    out = osm_details.for_destinations(dest, labels, det, windows).set_index("destination_id")
    assert list(out.columns) == osm_details.OUT_COLUMNS[1:]
    assert out.at["grocery:n1", "open_in_window"]  # Tuesday 18:00
    assert out.at["nightlife:w2", "open_in_window"]  # Saturday 00:30, from Friday 22:00
    assert pd.isna(out.at["sport:climbing:n4", "open_in_window"])  # no opening hours
    assert out.at["sport:climbing:n4", "website"] == "https://club.de"
    assert "grocery:n3" not in out.index
