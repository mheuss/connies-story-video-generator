"""Tests for story_video.pipeline.narration_prep — LLM-based TTS text preparation."""

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
