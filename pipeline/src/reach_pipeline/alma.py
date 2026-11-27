"""Course sessions from the public Alma timetable (F3.2, notes N23a, N31).

Alma (HISinOne) lists every session of a day on the public page "Tagesaktuelle Veranstaltungen"
(no login). For one reference teaching week we fetch one page per weekday (all rows on one page)
and keep course id, title, start, end, module number, parallel group, kind, room and building
(never people's names). `address_of` maps Alma's building names to the university's official
buildings (`alma.building_addresses` in `config/campus.yaml`); which programmes a course belongs
to comes from its detail page (`alma_courses.py`), the hours per programme and building from
`programmes.py`.

Polite by design (team decision, notes N23a): one session, two requests per day, `rate_limit_s`
between requests, identifying user agent, retries only for network errors, once per semester;
raw pages are kept under `data/raw/alma/<semester>/` and reused.

Usage: `uv run python -m reach_pipeline.alma crawl|sessions [--config config/config.yaml]`.
"""

from __future__ import annotations

import argparse
import gzip
import html
import logging
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from reach_pipeline.campus import Campus, load_campus
from reach_pipeline.config import Alma, load_config
from reach_pipeline.errors import ExternalError, StageValidationError

log = logging.getLogger(__name__)

FORM = "showEventsAndExaminationsOnDateForm"
TABLE = (
    FORM + ":tabContainer:term-planning-container:coursesAndExaminationsOnDateListTable"
    ":coursesAndExaminationsOnDateListTable"
)
# Table columns of the day view (HISinOne CSS classes `columnN`); lecturers (10, 11) are skipped.
COLUMNS = {
    1: "title",
    3: "start",
    4: "end",
    6: "number",
    7: "group",
    9: "kind",
    12: "room",
    13: "semester",
}
SESSION_COLUMNS = [
    "day",
    "unit_id",
    "period_id",
    "title",
    "start",
    "end",
    "number",
    "group",
    "kind",
    "room",
    "building",
    "semester",
]
_UNIT = re.compile(r"unitId=(\d+)&(?:amp;)?periodId=(\d*)")
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _text(fragment: str) -> str:
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


# --- parsing (pure) ------------------------------------------------------------------------------


def form_fields(page: str, form_id: str) -> tuple[str, dict[str, str]]:
    """Action URL and the fields a browser would submit (hidden, text, checked boxes, selects)."""
    start = page.find(f'id="{form_id}"')
    if start < 0:
        raise StageValidationError(f"alma: form {form_id} not found (page layout changed?)")
    form_tag = page[page.rfind("<form", 0, start + 1) : page.find(">", start) + 1]
    body = page[start : page.find("</form>", start)]
    action = html.unescape(re.search(r'action="([^"]+)"', form_tag).group(1))
    data: dict[str, str] = {}
    for tag in re.findall(r"<input[^>]*>", body):
        name = re.search(r'name="([^"]+)"', tag)
        kind = (re.search(r'type="([^"]+)"', tag) or [None, "text"])[1]
        if not name or kind in ("submit", "button", "image"):
            continue
        if kind in ("checkbox", "radio") and not re.search(r"\schecked\b", tag):
            continue
        value = re.search(r'value="([^"]*)"', tag)
        data[html.unescape(name.group(1))] = html.unescape(value.group(1)) if value else ""
    for name, options in re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', body, re.S):
        opt = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', options) or re.search(
            r'<option[^>]*value="([^"]*)"', options
        )
        data[html.unescape(name)] = html.unescape(opt.group(1)) if opt else ""
    return action, data


def day_request(page: str, day: date, rows: int) -> tuple[str, dict[str, str]]:
    """Form submission that shows all sessions of `day` on one page."""
    action, data = form_fields(page, FORM)
    refresh = FORM + ":tabContainer:date-selection-container:refreshBtn"
    data.update(
        {
            FORM + ":tabContainer:date-selection-container:date": day.strftime("%d.%m.%Y"),
            FORM + ":tabContainer:filter-container:selectCheckbox": "selectAllCourses",
            TABLE + "Navi2NumRowsInput": str(rows),
            "refreshButtonClickedId": refresh,
            "activePageElementId": refresh,
            refresh: "",
        }
    )
    return action, data


def building_of(room: str) -> str:
    """The last top-level bracket of the room, without its floor: `Hörsaal N01 (Hörsaalzentrum
    Morgenstelle (0))` → `Hörsaalzentrum Morgenstelle`; `Hörsaal A1 (A-206) (Cyber Valley Campus,
    MVL1 (EG))` → `Cyber Valley Campus, MVL1`."""
    room = room.rstrip()
    if not room.endswith(")"):
        return room.strip()
    depth, start = 0, None
    for i in range(len(room) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(room[i], 0)
        if depth == 0:
            start = i
            break
    if start is None:
        return room.strip()
    inner = room[start + 1 : -1]
    return re.sub(r"\s*\([^()]*\)\s*$", "", inner).strip()


def parse_day(page: str, day: date) -> pd.DataFrame:
    """Sessions of one day page; fails if the heading does not name `day` (wrong page)."""
    heading = re.search(r"Suchergebnisse für [^<]*?(\d{1,2})\. ([A-Za-zäöü]+) (\d{4})", page)
    if not heading or int(heading.group(1)) != day.day or int(heading.group(3)) != day.year:
        raise StageValidationError(f"alma: page is not the day view of {day.isoformat()}")
    total = re.search(r"Suchergebnis:\s*([\d.]+)\s*Ergebnisse", _TAG.sub(" ", page))
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cols = {
            int(m.group(1)): _text(cell)
            for attrs, cell in re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
            if (m := re.search(r"\bcolumn(\d+)\b", attrs)) and int(m.group(1)) in COLUMNS
        }
        if 3 in cols and 4 in cols and re.fullmatch(r"\d\d:\d\d", cols[3]):
            unit = _UNIT.search(tr)
            ids = {"unit_id": unit.group(1), "period_id": unit.group(2)} if unit else {}
            rows.append({COLUMNS[k]: cols.get(k, "") for k in COLUMNS} | ids)
    out = pd.DataFrame(rows, columns=[*COLUMNS.values(), "unit_id", "period_id"]).fillna("")
    if total and len(out) != int(total.group(1).replace(".", "")):
        raise StageValidationError(
            f"alma: {day.isoformat()} shows {len(out)} of {total.group(1)} sessions (paging?)"
        )
    out.insert(0, "day", day.isoformat())
    out["building"] = out["room"].map(lambda r: building_of(r) if r else "")
    return out[SESSION_COLUMNS]


def _hours(start: pd.Series, end: pd.Series) -> pd.Series:
    def minutes(s: pd.Series) -> pd.Series:
        hm = s.str.split(":", expand=True).astype(int)
        return hm[0] * 60 + hm[1]

    return (minutes(end) - minutes(start)).clip(lower=0) / 60


def address_of(buildings: pd.Series, campus: Campus) -> pd.Series:
    """Official building per Alma building name from `alma.building_addresses` (first match)."""
    out = pd.Series(pd.NA, index=buildings.index, dtype="object")
    for title, patterns in campus.alma.building_addresses.items():
        hit = out.isna() & buildings.str.contains("|".join(patterns), case=False, regex=True)
        out[hit] = title
    return out


def coverage(sessions: pd.DataFrame, campus: Campus, semester: str) -> dict[str, float | int]:
    """Share of the sessions with a room whose building maps to an official building."""
    s = sessions[(sessions["semester"] == semester) & (sessions["room"] != "")]
    matched = address_of(s["building"], campus).notna()
    return {
        "sessions": int(len(sessions)),
        "with_room": int(len(s)),
        "building_matched": round(float(matched.mean()), 3) if len(s) else 0.0,
    }


# --- network ------------------------------------------------------------------------------------


def _get(client: httpx.Client, cfg: Alma, method: str, url: str, **kw) -> str:
    for attempt in range(cfg.retries + 1):
        try:
            r = client.request(method, url, **kw)
            r.raise_for_status()
            return r.text
        except httpx.TransportError as exc:
            if attempt == cfg.retries:
                raise ExternalError(f"alma: {method} {url} failed: {exc}") from exc
            time.sleep(cfg.backoff_s * 2**attempt)
    raise AssertionError("unreachable")


def week(cfg: Alma) -> list[date]:
    return [cfg.reference_week + timedelta(days=i) for i in range(cfg.weekdays)]


def crawl(cfg: Alma, out_dir: Path, force: bool = False) -> list[Path]:
    """Fetch the day pages of the reference week (skips days already on disk unless `force`)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    headers = {"User-Agent": cfg.user_agent}
    with httpx.Client(
        base_url=cfg.base_url, headers=headers, timeout=cfg.timeout_s, follow_redirects=True
    ) as client:
        for day in week(cfg):
            path = out_dir / f"{day.isoformat()}.html.gz"
            paths.append(path)
            if path.exists() and not force:
                log.info("alma %s: reused %s", day, path.name)
                continue
            start = _get(client, cfg, "GET", cfg.day_view_path)
            time.sleep(cfg.rate_limit_s)
            action, data = day_request(start, day, cfg.rows_per_page)
            page = _get(client, cfg, "POST", action, data=data)
            parse_day(page, day)  # fail loudly before storing a wrong page
            path.write_bytes(gzip.compress(page.encode("utf-8")))
            log.info("alma %s: %d kB", day, len(page) // 1024)
            time.sleep(cfg.rate_limit_s)
    return paths


def sessions_of(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for p in paths:
        day = date.fromisoformat(p.name.split(".")[0])
        frames.append(parse_day(gzip.decompress(p.read_bytes()).decode("utf-8"), day))
    return pd.concat(frames, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="reach_pipeline.alma")
    ap.add_argument("action", choices=["crawl", "sessions"])
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--force", action="store_true", help="fetch again although pages exist")
    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    if cfg.alma is None:
        log.error("config has no alma section")
        return 2
    campus = load_campus(Path(args.config), generated=False)
    out_dir = cfg.data_dir / "raw" / "alma" / cfg.alma.semester_key
    try:
        paths = crawl(cfg.alma, out_dir, args.force) if args.action == "crawl" else None
        paths = paths or sorted(out_dir.glob("*.html.gz"))
        if not paths:
            raise StageValidationError(f"alma: no pages under {out_dir}; run crawl first")
        sessions = sessions_of(paths)
        sessions.to_parquet(out_dir / "sessions.parquet", index=False)
        log.info("alma coverage: %s", coverage(sessions, campus, cfg.alma.semester))
        s = sessions[sessions["room"] != ""]
        unknown = s.loc[address_of(s["building"], campus).isna(), "building"]
        top = unknown[unknown != ""].value_counts().head(15)
        log.info("alma buildings without an official building (top): %s", top.to_dict())
    except (ExternalError, StageValidationError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
