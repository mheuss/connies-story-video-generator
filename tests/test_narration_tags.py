"""Tests for story_video.utils.narration_tags — narration tag parsing."""

import pytest

from story_video.utils.narration_tags import (
    extract_tags,
    has_narration_tags,
    parse_narration_segments,
    parse_story_header,
    strip_narration_tags,
)


class TestHasNarrationTags:
    """has_narration_tags detects inline voice/mood tags."""

    def test_voice_tag_detected(self):
        assert has_narration_tags("Hello **voice:jane** world") is True

    def test_mood_tag_detected(self):
        assert has_narration_tags("**mood:sad** Goodbye.") is True

    def test_plain_text_not_detected(self):
        assert has_narration_tags("Just plain text.") is False

    def test_bold_text_not_detected(self):
        assert has_narration_tags("**bold text** is fine") is False

    def test_pause_tag_detected(self):
        assert has_narration_tags("Hello. **pause:1.0** Goodbye.") is True


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

    def test_empty_string_returns_empty(self):
        """Empty string produces no segments."""
        result = parse_narration_segments("", self.VOICE_MAP, "narrator", scene_number=1)
        assert result == []


# ---------------------------------------------------------------------------
# Strip narration tags
# ---------------------------------------------------------------------------


class TestStripNarrationTags:
    """strip_narration_tags() removes voice/mood tags from text."""

    def test_strips_voice_tags(self):
        text = "**voice:narrator** Hello. **voice:villain** Goodbye."
        assert strip_narration_tags(text) == "Hello. Goodbye."

    def test_strips_mood_tags(self):
        text = '**mood:angry** "Never!" he cried.'
        assert strip_narration_tags(text) == '"Never!" he cried.'

    def test_strips_combined_tags(self):
        text = '**voice:old_man** **mood:dry** "Black or white?"'
        assert strip_narration_tags(text) == '"Black or white?"'

    def test_no_tags_unchanged(self):
        text = "The hero spoke plainly."
        assert strip_narration_tags(text) == text

    def test_strips_pause_tags(self):
        text = "Hello. **pause:0.5** Goodbye."
        assert strip_narration_tags(text) == "Hello. Goodbye."


class TestExtractTags:
    """extract_tags returns all voice/mood tags in order."""

    def test_no_tags(self):
        assert extract_tags("Plain text with no tags.") == []

    def test_single_voice_tag(self):
        text = "**voice:narrator** He spoke softly."
        assert extract_tags(text) == ["**voice:narrator**"]

    def test_multiple_tags(self):
        text = '**voice:old_man** "I\'ve seen worse," **voice:narrator** he muttered.'
        assert extract_tags(text) == ["**voice:old_man**", "**voice:narrator**"]

    def test_mood_tag(self):
        text = "**mood:somber** The rain fell."
        assert extract_tags(text) == ["**mood:somber**"]

    def test_mixed_voice_and_mood(self):
        text = "**voice:jane** **mood:excited** She laughed."
        assert extract_tags(text) == ["**voice:jane**", "**mood:excited**"]

    def test_pause_tag(self):
        text = "Hello. **pause:0.5** Goodbye."
        assert extract_tags(text) == ["**pause:0.5**"]

    def test_mixed_voice_mood_pause(self):
        text = "**voice:jane** Hello. **pause:1.0** **mood:sad** Goodbye."
        assert extract_tags(text) == ["**voice:jane**", "**pause:1.0**", "**mood:sad**"]


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

    def test_negative_pause_raises(self):
        """Negative pause value raises ValidationError (Pydantic gt=0)."""
        text = "Hello. **pause:-1** Goodbye."
        with pytest.raises((ValueError,)):
            parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)

    def test_zero_pause_raises(self):
        """Zero pause value raises ValidationError (Pydantic gt=0)."""
        text = "Hello. **pause:0** Goodbye."
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
        import logging

        text = "Hello. **pause:60.0** Goodbye."
        with caplog.at_level(logging.WARNING):
            parse_narration_segments(text, self.VOICE_MAP, "narrator", scene_number=1)
        assert any("unusually long" in r.message for r in caplog.records)
