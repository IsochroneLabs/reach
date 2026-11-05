"""Small in-process LRU cache (arch. §6.5 rule 10); one per kind of answer. No locking is
needed: the API runs one event loop, and get/put never await."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from typing import Any


class LRUCache:
    """At most `max_entries` values; the least recently used one is dropped first."""

    def __init__(self, max_entries: int) -> None:
        self.max_entries = max_entries
        self._data: OrderedDict[Hashable, Any] = OrderedDict()
        self._pending: dict[Hashable, asyncio.Future] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> Any | None:
        if key not in self._data:
            self.misses += 1
            return None
        self.hits += 1
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: Hashable, value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    async def get_or_compute(
        self, key: Hashable, compute: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, bool]:
        """(value, computed here). Requests arriving while `key` is being computed wait for
        that computation instead of starting their own; they get its error if it fails."""
        value = self.get(key)
        if value is not None:
            return value, False
        pending = self._pending.get(key)
        if pending is not None:
            return await asyncio.shield(pending), False
        future = asyncio.get_running_loop().create_future()
        self._pending[key] = future
        try:
            value = await compute()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            future.exception()  # mark as retrieved when nobody waits
            raise
        finally:
            del self._pending[key]
        self.put(key, value)
        future.set_result(value)
        return value, True

    def __len__(self) -> int:
        return len(self._data)
