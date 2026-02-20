"""Tests for story_video.ffmpeg.filters — FFmpeg filter expression builders.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the filter builder functions.
"""

import pytest

from story_video.ffmpeg.filters import (
    blur_background_filter,
    parse_resolution,
    still_image_filter,
)

# ---------------------------------------------------------------------------
# Still image — scale and pad to fit resolution
# ---------------------------------------------------------------------------


class TestStillImageFilter:
    """still_image_filter scales and pads an image to fit the target resolution."""

    def test_filter_shape(self):
        """Output contains scale, pad, and centering for target resolution."""
        result = still_image_filter(resolution="1920x1080")
        assert "scale=" in result
        assert "pad=1920:1080" in result
        assert "force_original_aspect_ratio=decrease" in result
        assert "(ow-iw)/2" in result
        assert "(oh-ih)/2" in result

    def test_adapts_to_resolution(self):
        """Pad filter adapts to a different resolution."""
        result = still_image_filter(resolution="1280x720")
        assert "pad=1280:720" in result

    def test_deterministic(self):
        """Same inputs always produce the same output."""
        result1 = still_image_filter(resolution="1920x1080")
        result2 = still_image_filter(resolution="1920x1080")
        assert result1 == result2


# ---------------------------------------------------------------------------
# Blur background — contains scale, crop, blur components
# ---------------------------------------------------------------------------


class TestBlurBackgroundComponents:
    """blur_background_filter returns a filter chain with scale, crop, and blur."""

    def test_filter_shape(self):
        """Output contains scale (with aspect ratio), crop, and blur components."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "scale=" in result
        assert "crop=1920:1080" in result
        assert "gblur" in result
        assert "force_original_aspect_ratio=increase" in result

    def test_crop_uses_different_resolution(self):
        """Crop filter adapts to a different resolution."""
        result = blur_background_filter(blur_radius=20, resolution="1280x720")
        assert "crop=1280:720" in result


# ---------------------------------------------------------------------------
# Blur background — blur radius appears in output
# ---------------------------------------------------------------------------


class TestBlurBackgroundRadius:
    """blur_background_filter includes the blur radius in the output."""

    def test_blur_radius_in_output(self):
        """Blur radius value appears in the filter expression."""
        result = blur_background_filter(blur_radius=20, resolution="1920x1080")
        assert "sigma=20" in result

    def test_negative_blur_radius_raises(self):
        """Negative blur radius raises ValueError."""
        with pytest.raises(ValueError, match="blur_radius must be >= 0"):
            blur_background_filter(blur_radius=-5, resolution="1920x1080")

    def test_zero_blur_radius_allowed(self):
        """Zero blur radius is valid (no blur)."""
        result = blur_background_filter(blur_radius=0, resolution="1920x1080")
        assert "sigma=0" in result


# ---------------------------------------------------------------------------
# parse_resolution — WIDTHxHEIGHT parsing and validation
# ---------------------------------------------------------------------------


class TestParseResolution:
    """parse_resolution parses and validates resolution strings."""

    def test_returns_width_and_height(self):
        """Standard resolution returns (width, height) tuple."""
        assert parse_resolution("1920x1080") == ("1920", "1080")

    @pytest.mark.parametrize(
        "invalid_input",
        ["1920:1080", "widexhigh", "", "1920"],
        ids=["colon_separator", "non_numeric", "empty_string", "single_number"],
    )
    def test_rejects_invalid_resolution(self, invalid_input):
        """Invalid resolution strings are rejected."""
        with pytest.raises(ValueError, match="Invalid resolution"):
            parse_resolution(invalid_input)
