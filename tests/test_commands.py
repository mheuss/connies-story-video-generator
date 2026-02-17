"""Tests for story_video.ffmpeg.commands — FFmpeg command building and execution.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the command builder/executor functions.
All tests mock subprocess — no actual FFmpeg calls.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from story_video.ffmpeg.commands import (
    FFmpegError,
    build_concat_command,
    build_segment_command,
    probe_duration,
    run_ffmpeg,
)
from story_video.models import VideoConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def video_config():
    """Default VideoConfig for testing."""
    return VideoConfig()


@pytest.fixture()
def segment_args(tmp_path):
    """Common arguments for build_segment_command."""
    return {
        "image_path": tmp_path / "scene.png",
        "audio_path": tmp_path / "scene.mp3",
        "ass_path": tmp_path / "scene.ass",
        "output_path": tmp_path / "segment_01.mp4",
    }


# ---------------------------------------------------------------------------
# TestBuildSegmentCommand — building FFmpeg segment commands
# ---------------------------------------------------------------------------


class TestBuildSegmentCommand:
    """build_segment_command produces a valid FFmpeg command list."""

    def test_returns_list_of_strings(self, segment_args, video_config):
        """Result is a list where every element is a string."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_starts_with_ffmpeg(self, segment_args, video_config):
        """Command starts with 'ffmpeg'."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert result[0] == "ffmpeg"

    def test_contains_filter_complex(self, segment_args, video_config):
        """Command includes -filter_complex flag."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert "-filter_complex" in result

    def test_codec_from_config(self, segment_args):
        """Codec is taken from video_config (e.g. libx265)."""
        config = VideoConfig(codec="libx265")
        result = build_segment_command(**segment_args, video_config=config)
        assert "libx265" in result

    def test_crf_from_config(self, segment_args):
        """CRF is taken from video_config (e.g. 23)."""
        config = VideoConfig(crf=23)
        result = build_segment_command(**segment_args, video_config=config)
        assert "23" in result

    def test_contains_output_path(self, segment_args, video_config):
        """Command ends with the output path."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert str(segment_args["output_path"]) in result

    def test_contains_overwrite_flag(self, segment_args, video_config):
        """Command includes -y flag for overwrite."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert "-y" in result

    def test_contains_pix_fmt(self, segment_args, video_config):
        """Command includes -pix_fmt yuv420p."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert "-pix_fmt" in result
        pix_idx = result.index("-pix_fmt")
        assert result[pix_idx + 1] == "yuv420p"


# ---------------------------------------------------------------------------
# TestBuildConcatCommand — building FFmpeg concat commands
# ---------------------------------------------------------------------------


class TestBuildConcatCommand:
    """build_concat_command produces a valid FFmpeg concatenation command."""

    def test_two_segments_one_xfade(self, tmp_path, video_config):
        """Two segments produce one xfade in the filter."""
        segments = [tmp_path / "s1.mp4", tmp_path / "s2.mp4"]
        durations = [10.0, 10.0]
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, video_config)
        filter_str = result[result.index("-filter_complex") + 1]
        assert filter_str.count("xfade") == 1

    def test_three_segments_two_xfades(self, tmp_path, video_config):
        """Three segments produce two xfades in the filter."""
        segments = [tmp_path / "s1.mp4", tmp_path / "s2.mp4", tmp_path / "s3.mp4"]
        durations = [10.0, 10.0, 10.0]
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, video_config)
        filter_str = result[result.index("-filter_complex") + 1]
        assert filter_str.count("xfade") == 2

    def test_contains_output_path(self, tmp_path, video_config):
        """Command includes the output path."""
        segments = [tmp_path / "s1.mp4", tmp_path / "s2.mp4"]
        durations = [10.0, 10.0]
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, video_config)
        assert str(output) in result

    def test_empty_segments_raises(self, video_config):
        """Empty segment list raises ValueError."""
        with pytest.raises(ValueError, match="at least one segment"):
            build_concat_command([], [], Path("/tmp/final.mp4"), video_config)

    def test_single_segment_no_xfade(self, tmp_path, video_config):
        """Single segment produces no xfade, just fade in/out."""
        segments = [tmp_path / "s1.mp4"]
        durations = [10.0]
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, video_config)
        filter_str = result[result.index("-filter_complex") + 1]
        assert "xfade" not in filter_str
        assert "fade" in filter_str

    def test_acrossfade_uses_audio_transition_duration(self, tmp_path):
        """acrossfade duration uses audio_transition_duration, not transition_duration."""
        config = VideoConfig()  # defaults: transition_duration=1.5, audio_transition_duration=0.05
        segments = [tmp_path / "s1.mp4", tmp_path / "s2.mp4"]
        durations = [10.0, 10.0]
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, config)
        filter_str = result[result.index("-filter_complex") + 1]
        assert "acrossfade=d=0.05" in filter_str
        assert "acrossfade=d=1.5" not in filter_str

    def test_custom_audio_transition_duration_propagates(self, tmp_path):
        """Custom audio_transition_duration value appears in acrossfade filter."""
        config = VideoConfig(audio_transition_duration=0.1)
        segments = [tmp_path / "s1.mp4", tmp_path / "s2.mp4"]
        durations = [10.0, 10.0]
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, config)
        filter_str = result[result.index("-filter_complex") + 1]
        assert "acrossfade=d=0.1" in filter_str


# ---------------------------------------------------------------------------
# TestRunFfmpeg — subprocess execution wrapper
# ---------------------------------------------------------------------------


class TestRunFfmpeg:
    """run_ffmpeg wraps subprocess.run with error handling."""

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_calls_subprocess_run(self, mock_run):
        """run_ffmpeg calls subprocess.run with the provided command."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg", "-version"], returncode=0, stdout="", stderr=""
        )
        run_ffmpeg(["ffmpeg", "-version"])
        mock_run.assert_called_once_with(["ffmpeg", "-version"], capture_output=True, text=True)

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_raises_ffmpeg_error_on_nonzero_exit(self, mock_run):
        """Non-zero exit code raises FFmpegError."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg", "-bad"],
            returncode=1,
            stdout="",
            stderr="Unknown option: -bad",
        )
        with pytest.raises(FFmpegError) as exc_info:
            run_ffmpeg(["ffmpeg", "-bad"])
        assert exc_info.value.returncode == 1

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_ffmpeg_error_contains_details(self, mock_run):
        """FFmpegError contains cmd, returncode, and stderr."""
        cmd = ["ffmpeg", "-bad"]
        mock_run.return_value = subprocess.CompletedProcess(
            args=cmd, returncode=2, stdout="", stderr="Some error"
        )
        with pytest.raises(FFmpegError) as exc_info:
            run_ffmpeg(cmd)
        err = exc_info.value
        assert err.cmd == cmd
        assert err.returncode == 2
        assert err.stderr == "Some error"

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_returns_completed_process_on_success(self, mock_run):
        """Successful run returns the CompletedProcess object."""
        expected = subprocess.CompletedProcess(
            args=["ffmpeg", "-version"], returncode=0, stdout="ffmpeg version 6", stderr=""
        )
        mock_run.return_value = expected
        result = run_ffmpeg(["ffmpeg", "-version"])
        assert result is expected


# ---------------------------------------------------------------------------
# TestProbeDuration — ffprobe duration extraction
# ---------------------------------------------------------------------------


class TestProbeDuration:
    """probe_duration extracts duration from ffprobe output."""

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_returns_float_from_stdout(self, mock_run):
        """Parses ffprobe stdout as a float."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="12.345\n", stderr=""
        )
        result = probe_duration(Path("/tmp/test.mp4"))
        assert result == pytest.approx(12.345)

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_command_contains_ffprobe(self, mock_run):
        """The command passed to subprocess.run starts with 'ffprobe'."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="5.0\n", stderr=""
        )
        probe_duration(Path("/tmp/test.mp4"))
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "ffprobe"

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_raises_ffmpeg_error_on_failure(self, mock_run):
        """Non-zero exit from ffprobe raises FFmpegError."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=1, stdout="", stderr="No such file"
        )
        with pytest.raises(FFmpegError):
            probe_duration(Path("/tmp/nonexistent.mp4"))


# ---------------------------------------------------------------------------
# TestBuildSegmentCommandStillImage — uses still image filter
# ---------------------------------------------------------------------------


class TestBuildSegmentCommandStillImage:
    """build_segment_command uses still image filter (no zoompan)."""

    def test_no_zoompan_in_filtergraph(self):
        """Filtergraph does not contain zoompan."""
        config = VideoConfig()
        cmd = build_segment_command(
            image_path=Path("/tmp/img.png"),
            audio_path=Path("/tmp/audio.mp3"),
            ass_path=Path("/tmp/sub.ass"),
            output_path=Path("/tmp/out.mp4"),
            video_config=config,
        )
        filtergraph = cmd[cmd.index("-filter_complex") + 1]
        assert "zoompan" not in filtergraph

    def test_filtergraph_has_scale_and_pad(self):
        """Filtergraph contains scale and pad for still image."""
        config = VideoConfig()
        cmd = build_segment_command(
            image_path=Path("/tmp/img.png"),
            audio_path=Path("/tmp/audio.mp3"),
            ass_path=Path("/tmp/sub.ass"),
            output_path=Path("/tmp/out.mp4"),
            video_config=config,
        )
        filtergraph = cmd[cmd.index("-filter_complex") + 1]
        assert "force_original_aspect_ratio=decrease" in filtergraph
        assert "pad=" in filtergraph


# ---------------------------------------------------------------------------
# TestProbeDurationNonNumeric — non-numeric ffprobe output handling
# ---------------------------------------------------------------------------


class TestProbeDurationNonNumeric:
    """probe_duration handles non-numeric ffprobe output."""

    def test_empty_stdout_raises_ffmpeg_error(self, monkeypatch):
        """Empty stdout from ffprobe raises FFmpegError."""
        fake_result = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="", stderr=""
        )
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        with pytest.raises(FFmpegError, match="non-numeric duration"):
            probe_duration(Path("/tmp/corrupt.mp4"))

    def test_non_numeric_stdout_raises_ffmpeg_error(self, monkeypatch):
        """Non-numeric stdout like 'N/A' from ffprobe raises FFmpegError."""
        fake_result = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="N/A\n", stderr=""
        )
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        with pytest.raises(FFmpegError, match="non-numeric duration"):
            probe_duration(Path("/tmp/corrupt.mp4"))


# ---------------------------------------------------------------------------
# TestBuildConcatCommandLengthValidation — segment list length mismatch
# ---------------------------------------------------------------------------


class TestBuildConcatCommandLengthValidation:
    """build_concat_command validates segment_paths and segment_durations match."""

    def test_mismatched_lengths_raises_value_error(self):
        """Mismatched segment_paths and segment_durations raises ValueError."""
        with pytest.raises(ValueError, match="segment_paths.*segment_durations"):
            build_concat_command(
                segment_paths=[Path("/tmp/a.mp4"), Path("/tmp/b.mp4")],
                segment_durations=[10.0],
                output_path=Path("/tmp/out.mp4"),
                video_config=VideoConfig(),
            )


# ---------------------------------------------------------------------------
# TestBuildConcatCommandShortDuration — segments shorter than xfade
# ---------------------------------------------------------------------------


class TestBuildConcatCommandShortDuration:
    """build_concat_command handles segments shorter than xfade duration."""

    def test_zero_duration_segment(self):
        """Zero-duration segment in multi-segment concat."""
        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [0.0, 5.0]
        config = VideoConfig()
        cmd = build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert isinstance(cmd, list)

    def test_very_short_duration_segment(self):
        """Segment shorter than xfade transition duration."""
        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [0.5, 5.0]  # 0.5s < typical 1.5s xfade
        config = VideoConfig()
        cmd = build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert isinstance(cmd, list)
