"""Listing crawl on synthetic search pages and the anonymised ad fixtures (no network)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd
import pytest
from shapely.geometry import Point

from reach_pipeline.config import load_config
from reach_pipeline.errors import ExternalError
from reach_pipeline.listings import crawl
from reach_pipeline.listings.geocode import geocode, split_address
from reach_pipeline.zensus import cell_ids

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures" / "listings"
CARD = (
    '<a class="wgg-list-card offer_list_item " data-id="{i}" href="/{path}.{i}.html" '
    'aria-label="x">'
)


def _cfg(tmp_path: Path):
    cfg = load_config(REPO / "config" / "config.yaml")
    lst = cfg.listings.model_copy(update={"request_interval_s": 10, "max_search_pages": 2})
    return cfg.model_copy(update={"data_dir": tmp_path, "listings": lst})


def _run_dir(tmp_path: Path) -> None:
    v = tmp_path / "runs" / "20261127T000000Z" / "validate"
    v.mkdir(parents=True)
    pts = gpd.GeoSeries([Point(9.055, 48.534), Point(9.056, 48.534)], crs=4326).to_crs(25832)
    gpd.GeoDataFrame(
        {"street": ["Spemannstraße", "Spemannstraße"], "housenumber": ["1", "3"]},
        geometry=pts,
    ).to_parquet(v / "addresses.parquet")
    cell_ids(pts)[["cell_id"]].to_parquet(v / "cells.parquet")


def _transport(pages: dict[str, str], seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, text=pages.get(request.url.path, ""))

    return httpx.MockTransport(handler)


def test_crawl_fetches_new_ads_geocodes_and_carries_over(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(crawl.time, "sleep", lambda s: None)
    cfg = _cfg(tmp_path)
    _run_dir(tmp_path)
    ad = (FIX / "wg_minimal.html").read_text(encoding="utf-8")
    wg_path = "/wg-zimmer-in-Tuebingen-Innenstadt"
    pages = {
        "/wg-zimmer-in-Tuebingen.127.0.1.0.html": CARD.format(i=90000001, path=wg_path[1:]),
        "/1-zimmer-wohnungen-in-Tuebingen.127.1.1.0.html": "<p>keine</p>",
        "/wohnungen-in-Tuebingen.127.2.1.0.html": "<p>keine</p>",
        f"{wg_path}.90000001.html": ad,
    }
    seen: list[str] = []
    client = httpx.Client(base_url=cfg.listings.base_url, transport=_transport(pages, seen))
    with pytest.raises(Exception, match="no ads on the first studio page"):
        crawl.run(cfg, client=client)
    pages["/1-zimmer-wohnungen-in-Tuebingen.127.1.1.0.html"] = pages[
        "/wg-zimmer-in-Tuebingen.127.0.1.0.html"
    ]
    pages["/wohnungen-in-Tuebingen.127.2.1.0.html"] = pages[
        "/1-zimmer-wohnungen-in-Tuebingen.127.1.1.0.html"
    ]
    seen.clear()
    out = gpd.read_parquet(crawl.run(cfg, client=client) / "listings.parquet")
    assert len(out) == 1 and seen.count(f"{wg_path}.90000001.html") == 1
    row = out.iloc[0]
    assert row["geocode_precision"] == "street" and isinstance(row["cell_id"], str)
    # second day: the ad is known, only the search pages are fetched
    seen.clear()
    again = gpd.read_parquet(crawl.run(cfg, client=client) / "listings.parquet")
    assert f"{wg_path}.90000001.html" not in seen and len(again) == 1
    assert again.iloc[0]["first_seen"] == row["first_seen"]


def test_geocode_precision_order() -> None:
    addr = gpd.GeoDataFrame(
        {"street": ["Wilhelmstraße"], "housenumber": ["5"]},
        geometry=[Point(500_000, 5_375_000)],
        crs=25832,
    )
    lst = pd.DataFrame(
        {
            "address_text": ["Wilhelmstr. 5", "Wilhelmstraße 99", "Nowhere 1", None],
            "source_lat": [None, None, 48.52, None],
            "source_lon": [None, None, 9.05, None],
        }
    )
    g = geocode(lst, addr)
    assert g["geocode_precision"].tolist()[:3] == ["house", "street", "marker"]
    assert pd.isna(g["geocode_precision"].iloc[3]) and g.geometry.iloc[3] is None
    assert split_address("Hölderlinstraße 10 a") == ("hölderlinstr", "10a")


def test_block_page_stops(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    t = httpx.MockTransport(lambda r: httpx.Response(200, text="Bitte lösen Sie das Captcha"))
    f = crawl.Fetcher(cfg.listings, httpx.Client(base_url=cfg.listings.base_url, transport=t))
    with pytest.raises(ExternalError, match="block page"):
        f.get("/x")
    ok = httpx.MockTransport(
        lambda r: httpx.Response(200, text='<script src="recaptcha.js"></script>' + CARD)
    )
    f = crawl.Fetcher(cfg.listings, httpx.Client(base_url=cfg.listings.base_url, transport=ok))
    assert "recaptcha" in f.get("/y")
