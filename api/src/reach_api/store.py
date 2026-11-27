"""Loads the in-memory `Model` from `current` and reloads it when `current` moves (arch. §9)."""

from __future__ import annotations

import asyncio
import logging
import time

import pandas as pd

from reach_api import db as q
from reach_api.db import Database
from reach_api.model import Model

log = logging.getLogger(__name__)


class NotPublished(Exception):
    """No run has been published yet (HTTP 503)."""


class ModelStore:
    def __init__(self, database: Database, label_names: dict, refresh_s: float) -> None:
        self.db = database
        self.label_names = label_names
        self.refresh_s = refresh_s
        self._model: Model | None = None
        self._checked = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> Model:
        now = time.monotonic()
        if self._model is not None and now - self._checked < self.refresh_s:
            return self._model
        async with self._lock:
            if self._model is not None and time.monotonic() - self._checked < self.refresh_s:
                return self._model
            run_id = await self.db.run_id()
            self._checked = time.monotonic()
            if run_id is None:
                raise NotPublished("no published run yet")
            if self._model is None or self._model.run_id != run_id:
                self._model = await self._load(run_id)
            return self._model

    async def _load(self, run_id: str) -> Model:
        t0 = time.perf_counter()
        frames = {}
        for name, query in [
            ("cells", q.Q_CELLS),
            ("districts", q.Q_DISTRICTS),
            ("types", q.Q_TYPES),
            ("labels", q.Q_LABELS),
            ("sites", q.Q_SITES),
            ("programmes", q.Q_PROGRAMMES),
            ("destinations", q.Q_DESTINATIONS),
            ("times", q.Q_TIMES),
        ]:
            frames[name] = pd.DataFrame(await self.db.fetch(query))
        model = Model.build(run_id=run_id, label_names=self.label_names, **frames)
        log.info(
            "model of run %s: %d cells, %d terms, %d travel times, %.1f s",
            run_id,
            len(model.cell_ids),
            len(model.terms),
            len(frames["times"]),
            time.perf_counter() - t0,
        )
        return model
