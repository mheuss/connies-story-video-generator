"""Tests for story_video.utils.narration_tags — narration tag parsing."""

import pytest

from story_video.utils.narration_tags import parse_story_header


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
