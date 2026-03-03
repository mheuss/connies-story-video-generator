"""Tests for story_video.web.routes_tts -- TTS scene listing and regeneration."""

from unittest.mock import MagicMock, patch

import pytest

from story_video.config import load_config
from story_video.models import InputMode
from story_video.state import ProjectState


@pytest.fixture()
def project_with_scenes(output_dir):
    """Create a project with scenes, narration text, and audio files."""
    config = load_config(None)
    state = ProjectState.create("tts-project", InputMode.ADAPT, config, output_dir)

    state.add_scene(scene_number=1, title="The Storm", prose="The lighthouse keeper watched.")
    state.add_scene(scene_number=2, title="The Calm", prose="Morning came quietly.")

    # Set narration text on scenes
    state.metadata.scenes[0].narration_text = "The lighthouse keeper watched the horizon."
    state.metadata.scenes[1].narration_text = "Morning came quietly over the sea."
    state.save()

    # Create audio file for scene 1 only (scene 2 has no audio)
    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / "scene_001.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)

    return state


class TestListTTSScenes:
    """GET /api/v1/projects/{id}/tts-scenes returns scene metadata for TTS review."""

    def test_returns_scenes_with_audio_info(self, client, project_with_scenes):
        response = client.get("/api/v1/projects/tts-project/tts-scenes")
        assert response.status_code == 200
        data = response.json()
        assert "scenes" in data
        assert len(data["scenes"]) == 2

        scene1 = data["scenes"][0]
        assert scene1["scene_number"] == 1
        assert scene1["title"] == "The Storm"
        assert scene1["narration_text"] == "The lighthouse keeper watched the horizon."
        assert scene1["audio_file"] == "scene_001.mp3"
        assert scene1["has_audio"] is True

    def test_has_audio_false_when_no_file(self, client, project_with_scenes):
        response = client.get("/api/v1/projects/tts-project/tts-scenes")
        assert response.status_code == 200
        data = response.json()

        scene2 = data["scenes"][1]
        assert scene2["scene_number"] == 2
        assert scene2["has_audio"] is False

    def test_nonexistent_project_returns_404(self, client):
        response = client.get("/api/v1/projects/nonexistent/tts-scenes")
        assert response.status_code == 404

    def test_audio_url_format(self, client, project_with_scenes):
        response = client.get("/api/v1/projects/tts-project/tts-scenes")
        assert response.status_code == 200
        data = response.json()

        scene1 = data["scenes"][0]
        expected_url = "/api/v1/projects/tts-project/artifacts/tts_generation/scene_001.mp3"
        assert scene1["audio_url"] == expected_url


class TestRegenerateTTSScene:
    """POST /api/v1/projects/{id}/tts-scenes/{scene_number}/regenerate."""

    @patch("story_video.web.routes_tts.pipeline_runner")
    @patch("story_video.web.routes_tts._make_tts_provider")
    @patch("story_video.web.routes_tts.generate_audio")
    def test_regenerate_success(
        self,
        mock_generate_audio,
        mock_make_provider,
        mock_pipeline_runner,
        client,
        project_with_scenes,
    ):
        """Regenerate audio for a scene. Expect 200 with updated scene data."""
        mock_pipeline_runner.is_running.return_value = False
        mock_make_provider.return_value = MagicMock()

        # Side effect: write a fake audio file to simulate TTS output
        def write_fake_audio(scene, state, provider, story_header=None):
            audio_dir = state.project_dir / "audio"
            audio_dir.mkdir(exist_ok=True)
            (audio_dir / "scene_001.mp3").write_bytes(b"\xff\xfb\x90\x00fake")

        mock_generate_audio.side_effect = write_fake_audio

        response = client.post("/api/v1/projects/tts-project/tts-scenes/1/regenerate")
        assert response.status_code == 200

        data = response.json()
        assert data["scene_number"] == 1
        assert data["title"] == "The Storm"
        assert data["narration_text"] == "The lighthouse keeper watched the horizon."
        assert data["audio_file"] == "scene_001.mp3"
        assert data["audio_url"] == (
            "/api/v1/projects/tts-project/artifacts/tts_generation/scene_001.mp3"
        )
        assert data["has_audio"] is True

        # Verify generate_audio was called with the right scene
        mock_generate_audio.assert_called_once()
        call_args = mock_generate_audio.call_args
        assert call_args[0][0].scene_number == 1

    @patch("story_video.web.routes_tts.pipeline_runner")
    def test_regenerate_409_when_pipeline_running(
        self, mock_pipeline_runner, client, project_with_scenes
    ):
        """Return 409 Conflict when the pipeline is already running."""
        mock_pipeline_runner.is_running.return_value = True

        response = client.post("/api/v1/projects/tts-project/tts-scenes/1/regenerate")
        assert response.status_code == 409

    @patch("story_video.web.routes_tts.pipeline_runner")
    def test_regenerate_404_for_nonexistent_scene(
        self, mock_pipeline_runner, client, project_with_scenes
    ):
        """Return 404 when the scene number does not exist."""
        mock_pipeline_runner.is_running.return_value = False

        response = client.post("/api/v1/projects/tts-project/tts-scenes/999/regenerate")
        assert response.status_code == 404

    def test_regenerate_404_for_nonexistent_project(self, client):
        """Return 404 when the project does not exist."""
        response = client.post("/api/v1/projects/nonexistent/tts-scenes/1/regenerate")
        assert response.status_code == 404


class TestUpdateNarrationText:
    """PUT /api/v1/projects/{id}/tts-scenes/{scene_number}/narration-text."""

    def test_update_narration_text_success(self, client, project_with_scenes):
        """Update narration text for scene 1. Verify response and persistence."""
        response = client.put(
            "/api/v1/projects/tts-project/tts-scenes/1/narration-text",
            json={"narration_text": "The lighthouse keeper watched the storm approach."},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["scene_number"] == 1
        assert data["title"] == "The Storm"
        assert data["narration_text"] == "The lighthouse keeper watched the storm approach."
        assert data["audio_file"] == "scene_001.mp3"
        assert data["audio_url"] == (
            "/api/v1/projects/tts-project/artifacts/tts_generation/scene_001.mp3"
        )
        assert data["has_audio"] is True

        # Reload state from disk and verify text was persisted
        reloaded = ProjectState.load(project_with_scenes.project_dir)
        assert (
            reloaded.metadata.scenes[0].narration_text
            == "The lighthouse keeper watched the storm approach."
        )

    def test_update_404_for_nonexistent_scene(self, client, project_with_scenes):
        """Return 404 when the scene number does not exist."""
        response = client.put(
            "/api/v1/projects/tts-project/tts-scenes/999/narration-text",
            json={"narration_text": "Some text."},
        )
        assert response.status_code == 404

    def test_update_422_for_blank_text(self, client, project_with_scenes):
        """Return 422 when narration text is empty or whitespace-only."""
        response = client.put(
            "/api/v1/projects/tts-project/tts-scenes/1/narration-text",
            json={"narration_text": "   "},
        )
        assert response.status_code == 422

    def test_update_404_for_nonexistent_project(self, client):
        """Return 404 when the project does not exist."""
        response = client.put(
            "/api/v1/projects/nonexistent/tts-scenes/1/narration-text",
            json={"narration_text": "Some text."},
        )
        assert response.status_code == 404
