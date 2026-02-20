"""Tests for story_video.pipeline.narration_prep — LLM-based TTS text preparation."""

import json
from unittest.mock import MagicMock

import pytest

from story_video.pipeline.narration_prep import (
    _SYSTEM_PROMPT,
    _TOOL_NAME,
    _TOOL_SCHEMA,
    NarrationPrepError,
    _build_user_message,
    _validate_tags_preserved,
    prepare_narration_llm,
    write_narration_changelog,
)


class TestValidateTagsPreserved:
    """_validate_tags_preserved checks tags match between original and modified."""

    def test_identical_tags_valid(self):
        original = "**voice:narrator** Hello."
        modified = "**voice:narrator** Greetings."
        assert _validate_tags_preserved(original, modified) is True

    def test_missing_tag_invalid(self):
        original = "**voice:narrator** Hello **voice:bob** world."
        modified = "**voice:narrator** Hello world."
        assert _validate_tags_preserved(original, modified) is False

    def test_reordered_tags_invalid(self):
        original = "**voice:a** text **voice:b** more."
        modified = "**voice:b** text **voice:a** more."
        assert _validate_tags_preserved(original, modified) is False

    def test_extra_tag_invalid(self):
        original = "**voice:narrator** Hello."
        modified = "**voice:narrator** Hello **mood:sad** world."
        assert _validate_tags_preserved(original, modified) is False

    def test_pause_tag_counted_in_validation(self):
        """Pause tags are included in the tag validation check."""
        original = "Hello. **pause:0.5** Goodbye."
        modified = "Hello. **pause:0.5** Goodbye."
        assert _validate_tags_preserved(original, modified) is True

    def test_pause_tag_removed_fails_validation(self):
        """Removing a pause tag fails validation."""
        original = "Hello. **pause:0.5** Goodbye."
        modified = "Hello. Goodbye."
        assert _validate_tags_preserved(original, modified) is False

    def test_no_tags_both_sides_valid(self):
        assert _validate_tags_preserved("Plain text.", "Different plain text.") is True


class TestNarrationPrepError:
    """NarrationPrepError is a distinct exception type."""

    def test_is_exception(self):
        with pytest.raises(NarrationPrepError, match="scene 1"):
            raise NarrationPrepError("scene 1: tags corrupted")

    def test_subclass_of_exception(self):
        assert issubclass(NarrationPrepError, Exception)


class TestBuildUserMessage:
    """_build_user_message constructs the Claude user message."""

    def test_basic_message(self):
        result = _build_user_message(
            "Hello world.",
            pronunciation_guide=[],
            story_title="Test Story",
            scene_number=1,
            total_scenes=3,
        )
        assert "Test Story" in result
        assert "Scene 1 of 3" in result
        assert "Hello world." in result

    def test_includes_pronunciation_guide(self):
        guide = [{"term": "Cthulhu", "pronunciation": "kuh-THOO-loo", "context": "proper noun"}]
        result = _build_user_message(
            "Cthulhu rises.",
            pronunciation_guide=guide,
            story_title="Horror",
            scene_number=2,
            total_scenes=5,
        )
        assert "Cthulhu" in result
        assert "kuh-THOO-loo" in result

    def test_empty_guide_omitted(self):
        result = _build_user_message(
            "Plain text.",
            pronunciation_guide=[],
            story_title="Test",
            scene_number=1,
            total_scenes=1,
        )
        assert "Pronunciation guide" not in result


class TestPromptConstants:
    """Verify prompt constants exist and have expected structure."""

    def test_system_prompt_mentions_tags(self):
        assert "voice" in _SYSTEM_PROMPT.lower()
        assert "mood" in _SYSTEM_PROMPT.lower()

    def test_tool_schema_has_required_fields(self):
        props = _TOOL_SCHEMA["properties"]
        assert "modified_text" in props
        assert "changes" in props
        assert "pronunciation_guide_additions" in props

    def test_tool_name_is_string(self):
        assert isinstance(_TOOL_NAME, str)
        assert len(_TOOL_NAME) > 0


class TestPrepareNarrationLlm:
    """prepare_narration_llm calls Claude and returns structured result."""

    def _make_mock_client(self, modified_text="Prepared text.", changes=None, guide=None):
        """Create a mock ClaudeClient returning a canned response."""
        client = MagicMock()
        client.generate_structured.return_value = {
            "modified_text": modified_text,
            "changes": changes or [],
            "pronunciation_guide_additions": guide or [],
        }
        return client

    def test_returns_modified_text(self):
        client = self._make_mock_client(modified_text="Rewritten text.")
        result = prepare_narration_llm("Original text.", client)
        assert result["modified_text"] == "Rewritten text."

    def test_returns_changes(self):
        changes = [{"original": "Dr.", "replacement": "Doctor", "reason": "abbreviation"}]
        client = self._make_mock_client(changes=changes)
        result = prepare_narration_llm("Dr. Smith spoke.", client)
        assert result["changes"] == changes

    def test_returns_pronunciation_guide_additions(self):
        guide = [{"term": "Cthulhu", "pronunciation": "kuh-THOO-loo", "context": "deity name"}]
        client = self._make_mock_client(guide=guide)
        result = prepare_narration_llm("Cthulhu rises.", client)
        assert result["pronunciation_guide_additions"] == guide

    def test_passes_pronunciation_guide_to_prompt(self):
        client = self._make_mock_client()
        guide = [{"term": "Nyarlathotep", "pronunciation": "nyar-LATH-oh-tep", "context": "name"}]
        prepare_narration_llm(
            "Plain text.", client, pronunciation_guide=guide, scene_number=2, total_scenes=3
        )

        call_kwargs = client.generate_structured.call_args.kwargs
        assert "Nyarlathotep" in call_kwargs["user_message"]

    def test_preserves_tags_passes(self):
        client = self._make_mock_client(modified_text="**voice:narrator** Prepared text.")
        result = prepare_narration_llm("**voice:narrator** Original text.", client)
        assert result["modified_text"] == "**voice:narrator** Prepared text."

    def test_corrupted_tags_retries_once(self):
        client = MagicMock()
        # First call: tags missing. Second call: tags correct.
        client.generate_structured.side_effect = [
            {
                "modified_text": "Tags removed.",
                "changes": [],
                "pronunciation_guide_additions": [],
            },
            {
                "modified_text": "**voice:narrator** Tags restored.",
                "changes": [],
                "pronunciation_guide_additions": [],
            },
        ]
        result = prepare_narration_llm("**voice:narrator** Original.", client)
        assert client.generate_structured.call_count == 2
        assert result["modified_text"] == "**voice:narrator** Tags restored."

    def test_corrupted_tags_after_retry_raises(self):
        client = MagicMock()
        # Both calls return corrupted tags
        client.generate_structured.return_value = {
            "modified_text": "No tags here.",
            "changes": [],
            "pronunciation_guide_additions": [],
        }
        with pytest.raises(NarrationPrepError, match="tags corrupted"):
            prepare_narration_llm("**voice:narrator** Original.", client)

    def test_empty_modified_text_raises(self):
        client = self._make_mock_client(modified_text="")
        with pytest.raises(NarrationPrepError, match="empty"):
            prepare_narration_llm("Some text.", client)

    def test_tags_only_scene_passes_validation(self):
        """Scene with only tags and no prose passes tag validation."""
        tags_only = "**voice:narrator** **mood:calm**"
        client = self._make_mock_client(modified_text=tags_only)
        result = prepare_narration_llm(tags_only, client)
        assert result["modified_text"] == tags_only

    def test_calls_generate_structured_with_tool_schema(self):
        client = self._make_mock_client()
        prepare_narration_llm("Text.", client)
        client.generate_structured.assert_called_once()
        call_kwargs = client.generate_structured.call_args.kwargs
        assert call_kwargs["tool_name"] == _TOOL_NAME
        assert call_kwargs["tool_schema"] == _TOOL_SCHEMA


class TestWriteNarrationChangelog:
    """write_narration_changelog writes JSON to project directory."""

    def test_writes_json_file(self, tmp_path):
        changelog = [
            {
                "scene": 1,
                "original": "Dr. Smith",
                "replacement": "Doctor Smith",
                "reason": "abbreviation",
            }
        ]
        path = write_narration_changelog(changelog, tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["original"] == "Dr. Smith"

    def test_file_name(self, tmp_path):
        path = write_narration_changelog([], tmp_path)
        assert path.name == "narration_prep_changelog.json"

    def test_empty_changelog(self, tmp_path):
        path = write_narration_changelog([], tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []

    def test_multiple_scenes(self, tmp_path):
        changelog = [
            {"scene": 1, "original": "5", "replacement": "five", "reason": "number"},
            {"scene": 2, "original": "Mr.", "replacement": "Mister", "reason": "abbreviation"},
        ]
        path = write_narration_changelog(changelog, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["scene"] == 1
        assert data[1]["scene"] == 2
