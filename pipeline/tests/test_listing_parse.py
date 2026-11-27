"""Listing parser (F4.2): anonymised WG-Gesucht fixtures → parser output of the data contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reach_pipeline.config import load_config
from reach_pipeline.listings.parse import (
    REDACTED,
    Listing,
    coverage,
    parse_ad,
    parse_search,
    strip_contact,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "pipeline" / "tests" / "fixtures" / "listings"
NAMES = ["wg_minimal", "wg_rich", "wg_medium", "studio", "flat"]
FETCHED = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
CFG = load_config(REPO / "config" / "config.yaml").listings


def _parse(raw: str, url: str | None = None) -> Listing:
    return parse_ad(
        raw,
        url,
        FETCHED,
        description_max_chars=CFG.description_max_chars,
        title_max_chars=CFG.title_max_chars,
    )


def _fixture(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_fixture_matches_expected(name):
    """Every fixture parses to its expected JSON (shared with the browser parser, F4.3)."""
    expected = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert _parse(_fixture(name)).to_dict() == expected


@pytest.mark.parametrize("name", NAMES)
def test_fixture_is_small_and_fully_covered(name):
    assert (FIXTURES / f"{name}.html").stat().st_size < 200_000
    listing = _parse(_fixture(name))
    assert coverage(listing) == 1.0, listing.warnings
    assert listing.errors == []


def test_contact_data_is_stripped_from_the_excerpt():
    excerpt = _parse(_fixture("wg_rich")).description_excerpt
    assert REDACTED in excerpt
    for leak in ("example.org", "0170", "1234567", "@wg_beispiel"):
        assert leak not in excerpt


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("Ruf an: +49 (0)7071 123456!", "123456"),
        ("Tel. 07071/12 34 56", "34 56"),
        ("Mail: a.b-c@uni-tuebingen.de", "@uni"),
        ("Insta @meine.wg", "@meine"),
        ("Infos auf https://example.org/x?y=1", "example"),
    ],
)
def test_strip_contact(text, leak):
    out = strip_contact(text)
    assert leak not in out and REDACTED in out


def test_strip_contact_keeps_prices_dates_and_sizes():
    text = "Miete 590 €, frei ab 01.12.2026, 18 m², 3er-WG, Bus 2 Minuten"
    assert strip_contact(text) == text


def test_excerpt_is_cut_at_a_word():
    listing = parse_ad(
        _fixture("wg_rich"), None, FETCHED, description_max_chars=40, title_max_chars=10
    )
    assert len(listing.description_excerpt) <= 42
    assert listing.description_excerpt.endswith("…")
    assert listing.title.endswith("…")


def test_missing_address_is_an_error_not_a_crash():
    raw = _fixture("wg_minimal")
    start = raw.index("Adresse")
    raw = (
        raw[: raw.rindex('<div class="panel section_panel">', 0, start)]
        + raw[raw.index("Verfügbarkeit") :]
    )
    listing = _parse(raw)
    assert "no_address" in listing.errors
    assert "unknown:address_text" in listing.warnings
    assert listing.rent_total_eur == 590


def test_unknown_page_gives_not_an_ad():
    raw = "<html><body><h1>Bitte bestätigen Sie, dass Sie kein Roboter sind</h1></body></html>"
    listing = _parse(raw, "https://www.wg-gesucht.de/wg-zimmer-in-Tuebingen-Wanne.1.html")
    assert listing.errors == ["not_an_ad"]
    assert listing.kind == "wg_room"
    assert listing.listing_id is None


@pytest.mark.parametrize("cut", [0.2, 0.5, 0.8])
def test_truncated_page_never_raises(cut):
    raw = _fixture("wg_rich")
    listing = _parse(raw[: int(len(raw) * cut)])
    assert isinstance(listing, Listing)


def test_german_numbers_and_ab_sofort():
    raw = (
        _fixture("flat")
        .replace("1150&euro;", "1.150,50&euro;")
        .replace("120m&sup2;", "18,5m&sup2;")
        .replace("01.12.2026", "ab sofort")
    )
    listing = _parse(raw)
    assert listing.rent_total_eur == 1150  # rounded half to even
    assert listing.size_m2 == 18.5
    assert listing.available_from == "2026-11-27"


def test_relative_online_time_needs_the_fetch_time():
    listing = parse_ad(
        _fixture("wg_minimal"), None, None, description_max_chars=10, title_max_chars=10
    )
    assert listing.online_text == "10 Stunden"
    assert listing.online_since is None
    assert _parse(_fixture("wg_minimal")).online_since == "2026-11-27T02:00:00+00:00"


def test_search_page_hits_in_order_without_duplicates():
    card = (
        '<a id="liste-details-ad-{i}" class="wgg-list-card offer_list_item " data-id="{i}" '
        'href="/{path}.{i}.html" aria-label="x">'
    )
    raw = "".join(
        card.format(i=i, path=p)
        for i, p in [
            (90000001, "wg-zimmer-in-Tuebingen-Innenstadt"),
            (90000004, "1-zimmer-wohnungen-in-Tuebingen-Lustnau"),
            (90000001, "wg-zimmer-in-Tuebingen-Innenstadt"),
            (90000005, "wohnungen-in-Tuebingen-Derendingen"),
        ]
    )
    hits = parse_search(raw, "https://www.wg-gesucht.de")
    assert [h.listing_id for h in hits] == [
        "wg_gesucht:90000001",
        "wg_gesucht:90000004",
        "wg_gesucht:90000005",
    ]
    assert [h.kind for h in hits] == ["wg_room", "studio", "flat"]
    assert (
        hits[0].url == "https://www.wg-gesucht.de/wg-zimmer-in-Tuebingen-Innenstadt.90000001.html"
    )
