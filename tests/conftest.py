"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch):
    """Eliminate retry delays so tests run instantly."""
    monkeypatch.setattr("time.sleep", lambda _: None)
