"""Tests for story_video.pipeline.video_assembler — video assembly orchestration.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the video assembler module.
FFmpeg calls are mocked — no actual FFmpeg execution.
"""

from unittest.mock import patch

import pytest

from story_video.ffmpeg.commands import FFmpegError
from story_video.models import (
    AppConfig,
    AssetType,
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    InputMode,
    SceneStatus,
    TTSConfig,
)
from story_video.pipeline.video_assembler import assemble_scene, assemble_video
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_caption_json():
    """Return valid caption JSON string."""
    result = CaptionResult(
        segments=[CaptionSegment(text="Test.", start=0.0, end=1.0)],
        words=[CaptionWord(word="Test.", start=0.0, end=1.0)],
        language="en",
        duration=1.0,
    )
    return result.model_dump_json(indent=2)


def _setup_scene_prerequisites(state, scene_number=1):
    """Create all prerequisite files for scene assembly."""
    tts_config = state.metadata.config.tts
    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / f"scene_{scene_number:03d}.{tts_config.output_format}").write_bytes(b"audio")

    images_dir = state.project_dir / "images"
    images_dir.mkdir(exist_ok=True)
    (images_dir / f"scene_{scene_number:03d}.png").write_bytes(b"image")

    captions_dir = state.project_dir / "captions"
    captions_dir.mkdir(exist_ok=True)
    (captions_dir / f"scene_{scene_number:03d}.json").write_text(
        _make_caption_json(), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_state(tmp_path):
    """Project state with one scene that has all asset prerequisites completed."""
    config = AppConfig(tts=TTSConfig(output_format="mp3"))
    state = ProjectState.create("test-video", InputMode.ADAPT, config, tmp_path)
    state.add_scene(scene_number=1, title="Scene One", prose="Test prose.")
    # Complete all prerequisite assets
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.AUDIO, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.IMAGE, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.CAPTIONS, SceneStatus.COMPLETED)
    state.save()
    _setup_scene_prerequisites(state)
    return state


# ---------------------------------------------------------------------------
# TestAssembleSceneHappyPath — happy path with mocked run_ffmpeg
# ---------------------------------------------------------------------------


class TestAssembleSceneHappyPath:
    """assemble_scene() renders a scene segment and updates state."""

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_updates_asset_status_to_completed(self, mock_run, project_state):
        """Scene asset_status.video_segment is COMPLETED after assembly."""
        scene = project_state.metadata.scenes[0]
        assemble_scene(scene, project_state)

        assert scene.asset_status.video_segment == SceneStatus.COMPLETED

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_saves_state_to_disk(self, mock_run, project_state):
        """State is persisted — reload from disk, verify status."""
        scene = project_state.metadata.scenes[0]
        assemble_scene(scene, project_state)

        reloaded = ProjectState.load(project_state.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.video_segment == SceneStatus.COMPLETED

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_calls_run_ffmpeg_once(self, mock_run, project_state):
        """run_ffmpeg is called exactly once for the segment render."""
        scene = project_state.metadata.scenes[0]
        assemble_scene(scene, project_state)

        mock_run.assert_called_once()

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_writes_ass_file(self, mock_run, project_state):
        """ASS subtitle file is written to captions/scene_001.ass."""
        scene = project_state.metadata.scenes[0]
        assemble_scene(scene, project_state)

        ass_path = project_state.project_dir / "captions" / "scene_001.ass"
        assert ass_path.exists()
        content = ass_path.read_text(encoding="utf-8")
        assert "[Script Info]" in content

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_creates_segments_directory(self, mock_run, project_state):
        """segments/ directory is created for the output segment."""
        scene = project_state.metadata.scenes[0]
        assemble_scene(scene, project_state)

        segments_dir = project_state.project_dir / "segments"
        assert segments_dir.is_dir()


# ---------------------------------------------------------------------------
# TestAssembleSceneValidation — prerequisite file checks
# ---------------------------------------------------------------------------


class TestAssembleSceneValidation:
    """assemble_scene() raises FileNotFoundError when prerequisites are missing."""

    def test_raises_when_audio_missing(self, project_state):
        """FileNotFoundError raised when audio file does not exist."""
        audio_path = project_state.project_dir / "audio" / "scene_001.mp3"
        audio_path.unlink()

        scene = project_state.metadata.scenes[0]
        with pytest.raises(FileNotFoundError, match="audio"):
            assemble_scene(scene, project_state)

    def test_raises_when_image_missing(self, project_state):
        """FileNotFoundError raised when image file does not exist."""
        image_path = project_state.project_dir / "images" / "scene_001.png"
        image_path.unlink()

        scene = project_state.metadata.scenes[0]
        with pytest.raises(FileNotFoundError, match="image"):
            assemble_scene(scene, project_state)

    def test_raises_when_caption_json_missing(self, project_state):
        """FileNotFoundError raised when caption JSON does not exist."""
        caption_path = project_state.project_dir / "captions" / "scene_001.json"
        caption_path.unlink()

        scene = project_state.metadata.scenes[0]
        with pytest.raises(FileNotFoundError, match="caption"):
            assemble_scene(scene, project_state)


# ---------------------------------------------------------------------------
# TestAssembleSceneFFmpegError — error propagation
# ---------------------------------------------------------------------------


class TestAssembleSceneFFmpegError:
    """assemble_scene() propagates FFmpegError from run_ffmpeg."""

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_ffmpeg_error_propagates(self, mock_run, project_state):
        """FFmpegError from run_ffmpeg is not swallowed."""
        mock_run.side_effect = FFmpegError(
            cmd=["ffmpeg", "-bad"], returncode=1, stderr="encode failed"
        )

        scene = project_state.metadata.scenes[0]
        with pytest.raises(FFmpegError):
            assemble_scene(scene, project_state)


# ---------------------------------------------------------------------------
# TestAssembleVideoHappyPath — final video assembly with mocked FFmpeg
# ---------------------------------------------------------------------------


class TestAssembleVideoHappyPath:
    """assemble_video() concatenates segments into final.mp4."""

    @patch("story_video.pipeline.video_assembler.probe_duration", return_value=10.0)
    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_returns_path_to_final_mp4(self, mock_run, mock_probe, project_state):
        """assemble_video() returns the path to final.mp4."""
        # Create a fake segment file
        segments_dir = project_state.project_dir / "segments"
        segments_dir.mkdir(exist_ok=True)
        (segments_dir / "scene_001.mp4").write_bytes(b"segment")

        # Mark video_segment as completed
        project_state.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
        project_state.save()

        result = assemble_video(project_state)

        expected = project_state.project_dir / "final.mp4"
        assert result == expected

    @patch("story_video.pipeline.video_assembler.probe_duration", return_value=10.0)
    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_calls_run_ffmpeg_once(self, mock_run, mock_probe, project_state):
        """run_ffmpeg is called exactly once for concatenation."""
        segments_dir = project_state.project_dir / "segments"
        segments_dir.mkdir(exist_ok=True)
        (segments_dir / "scene_001.mp4").write_bytes(b"segment")

        project_state.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
        project_state.save()

        assemble_video(project_state)

        mock_run.assert_called_once()

    @patch("story_video.pipeline.video_assembler.probe_duration", return_value=10.0)
    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_collects_segments_in_scene_order(self, mock_run, mock_probe, tmp_path):
        """Segments are collected in scene_number order (1, 2, 3)."""
        config = AppConfig(tts=TTSConfig(output_format="mp3"))
        state = ProjectState.create("multi-scene", InputMode.ADAPT, config, tmp_path)

        for i in [1, 2, 3]:
            state.add_scene(scene_number=i, title=f"Scene {i}", prose=f"Prose {i}.")
            state.update_scene_asset(i, AssetType.TEXT, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.AUDIO, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.IMAGE, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.CAPTIONS, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)

        state.save()

        # Create fake segment files
        segments_dir = state.project_dir / "segments"
        segments_dir.mkdir(exist_ok=True)
        for i in [1, 2, 3]:
            (segments_dir / f"scene_{i:03d}.mp4").write_bytes(b"segment")

        assemble_video(state)

        # Verify run_ffmpeg was called with a command containing segments in order
        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        idx_1 = cmd_str.index("scene_001.mp4")
        idx_2 = cmd_str.index("scene_002.mp4")
        idx_3 = cmd_str.index("scene_003.mp4")
        assert idx_1 < idx_2 < idx_3

    @patch("story_video.pipeline.video_assembler.probe_duration", return_value=10.0)
    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_skips_incomplete_scenes(self, mock_run, mock_probe, tmp_path):
        """Only scenes with completed video_segment are included."""
        config = AppConfig(tts=TTSConfig(output_format="mp3"))
        state = ProjectState.create("skip-test", InputMode.ADAPT, config, tmp_path)

        for i in [1, 2]:
            state.add_scene(scene_number=i, title=f"Scene {i}", prose=f"Prose {i}.")
            state.update_scene_asset(i, AssetType.TEXT, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.AUDIO, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.IMAGE, SceneStatus.COMPLETED)
            state.update_scene_asset(i, AssetType.CAPTIONS, SceneStatus.COMPLETED)

        # Only scene 1 has completed video_segment
        state.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
        state.save()

        segments_dir = state.project_dir / "segments"
        segments_dir.mkdir(exist_ok=True)
        (segments_dir / "scene_001.mp4").write_bytes(b"segment")

        assemble_video(state)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "scene_001.mp4" in cmd_str
        assert "scene_002.mp4" not in cmd_str


# ---------------------------------------------------------------------------
# TestAssembleVideoSegmentValidation — missing segment file check
# ---------------------------------------------------------------------------


class TestAssembleVideoSegmentValidation:
    """assemble_video() validates segment files exist before probing."""

    def test_raises_when_segment_file_missing(self, project_state):
        """FileNotFoundError when segment is marked complete but file doesn't exist."""
        # Mark video_segment as completed but don't create the file
        project_state.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
        project_state.save()

        with pytest.raises(FileNotFoundError, match="Segment file"):
            assemble_video(project_state)


# ---------------------------------------------------------------------------
# TestAssembleVideoEmptySegments — empty segment list guard
# ---------------------------------------------------------------------------


class TestAssembleVideoEmptySegments:
    """assemble_video raises ValueError when no segments are completed."""

    def test_raises_when_no_segments_completed(self, project_state):
        """All scenes with non-completed video_segment raises ValueError."""
        for scene in project_state.metadata.scenes:
            scene.asset_status.video_segment = SceneStatus.PENDING
        project_state.save()

        with pytest.raises(ValueError, match="[Nn]o completed video segments"):
            assemble_video(project_state)


# ---------------------------------------------------------------------------
# TestAssembleVideoFFmpegError — FFmpegError propagation from concat step
# ---------------------------------------------------------------------------


class TestAssembleVideoFFmpegError:
    """assemble_video() propagates FFmpegError from the concat step."""

    @patch("story_video.pipeline.video_assembler.probe_duration", return_value=10.0)
    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_ffmpeg_error_propagates(self, mock_run, mock_probe, project_state):
        """FFmpegError from concat run_ffmpeg is not swallowed."""
        segments_dir = project_state.project_dir / "segments"
        segments_dir.mkdir(exist_ok=True)
        (segments_dir / "scene_001.mp4").write_bytes(b"segment")

        project_state.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
        project_state.save()

        mock_run.side_effect = FFmpegError(
            cmd=["ffmpeg", "-concat"], returncode=1, stderr="concat failed"
        )

        with pytest.raises(FFmpegError):
            assemble_video(project_state)
