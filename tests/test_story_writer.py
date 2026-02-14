"""Tests for story_video.pipeline.story_writer — scene splitting.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the split_scenes function.
"""

from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, InputMode, SceneStatus
from story_video.pipeline.story_writer import (
    SCENE_SPLIT_SCHEMA,
    SCENE_SPLIT_SYSTEM,
    _check_preservation,
    split_scenes,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SOURCE_TEXT = (
    "Part one of the story. It was a dark and stormy night. "
    "Part two of the story. The hero ventured forth bravely. "
    "Part three of the story. And they all lived happily ever after."
)

SCENE_RESPONSES = {
    "scenes": [
        {
            "title": "The Storm",
            "text": "Part one of the story. It was a dark and stormy night.",
        },
        {
            "title": "The Journey",
            "text": "Part two of the story. The hero ventured forth bravely.",
        },
        {
            "title": "The Ending",
            "text": "Part three of the story. And they all lived happily ever after.",
        },
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client():
    """Create a mock ClaudeClient."""
    client = MagicMock()
    client.generate_structured.return_value = SCENE_RESPONSES
    return client


@pytest.fixture()
def sample_state(tmp_path):
    """Create a project state in adapt mode with source_story.txt."""
    state = ProjectState.create(
        project_id="test-project",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    source = tmp_path / "test-project" / "source_story.txt"
    source.write_text(SOURCE_TEXT)
    return state


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestSplitScenesHappyPath:
    """split_scenes() correctly splits a story into scenes."""

    def test_split_scenes_happy_path(self, sample_state, mock_client):
        """Source with known text produces 3 scenes; state has 3 scenes, .md files exist."""
        split_scenes(sample_state, mock_client)

        assert len(sample_state.metadata.scenes) == 3

        scenes_dir = sample_state.project_dir / "scenes"
        assert (scenes_dir / "scene_01.md").exists()
        assert (scenes_dir / "scene_02.md").exists()
        assert (scenes_dir / "scene_03.md").exists()


# ---------------------------------------------------------------------------
# State updates
# ---------------------------------------------------------------------------


class TestSplitScenesStateUpdated:
    """split_scenes() updates project state correctly."""

    def test_split_scenes_state_updated(self, sample_state, mock_client):
        """Verify add_scene() called with correct scene_number, title, prose."""
        split_scenes(sample_state, mock_client)

        scenes = sample_state.metadata.scenes
        assert scenes[0].scene_number == 1
        assert scenes[0].title == "The Storm"
        assert scenes[0].prose == "Part one of the story. It was a dark and stormy night."

        assert scenes[1].scene_number == 2
        assert scenes[1].title == "The Journey"
        assert scenes[1].prose == "Part two of the story. The hero ventured forth bravely."

        assert scenes[2].scene_number == 3
        assert scenes[2].title == "The Ending"
        assert scenes[2].prose == "Part three of the story. And they all lived happily ever after."


# ---------------------------------------------------------------------------
# Asset status
# ---------------------------------------------------------------------------


class TestSplitScenesAssetStatus:
    """split_scenes() sets TEXT asset to COMPLETED for each scene."""

    def test_split_scenes_asset_status_completed(self, sample_state, mock_client):
        """Verify TEXT asset set to COMPLETED for each scene."""
        split_scenes(sample_state, mock_client)

        for scene in sample_state.metadata.scenes:
            assert scene.asset_status.text == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# Markdown files
# ---------------------------------------------------------------------------


class TestSplitScenesMdFilesWritten:
    """split_scenes() writes correctly formatted .md files."""

    def test_split_scenes_md_files_written(self, sample_state, mock_client):
        """Verify scene_01.md, scene_02.md content matches expected format."""
        split_scenes(sample_state, mock_client)

        scenes_dir = sample_state.project_dir / "scenes"

        content_01 = (scenes_dir / "scene_01.md").read_text()
        expected_01 = (
            "# Scene 1: The Storm\n\nPart one of the story. It was a dark and stormy night.\n"
        )
        assert content_01 == expected_01

        content_02 = (scenes_dir / "scene_02.md").read_text()
        expected_02 = (
            "# Scene 2: The Journey\n\nPart two of the story. The hero ventured forth bravely.\n"
        )
        assert content_02 == expected_02

        content_03 = (scenes_dir / "scene_03.md").read_text()
        expected_03 = (
            "# Scene 3: The Ending\n\n"
            "Part three of the story. And they all lived happily ever after.\n"
        )
        assert content_03 == expected_03


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestSplitScenesStateSaved:
    """split_scenes() persists state to project.json."""

    def test_split_scenes_state_saved(self, sample_state, mock_client):
        """Verify state.save() called (check project.json is updated)."""
        split_scenes(sample_state, mock_client)

        # Reload state from disk and verify scenes are persisted
        reloaded = ProjectState.load(sample_state.project_dir)
        assert len(reloaded.metadata.scenes) == 3
        assert reloaded.metadata.scenes[0].title == "The Storm"


# ---------------------------------------------------------------------------
# Preservation check — passing
# ---------------------------------------------------------------------------


class TestSplitScenesPreservationPasses:
    """split_scenes() passes the preservation check when text is preserved."""

    def test_split_scenes_preservation_check_passes(self, sample_state, mock_client):
        """Exact text preserved does not raise."""
        # This is a subset of the happy path — no exception means pass
        split_scenes(sample_state, mock_client)

        # Verify all scenes exist (implicitly proves preservation passed)
        assert len(sample_state.metadata.scenes) == 3


# ---------------------------------------------------------------------------
# Preservation check — failing
# ---------------------------------------------------------------------------


class TestSplitScenesPreservationFails:
    """split_scenes() raises ValueError when text is not preserved."""

    def test_split_scenes_preservation_check_fails(self, sample_state, mock_client):
        """Modified text raises ValueError with mismatch info."""
        mock_client.generate_structured.return_value = {
            "scenes": [
                {"title": "Part One", "text": "Part one of the MODIFIED story."},
                {
                    "title": "Part Two",
                    "text": "Part two of the story. The hero ventured forth bravely.",
                },
                {
                    "title": "Part Three",
                    "text": "Part three of the story. And they all lived happily ever after.",
                },
            ]
        }

        with pytest.raises(ValueError, match="mismatch"):
            split_scenes(sample_state, mock_client)


# ---------------------------------------------------------------------------
# Zero scenes
# ---------------------------------------------------------------------------


class TestSplitScenesZeroScenes:
    """split_scenes() raises ValueError when Claude returns zero scenes."""

    def test_split_scenes_zero_scenes_raises(self, sample_state, mock_client):
        """Empty scenes list raises ValueError."""
        mock_client.generate_structured.return_value = {"scenes": []}

        with pytest.raises(ValueError, match="zero scenes"):
            split_scenes(sample_state, mock_client)


# ---------------------------------------------------------------------------
# Empty scene text
# ---------------------------------------------------------------------------


class TestSplitScenesEmptySceneText:
    """split_scenes() raises ValueError when a scene has blank text."""

    def test_split_scenes_empty_scene_text_raises(self, sample_state, mock_client):
        """Scene with blank text raises ValueError."""
        mock_client.generate_structured.return_value = {
            "scenes": [
                {"title": "Part One", "text": "Part one of the story."},
                {"title": "Empty Scene", "text": "   "},
            ]
        }

        with pytest.raises(ValueError, match="Empty text in scene 2"):
            split_scenes(sample_state, mock_client)


# ---------------------------------------------------------------------------
# Source file missing
# ---------------------------------------------------------------------------


class TestSplitScenesSourceFileMissing:
    """split_scenes() raises FileNotFoundError when source_story.txt is missing."""

    def test_split_scenes_source_file_missing(self, tmp_path, mock_client):
        """No source_story.txt raises FileNotFoundError."""
        state = ProjectState.create(
            project_id="no-source",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        # Do NOT write source_story.txt

        with pytest.raises(FileNotFoundError, match="source_story.txt"):
            split_scenes(state, mock_client)


# ---------------------------------------------------------------------------
# Source file path
# ---------------------------------------------------------------------------


class TestSplitScenesReadsCorrectFile:
    """split_scenes() reads source_story.txt from the correct project directory."""

    def test_split_scenes_reads_source_from_project_dir(self, sample_state, mock_client):
        """Verify correct file path used by checking Claude receives the source text."""
        split_scenes(sample_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        assert call_kwargs["user_message"] == SOURCE_TEXT


# ---------------------------------------------------------------------------
# Claude call parameters
# ---------------------------------------------------------------------------


class TestSplitScenesClaudeParams:
    """split_scenes() calls Claude with correct system prompt, tool name, and schema."""

    def test_split_scenes_calls_claude_with_correct_params(self, sample_state, mock_client):
        """Verify system prompt, tool name, schema passed to generate_structured."""
        split_scenes(sample_state, mock_client)

        mock_client.generate_structured.assert_called_once()
        call_kwargs = mock_client.generate_structured.call_args.kwargs

        assert call_kwargs["system"] == SCENE_SPLIT_SYSTEM
        assert call_kwargs["tool_name"] == "split_into_scenes"
        assert call_kwargs["tool_schema"] == SCENE_SPLIT_SCHEMA


# ---------------------------------------------------------------------------
# Preservation check — whitespace normalization
# ---------------------------------------------------------------------------


class TestPreservationCheckNormalizesWhitespace:
    """_check_preservation() normalizes whitespace before comparison."""

    def test_preservation_check_normalizes_whitespace(self):
        """Extra newlines/spaces between scenes do not cause failure."""
        original = "Word one.  Word two.\n\nWord three.\tWord four."
        scenes = [
            {"title": "A", "text": "Word one. Word two."},
            {"title": "B", "text": "Word three. Word four."},
        ]

        # Should NOT raise — whitespace differences are normalized away
        _check_preservation(original, scenes)

    def test_preservation_check_detects_real_mismatch(self):
        """Actual word differences are detected after normalization."""
        original = "The quick brown fox."
        scenes = [{"title": "A", "text": "The slow brown fox."}]

        with pytest.raises(ValueError, match="mismatch"):
            _check_preservation(original, scenes)
