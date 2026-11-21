"""Fixtures of the API tests: a fake database, deps from the repo config, no DNS.

`fixtures/valhalla/marktplatz_route.json` holds real Valhalla 3.9.1 answers recorded once on the
Tübingen tiles (archive): a walking route from the Marktplatz cell and the error for a location
without nearby edges.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from reach_api.deps import Deps
from reach_api.main import create_app
from reach_api.settings import load_config
from reach_api.valhalla import ValhallaClient

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
VALHALLA = "http://valhalla.test"
RUN_ID = "20261105T184022Z"


class FakeDatabase:
    """`Database` with a fixed run id; `calls` lists the methods used."""

    def __init__(self) -> None:
        self.run: str | None = RUN_ID
        self.calls: list[str] = []

    async def run_id(self) -> str | None:
        self.calls.append("run_id")
        return self.run


def make_deps(db: FakeDatabase, build_sha: str = "abc1234") -> Deps:
    config = load_config(REPO / "config" / "config.yaml")
    return Deps(
        config=config,
        db=db,
        valhalla=ValhallaClient(VALHALLA, config.api.valhalla),
        build_sha=build_sha,
    )


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never resolve names: "localhost" is 127.0.0.1, every other host is unknown."""

    def fake(host: str, port: object) -> list:
        if host == "localhost":
            return [(None, None, None, None, ("127.0.0.1", 0))]
        raise OSError(f"{host} does not resolve in tests")

    monkeypatch.setattr("reach_api.ratelimit.getaddrinfo", fake)


@pytest.fixture
def rec() -> dict[str, Any]:
    return json.loads((FIXTURES / "valhalla" / "marktplatz_route.json").read_text())


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def client(db: FakeDatabase) -> Iterator[TestClient]:
    with TestClient(create_app(make_deps(db))) as c:
        yield c
