"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch):
    """Eliminate retry delays so tests run instantly."""
    monkeypatch.setattr("time.sleep", lambda _: None)


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)
