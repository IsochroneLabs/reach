"""Shared fixtures: tests never post to a real failure webhook."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_failure_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAILURE_WEBHOOK_URL", raising=False)
