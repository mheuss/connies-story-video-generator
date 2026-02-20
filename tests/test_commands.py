"""Tests for story_video.ffmpeg.commands — FFmpeg command building and execution.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the command builder/executor functions.
All tests mock subprocess — no actual FFmpeg calls.
"""

import logging
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

    def test_command_shape(self, segment_args, video_config):
        """Command is a string list starting with ffmpeg, with required flags."""
        result = build_segment_command(**segment_args, video_config=video_config)
        assert isinstance(result, list)
        assert result[0] == "ffmpeg"
        assert "-filter_complex" in result
        assert "-y" in result
        assert "-shortest" in result
        assert "-loop" in result
        assert result[result.index("-loop") + 1] == "1"
        assert "-pix_fmt" in result
        assert result[result.index("-pix_fmt") + 1] == "yuv420p"
        assert str(segment_args["output_path"]) in result

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

    def test_maps_audio_from_second_input(self, segment_args, video_config):
        """Audio is mapped from the second input (1:a)."""
        result = build_segment_command(**segment_args, video_config=video_config)
        map_indices = [i for i, v in enumerate(result) if v == "-map"]
        audio_map = result[map_indices[1] + 1]
        assert audio_map == "1:a"

    def test_fps_from_config(self, segment_args):
        """FPS is taken from video_config."""
        config = VideoConfig(fps=30)
        result = build_segment_command(**segment_args, video_config=config)
        r_idx = result.index("-r")
        assert result[r_idx + 1] == "30"


# ---------------------------------------------------------------------------
# TestBuildConcatCommand — building FFmpeg concat commands
# ---------------------------------------------------------------------------


class TestBuildConcatCommand:
    """build_concat_command produces a valid FFmpeg concatenation command."""

    @pytest.mark.parametrize(
        "segment_count,expected_xfade_count",
        [(1, 0), (2, 1), (3, 2)],
        ids=["single", "two", "three"],
    )
    def test_xfade_count_matches_segments(
        self, tmp_path, video_config, segment_count, expected_xfade_count
    ):
        """Segment count determines xfade count in the filter."""
        segments = [tmp_path / f"s{i + 1}.mp4" for i in range(segment_count)]
        durations = [10.0] * segment_count
        output = tmp_path / "final.mp4"
        result = build_concat_command(segments, durations, output, video_config)
        filter_str = result[result.index("-filter_complex") + 1]
        assert filter_str.count("xfade") == expected_xfade_count

    def test_empty_segments_raises(self, video_config):
        """Empty segment list raises ValueError."""
        with pytest.raises(ValueError, match="at least one segment"):
            build_concat_command([], [], Path("/tmp/final.mp4"), video_config)

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
        mock_run.assert_called_once_with(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=600
        )

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

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_timeout_raises_ffmpeg_error(self, mock_run):
        """Timed-out process raises FFmpegError."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=600)
        with pytest.raises(FFmpegError, match="timed out"):
            run_ffmpeg(["ffmpeg", "-i", "input.mp4"])

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_custom_timeout_propagated(self, mock_run):
        """Custom timeout value is passed to subprocess.run."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout="", stderr=""
        )
        run_ffmpeg(["ffmpeg", "-version"], timeout=1200)
        mock_run.assert_called_once_with(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=1200
        )


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

    @patch("story_video.ffmpeg.commands.subprocess.run")
    def test_uses_short_timeout(self, mock_run):
        """probe_duration passes a 30-second timeout to subprocess.run."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="5.0\n", stderr=""
        )
        probe_duration(Path("/tmp/test.mp4"))
        assert mock_run.call_args[1]["timeout"] == 30


# ---------------------------------------------------------------------------
# TestBuildSegmentCommandStillImage — uses still image filter
# ---------------------------------------------------------------------------


class TestBuildSegmentCommandStillImage:
    """build_segment_command uses still image filter (no zoompan)."""

    def test_filtergraph_shape(self):
        """Filtergraph uses still image (no zoompan), with scale, pad, ass, blur, overlay."""
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
        assert "force_original_aspect_ratio=decrease" in filtergraph
        assert "pad=" in filtergraph
        assert "ass=" in filtergraph
        assert "gblur" in filtergraph
        assert "overlay" in filtergraph


# ---------------------------------------------------------------------------
# TestProbeDurationNonNumeric — non-numeric ffprobe output handling
# ---------------------------------------------------------------------------


class TestProbeDurationNonNumeric:
    """probe_duration handles non-numeric ffprobe output."""

    @pytest.mark.parametrize(
        "stdout",
        ["", "N/A\n"],
        ids=["empty", "non_numeric"],
    )
    def test_non_numeric_stdout_raises_ffmpeg_error(self, monkeypatch, stdout):
        """Non-numeric or empty stdout from ffprobe raises FFmpegError."""
        fake_result = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=stdout, stderr=""
        )
        monkeypatch.setattr(
            "story_video.ffmpeg.commands.subprocess.run", lambda *a, **kw: fake_result
        )
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

    def test_very_short_duration_segment(self):
        """Segment shorter than xfade transition duration clamps offset."""
        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [0.5, 5.0]  # 0.5s < typical 1.5s xfade
        config = VideoConfig()
        cmd = build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert "-filter_complex" in cmd
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # Offset should be clamped to 0 when duration < xfade
        assert "offset=0" in filter_str


# ---------------------------------------------------------------------------
# TestBuildConcatCommandXfadeClamp — negative xfade offset guard
# ---------------------------------------------------------------------------


class TestBuildConcatCommandXfadeClamp:
    """build_concat_command clamps negative xfade offsets to zero."""

    def test_clamping_logs_warning(self, caplog):
        """Clamping emits a warning log message."""
        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [0.5, 5.0]
        config = VideoConfig()
        with caplog.at_level(logging.WARNING, logger="story_video.ffmpeg.commands"):
            build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert any("clamped" in record.message for record in caplog.records)

    def test_no_warning_when_offset_positive(self, caplog):
        """No warning when segment duration exceeds transition_duration."""
        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [10.0, 10.0]
        config = VideoConfig()
        with caplog.at_level(logging.WARNING, logger="story_video.ffmpeg.commands"):
            build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert not any("clamped" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# TestBuildConcatCommandFadeOut — fade-out timing math
# ---------------------------------------------------------------------------


class TestBuildConcatCommandFadeOut:
    """build_concat_command calculates correct fade-out start times."""

    def test_single_segment_fade_out_start(self):
        """Single segment: fade_out_start = duration - fade_out_duration."""
        config = VideoConfig()  # fade_out_duration=3.0
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # 10.0 - 3.0 = 7.0
        assert "fade=t=out:st=7.0:d=3.0" in filter_str

    def test_multi_segment_fade_out_accounts_for_transitions(self):
        """Multi-segment: fade-out start accounts for xfade overlap."""
        config = VideoConfig()  # transition_duration=1.5, fade_out_duration=3.0
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4")],
            [10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # total_dur = 10 + 10 - 1*1.5 = 18.5; fade_out_start = 18.5 - 3.0 = 15.5
        assert "fade=t=out:st=15.5:d=3.0" in filter_str


# ---------------------------------------------------------------------------
# TestBuildConcatCommandFadeIn — fade-in timing
# ---------------------------------------------------------------------------


class TestBuildConcatCommandFadeIn:
    """build_concat_command includes correct fade-in filter."""

    def test_multi_segment_fade_in(self):
        """Multi-segment: fade-in starts at 0 with configured duration."""
        config = VideoConfig()
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4")],
            [10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "fade=t=in:st=0:d=2.0" in filter_str

    def test_single_segment_audio_fade_in(self):
        """Single segment: audio fade-in starts at 0."""
        config = VideoConfig()
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "afade=t=in:st=0:d=2.0" in filter_str


# ---------------------------------------------------------------------------
# TestBuildConcatCommandStreamLabels — filtergraph wiring
# ---------------------------------------------------------------------------


class TestBuildConcatCommandStreamLabels:
    """build_concat_command produces correctly chained stream labels."""

    def test_two_segments_label_chain(self):
        """Two-segment filtergraph chains [0:v][1:v] -> [xf0] -> [outv]."""
        config = VideoConfig()
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4")],
            [10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "[0:v][1:v]xfade=" in filter_str
        assert "[xf0]" in filter_str
        assert "[outv]" in filter_str

    def test_three_segments_label_chain(self):
        """Three-segment filtergraph chains through [xf0] and [xf1]."""
        config = VideoConfig()
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4"), Path("/c.mp4")],
            [10.0, 10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # First xfade: [0:v][1:v] -> [xf0]
        assert "[0:v][1:v]xfade=" in filter_str
        assert "[xf0]" in filter_str
        # Second xfade: [xf0][2:v] -> [xf1]
        assert "[xf0][2:v]xfade=" in filter_str
        assert "[xf1]" in filter_str

    def test_audio_labels_chain(self):
        """Audio filtergraph chains acrossfade labels correctly."""
        config = VideoConfig()
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4"), Path("/c.mp4")],
            [10.0, 10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "[0:a][1:a]acrossfade=" in filter_str
        assert "[axf0]" in filter_str
        assert "[axf0][2:a]acrossfade=" in filter_str
        assert "[outa]" in filter_str
