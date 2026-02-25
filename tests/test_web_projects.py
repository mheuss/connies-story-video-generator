"""Tests for story_video.web.routes_projects — project CRUD endpoints."""

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


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
