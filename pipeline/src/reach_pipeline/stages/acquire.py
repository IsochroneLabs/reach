"""acquire: download OSM, GTFS and Zensus into `data/raw/<run_id>/`, with provenance.

A source is downloaded only if it changed since the previous run (Geofabrik `.md5`, HTTP
`ETag`/`Last-Modified`, else the SHA-256 of the new file); unchanged files are hard-linked from
the previous run. Zip members named in the config are unpacked next to the archive.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pandas as pd

from reach_pipeline.config import Download, Source, config_files
from reach_pipeline.context import RunContext, is_run_id
from reach_pipeline.errors import ExternalError, StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    file_inputs,
    is_up_to_date,
    read_manifest,
    write_manifest,
)
from reach_pipeline.metrics import measure

STAGE = "acquire"
PROVENANCE = "data_sources.parquet"
_CHUNK = 1 << 20

log = logging.getLogger(__name__)


@dataclass
class Record:
    """One row of `data_sources.parquet` (data contract `meta.data_sources` plus HTTP metadata)."""

    run_id: str
    source: str
    url: str
    retrieved_at: datetime
    checked_at: datetime
    checksum: str
    licence: str
    path: str
    etag: str | None
    last_modified: str | None
    md5: str | None
    reused: bool


class _Retryable(Exception):
    pass


def raw_path(raw_dir: Path, source: str, url_or_member: str) -> Path:
    """Where a downloaded file or unpacked member lives: `<raw_dir>/<source>/<file name>`."""
    name = Path(urlparse(url_or_member).path).name if "://" in url_or_member else url_or_member
    return raw_dir / source / name


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.unlink(missing_ok=True)
    os.link(src, dst)


def _with_retries[T](cfg: Download, what: str, fn: Callable[[], T]) -> T:
    for attempt in range(cfg.retries + 1):
        try:
            return fn()
        except (httpx.TransportError, _Retryable) as exc:
            if attempt == cfg.retries:
                raise ExternalError(f"{what}: failed after {attempt + 1} attempts: {exc}") from exc
            wait = cfg.backoff_s * 2**attempt
            log.warning("%s: %s; retry %d in %.0f s", what, exc, attempt + 1, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def _check_status(resp: httpx.Response, what: str) -> None:
    if resp.status_code >= 500 or resp.status_code == 429:
        raise _Retryable(f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise ExternalError(f"{what}: HTTP {resp.status_code} for {resp.url}")


def _fetch_md5(client: httpx.Client, url: str, cfg: Download) -> str:
    def get() -> str:
        resp = client.get(url)
        _check_status(resp, url)
        return resp.text.split()[0].lower()

    return _with_retries(cfg, url, get)


def _stream(
    client: httpx.Client, url: str, dst: Path, headers: dict[str, str], cfg: Download
) -> httpx.Response | None:
    """GET `url` into `dst` (via a `.part` file); None if the server answers 304."""

    def get() -> httpx.Response | None:
        part = dst.with_name(dst.name + ".part")
        with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 304:
                return None
            _check_status(resp, url)
            with part.open("wb") as fh:
                for chunk in resp.iter_bytes(_CHUNK):
                    fh.write(chunk)
        part.replace(dst)
        return resp

    dst.parent.mkdir(parents=True, exist_ok=True)
    return _with_retries(cfg, url, get)


def _digests(path: Path) -> tuple[str, str]:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest()


def download(
    name: str,
    source: Source,
    raw_dir: Path,
    run_id: str,
    previous: Record | None,
    client: httpx.Client,
    cfg: Download,
) -> Record:
    """Fetch one source, or hard-link the previous run's file if it is unchanged."""
    dst = raw_path(raw_dir, name, source.url)
    now = datetime.now(UTC)
    prev_ok = previous is not None and Path(previous.path).exists()

    def reuse(why: str) -> Record:
        assert previous is not None
        _link(Path(previous.path), dst)
        log.info("%s unchanged (%s), linked from the previous run", name, why)
        return Record(
            **{
                **asdict(previous),
                "run_id": run_id,
                "path": str(dst),
                "checked_at": now,
                "reused": True,
            }
        )

    md5 = _fetch_md5(client, source.md5_url, cfg) if source.md5_url else None
    if prev_ok and md5 is not None and md5 == previous.md5:
        return reuse("md5")

    headers = {}
    if prev_ok and md5 is None:
        if previous.etag:
            headers["If-None-Match"] = previous.etag
        if previous.last_modified:
            headers["If-Modified-Since"] = previous.last_modified
    log.info("requesting %s from %s", name, source.url)
    resp = _stream(client, source.url, dst, headers, cfg)
    if resp is None:
        return reuse("HTTP 304")
    sha, file_md5 = _digests(dst)
    if md5 is not None and file_md5 != md5:
        raise ExternalError(f"{name}: md5 of the download {file_md5} != published {md5}")
    if prev_ok and sha == previous.checksum:
        return reuse("same SHA-256")
    return Record(
        run_id=run_id,
        source=name,
        url=source.url,
        retrieved_at=now,
        checked_at=now,
        checksum=sha,
        licence=source.licence,
        path=str(dst),
        etag=resp.headers.get("etag"),
        last_modified=resp.headers.get("last-modified"),
        md5=file_md5,
        reused=False,
    )


def unpack(archive: Path, members: list[str], previous_archive: Path | None) -> list[Path]:
    """Unpack `members` next to `archive`; links them from the previous run if it is the same
    archive (hard link) and its members still exist."""
    out = [archive.parent / m for m in members]
    if previous_archive is not None and previous_archive.exists():
        old = [previous_archive.parent / m for m in members]
        if os.path.samefile(previous_archive, archive) and all(p.exists() for p in old):
            for src, dst in zip(old, out, strict=True):
                _link(src, dst)
            return out
    try:
        with zipfile.ZipFile(archive) as zf:
            missing = sorted(set(members) - set(zf.namelist()))
            if missing:
                raise StageValidationError(f"{archive.name}: missing members {missing}")
            for member, dst in zip(members, out, strict=True):
                with zf.open(member) as src, dst.open("wb") as fh:
                    shutil.copyfileobj(src, fh, _CHUNK)
    except zipfile.BadZipFile as exc:
        raise StageValidationError(f"{archive.name}: not a valid zip archive") from exc
    return out


def previous_records(ctx: RunContext) -> dict[str, Record]:
    """Provenance of the newest earlier run whose acquire finished ok."""
    if not ctx.runs_dir.is_dir():
        return {}
    earlier = sorted(
        (p.name for p in ctx.runs_dir.iterdir() if is_run_id(p.name) and p.name < ctx.run_id),
        reverse=True,
    )
    for run_id in earlier:
        stage_dir = ctx.runs_dir / run_id / STAGE
        manifest = read_manifest(stage_dir)
        if manifest is not None and manifest.status == "ok" and (stage_dir / PROVENANCE).exists():
            rows = pd.read_parquet(stage_dir / PROVENANCE).to_dict("records")
            return {r["source"]: Record(**_clean(r)) for r in rows}
    return {}


def _clean(row: dict) -> dict:
    # Parquet gives pandas Timestamps and NaN/None for empty strings.
    out = {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in row.items()}
    for key in ("retrieved_at", "checked_at"):
        out[key] = pd.Timestamp(out[key]).to_pydatetime()
    return out


def run(ctx: RunContext) -> Manifest:
    """Download all sources of `config.sources` (first stage, no previous manifest)."""
    stage_dir = ctx.stage_dir(STAGE)
    inputs = file_inputs(config_files(ctx.config_path))
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    cfg = ctx.config
    with measure() as m:
        before = previous_records(ctx)
        records: list[Record] = []
        outputs: list[FileOutput] = []
        timeout = httpx.Timeout(cfg.download.timeout_s)
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            for name in type(cfg.sources).model_fields:
                src: Source = getattr(cfg.sources, name)
                prev = before.get(name)
                rec = download(name, src, ctx.raw_dir, ctx.run_id, prev, client, cfg.download)
                records.append(rec)
                outputs.append(FileOutput(path=rec.path))
                if src.members:
                    prev_archive = Path(prev.path) if prev else None
                    for p in unpack(Path(rec.path), src.members, prev_archive):
                        outputs.append(FileOutput(path=str(p)))
        stage_dir.mkdir(parents=True, exist_ok=True)
        prov = stage_dir / PROVENANCE
        pd.DataFrame([asdict(r) for r in records]).to_parquet(prov, index=False)
        outputs.append(FileOutput(path=str(prov), rows=len(records)))
    reused = [r.source for r in records if r.reused]
    message = f"{len(records)} sources, unchanged (linked): {reused or 'none'}"
    log.info(message)
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=outputs,
        message=message,
    )
    write_manifest(manifest, stage_dir)
    return manifest
