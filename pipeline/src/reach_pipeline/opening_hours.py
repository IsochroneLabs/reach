"""Is a place open at a given weekday and time? A small reader for the common subset of the OSM
`opening_hours` syntax (notes N29): `24/7`; rules separated by `;`, later rules replacing earlier
ones for their days; weekday lists and ranges (`Mo-Fr`, `Mo,We`, `Sa-Mo`); time spans that may
pass midnight (`18:00-02:00`); `off`/`closed`. Anything else (public holidays, months, weeks,
sunrise, comments) gives None: unknown, never a guess.
"""

from __future__ import annotations

import re

DAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)"
_DAY_RANGE = rf"{_DAY}(?:-{_DAY})?"
_DAY_LIST = rf"{_DAY_RANGE}(?:\s*,\s*{_DAY_RANGE})*"
_TIME = r"\d{1,2}:\d{2}-\d{1,2}:\d{2}\+?"
_TIME_LIST = rf"{_TIME}(?:\s*,\s*{_TIME})*"
_SUB = re.compile(rf"\s*(?:(?P<days>{_DAY_LIST})\s*)?(?P<what>off|closed|{_TIME_LIST})?\s*(?:,|$)")
_SPAN = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")
FULL_DAY = 24 * 60


class Unsupported(ValueError):
    pass


def _days(spec: str) -> set[int]:
    """Weekdays of a day list; public and school holidays (PH, SH) are dropped because the
    reference dates are never holidays (methodology §5)."""
    out: set[int] = set()
    for part in re.split(r"\s*,\s*", spec.strip()):
        a, _, b = part.partition("-")
        if a in ("PH", "SH") or b in ("PH", "SH"):
            continue
        i, j = DAYS.index(a), DAYS.index(b or a)
        k = i
        while True:
            out.add(k)
            if k == j:
                break
            k = (k + 1) % 7
    return out


def _spans(spec: str) -> list[tuple[int, int]]:
    spans = []
    for h1, m1, h2, m2 in _SPAN.findall(spec):
        a, b = int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)
        spans.append((a, b if b > a else b + FULL_DAY))
    return spans


def _subrules(rule: str) -> list[tuple[str | None, str]]:
    """`Mo-Fr 08:00-12:00, Sa 09:00-12:00` → [("Mo-Fr", "08:00-12:00"), ("Sa", "09:00-12:00")]."""
    out, pos = [], 0
    while pos < len(rule):
        m = _SUB.match(rule, pos)
        if not m or m.end() == pos or not (m.group("days") or m.group("what")):
            raise Unsupported(rule[pos:])
        out.append((m.group("days"), (m.group("what") or "").strip()))
        pos = m.end()
    return out


def rules(text: str) -> dict[int, list[tuple[int, int]]]:
    """Weekday → time spans (minutes; end may exceed 24 h for spans past midnight). Rules after
    `;` replace earlier ones for their days; comma-joined parts of one rule add up."""
    week: dict[int, list[tuple[int, int]]] = {}
    for raw in text.split(";"):
        rule = raw.strip()
        if not rule:
            continue
        if rule == "24/7":
            week.update({d: [(0, FULL_DAY)] for d in range(7)})
            continue
        this: dict[int, list[tuple[int, int]]] = {}
        for days_spec, what in _subrules(rule):
            days = _days(days_spec) if days_spec else set(range(7))
            if what in ("off", "closed"):
                spans: list[tuple[int, int]] = []
            elif what == "":
                spans = [(0, FULL_DAY)]
            else:
                spans = _spans(what)
            for d in days:
                this.setdefault(d, []).extend(spans)
        week.update(this)
    return week


def open_at(text: str | None, weekday: int, minute: int) -> bool | None:
    """True/False if `text` says so for weekday (0 = Monday) and minute of the day, else None."""
    if not text:
        return None
    try:
        week = rules(text.strip())
    except Unsupported:
        return None
    if not week:
        return None
    today = week.get(weekday, [])
    yesterday = week.get((weekday - 1) % 7, [])
    if any(a <= minute < b for a, b in today):
        return True
    return any(a <= minute + FULL_DAY < b for a, b in yesterday)
