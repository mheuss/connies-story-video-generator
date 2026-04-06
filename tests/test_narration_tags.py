"""Tests for story_video.utils.narration_tags — narration tag parsing."""

import logging

import pytest

from story_video.models import AudioAsset, ImageTag, MusicTag
from story_video.utils.narration_tags import (
    extract_image_tags,
    extract_image_tags_stripped,
    extract_music_tags,
    extract_music_tags_stripped,
    extract_tags,
    has_narration_tags,
    parse_narration_segments,
    parse_story_header,
    strip_image_tags,
    strip_music_tags,
    strip_narration_tags,
    validate_image_tags,
    validate_music_tags,
)


class TestHasNarrationTags:
    """has_narration_tags detects inline voice/mood tags."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Hello **voice:jane** world", True),
            ("**mood:sad** Goodbye.", True),
            ("Just plain text.", False),
            ("**bold text** is fine", False),
            ("Hello. **pause:1.0** Goodbye.", True),
            ("", False),
        ],
        ids=["voice", "mood", "plain", "bold", "pause", "empty"],
    )
    def test_has_narration_tags(self, text, expected):
        assert has_narration_tags(text) is expected


class TestParseStoryHeader:
    """parse_story_header extracts YAML front matter from story text."""

    def test_valid_header(self):
        text = (
            "---\nvoices:\n  narrator: nova\n  jane: shimmer\n"
            "default_voice: narrator\n---\nStory text here."
        )
        header, body = parse_story_header(text)
        assert header is not None
        assert header.voices == {"narrator": "nova", "jane": "shimmer"}
        assert header.default_voice == "narrator"
        assert body == "Story text here."

    def test_no_header(self):
        text = "Just a plain story with no header."
        header, body = parse_story_header(text)
        assert header is None
        assert body == text

    def test_default_voice_defaults_to_narrator(self):
        text = "---\nvoices:\n  narrator: nova\n---\nBody."
        header, body = parse_story_header(text)
        assert header.default_voice == "narrator"

    def test_empty_voices_raises(self):
        text = "---\nvoices: {}\n---\nBody."
        with pytest.raises(ValueError, match="[Ee]mpty"):
            parse_story_header(text)

    def test_invalid_yaml_raises(self):
        text = "---\n: invalid: yaml: {{{\n---\nBody."
        with pytest.raises(ValueError, match="[Pp]arse"):
            parse_story_header(text)

    def test_body_whitespace_stripped(self):
        text = "---\nvoices:\n  narrator: nova\n---\n\n  Story text.  \n\n"
        header, body = parse_story_header(text)
        assert body == "Story text."

    def test_no_closing_delimiter(self):
        text = "---\nvoices:\n  narrator: nova\nStory text."
        header, body = parse_story_header(text)
        assert header is None
        assert body == text

    def test_non_dict_yaml_raises(self):
        """YAML that parses to a scalar (not a dict) raises ValueError."""
        text = "---\njust a string\n---\nBody."
        with pytest.raises(ValueError, match="[Ee]mpty"):
            parse_story_header(text)

    def test_voices_null_raises(self):
        """voices: null (YAML None) raises ValueError."""
        text = "---\nvoices:\n---\nBody."
        with pytest.raises(ValueError, match="[Ee]mpty"):
            parse_story_header(text)

    def test_invalid_default_voice_raises(self):
        """default_voice not in voices triggers Pydantic validation error."""
        text = "---\nvoices:\n  narrator: nova\ndefault_voice: unknown\n---\nBody."
        with pytest.raises(ValueError, match="Invalid story header"):
            parse_story_header(text)


class TestParseStoryHeaderYamlDelimiter:
    """parse_story_header handles --- appearing inside YAML values.

    The closing --- delimiter must not be confused with --- that appears
    as part of a YAML value (e.g., in a multi-line quoted string or
    block scalar). These tests verify that values containing --- are
    preserved and that no data is silently lost.
    """

    def test_dashes_in_quoted_string_same_line(self):
        """--- inside a quoted string on the same line is not a delimiter."""
        text = (
            "---\nvoices:\n  narrator: nova\n"
            'images:\n  divider: "A scene showing --- between worlds"\n'
            "---\nBody text."
        )
        header, body = parse_story_header(text)
        assert header is not None
        assert header.images["divider"] == "A scene showing --- between worlds"
        assert body == "Body text."

    def test_block_scalar_dashes_at_column_zero_terminates_header(self):
        """--- at column 0 terminates a block scalar and the header.

        PyYAML treats --- at column 0 as a document separator in all
        contexts.  In a block scalar, this truncates the value and ends
        the front matter.  Any YAML keys after the --- are lost.  Authors
        must use indented --- (inside block scalars) or inline ---
        (inside quoted strings) to include literal dashes in values.
        """
        text = (
            "---\nvoices:\n  narrator: nova\nimages:\n  scene: |\n    text before\n---\nBody text."
        )
        header, body = parse_story_header(text)
        assert header is not None
        # Block scalar value is truncated at the --- document boundary
        assert "text before" in header.images["scene"]
        assert "---" not in header.images["scene"]
        assert body == "Body text."

    def test_dashes_in_block_scalar_indented(self):
        """--- indented inside a block scalar is not a delimiter."""
        text = (
            "---\n"
            "voices:\n"
            "  narrator: nova\n"
            "images:\n"
            "  transition: |\n"
            "    A horizontal divider\n"
            "    ---\n"
            "    separating two worlds\n"
            '  lighthouse: "A lighthouse at dawn"\n'
            "---\n"
            "Body text."
        )
        header, body = parse_story_header(text)
        assert header is not None
        assert "transition" in header.images
        assert "lighthouse" in header.images
        assert "---" in header.images["transition"]
        assert body == "Body text."

    def test_body_starting_with_dashes_not_confused(self):
        """--- in the body text (e.g., markdown HR) does not affect parsing."""
        text = "---\nvoices:\n  narrator: nova\n---\n---\nThe story begins."
        header, body = parse_story_header(text)
        assert header is not None
        assert header.voices == {"narrator": "nova"}
        assert body.startswith("---")


class TestParseStoryHeaderNonAscii:
    """parse_story_header handles non-ASCII characters in voice labels and values."""

    def test_non_ascii_voice_labels(self):
        """Unicode voice labels (e.g., CJK, accented) parse correctly."""
        text = "---\nvoices:\n  旁白: nova\n  María: shimmer\ndefault_voice: 旁白\n---\nBody text."
        header, body = parse_story_header(text)
        assert header is not None
        assert header.voices == {"旁白": "nova", "María": "shimmer"}
        assert header.default_voice == "旁白"
        assert body == "Body text."

    def test_non_ascii_voice_ids(self):
        """Unicode characters in voice ID values parse correctly."""
        text = "---\nvoices:\n  narrator: ナレーター\n---\nBody text."
        header, body = parse_story_header(text)
        assert header is not None
        assert header.voices["narrator"] == "ナレーター"

    def test_non_ascii_image_keys_and_prompts(self):
        """Unicode in image keys and prompt values parse correctly."""
        text = '---\nvoices:\n  narrator: nova\nimages:\n  灯台: "夜明けの灯台"\n---\nBody text.'
        header, body = parse_story_header(text)
        assert header is not None
        assert header.images["灯台"] == "夜明けの灯台"

    def test_emoji_in_voice_label(self):
        """Emoji characters in voice labels parse correctly."""
        text = "---\nvoices:\n  narrator_🎙️: nova\ndefault_voice: narrator_🎙️\n---\nBody text."
        header, body = parse_story_header(text)
        assert header is not None
        assert "narrator_🎙️" in header.voices


class TestParseNarrationSegments:
    """parse_narration_segments splits tagged text into segments."""

    VOICE_MAP = {"narrator": "nova", "jane": "shimmer", "bob": "echo"}

    def test_no_tags_single_segment(self):
        segments = parse_narration_segments(
            "Plain text.", self.VOICE_MAP, "narrator", scene_number=1
        )
        assert len(segments) == 1
        assert segments[0].text == "Plain text."
        assert segments[0].voice == "nova"
        assert segments[0].voice_label == "narrator"
        assert segments[0].mood is None

    def test_voice_tag_splits_into_two_segments(self):
        text = 'The narrator spoke. **voice:jane** "Hello!" she said.'
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 2
        assert segments[0].voice_label == "narrator"
        assert segments[0].text == "The narrator spoke."
        assert segments[1].voice_label == "jane"
        assert segments[1].voice == "shimmer"

    def test_mood_tag_sets_instructions(self):
        text = '**mood:sad** "My mother died today."'
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 1
        assert segments[0].mood == "sad"

    def test_voice_tag_resets_mood(self):
        text = "**mood:sad** Sad text. **voice:jane** Happy text."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert segments[0].mood == "sad"
        assert segments[1].mood is None

    def test_consecutive_tags_merge(self):
        text = '**voice:jane** **mood:happy** "Hooray!"'
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 1
        assert segments[0].voice_label == "jane"
        assert segments[0].mood == "happy"

    def test_whitespace_only_segments_dropped(self):
        text = '   **voice:jane** "Hello!"'
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 1
        assert segments[0].voice_label == "jane"

    def test_unknown_voice_raises(self):
        text = '**voice:unknown** "Hello!"'
        with pytest.raises(ValueError, match="Unknown voice label"):
            parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)

    def test_segment_indices_sequential(self):
        text = "A. **voice:jane** B. **voice:bob** C."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert [s.segment_index for s in segments] == [0, 1, 2]

    def test_scene_number_propagated(self):
        segments = parse_narration_segments("Text.", self.VOICE_MAP, "narrator", scene_number=5)
        assert segments[0].scene_number == 5

    def test_mood_neutral_clears_mood(self):
        text = "**mood:sad** Sad text. **mood:neutral** Neutral text."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert segments[0].mood == "sad"
        assert segments[1].mood is None

    def test_multiple_voice_switches(self):
        text = (
            'Narration. **voice:jane** "Hi." **voice:bob** "Yo." **voice:narrator** More narration.'
        )
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 4
        labels = [s.voice_label for s in segments]
        assert labels == ["narrator", "jane", "bob", "narrator"]

    def test_unknown_default_voice_raises(self):
        """Unknown default voice (no tags in text) raises ValueError."""
        with pytest.raises(ValueError, match="Unknown voice label"):
            parse_narration_segments(
                "Plain text.", self.VOICE_MAP, "unknown_default", scene_number=1
            )

    def test_consecutive_mood_tags_last_wins(self):
        """Two consecutive mood tags — second overwrites first."""
        text = "**mood:sad** **mood:happy** Text."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 1
        assert segments[0].mood == "happy"


class TestParseNarrationSegmentsEdgeCases:
    """parse_narration_segments handles edge-case inputs."""

    VOICE_MAP = {"narrator": "nova"}

    def test_empty_string_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty or whitespace"):
            parse_narration_segments("", self.VOICE_MAP, "narrator", scene_number=1)

    def test_whitespace_only_raises(self):
        """Whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="empty or whitespace"):
            parse_narration_segments("   ", self.VOICE_MAP, "narrator", scene_number=1)

    def test_empty_voice_map_raises(self):
        """Empty voice_map raises ValueError."""
        with pytest.raises(ValueError, match="voice_map must not be empty"):
            parse_narration_segments("Hello.", {}, "narrator", scene_number=1)


# ---------------------------------------------------------------------------
# Strip narration tags
# ---------------------------------------------------------------------------


class TestStripNarrationTags:
    """strip_narration_tags() removes voice/mood tags from text."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("**voice:narrator** Hello. **voice:villain** Goodbye.", "Hello. Goodbye."),
            ('**mood:angry** "Never!" he cried.', '"Never!" he cried.'),
            ('**voice:old_man** **mood:dry** "Black or white?"', '"Black or white?"'),
            ("The hero spoke plainly.", "The hero spoke plainly."),
            ("Hello. **pause:0.5** Goodbye.", "Hello. Goodbye."),
            ("", ""),
        ],
        ids=["voice", "mood", "combined", "no_tags", "pause", "empty"],
    )
    def test_strip_narration_tags(self, text, expected):
        assert strip_narration_tags(text) == expected

    def test_strips_image_tags(self):
        text = "Before **image:lighthouse** after"
        assert strip_narration_tags(text) == "Before after"


class TestExtractTags:
    """extract_tags returns all voice/mood tags in order."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Plain text with no tags.", []),
            ("**voice:narrator** He spoke softly.", ["**voice:narrator**"]),
            (
                '**voice:old_man** "I\'ve seen worse," **voice:narrator** he muttered.',
                ["**voice:old_man**", "**voice:narrator**"],
            ),
            ("**mood:somber** The rain fell.", ["**mood:somber**"]),
            (
                "**voice:jane** **mood:excited** She laughed.",
                ["**voice:jane**", "**mood:excited**"],
            ),
            ("Hello. **pause:0.5** Goodbye.", ["**pause:0.5**"]),
            (
                "**voice:jane** Hello. **pause:1.0** **mood:sad** Goodbye.",
                ["**voice:jane**", "**pause:1.0**", "**mood:sad**"],
            ),
            ("", []),
        ],
        ids=[
            "no_tags",
            "single_voice",
            "multiple_tags",
            "mood",
            "mixed_voice_mood",
            "pause",
            "mixed_all",
            "empty",
        ],
    )
    def test_extract_tags(self, text, expected):
        assert extract_tags(text) == expected


class TestPauseTagParsing:
    """parse_narration_segments handles **pause:N** tags."""

    VOICE_MAP = {"narrator": "nova", "jane": "shimmer"}

    def test_pause_segment_has_duration(self):
        """**pause:0.5** produces a segment with pause_duration=0.5."""
        text = "Hello. **pause:0.5** Goodbye."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        pause_segments = [s for s in segments if s.pause_duration is not None]
        assert len(pause_segments) == 1
        assert pause_segments[0].pause_duration == 0.5

    def test_pause_between_voice_segments(self):
        """Pause between two voice segments produces 3 segments: speech, pause, speech."""
        text = 'Hello. **pause:1.0** **voice:jane** "Hi!"'
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 3
        assert segments[0].text == "Hello."
        assert segments[0].pause_duration is None
        assert segments[1].pause_duration == 1.0
        assert segments[2].text == '"Hi!"'

    def test_pause_at_start(self):
        """Pause at start of text."""
        text = "**pause:0.5** Hello."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert segments[0].pause_duration == 0.5
        assert segments[1].text == "Hello."

    def test_pause_at_end(self):
        """Pause at end of text — no trailing speech segment."""
        text = "Hello. **pause:0.5**"
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert len(segments) == 2
        assert segments[0].text == "Hello."
        assert segments[1].pause_duration == 0.5

    def test_consecutive_pauses(self):
        """Two consecutive pauses both produce segments."""
        text = "Hello. **pause:0.5** **pause:1.0** Goodbye."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        pauses = [s for s in segments if s.pause_duration is not None]
        assert len(pauses) == 2
        assert pauses[0].pause_duration == 0.5
        assert pauses[1].pause_duration == 1.0

    def test_invalid_pause_value_raises(self):
        """Non-numeric pause value raises ValueError."""
        text = "Hello. **pause:abc** Goodbye."
        with pytest.raises(ValueError, match="[Ii]nvalid pause duration"):
            parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)

    @pytest.mark.parametrize("value", [-1, 0], ids=["negative", "zero"])
    def test_non_positive_pause_raises(self, value):
        """Negative or zero pause value raises ValueError (Pydantic gt=0)."""
        text = f"Hello. **pause:{value}** Goodbye."
        with pytest.raises((ValueError,)):
            parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)

    def test_pause_segment_indices_sequential(self):
        """Pause segments get correct sequential indices."""
        text = "A. **pause:0.5** B."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert [s.segment_index for s in segments] == [0, 1, 2]

    def test_large_pause_allowed(self):
        """Large pause values (>30s) are allowed."""
        text = "Hello. **pause:60.0** Goodbye."
        segments = parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        pauses = [s for s in segments if s.pause_duration is not None]
        assert pauses[0].pause_duration == 60.0

    def test_large_pause_logs_warning(self, caplog):
        """Pause >30s logs a warning."""
        text = "Hello. **pause:60.0** Goodbye."
        with caplog.at_level(logging.WARNING):
            parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert any("unusually long" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Extract image tags
# ---------------------------------------------------------------------------


class TestExtractImageTags:
    """extract_image_tags() finds image tags with character offsets."""

    def test_single_tag(self):
        text = "Some text **image:lighthouse** more text"
        tags = extract_image_tags(text)
        assert len(tags) == 1
        assert tags[0].key == "lighthouse"
        assert tags[0].position == 10

    def test_multiple_tags(self):
        text = "Start **image:lighthouse** middle **image:harbor** end"
        tags = extract_image_tags(text)
        assert len(tags) == 2
        assert tags[0].key == "lighthouse"
        assert tags[1].key == "harbor"
        assert tags[0].position < tags[1].position

    def test_no_tags(self):
        text = "Plain text with no tags"
        assert extract_image_tags(text) == []

    def test_mixed_with_other_tags(self):
        text = "**voice:narrator** text **image:lighthouse** more **mood:sad** end"
        tags = extract_image_tags(text)
        assert len(tags) == 1
        assert tags[0].key == "lighthouse"


# ---------------------------------------------------------------------------
# StoryHeader images map
# ---------------------------------------------------------------------------


class TestStoryHeaderImages:
    """StoryHeader accepts an optional images map."""

    def test_header_with_images(self):
        header, body = parse_story_header(
            "---\nvoices:\n  narrator: alloy\n"
            'images:\n  lighthouse: "A lighthouse at dawn"\n---\nBody text'
        )
        assert header is not None
        assert header.images == {"lighthouse": "A lighthouse at dawn"}

    def test_header_without_images(self):
        header, body = parse_story_header("---\nvoices:\n  narrator: alloy\n---\nBody text")
        assert header is not None
        assert header.images == {}

    def test_header_images_empty_value_rejected(self):
        with pytest.raises(ValueError):
            parse_story_header(
                '---\nvoices:\n  narrator: alloy\nimages:\n  lighthouse: ""\n---\nBody'
            )


# ---------------------------------------------------------------------------
# Validate image tags
# ---------------------------------------------------------------------------


class TestValidateImageTags:
    """validate_image_tags() checks tag keys against YAML images map."""

    def test_valid_tags_pass(self):
        images = {"lighthouse": "A lighthouse", "harbor": "A harbor"}
        tags = [ImageTag(key="lighthouse", position=0), ImageTag(key="harbor", position=50)]
        validate_image_tags(tags, images)  # Should not raise

    def test_unknown_tag_raises(self):
        images = {"lighthouse": "A lighthouse"}
        tags = [ImageTag(key="lighthouse", position=0), ImageTag(key="castle", position=50)]
        with pytest.raises(ValueError, match="castle"):
            validate_image_tags(tags, images)

    def test_empty_tags_pass(self):
        validate_image_tags([], {})  # No tags, no images — valid

    def test_unused_images_allowed(self):
        images = {"lighthouse": "A lighthouse", "harbor": "A harbor"}
        tags = [ImageTag(key="lighthouse", position=0)]
        validate_image_tags(tags, images)  # harbor unused but allowed


# ---------------------------------------------------------------------------
# Strip image tags (image-only stripping)
# ---------------------------------------------------------------------------


class TestStripImageTags:
    """strip_image_tags() removes only image tags, leaving voice/mood intact."""

    def test_removes_image_tags(self):
        text = "Before **image:lighthouse** after"
        assert strip_image_tags(text) == "Before after"

    def test_removes_multiple_image_tags(self):
        text = "A **image:lighthouse** B **image:harbor** C"
        assert strip_image_tags(text) == "A B C"

    def test_preserves_voice_tags(self):
        text = "**voice:narrator** Hello **image:lighthouse** world"
        assert strip_image_tags(text) == "**voice:narrator** Hello world"

    def test_preserves_mood_tags(self):
        text = "**mood:sad** Goodbye **image:castle** forever"
        assert strip_image_tags(text) == "**mood:sad** Goodbye forever"

    def test_no_tags_unchanged(self):
        text = "Plain text with no tags."
        assert strip_image_tags(text) == text

    def test_only_image_tags(self):
        text = "**image:a** **image:b**"
        assert strip_image_tags(text) == ""


# ---------------------------------------------------------------------------
# Extract image tags with stripped positions
# ---------------------------------------------------------------------------


class TestExtractImageTagsStripped:
    """extract_image_tags_stripped() returns positions in stripped coordinates."""

    def test_single_tag_no_other_tags(self):
        """Position in text with no other tags to strip."""
        text = "Before **image:lighthouse** after"
        tags = extract_image_tags_stripped(text)
        assert len(tags) == 1
        assert tags[0].key == "lighthouse"
        # Stripped text is "Before after" — tag was at position 7 ("Before ")
        assert tags[0].position == 7

    def test_positions_in_stripped_coordinate_system(self):
        """Positions map correctly when voice/mood tags precede image tags."""
        text = "**voice:narrator** Before **image:a** between **image:b** after"
        tags = extract_image_tags_stripped(text)
        assert len(tags) == 2
        assert tags[0].key == "a"
        assert tags[1].key == "b"
        # All-tags-stripped text: "Before between after"
        # "Before " = 7 chars
        stripped_text = strip_narration_tags(text)
        assert stripped_text == "Before between after"
        assert stripped_text[tags[0].position :].startswith("between")
        assert stripped_text[tags[1].position :].startswith("after")

    def test_no_tags_returns_empty(self):
        text = "Plain text with no tags."
        assert extract_image_tags_stripped(text) == []

    def test_image_tag_after_voice_and_mood(self):
        """Position adjusts for all preceding stripped tags."""
        text = "**voice:narrator** **mood:dry** Hello **image:lighthouse** world"
        tags = extract_image_tags_stripped(text)
        assert len(tags) == 1
        assert tags[0].key == "lighthouse"
        # Stripped text: "Hello world"
        stripped_text = strip_narration_tags(text)
        assert stripped_text == "Hello world"
        assert stripped_text[tags[0].position :].startswith("world")

    def test_multiple_image_tags_sequential_positions(self):
        """Multiple image tags get correct sequential positions."""
        text = "**image:a** middle **image:b**"
        tags = extract_image_tags_stripped(text)
        assert len(tags) == 2
        # Stripped text: "middle " (trailing space from between tags)
        stripped_text = strip_narration_tags(text)
        assert stripped_text == "middle "
        # First image tag at position 0 (start of stripped text)
        assert tags[0].position == 0
        # Second image tag at position 7 ("middle " = 7 chars)
        assert tags[1].position == 7

    def test_positions_stay_aligned_with_multiline_whitespace_between_tags(self):
        """Image positions are measured from the fully stripped prefix text."""
        text = "**voice:narrator**\n  Before\n  **mood:dry**\n  **image:lighthouse** After"
        tags = extract_image_tags_stripped(text)
        stripped_text = strip_narration_tags(text)

        assert stripped_text == "Before\n  After"
        assert tags[0].position == len("Before\n  ")
        assert stripped_text[tags[0].position :] == "After"


# ---------------------------------------------------------------------------
# Extract music tags
# ---------------------------------------------------------------------------


class TestExtractMusicTags:
    """extract_music_tags finds **music:key** tags with positions."""

    def test_no_tags(self):
        assert extract_music_tags("No tags here.") == []

    def test_single_tag(self):
        text = "The rain fell. **music:rain** Thunder rolled."
        tags = extract_music_tags(text)
        assert len(tags) == 1
        assert tags[0].key == "rain"
        assert tags[0].position == text.index("**music:rain**")

    def test_multiple_tags(self):
        text = "**music:rain** Then **music:thunder** boom."
        tags = extract_music_tags(text)
        assert len(tags) == 2
        assert tags[0].key == "rain"
        assert tags[1].key == "thunder"

    def test_key_whitespace_stripped(self):
        text = "**music: rain ** hello"
        tags = extract_music_tags(text)
        assert tags[0].key == "rain"

    def test_ignores_other_tag_types(self):
        text = "**voice:jane** **mood:sad** **pause:1.0** **image:pic**"
        assert extract_music_tags(text) == []


# ---------------------------------------------------------------------------
# Strip music tags
# ---------------------------------------------------------------------------


class TestStripMusicTags:
    """strip_music_tags removes only **music:key** tags."""

    def test_removes_music_tag(self):
        assert strip_music_tags("Hello **music:rain** world") == "Hello world"

    def test_preserves_other_tags(self):
        text = "**voice:jane** hello **music:rain** world"
        result = strip_music_tags(text)
        assert "**voice:jane**" in result
        assert "**music:rain**" not in result

    def test_no_tags_unchanged(self):
        text = "Plain text."
        assert strip_music_tags(text) == text

    def test_multiple_tags(self):
        text = "**music:rain** a **music:thunder** b"
        result = strip_music_tags(text)
        assert result == "a b"


# ---------------------------------------------------------------------------
# Extract music tags with stripped positions
# ---------------------------------------------------------------------------


class TestExtractMusicTagsStripped:
    """extract_music_tags_stripped computes positions in stripped-text coordinates."""

    def test_position_accounts_for_stripped_tags(self):
        # voice tag (18 chars with trailing space) appears before music tag
        text = "**voice:narrator** Hello. **music:rain** World."
        tags = extract_music_tags_stripped(text)
        assert len(tags) == 1
        assert tags[0].key == "rain"
        # Stripped text: "Hello. World."
        # "Hello. " = 7 chars
        assert tags[0].position == 7

    def test_multiple_music_tags_with_other_tags(self):
        text = "**voice:jane** A **music:rain** B **mood:sad** C **music:thunder** D"
        tags = extract_music_tags_stripped(text)
        assert len(tags) == 2
        assert tags[0].key == "rain"
        assert tags[1].key == "thunder"

    def test_no_tags(self):
        assert extract_music_tags_stripped("Plain text") == []


# ---------------------------------------------------------------------------
# Validate music tags
# ---------------------------------------------------------------------------


class TestValidateMusicTags:
    """validate_music_tags ensures all tag keys exist in audio map."""

    def test_valid_keys_pass(self):
        tags = [MusicTag(key="rain", position=0)]
        audio_map = {"rain": AudioAsset(file="rain.mp3")}
        validate_music_tags(tags, audio_map)  # Should not raise

    def test_unknown_key_raises(self):
        tags = [MusicTag(key="thunder", position=0)]
        audio_map = {"rain": AudioAsset(file="rain.mp3")}
        with pytest.raises(ValueError, match="thunder"):
            validate_music_tags(tags, audio_map)

    def test_empty_tags_pass(self):
        validate_music_tags([], {})  # Should not raise


# ---------------------------------------------------------------------------
# StoryHeader audio map parsing
# ---------------------------------------------------------------------------


class TestParseStoryHeaderAudio:
    """parse_story_header parses the audio: map from YAML front matter."""

    def test_header_with_audio_map(self):
        text = (
            "---\n"
            "voices:\n"
            "  narrator: nova\n"
            "audio:\n"
            "  rain:\n"
            "    file: sounds/rain.mp3\n"
            "    volume: 0.2\n"
            "    loop: true\n"
            "  thunder:\n"
            "    file: sounds/thunder.mp3\n"
            "---\n"
            "Story body here."
        )
        header, body = parse_story_header(text)
        assert header is not None
        assert len(header.audio) == 2
        assert header.audio["rain"].file == "sounds/rain.mp3"
        assert header.audio["rain"].volume == 0.2
        assert header.audio["rain"].loop is True
        assert header.audio["thunder"].file == "sounds/thunder.mp3"
        assert header.audio["thunder"].volume == 0.3  # default
        assert body == "Story body here."

    def test_header_without_audio_still_works(self):
        text = "---\nvoices:\n  narrator: nova\n---\nBody."
        header, _ = parse_story_header(text)
        assert header is not None
        assert header.audio == {}

    def test_audio_with_invalid_volume_raises(self):
        text = (
            "---\n"
            "voices:\n"
            "  narrator: nova\n"
            "audio:\n"
            "  rain:\n"
            "    file: rain.mp3\n"
            "    volume: 2.0\n"
            "---\n"
            "Body."
        )
        with pytest.raises(ValueError, match="Invalid story header"):
            parse_story_header(text)

    def test_audio_with_empty_file_raises(self):
        text = "---\nvoices:\n  narrator: nova\naudio:\n  rain:\n    file: ''\n---\nBody."
        with pytest.raises(ValueError, match="Invalid story header"):
            parse_story_header(text)
