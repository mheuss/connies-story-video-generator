"""Tests for story_video.pipeline.narration_prep — LLM-based TTS text preparation."""

import json
from unittest.mock import MagicMock

import pytest


class TestExtractTags:
    """_extract_tags returns all voice/mood tags in order."""

    def test_no_tags(self):
        from story_video.pipeline.narration_prep import _extract_tags

        assert _extract_tags("Plain text with no tags.") == []

    def test_single_voice_tag(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = "**voice:narrator** He spoke softly."
        assert _extract_tags(text) == ["**voice:narrator**"]

    def test_multiple_tags(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = '**voice:old_man** "I\'ve seen worse," **voice:narrator** he muttered.'
        assert _extract_tags(text) == ["**voice:old_man**", "**voice:narrator**"]

    def test_mood_tag(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = "**mood:somber** The rain fell."
        assert _extract_tags(text) == ["**mood:somber**"]

    def test_mixed_voice_and_mood(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = "**voice:jane** **mood:excited** She laughed."
        assert _extract_tags(text) == ["**voice:jane**", "**mood:excited**"]


class TestValidateTagsPreserved:
    """_validate_tags_preserved checks tags match between original and modified."""

    def test_identical_tags_valid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:narrator** Hello."
        modified = "**voice:narrator** Greetings."
        assert _validate_tags_preserved(original, modified) is True

    def test_missing_tag_invalid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:narrator** Hello **voice:bob** world."
        modified = "**voice:narrator** Hello world."
        assert _validate_tags_preserved(original, modified) is False

    def test_reordered_tags_invalid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:a** text **voice:b** more."
        modified = "**voice:b** text **voice:a** more."
        assert _validate_tags_preserved(original, modified) is False

    def test_extra_tag_invalid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:narrator** Hello."
        modified = "**voice:narrator** Hello **mood:sad** world."
        assert _validate_tags_preserved(original, modified) is False

    def test_no_tags_both_sides_valid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        assert _validate_tags_preserved("Plain text.", "Different plain text.") is True


class TestNarrationPrepError:
    """NarrationPrepError is a distinct exception type."""

    def test_is_exception(self):
        from story_video.pipeline.narration_prep import NarrationPrepError

        with pytest.raises(NarrationPrepError, match="scene 1"):
            raise NarrationPrepError("scene 1: tags corrupted")

    def test_subclass_of_exception(self):
        from story_video.pipeline.narration_prep import NarrationPrepError

        assert issubclass(NarrationPrepError, Exception)


class TestBuildUserMessage:
    """_build_user_message constructs the Claude user message."""

    def test_basic_message(self):
        from story_video.pipeline.narration_prep import _build_user_message

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
        from story_video.pipeline.narration_prep import _build_user_message

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
        from story_video.pipeline.narration_prep import _build_user_message

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
        from story_video.pipeline.narration_prep import _SYSTEM_PROMPT

        assert "voice" in _SYSTEM_PROMPT.lower()
        assert "mood" in _SYSTEM_PROMPT.lower()

    def test_tool_schema_has_required_fields(self):
        from story_video.pipeline.narration_prep import _TOOL_SCHEMA

        props = _TOOL_SCHEMA["properties"]
        assert "modified_text" in props
        assert "changes" in props
        assert "pronunciation_guide_additions" in props

    def test_tool_name_is_string(self):
        from story_video.pipeline.narration_prep import _TOOL_NAME

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
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = self._make_mock_client(modified_text="Rewritten text.")
        result = prepare_narration_llm("Original text.", client)
        assert result["modified_text"] == "Rewritten text."

    def test_returns_changes(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        changes = [{"original": "Dr.", "replacement": "Doctor", "reason": "abbreviation"}]
        client = self._make_mock_client(changes=changes)
        result = prepare_narration_llm("Dr. Smith spoke.", client)
        assert result["changes"] == changes

    def test_returns_pronunciation_guide_additions(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        guide = [{"term": "Cthulhu", "pronunciation": "kuh-THOO-loo", "context": "deity name"}]
        client = self._make_mock_client(guide=guide)
        result = prepare_narration_llm("Cthulhu rises.", client)
        assert result["pronunciation_guide_additions"] == guide

    def test_passes_pronunciation_guide_to_prompt(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = self._make_mock_client()
        guide = [{"term": "Nyarlathotep", "pronunciation": "nyar-LATH-oh-tep", "context": "name"}]
        prepare_narration_llm(
            "Plain text.", client, pronunciation_guide=guide, scene_number=2, total_scenes=3
        )

        call_kwargs = client.generate_structured.call_args.kwargs
        assert "Nyarlathotep" in call_kwargs["user_message"]

    def test_preserves_tags_passes(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = self._make_mock_client(modified_text="**voice:narrator** Prepared text.")
        result = prepare_narration_llm("**voice:narrator** Original text.", client)
        assert result["modified_text"] == "**voice:narrator** Prepared text."

    def test_corrupted_tags_retries_once(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

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
        from story_video.pipeline.narration_prep import (
            NarrationPrepError,
            prepare_narration_llm,
        )

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
        from story_video.pipeline.narration_prep import (
            NarrationPrepError,
            prepare_narration_llm,
        )

        client = self._make_mock_client(modified_text="")
        with pytest.raises(NarrationPrepError, match="empty"):
            prepare_narration_llm("Some text.", client)

    def test_calls_generate_structured_with_tool_schema(self):
        from story_video.pipeline.narration_prep import (
            _TOOL_NAME,
            _TOOL_SCHEMA,
            prepare_narration_llm,
        )

        client = self._make_mock_client()
        prepare_narration_llm("Text.", client)
        client.generate_structured.assert_called_once()
        call_kwargs = client.generate_structured.call_args.kwargs
        assert call_kwargs["tool_name"] == _TOOL_NAME
        assert call_kwargs["tool_schema"] == _TOOL_SCHEMA


class TestWriteNarrationChangelog:
    """write_narration_changelog writes JSON to project directory."""

    def test_writes_json_file(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

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
        from story_video.pipeline.narration_prep import write_narration_changelog

        path = write_narration_changelog([], tmp_path)
        assert path.name == "narration_prep_changelog.json"

    def test_empty_changelog(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

        path = write_narration_changelog([], tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []

    def test_multiple_scenes(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

        changelog = [
            {"scene": 1, "original": "5", "replacement": "five", "reason": "number"},
            {"scene": 2, "original": "Mr.", "replacement": "Mister", "reason": "abbreviation"},
        ]
        path = write_narration_changelog(changelog, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["scene"] == 1
        assert data[1]["scene"] == 2
