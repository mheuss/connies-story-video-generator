"""Tests for story_video.ffmpeg.subtitles — ASS subtitle generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the subtitle generation functions.
"""

import re
from pathlib import Path

import pytest

from story_video.ffmpeg.subtitles import (
    _format_ass_time,
    _group_words_into_events,
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

    def test_header_shape(self):
        """Output contains [Script Info] with resolution and script type."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[Script Info]" in result
        assert "PlayResX: 1920" in result
        assert "PlayResY: 1080" in result
        assert "ScriptType: v4.00+" in result

    def test_play_res_custom_resolution(self):
        """PlayResX/Y adapt to a custom resolution."""
        video_config = VideoConfig(resolution="1280x720")
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), video_config
        )
        assert "PlayResX: 1280" in result
        assert "PlayResY: 720" in result


# ---------------------------------------------------------------------------
# ASS style — [V4+ Styles] section
# ---------------------------------------------------------------------------


class TestASSStyle:
    """generate_ass_content produces a valid [V4+ Styles] section."""

    def test_style_section_shape(self):
        """Output contains [V4+ Styles] with Style line and default font."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[V4+ Styles]" in result
        assert "Style:" in result
        assert "Montserrat" in result
        assert ",48," in result

    def test_custom_font_name(self):
        """Style line uses a custom font name when configured."""
        config = SubtitleConfig(font="Comic Sans")
        result = generate_ass_content(_make_caption_result(), config, _default_video_config())
        assert "Comic Sans" in result

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

    @pytest.mark.parametrize(
        "hex_input,expected",
        [
            ("#FFFFFF", "&H00FFFFFF&"),
            ("#FF0000", "&H000000FF&"),
            ("#000000", "&H00000000&"),
            ("#1A2B3C", "&H003C2B1A&"),
        ],
        ids=["white", "red", "black", "arbitrary"],
    )
    def test_hex_to_ass_color(self, hex_input, expected):
        """Hex color is correctly converted to ASS &H00BBGGRR& format."""
        assert _hex_to_ass_color(hex_input) == expected


class TestColorInOutput:
    """Colors from SubtitleConfig appear in the ASS output."""

    def test_default_colors_in_output(self):
        """Default primary (#FFFFFF) and outline (#000000) colors appear in output."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "&H00FFFFFF&" in result
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

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "0:00:00.00"),
            (2.56, "0:00:02.56"),
            (65.0, "0:01:05.00"),
            (3661.5, "1:01:01.50"),
            (1.999, "0:00:02.00"),
        ],
        ids=["zero", "fractional", "minutes", "hours", "centisecond_rounding"],
    )
    def test_format_ass_time(self, seconds, expected):
        """Seconds are correctly formatted as H:MM:SS.cc."""
        assert _format_ass_time(seconds) == expected

    def test_negative_seconds_raises(self):
        """Negative seconds raises ValueError."""
        with pytest.raises(ValueError, match="seconds must be >= 0"):
            _format_ass_time(-1.5)


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

    def test_dialogue_events_facets(self):
        """Events section has Dialogue lines with correct timing, format, and text."""
        result = generate_ass_content(
            _make_caption_result(), _default_subtitle_config(), _default_video_config()
        )

        # Contains [Events] section with Dialogue lines
        assert "[Events]" in result
        assert "Dialogue:" in result

        # Dialogue lines have ASS time format
        dialogue_lines = [ln for ln in result.split("\n") if ln.startswith("Dialogue:")]
        for line in dialogue_lines:
            times = re.findall(r"\d:\d{2}:\d{2}\.\d{2}", line)
            assert len(times) >= 2, f"Expected 2 timestamps in: {line}"

        # First dialogue starts at word start time
        assert "0:00:00.00" in dialogue_lines[0]

        # All words appear in the output
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

    def test_escapes_single_quote_in_path(self):
        """Single quotes in path are escaped to prevent filter graph breakage."""
        result = subtitle_filter(Path("/tmp/user's project/scene.ass"))
        assert "\\'" in result
        assert result == "ass='/tmp/user\\'s project/scene.ass'"

    def test_escapes_backslash_in_path(self):
        """Backslashes in path are escaped for FFmpeg filter safety."""
        result = subtitle_filter(Path("/tmp/back\\slash/scene.ass"))
        assert result == "ass='/tmp/back\\\\slash/scene.ass'"

    def test_special_chars_safe_inside_quotes(self):
        """Colons and semicolons (FFmpeg separators) are safe inside single-quoted values."""
        result = subtitle_filter(Path("/tmp/project:v2/scene.ass"))
        assert result == "ass='/tmp/project:v2/scene.ass'"
        result = subtitle_filter(Path("/tmp/dir;name/scene.ass"))
        assert result == "ass='/tmp/dir;name/scene.ass'"


# ---------------------------------------------------------------------------
# Empty words — no Dialogue lines produced
# ---------------------------------------------------------------------------


class TestEmptyWords:
    """Empty word list produces valid ASS with no Dialogue lines."""

    def test_empty_words_has_sections_but_no_dialogue(self):
        """Empty caption result produces valid ASS structure but no Dialogue lines."""
        result = generate_ass_content(
            _make_empty_caption_result(), _default_subtitle_config(), _default_video_config()
        )
        assert "[Script Info]" in result
        assert "[V4+ Styles]" in result
        assert "[Events]" in result
        assert "Dialogue:" not in result


# ---------------------------------------------------------------------------
# _hex_to_ass_color input validation
# ---------------------------------------------------------------------------


class TestHexToAssColorValidation:
    """_hex_to_ass_color rejects malformed hex input."""

    @pytest.mark.parametrize(
        "invalid_hex",
        ["#FFF", "#GGGGGG", "FFFFFF", ""],
        ids=["short_hex", "non_hex_chars", "missing_hash", "empty_string"],
    )
    def test_rejects_invalid_hex(self, invalid_hex):
        """Malformed hex input is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color(invalid_hex)


# ---------------------------------------------------------------------------
# _group_words_into_events — direct unit tests for boundary cases
# ---------------------------------------------------------------------------


class TestGroupWordsIntoEvents:
    """_group_words_into_events boundary case tests."""

    def test_exactly_max_chars_per_line_fits_on_one_line(self):
        """Words totalling exactly max_chars_per_line stay on one line."""
        # "abc def" = 7 chars (3 + 1 space + 3)
        words = [
            CaptionWord(word="abc", start=0.0, end=0.5),
            CaptionWord(word="def", start=0.6, end=1.0),
        ]
        events = _group_words_into_events(words, max_chars_per_line=7, max_lines=2)
        assert len(events) == 1
        assert len(events[0]) == 1  # single line
        assert len(events[0][0]) == 2  # both words on the same line

    def test_exactly_max_lines_per_event(self):
        """When lines fill exactly max_lines, one event is produced with that many lines."""
        # Each word is 5 chars, max_chars_per_line=5, so each word gets its own line
        words = [
            CaptionWord(word="alpha", start=0.0, end=0.5),
            CaptionWord(word="bravo", start=0.6, end=1.0),
            CaptionWord(word="delta", start=1.1, end=1.5),
        ]
        events = _group_words_into_events(words, max_chars_per_line=5, max_lines=3)
        assert len(events) == 1
        assert len(events[0]) == 3  # three lines in one event

    def test_single_word_exceeding_max_chars(self):
        """A single word longer than max_chars_per_line is placed on its own line."""
        words = [
            CaptionWord(word="Supercalifragilistic", start=0.0, end=1.0),
        ]
        events = _group_words_into_events(words, max_chars_per_line=5, max_lines=2)
        assert len(events) == 1
        assert len(events[0]) == 1  # one line
        assert events[0][0][0].word == "Supercalifragilistic"
