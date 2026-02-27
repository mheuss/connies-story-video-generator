"""Tests for story_video.web.routes_artifacts -- artifact listing and serving."""

import json

import pytest
from fastapi.testclient import TestClient

from story_video.config import load_config
from story_video.models import InputMode
from story_video.state import ProjectState
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


@pytest.fixture()
def project_with_artifacts(output_dir):
    """Create a project with some artifact files on disk."""
    config = load_config(None)
    state = ProjectState.create("test-project", InputMode.ADAPT, config, output_dir)

    # Analysis/outline produce project-level JSON in the project root
    (state.project_dir / "analysis.json").write_text(
        json.dumps({"craft_notes": "dramatic tone"}), encoding="utf-8"
    )
    (state.project_dir / "outline.json").write_text(
        json.dumps({"scenes": [{"title": "Opening"}]}), encoding="utf-8"
    )

    images_dir = state.project_dir / "images"
    images_dir.mkdir(exist_ok=True)
    (images_dir / "scene_001_000.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / "scene_001.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)

    return state


class TestListArtifacts:
    """GET /api/v1/projects/{id}/artifacts/{phase} lists phase artifacts."""

    def test_list_analysis_artifacts(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/analysis")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        filenames = [f["name"] for f in data["files"]]
        assert "analysis.json" in filenames

    def test_list_image_generation_artifacts(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/image_generation")
        assert response.status_code == 200
        data = response.json()
        filenames = [f["name"] for f in data["files"]]
        assert "scene_001_000.png" in filenames

    def test_nonexistent_project_returns_404(self, client):
        response = client.get("/api/v1/projects/nonexistent/artifacts/analysis")
        assert response.status_code == 404

    def test_invalid_phase_returns_422(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/invalid_phase")
        assert response.status_code == 422


class TestGetArtifact:
    """GET /api/v1/projects/{id}/artifacts/{phase}/{filename} serves a file."""

    def test_serve_json_artifact(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/analysis/analysis.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert data["craft_notes"] == "dramatic tone"

    def test_serve_image_artifact(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/image_generation/scene_001_000.png"
        )
        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]

    def test_serve_audio_artifact(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/tts_generation/scene_001.mp3"
        )
        assert response.status_code == 200
        assert "audio" in response.headers["content-type"]

    def test_nonexistent_file_returns_404(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/analysis/nonexistent.json")
        assert response.status_code == 404

    def test_path_traversal_rejected(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/analysis/..%2F..%2Fpyproject.toml"
        )
        assert response.status_code in (400, 404)


class TestUpdateArtifact:
    """PUT /api/v1/projects/{id}/artifacts/{phase}/{filename} updates a file."""

    def test_update_json_artifact(self, client, project_with_artifacts):
        new_content = {"craft_notes": "updated tone", "style": "poetic"}
        response = client.put(
            "/api/v1/projects/test-project/artifacts/analysis/analysis.json",
            json={"content": json.dumps(new_content)},
        )
        assert response.status_code == 200
        fetch = client.get("/api/v1/projects/test-project/artifacts/analysis/analysis.json")
        assert fetch.json()["craft_notes"] == "updated tone"

    def test_update_nonexistent_file_returns_404(self, client, project_with_artifacts):
        response = client.put(
            "/api/v1/projects/test-project/artifacts/analysis/nonexistent.json",
            json={"content": "new content"},
        )
        assert response.status_code == 404

    def test_update_rejects_empty_content(self, client, project_with_artifacts):
        response = client.put(
            "/api/v1/projects/test-project/artifacts/analysis/analysis.json",
            json={"content": "  "},
        )
        assert response.status_code == 422
