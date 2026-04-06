"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app


@pytest.fixture()
def patch_sleep(monkeypatch):
    """Patch time.sleep to eliminate tenacity retry delays.

    Not autouse — only tests that exercise retry paths should use this.
    Apply via @pytest.mark.usefixtures("patch_sleep") or request it directly.
    """
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
