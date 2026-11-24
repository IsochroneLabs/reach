"""Zensus 100 m CSV: column check, bbox filter while reading, cell geometries in EPSG:25832."""

from __future__ import annotations

from pathlib import Path

import pytest

from reach_pipeline import zensus
from reach_pipeline.errors import StageValidationError

CSV = """GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner
CRS3035RES100mN2822200E4250500;4250550;2822250;271
CRS3035RES100mN2822200E4250600;4250650;2822250;3
CRS3035RES100mN2700000E4000000;4000050;2700050;10
"""


@pytest.fixture
def csv(tmp_path: Path) -> Path:
    path = tmp_path / "grid.csv"
    path.write_text(CSV, encoding="ascii")
    return path


def test_read_grid_filters_bbox(csv: Path) -> None:
    grid = zensus.read_grid(csv, (4250000, 2822000, 4251000, 2823000))
    assert list(grid["cell_id"]) == [
        "CRS3035RES100mN2822200E4250500",
        "CRS3035RES100mN2822200E4250600",
    ]
    assert grid["population"].tolist() == [271, 3]


def test_cell_geometries(csv: Path) -> None:
    cells = zensus.cell_geometries(zensus.read_grid(csv, (4250000, 2822000, 4251000, 2823000)))
    assert cells.crs.to_string() == "EPSG:25832"
    assert cells["origin_geom"].crs.to_string() == "EPSG:25832"
    assert cells.area.to_numpy() == pytest.approx(10_000, rel=0.01)  # 100 m cell, slight distortion
    assert cells.geometry.contains(cells["origin_geom"]).all()


def test_missing_column_fails(tmp_path: Path) -> None:
    path = tmp_path / "grid.csv"
    path.write_text("GITTER_ID_100m;x;y;Einwohner\nA;1;2;3\n", encoding="ascii")
    with pytest.raises(StageValidationError, match="x_mp_100m"):
        zensus.read_grid(path, (0, 0, 10, 10))
