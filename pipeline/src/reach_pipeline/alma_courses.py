"""Modules and programmes of each Alma course → compulsory hours per programme and building (N31).

The day view (`alma.py`) knows when and where a session takes place, but not who has to attend.
Each course's public detail page has a tab "Module / Studiengänge" with two tables:

- **modules** the course belongs to, each with a short text `<degree>|<subject>|<H/N>|<PO>-<module>`
  (e.g. `82|410|H|2023-B220` = Bachelor, subject 410, major, exam regulations 2023, module B220)
  and the module name ("Marketing", "Elective Studies", "Wahlpflichtmodul …");
- **programmes** (Studiengänge) with name, degree, subject, major/minor and PO version.

Polite crawl (Juju, 27 Nov 2026): one session, two requests per course (page, then the tab),
`course_rate_limit_s` between requests, only courses with a room in the reference week, once per
semester; raw pages are kept under `data/raw/alma/<semester>/courses/` and reused. The table size
is set to 300 rows once per session (Alma remembers it), so no paging is needed.

Usage: `uv run python -m reach_pipeline.alma_courses crawl [--limit N]`.
"""

from __future__ import annotations

import argparse
import gzip
import logging
import re
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

from reach_pipeline import alma
from reach_pipeline.config import Alma, load_config
from reach_pipeline.errors import ExternalError, StageValidationError

log = logging.getLogger(__name__)

FORM = "detailViewData"
_PFX = FORM + ":tabContainer:term-planning-container:"
TAB = _PFX + "tabs:modulesCourseOfStudiesTab"
_ROWS = {
    _PFX + "modules:moduleAssignments:moduleAssignmentsNavi2NumRowsInput": "300",
    _PFX
    + "courseOfStudies:courseOfStudyAssignments:courseOfStudyAssignmentsNavi2NumRowsInput": "300",
    _PFX
    + "courseOfStudies:courseOfStudyAssignments:courseOfStudyAssignmentsNavi2NumRowsRefresh": "",
}
_ROWS_INPUT = re.compile(r'NumRowsInput"[^>]*value="(\d+)"')
MODULE_COLUMNS = ["unit_id", "module", "code", "name", "open"]
PROGRAMME_COLUMNS = ["unit_id", "programme", "kind", "degree", "subject", "major", "po", "open"]
MAX_ROWS = 300  # Alma's largest table size; a course in more programmes is open to everyone
_CODE = re.compile(r"^(\d+)\|(\d+)\|(?:-\|)*([HN])\|(?:-\|)*(\d{4})-(.+)$")


# --- parsing (pure) ------------------------------------------------------------------------------


def _table(page: str, marker: str) -> list[dict[int, str]]:
    """Rows of the table whose id contains `marker` as {column: text}."""
    start = page.find(marker)
    if start < 0:
        return []
    end = page.find("</table>", start)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page[start:end], re.S):
        cols = {
            int(m.group(1)): alma._text(cell)
            for attrs, cell in re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
            if (m := re.search(r"\bcolumn(\d+)\b", attrs))
        }
        if cols:
            rows.append(cols)
    return rows


def _total(page: str, marker: str) -> int | None:
    start = page.find(marker)
    if start < 0:
        return None
    m = re.search(r"Suchergebnis:\s*([\d.]+)\s*Ergebnis", alma._TAG.sub(" ", page[start:]))
    return int(m.group(1).replace(".", "")) if m else None


def parse_course(page: str, unit_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Module and programme rows of one course tab page; fails on a wrong or truncated page.

    A table with more rows than Alma shows at most (`MAX_ROWS`, e.g. a course for 655
    programmes) marks the course `open`: it is open to everyone and says nothing about a single
    programme (N31)."""
    if "modulesCourseOfStudiesTab" not in page or "Zugeordnete Studieng" not in page:
        raise StageValidationError(f"alma course {unit_id}: not the 'Module / Studiengänge' tab")
    mods = [
        {"unit_id": unit_id, "module": r.get(0, ""), "code": r.get(1, ""), "name": r.get(2, "")}
        for r in _table(page, "moduleAssignmentsTable")
        if 1 in r
    ]
    progs = [
        {
            "unit_id": unit_id,
            "programme": r.get(0, ""),
            "kind": r.get(1, ""),
            "degree": r.get(2, ""),
            "subject": r.get(3, ""),
            "major": r.get(6, ""),
            "po": r.get(7, "").removeprefix("PO-Version ").strip(),
        }
        for r in _table(page, "courseOfStudyAssignmentsTable")
        if 3 in r
    ]
    is_open = False
    for rows, marker in (
        (mods, "moduleAssignmentsTable"),
        (progs, "courseOfStudyAssignmentsTable"),
    ):
        total = _total(page, marker)
        if total is not None and total != len(rows):
            if len(rows) < MAX_ROWS:
                raise StageValidationError(
                    f"alma course {unit_id}: {len(rows)} of {total} rows in {marker} (paging?)"
                )
            is_open = True
    return (
        pd.DataFrame(mods, columns=MODULE_COLUMNS[:-1]).assign(open=is_open),
        pd.DataFrame(progs, columns=PROGRAMME_COLUMNS[:-1]).assign(open=is_open),
    )


def split_code(codes: pd.Series) -> pd.DataFrame:
    """`82|410|H|2023-B220` → degree_code 82, subject_code 410, major H, po 2023, module B220."""
    out = codes.str.extract(_CODE)
    out.columns = ["degree_code", "subject_code", "major_code", "po", "module_no"]
    return out


# --- network ------------------------------------------------------------------------------------


def _post(client: httpx.Client, cfg: Alma, page: str, extra: dict[str, str]) -> str:
    action, data = alma.form_fields(page, FORM)
    data |= extra | {"DISABLE_VALIDATION": "true"}
    time.sleep(cfg.course_rate_limit_s)
    return alma._get(client, cfg, "POST", action, files={k: (None, v) for k, v in data.items()})


def courses_to_fetch(sessions: pd.DataFrame) -> pd.DataFrame:
    """One row per course with a room in the reference week (unit_id, period_id)."""
    rooms = sessions[(sessions["room"] != "") & (sessions["unit_id"] != "")]
    return rooms[["unit_id", "period_id"]].drop_duplicates("unit_id").reset_index(drop=True)


def crawl(cfg: Alma, courses: pd.DataFrame, out_dir: Path, limit: int | None = None) -> int:
    """Fetch the modules tab of every course not yet on disk; returns the number fetched."""
    if not cfg.course_detail_path:
        raise StageValidationError("alma: config has no course_detail_path")
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [r for r in courses.itertuples() if not (out_dir / f"{r.unit_id}.html.gz").exists()]
    todo = todo[:limit] if limit else todo
    log.info("alma courses: %d on disk, %d to fetch", len(courses) - len(todo), len(todo))
    fetched = 0
    with httpx.Client(
        base_url=cfg.base_url,
        headers={"User-Agent": cfg.user_agent},
        timeout=cfg.timeout_s,
        follow_redirects=True,
    ) as client:
        for r in todo:
            url = cfg.course_detail_path.format(unit_id=r.unit_id, period_id=r.period_id)
            page = alma._get(client, cfg, "GET", url)
            page = _post(client, cfg, page, {TAB: ""})
            sizes = set(_ROWS_INPUT.findall(page))
            if sizes and sizes != {"300"}:  # new session: set the table size once
                page = _post(client, cfg, page, dict(_ROWS))
            parse_course(page, r.unit_id)  # fail loudly before storing a wrong page
            (out_dir / f"{r.unit_id}.html.gz").write_bytes(gzip.compress(page.encode("utf-8")))
            fetched += 1
            if fetched % 50 == 0:
                log.info("alma courses: %d / %d", fetched, len(todo))
            time.sleep(cfg.course_rate_limit_s)
    return fetched


def load_courses(out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All module and programme rows of the pages on disk."""
    mods, progs = [], []
    for p in sorted(out_dir.glob("*.html.gz")):
        m, g = parse_course(gzip.decompress(p.read_bytes()).decode("utf-8"), p.name.split(".")[0])
        mods.append(m)
        progs.append(g)
    if not mods:
        raise StageValidationError(f"alma: no course pages under {out_dir}; run crawl first")
    return pd.concat(mods, ignore_index=True), pd.concat(progs, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per course batch is enough
    ap = argparse.ArgumentParser(prog="reach_pipeline.alma_courses")
    ap.add_argument("action", choices=["crawl"])
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--limit", type=int, default=None, help="fetch at most N courses")
    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    if cfg.alma is None:
        log.error("config has no alma section")
        return 2
    sem_dir = cfg.data_dir / "raw" / "alma" / cfg.alma.semester_key
    try:
        sessions = alma.sessions_of(sorted(sem_dir.glob("*.html.gz")))
        n = crawl(cfg.alma, courses_to_fetch(sessions), sem_dir / "courses", args.limit)
        log.info("alma courses: fetched %d", n)
    except (ExternalError, StageValidationError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
