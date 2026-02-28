"""Tests for SSE progress endpoint — GET /api/v1/projects/{id}/progress."""

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


@pytest.fixture()
def project_id(client):
    resp = client.post(
        "/api/v1/projects",
        json={"mode": "adapt", "source_text": "A story."},
    )
    return resp.json()["project_id"]


class TestSSEProgressEndpoint:
    """GET /api/v1/projects/{id}/progress streams SSE events."""

    def test_streams_events_from_bridge(self, client, project_id):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started", data={"phase": "analysis"}))
        bridge.push(ProgressEvent(event="completed", data={}))

        with patch(
            "story_video.web.routes_pipeline.get_bridge",
            return_value=bridge,
        ):
            with client.stream("GET", f"/api/v1/projects/{project_id}/progress") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                lines = []
                for line in response.iter_lines():
                    lines.append(line)
                    if "completed" in line:
                        break

        text = "\n".join(lines)
        assert "phase_started" in text
        assert "completed" in text

    def test_404_for_nonexistent_project(self, client):
        response = client.get("/api/v1/projects/nonexistent/progress")
        assert response.status_code == 404

    def test_emits_error_when_thread_dies(self, client, project_id):
        """SSE yields error event when pipeline thread dies without terminal event."""
        bridge = ProgressBridge()
        # Bridge has no events queued and is_done is False.

        with (
            patch(
                "story_video.web.routes_pipeline.get_bridge",
                return_value=bridge,
            ),
            patch("story_video.web.routes_pipeline.pipeline_runner") as mock_runner,
        ):
            mock_runner.is_running.return_value = False
            with client.stream("GET", f"/api/v1/projects/{project_id}/progress") as response:
                lines = list(response.iter_lines())

        text = "\n".join(lines)
        assert "event: error" in text
        assert "Pipeline terminated unexpectedly" in text

    def test_times_out_when_no_bridge(self, client, project_id):
        """SSE yields timeout error when no bridge appears within timeout."""
        with (
            patch(
                "story_video.web.routes_pipeline.get_bridge",
                return_value=None,
            ),
            patch(
                "story_video.web.routes_pipeline._BRIDGE_WAIT_TIMEOUT",
                0.5,
            ),
        ):
            with client.stream("GET", f"/api/v1/projects/{project_id}/progress") as response:
                lines = list(response.iter_lines())

        text = "\n".join(lines)
        assert "event: error" in text
        assert "No pipeline activity (timed out)" in text
