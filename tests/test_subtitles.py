"""Tests for story_video.ffmpeg.subtitles — ASS subtitle generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the subtitle generation functions.
"""

from pathlib import Path

import pytest

from story_video.ffmpeg.subtitles import (
    _format_ass_time,
    _hex_to_ass_color,
    generate_ass_content,
    subtitle_filter,
)
from story_video.models import (
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    SubtitleConfig,
    VideoConfig,
)

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def _make_caption_result() -> CaptionResult:
    """Caption result with 9 words across 2 segments."""
    return CaptionResult(
        segments=[
            CaptionSegment(text="The storm raged on.", start=0.0, end=2.5),
            CaptionSegment(text="Lightning cracked the sky above.", start=2.6, end=5.0),
        ],
        words=[
            CaptionWord(word="The", start=0.0, end=0.3),
            CaptionWord(word="storm", start=0.4, end=0.8),
            CaptionWord(word="raged", start=0.9, end=1.4),
            CaptionWord(word="on.", start=1.5, end=2.5),
            CaptionWord(word="Lightning", start=2.6, end=3.0),
            CaptionWord(word="cracked", start=3.1, end=3.5),
            CaptionWord(word="the", start=3.6, end=3.8),
            CaptionWord(word="sky", start=3.9, end=4.2),
            CaptionWord(word="above.", start=4.3, end=5.0),
        ],
        language="en",
        duration=5.0,
    )


def _make_empty_caption_result() -> CaptionResult:
    """Caption result with no words and no segments."""
    return CaptionResult(
        segments=[],
        words=[],
        language="en",
        duration=0.0,
    )


def _default_subtitle_config() -> SubtitleConfig:
    """Default SubtitleConfig for tests."""
    return SubtitleConfig()


def _default_video_config() -> VideoConfig:
    """Default VideoConfig for tests."""
    return VideoConfig()


# ---------------------------------------------------------------------------
# ASS header — [Script Info] section
# ---------------------------------------------------------------------------


class TestASSHeader:
    """generate_ass_content produces a valid [Script Info] section."""

    def test_contains_script_info_section(self):
        """Output contains [Script Info] section header."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[Script Info]" in result

    def test_play_res_x_from_video_config(self):
        """PlayResX matches the width from VideoConfig resolution."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "PlayResX: 1920" in result

    def test_play_res_y_from_video_config(self):
        """PlayResY matches the height from VideoConfig resolution."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "PlayResY: 1080" in result

    def test_play_res_custom_resolution(self):
        """PlayResX/Y adapt to a custom resolution."""
        video_config = VideoConfig(resolution="1280x720")
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), video_config
        )
        assert "PlayResX: 1280" in result
        assert "PlayResY: 720" in result

    def test_script_type_v4_plus(self):
        """Output contains ScriptType: v4.00+ for ASS format."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "ScriptType: v4.00+" in result


# ---------------------------------------------------------------------------
# ASS style — [V4+ Styles] section
# ---------------------------------------------------------------------------


class TestASSStyle:
    """generate_ass_content produces a valid [V4+ Styles] section."""

    def test_contains_v4_styles_section(self):
        """Output contains [V4+ Styles] section header."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[V4+ Styles]" in result

    def test_contains_style_line(self):
        """Output contains a Style: definition line."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "Style:" in result

    def test_font_name_from_config(self):
        """Style line uses the font name from SubtitleConfig."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "Montserrat" in result

    def test_custom_font_name(self):
        """Style line uses a custom font name when configured."""
        config = SubtitleConfig(font="Comic Sans")
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        assert "Comic Sans" in result

    def test_font_size_from_config(self):
        """Style line uses the font size from SubtitleConfig."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        # Default font_size is 48
        assert ",48," in result

    def test_custom_font_size(self):
        """Style line uses a custom font size when configured."""
        config = SubtitleConfig(font_size=36)
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        assert ",36," in result


# ---------------------------------------------------------------------------
# Color conversion — hex to ASS &H00BBGGRR& format
# ---------------------------------------------------------------------------


class TestHexToASSColor:
    """_hex_to_ass_color converts #RRGGBB to &H00BBGGRR& format."""

    def test_white(self):
        """White #FFFFFF becomes &H00FFFFFF&."""
        assert _hex_to_ass_color("#FFFFFF") == "&H00FFFFFF&"

    def test_red(self):
        """Red #FF0000 becomes &H000000FF& (BGR reversal)."""
        assert _hex_to_ass_color("#FF0000") == "&H000000FF&"

    def test_green(self):
        """Green #00FF00 stays &H0000FF00& (middle byte unchanged)."""
        assert _hex_to_ass_color("#00FF00") == "&H0000FF00&"

    def test_blue(self):
        """Blue #0000FF becomes &H00FF0000&."""
        assert _hex_to_ass_color("#0000FF") == "&H00FF0000&"

    def test_black(self):
        """Black #000000 becomes &H00000000&."""
        assert _hex_to_ass_color("#000000") == "&H00000000&"

    def test_arbitrary_color(self):
        """Arbitrary color #1A2B3C becomes &H003C2B1A&."""
        assert _hex_to_ass_color("#1A2B3C") == "&H003C2B1A&"

    def test_lowercase_input(self):
        """Lowercase hex input is handled correctly."""
        assert _hex_to_ass_color("#ff0000") == "&H000000FF&"


class TestColorInOutput:
    """Colors from SubtitleConfig appear in the ASS output."""

    def test_primary_color_in_output(self):
        """Primary text color appears in the style section."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        # Default color #FFFFFF -> &H00FFFFFF&
        assert "&H00FFFFFF&" in result

    def test_outline_color_in_output(self):
        """Outline color appears in the style section."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        # Default outline_color #000000 -> &H00000000&
        assert "&H00000000&" in result

    def test_custom_colors(self):
        """Custom colors are properly converted and appear in output."""
        config = SubtitleConfig(color="#FF0000", outline_color="#00FF00")
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        # Red text -> &H000000FF&
        assert "&H000000FF&" in result
        # Green outline -> &H0000FF00&
        assert "&H0000FF00&" in result


# ---------------------------------------------------------------------------
# ASS time formatting
# ---------------------------------------------------------------------------


class TestFormatASSTime:
    """_format_ass_time converts seconds to H:MM:SS.cc format."""

    def test_zero_seconds(self):
        """0.0 seconds formats as 0:00:00.00."""
        assert _format_ass_time(0.0) == "0:00:00.00"

    def test_one_second(self):
        """1.0 seconds formats as 0:00:01.00."""
        assert _format_ass_time(1.0) == "0:00:01.00"

    def test_fractional_seconds(self):
        """2.56 seconds formats as 0:00:02.56."""
        assert _format_ass_time(2.56) == "0:00:02.56"

    def test_minutes(self):
        """65.0 seconds formats as 0:01:05.00."""
        assert _format_ass_time(65.0) == "0:01:05.00"

    def test_hours(self):
        """3661.5 seconds formats as 1:01:01.50."""
        assert _format_ass_time(3661.5) == "1:01:01.50"

    def test_centisecond_precision(self):
        """Time is rounded to centisecond precision."""
        assert _format_ass_time(1.234) == "0:00:01.23"

    def test_centisecond_rounding(self):
        """Time with >2 decimal digits is rounded to centiseconds."""
        assert _format_ass_time(1.999) == "0:00:02.00"


# ---------------------------------------------------------------------------
# Line wrapping — words grouped within max_chars_per_line
# ---------------------------------------------------------------------------


class TestLineWrapping:
    """Words are grouped into subtitle lines respecting max_chars_per_line."""

    def test_no_line_exceeds_max_chars(self):
        """No individual subtitle line exceeds max_chars_per_line."""
        config = SubtitleConfig(max_chars_per_line=20)
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        # Extract Dialogue lines and check \N-split lines
        for line in result.split("\n"):
            if line.startswith("Dialogue:"):
                # Extract text portion after the last comma-delimited field header
                # Format: Dialogue: 0,start,end,Default,,0,0,0,,text
                text = line.split(",", 9)[-1]
                for sub_line in text.split("\\N"):
                    assert len(sub_line) <= 20, (
                        f"Line exceeds limit: '{sub_line}' ({len(sub_line)} chars)"
                    )

    def test_single_long_word_placed_alone(self):
        """A single word longer than max_chars_per_line is placed on its own line."""
        long_word = CaptionWord(word="Supercalifragilisticexpialidocious", start=0.0, end=1.0)
        caption = CaptionResult(
            segments=[CaptionSegment(text=long_word.word, start=0.0, end=1.0)],
            words=[long_word],
            language="en",
            duration=1.0,
        )
        config = SubtitleConfig(max_chars_per_line=10)
        result = generate_ass_content(caption, config, _default_video_config())
        # Should still produce at least one Dialogue line
        assert "Dialogue:" in result

    def test_words_grouped_across_lines(self):
        """With small max_chars_per_line, words are split across multiple subtitle lines."""
        config = SubtitleConfig(max_chars_per_line=15, max_lines=2)
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        # With max_chars=15 and max_lines=2, "The storm raged on." should be split
        # across lines, producing \N in the dialogue text
        dialogue_lines = [ln for ln in result.split("\n") if ln.startswith("Dialogue:")]
        has_multiline = any("\\N" in ln for ln in dialogue_lines)
        assert has_multiline, "Expected multi-line subtitles with small max_chars_per_line"

    def test_max_lines_one_creates_single_line_events(self):
        """With max_lines=1, each subtitle line becomes its own event (no \\N)."""
        config = SubtitleConfig(max_chars_per_line=20, max_lines=1)
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        dialogue_lines = [ln for ln in result.split("\n") if ln.startswith("Dialogue:")]
        for line in dialogue_lines:
            text = line.split(",", 9)[-1]
            assert "\\N" not in text, f"Expected single-line event, got: '{text}'"

    def test_default_config_fits_short_text(self):
        """With default config (42 chars), our 9-word test fits in few dialogue events."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        dialogue_lines = [ln for ln in result.split("\n") if ln.startswith("Dialogue:")]
        # 9 short words should fit in 1-2 dialogue events with 42 char limit
        assert len(dialogue_lines) >= 1
        assert len(dialogue_lines) <= 3


# ---------------------------------------------------------------------------
# Dialogue events — [Events] section
# ---------------------------------------------------------------------------


class TestDialogueEvents:
    """generate_ass_content produces a valid [Events] section."""

    def test_contains_events_section(self):
        """Output contains [Events] section header."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[Events]" in result

    def test_contains_dialogue_lines(self):
        """Output contains at least one Dialogue: line."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "Dialogue:" in result

    def test_dialogue_has_ass_time_format(self):
        """Dialogue lines contain times in H:MM:SS.cc format."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        import re

        dialogue_lines = [ln for ln in result.split("\n") if ln.startswith("Dialogue:")]
        for line in dialogue_lines:
            # Should contain at least two ASS timestamps
            times = re.findall(r"\d:\d{2}:\d{2}\.\d{2}", line)
            assert len(times) >= 2, f"Expected 2 timestamps in: {line}"

    def test_dialogue_times_from_word_timestamps(self):
        """Dialogue start/end times correspond to word start/end timestamps."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        dialogue_lines = [ln for ln in result.split("\n") if ln.startswith("Dialogue:")]
        # First dialogue should start at 0:00:00.00 (first word starts at 0.0)
        assert "0:00:00.00" in dialogue_lines[0]

    def test_dialogue_contains_word_text(self):
        """Dialogue lines contain the actual words from the caption."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        # All words should appear somewhere in the dialogue
        for word in [
            "The",
            "storm",
            "raged",
            "on.",
            "Lightning",
            "cracked",
            "the",
            "sky",
            "above.",
        ]:
            assert word in result, f"Word '{word}' not found in output"


# ---------------------------------------------------------------------------
# Subtitle filter — FFmpeg ASS filter fragment
# ---------------------------------------------------------------------------


class TestSubtitleFilter:
    """subtitle_filter returns the correct FFmpeg filter fragment."""

    def test_returns_ass_filter(self):
        """Returns ass='path' filter string."""
        result = subtitle_filter(Path("/tmp/subs.ass"))
        assert result == "ass='/tmp/subs.ass'"

    def test_different_path(self):
        """Works with a different file path."""
        result = subtitle_filter(Path("/output/project/subtitles/scene_01.ass"))
        assert result == "ass='/output/project/subtitles/scene_01.ass'"

    def test_escapes_single_quote_in_path(self):
        """Single quotes in path are escaped to prevent filter graph breakage."""
        result = subtitle_filter(Path("/tmp/user's project/scene.ass"))
        assert "\\'" in result
        assert result == "ass='/tmp/user\\'s project/scene.ass'"

    def test_escapes_backslash_in_path(self):
        """Backslashes in path are escaped for FFmpeg filter safety."""
        result = subtitle_filter(Path("/tmp/back\\slash/scene.ass"))
        assert result == "ass='/tmp/back\\\\slash/scene.ass'"

    def test_clean_path_unchanged(self):
        """Normal paths without special characters pass through unchanged."""
        result = subtitle_filter(Path("/tmp/subs.ass"))
        assert result == "ass='/tmp/subs.ass'"


# ---------------------------------------------------------------------------
# Empty words — no Dialogue lines produced
# ---------------------------------------------------------------------------


class TestEmptyWords:
    """Empty word list produces valid ASS with no Dialogue lines."""

    def test_empty_words_has_header(self):
        """Empty caption result still produces script info and styles."""
        result = generate_ass_content(
            _make_empty_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[Script Info]" in result
        assert "[V4+ Styles]" in result
        assert "[Events]" in result

    def test_empty_words_no_dialogue(self):
        """Empty caption result produces no Dialogue lines."""
        result = generate_ass_content(
            _make_empty_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "Dialogue:" not in result


# ---------------------------------------------------------------------------
# _hex_to_ass_color input validation
# ---------------------------------------------------------------------------


class TestHexToAssColorValidation:
    """_hex_to_ass_color rejects malformed hex input."""

    def test_rejects_short_hex(self):
        """Three-digit hex is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("#FFF")

    def test_rejects_non_hex_characters(self):
        """Non-hex characters are rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("#GGGGGG")

    def test_rejects_missing_hash(self):
        """Missing '#' prefix is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("FFFFFF")

    def test_rejects_empty_string(self):
        """Empty string is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("")
