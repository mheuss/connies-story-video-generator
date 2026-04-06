"""Tests for story_video.web.routes_artifacts -- artifact listing and serving."""

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from story_video.config import load_config
from story_video.models import InputMode, SceneImagePrompt
from story_video.state import ProjectState
from story_video.web.routes_artifacts import (
    _export_image_prompts,
    _guard_path_traversal,
    _resolve_artifact_dir,
)


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


class TestExportImagePrompts:
    """_export_image_prompts writes scene prompts as editable JSON files."""

    def test_skips_on_missing_project_state(self, output_dir):
        """Silently returns when project.json doesn't exist."""
        fake_dir = output_dir / "nonexistent"
        fake_dir.mkdir()
        _export_image_prompts(fake_dir)  # Should not raise

    def test_preserves_existing_files(self, client, output_dir):
        """Does not overwrite manually edited prompt files."""
        # Create a project
        resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A story."},
        )
        pid = resp.json()["project_id"]
        project_dir = output_dir / pid

        # Load state, add a scene with image prompts
        state = ProjectState.load(project_dir)
        state.add_scene(scene_number=1, title="Test Scene", prose="Once upon a time.")
        scene = state.metadata.scenes[0]
        scene.image_prompts = [SceneImagePrompt(key="hero", prompt="A hero stands tall")]
        state.save()

        # Create existing file that should not be overwritten
        scenes_dir = project_dir / "scenes"
        scenes_dir.mkdir(exist_ok=True)
        existing = scenes_dir / f"image_prompts_scene_{scene.scene_number:03d}.json"
        existing.write_text("CUSTOM EDIT", encoding="utf-8")

        _export_image_prompts(project_dir)
        assert existing.read_text(encoding="utf-8") == "CUSTOM EDIT"


class TestGuardPathTraversal:
    """_guard_path_traversal validates against both base_dir and _output_dir."""

    def test_allows_valid_filename(self, output_dir):
        """A simple filename within base_dir and _output_dir passes."""
        base = output_dir / "test-project"
        base.mkdir()
        target = base / "analysis.json"
        target.touch()
        with patch("story_video.web.routes_artifacts._output_dir", output_dir):
            result = _guard_path_traversal(base, "analysis.json")
        assert result == target.resolve()

    def test_rejects_traversal_out_of_base_dir(self, output_dir):
        """Path traversal escaping base_dir is rejected."""
        base = output_dir / "test-project" / "scenes"
        base.mkdir(parents=True)
        with patch("story_video.web.routes_artifacts._output_dir", output_dir):
            with pytest.raises(HTTPException) as exc_info:
                _guard_path_traversal(base, "../../pyproject.toml")
            assert exc_info.value.status_code == 400

    def test_rejects_path_outside_output_dir(self, tmp_path):
        """Even if base_dir is outside _output_dir, the safety net catches it."""
        real_output = tmp_path / "output"
        real_output.mkdir()
        rogue_base = tmp_path / "sensitive"
        rogue_base.mkdir()
        (rogue_base / "secrets.json").touch()
        with patch("story_video.web.routes_artifacts._output_dir", real_output):
            with pytest.raises(HTTPException) as exc_info:
                _guard_path_traversal(rogue_base, "secrets.json")
            assert exc_info.value.status_code == 400


class TestResolveArtifactDir:
    """_resolve_artifact_dir raises 500 for valid but unmapped phases."""

    def test_unmapped_phase_returns_500(self, project_with_artifacts):
        """A phase that passes validation but has no _PHASE_DIRS entry raises 500."""
        with (
            patch(
                "story_video.web.routes_projects._output_dir",
                project_with_artifacts.project_dir.parent,
            ),
            patch(
                "story_video.web.routes_artifacts._validate_phase",
                return_value="future_phase",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                _resolve_artifact_dir("test-project", "future_phase")
            assert exc_info.value.status_code == 500
            assert "no artifact directory mapping" in exc_info.value.detail
