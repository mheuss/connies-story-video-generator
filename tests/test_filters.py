"""Tests for story_video.ffmpeg.filters — FFmpeg filter expression builders.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the filter builder functions.
"""

import pytest

from story_video.ffmpeg.filters import (
    _parse_resolution,
    blur_background_filter,
    still_image_filter,
)

# ---------------------------------------------------------------------------
# Still image — scale and pad to fit resolution
# ---------------------------------------------------------------------------


class TestStillImageFilter:
    """still_image_filter scales and pads an image to fit the target resolution."""

    def test_contains_scale(self):
        """Output contains a scale filter."""
        result = still_image_filter(resolution="1920x1080")
        assert "scale=" in result

    def test_contains_pad(self):
        """Output contains a pad filter."""
        result = still_image_filter(resolution="1920x1080")
        assert "pad=" in result

    def test_uses_force_original_aspect_ratio_decrease(self):
        """Scale filter uses force_original_aspect_ratio=decrease (fit within)."""
        result = still_image_filter(resolution="1920x1080")
        assert "force_original_aspect_ratio=decrease" in result

    def test_pad_uses_resolution(self):
        """Pad filter uses the target resolution dimensions."""
        result = still_image_filter(resolution="1920x1080")
        assert "pad=1920:1080" in result

    def test_pad_uses_different_resolution(self):
        """Pad filter adapts to a different resolution."""
        result = still_image_filter(resolution="1280x720")
        assert "pad=1280:720" in result

    def test_centers_image(self):
        """Pad expression centers the image within the frame."""
        result = still_image_filter(resolution="1920x1080")
        assert "(ow-iw)/2" in result
        assert "(oh-ih)/2" in result

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


# ---------------------------------------------------------------------------
# _parse_resolution — WIDTHxHEIGHT parsing and validation
# ---------------------------------------------------------------------------


class TestParseResolution:
    """_parse_resolution parses and validates resolution strings."""

    def test_returns_width_and_height(self):
        """Standard resolution returns (width, height) tuple."""
        assert _parse_resolution("1920x1080") == ("1920", "1080")

    def test_returns_different_resolution(self):
        """Works with non-standard dimensions."""
        assert _parse_resolution("1280x720") == ("1280", "720")

    def test_rejects_missing_x_separator(self):
        """Resolution without 'x' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resolution"):
            _parse_resolution("1920:1080")

    def test_rejects_non_numeric(self):
        """Non-numeric values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid resolution"):
            _parse_resolution("widexhigh")

    def test_rejects_empty_string(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resolution"):
            _parse_resolution("")

    def test_rejects_single_number(self):
        """Single number without x raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resolution"):
            _parse_resolution("1920")
