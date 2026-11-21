"""Runtime and peak-memory measurement for pipeline stages."""

from __future__ import annotations

import resource
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


def _maxrss_mb(who: int) -> float:
    # ru_maxrss is bytes on macOS and kilobytes on Linux.
    raw = resource.getrusage(who).ru_maxrss
    return raw / 1024**2 if sys.platform == "darwin" else raw / 1024


def peak_rss_mb() -> float:
    """Peak RSS in MB: maximum of this process and its largest child (not the sum)."""
    return max(_maxrss_mb(resource.RUSAGE_SELF), _maxrss_mb(resource.RUSAGE_CHILDREN))


@dataclass
class Measurement:
    runtime_s: float = 0.0
    peak_rss_mb: float = 0.0


@contextmanager
def measure() -> Iterator[Measurement]:
    """Measure wall time and peak RSS of the enclosed block; values are set on exit."""
    m = Measurement()
    start = time.perf_counter()
    try:
        yield m
    finally:
        m.runtime_s = round(time.perf_counter() - start, 3)
        m.peak_rss_mb = round(peak_rss_mb(), 1)
