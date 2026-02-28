"""Tests for story_video.web.routes_projects — project CRUD endpoints."""

import pytest
from fastapi import HTTPException

from story_video.state import ProjectState


class TestCreateProject:
    """POST /api/v1/projects creates a new project."""

    def test_create_adapt_project_with_source_text(self, client, output_dir):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "Once upon a time there was a story."},
        )
        assert response.status_code == 201
        data = response.json()
        assert "project_id" in data
        assert data["mode"] == "adapt"
        project_dir = output_dir / data["project_id"]
        assert project_dir.exists()
        assert (project_dir / "project.json").exists()

    def test_create_original_project_with_source_text(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "original", "source_text": "A story about a lighthouse keeper."},
        )
        assert response.status_code == 201
        assert response.json()["mode"] == "original"

    def test_create_inspired_by_project(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "inspired_by", "source_text": "An inspiring tale."},
        )
        assert response.status_code == 201
        assert response.json()["mode"] == "inspired_by"

    def test_rejects_invalid_mode(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "invalid", "source_text": "text"},
        )
        assert response.status_code == 422

    def test_requires_source_text(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt"},
        )
        assert response.status_code == 422

    def test_rejects_oversized_source_text(self, client):
        huge_text = "x" * (10 * 1024 * 1024 + 1)
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": huge_text},
        )
        assert response.status_code == 422

    def test_source_text_written_to_disk(self, client, output_dir):
        source = "The lighthouse keeper climbed the stairs."
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": source},
        )
        project_id = response.json()["project_id"]
        source_path = output_dir / project_id / "source_story.txt"
        assert source_path.exists()
        assert source_path.read_text(encoding="utf-8") == source

    def test_project_creation_cap_returns_409(self, client, output_dir, monkeypatch):
        """Creating too many projects on the same day returns 409."""
        monkeypatch.setattr(
            "story_video.web.routes_projects.generate_project_id",
            lambda mode, output_dir: (_ for _ in ()).throw(
                RuntimeError("Could not generate unique project ID")
            ),
        )
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A story."},
        )
        assert response.status_code == 409


class TestCreateProjectAutonomous:
    """POST /api/v1/projects respects the autonomous flag."""

    def test_create_project_with_autonomous_true(self, client, output_dir):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "Test story.", "autonomous": True},
        )
        assert response.status_code == 201
        project_id = response.json()["project_id"]
        state = ProjectState.load(output_dir / project_id)
        assert state.metadata.config.pipeline.autonomous is True

    def test_create_project_defaults_autonomous_false(self, client, output_dir):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "Test story."},
        )
        assert response.status_code == 201
        project_id = response.json()["project_id"]
        state = ProjectState.load(output_dir / project_id)
        assert state.metadata.config.pipeline.autonomous is False


class TestGetProject:
    """GET /api/v1/projects/{id} returns project status."""

    def test_get_existing_project(self, client):
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A story."},
        )
        project_id = create_resp.json()["project_id"]
        response = client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == project_id
        assert data["mode"] == "adapt"
        assert data["status"] == "pending"
        assert data["current_phase"] is None
        assert "scene_count" in data

    def test_get_nonexistent_project_returns_404(self, client):
        response = client.get("/api/v1/projects/nonexistent")
        assert response.status_code == 404


class TestDeleteProject:
    """DELETE /api/v1/projects/{id} removes the project."""

    def test_delete_existing_project(self, client, output_dir):
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A story."},
        )
        project_id = create_resp.json()["project_id"]
        project_dir = output_dir / project_id
        response = client.delete(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200
        assert not project_dir.exists()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/v1/projects/nonexistent")
        assert response.status_code == 404

    def test_resolve_project_dir_rejects_traversal(self, output_dir):
        """_resolve_project_dir rejects path traversal attempts."""
        from story_video.web.routes_projects import _resolve_project_dir

        with pytest.raises(HTTPException) as exc_info:
            _resolve_project_dir("../../etc")
        assert exc_info.value.status_code == 400
