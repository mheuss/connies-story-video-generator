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
