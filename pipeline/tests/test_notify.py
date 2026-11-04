"""Failure webhook: no-op without URL, JSON post with URL, never raises."""

from __future__ import annotations

import json

import httpx
import respx

from reach_pipeline import notify

URL = "https://chat.example.org/hooks/abc"


def test_no_url_is_a_noop() -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post(URL)
        assert notify.failure("boom") is False
        assert notify.failure("boom", url="  ") is False
    assert not route.called


def test_posts_text() -> None:
    with respx.mock() as router:
        route = router.post(URL).mock(return_value=httpx.Response(200))
        assert notify.failure("run failed", url=URL) is True
    assert json.loads(route.calls.last.request.content) == {"text": "run failed"}


def test_failure_is_logged_not_raised() -> None:
    with respx.mock() as router:
        route = router.post(URL).mock(return_value=httpx.Response(500))
        assert notify.failure("run failed", url=URL) is False
    assert route.call_count == notify.ATTEMPTS
