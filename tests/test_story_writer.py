"""Tests for story_video.pipeline.story_writer — scene splitting and narration flagging.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the split_scenes or flag_narration function.
"""

import json
import logging
from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, AssetType, InputMode, PipelineConfig, SceneStatus
from story_video.pipeline.story_writer import (
    NARRATION_FLAGS_SCHEMA,
    NARRATION_FLAGS_SYSTEM,
    SCENE_SPLIT_SCHEMA,
    SCENE_SPLIT_SYSTEM,
    _check_preservation,
    _load_json_artifact,
    _split_by_scene_tags,
    analyze_source,
    create_outline,
    create_story_bible,
    critique_and_revise,
    flag_narration,
    split_scenes,
    write_scene_prose,
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

SOURCE_TEXT_WITH_HEADER = (
    "---\n"
    "voices:\n"
    "  narrator: alloy\n"
    "  old_man: echo\n"
    "default_voice: narrator\n"
    "---\n"
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
    source.write_text(SOURCE_TEXT, encoding="utf-8")
    return state


@pytest.fixture()
def state_with_header(tmp_path):
    """Create a project state with source_story.txt that has YAML front matter."""
    state = ProjectState.create(
        project_id="header-test",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    source = tmp_path / "header-test" / "source_story.txt"
    source.write_text(SOURCE_TEXT_WITH_HEADER, encoding="utf-8")
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
        assert (scenes_dir / "scene_001.md").exists()
        assert (scenes_dir / "scene_002.md").exists()
        assert (scenes_dir / "scene_003.md").exists()


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
        """Verify scene_001.md, scene_002.md content matches expected format."""
        split_scenes(sample_state, mock_client)

        scenes_dir = sample_state.project_dir / "scenes"

        content_01 = (scenes_dir / "scene_001.md").read_text()
        expected_01 = (
            "# Scene 1: The Storm\n\nPart one of the story. It was a dark and stormy night.\n"
        )
        assert content_01 == expected_01

        content_02 = (scenes_dir / "scene_002.md").read_text()
        expected_02 = (
            "# Scene 2: The Journey\n\nPart two of the story. The hero ventured forth bravely.\n"
        )
        assert content_02 == expected_02

        content_03 = (scenes_dir / "scene_003.md").read_text()
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
# YAML header stripping
# ---------------------------------------------------------------------------


class TestSplitScenesStripsYamlHeader:
    """split_scenes() strips YAML front matter before scene splitting."""

    def test_source_with_header_sends_only_body_to_claude(self, state_with_header, mock_client):
        """YAML header is stripped — Claude receives only the story body."""
        split_scenes(state_with_header, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        user_message = call_kwargs["user_message"]
        assert "---" not in user_message
        assert "voices:" not in user_message
        assert "narrator: alloy" not in user_message
        assert user_message.startswith("Part one of the story")

    def test_source_with_header_preservation_passes(self, state_with_header, mock_client):
        """Preservation check compares against body only, not the YAML header."""
        split_scenes(state_with_header, mock_client)

        assert len(state_with_header.metadata.scenes) == 3

    def test_source_with_header_preservation_fails_on_mismatch(
        self, state_with_header, mock_client
    ):
        """Preservation check still catches mismatches in the body text."""
        mock_client.generate_structured.return_value = {
            "scenes": [
                {"title": "Part One", "text": "WRONG TEXT here."},
            ]
        }

        with pytest.raises(ValueError, match="mismatch"):
            split_scenes(state_with_header, mock_client)


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


class TestPreservationCheckUnicode:
    """_check_preservation() preserves Unicode characters through normalization."""

    def test_accented_characters_preserved(self):
        """Accented characters (e, n, u) survive whitespace normalization."""
        text = "Caf\u00e9 r\u00e9sum\u00e9 \u2014 she whispered, \u201cBuenas noches.\u201d"
        scenes = [{"title": "A", "text": text}]
        _check_preservation(text, scenes)

    def test_unicode_punctuation_preserved(self):
        """Em dashes, curly quotes, and ellipsis survive normalization."""
        text = (
            "He paused\u2026 then said, \u201cIt\u2019s over.\u201d She\u2014stunned\u2014nodded."
        )
        scenes = [{"title": "A", "text": text}]
        _check_preservation(text, scenes)


# ---------------------------------------------------------------------------
# Marker-based scene splitting — test data
# ---------------------------------------------------------------------------

SOURCE_WITH_SCENE_TAGS = (
    "**scene:The Storm**\n"
    "Part one of the story. It was a dark and stormy night.\n\n"
    "**scene:The Journey**\n"
    "Part two of the story. The hero ventured forth bravely.\n\n"
    "**scene:The Ending**\n"
    "Part three of the story. And they all lived happily ever after."
)

SOURCE_WITH_OPENING_BEFORE_FIRST_TAG = (
    "Once upon a time, in a land far away.\n\n"
    "**scene:The Storm**\n"
    "Part one of the story. It was a dark and stormy night.\n\n"
    "**scene:The Journey**\n"
    "Part two of the story. The hero ventured forth bravely."
)


# ---------------------------------------------------------------------------
# _split_by_scene_tags — no tags (returns None)
# ---------------------------------------------------------------------------


class TestSplitBySceneTagsNoTags:
    """_split_by_scene_tags returns None when no scene tags present."""

    def test_no_tags_returns_none(self):
        result = _split_by_scene_tags("Just a plain story with no tags.")
        assert result is None

    def test_bold_text_not_confused_with_scene_tag(self):
        result = _split_by_scene_tags("**bold text** and more text.")
        assert result is None


# ---------------------------------------------------------------------------
# _split_by_scene_tags — basic splitting
# ---------------------------------------------------------------------------


class TestSplitBySceneTagsBasic:
    """_split_by_scene_tags splits text on scene tags."""

    def test_three_scenes(self):
        result = _split_by_scene_tags(SOURCE_WITH_SCENE_TAGS)
        assert result is not None
        assert len(result) == 3

    def test_scene_titles_extracted(self):
        result = _split_by_scene_tags(SOURCE_WITH_SCENE_TAGS)
        assert result[0]["title"] == "The Storm"
        assert result[1]["title"] == "The Journey"
        assert result[2]["title"] == "The Ending"

    def test_scene_text_extracted(self):
        result = _split_by_scene_tags(SOURCE_WITH_SCENE_TAGS)
        assert result[0]["text"] == "Part one of the story. It was a dark and stormy night."
        assert result[1]["text"] == "Part two of the story. The hero ventured forth bravely."
        assert (
            result[2]["text"] == "Part three of the story. And they all lived happily ever after."
        )


# ---------------------------------------------------------------------------
# _split_by_scene_tags — text before first tag
# ---------------------------------------------------------------------------


class TestSplitBySceneTagsOpeningText:
    """_split_by_scene_tags handles text before the first scene tag."""

    def test_opening_text_becomes_opening_scene(self):
        result = _split_by_scene_tags(SOURCE_WITH_OPENING_BEFORE_FIRST_TAG)
        assert result is not None
        assert len(result) == 3

    def test_opening_scene_title(self):
        result = _split_by_scene_tags(SOURCE_WITH_OPENING_BEFORE_FIRST_TAG)
        assert result[0]["title"] == "Opening"

    def test_opening_scene_text(self):
        result = _split_by_scene_tags(SOURCE_WITH_OPENING_BEFORE_FIRST_TAG)
        assert result[0]["text"] == "Once upon a time, in a land far away."


# ---------------------------------------------------------------------------
# _split_by_scene_tags — whitespace-only before first tag
# ---------------------------------------------------------------------------


class TestSplitBySceneTagsWhitespaceOpening:
    """_split_by_scene_tags ignores whitespace-only text before first tag."""

    def test_whitespace_before_first_tag_ignored(self):
        text = "\n\n  \n**scene:First** Content here."
        result = _split_by_scene_tags(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "First"


# ---------------------------------------------------------------------------
# _split_by_scene_tags — empty scene text raises
# ---------------------------------------------------------------------------


class TestSplitBySceneTagsEmptyText:
    """_split_by_scene_tags raises ValueError for empty scene text."""

    def test_empty_scene_text_raises(self):
        text = "**scene:First**\nSome text.\n**scene:Second**\n  \n"
        with pytest.raises(ValueError, match="Empty text"):
            _split_by_scene_tags(text)


# ---------------------------------------------------------------------------
# _split_by_scene_tags — title whitespace stripped
# ---------------------------------------------------------------------------


class TestSplitBySceneTagsTitleStrip:
    """_split_by_scene_tags strips whitespace from titles."""

    def test_title_whitespace_stripped(self):
        text = "**scene:  The Storm  **\nContent here."
        result = _split_by_scene_tags(text)
        assert result[0]["title"] == "The Storm"


# ---------------------------------------------------------------------------
# split_scenes with scene tags — skips Claude
# ---------------------------------------------------------------------------


class TestSplitScenesWithSceneTags:
    """split_scenes() skips Claude call when scene tags present."""

    def test_claude_not_called(self, tmp_path, mock_client):
        state = ProjectState.create(
            project_id="tagged-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "tagged-project" / "source_story.txt"
        source.write_text(SOURCE_WITH_SCENE_TAGS, encoding="utf-8")

        split_scenes(state, mock_client)

        mock_client.generate_structured.assert_not_called()

    def test_scenes_created_from_tags(self, tmp_path, mock_client):
        state = ProjectState.create(
            project_id="tagged-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "tagged-project" / "source_story.txt"
        source.write_text(SOURCE_WITH_SCENE_TAGS, encoding="utf-8")

        split_scenes(state, mock_client)

        assert len(state.metadata.scenes) == 3
        assert state.metadata.scenes[0].title == "The Storm"
        assert state.metadata.scenes[1].title == "The Journey"
        assert state.metadata.scenes[2].title == "The Ending"

    def test_md_files_written(self, tmp_path, mock_client):
        state = ProjectState.create(
            project_id="tagged-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "tagged-project" / "source_story.txt"
        source.write_text(SOURCE_WITH_SCENE_TAGS, encoding="utf-8")

        split_scenes(state, mock_client)

        scenes_dir = state.project_dir / "scenes"
        assert (scenes_dir / "scene_001.md").exists()
        assert (scenes_dir / "scene_002.md").exists()
        assert (scenes_dir / "scene_003.md").exists()

    def test_scene_tags_with_yaml_header(self, tmp_path, mock_client):
        """Scene tags work with YAML front matter — header stripped first."""
        state = ProjectState.create(
            project_id="tagged-header",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "tagged-header" / "source_story.txt"
        source.write_text(
            "---\nvoices:\n  narrator: alloy\n---\n" + SOURCE_WITH_SCENE_TAGS,
            encoding="utf-8",
        )

        split_scenes(state, mock_client)

        mock_client.generate_structured.assert_not_called()
        assert len(state.metadata.scenes) == 3

    def test_logs_marker_splitting(self, tmp_path, mock_client, caplog):
        """Logs info message when using marker-based splitting."""
        state = ProjectState.create(
            project_id="tagged-log",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "tagged-log" / "source_story.txt"
        source.write_text(SOURCE_WITH_SCENE_TAGS, encoding="utf-8")

        with caplog.at_level(logging.INFO):
            split_scenes(state, mock_client)

        assert any("scene tag" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Narration flagging — test data
# ---------------------------------------------------------------------------

SAMPLE_FLAGS_RESPONSE = {
    "flags": [
        {
            "scene_number": 1,
            "location": "paragraph 1, sentence 2",
            "category": "footnote",
            "original_text": "as noted in [1]",
            "suggested_fix": "as noted in the first reference",
            "severity": "must_fix",
        },
        {
            "scene_number": 2,
            "location": "paragraph 2, sentence 1",
            "category": "typography",
            "original_text": "he paused... ... ... then spoke",
            "suggested_fix": "he paused, then spoke",
            "severity": "should_fix",
        },
    ]
}

ZERO_FLAGS_RESPONSE = {"flags": []}


# ---------------------------------------------------------------------------
# Narration flagging — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def flagging_client():
    """Create a mock ClaudeClient for narration flagging."""
    client = MagicMock()
    client.generate_structured.return_value = SAMPLE_FLAGS_RESPONSE
    return client


@pytest.fixture()
def state_with_scenes(tmp_path):
    """Create a project state with pre-populated scenes."""
    state = ProjectState.create(
        project_id="flag-test",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    state.add_scene(1, "The Storm", "The storm raged as noted in [1] and the wind howled.")
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.add_scene(
        2,
        "The Journey",
        "The hero set out. he paused... ... ... then spoke to no one.",
    )
    state.update_scene_asset(2, AssetType.TEXT, SceneStatus.COMPLETED)
    state.add_scene(3, "The Ending", "They all lived happily ever after.")
    state.update_scene_asset(3, AssetType.TEXT, SceneStatus.COMPLETED)
    return state


@pytest.fixture()
def autonomous_state(tmp_path):
    """Create a project state in autonomous mode with pre-populated scenes."""
    config = AppConfig(pipeline=PipelineConfig(autonomous=True))
    state = ProjectState.create(
        project_id="auto-flag-test",
        mode=InputMode.ADAPT,
        config=config,
        output_dir=tmp_path,
    )
    state.add_scene(1, "The Storm", "The storm raged as noted in [1] and the wind howled.")
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.add_scene(
        2,
        "The Journey",
        "The hero set out. he paused... ... ... then spoke to no one.",
    )
    state.update_scene_asset(2, AssetType.TEXT, SceneStatus.COMPLETED)
    return state


# ---------------------------------------------------------------------------
# Narration flagging — happy path with flags
# ---------------------------------------------------------------------------


class TestFlagNarrationHappyPathWithFlags:
    """flag_narration() writes a flags file when issues are found."""

    def test_flag_narration_happy_path_with_flags(self, state_with_scenes, flagging_client):
        """Flags returned -> flags file written with content."""
        flag_narration(state_with_scenes, flagging_client)

        flags_file = state_with_scenes.project_dir / "narration_flags.md"
        assert flags_file.exists()
        content = flags_file.read_text()
        assert "# Narration Flags" in content
        assert "footnote" in content
        assert "as noted in [1]" in content


# ---------------------------------------------------------------------------
# Narration flagging — zero flags
# ---------------------------------------------------------------------------


class TestFlagNarrationZeroFlags:
    """flag_narration() writes 'no issues' message when no flags found."""

    def test_flag_narration_zero_flags(self, state_with_scenes, flagging_client):
        """No issues -> 'no issues found' written."""
        flagging_client.generate_structured.return_value = ZERO_FLAGS_RESPONSE

        flag_narration(state_with_scenes, flagging_client)

        flags_file = state_with_scenes.project_dir / "narration_flags.md"
        content = flags_file.read_text()
        assert (
            content == "# Narration Flags\n\nNo TTS issues found. All scenes are narration-ready.\n"
        )


# ---------------------------------------------------------------------------
# Narration flagging — no scenes raises
# ---------------------------------------------------------------------------


class TestFlagNarrationNoScenesRaises:
    """flag_narration() raises ValueError when no scenes exist."""

    def test_flag_narration_no_scenes_raises(self, tmp_path, flagging_client):
        """Empty scenes list -> ValueError."""
        state = ProjectState.create(
            project_id="empty-scenes",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        with pytest.raises(ValueError, match="No scenes in project"):
            flag_narration(state, flagging_client)


# ---------------------------------------------------------------------------
# Narration flagging — user message format
# ---------------------------------------------------------------------------


class TestFlagNarrationBuildsUserMessage:
    """flag_narration() builds correctly formatted user message with numbered scenes."""

    def test_flag_narration_builds_user_message_correctly(self, state_with_scenes, flagging_client):
        """Verify numbered scene format sent to Claude."""
        flag_narration(state_with_scenes, flagging_client)

        call_kwargs = flagging_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]

        assert "=== Scene 1: The Storm ===" in user_msg
        assert "=== Scene 2: The Journey ===" in user_msg
        assert "=== Scene 3: The Ending ===" in user_msg
        assert "The storm raged" in user_msg
        assert "They all lived happily ever after." in user_msg


# ---------------------------------------------------------------------------
# Narration flagging — voice/mood tags stripped for Claude
# ---------------------------------------------------------------------------


class TestFlagNarrationStripsVoiceTags:
    """flag_narration() strips voice/mood tags before sending to Claude."""

    def test_voice_tags_not_sent_to_claude(self, tmp_path, flagging_client):
        """Voice/mood tags are stripped from the user message sent to Claude."""
        config = AppConfig(pipeline=PipelineConfig(autonomous=True))
        state = ProjectState.create(
            project_id="tag-strip-test",
            mode=InputMode.ADAPT,
            config=config,
            output_dir=tmp_path,
        )
        state.add_scene(
            1,
            "Tagged Scene",
            "**voice:narrator** The hero spoke."
            ' **voice:villain** **mood:angry** "Never!" he cried.',
        )
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        flag_narration(state, flagging_client)

        call_kwargs = flagging_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "**voice:" not in user_msg
        assert "**mood:" not in user_msg
        assert "The hero spoke." in user_msg
        assert '"Never!" he cried.' in user_msg

    def test_autonomous_fix_preserves_voice_tags(self, tmp_path):
        """Autonomous fixes are applied without stripping voice/mood tags."""
        config = AppConfig(pipeline=PipelineConfig(autonomous=True))
        state = ProjectState.create(
            project_id="tag-preserve-test",
            mode=InputMode.ADAPT,
            config=config,
            output_dir=tmp_path,
        )
        state.add_scene(
            1,
            "Tagged Scene",
            '**voice:narrator** The storm raged as noted in [1]. **voice:old_man** "Run!" he said.',
        )
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        client = MagicMock()
        client.generate_structured.return_value = {
            "flags": [
                {
                    "scene_number": 1,
                    "location": "paragraph 1",
                    "category": "footnote",
                    "original_text": "as noted in [1]",
                    "suggested_fix": "as noted in the first reference",
                    "severity": "must_fix",
                }
            ]
        }

        flag_narration(state, client)

        scene = state.metadata.scenes[0]
        # Fix applied
        assert "as noted in the first reference" in scene.narration_text
        # Voice tags preserved
        assert "**voice:narrator**" in scene.narration_text
        assert "**voice:old_man**" in scene.narration_text


# ---------------------------------------------------------------------------
# Narration flagging — Claude call parameters
# ---------------------------------------------------------------------------


class TestFlagNarrationClaudeParams:
    """flag_narration() calls Claude with correct system prompt, tool name, and schema."""

    def test_flag_narration_calls_claude_with_correct_params(
        self, state_with_scenes, flagging_client
    ):
        """Verify system prompt, tool name, schema passed to generate_structured."""
        flag_narration(state_with_scenes, flagging_client)

        flagging_client.generate_structured.assert_called_once()
        call_kwargs = flagging_client.generate_structured.call_args.kwargs

        assert call_kwargs["system"] == NARRATION_FLAGS_SYSTEM
        assert call_kwargs["tool_name"] == "flag_narration_issues"
        assert call_kwargs["tool_schema"] == NARRATION_FLAGS_SCHEMA


# ---------------------------------------------------------------------------
# Narration flagging — autonomous applies fixes
# ---------------------------------------------------------------------------


class TestFlagNarrationAutonomousAppliesFixes:
    """flag_narration() in autonomous mode applies suggested fixes to narration_text."""

    def test_flag_narration_autonomous_applies_fixes(self, autonomous_state, flagging_client):
        """autonomous=True -> narration_text updated with fix."""
        flag_narration(autonomous_state, flagging_client)

        scene1 = autonomous_state.metadata.scenes[0]
        assert scene1.narration_text is not None
        assert "as noted in the first reference" in scene1.narration_text
        assert "as noted in [1]" not in scene1.narration_text


# ---------------------------------------------------------------------------
# Narration flagging — autonomous copies prose first
# ---------------------------------------------------------------------------


class TestFlagNarrationAutonomousCopiesProseFirst:
    """flag_narration() copies prose to narration_text before applying fix."""

    def test_flag_narration_autonomous_copies_prose_first(self, autonomous_state, flagging_client):
        """narration_text is None -> copies from prose, then applies fix."""
        # Confirm narration_text starts as None
        scene1 = autonomous_state.metadata.scenes[0]
        assert scene1.narration_text is None

        flag_narration(autonomous_state, flagging_client)

        scene1 = autonomous_state.metadata.scenes[0]
        # Should contain the rest of the prose with the fix applied
        assert "The storm raged" in scene1.narration_text
        assert "and the wind howled" in scene1.narration_text


# ---------------------------------------------------------------------------
# Narration flagging — autonomous preserves existing narration_text
# ---------------------------------------------------------------------------


class TestFlagNarrationAutonomousPreservesExistingNarrationText:
    """flag_narration() applies fix to existing narration_text, not prose."""

    def test_flag_narration_autonomous_preserves_existing_narration_text(
        self, autonomous_state, flagging_client
    ):
        """If narration_text already set, applies fix to it (not prose)."""
        # Set narration_text to something different from prose
        scene1 = autonomous_state.metadata.scenes[0]
        scene1.narration_text = "The storm raged, as noted in [1], and the wind howled fiercely."

        flag_narration(autonomous_state, flagging_client)

        scene1 = autonomous_state.metadata.scenes[0]
        # Fix applied to narration_text, not prose
        assert "as noted in the first reference" in scene1.narration_text
        # Should keep the modified ending from the existing narration_text
        assert "fiercely" in scene1.narration_text


# ---------------------------------------------------------------------------
# Narration flagging — semi-auto no fixes
# ---------------------------------------------------------------------------


class TestFlagNarrationSemiAutoNoFixes:
    """flag_narration() in semi-auto mode writes flags but doesn't apply fixes."""

    def test_flag_narration_semi_auto_no_fixes(self, state_with_scenes, flagging_client):
        """autonomous=False -> narration_text unchanged (None)."""
        flag_narration(state_with_scenes, flagging_client)

        for scene in state_with_scenes.metadata.scenes:
            assert scene.narration_text is None


# ---------------------------------------------------------------------------
# Narration flagging — invalid scene number skipped
# ---------------------------------------------------------------------------


class TestFlagNarrationInvalidSceneNumberSkipped:
    """flag_narration() skips flags with invalid scene numbers."""

    def test_flag_narration_invalid_scene_number_skipped(
        self, autonomous_state, flagging_client, caplog
    ):
        """Flag with scene_number=99 -> skipped, no crash."""
        flagging_client.generate_structured.return_value = {
            "flags": [
                {
                    "scene_number": 99,
                    "location": "paragraph 1, sentence 1",
                    "category": "footnote",
                    "original_text": "see [1]",
                    "suggested_fix": "see the reference",
                    "severity": "must_fix",
                }
            ]
        }

        with caplog.at_level(logging.WARNING):
            flag_narration(autonomous_state, flagging_client)

        # No crash; warning logged
        assert any("99" in record.message for record in caplog.records)

        # narration_text untouched since the only flag was invalid
        for scene in autonomous_state.metadata.scenes:
            assert scene.narration_text is None


class TestFlagNarrationAutonomousFixNotFound:
    """flag_narration() logs warning when original_text not found in narration_text."""

    def test_original_text_not_found_logs_warning(self, tmp_path, caplog):
        """When original_text doesn't match narration_text, warning is logged and text unchanged."""
        config = AppConfig(pipeline=PipelineConfig(autonomous=True))
        state = ProjectState.create(
            project_id="fix-not-found-test",
            mode=InputMode.ADAPT,
            config=config,
            output_dir=tmp_path,
        )

        client = MagicMock()
        client.generate_structured.return_value = {
            "flags": [
                {
                    "scene_number": 1,
                    "category": "abbreviation",
                    "location": "paragraph 1",
                    "severity": "must_fix",
                    "original_text": "text that does not exist in scene",
                    "suggested_fix": "replacement text",
                }
            ]
        }

        state.add_scene(1, "Test Scene", "The actual scene prose.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]
        scene.narration_text = "The actual scene narration text."
        original_narration = scene.narration_text

        with caplog.at_level(logging.WARNING):
            flag_narration(state, client)

        assert any("not found" in r.message.lower() for r in caplog.records)
        assert scene.narration_text == original_narration


# ---------------------------------------------------------------------------
# Narration flagging — flags file format
# ---------------------------------------------------------------------------


class TestFlagNarrationFlagsFileFormat:
    """flag_narration() writes flags file with correct format."""

    def test_flag_narration_flags_file_format(self, state_with_scenes, flagging_client):
        """Verify flags file contains scene number, category, original, fix."""
        flag_narration(state_with_scenes, flagging_client)

        flags_file = state_with_scenes.project_dir / "narration_flags.md"
        content = flags_file.read_text()

        # Check format elements for first flag
        assert "## Scene 1: footnote" in content
        assert "**Location:** paragraph 1, sentence 2" in content
        assert "**Severity:** must_fix" in content
        assert "**Original:** as noted in [1]" in content
        assert "**Suggested fix:** as noted in the first reference" in content

        # Check format elements for second flag
        assert "## Scene 2: typography" in content
        assert "**Severity:** should_fix" in content

        # Check separator
        assert "---" in content


# ---------------------------------------------------------------------------
# Narration flagging — state saved
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Narration flagging — multiple flags same scene
# ---------------------------------------------------------------------------


class TestFlagNarrationMultipleFlagsSameScene:
    """flag_narration() applies multiple fixes to the same scene sequentially."""

    def test_flag_narration_multiple_flags_same_scene(self, autonomous_state, flagging_client):
        """Multiple fixes applied to same scene sequentially."""
        flagging_client.generate_structured.return_value = {
            "flags": [
                {
                    "scene_number": 1,
                    "location": "paragraph 1, sentence 1",
                    "category": "footnote",
                    "original_text": "as noted in [1]",
                    "suggested_fix": "as noted in the first reference",
                    "severity": "must_fix",
                },
                {
                    "scene_number": 1,
                    "location": "paragraph 1, sentence 1",
                    "category": "typography",
                    "original_text": "the wind howled",
                    "suggested_fix": "the wind roared",
                    "severity": "should_fix",
                },
            ]
        }

        flag_narration(autonomous_state, flagging_client)

        scene1 = autonomous_state.metadata.scenes[0]
        assert scene1.narration_text is not None
        # Both fixes applied
        assert "as noted in the first reference" in scene1.narration_text
        assert "the wind roared" in scene1.narration_text
        # Originals replaced
        assert "as noted in [1]" not in scene1.narration_text
        assert "the wind howled" not in scene1.narration_text


# ---------------------------------------------------------------------------
# Narration flagging — NARRATION_TEXT asset status updates
# ---------------------------------------------------------------------------


class TestFlagNarrationUpdatesNarrationTextStatus:
    """flag_narration() updates NARRATION_TEXT asset status."""

    def test_autonomous_marks_narration_text_completed(self, autonomous_state, flagging_client):
        """In autonomous mode, NARRATION_TEXT status is COMPLETED for flagged scenes."""
        flag_narration(autonomous_state, flagging_client)

        for scene in autonomous_state.metadata.scenes:
            assert scene.asset_status.narration_text == SceneStatus.COMPLETED

    def test_semi_auto_marks_narration_text_completed(self, state_with_scenes, flagging_client):
        """In semi-auto mode, NARRATION_TEXT status is also COMPLETED."""
        flag_narration(state_with_scenes, flagging_client)

        for scene in state_with_scenes.metadata.scenes:
            assert scene.asset_status.narration_text == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# Preservation check — edge cases
# ---------------------------------------------------------------------------


class TestCheckPreservationEdgeCases:
    """_check_preservation handles edge-case inputs."""

    def test_empty_original_and_scenes(self):
        """Empty original text with no scenes passes."""
        _check_preservation("", [])

    def test_whitespace_only_original(self):
        """Whitespace-only original with no scenes passes."""
        _check_preservation("   \n\t  ", [])


# ---------------------------------------------------------------------------
# Analysis phase — test data
# ---------------------------------------------------------------------------

ANALYSIS_RESPONSE = {
    "craft_notes": {
        "sentence_structure": "Short declarative sentences.",
        "vocabulary": "Simple, concrete nouns.",
        "tone": "Dry, understated.",
        "pacing": "Slow openings.",
        "narrative_voice": "Third person limited, past tense.",
    },
    "thematic_brief": {
        "themes": ["isolation", "duty"],
        "emotional_arc": "Resignation to acceptance",
        "central_tension": "Bound to a place",
        "mood": "Melancholic",
    },
    "source_stats": {
        "word_count": 90,
        "scene_count_estimate": 3,
    },
    "characters": [
        {
            "name": "The Keeper",
            "visual_description": (
                "A weathered man in his sixties with grey stubble"
                " and deep-set eyes. Wears a faded navy peacoat."
            ),
        },
    ],
}


# ---------------------------------------------------------------------------
# Analysis phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def analysis_client():
    """Mock ClaudeClient for analysis phase."""
    client = MagicMock()
    client.generate_structured.return_value = ANALYSIS_RESPONSE
    return client


@pytest.fixture()
def inspired_state(tmp_path):
    """Create a project state in inspired_by mode with source_story.txt."""
    state = ProjectState.create(
        project_id="inspired-test",
        mode=InputMode.INSPIRED_BY,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    source = tmp_path / "inspired-test" / "source_story.txt"
    source.write_text(SOURCE_TEXT, encoding="utf-8")
    return state


@pytest.fixture()
def original_state(tmp_path):
    """Create a project state in original mode with a creative brief."""
    state = ProjectState.create(
        project_id="original-test",
        mode=InputMode.ORIGINAL,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    brief = tmp_path / "original-test" / "source_story.txt"
    brief.write_text("A story about love and sacrifice between a married couple.", encoding="utf-8")
    return state


# ---------------------------------------------------------------------------
# Analysis phase — tests
# ---------------------------------------------------------------------------


class TestAnalyzeSourceCallsClaude:
    """analyze_source() sends source material to Claude."""

    def test_source_text_in_user_message(self, inspired_state, analysis_client):
        """Source material is included in the user message to Claude."""
        analyze_source(inspired_state, analysis_client)

        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert SOURCE_TEXT in call_kwargs["user_message"]


class TestAnalyzeSourceStripsYamlHeader:
    """analyze_source() strips YAML front matter before sending to Claude."""

    def test_header_stripped_from_user_message(self, tmp_path, analysis_client):
        """YAML front matter is stripped — Claude receives only the story body."""
        state = ProjectState.create(
            project_id="header-analysis-test",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "header-analysis-test" / "source_story.txt"
        source.write_text(SOURCE_TEXT_WITH_HEADER, encoding="utf-8")

        analyze_source(state, analysis_client)

        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        user_message = call_kwargs["user_message"]
        assert "---" not in user_message
        assert "voices:" not in user_message
        assert "narrator: alloy" not in user_message
        assert user_message.startswith("Part one of the story")


class TestAnalyzeSourceWritesJson:
    """analyze_source() writes analysis.json to project directory."""

    def test_analysis_json_written(self, inspired_state, analysis_client):
        """analysis.json exists after call and contains expected keys."""
        analyze_source(inspired_state, analysis_client)

        analysis_path = inspired_state.project_dir / "analysis.json"
        assert analysis_path.exists()
        data = json.loads(analysis_path.read_text())
        assert "craft_notes" in data
        assert "thematic_brief" in data
        assert "source_stats" in data
        assert "word_count" in data["source_stats"]
        assert "scene_count_estimate" in data["source_stats"]


class TestAnalyzeSourceCraftNotes:
    """analyze_source() stores craft notes with all required fields."""

    def test_craft_notes_fields(self, inspired_state, analysis_client):
        """Craft notes contain sentence_structure, vocabulary, tone, pacing, narrative_voice."""
        analyze_source(inspired_state, analysis_client)

        data = json.loads((inspired_state.project_dir / "analysis.json").read_text())
        craft = data["craft_notes"]
        assert "sentence_structure" in craft
        assert "vocabulary" in craft
        assert "tone" in craft
        assert "pacing" in craft
        assert "narrative_voice" in craft


class TestAnalyzeSourceThematicBrief:
    """analyze_source() stores thematic brief with all required fields."""

    def test_thematic_brief_fields(self, inspired_state, analysis_client):
        """Thematic brief contains themes, emotional_arc, central_tension, mood."""
        analyze_source(inspired_state, analysis_client)

        data = json.loads((inspired_state.project_dir / "analysis.json").read_text())
        brief = data["thematic_brief"]
        assert "themes" in brief
        assert "emotional_arc" in brief
        assert "central_tension" in brief
        assert "mood" in brief


class TestAnalyzeSourceMissingFile:
    """analyze_source() raises FileNotFoundError when source_story.txt is missing."""

    def test_missing_source_raises(self, tmp_path, analysis_client):
        """No source_story.txt raises FileNotFoundError."""
        state = ProjectState.create(
            project_id="no-source",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        with pytest.raises(FileNotFoundError, match="source_story.txt"):
            analyze_source(state, analysis_client)


class TestAnalyzeSourceCharacters:
    """analyze_source() stores character descriptions."""

    def test_characters_present_in_analysis(self, inspired_state, analysis_client):
        """analysis.json contains characters array."""
        analyze_source(inspired_state, analysis_client)

        data = json.loads((inspired_state.project_dir / "analysis.json").read_text())
        assert "characters" in data
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "The Keeper"
        assert "visual_description" in data["characters"][0]


class TestAnalyzeSourceOriginalMode:
    """analyze_source() in ORIGINAL mode interprets a creative brief."""

    def test_uses_brief_analysis_prompt(self, original_state, analysis_client):
        """ORIGINAL mode uses BRIEF_ANALYSIS_SYSTEM, not ANALYSIS_SYSTEM."""
        analyze_source(original_state, analysis_client)
        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert "creative brief" in call_kwargs["system"].lower()

    def test_brief_text_in_user_message(self, original_state, analysis_client):
        """Brief content is included in user message."""
        analyze_source(original_state, analysis_client)
        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert "love and sacrifice" in call_kwargs["user_message"]

    def test_source_stats_from_config(self, original_state, analysis_client):
        """source_stats are computed from config, not from Claude response."""
        analyze_source(original_state, analysis_client)
        analysis_path = original_state.project_dir / "analysis.json"
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        # Default config: target_duration_minutes=30, words_per_minute=150
        # -> word_count = 30 * 150 = 4500
        assert analysis["source_stats"]["word_count"] == 4500

    def test_scene_count_from_word_count(self, original_state, analysis_client):
        """scene_count_estimate derived from word_count / WORDS_PER_SCENE_ESTIMATE."""
        analyze_source(original_state, analysis_client)
        analysis_path = original_state.project_dir / "analysis.json"
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        # 4500 / 600 = 7
        assert analysis["source_stats"]["scene_count_estimate"] == 7


@pytest.fixture()
def adapt_state(tmp_path):
    """Create a project state in adapt mode with source_story.txt."""
    state = ProjectState.create(
        project_id="adapt-test",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    source = tmp_path / "adapt-test" / "source_story.txt"
    source.write_text(SOURCE_TEXT, encoding="utf-8")
    return state


class TestAnalyzeSourceAdaptMode:
    """analyze_source() in ADAPT mode extracts characters from existing story."""

    def test_uses_adapt_analysis_prompt(self, adapt_state, analysis_client):
        """ADAPT mode uses ADAPT_ANALYSIS_SYSTEM."""
        analyze_source(adapt_state, analysis_client)
        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert "adapting" in call_kwargs["system"].lower() or (
            "adaptation" in call_kwargs["system"].lower()
        )

    def test_source_text_in_user_message(self, adapt_state, analysis_client):
        """Source story text is included in user message."""
        analyze_source(adapt_state, analysis_client)
        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert SOURCE_TEXT in call_kwargs["user_message"]

    def test_characters_in_analysis_json(self, adapt_state, analysis_client):
        """analysis.json contains characters for adapt mode."""
        analyze_source(adapt_state, analysis_client)
        data = json.loads((adapt_state.project_dir / "analysis.json").read_text())
        assert "characters" in data

    def test_strips_yaml_header(self, tmp_path, analysis_client):
        """YAML front matter is stripped in adapt mode."""
        state = ProjectState.create(
            project_id="adapt-header-test",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "adapt-header-test" / "source_story.txt"
        source.write_text(SOURCE_TEXT_WITH_HEADER, encoding="utf-8")

        analyze_source(state, analysis_client)

        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert "---" not in call_kwargs["user_message"]
        assert call_kwargs["user_message"].startswith("Part one")


# ---------------------------------------------------------------------------
# Story bible phase — test data
# ---------------------------------------------------------------------------

BIBLE_RESPONSE = {
    "characters": [
        {
            "name": "Maren",
            "role": "protagonist",
            "description": "A quiet woman in her fifties. Weathered hands, sharp eyes.",
            "arc": "Resignation to cautious hope",
        },
    ],
    "setting": {
        "place": "A remote island lighthouse",
        "time_period": "1970s",
        "atmosphere": "Grey, salt-weathered, isolated",
    },
    "premise": "A lighthouse keeper receives an unexpected visitor.",
    "rules": ["No magic or supernatural elements"],
}


# ---------------------------------------------------------------------------
# Story bible phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bible_client():
    """Mock ClaudeClient for story bible phase."""
    client = MagicMock()
    client.generate_structured.return_value = BIBLE_RESPONSE
    return client


@pytest.fixture()
def state_with_analysis(inspired_state, analysis_client):
    """State with analysis.json already written."""
    analyze_source(inspired_state, analysis_client)
    return inspired_state


# ---------------------------------------------------------------------------
# Story bible phase — tests
# ---------------------------------------------------------------------------


class TestCreateStoryBibleCallsClaude:
    """create_story_bible() sends analysis context to Claude."""

    def test_craft_notes_in_context(self, state_with_analysis, bible_client):
        """Craft notes from analysis are included in the user message."""
        create_story_bible(state_with_analysis, bible_client)

        call_kwargs = bible_client.generate_structured.call_args.kwargs
        assert "sentence_structure" in call_kwargs["user_message"]
        assert "Short declarative" in call_kwargs["user_message"]


class TestCreateStoryBibleWritesJson:
    """create_story_bible() writes story_bible.json."""

    def test_bible_json_written(self, state_with_analysis, bible_client):
        """story_bible.json exists and contains characters and setting."""
        create_story_bible(state_with_analysis, bible_client)

        bible_path = state_with_analysis.project_dir / "story_bible.json"
        assert bible_path.exists()
        data = json.loads(bible_path.read_text())
        assert "characters" in data
        assert "setting" in data
        assert "premise" in data


class TestCreateStoryBibleWithPremise:
    """create_story_bible() includes premise hint when premise.txt exists."""

    def test_premise_in_user_message(self, state_with_analysis, bible_client):
        """premise.txt content is included in the user message."""
        (state_with_analysis.project_dir / "premise.txt").write_text(
            "set it in space", encoding="utf-8"
        )
        create_story_bible(state_with_analysis, bible_client)

        call_kwargs = bible_client.generate_structured.call_args.kwargs
        assert "set it in space" in call_kwargs["user_message"]

    def test_no_premise_file_still_works(self, state_with_analysis, bible_client):
        """Without premise.txt, bible creation still works."""
        create_story_bible(state_with_analysis, bible_client)

        bible_path = state_with_analysis.project_dir / "story_bible.json"
        assert bible_path.exists()


class TestCreateStoryBibleMissingAnalysis:
    """create_story_bible() raises when analysis.json is missing."""

    def test_missing_analysis_raises(self, inspired_state, bible_client):
        """No analysis.json raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="analysis.json"):
            create_story_bible(inspired_state, bible_client)


class TestCreateStoryBibleMalformedJson:
    """create_story_bible() raises ValueError on corrupt analysis.json."""

    def test_malformed_analysis_json_raises(self, inspired_state, bible_client):
        """Corrupt analysis.json raises ValueError with 'Malformed JSON'."""
        analysis_path = inspired_state.project_dir / "analysis.json"
        analysis_path.write_text("{ this is not valid json !!!", encoding="utf-8")

        with pytest.raises(ValueError, match="Malformed JSON"):
            create_story_bible(inspired_state, bible_client)


# ---------------------------------------------------------------------------
# Outline phase — test data
# ---------------------------------------------------------------------------

OUTLINE_RESPONSE = {
    "scenes": [
        {
            "scene_number": 1,
            "title": "The Arrival",
            "beat": "Maren steps off the ferry.",
            "target_words": 300,
        },
        {
            "scene_number": 2,
            "title": "The Stranger",
            "beat": "A visitor appears.",
            "target_words": 350,
        },
        {
            "scene_number": 3,
            "title": "The Storm",
            "beat": "A storm forces them together.",
            "target_words": 250,
        },
    ],
    "total_target_words": 900,
}


# ---------------------------------------------------------------------------
# Outline phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def outline_client():
    """Mock ClaudeClient for outline phase."""
    client = MagicMock()
    client.generate_structured.return_value = OUTLINE_RESPONSE
    return client


@pytest.fixture()
def state_with_bible(state_with_analysis, bible_client):
    """State with both analysis.json and story_bible.json."""
    create_story_bible(state_with_analysis, bible_client)
    return state_with_analysis


# ---------------------------------------------------------------------------
# Outline phase — tests
# ---------------------------------------------------------------------------


class TestCreateOutlineCallsClaude:
    """create_outline() sends bible and analysis to Claude."""

    def test_bible_in_context(self, state_with_bible, outline_client):
        """Story bible is included in the user message."""
        create_outline(state_with_bible, outline_client)

        call_kwargs = outline_client.generate_structured.call_args.kwargs
        assert "Maren" in call_kwargs["user_message"]


class TestCreateOutlineWritesJson:
    """create_outline() writes outline.json."""

    def test_outline_json_written(self, state_with_bible, outline_client):
        """outline.json exists and contains scenes array."""
        create_outline(state_with_bible, outline_client)

        outline_path = state_with_bible.project_dir / "outline.json"
        assert outline_path.exists()
        data = json.loads(outline_path.read_text())
        assert "scenes" in data
        assert len(data["scenes"]) == 3
        assert "total_target_words" in data


class TestCreateOutlineSceneBeats:
    """create_outline() scenes have required fields."""

    def test_scene_beat_fields(self, state_with_bible, outline_client):
        """Each scene beat has scene_number, title, beat, target_words."""
        create_outline(state_with_bible, outline_client)

        data = json.loads((state_with_bible.project_dir / "outline.json").read_text())
        scene = data["scenes"][0]
        assert "scene_number" in scene
        assert "title" in scene
        assert "beat" in scene
        assert "target_words" in scene


class TestCreateOutlineSourceStats:
    """create_outline() includes source stats for length targeting."""

    def test_source_stats_in_context(self, state_with_bible, outline_client):
        """Source word count and scene estimate are in the user message."""
        create_outline(state_with_bible, outline_client)

        call_kwargs = outline_client.generate_structured.call_args.kwargs
        # source_stats from ANALYSIS_RESPONSE: word_count=90, scene_count_estimate=3
        assert "90" in call_kwargs["user_message"]


class TestCreateOutlineMissingBible:
    """create_outline() raises when story_bible.json is missing."""

    def test_missing_bible_raises(self, state_with_analysis, outline_client):
        """No story_bible.json raises FileNotFoundError."""
        # state_with_analysis has analysis.json but not story_bible.json
        with pytest.raises(FileNotFoundError, match="story_bible.json"):
            create_outline(state_with_analysis, outline_client)


class TestCreateOutlineIncludesPremise:
    """create_outline() passes premise.txt content to Claude when it exists."""

    def test_premise_in_user_message(self, state_with_bible, outline_client):
        """Premise text appears in user message sent to Claude."""
        (state_with_bible.project_dir / "premise.txt").write_text(
            "set it in space", encoding="utf-8"
        )

        create_outline(state_with_bible, outline_client)

        call_kwargs = outline_client.generate_structured.call_args_list[0].kwargs
        assert "set it in space" in call_kwargs["user_message"]

    def test_no_premise_file_still_works(self, state_with_bible, outline_client):
        """Outline proceeds without error when premise.txt doesn't exist."""
        create_outline(state_with_bible, outline_client)

        assert outline_client.generate_structured.call_count == 1


# ---------------------------------------------------------------------------
# Scene prose phase — test data
# ---------------------------------------------------------------------------

PROSE_RESPONSE_1 = {
    "prose": "Maren stepped off the ferry onto the wet stones.",
    "summary": "Maren arrives on the island and sees the lighthouse.",
}

PROSE_RESPONSE_2 = {
    "prose": "The stranger stood at the door, rain dripping from his coat.",
    "summary": "A stranger appears at the lighthouse door during the storm.",
}

PROSE_RESPONSE_3 = {
    "prose": "The storm rattled the windows as they sat in silence.",
    "summary": "Maren and the stranger wait out the storm together.",
}


# ---------------------------------------------------------------------------
# Scene prose phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prose_client():
    """Mock ClaudeClient for scene prose phase."""
    client = MagicMock()
    client.generate_structured.side_effect = [
        PROSE_RESPONSE_1,
        PROSE_RESPONSE_2,
        PROSE_RESPONSE_3,
    ]
    return client


@pytest.fixture()
def state_with_outline(state_with_bible, outline_client):
    """State with analysis.json, story_bible.json, and outline.json."""
    create_outline(state_with_bible, outline_client)
    return state_with_bible


# ---------------------------------------------------------------------------
# Scene prose phase — tests
# ---------------------------------------------------------------------------


class TestWriteSceneProseCreatesScenes:
    """write_scene_prose() creates scenes in state."""

    def test_scenes_created(self, state_with_outline, prose_client):
        """One scene created per outline beat."""
        write_scene_prose(state_with_outline, prose_client)

        assert len(state_with_outline.metadata.scenes) == 3


class TestWriteSceneProseContent:
    """write_scene_prose() stores correct prose in each scene."""

    def test_scene_prose_matches_response(self, state_with_outline, prose_client):
        """Scene prose matches Claude response."""
        write_scene_prose(state_with_outline, prose_client)

        scenes = state_with_outline.metadata.scenes
        assert scenes[0].prose == PROSE_RESPONSE_1["prose"]
        assert scenes[1].prose == PROSE_RESPONSE_2["prose"]
        assert scenes[2].prose == PROSE_RESPONSE_3["prose"]


class TestWriteSceneProseCallsPerScene:
    """write_scene_prose() makes one Claude call per outline scene."""

    def test_one_call_per_scene(self, state_with_outline, prose_client):
        """Claude called once per scene beat."""
        write_scene_prose(state_with_outline, prose_client)

        assert prose_client.generate_structured.call_count == 3


class TestWriteSceneProseRunningSummary:
    """write_scene_prose() includes running summary in subsequent calls."""

    def test_second_call_includes_prior_summary(self, state_with_outline, prose_client):
        """Second scene call includes summary of first scene."""
        write_scene_prose(state_with_outline, prose_client)

        # First call should not have prior summary
        first_call = prose_client.generate_structured.call_args_list[0].kwargs
        assert "Previously:" not in first_call["user_message"]

        # Second call should include first scene's summary
        second_call = prose_client.generate_structured.call_args_list[1].kwargs
        assert PROSE_RESPONSE_1["summary"] in second_call["user_message"]


class TestWriteSceneProseWritesMdFiles:
    """write_scene_prose() writes scene .md files."""

    def test_md_files_created(self, state_with_outline, prose_client):
        """scenes/*.md files are written for each scene."""
        write_scene_prose(state_with_outline, prose_client)

        scenes_dir = state_with_outline.project_dir / "scenes"
        assert (scenes_dir / "scene_001.md").exists()
        assert (scenes_dir / "scene_002.md").exists()
        assert (scenes_dir / "scene_003.md").exists()


class TestWriteSceneProseAssetStatus:
    """write_scene_prose() sets TEXT asset to COMPLETED."""

    def test_text_asset_completed(self, state_with_outline, prose_client):
        """TEXT asset status is COMPLETED for each scene."""
        write_scene_prose(state_with_outline, prose_client)

        for scene in state_with_outline.metadata.scenes:
            assert scene.asset_status.text == SceneStatus.COMPLETED


class TestWriteSceneProseSavesPerScene:
    """write_scene_prose() persists state after each scene for resume support."""

    def test_state_saved_once_per_scene(self, state_with_outline, prose_client, mocker):
        """state.save() called once per scene to enable incremental resume."""
        spy = mocker.patch.object(state_with_outline, "save", wraps=state_with_outline.save)

        write_scene_prose(state_with_outline, prose_client)

        assert spy.call_count == 3


class TestWriteSceneProseSummaryStored:
    """write_scene_prose() persists summary from Claude response."""

    def test_summary_stored_on_scene(self, state_with_outline, prose_client):
        """Scene summary matches Claude response."""
        write_scene_prose(state_with_outline, prose_client)

        scenes = state_with_outline.metadata.scenes
        assert scenes[0].summary == PROSE_RESPONSE_1["summary"]
        assert scenes[1].summary == PROSE_RESPONSE_2["summary"]
        assert scenes[2].summary == PROSE_RESPONSE_3["summary"]


class TestWriteSceneProseResume:
    """write_scene_prose() skips already-created scenes on resume."""

    def test_resume_skips_completed_scenes(self, state_with_outline, prose_client):
        """With scene 1 already added, only scenes 2 and 3 are processed."""
        # Manually add scene 1
        state_with_outline.add_scene(1, "The Arrival", "Pre-existing prose.")
        state_with_outline.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        # Only 2 calls needed now
        prose_client.generate_structured.side_effect = [
            PROSE_RESPONSE_2,
            PROSE_RESPONSE_3,
        ]

        write_scene_prose(state_with_outline, prose_client)

        assert len(state_with_outline.metadata.scenes) == 3
        # Scene 1 prose unchanged
        assert state_with_outline.metadata.scenes[0].prose == "Pre-existing prose."
        # Scenes 2 and 3 from Claude
        assert state_with_outline.metadata.scenes[1].prose == PROSE_RESPONSE_2["prose"]
        assert prose_client.generate_structured.call_count == 2

    def test_resume_uses_stored_summary_for_context(self, state_with_outline, prose_client):
        """On resume, stored summary used instead of title-only for running context."""
        # Scene 1 already has a summary
        state_with_outline.add_scene(
            1, "The Arrival", "Pre-existing prose.", summary="Maren arrives on the island."
        )
        state_with_outline.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        prose_client.generate_structured.side_effect = [
            PROSE_RESPONSE_2,
            PROSE_RESPONSE_3,
        ]

        write_scene_prose(state_with_outline, prose_client)

        # Second call (scene 2) should use stored summary, not just title
        first_call = prose_client.generate_structured.call_args_list[0].kwargs
        assert "Maren arrives on the island." in first_call["user_message"]

    def test_resume_falls_back_to_title_when_no_summary(self, state_with_outline, prose_client):
        """On resume, falls back to title-only when summary is None (backward compat)."""
        # Scene 1 without summary (backward compat)
        state_with_outline.add_scene(1, "The Arrival", "Pre-existing prose.")
        state_with_outline.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        prose_client.generate_structured.side_effect = [
            PROSE_RESPONSE_2,
            PROSE_RESPONSE_3,
        ]

        write_scene_prose(state_with_outline, prose_client)

        first_call = prose_client.generate_structured.call_args_list[0].kwargs
        assert "Scene 1: The Arrival" in first_call["user_message"]
        # Must NOT use summary format "Scene 1 (The Arrival): ..."
        assert "(The Arrival)" not in first_call["user_message"]


class TestWriteSceneProseMissingOutline:
    """write_scene_prose() raises when outline.json is missing."""

    def test_missing_outline_raises(self, state_with_bible, prose_client):
        """No outline.json raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="outline.json"):
            write_scene_prose(state_with_bible, prose_client)


# ---------------------------------------------------------------------------
# Critique/revision phase — test data
# ---------------------------------------------------------------------------

CRITIQUE_RESPONSE_1 = {
    "revised_prose": "Maren stepped off the ferry onto wet stones. The lighthouse waited.",
    "changes": ["Shortened the opening — removed redundant description"],
}

CRITIQUE_RESPONSE_2 = {
    "revised_prose": "A stranger stood at the door. Rain dripped from his coat.",
    "changes": ["Split compound sentence for pacing consistency with craft notes"],
}

CRITIQUE_RESPONSE_3 = {
    "revised_prose": "The storm shook the windows. They sat without speaking.",
    "changes": ["Replaced 'rattled' with 'shook' — simpler vocabulary per craft notes"],
}


# ---------------------------------------------------------------------------
# Critique/revision phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def critique_client():
    """Mock ClaudeClient for critique phase."""
    client = MagicMock()
    client.generate_structured.side_effect = [
        CRITIQUE_RESPONSE_1,
        CRITIQUE_RESPONSE_2,
        CRITIQUE_RESPONSE_3,
    ]
    return client


@pytest.fixture()
def state_with_prose(state_with_outline, prose_client):
    """State with scenes created by write_scene_prose."""
    write_scene_prose(state_with_outline, prose_client)
    return state_with_outline


# ---------------------------------------------------------------------------
# Critique/revision phase — tests
# ---------------------------------------------------------------------------


class TestCritiqueAndReviseUpdatesProse:
    """critique_and_revise() overwrites scene prose with revised version."""

    def test_prose_overwritten(self, state_with_prose, critique_client):
        """Each scene's prose is replaced with the revised version."""
        critique_and_revise(state_with_prose, critique_client)

        scenes = state_with_prose.metadata.scenes
        assert scenes[0].prose == CRITIQUE_RESPONSE_1["revised_prose"]
        assert scenes[1].prose == CRITIQUE_RESPONSE_2["revised_prose"]
        assert scenes[2].prose == CRITIQUE_RESPONSE_3["revised_prose"]


class TestCritiqueAndReviseCallsPerScene:
    """critique_and_revise() makes one Claude call per scene."""

    def test_one_call_per_scene(self, state_with_prose, critique_client):
        """Claude called once per scene."""
        critique_and_revise(state_with_prose, critique_client)

        assert critique_client.generate_structured.call_count == 3


class TestCritiqueAndReviseSavesPerScene:
    """critique_and_revise() persists state after each scene for resume support."""

    def test_state_saved_once_per_scene(self, state_with_prose, critique_client, mocker):
        """state.save() called once per scene to enable incremental resume."""
        spy = mocker.patch.object(state_with_prose, "save", wraps=state_with_prose.save)

        critique_and_revise(state_with_prose, critique_client)

        assert spy.call_count == 3


class TestCritiqueAndReviseWritesChangelog:
    """critique_and_revise() writes change notes to critique/ directory."""

    def test_changelog_files_written(self, state_with_prose, critique_client):
        """critique/scene_01_changes.md exists with change descriptions."""
        critique_and_revise(state_with_prose, critique_client)

        critique_dir = state_with_prose.project_dir / "critique"
        assert (critique_dir / "scene_001_changes.md").exists()
        content = (critique_dir / "scene_001_changes.md").read_text()
        assert "Shortened the opening" in content


class TestCritiqueAndReviseCraftNotesInContext:
    """critique_and_revise() includes craft notes in Claude calls."""

    def test_craft_notes_in_user_message(self, state_with_prose, critique_client):
        """Craft notes are in the user message for consistency checking."""
        critique_and_revise(state_with_prose, critique_client)

        call_kwargs = critique_client.generate_structured.call_args_list[0].kwargs
        assert "sentence_structure" in call_kwargs["user_message"]


class TestCritiqueAndReviseMissingAnalysis:
    """critique_and_revise() raises when analysis.json is missing."""

    def test_missing_analysis_raises(self, tmp_path, critique_client):
        """No analysis.json raises FileNotFoundError."""
        state = ProjectState.create(
            project_id="no-analysis",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(1, "Test", "Some prose.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        with pytest.raises(FileNotFoundError, match="analysis.json"):
            critique_and_revise(state, critique_client)


class TestCritiqueAndReviseNoScenes:
    """critique_and_revise() raises when no scenes exist."""

    def test_no_scenes_raises(self, inspired_state, critique_client):
        """Empty scenes list raises ValueError."""
        # Write analysis.json so that's not the failure point
        (inspired_state.project_dir / "analysis.json").write_text(
            json.dumps(ANALYSIS_RESPONSE), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="No scenes"):
            critique_and_revise(inspired_state, critique_client)


class TestCritiqueAndReviseUpdatesMdFiles:
    """critique_and_revise() updates the scene .md files with revised prose."""

    def test_md_files_updated(self, state_with_prose, critique_client):
        """scenes/*.md files contain revised prose after critique."""
        critique_and_revise(state_with_prose, critique_client)

        scenes_dir = state_with_prose.project_dir / "scenes"
        content = (scenes_dir / "scene_001.md").read_text()
        assert CRITIQUE_RESPONSE_1["revised_prose"] in content


class TestCritiqueAndReviseResume:
    """critique_and_revise() skips already-critiqued scenes on resume."""

    def test_resume_skips_critiqued_scenes(self, state_with_prose, critique_client):
        """Scenes with existing changelog files are skipped on resume."""
        # Manually create changelog for scene 1 (simulating prior run)
        critique_dir = state_with_prose.project_dir / "critique"
        critique_dir.mkdir(exist_ok=True)
        (critique_dir / "scene_001_changes.md").write_text(
            "# Scene 1: The Arrival — Changes\n\n- Already revised\n",
            encoding="utf-8",
        )

        # Only 2 calls needed (scenes 2 and 3)
        critique_client.generate_structured.side_effect = [
            CRITIQUE_RESPONSE_2,
            CRITIQUE_RESPONSE_3,
        ]

        critique_and_revise(state_with_prose, critique_client)

        # Scene 1 prose unchanged (not re-critiqued)
        assert state_with_prose.metadata.scenes[0].prose == PROSE_RESPONSE_1["prose"]
        # Scenes 2 and 3 revised
        assert state_with_prose.metadata.scenes[1].prose == CRITIQUE_RESPONSE_2["revised_prose"]
        assert critique_client.generate_structured.call_count == 2


class TestCritiqueAndReviseEmptyChanges:
    """critique_and_revise() handles scenes with no changes needed."""

    def test_empty_changes_writes_no_changes_file(self, state_with_prose):
        """When Claude returns empty changes list, changelog says 'No changes needed'."""
        client = MagicMock()
        client.generate_structured.side_effect = [
            {"revised_prose": "Same prose scene 1.", "changes": []},
            CRITIQUE_RESPONSE_2,
            CRITIQUE_RESPONSE_3,
        ]

        critique_and_revise(state_with_prose, client)

        critique_dir = state_with_prose.project_dir / "critique"
        content = (critique_dir / "scene_001_changes.md").read_text()
        assert "No changes needed" in content


# ---------------------------------------------------------------------------
# Integration test — full inspired_by creative flow
# ---------------------------------------------------------------------------


class TestInspiredByIntegration:
    """Full inspired_by creative flow integration test."""

    def test_full_creative_flow(self, tmp_path):
        """All 5 creative phases run end-to-end with mocked Claude."""
        # --- Setup ---
        state = ProjectState.create(
            project_id="integration-test",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "integration-test" / "source_story.txt"
        source.write_text("A short story about a cat who learns to fly.", encoding="utf-8")

        client = MagicMock()

        # Configure mock responses for each phase
        client.generate_structured.side_effect = [
            # Phase 1: analyze_source
            ANALYSIS_RESPONSE,
            # Phase 2: create_story_bible
            BIBLE_RESPONSE,
            # Phase 3: create_outline (2 scenes for simplicity)
            {
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "The Discovery",
                        "beat": "Cat finds wings.",
                        "target_words": 200,
                    },
                    {
                        "scene_number": 2,
                        "title": "First Flight",
                        "beat": "Cat takes off.",
                        "target_words": 200,
                    },
                ],
                "total_target_words": 400,
            },
            # Phase 4: write_scene_prose (one per scene)
            {
                "prose": "The cat found wings in the attic.",
                "summary": "Cat finds mysterious wings.",
            },
            {
                "prose": "She leaped from the windowsill and soared.",
                "summary": "Cat flies for the first time.",
            },
            # Phase 5: critique_and_revise (one per scene)
            {
                "revised_prose": "The cat discovered wings in the dusty attic.",
                "changes": ["Added sensory detail"],
            },
            {
                "revised_prose": "She launched from the sill and caught the wind.",
                "changes": ["Stronger verb choice"],
            },
        ]

        # --- Execute all 5 phases ---
        analyze_source(state, client)
        create_story_bible(state, client)
        create_outline(state, client)
        write_scene_prose(state, client)
        critique_and_revise(state, client)

        # --- Verify end state ---
        # All artifact files exist
        project_dir = state.project_dir
        assert (project_dir / "analysis.json").exists()
        assert (project_dir / "story_bible.json").exists()
        assert (project_dir / "outline.json").exists()
        assert (project_dir / "scenes" / "scene_001.md").exists()
        assert (project_dir / "scenes" / "scene_002.md").exists()
        assert (project_dir / "critique" / "scene_001_changes.md").exists()

        # Scenes have revised prose (from critique, not original prose)
        scenes = state.metadata.scenes
        assert len(scenes) == 2
        assert "dusty attic" in scenes[0].prose
        assert "caught the wind" in scenes[1].prose

        # TEXT asset is COMPLETED for all scenes
        for scene in scenes:
            assert scene.asset_status.text == SceneStatus.COMPLETED

        # 7 total Claude calls: 1 analysis + 1 bible + 1 outline + 2 prose + 2 critique
        assert client.generate_structured.call_count == 7


# ---------------------------------------------------------------------------
# _load_json_artifact — malformed JSON
# ---------------------------------------------------------------------------


class TestLoadJsonArtifactMalformed:
    """_load_json_artifact raises ValueError for malformed JSON."""

    def test_malformed_json_raises(self, tmp_path):
        """Corrupt JSON file raises ValueError with descriptive message."""
        (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed JSON"):
            _load_json_artifact(tmp_path, "bad.json")
