"""Tests for story_video.web.routes_pipeline -- pipeline start/approve endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from story_video.models import PipelinePhase
from story_video.state import ProjectState
from story_video.web.app import create_app


def _make_awaiting_project(client, output_dir):
    """Helper: create a project and advance it to awaiting_review."""
    resp = client.post(
        "/api/v1/projects",
        json={"mode": "adapt", "source_text": "A story."},
    )
    pid = resp.json()["project_id"]
    state = ProjectState.load(output_dir / pid)
    state.start_phase(PipelinePhase.ANALYSIS)
    state.await_review()
    state.save()
    return pid, state


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
        json={"mode": "adapt", "source_text": "A story about a lighthouse."},
    )
    return resp.json()["project_id"]


class TestStartPipeline:
    """POST /api/v1/projects/{id}/start kicks off the pipeline."""

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_start_returns_202(self, mock_run, client, project_id):
        mock_run.return_value = None
        response = client.post(f"/api/v1/projects/{project_id}/start")
        assert response.status_code == 202
        mock_run.assert_called_once()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_start_nonexistent_project_returns_404(self, mock_run, client):
        response = client.post("/api/v1/projects/nonexistent/start")
        assert response.status_code == 404
        mock_run.assert_not_called()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_start_while_running_returns_409(self, mock_run, client, project_id, output_dir):
        state = ProjectState.load(output_dir / project_id)
        state.start_phase(PipelinePhase.ANALYSIS)
        state.save()
        response = client.post(f"/api/v1/projects/{project_id}/start")
        assert response.status_code == 409
        mock_run.assert_not_called()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    @patch("story_video.web.pipeline_runner.is_running", return_value=True)
    def test_start_while_thread_alive_returns_409(
        self, _mock_is_running, mock_run, client, project_id
    ):
        response = client.post(f"/api/v1/projects/{project_id}/start")
        assert response.status_code == 409
        mock_run.assert_not_called()


class TestApprovePipeline:
    """POST /api/v1/projects/{id}/approve resumes after checkpoint."""

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_awaiting_review_returns_202(self, mock_run, client, project_id, output_dir):
        state = ProjectState.load(output_dir / project_id)
        state.start_phase(PipelinePhase.ANALYSIS)
        state.await_review()
        state.save()
        response = client.post(f"/api/v1/projects/{project_id}/approve")
        assert response.status_code == 202
        mock_run.assert_called_once()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_when_not_awaiting_returns_409(self, mock_run, client, project_id):
        response = client.post(f"/api/v1/projects/{project_id}/approve")
        assert response.status_code == 409
        mock_run.assert_not_called()


class TestApproveAutoFlag:
    """POST /approve with auto flag switches project to autonomous mode."""

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_with_auto_sets_autonomous(self, mock_run, client, output_dir):
        mock_run.return_value = None
        pid, _ = _make_awaiting_project(client, output_dir)
        response = client.post(
            f"/api/v1/projects/{pid}/approve",
            json={"auto": True},
        )
        assert response.status_code == 202
        state = ProjectState.load(output_dir / pid)
        assert state.metadata.config.pipeline.autonomous is True

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_without_auto_stays_manual(self, mock_run, client, output_dir):
        mock_run.return_value = None
        pid, _ = _make_awaiting_project(client, output_dir)
        response = client.post(f"/api/v1/projects/{pid}/approve")
        assert response.status_code == 202
        state = ProjectState.load(output_dir / pid)
        assert state.metadata.config.pipeline.autonomous is False

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_with_auto_false_stays_manual(self, mock_run, client, output_dir):
        mock_run.return_value = None
        pid, _ = _make_awaiting_project(client, output_dir)
        response = client.post(
            f"/api/v1/projects/{pid}/approve",
            json={"auto": False},
        )
        assert response.status_code == 202
        state = ProjectState.load(output_dir / pid)
        assert state.metadata.config.pipeline.autonomous is False
