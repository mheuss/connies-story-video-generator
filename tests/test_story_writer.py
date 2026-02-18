"""Tests for story_video.pipeline.story_writer — scene splitting and narration flagging.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the split_scenes or flag_narration function.
"""

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
    flag_narration,
    split_scenes,
)
from story_video.state import ProjectState
from story_video.utils.narration_tags import strip_narration_tags

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
    source.write_text(SOURCE_TEXT)
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
    source.write_text(SOURCE_TEXT_WITH_HEADER)
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

    def test_source_without_header_unchanged(self, sample_state, mock_client):
        """Source without YAML header still works — body equals full text."""
        split_scenes(sample_state, mock_client)

        call_kwargs = mock_client.generate_structured.call_args.kwargs
        assert call_kwargs["user_message"] == SOURCE_TEXT


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
# Strip narration tags helper
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


class TestFlagNarrationStateSaved:
    """flag_narration() persists state via state.save()."""

    def test_flag_narration_state_saved(self, state_with_scenes, flagging_client):
        """Verify state.save() called."""
        flag_narration(state_with_scenes, flagging_client)

        # Reload from disk — if save was called, project.json is updated
        reloaded = ProjectState.load(state_with_scenes.project_dir)
        assert len(reloaded.metadata.scenes) == 3


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
