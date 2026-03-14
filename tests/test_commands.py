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
    AudioCueSpec,
    FFmpegError,
    _build_audio_mix_filters,
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
        "image_paths": [tmp_path / "scene.png"],
        "image_timings": [(0.0, 30.0)],
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
    def test_success_calls_subprocess_and_returns_result(self, mock_run):
        """Successful run calls subprocess.run correctly and returns CompletedProcess."""
        expected = subprocess.CompletedProcess(
            args=["ffmpeg", "-version"], returncode=0, stdout="ffmpeg version 6", stderr=""
        )
        mock_run.return_value = expected
        result = run_ffmpeg(["ffmpeg", "-version"])

        mock_run.assert_called_once_with(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=600
        )
        assert result is expected

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
    def test_happy_path(self, mock_run):
        """Calls ffprobe with short timeout, parses stdout as float."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="12.345\n", stderr=""
        )
        result = probe_duration(Path("/tmp/test.mp4"))

        assert result == pytest.approx(12.345)
        assert mock_run.call_args[0][0][0] == "ffprobe"
        assert mock_run.call_args[1]["timeout"] == 30

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

    def test_filtergraph_shape(self):
        """Filtergraph uses still image (no zoompan), with scale, pad, ass, blur, overlay."""
        config = VideoConfig()
        cmd = build_segment_command(
            image_paths=[Path("/tmp/img.png")],
            image_timings=[(0.0, 30.0)],
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
        """Single segment: fade starts no earlier than when narration ends."""
        config = VideoConfig()  # lead_in=2.0, fade_out=3.0, end_hold=2.0
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # effective_hold = max(2.0, 3.0) = 3.0
        # total = 2.0 + 10.0 + 3.0 = 15.0; fade_out_start = 15.0 - 3.0 = 12.0
        # 12.0 = lead_in(2) + duration(10) — fade starts exactly when narration ends
        assert "fade=t=out:st=12.0:d=3.0" in filter_str
        assert "tpad=stop_mode=clone:stop_duration=3.0" in filter_str
        assert "apad=pad_dur=3.0" in filter_str

    def test_multi_segment_fade_out_accounts_for_transitions(self):
        """Multi-segment: fade uses lead_in + audio timeline + effective hold."""
        # Defaults: lead_in=2.0, transition=1.5, audio_transition=0.05,
        # fade_out=3.0, end_hold=2.0
        config = VideoConfig()
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4")],
            [10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # effective_hold = max(2.0, 3.0) = 3.0
        # audio_total = 10 + 10 - 0.05 = 19.95; total = 2.0 + 19.95 + 3.0 = 24.95
        # fade_out_start = 24.95 - 3.0 = 21.95
        assert "fade=t=out:st=21.95:d=3.0" in filter_str
        # Video padded: audio_total - video_total + effective_hold
        #             = 19.95 - 18.5 + 3.0 = 4.45
        assert "tpad=stop_mode=clone:stop_duration=" in filter_str
        assert "apad=pad_dur=3.0" in filter_str

    def test_fade_out_never_overlaps_narration(self):
        """Fade-out must not begin before narration ends, even with short end_hold."""
        config = VideoConfig(fade_out_duration=5.0, end_hold_duration=1.0, lead_in_duration=0.0)
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # effective_hold = max(1.0, 5.0) = 5.0
        # total = 0 + 10.0 + 5.0 = 15.0; fade_out_start = 15.0 - 5.0 = 10.0
        # 10.0 = duration — fade starts exactly when narration ends
        assert "fade=t=out:st=10.0:d=5.0" in filter_str

    def test_end_hold_longer_than_fade_preserves_hold(self):
        """When end_hold > fade_out, the full hold period is used."""
        config = VideoConfig(fade_out_duration=1.0, end_hold_duration=5.0, lead_in_duration=0.0)
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # effective_hold = max(5.0, 1.0) = 5.0 (hold is already longer)
        # total = 0 + 10.0 + 5.0 = 15.0; fade_out_start = 15.0 - 1.0 = 14.0
        assert "fade=t=out:st=14.0:d=1.0" in filter_str

    def test_multi_segment_end_hold_longer_than_fade(self):
        """Multi-segment: when end_hold > fade_out, the full hold is preserved."""
        config = VideoConfig(fade_out_duration=1.0, end_hold_duration=5.0, lead_in_duration=0.0)
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4")],
            [10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # effective_hold = max(5.0, 1.0) = 5.0
        # audio_total = 10 + 10 - 0.05 = 19.95
        # total = 0 + 19.95 + 5.0 = 24.95; fade_out_start = 24.95 - 1.0 = 23.95
        assert "fade=t=out:st=23.95:d=1.0" in filter_str


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


# ---------------------------------------------------------------------------
# TestBuildConcatCommandLeadIn — lead-in silence before narration
# ---------------------------------------------------------------------------


class TestBuildConcatCommandLeadIn:
    """build_concat_command delays audio by lead_in_duration."""

    def test_single_segment_has_adelay_and_tpad(self):
        """Single segment: audio delayed, video padded at start."""
        config = VideoConfig(lead_in_duration=2.0)
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "adelay=2000|2000" in filter_str
        assert "tpad=start_mode=clone:start_duration=2.0" in filter_str

    def test_multi_segment_has_adelay_and_tpad(self):
        """Multi-segment: audio delayed, video padded at start."""
        config = VideoConfig(lead_in_duration=2.0)
        cmd = build_concat_command(
            [Path("/a.mp4"), Path("/b.mp4")],
            [10.0, 10.0],
            Path("/out.mp4"),
            config,
        )
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "adelay=2000|2000" in filter_str
        assert "tpad=start_mode=clone:start_duration=2.0" in filter_str

    def test_lead_in_shifts_fade_out_start(self):
        """Lead-in adds to total duration, pushing fade-out later."""
        config = VideoConfig(lead_in_duration=2.0)
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        # effective_hold = max(2.0, 3.0) = 3.0
        # total = 2.0 + 10.0 + 3.0 = 15.0; fade_out_start = 15.0 - 3.0 = 12.0
        assert "fade=t=out:st=12.0:d=3.0" in filter_str

    def test_zero_lead_in_omits_filters(self):
        """Zero lead_in_duration produces no adelay or start tpad."""
        config = VideoConfig(lead_in_duration=0.0)
        cmd = build_concat_command([Path("/a.mp4")], [10.0], Path("/out.mp4"), config)
        filter_str = cmd[cmd.index("-filter_complex") + 1]
        assert "adelay" not in filter_str
        assert "start_mode=clone" not in filter_str


# ---------------------------------------------------------------------------
# TestBuildMultiImageSegmentCommand — multiple images with crossfade
# ---------------------------------------------------------------------------


class TestBuildMultiImageSegmentCommand:
    """build_segment_command handles multiple images with crossfade transitions."""

    def test_two_images_produces_xfade(self, video_config):
        """Two images produce an xfade transition in the filter graph."""
        cmd = build_segment_command(
            image_paths=[Path("/img/000.png"), Path("/img/001.png")],
            image_timings=[(0.0, 15.0), (15.0, 30.0)],
            audio_path=Path("/audio/scene.mp3"),
            ass_path=Path("/captions/scene.ass"),
            output_path=Path("/segments/scene.mp4"),
            video_config=video_config,
        )
        filter_arg = cmd[cmd.index("-filter_complex") + 1]
        assert "xfade" in filter_arg
        # Both images should be inputs
        assert str(Path("/img/000.png")) in " ".join(cmd)
        assert str(Path("/img/001.png")) in " ".join(cmd)

    def test_three_images_produces_two_xfades(self, video_config):
        """Three images produce two xfade transitions."""
        cmd = build_segment_command(
            image_paths=[Path("/img/0.png"), Path("/img/1.png"), Path("/img/2.png")],
            image_timings=[(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)],
            audio_path=Path("/audio/scene.mp3"),
            ass_path=Path("/captions/scene.ass"),
            output_path=Path("/segments/scene.mp4"),
            video_config=video_config,
        )
        filter_arg = cmd[cmd.index("-filter_complex") + 1]
        assert filter_arg.count("xfade") == 2

    def test_multi_image_has_subtitle_filter(self, video_config):
        """Multi-image filter graph includes subtitle burn-in."""
        cmd = build_segment_command(
            image_paths=[Path("/img/0.png"), Path("/img/1.png")],
            image_timings=[(0.0, 15.0), (15.0, 30.0)],
            audio_path=Path("/audio/scene.mp3"),
            ass_path=Path("/captions/scene.ass"),
            output_path=Path("/segments/scene.mp4"),
            video_config=video_config,
        )
        filter_arg = cmd[cmd.index("-filter_complex") + 1]
        assert "subtitles" in filter_arg or "ass" in filter_arg.lower()

    def test_multi_image_maps_audio_from_last_input(self, video_config):
        """Audio input is mapped from the last FFmpeg input index."""
        cmd = build_segment_command(
            image_paths=[Path("/img/0.png"), Path("/img/1.png")],
            image_timings=[(0.0, 15.0), (15.0, 30.0)],
            audio_path=Path("/audio/scene.mp3"),
            ass_path=Path("/captions/scene.ass"),
            output_path=Path("/segments/scene.mp4"),
            video_config=video_config,
        )
        # Audio is the 3rd input (index 2) for 2 images
        audio_maps = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-map" and i + 1 < len(cmd)]
        assert "2:a" in audio_maps

    def test_single_image_no_xfade(self, video_config):
        """Single image in list produces same simple filter graph as before."""
        cmd = build_segment_command(
            image_paths=[Path("/img/scene.png")],
            image_timings=[(0.0, 30.0)],
            audio_path=Path("/audio/scene.mp3"),
            ass_path=Path("/captions/scene.ass"),
            output_path=Path("/segments/scene.mp4"),
            video_config=video_config,
        )
        filter_arg = cmd[cmd.index("-filter_complex") + 1]
        assert "xfade" not in filter_arg

    def test_empty_image_paths_raises(self, video_config):
        """Empty image_paths raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            build_segment_command(
                image_paths=[],
                image_timings=[],
                audio_path=Path("/audio/scene.mp3"),
                ass_path=Path("/captions/scene.ass"),
                output_path=Path("/segments/scene.mp4"),
                video_config=video_config,
            )

    def test_mismatched_lengths_raises(self, video_config):
        """Mismatched image_paths and image_timings raises ValueError."""
        with pytest.raises(ValueError, match="same length"):
            build_segment_command(
                image_paths=[Path("/img/0.png"), Path("/img/1.png")],
                image_timings=[(0.0, 15.0)],
                audio_path=Path("/audio/scene.mp3"),
                ass_path=Path("/captions/scene.ass"),
                output_path=Path("/segments/scene.mp4"),
                video_config=video_config,
            )


class TestBuildMultiImageNegativeDuration:
    """_build_multi_image_command warns when image duration is negative."""

    def test_multi_image_logs_warning_for_negative_duration(self, tmp_path, caplog):
        """_build_multi_image_command logs a warning when image duration is negative."""
        import logging

        from story_video.ffmpeg.commands import _build_multi_image_command
        from story_video.models import VideoConfig

        video_config = VideoConfig()
        img = tmp_path / "img.png"
        img.touch()
        audio = tmp_path / "audio.mp3"
        audio.touch()
        output = tmp_path / "out.mp4"

        with caplog.at_level(logging.WARNING, logger="story_video.ffmpeg.commands"):
            _build_multi_image_command(
                image_paths=[img, img],
                image_timings=[(0.0, 5.0), (5.0, 3.0)],  # second image has negative duration
                audio_path=audio,
                output_path=output,
                video_config=video_config,
                bg_filter="scale=1920:1080",
                fg_filter="scale=1920:1080",
                sub_filter="",
            )

        assert "Image 1 duration is negative" in caplog.text


# ---------------------------------------------------------------------------
# TestAudioCueSpec — frozen dataclass for FFmpeg music mixing parameters
# ---------------------------------------------------------------------------


class TestAudioCueSpec:
    """AudioCueSpec bundles FFmpeg music mixing parameters."""

    def test_construction(self):
        spec = AudioCueSpec(
            file_path=Path("/sounds/rain.mp3"),
            start_time=2.5,
            volume=0.3,
            loop=True,
            fade_in=1.0,
            fade_out=1.0,
            scene_duration=30.0,
        )
        assert spec.file_path == Path("/sounds/rain.mp3")
        assert spec.start_time == 2.5
        assert spec.volume == 0.3
        assert spec.loop is True
        assert spec.fade_in == 1.0
        assert spec.fade_out == 1.0
        assert spec.scene_duration == 30.0


# ---------------------------------------------------------------------------
# TestBuildAudioMixFilters — filter chain for music/SFX mixing
# ---------------------------------------------------------------------------


class TestBuildAudioMixFilters:
    """_build_audio_mix_filters creates filter chains for music mixing."""

    def test_single_cue_no_loop(self):
        """One-shot sound effect at 2.5s, volume 0.6."""

        cues = [
            AudioCueSpec(
                file_path=Path("thunder.mp3"),
                start_time=2.5,
                volume=0.6,
                loop=False,
                fade_in=0.0,
                fade_out=0.0,
                scene_duration=30.0,
            )
        ]
        filters, output_label = _build_audio_mix_filters(
            cues, narration_label="[1:a]", first_cue_index=2
        )
        combined = ";".join(filters)
        assert "adelay=2500|2500" in combined
        assert "volume=0.6" in combined
        assert "amix=inputs=2" in combined
        assert "duration=first" in combined
        assert "aloop" not in combined
        assert output_label == "[amix]"

    def test_looping_ambient_track(self):
        """Ambient track that loops from 0s with fade in/out."""

        cues = [
            AudioCueSpec(
                file_path=Path("rain.mp3"),
                start_time=0.0,
                volume=0.2,
                loop=True,
                fade_in=2.0,
                fade_out=2.0,
                scene_duration=30.0,
            )
        ]
        filters, _ = _build_audio_mix_filters(cues, narration_label="[1:a]", first_cue_index=2)
        combined = ";".join(filters)
        assert "aloop" in combined
        assert "atrim" in combined
        assert "afade=t=in" in combined
        assert "afade=t=out" in combined
        assert "volume=0.2" in combined

    def test_multiple_cues(self):
        """Two cues produce amix=inputs=3."""

        cues = [
            AudioCueSpec(
                file_path=Path("rain.mp3"),
                start_time=0.0,
                volume=0.2,
                loop=False,
                fade_in=0.0,
                fade_out=0.0,
                scene_duration=30.0,
            ),
            AudioCueSpec(
                file_path=Path("thunder.mp3"),
                start_time=5.0,
                volume=0.6,
                loop=False,
                fade_in=0.0,
                fade_out=0.0,
                scene_duration=30.0,
            ),
        ]
        filters, _ = _build_audio_mix_filters(cues, narration_label="[1:a]", first_cue_index=2)
        combined = ";".join(filters)
        assert "amix=inputs=3" in combined

    def test_empty_cues_returns_narration_label(self):
        """No cues: returns narration label unchanged."""

        filters, output_label = _build_audio_mix_filters(
            [], narration_label="[1:a]", first_cue_index=2
        )
        assert filters == []
        assert output_label == "[1:a]"

    def test_no_adelay_when_start_time_zero(self):
        """Don't add adelay filter when start_time is 0."""

        cues = [
            AudioCueSpec(
                file_path=Path("rain.mp3"),
                start_time=0.0,
                volume=0.3,
                loop=False,
                fade_in=0.0,
                fade_out=0.0,
                scene_duration=30.0,
            )
        ]
        filters, _ = _build_audio_mix_filters(cues, narration_label="[1:a]", first_cue_index=2)
        combined = ";".join(filters)
        assert "adelay" not in combined

    def test_fade_out_start_time_calculated_correctly(self):
        """Fade-out start time = (scene_duration - start_time) - fade_out duration."""

        cues = [
            AudioCueSpec(
                file_path=Path("music.mp3"),
                start_time=5.0,
                volume=0.3,
                loop=False,
                fade_in=0.0,
                fade_out=3.0,
                scene_duration=30.0,
            )
        ]
        filters, _ = _build_audio_mix_filters(cues, narration_label="[1:a]", first_cue_index=2)
        combined = ";".join(filters)
        # remaining = 30.0 - 5.0 = 25.0; fade_out_start = 25.0 - 3.0 = 22.0
        assert "afade=t=out:st=22.0:d=3.0" in combined

    def test_fade_out_start_clamped_when_exceeds_remaining(self):
        """fade_out_start is clamped to 0.0 when fade_out > remaining duration."""

        cues = [
            AudioCueSpec(
                file_path=Path("/music.mp3"),
                start_time=8.0,
                scene_duration=10.0,
                volume=0.3,
                loop=False,
                fade_in=0.0,
                fade_out=5.0,  # remaining=2.0, fade_out=5.0 -> clamped
            )
        ]
        filters, _ = _build_audio_mix_filters(cues, narration_label="[0:a]", first_cue_index=1)
        # The fade filter should use st=0.0 (clamped from -3.0)
        fade_filter = [f for f in filters if "afade=t=out" in f][0]
        assert "st=0.0" in fade_filter

    def test_input_indices_correct(self):
        """Each cue uses the correct FFmpeg input index."""

        cues = [
            AudioCueSpec(
                file_path=Path("a.mp3"),
                start_time=0.0,
                volume=0.3,
                loop=False,
                fade_in=0.0,
                fade_out=0.0,
                scene_duration=30.0,
            ),
            AudioCueSpec(
                file_path=Path("b.mp3"),
                start_time=1.0,
                volume=0.4,
                loop=False,
                fade_in=0.0,
                fade_out=0.0,
                scene_duration=30.0,
            ),
        ]
        filters, _ = _build_audio_mix_filters(cues, narration_label="[1:a]", first_cue_index=3)
        combined = ";".join(filters)
        assert "[3:a]" in combined  # first cue
        assert "[4:a]" in combined  # second cue


# ---------------------------------------------------------------------------
# TestBuildSegmentCommandWithAudioCues — audio cues wired into segment command
# ---------------------------------------------------------------------------


class TestBuildSegmentCommandWithAudioCues:
    """build_segment_command with audio_cues adds music inputs and amix."""

    def test_no_cues_unchanged(self, segment_args, video_config):
        """Without audio_cues, command is identical to before."""
        cmd_without = build_segment_command(**segment_args, video_config=video_config)
        cmd_with = build_segment_command(**segment_args, video_config=video_config, audio_cues=None)
        assert cmd_without == cmd_with

    def test_single_cue_adds_input_and_amix(self, segment_args, video_config, tmp_path):
        """One audio cue adds an extra input and amix filter."""
        cue = AudioCueSpec(
            file_path=tmp_path / "rain.mp3",
            start_time=0.0,
            volume=0.3,
            loop=False,
            fade_in=0.0,
            fade_out=0.0,
            scene_duration=30.0,
        )
        cmd = build_segment_command(**segment_args, video_config=video_config, audio_cues=[cue])
        cmd_str = " ".join(cmd)
        assert str(tmp_path / "rain.mp3") in cmd_str
        assert "amix" in cmd_str

    def test_audio_cue_maps_mixed_audio(self, segment_args, video_config, tmp_path):
        """With audio cues, -map uses [amix] instead of raw narration input."""
        cue = AudioCueSpec(
            file_path=tmp_path / "rain.mp3",
            start_time=0.0,
            volume=0.3,
            loop=False,
            fade_in=0.0,
            fade_out=0.0,
            scene_duration=30.0,
        )
        cmd = build_segment_command(**segment_args, video_config=video_config, audio_cues=[cue])
        # Should map [amix] for audio, not the raw audio input
        assert "[amix]" in cmd

    def test_multi_image_single_cue_adds_input_and_amix(self, video_config, tmp_path):
        """Multi-image: one audio cue adds an extra input and amix filter."""
        cue = AudioCueSpec(
            file_path=tmp_path / "rain.mp3",
            start_time=0.0,
            volume=0.3,
            loop=False,
            fade_in=0.0,
            fade_out=0.0,
            scene_duration=30.0,
        )
        cmd = build_segment_command(
            image_paths=[tmp_path / "a.png", tmp_path / "b.png"],
            image_timings=[(0.0, 15.0), (15.0, 30.0)],
            audio_path=tmp_path / "scene.mp3",
            ass_path=tmp_path / "scene.ass",
            output_path=tmp_path / "segment.mp4",
            video_config=video_config,
            audio_cues=[cue],
        )
        cmd_str = " ".join(cmd)
        assert str(tmp_path / "rain.mp3") in cmd_str
        assert "amix" in cmd_str
        assert "[amix]" in cmd
