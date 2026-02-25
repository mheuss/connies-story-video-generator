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
    SceneAudioCue,
    SceneImagePrompt,
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


def _make_multi_image_caption_json():
    """Return caption JSON with enough words and duration for two images.

    Creates 14 seconds of captions with 14 words, each 1 second long.
    The second image tag at position=42 maps to word6 (char offset 42),
    giving a 7s/7s split — both above the 5.5s minimum (4.0 + 1.5).
    """
    words = []
    for i in range(14):
        words.append(CaptionWord(word=f"word{i:02d}", start=float(i), end=float(i + 1)))
    text = " ".join(w.word for w in words)
    result = CaptionResult(
        segments=[CaptionSegment(text=text, start=0.0, end=14.0)],
        words=words,
        language="en",
        duration=14.0,
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
    (images_dir / f"scene_{scene_number:03d}_000.png").write_bytes(b"image")

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
    def test_happy_path(self, mock_run, project_state):
        """assemble_scene renders segment, updates state, writes ASS, creates dirs."""
        scene = project_state.metadata.scenes[0]
        assemble_scene(scene, project_state)

        # Status updated
        assert scene.asset_status.video_segment == SceneStatus.COMPLETED

        # State persisted to disk
        reloaded = ProjectState.load(project_state.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.video_segment == SceneStatus.COMPLETED

        # FFmpeg called once
        mock_run.assert_called_once()

        # ASS subtitle file written
        ass_path = project_state.project_dir / "captions" / "scene_001.ass"
        assert ass_path.exists()
        assert "[Script Info]" in ass_path.read_text(encoding="utf-8")

        # Segments directory created
        assert (project_state.project_dir / "segments").is_dir()


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
        image_path = project_state.project_dir / "images" / "scene_001_000.png"
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
    def test_returns_path_and_calls_ffmpeg(self, mock_run, mock_probe, project_state):
        """assemble_video() returns final.mp4 path and calls run_ffmpeg once."""
        segments_dir = project_state.project_dir / "segments"
        segments_dir.mkdir(exist_ok=True)
        (segments_dir / "scene_001.mp4").write_bytes(b"segment")

        project_state.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
        project_state.save()

        result = assemble_video(project_state)

        assert result == project_state.project_dir / "final.mp4"
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


# ---------------------------------------------------------------------------
# TestAssembleSceneMultiImage — multi-image scene assembly
# ---------------------------------------------------------------------------


class TestAssembleSceneMultiImage:
    """assemble_scene handles scenes with multiple images."""

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_multi_image_scene_passes_all_paths(self, mock_run, project_state):
        """Scene with 2 image prompts passes both image paths to FFmpeg."""
        state = project_state
        scene = state.metadata.scenes[0]
        scene.image_prompts = [
            SceneImagePrompt(key="lighthouse", prompt="A lighthouse", position=0),
            SceneImagePrompt(key="harbor", prompt="A harbor", position=42),
        ]
        nn = f"{scene.scene_number:03d}"

        # Write multi-image caption JSON (needs enough duration for two images)
        caption_path = state.project_dir / "captions" / f"scene_{nn}.json"
        caption_path.write_text(_make_multi_image_caption_json(), encoding="utf-8")

        # Create second image file (first is created by _setup_scene_prerequisites)
        (state.project_dir / "images" / f"scene_{nn}_001.png").write_bytes(b"fake")

        assemble_scene(scene, state)

        assert scene.asset_status.video_segment == SceneStatus.COMPLETED
        # Verify FFmpeg was called with multi-image command
        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "scene_001_000.png" in cmd_str
        assert "scene_001_001.png" in cmd_str

    def test_multi_image_missing_second_file_raises(self, project_state):
        """Missing image file for multi-image scene raises FileNotFoundError."""
        state = project_state
        scene = state.metadata.scenes[0]
        scene.image_prompts = [
            SceneImagePrompt(key="a", prompt="A", position=0),
            SceneImagePrompt(key="b", prompt="B", position=50),
        ]
        # Only first image exists (_setup_scene_prerequisites creates _000.png)
        # Second image (_001.png) is missing

        with pytest.raises(FileNotFoundError, match="001.png"):
            assemble_scene(scene, state)

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_single_image_scene_unchanged(self, mock_run, project_state):
        """Scene with no image_prompts still works as single-image scene."""
        state = project_state
        scene = state.metadata.scenes[0]
        # image_prompts defaults to empty list

        assemble_scene(scene, state)

        assert scene.asset_status.video_segment == SceneStatus.COMPLETED
        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "scene_001_000.png" in cmd_str


# ---------------------------------------------------------------------------
# TestAssembleSceneWithAudioCues — audio cue resolution and FFmpeg wiring
# ---------------------------------------------------------------------------


class TestAssembleSceneWithAudioCues:
    """assemble_scene resolves audio cues and passes them to FFmpeg."""

    _STORY_HEADER = (
        "---\n"
        "voices:\n"
        "  narrator: nova\n"
        "audio:\n"
        "  rain:\n"
        "    file: sounds/rain.mp3\n"
        "---\n"
        "Test prose."
    )

    _STORY_HEADER_WITH_VOLUME = (
        "---\n"
        "voices:\n"
        "  narrator: nova\n"
        "audio:\n"
        "  rain:\n"
        "    file: sounds/rain.mp3\n"
        "    volume: 0.2\n"
        "---\n"
        "Test prose."
    )

    def test_missing_audio_file_raises(self, project_state):
        """Missing audio file for an audio cue raises FileNotFoundError."""
        scene = project_state.metadata.scenes[0]
        scene.audio_cues = [SceneAudioCue(key="rain", position=0)]

        # Write source story with audio map pointing to nonexistent file
        source_path = project_state.project_dir / "source_story.txt"
        source_path.write_text(self._STORY_HEADER, encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="rain.mp3"):
            assemble_scene(scene, project_state)

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_audio_cues_produce_amix_in_command(self, mock_run, project_state):
        """Scene with audio cues produces FFmpeg command with amix filter."""
        scene = project_state.metadata.scenes[0]
        scene.audio_cues = [SceneAudioCue(key="rain", position=0)]

        # Write source story with audio map
        source_path = project_state.project_dir / "source_story.txt"
        source_path.write_text(self._STORY_HEADER_WITH_VOLUME, encoding="utf-8")

        # Create the audio file on disk
        sounds_dir = project_state.project_dir / "sounds"
        sounds_dir.mkdir()
        (sounds_dir / "rain.mp3").write_bytes(b"fake audio")

        assemble_scene(scene, project_state)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "amix" in cmd_str
        assert "rain.mp3" in cmd_str

    def test_unknown_cue_key_raises(self, project_state):
        """Audio cue with key absent from the audio map raises KeyError."""
        scene = project_state.metadata.scenes[0]
        scene.audio_cues = [SceneAudioCue(key="nonexistent", position=0)]

        source_path = project_state.project_dir / "source_story.txt"
        source_path.write_text(self._STORY_HEADER, encoding="utf-8")

        with pytest.raises(KeyError, match="nonexistent"):
            assemble_scene(scene, project_state)

    def test_path_traversal_raises(self, project_state):
        """Audio file path that escapes project directory raises ValueError."""
        scene = project_state.metadata.scenes[0]
        scene.audio_cues = [SceneAudioCue(key="evil", position=0)]

        # Write source story with path traversal in audio file
        source_path = project_state.project_dir / "source_story.txt"
        source_path.write_text(
            "---\nvoices:\n  narrator: nova\naudio:\n  evil:\n"
            "    file: ../../../etc/passwd\n---\nTest.",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="escapes project directory"):
            assemble_scene(scene, project_state)

    @patch("story_video.pipeline.video_assembler.run_ffmpeg")
    def test_no_audio_cues_unchanged(self, mock_run, project_state):
        """Scene without audio cues produces same command as before."""
        scene = project_state.metadata.scenes[0]
        # No audio_cues set (empty list by default)

        assemble_scene(scene, project_state)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(str(c) for c in cmd)
        assert "amix" not in cmd_str
