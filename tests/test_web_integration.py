"""Integration test -- full create-to-checkpoint flow via web API.

Exercises the end-to-end flow: project creation, pipeline start (mocked),
and SSE progress streaming. Verifies that the route wiring connects
project CRUD, pipeline control, and progress streaming correctly.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app
from story_video.web.progress import ProgressBridge, ProgressEvent


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


class TestCreateToProgressFlow:
    """Full flow: create project -> start pipeline -> receive progress events."""

    def test_create_start_and_receive_checkpoint(self, client):
        # 1. Create project
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A lighthouse keeper story."},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        # 2. Prepare a bridge that simulates progress then a checkpoint.
        #    The SSE stream closes on any terminal event (checkpoint, completed, error).
        #    After a checkpoint the client would call /approve and open a new SSE stream.
        bridge = ProgressBridge()
        bridge.push(
            ProgressEvent(event="phase_started", data={"phase": "analysis", "scene_count": 0})
        )
        bridge.push(ProgressEvent(event="checkpoint", data={"phase": "analysis"}))

        # 3. Start pipeline (mocked -- the real one spawns threads and calls external APIs)
        with patch(
            "story_video.web.pipeline_runner.run_pipeline_in_thread",
            return_value=bridge,
        ):
            start_resp = client.post(f"/api/v1/projects/{project_id}/start")
            assert start_resp.status_code == 202

        # 4. Stream progress -- SSE closes after checkpoint (terminal event)
        with patch("story_video.web.routes_pipeline.get_bridge", return_value=bridge):
            with client.stream("GET", f"/api/v1/projects/{project_id}/progress") as response:
                assert response.status_code == 200
                lines = list(response.iter_lines())

        text = "\n".join(lines)
        assert "phase_started" in text
        assert "checkpoint" in text

    def test_project_status_reflects_pending_state(self, client):
        # Create and verify initial status
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "original", "source_text": "A topic for a story."},
        )
        project_id = create_resp.json()["project_id"]

        status_resp = client.get(f"/api/v1/projects/{project_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "pending"
        assert data["current_phase"] is None
        assert data["scene_count"] == 0

    def test_health_check_always_available(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
