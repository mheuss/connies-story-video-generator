"""Tests for story_video.pipeline.image_prompt_writer — DALL-E prompt generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the generate_image_prompts function.
"""

import json
import logging
from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, AssetType, InputMode, SceneStatus
from story_video.pipeline.image_prompt_writer import (
    IMAGE_PROMPT_SCHEMA,
    IMAGE_PROMPT_SYSTEM,
    generate_image_prompts,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

PROMPT_RESPONSE = {
    "prompts": [
        {"scene_number": 1, "image_prompt": "A dark forest with towering pines under a stormy sky"},
        {"scene_number": 2, "image_prompt": "A castle on a hill bathed in golden sunset light"},
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client():
    """Create a mock ClaudeClient."""
    client = MagicMock()
    client.generate_structured.return_value = PROMPT_RESPONSE
    return client


@pytest.fixture()
def state_with_scenes(tmp_path):
    """Create a project state with 2 scenes, TEXT asset COMPLETED for both."""
    state = ProjectState.create(
        project_id="prompt-test",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    state.add_scene(1, "The Forest", "The dark forest loomed ahead, its pines swaying.")
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.add_scene(2, "The Castle", "A castle stood on the hill, glowing in sunset light.")
    state.update_scene_asset(2, AssetType.TEXT, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(2, AssetType.TEXT, SceneStatus.COMPLETED)
    return state


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsHappyPath:
    """generate_image_prompts() correctly sets image prompts on scenes."""

    def test_sets_prompts_and_marks_completed(self, state_with_scenes, mock_client):
        """Scenes get image_prompt from Claude response and asset marked COMPLETED."""
        generate_image_prompts(state_with_scenes, mock_client)

        scenes = state_with_scenes.metadata.scenes
        assert scenes[0].image_prompt == "A dark forest with towering pines under a stormy sky"
        assert scenes[1].image_prompt == "A castle on a hill bathed in golden sunset light"
        for scene in scenes:
            assert scene.asset_status.image_prompt == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsStateSaved:
    """generate_image_prompts() persists state via state.save()."""

    def test_state_saved(self, state_with_scenes, mock_client):
        """Reload from disk, verify image prompts persisted."""
        generate_image_prompts(state_with_scenes, mock_client)

        reloaded = ProjectState.load(state_with_scenes.project_dir)
        assert len(reloaded.metadata.scenes) == 2
        assert reloaded.metadata.scenes[0].image_prompt == (
            "A dark forest with towering pines under a stormy sky"
        )
        assert reloaded.metadata.scenes[1].image_prompt == (
            "A castle on a hill bathed in golden sunset light"
        )


# ---------------------------------------------------------------------------
# Claude call parameters
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsClaudeParams:
    """generate_image_prompts() calls Claude with correct params."""

    def test_claude_call_params_and_user_message(self, state_with_scenes, mock_client):
        """System, tool_name, schema, and user message with numbered scenes verified."""
        generate_image_prompts(state_with_scenes, mock_client)

        mock_client.generate_structured.assert_called_once()
        call_kwargs = mock_client.generate_structured.call_args.kwargs

        assert call_kwargs["system"] == IMAGE_PROMPT_SYSTEM
        assert call_kwargs["tool_name"] == "generate_image_prompts"
        assert call_kwargs["tool_schema"] == IMAGE_PROMPT_SCHEMA

        user_msg = call_kwargs["user_message"]
        assert "=== Scene 1: The Forest ===" in user_msg
        assert "=== Scene 2: The Castle ===" in user_msg
        assert "The dark forest loomed ahead" in user_msg
        assert "A castle stood on the hill" in user_msg


# ---------------------------------------------------------------------------
# No scenes raises
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsNoScenes:
    """generate_image_prompts() raises ValueError when no scenes exist."""

    def test_no_scenes_raises(self, tmp_path, mock_client):
        """Empty scenes -> ValueError."""
        state = ProjectState.create(
            project_id="empty-prompts",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        with pytest.raises(ValueError, match="No scenes in project"):
            generate_image_prompts(state, mock_client)


# ---------------------------------------------------------------------------
# Extra scene number in response — skipped with warning
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsMissingScene:
    """generate_image_prompts() skips scene numbers not in state."""

    def test_extra_scene_number_skipped(self, state_with_scenes, mock_client, caplog):
        """Scene 99 in response -> warning logged, valid scenes still updated."""
        mock_client.generate_structured.return_value = {
            "prompts": [
                {"scene_number": 1, "image_prompt": "A dark forest"},
                {"scene_number": 99, "image_prompt": "A phantom scene"},
                {"scene_number": 2, "image_prompt": "A castle on a hill"},
            ]
        }

        with caplog.at_level(logging.WARNING):
            generate_image_prompts(state_with_scenes, mock_client)

        # Warning logged for scene 99
        assert any("99" in record.message for record in caplog.records)

        # Valid scenes still updated
        scenes = state_with_scenes.metadata.scenes
        assert scenes[0].image_prompt == "A dark forest"
        assert scenes[1].image_prompt == "A castle on a hill"


# ---------------------------------------------------------------------------
# Scene not in response — stays None
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsSceneMissingFromResponse:
    """generate_image_prompts() raises ValueError when scenes are missing from response."""

    def test_missing_scene_raises_and_marks_failed(self, state_with_scenes, mock_client):
        """Scene 2 not in response -> ValueError raised, missing scene marked FAILED."""
        mock_client.generate_structured.return_value = {
            "prompts": [
                {"scene_number": 1, "image_prompt": "A dark forest"},
            ]
        }

        with pytest.raises(ValueError, match="Claude did not return prompts for scenes: \\[2\\]"):
            generate_image_prompts(state_with_scenes, mock_client)

        scenes = state_with_scenes.metadata.scenes
        # Scene 1 was processed before the error
        assert scenes[0].image_prompt == "A dark forest"
        assert scenes[0].asset_status.image_prompt == SceneStatus.COMPLETED

        # Scene 2 missing from response — marked FAILED
        assert scenes[1].image_prompt is None
        assert scenes[1].asset_status.image_prompt == SceneStatus.FAILED


# ---------------------------------------------------------------------------
# Character reference from analysis.json
# ---------------------------------------------------------------------------


class TestGenerateImagePromptsCharacterReference:
    """generate_image_prompts() includes character reference from analysis.json."""

    def test_character_reference_in_user_message(self, state_with_scenes, mock_client):
        """Character descriptions from analysis.json are prepended to user message."""
        analysis = {
            "characters": [
                {
                    "name": "Elara",
                    "visual_description": "A tall woman with silver hair and green eyes.",
                },
                {
                    "name": "Borin",
                    "visual_description": "A stocky dwarf with a braided red beard.",
                },
            ]
        }
        analysis_path = state_with_scenes.project_dir / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        generate_image_prompts(state_with_scenes, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "=== Character Reference ===" in user_msg
        assert "Elara: A tall woman with silver hair" in user_msg
        assert "Borin: A stocky dwarf with a braided red beard" in user_msg

    def test_character_reference_before_scenes(self, state_with_scenes, mock_client):
        """Character reference block appears before the first scene."""
        analysis = {
            "characters": [
                {
                    "name": "Elara",
                    "visual_description": "A tall woman with silver hair.",
                },
            ]
        }
        analysis_path = state_with_scenes.project_dir / "analysis.json"
        analysis_path.write_text(json.dumps(analysis), encoding="utf-8")

        generate_image_prompts(state_with_scenes, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        char_pos = user_msg.index("=== Character Reference ===")
        scene_pos = user_msg.index("=== Scene 1:")
        assert char_pos < scene_pos

    @pytest.mark.parametrize(
        "analysis_content",
        [
            None,
            {"characters": []},
            {"craft_notes": {}, "thematic_brief": {}, "source_stats": {}},
        ],
        ids=["no_file", "empty_array", "no_characters_key"],
    )
    def test_no_character_reference_in_message(
        self, state_with_scenes, mock_client, analysis_content
    ):
        """No character block when analysis is absent, empty, or lacks characters key."""
        if analysis_content is not None:
            analysis_path = state_with_scenes.project_dir / "analysis.json"
            analysis_path.write_text(json.dumps(analysis_content), encoding="utf-8")

        generate_image_prompts(state_with_scenes, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Character Reference" not in user_msg
        assert "=== Scene 1:" in user_msg

    def test_malformed_analysis_json_skipped(self, state_with_scenes, mock_client, caplog):
        """Malformed analysis.json is silently skipped with a warning."""
        analysis_path = state_with_scenes.project_dir / "analysis.json"
        analysis_path.write_text("{broken json", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            generate_image_prompts(state_with_scenes, mock_client)

        assert any("Malformed" in r.message for r in caplog.records)
        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Character Reference" not in user_msg
        assert "=== Scene 1:" in user_msg
