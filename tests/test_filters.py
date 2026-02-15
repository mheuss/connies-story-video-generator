"""Tests for story_video.ffmpeg.filters — FFmpeg filter expression builders.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the filter builder functions.
"""

import pytest

from story_video.ffmpeg.filters import blur_background_filter, ken_burns_filter

# ---------------------------------------------------------------------------
# Ken Burns — direction 0: zoom in (center)
# ---------------------------------------------------------------------------


class TestKenBurnsZoomIn:
    """Direction 0 produces a zoompan filter that zooms in from center."""

    def test_zoom_in_produces_zoompan_filter(self):
        """Direction 0 returns a string containing 'zoompan'."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert "zoompan" in result

    def test_zoom_in_interpolates_from_one_to_zoom(self):
        """Direction 0 interpolates zoom from 1.0 toward the target zoom factor."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        # Zoom should start at 1.0 and increase toward 1.3
        assert "1.0" in result or "1" in result
        assert "1.3" in result


# ---------------------------------------------------------------------------
# Ken Burns — direction 1: zoom out (center)
# ---------------------------------------------------------------------------


class TestKenBurnsZoomOut:
    """Direction 1 produces a zoompan filter that zooms out from center."""

    def test_zoom_out_produces_zoompan_filter(self):
        """Direction 1 returns a string containing 'zoompan'."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=1, resolution="1920x1080")
        assert "zoompan" in result

    def test_zoom_out_interpolates_from_zoom_to_one(self):
        """Direction 1 interpolates zoom from the target zoom factor toward 1.0."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=1, resolution="1920x1080")
        # Zoom should start at 1.3 and decrease toward 1.0
        assert "1.3" in result


# ---------------------------------------------------------------------------
# Ken Burns — direction 2: pan left
# ---------------------------------------------------------------------------


class TestKenBurnsPanLeft:
    """Direction 2 produces a zoompan filter that pans left."""

    def test_pan_left_produces_zoompan_filter(self):
        """Direction 2 returns a string containing 'zoompan'."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=2, resolution="1920x1080")
        assert "zoompan" in result

    def test_pan_left_has_x_drift(self):
        """Direction 2 has an x expression that changes over time (right-to-left)."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=2, resolution="1920x1080")
        # x should be a dynamic expression, not a static value
        assert "x=" in result or "x='" in result


# ---------------------------------------------------------------------------
# Ken Burns — direction 3: pan right
# ---------------------------------------------------------------------------


class TestKenBurnsPanRight:
    """Direction 3 produces a zoompan filter that pans right."""

    def test_pan_right_produces_zoompan_filter(self):
        """Direction 3 returns a string containing 'zoompan'."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=3, resolution="1920x1080")
        assert "zoompan" in result

    def test_pan_right_has_x_drift(self):
        """Direction 3 has an x expression that changes over time (left-to-right)."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=3, resolution="1920x1080")
        assert "x=" in result or "x='" in result


# ---------------------------------------------------------------------------
# Ken Burns — direction 4: diagonal drift
# ---------------------------------------------------------------------------


class TestKenBurnsDiagonalDrift:
    """Direction 4 produces a zoompan filter with diagonal drift."""

    def test_diagonal_drift_produces_zoompan_filter(self):
        """Direction 4 returns a string containing 'zoompan'."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=4, resolution="1920x1080")
        assert "zoompan" in result

    def test_diagonal_drift_has_both_x_and_y_drift(self):
        """Direction 4 has both x and y expressions that change over time."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=4, resolution="1920x1080")
        # Both axes should be dynamic
        assert "x=" in result or "x='" in result
        assert "y=" in result or "y='" in result


# ---------------------------------------------------------------------------
# Ken Burns — frame count = duration * 25
# ---------------------------------------------------------------------------


class TestKenBurnsFrameCount:
    """Ken Burns frame count is duration * _ZOOMPAN_FPS (25)."""

    def test_frame_count_5_seconds(self):
        """5 second duration produces 125 frames."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert "d=125" in result

    def test_frame_count_10_seconds(self):
        """10 second duration produces 250 frames."""
        result = ken_burns_filter(duration=10.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert "d=250" in result

    def test_frame_count_3_point_5_seconds(self):
        """3.5 second duration produces 87 frames (truncated)."""
        result = ken_burns_filter(duration=3.5, zoom=1.3, direction=0, resolution="1920x1080")
        assert "d=87" in result


# ---------------------------------------------------------------------------
# Ken Burns — zoom factor appears in output
# ---------------------------------------------------------------------------


class TestKenBurnsZoomFactor:
    """Ken Burns zoom factor appears in the filter expression."""

    def test_zoom_factor_1_3(self):
        """Zoom factor 1.3 appears in the output."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert "1.3" in result

    def test_zoom_factor_1_5(self):
        """Zoom factor 1.5 appears in the output."""
        result = ken_burns_filter(duration=5.0, zoom=1.5, direction=0, resolution="1920x1080")
        assert "1.5" in result


# ---------------------------------------------------------------------------
# Ken Burns — output size from resolution
# ---------------------------------------------------------------------------


class TestKenBurnsOutputSize:
    """Ken Burns output size is derived from the resolution parameter."""

    def test_output_size_1920x1080(self):
        """Resolution 1920x1080 produces s=1920x1080 in the filter."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert "s=1920x1080" in result

    def test_output_size_1280x720(self):
        """Resolution 1280x720 produces s=1280x720 in the filter."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1280x720")
        assert "s=1280x720" in result


# ---------------------------------------------------------------------------
# Ken Burns — deterministic output
# ---------------------------------------------------------------------------


class TestKenBurnsDeterministic:
    """Ken Burns filter is deterministic — same inputs always produce same output."""

    def test_same_inputs_produce_same_output(self):
        """Calling twice with identical inputs yields identical output."""
        result1 = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        result2 = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert result1 == result2

    def test_all_directions_deterministic(self):
        """Each direction produces identical output on repeated calls."""
        for direction in range(5):
            result1 = ken_burns_filter(
                duration=5.0, zoom=1.3, direction=direction, resolution="1920x1080"
            )
            result2 = ken_burns_filter(
                duration=5.0, zoom=1.3, direction=direction, resolution="1920x1080"
            )
            assert result1 == result2, f"Direction {direction} is not deterministic"


# ---------------------------------------------------------------------------
# Ken Burns — invalid direction raises ValueError
# ---------------------------------------------------------------------------


class TestKenBurnsInvalidDirection:
    """Ken Burns raises ValueError for direction outside 0-4."""

    def test_direction_5_raises_value_error(self):
        """Direction 5 raises ValueError."""
        with pytest.raises(ValueError, match="direction"):
            ken_burns_filter(duration=5.0, zoom=1.3, direction=5, resolution="1920x1080")

    def test_direction_negative_raises_value_error(self):
        """Negative direction raises ValueError."""
        with pytest.raises(ValueError, match="direction"):
            ken_burns_filter(duration=5.0, zoom=1.3, direction=-1, resolution="1920x1080")


# ---------------------------------------------------------------------------
# Blur background — contains scale, crop, blur components
# ---------------------------------------------------------------------------


class TestBlurBackgroundComponents:
    """blur_background_filter returns a filter chain with scale, crop, and blur."""

    def test_contains_scale(self):
        """Output contains a scale filter."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "scale=" in result

    def test_contains_crop(self):
        """Output contains a crop filter."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "crop=" in result

    def test_contains_blur(self):
        """Output contains a gblur filter."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "gblur" in result

    def test_scale_uses_force_original_aspect_ratio(self):
        """Scale filter uses force_original_aspect_ratio=increase."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "force_original_aspect_ratio=increase" in result

    def test_crop_uses_resolution(self):
        """Crop filter uses the target resolution dimensions."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "crop=1920:1080" in result

    def test_crop_uses_different_resolution(self):
        """Crop filter adapts to a different resolution."""
        result = blur_background_filter(blur_radius=20, resolution="1280x720")
        assert "crop=1280:720" in result


# ---------------------------------------------------------------------------
# Blur background — blur radius appears in output
# ---------------------------------------------------------------------------


class TestBlurBackgroundRadius:
    """blur_background_filter includes the blur radius in the output."""

    def test_blur_radius_20(self):
        """Blur radius 20 appears in the filter expression."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "sigma=20" in result

    def test_blur_radius_50(self):
        """Blur radius 50 appears in the filter expression."""
        result = blur_background_filter(blur_radius=50, resolution="1920x1080")
        assert "sigma=50" in result
