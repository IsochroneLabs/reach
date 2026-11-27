"""OSM opening_hours subset (notes N29)."""

from __future__ import annotations

import pytest

from reach_pipeline.opening_hours import open_at

TU, SA = 1, 5


@pytest.mark.parametrize(
    ("text", "day", "hhmm", "expected"),
    [
        ("Mo-Sa 07:00-22:00", TU, "18:00", True),
        ("Mo-Sa 07:00-22:00", 6, "18:00", False),
        ("Mo-Fr 08:00-12:00,14:00-18:00", TU, "12:30", False),
        ("Mo-Fr 08:00-12:00,14:00-18:00; Tu off", TU, "09:00", False),
        ("24/7", SA, "00:30", True),
        ("Fr 20:00-02:00", SA, "00:30", True),  # past midnight from Friday
        ("Fr-Sa 20:00-03:00", SA, "02:30", True),
        ("Th-Sa 21:00-03:00", TU, "00:30", False),
        ("08:00-20:00", 6, "10:00", True),
        ("Mo-Fr 08:00-18:00; PH off", TU, "10:00", True),
        ("Mo-Sa 08:00-20:00; Su,PH off", 6, "10:00", False),
        ("Mo-Fr 08:00-20:00; Sa, Su, PH off", SA, "10:00", False),
        ("Mo-Fr 08:00-12:00, Mo,Tu,Th 14:00-18:00", TU, "15:00", True),
        ("Mo-Fr 08:00-12:00, Mo,Tu,Th 14:00-18:00", 2, "15:00", False),
        ("Mo-Fr 08:00-12:00, Sa 09:00-12:00", SA, "10:00", True),
        ("Mo-Su,PH 10:00-22:00", 6, "21:00", True),
        ("Mo-Fr 08:00-18:00; week 01-10 off", TU, "10:00", None),
        ('"Termine nach Vereinbarung"', TU, "10:00", None),
        ("", TU, "10:00", None),
    ],
)
def test_open_at(text: str, day: int, hhmm: str, expected: bool | None) -> None:
    h, m = (int(x) for x in hhmm.split(":"))
    assert open_at(text, day, h * 60 + m) is expected
