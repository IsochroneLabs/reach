"""Geocoding of listing addresses against the run's address index (F4.5, methodology §8.1).

Order: exact house number → street midpoint → the ad's own map marker. The precision is stored
with the listing; `house` is exact, `street` and `marker` are marked approximate in the app.
"""

from __future__ import annotations

import re

import geopandas as gpd
import pandas as pd

CRS = "EPSG:25832"

_STREET_ABBR = (("straße", "str"), ("strasse", "str"), ("str.", "str"))


def norm_street(text: str | None) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    t = text.lower().strip()
    for a, b in _STREET_ABBR:
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9äöüß]+", "", t) or None


def split_address(text: str | None) -> tuple[str | None, str | None]:
    """`Wilhelmstraße 5a` → (`wilhelmstr`, `5a`); no number → (street, None)."""
    if not isinstance(text, str) or not text:
        return None, None
    m = re.match(r"^\s*(.*?)\s+(\d+\s*[a-zA-Z]?)\s*$", text)
    if not m:
        return norm_street(text), None
    return norm_street(m.group(1)), m.group(2).replace(" ", "").lower()


def geocode(listings: pd.DataFrame, addresses: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Point and precision per listing: exact house number → `house`, street mean → `street`,
    else the ad's own map marker → `marker` (approximate), else none."""
    a = addresses.assign(
        _s=addresses["street"].map(norm_street),
        _h=addresses["housenumber"].astype(str).str.replace(" ", "").str.lower(),
        _x=addresses.geometry.x,
        _y=addresses.geometry.y,
    )
    house = a.groupby(["_s", "_h"])[["_x", "_y"]].mean()
    street = a.groupby("_s")[["_x", "_y"]].mean()
    parts = listings["address_text"].map(split_address)
    s = parts.str[0]
    h = parts.str[1]
    xy = pd.DataFrame(index=listings.index, columns=["x", "y"], dtype=float)
    precision = pd.Series(pd.NA, index=listings.index, dtype="object")
    hk = pd.MultiIndex.from_arrays([s, h])
    hit = hk.isin(house.index)
    xy.loc[hit, ["x", "y"]] = house.loc[hk[hit]].to_numpy()
    precision[hit] = "house"
    st = ~hit & s.isin(street.index).to_numpy()
    xy.loc[st, ["x", "y"]] = street.loc[s[st]].to_numpy()
    precision[st] = "street"
    marker = precision.isna() & listings["source_lat"].notna()
    if marker.any():
        pts = gpd.GeoSeries(
            gpd.points_from_xy(
                listings.loc[marker, "source_lon"], listings.loc[marker, "source_lat"]
            ),
            crs="EPSG:4326",
        ).to_crs(CRS)
        xy.loc[marker, "x"] = pts.x.to_numpy()
        xy.loc[marker, "y"] = pts.y.to_numpy()
        precision[marker] = "marker"
    geom = gpd.points_from_xy(xy["x"], xy["y"])
    out = gpd.GeoDataFrame(listings.assign(geocode_precision=precision), geometry=geom, crs=CRS)
    out.loc[precision.isna(), "geometry"] = None
    return out


def assign_cells(listings: gpd.GeoDataFrame, cells: pd.DataFrame) -> pd.Series:
    """Zensus cell of each point; points outside the run's cells get none."""
    from reach_pipeline.zensus import cell_ids

    ok = listings.geometry.notna() & ~listings.geometry.is_empty
    ids = pd.Series(pd.NA, index=listings.index, dtype="object")
    if ok.any():
        ids[ok] = cell_ids(listings.loc[ok].geometry)["cell_id"].to_numpy()
    return ids.where(ids.isin(set(cells["cell_id"])))
