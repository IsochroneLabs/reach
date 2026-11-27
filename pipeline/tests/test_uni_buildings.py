"""Official address list of the university buildings → campus sites (notes N30, no network)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from reach_pipeline import uni_buildings
from reach_pipeline.campus import load_campus

REPO = Path(__file__).resolve().parents[2]

LIST = """<table class="ut-table--striped"><tr><td><h3>A B C</h3></td></tr>
<tr><td><a href="/universitaet/standort-und-anfahrt/lageplaene/karte-d-altstadt/alte-aula/"
 class="internal-link">Alte Aula &ndash; Münzgasse 30</a></td></tr>
<tr><td><a href="/universitaet/standort-und-anfahrt/lageplaene/karte-a-morgenstelle/adm-16/"
 class="internal-link">Auf der Morgenstelle 16</a></td></tr></table>"""

PAGE = """<nav><li>Karte D: Altstadt</li></nav><main><ul><li>Karte A: Morgenstelle</li>
<li>Karte D: Altstadt</li></ul><h1>Auf der Morgenstelle 16</h1><p>Hörsaalzentrum</p>
<p>Mensa</p><p>Auf der Morgenstelle 16</p><p>72076 Tübingen</p><p>Nr. 12</p></main>"""


def test_list_and_page() -> None:
    entries = uni_buildings.parse_list(LIST)
    assert entries["sheet"].tolist() == ["d", "a"]
    assert entries["title"].tolist() == ["Alte Aula – Münzgasse 30", "Auf der Morgenstelle 16"]
    info = uni_buildings.parse_page(PAGE)
    assert info == {"address": "Auf der Morgenstelle 16", "institutes": "Hörsaalzentrum; Mensa"}
    assert uni_buildings.title_address("Alte Aula – Münzgasse 30") == "Münzgasse 30"


def test_address_keys_and_candidates() -> None:
    assert uni_buildings.address_key("Liebermeisterstraße 12 bis 16") == "liebermeisterstr 12"
    assert uni_buildings.address_key("Sand 6/7") == "sand 6"
    assert uni_buildings.address_key("Geschwister-Scholl-Platz") is None
    assert uni_buildings.candidates(
        "Gmelinstraße 6, Eingang Nauklerstraße", "Alte Physik – Gmelinstraße 6"
    ) == ["gmelinstr 6"]
    assert uni_buildings.candidates(
        "Wilhelmstraße 9 / Nauklerstraße 2 und 2/1", "Nauklerstraße 2 (mit Wilhelmstraße 9)"
    )[:2] == ["wilhelmstr 9", "nauklerstr 2"]


def test_locate_assigns_the_nearest_site() -> None:
    campus = load_campus(REPO / "config" / "config.yaml")
    pts = gpd.GeoSeries([Point(9.0561, 48.5389), Point(9.0557, 48.5198)], crs=4326).to_crs(
        "EPSG:25832"
    )
    addresses = gpd.GeoDataFrame(
        {
            "street": ["Maria-von-Linden-Straße", "Münzgasse"],
            "housenumber": ["6", "30"],
            "city": ["Tübingen", "Tübingen"],
        },
        geometry=pts.values,
        crs="EPSG:25832",
    )
    buildings = pd.DataFrame(
        {
            "title": ["Maria-von-Linden-Straße 6", "Alte Aula – Münzgasse 30", "Schulberg 2"],
            "sheet": ["c", "d", "d"],
            "address": ["Maria-von-Linden-Straße 6", "Münzgasse 30", "Schulberg 2"],
            "institutes": ["", "", ""],
        }
    )
    out = uni_buildings.locate(buildings, addresses, campus).set_index("title")
    assert out.at["Maria-von-Linden-Straße 6", "site"] == "cyber_valley"
    assert out.at["Alte Aula – Münzgasse 30", "site"] == "altstadt"
    assert out.at["Schulberg 2", "located"] == "campus.yaml"  # building_points
    assert out["site_m"].max() < 300
