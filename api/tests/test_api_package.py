"""Smoke test: the API package is installed in the workspace environment."""

import reach_api


def test_package_importable() -> None:
    assert reach_api.__version__
