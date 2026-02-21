"""Tests for story_video.models — Pydantic data models.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the data models.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from story_video.models import (
    ADAPT_FLOW_PHASES,
    CREATIVE_FLOW_PHASES,
    AppConfig,
    AssetType,
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    ImageConfig,
    InputMode,
    NarrationSegment,
    PhaseStatus,
    PipelinePhase,
    ProjectMetadata,
    Scene,
    SceneAssetStatus,
    SceneStatus,
    StoryConfig,
    StoryHeader,
    SubtitleConfig,
    TTSConfig,
    VideoConfig,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestInputMode:
    """InputMode enum — three input modes for story generation."""

    def test_json_serializes_as_string_value(self):
        """Pydantic serializes the enum as its string value in JSON."""
        project = ProjectMetadata(project_id="test", mode=InputMode.ORIGINAL)
        json_str = project.model_dump_json()
        assert '"original"' in json_str


class TestSceneStatus:
    """SceneStatus enum — scene-level status tracking."""

    def test_does_not_have_awaiting_review(self):
        """Scene status does not include awaiting_review — only phases have that."""
        member_values = {m.value for m in SceneStatus}
        assert "awaiting_review" not in member_values


# ---------------------------------------------------------------------------
# Phase sequence helper tests
# ---------------------------------------------------------------------------


class TestPhaseSequences:
    """Phase sequences for each input mode."""

    def test_creative_flow_sequence(self):
        """original/inspired_by mode uses creative phases then shared phases."""
        expected = (
            PipelinePhase.ANALYSIS,
            PipelinePhase.STORY_BIBLE,
            PipelinePhase.OUTLINE,
            PipelinePhase.SCENE_PROSE,
            PipelinePhase.CRITIQUE_REVISION,
            PipelinePhase.IMAGE_PROMPTS,
            PipelinePhase.NARRATION_PREP,
            PipelinePhase.TTS_GENERATION,
            PipelinePhase.IMAGE_GENERATION,
            PipelinePhase.CAPTION_GENERATION,
            PipelinePhase.VIDEO_ASSEMBLY,
        )
        assert CREATIVE_FLOW_PHASES == expected

    def test_adapt_flow_sequence(self):
        """adapt mode uses analysis then adapt-specific phases then shared phases."""
        expected = (
            PipelinePhase.ANALYSIS,
            PipelinePhase.SCENE_SPLITTING,
            PipelinePhase.NARRATION_FLAGGING,
            PipelinePhase.IMAGE_PROMPTS,
            PipelinePhase.NARRATION_PREP,
            PipelinePhase.TTS_GENERATION,
            PipelinePhase.IMAGE_GENERATION,
            PipelinePhase.CAPTION_GENERATION,
            PipelinePhase.VIDEO_ASSEMBLY,
        )
        assert ADAPT_FLOW_PHASES == expected

    def test_shared_phases_are_shared(self):
        """The trailing shared phases are the same in both flows."""
        shared_in_creative = CREATIVE_FLOW_PHASES[-6:]
        shared_in_adapt = ADAPT_FLOW_PHASES[-6:]
        assert shared_in_creative == shared_in_adapt


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------


class TestStoryConfig:
    """StoryConfig — story generation parameters."""

    def test_rejects_negative_duration(self):
        with pytest.raises(ValidationError):
            StoryConfig(target_duration_minutes=-1)

    def test_rejects_zero_words_per_minute(self):
        with pytest.raises(ValidationError):
            StoryConfig(words_per_minute=0)


class TestStoryConfigWordCountValidation:
    """StoryConfig enforces min <= target <= max for scene word counts."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"scene_word_min": 200, "scene_word_max": 100, "scene_word_target": 150},
            {"scene_word_min": 100, "scene_word_max": 200, "scene_word_target": 250},
            {"scene_word_min": 100, "scene_word_max": 200, "scene_word_target": 50},
        ],
        ids=["min_exceeds_max", "target_exceeds_max", "target_below_min"],
    )
    def test_invalid_word_count_bounds_rejected(self, kwargs):
        with pytest.raises(ValidationError):
            StoryConfig(**kwargs)

    def test_valid_bounds_accepted(self):
        """Valid ordering passes validation."""
        config = StoryConfig(scene_word_min=500, scene_word_target=1800, scene_word_max=3000)
        assert config.scene_word_min == 500

    def test_equal_bounds_accepted(self):
        """All three values equal is valid."""
        config = StoryConfig(scene_word_min=1000, scene_word_target=1000, scene_word_max=1000)
        assert config.scene_word_target == 1000


class TestTTSConfig:
    """TTSConfig — text-to-speech parameters."""

    def test_rejects_non_positive_speed(self):
        with pytest.raises(ValidationError):
            TTSConfig(speed=0.0)

    def test_rejects_unknown_provider(self):
        """Unknown TTS provider name raises ValidationError."""
        with pytest.raises(ValidationError, match="Unknown TTS provider"):
            TTSConfig(provider="google")


class TestTTSConfigFileExtension:
    """TTSConfig.file_extension extracts codec from output_format."""

    @pytest.mark.parametrize(
        "fmt,expected",
        [("mp3", "mp3"), ("mp3_44100_128", "mp3"), ("opus", "opus")],
    )
    def test_file_extension(self, fmt, expected):
        assert TTSConfig(output_format=fmt).file_extension == expected


class TestImageConfigSizeValidator:
    """ImageConfig.size must be WIDTHxHEIGHT format."""

    def test_valid_size_accepted(self):
        config = ImageConfig(size="1024x1024")
        assert config.size == "1024x1024"

    def test_invalid_size_rejected(self):
        with pytest.raises(ValidationError, match="WIDTHxHEIGHT"):
            ImageConfig(size="big")


class TestVideoConfig:
    """VideoConfig — video assembly parameters."""

    def test_rejects_negative_fps(self):
        with pytest.raises(ValidationError):
            VideoConfig(fps=-1)

    def test_rejects_negative_crf(self):
        with pytest.raises(ValidationError):
            VideoConfig(crf=-1)


class TestSubtitleConfig:
    """SubtitleConfig — subtitle rendering parameters."""

    def test_rejects_non_positive_font_size(self):
        with pytest.raises(ValidationError):
            SubtitleConfig(font_size=0)

    def test_rejects_non_positive_max_lines(self):
        with pytest.raises(ValidationError):
            SubtitleConfig(max_lines=0)


class TestAppConfig:
    """AppConfig — top-level config combining all sections."""

    def test_json_roundtrip(self):
        config = AppConfig()
        json_str = config.model_dump_json()
        restored = AppConfig.model_validate_json(json_str)
        assert restored == config

    def test_rejects_unknown_top_level_key(self):
        """Extra="forbid" on sub-configs rejects unknown nested keys."""
        with pytest.raises(ValidationError):
            AppConfig(story=StoryConfig(), unknown_section="bad")

    def test_rejects_unknown_nested_key(self):
        """Extra="forbid" on StoryConfig rejects unknown fields."""
        with pytest.raises(ValidationError):
            AppConfig(story={"target_duration_minutes": 30, "bogus_key": True})


# ---------------------------------------------------------------------------
# Scene asset status tests
# ---------------------------------------------------------------------------


class TestSceneAssetStatus:
    """SceneAssetStatus — per-asset status tracking for a scene."""

    def test_individual_status_update(self):
        status = SceneAssetStatus(text=SceneStatus.COMPLETED)
        assert status.text == SceneStatus.COMPLETED
        assert status.audio == SceneStatus.PENDING

    def test_serialization_roundtrip(self):
        status = SceneAssetStatus(
            text=SceneStatus.COMPLETED,
            audio=SceneStatus.FAILED,
        )
        data = status.model_dump()
        restored = SceneAssetStatus(**data)
        assert restored == status

    def test_asset_status_fields_match_asset_type_members(self):
        expected_fields = {member.value for member in AssetType}
        actual_fields = set(SceneAssetStatus.model_fields.keys())
        assert actual_fields == expected_fields


# ---------------------------------------------------------------------------
# Scene tests
# ---------------------------------------------------------------------------


class TestScene:
    """Scene — content and metadata for a single story scene."""

    def test_all_fields_populated(self):
        scene = Scene(
            scene_number=3,
            title="The Confrontation",
            prose="She stood her ground...",
            narration_text="She stood her ground.",
            image_prompt="A woman standing firm in a dark alley, cinematic lighting",
            asset_status=SceneAssetStatus(
                text=SceneStatus.COMPLETED,
                narration_text=SceneStatus.COMPLETED,
            ),
        )
        assert scene.scene_number == 3
        assert scene.narration_text == "She stood her ground."
        assert scene.image_prompt is not None
        assert scene.asset_status.text == SceneStatus.COMPLETED

    def test_rejects_non_positive_scene_number(self):
        with pytest.raises(ValidationError):
            Scene(scene_number=0, title="Bad", prose="No")

    def test_rejects_empty_title(self):
        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="", prose="Some text")

    def test_rejects_empty_prose(self):
        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="Title", prose="")

    def test_summary_defaults_to_none(self):
        scene = Scene(scene_number=1, title="Opening", prose="The story begins.")
        assert scene.summary is None

    def test_summary_stored_when_provided(self):
        scene = Scene(
            scene_number=1,
            title="Opening",
            prose="The story begins.",
            summary="Hero arrives at the castle.",
        )
        assert scene.summary == "Hero arrives at the castle."

    def test_json_roundtrip(self):
        scene = Scene(
            scene_number=2,
            title="The Journey",
            prose="They walked for miles...",
        )
        json_str = scene.model_dump_json()
        restored = Scene.model_validate_json(json_str)
        assert restored == scene

    def test_json_roundtrip_with_summary(self):
        scene = Scene(
            scene_number=2,
            title="The Journey",
            prose="They walked for miles...",
            summary="The group travels across the plains.",
        )
        json_str = scene.model_dump_json()
        restored = Scene.model_validate_json(json_str)
        assert restored.summary == "The group travels across the plains."


# ---------------------------------------------------------------------------
# ProjectMetadata tests
# ---------------------------------------------------------------------------


class TestProjectMetadata:
    """ProjectMetadata — project-level tracking information."""

    def test_creation_with_required_fields(self):
        project = ProjectMetadata(
            project_id="lighthouse-2026-02-11-abc123",
            mode=InputMode.ORIGINAL,
        )
        assert project.project_id == "lighthouse-2026-02-11-abc123"
        assert project.mode == InputMode.ORIGINAL

    def test_created_at_defaults_to_now(self):
        before = datetime.now(timezone.utc)
        project = ProjectMetadata(
            project_id="test-project",
            mode=InputMode.ADAPT,
        )
        after = datetime.now(timezone.utc)
        assert before <= project.created_at <= after

    def test_rejects_empty_project_id(self):
        with pytest.raises(ValidationError):
            ProjectMetadata(project_id="", mode=InputMode.ORIGINAL)

    def test_full_creation(self):
        project = ProjectMetadata(
            project_id="my-story-2026",
            mode=InputMode.INSPIRED_BY,
            current_phase=PipelinePhase.ANALYSIS,
            status=PhaseStatus.IN_PROGRESS,
            config=AppConfig(story=StoryConfig(target_duration_minutes=60)),
            scenes=[
                Scene(scene_number=1, title="Opening", prose="It began..."),
            ],
        )
        assert project.mode == InputMode.INSPIRED_BY
        assert project.current_phase == PipelinePhase.ANALYSIS
        assert project.status == PhaseStatus.IN_PROGRESS
        assert len(project.scenes) == 1
        assert project.config.story.target_duration_minutes == 60

    def test_json_roundtrip(self):
        project = ProjectMetadata(
            project_id="json-test",
            mode=InputMode.ORIGINAL,
        )
        json_str = project.model_dump_json()
        restored = ProjectMetadata.model_validate_json(json_str)
        assert restored.project_id == project.project_id
        assert restored.mode == project.mode


# ---------------------------------------------------------------------------
# VideoConfig resolution validation tests
# ---------------------------------------------------------------------------


class TestVideoConfigResolutionValidation:
    """VideoConfig.resolution validates WIDTHxHEIGHT format."""

    def test_valid_resolution_1080p(self):
        """Standard 1080p resolution is accepted."""
        config = VideoConfig(resolution="1920x1080")
        assert config.resolution == "1920x1080"

    @pytest.mark.parametrize(
        "invalid",
        ["1920X1080", "1920:1080", "1920x1080x720", "fullhd"],
    )
    def test_invalid_resolution_rejected(self, invalid):
        with pytest.raises(ValidationError):
            VideoConfig(resolution=invalid)


# ---------------------------------------------------------------------------
# Caption data models — importable from models module
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CaptionWord timestamp validation
# ---------------------------------------------------------------------------


class TestCaptionWordTimestampValidation:
    """CaptionWord rejects negative timestamps."""

    def test_rejects_negative_start(self):
        """Negative start timestamp is rejected."""

        with pytest.raises(ValidationError):
            CaptionWord(word="hello", start=-0.1, end=0.5)

    def test_accepts_zero_timestamps(self):
        """Zero timestamps are valid."""

        word = CaptionWord(word="hello", start=0.0, end=0.0)
        assert word.start == 0.0
        assert word.end == 0.0

    def test_rejects_start_after_end(self):
        """start > end is rejected."""

        with pytest.raises(ValidationError, match="start.*must not exceed.*end"):
            CaptionWord(word="hello", start=1.0, end=0.5)


class TestCaptionSegmentTimestampValidation:
    """CaptionSegment rejects invalid timestamps."""

    def test_rejects_start_after_end(self):
        """start > end is rejected."""

        with pytest.raises(ValidationError, match="start.*must not exceed.*end"):
            CaptionSegment(text="hello", start=2.0, end=1.0)


class TestCaptionResultDurationValidation:
    """CaptionResult.duration rejects negative values."""

    def test_rejects_negative_duration(self):
        """Negative duration is rejected."""

        with pytest.raises(ValidationError):
            CaptionResult(
                segments=[CaptionSegment(text="hi", start=0.0, end=1.0)],
                words=[CaptionWord(word="hi", start=0.0, end=1.0)],
                language="en",
                duration=-1.0,
            )

    def test_accepts_zero_duration(self):
        """Zero duration is valid (empty transcription)."""

        result = CaptionResult(segments=[], words=[], language="en", duration=0.0)
        assert result.duration == 0.0


# ---------------------------------------------------------------------------
# StoryHeader tests
# ---------------------------------------------------------------------------


class TestStoryHeader:
    """StoryHeader model for parsed front matter."""

    def test_defaults(self):
        header = StoryHeader(voices={"narrator": "nova"})
        assert header.default_voice == "narrator"

    def test_custom_default_voice(self):
        header = StoryHeader(
            voices={"narrator": "nova", "bob": "echo"},
            default_voice="bob",
        )
        assert header.default_voice == "bob"

    def test_voices_required(self):
        with pytest.raises(ValidationError):
            StoryHeader()

    def test_rejects_empty_voices(self):
        with pytest.raises(ValidationError):
            StoryHeader(voices={})

    def test_frozen(self):
        header = StoryHeader(voices={"narrator": "nova"})
        with pytest.raises(ValidationError):
            header.default_voice = "other"

    def test_rejects_default_voice_not_in_voices(self):
        """default_voice must exist in voices dict."""
        with pytest.raises(ValidationError, match="default_voice"):
            StoryHeader(voices={"narrator": "nova"}, default_voice="nonexistent")

    def test_serialization_roundtrip(self):
        header = StoryHeader(voices={"jane": "nova", "bob": "alloy"}, default_voice="jane")
        data = header.model_dump()
        restored = StoryHeader(**data)
        assert restored == header


# ---------------------------------------------------------------------------
# NarrationSegment tests
# ---------------------------------------------------------------------------


class TestNarrationSegment:
    """NarrationSegment model for parsed text chunks."""

    def test_required_fields(self):
        seg = NarrationSegment(
            text="Hello",
            voice="nova",
            voice_label="narrator",
            scene_number=1,
            segment_index=0,
        )
        assert seg.text == "Hello"
        assert seg.mood is None

    def test_with_mood(self):
        seg = NarrationSegment(
            text="Goodbye",
            voice="nova",
            voice_label="narrator",
            mood="sad",
            scene_number=1,
            segment_index=0,
        )
        assert seg.mood == "sad"

    def test_rejects_empty_text(self):
        with pytest.raises(ValidationError):
            NarrationSegment(
                text="",
                voice="nova",
                voice_label="narrator",
                scene_number=1,
                segment_index=0,
            )

    def test_frozen(self):
        seg = NarrationSegment(
            text="Hi",
            voice="nova",
            voice_label="narrator",
            scene_number=1,
            segment_index=0,
        )
        with pytest.raises(ValidationError):
            seg.text = "other"

    def test_rejects_scene_number_zero(self):
        with pytest.raises(ValidationError):
            NarrationSegment(
                text="Hi",
                voice="nova",
                voice_label="narrator",
                scene_number=0,
                segment_index=0,
            )

    def test_rejects_negative_segment_index(self):
        with pytest.raises(ValidationError):
            NarrationSegment(
                text="Hi",
                voice="nova",
                voice_label="narrator",
                scene_number=1,
                segment_index=-1,
            )

    def test_rejects_empty_voice(self):
        with pytest.raises(ValidationError):
            NarrationSegment(
                text="Hi",
                voice="",
                voice_label="narrator",
                scene_number=1,
                segment_index=0,
            )

    def test_rejects_empty_voice_label(self):
        with pytest.raises(ValidationError):
            NarrationSegment(
                text="Hi",
                voice="nova",
                voice_label="",
                scene_number=1,
                segment_index=0,
            )

    def test_serialization_roundtrip(self):
        seg = NarrationSegment(
            text="Hello world",
            voice="nova",
            voice_label="narrator",
            mood="happy",
            scene_number=2,
            segment_index=3,
        )
        data = seg.model_dump()
        restored = NarrationSegment(**data)
        assert restored == seg

    def test_rejects_zero_pause_duration(self):
        """pause_duration=0 is rejected (gt=0 constraint)."""
        with pytest.raises(ValidationError):
            NarrationSegment(
                text="[pause]",
                voice="nova",
                voice_label="narrator",
                scene_number=1,
                segment_index=0,
                pause_duration=0,
            )

    def test_accepts_positive_pause_duration(self):
        """Positive pause_duration is accepted."""
        seg = NarrationSegment(
            text="[pause]",
            voice="nova",
            voice_label="narrator",
            scene_number=1,
            segment_index=0,
            pause_duration=0.5,
        )
        assert seg.pause_duration == 0.5


# ---------------------------------------------------------------------------
# SubtitleConfig hex color validation tests
# ---------------------------------------------------------------------------


class TestSubtitleConfigColorValidation:
    """SubtitleConfig rejects invalid hex color formats."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("color", "red"),
            ("color", "#FFF"),
            ("outline_color", "blue"),
        ],
    )
    def test_rejects_invalid_color(self, field, value):
        with pytest.raises(ValidationError):
            SubtitleConfig(**{field: value})

    def test_accepts_valid_uppercase_hex(self):
        """Standard #RRGGBB format passes."""
        config = SubtitleConfig(color="#FF0000")
        assert config.color == "#FF0000"


# ---------------------------------------------------------------------------
# Package version
# ---------------------------------------------------------------------------


class TestPackageVersion:
    """Package exposes __version__."""

    def test_version_is_importable(self):
        """__version__ is a non-empty string."""
        from story_video import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0
