"""Tests for story_video.pipeline.visual_reference_writer.

TDD: These tests are written first, before the implementation.
"""

import json
from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, InputMode
from story_video.pipeline.visual_reference_writer import (
    ADAPT_SYSTEM,
    CREATIVE_SYSTEM,
    VISUAL_REF_SCHEMA,
    generate_visual_reference,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

STORY_BIBLE_CHARACTERS = {
    "characters": [
        {
            "name": "Iris Chen",
            "role": "protagonist",
            "description": (
                "Seventeen, rail-thin with dark circles under her eyes and "
                "permanently chapped hands. Fiercely intelligent but emotionally "
                "stunted."
            ),
            "arc": "Begins in rigid control, tentatively allows hope, descends into horror.",
        },
        {
            "name": "Uncle Davis",
            "role": "supporting",
            "description": (
                "Early thirties, perpetually rumpled with ink-stained fingers "
                "and a gentle, distracted manner. A former graduate student."
            ),
            "arc": "Starts as stable guardian, begins regressing, forces Iris into caretaker mode.",
        },
    ],
    "setting": {
        "place": "Millbrook, a small Rust Belt town in western Pennsylvania.",
        "time_period": "Near-future, two years after infrastructure collapse.",
        "atmosphere": "Suffocating isolation and creeping wrongness.",
    },
    "premise": "A teenager survives in an isolated town as adults regress.",
    "rules": ["No external rescue", "Regression is irreversible"],
}

ANALYSIS_WITH_CHARACTERS = {
    "craft_notes": {"tone": "Dark and urgent"},
    "thematic_brief": {"themes": ["Survival"]},
    "source_stats": {"word_count": 1000, "scene_count_estimate": 5},
    "characters": [
        {"name": "Sim", "visual_description": "Teenage girl, approximately 15."},
        {"name": "Jake", "visual_description": "Teenage boy, approximately 16."},
    ],
}

CLAUDE_VISUAL_REF_RESPONSE = {
    "characters": [
        {
            "name": "Iris Chen",
            "visual_description": (
                "17-year-old East Asian girl, rail-thin, dark circles under "
                "hollow eyes, permanently chapped red hands."
            ),
        },
        {
            "name": "Uncle Davis",
            "visual_description": (
                "Early-30s white man, rumpled corduroy jacket, ink-stained "
                "fingers, gentle distracted expression."
            ),
        },
    ],
    "setting": {
        "visual_summary": (
            "Small Rust Belt town. Crumbling brick factories, overcast skies, muted colors."
        ),
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client():
    """Create a mock ClaudeClient that returns a visual reference response."""
    client = MagicMock()
    client.generate_structured.return_value = CLAUDE_VISUAL_REF_RESPONSE
    return client


@pytest.fixture()
def creative_state(tmp_path):
    """Create an INSPIRED_BY project with analysis.json and story_bible.json."""
    state = ProjectState.create(
        project_id="vis-ref-test",
        mode=InputMode.INSPIRED_BY,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    analysis_path = state.project_dir / "analysis.json"
    analysis_path.write_text(json.dumps(ANALYSIS_WITH_CHARACTERS, indent=2), encoding="utf-8")
    bible_path = state.project_dir / "story_bible.json"
    bible_path.write_text(json.dumps(STORY_BIBLE_CHARACTERS, indent=2), encoding="utf-8")
    return state


# ---------------------------------------------------------------------------
# Creative mode — reads story_bible.json
# ---------------------------------------------------------------------------


class TestVisualReferenceCreativeMode:
    """Creative modes read story_bible.json for character and setting data."""

    def test_writes_visual_reference_json(self, creative_state, mock_client):
        """visual_reference.json is written to the project directory."""
        generate_visual_reference(creative_state, mock_client)

        ref_path = creative_state.project_dir / "visual_reference.json"
        assert ref_path.exists()
        data = json.loads(ref_path.read_text(encoding="utf-8"))
        assert "characters" in data
        assert "setting" in data
        assert len(data["characters"]) == 2
        assert data["characters"][0]["name"] == "Iris Chen"
        assert "visual_description" in data["characters"][0]

    def test_claude_receives_story_bible_characters(self, creative_state, mock_client):
        """User message sent to Claude includes story bible character descriptions."""
        generate_visual_reference(creative_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Iris Chen" in user_msg
        assert "rail-thin with dark circles" in user_msg
        assert "Uncle Davis" in user_msg
        assert "ink-stained fingers" in user_msg

    def test_claude_receives_story_bible_setting(self, creative_state, mock_client):
        """User message includes setting from story_bible.json."""
        generate_visual_reference(creative_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Millbrook" in user_msg
        assert "Rust Belt" in user_msg

    def test_claude_receives_correct_schema(self, creative_state, mock_client):
        """Claude is called with the visual reference schema."""
        generate_visual_reference(creative_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        assert call_kwargs["tool_name"] == "generate_visual_reference"
        assert call_kwargs["tool_schema"] == VISUAL_REF_SCHEMA

    def test_claude_receives_craft_notes(self, creative_state, mock_client):
        """User message includes craft notes from analysis.json."""
        generate_visual_reference(creative_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Craft Notes" in user_msg
        assert "Dark and urgent" in user_msg

    def test_missing_story_bible_raises(self, tmp_path, mock_client):
        """FileNotFoundError when story_bible.json is missing in creative mode."""
        state = ProjectState.create(
            project_id="no-bible",
            mode=InputMode.ORIGINAL,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        analysis_path = state.project_dir / "analysis.json"
        analysis_path.write_text(json.dumps(ANALYSIS_WITH_CHARACTERS), encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="story_bible.json"):
            generate_visual_reference(state, mock_client)

    def test_uses_creative_system_prompt(self, creative_state, mock_client):
        """Creative mode uses the CREATIVE_SYSTEM prompt, not ADAPT_SYSTEM."""
        generate_visual_reference(creative_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        assert call_kwargs["system"] == CREATIVE_SYSTEM

    def test_missing_analysis_raises(self, tmp_path, mock_client):
        """FileNotFoundError when analysis.json is missing in creative mode."""
        state = ProjectState.create(
            project_id="no-analysis-creative",
            mode=InputMode.ORIGINAL,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        bible_path = state.project_dir / "story_bible.json"
        bible_path.write_text(json.dumps(STORY_BIBLE_CHARACTERS), encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="analysis.json"):
            generate_visual_reference(state, mock_client)

    def test_malformed_story_bible_raises(self, tmp_path, mock_client):
        """ValueError when story_bible.json contains malformed JSON."""
        state = ProjectState.create(
            project_id="bad-bible",
            mode=InputMode.ORIGINAL,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        analysis_path = state.project_dir / "analysis.json"
        analysis_path.write_text(json.dumps(ANALYSIS_WITH_CHARACTERS), encoding="utf-8")
        bible_path = state.project_dir / "story_bible.json"
        bible_path.write_text("{broken json", encoding="utf-8")

        with pytest.raises(ValueError, match="Malformed JSON"):
            generate_visual_reference(state, mock_client)

    def test_state_saved_after_generation(self, creative_state, mock_client):
        """state.save() is called after writing visual_reference.json."""
        generate_visual_reference(creative_state, mock_client)

        reloaded = ProjectState.load(creative_state.project_dir)
        assert reloaded.metadata.project_id == "vis-ref-test"


# ---------------------------------------------------------------------------
# Adapt mode fixtures
# ---------------------------------------------------------------------------

ADAPT_SOURCE_TEXT = "The dark forest loomed ahead. Sim grabbed Jake's hand as they ran."


@pytest.fixture()
def adapt_state(tmp_path):
    """Create an ADAPT project with analysis.json and source_story.txt."""
    state = ProjectState.create(
        project_id="adapt-vis-ref",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    analysis_path = state.project_dir / "analysis.json"
    analysis_path.write_text(json.dumps(ANALYSIS_WITH_CHARACTERS, indent=2), encoding="utf-8")
    source_path = state.project_dir / "source_story.txt"
    source_path.write_text(ADAPT_SOURCE_TEXT, encoding="utf-8")
    return state


# ---------------------------------------------------------------------------
# Adapt mode — reads analysis.json + source material
# ---------------------------------------------------------------------------


class TestVisualReferenceAdaptMode:
    """Adapt mode reads analysis.json for characters and source_story.txt for context."""

    def test_writes_visual_reference_json(self, adapt_state, mock_client):
        """visual_reference.json is written to the project directory."""
        generate_visual_reference(adapt_state, mock_client)

        ref_path = adapt_state.project_dir / "visual_reference.json"
        assert ref_path.exists()

    def test_claude_receives_analysis_characters(self, adapt_state, mock_client):
        """User message includes character names from analysis.json."""
        generate_visual_reference(adapt_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Sim" in user_msg
        assert "Teenage girl" in user_msg
        assert "Jake" in user_msg

    def test_claude_receives_source_material(self, adapt_state, mock_client):
        """User message includes source story text."""
        generate_visual_reference(adapt_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "The dark forest loomed ahead" in user_msg

    def test_uses_adapt_system_prompt(self, adapt_state, mock_client):
        """Claude is called with the ADAPT_SYSTEM prompt, not the creative one."""
        generate_visual_reference(adapt_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        assert call_kwargs["system"] == ADAPT_SYSTEM

    def test_missing_analysis_raises(self, tmp_path, mock_client):
        """FileNotFoundError when analysis.json is missing in adapt mode."""
        state = ProjectState.create(
            project_id="no-analysis",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        with pytest.raises(FileNotFoundError, match="analysis.json"):
            generate_visual_reference(state, mock_client)

    def test_malformed_analysis_raises(self, tmp_path, mock_client):
        """ValueError when analysis.json contains malformed JSON."""
        state = ProjectState.create(
            project_id="bad-analysis",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        analysis_path = state.project_dir / "analysis.json"
        analysis_path.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(ValueError, match="Malformed JSON"):
            generate_visual_reference(state, mock_client)

    def test_missing_source_still_works(self, tmp_path, mock_client):
        """Adapt mode works without source_story.txt, using only analysis characters."""
        state = ProjectState.create(
            project_id="no-source",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        analysis_path = state.project_dir / "analysis.json"
        analysis_path.write_text(json.dumps(ANALYSIS_WITH_CHARACTERS, indent=2), encoding="utf-8")

        generate_visual_reference(state, mock_client)

        ref_path = state.project_dir / "visual_reference.json"
        assert ref_path.exists()
