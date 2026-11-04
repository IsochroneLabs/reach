"""Failure notification to the team chat (arch. §11 "Monitoring", O10/O14).

POSTs `{"text": ...}` to `FAILURE_WEBHOOK_URL` (Slack/Mattermost-style incoming webhook); empty
or unset = no-op. Never raises: a failing webhook must not hide the pipeline error.
"""

from __future__ import annotations

import logging
import os

import httpx

WEBHOOK_ENV = "FAILURE_WEBHOOK_URL"
TIMEOUT_S = 10.0
ATTEMPTS = 2

log = logging.getLogger(__name__)


def failure(text: str, url: str | None = None) -> bool:
    """Send `text` to the webhook; returns True if it was delivered."""
    url = (url if url is not None else os.environ.get(WEBHOOK_ENV, "")).strip()
    if not url:
        return False
    for attempt in range(1, ATTEMPTS + 1):
        try:
            httpx.post(url, json={"text": text}, timeout=TIMEOUT_S).raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("failure webhook attempt %d/%d failed: %s", attempt, ATTEMPTS, exc)
    return False
