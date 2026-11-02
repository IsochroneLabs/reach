"""Smoke test: the pipeline package is installed in the workspace environment."""

import reach_pipeline


def test_package_importable() -> None:
    assert reach_pipeline.__version__
