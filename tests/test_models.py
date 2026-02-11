"""Tests for story_video.models — Pydantic data models.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the data models.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestInputMode:
    """InputMode enum — three input modes for story generation."""

    def test_has_original_member(self):
        from story_video.models import InputMode

        assert InputMode.ORIGINAL == "original"

    def test_has_inspired_by_member(self):
        from story_video.models import InputMode

        assert InputMode.INSPIRED_BY == "inspired_by"

    def test_has_adapt_member(self):
        from story_video.models import InputMode

        assert InputMode.ADAPT == "adapt"

    def test_has_exactly_three_members(self):
        from story_video.models import InputMode

        assert len(InputMode) == 3

    def test_is_string_enum(self):
        from story_video.models import InputMode

        assert isinstance(InputMode.ORIGINAL, str)

    def test_json_serializes_as_string(self):
        from story_video.models import InputMode

        assert InputMode.ORIGINAL == "original"
        # str enum members serialize as their string value
        assert (
            str(InputMode.ORIGINAL) == "InputMode.ORIGINAL"
            or InputMode.ORIGINAL.value == "original"
        )


class TestPhaseStatus:
    """PhaseStatus enum — phase-level status tracking."""

    def test_has_pending(self):
        from story_video.models import PhaseStatus

        assert PhaseStatus.PENDING == "pending"

    def test_has_in_progress(self):
        from story_video.models import PhaseStatus

        assert PhaseStatus.IN_PROGRESS == "in_progress"

    def test_has_completed(self):
        from story_video.models import PhaseStatus

        assert PhaseStatus.COMPLETED == "completed"

    def test_has_awaiting_review(self):
        from story_video.models import PhaseStatus

        assert PhaseStatus.AWAITING_REVIEW == "awaiting_review"

    def test_has_failed(self):
        from story_video.models import PhaseStatus

        assert PhaseStatus.FAILED == "failed"

    def test_has_exactly_five_members(self):
        from story_video.models import PhaseStatus

        assert len(PhaseStatus) == 5


class TestSceneStatus:
    """SceneStatus enum — scene-level status tracking."""

    def test_has_pending(self):
        from story_video.models import SceneStatus

        assert SceneStatus.PENDING == "pending"

    def test_has_in_progress(self):
        from story_video.models import SceneStatus

        assert SceneStatus.IN_PROGRESS == "in_progress"

    def test_has_completed(self):
        from story_video.models import SceneStatus

        assert SceneStatus.COMPLETED == "completed"

    def test_has_failed(self):
        from story_video.models import SceneStatus

        assert SceneStatus.FAILED == "failed"

    def test_has_exactly_four_members(self):
        from story_video.models import SceneStatus

        assert len(SceneStatus) == 4

    def test_does_not_have_awaiting_review(self):
        """Scene status does not include awaiting_review — only phases have that."""
        from story_video.models import SceneStatus

        member_values = {m.value for m in SceneStatus}
        assert "awaiting_review" not in member_values


class TestAssetType:
    """AssetType enum — per-scene asset types tracked in status."""

    def test_has_text(self):
        from story_video.models import AssetType

        assert AssetType.TEXT == "text"

    def test_has_narration_text(self):
        from story_video.models import AssetType

        assert AssetType.NARRATION_TEXT == "narration_text"

    def test_has_audio(self):
        from story_video.models import AssetType

        assert AssetType.AUDIO == "audio"

    def test_has_image(self):
        from story_video.models import AssetType

        assert AssetType.IMAGE == "image"

    def test_has_captions(self):
        from story_video.models import AssetType

        assert AssetType.CAPTIONS == "captions"

    def test_has_video_segment(self):
        from story_video.models import AssetType

        assert AssetType.VIDEO_SEGMENT == "video_segment"

    def test_has_exactly_six_members(self):
        from story_video.models import AssetType

        assert len(AssetType) == 6


class TestPipelinePhase:
    """PipelinePhase enum — all pipeline phases across both flows."""

    def test_creative_phases_exist(self):
        """original/inspired_by phases."""
        from story_video.models import PipelinePhase

        assert PipelinePhase.ANALYSIS == "analysis"
        assert PipelinePhase.STORY_BIBLE == "story_bible"
        assert PipelinePhase.OUTLINE == "outline"
        assert PipelinePhase.SCENE_PROSE == "scene_prose"
        assert PipelinePhase.CRITIQUE_REVISION == "critique_revision"

    def test_adapt_phases_exist(self):
        """adapt-only phases."""
        from story_video.models import PipelinePhase

        assert PipelinePhase.SCENE_SPLITTING == "scene_splitting"
        assert PipelinePhase.NARRATION_FLAGGING == "narration_flagging"

    def test_shared_phases_exist(self):
        """Phases shared by all modes."""
        from story_video.models import PipelinePhase

        assert PipelinePhase.IMAGE_PROMPTS == "image_prompts"
        assert PipelinePhase.NARRATION_PREP == "narration_prep"
        assert PipelinePhase.TTS_GENERATION == "tts_generation"
        assert PipelinePhase.IMAGE_GENERATION == "image_generation"
        assert PipelinePhase.CAPTION_GENERATION == "caption_generation"
        assert PipelinePhase.VIDEO_ASSEMBLY == "video_assembly"

    def test_has_exactly_thirteen_members(self):
        """5 creative + 2 adapt + 6 shared = 13 total phases."""
        from story_video.models import PipelinePhase

        assert len(PipelinePhase) == 13


# ---------------------------------------------------------------------------
# Phase sequence helper tests
# ---------------------------------------------------------------------------


class TestPhaseSequences:
    """Phase sequences for each input mode."""

    def test_creative_flow_sequence(self):
        """original/inspired_by mode uses creative phases then shared phases."""
        from story_video.models import CREATIVE_FLOW_PHASES, PipelinePhase

        expected = [
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
        ]
        assert CREATIVE_FLOW_PHASES == expected

    def test_adapt_flow_sequence(self):
        """adapt mode uses adapt-specific phases then shared phases."""
        from story_video.models import ADAPT_FLOW_PHASES, PipelinePhase

        expected = [
            PipelinePhase.SCENE_SPLITTING,
            PipelinePhase.NARRATION_FLAGGING,
            PipelinePhase.IMAGE_PROMPTS,
            PipelinePhase.NARRATION_PREP,
            PipelinePhase.TTS_GENERATION,
            PipelinePhase.IMAGE_GENERATION,
            PipelinePhase.CAPTION_GENERATION,
            PipelinePhase.VIDEO_ASSEMBLY,
        ]
        assert ADAPT_FLOW_PHASES == expected

    def test_shared_phases_are_shared(self):
        """The trailing shared phases are the same in both flows."""
        from story_video.models import ADAPT_FLOW_PHASES, CREATIVE_FLOW_PHASES

        shared_in_creative = CREATIVE_FLOW_PHASES[-6:]
        shared_in_adapt = ADAPT_FLOW_PHASES[-6:]
        assert shared_in_creative == shared_in_adapt


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------


class TestStoryConfig:
    """StoryConfig — story generation parameters."""

    def test_defaults(self):
        from story_video.models import StoryConfig

        config = StoryConfig()
        assert config.target_duration_minutes == 30
        assert config.words_per_minute == 150
        assert config.scene_word_target == 1800
        assert config.scene_word_min == 500
        assert config.scene_word_max == 3000

    def test_custom_values(self):
        from story_video.models import StoryConfig

        config = StoryConfig(target_duration_minutes=60, scene_word_target=2000)
        assert config.target_duration_minutes == 60
        assert config.scene_word_target == 2000

    def test_rejects_negative_duration(self):
        from story_video.models import StoryConfig

        with pytest.raises(ValidationError):
            StoryConfig(target_duration_minutes=-1)

    def test_rejects_zero_words_per_minute(self):
        from story_video.models import StoryConfig

        with pytest.raises(ValidationError):
            StoryConfig(words_per_minute=0)

    def test_serialization_roundtrip(self):
        from story_video.models import StoryConfig

        config = StoryConfig(target_duration_minutes=45)
        data = config.model_dump()
        restored = StoryConfig(**data)
        assert restored == config


class TestTTSConfig:
    """TTSConfig — text-to-speech parameters."""

    def test_defaults(self):
        from story_video.models import TTSConfig

        config = TTSConfig()
        assert config.provider == "openai"
        assert config.model == "tts-1-hd"
        assert config.voice == "nova"
        assert config.speed == 1.0
        assert config.output_format == "mp3"

    def test_custom_voice(self):
        from story_video.models import TTSConfig

        config = TTSConfig(voice="alloy")
        assert config.voice == "alloy"

    def test_rejects_non_positive_speed(self):
        from story_video.models import TTSConfig

        with pytest.raises(ValidationError):
            TTSConfig(speed=0.0)

    def test_serialization_roundtrip(self):
        from story_video.models import TTSConfig

        config = TTSConfig(voice="echo", speed=1.2)
        data = config.model_dump()
        restored = TTSConfig(**data)
        assert restored == config


class TestImageConfig:
    """ImageConfig — image generation parameters."""

    def test_defaults(self):
        from story_video.models import ImageConfig

        config = ImageConfig()
        assert config.provider == "openai"
        assert config.model == "dall-e-3"
        assert config.size == "1024x1024"
        assert config.quality == "standard"
        assert config.style == "vivid"
        assert config.style_prefix == "Cinematic digital painting, dramatic lighting:"

    def test_custom_values(self):
        from story_video.models import ImageConfig

        config = ImageConfig(quality="hd", style="natural")
        assert config.quality == "hd"
        assert config.style == "natural"

    def test_serialization_roundtrip(self):
        from story_video.models import ImageConfig

        config = ImageConfig(quality="hd")
        data = config.model_dump()
        restored = ImageConfig(**data)
        assert restored == config


class TestVideoConfig:
    """VideoConfig — video assembly parameters."""

    def test_defaults(self):
        from story_video.models import VideoConfig

        config = VideoConfig()
        assert config.resolution == "1920x1080"
        assert config.fps == 30
        assert config.codec == "libx264"
        assert config.crf == 18
        assert config.background_mode == "blur"
        assert config.background_blur_radius == 40
        assert config.background_image is None
        assert config.ken_burns_zoom == 1.08
        assert config.transition_duration == 1.5
        assert config.fade_in_duration == 2.0
        assert config.fade_out_duration == 3.0

    def test_background_image_optional(self):
        from story_video.models import VideoConfig

        config = VideoConfig(background_image=Path("/some/image.png"))
        assert config.background_image == Path("/some/image.png")

    def test_rejects_negative_fps(self):
        from story_video.models import VideoConfig

        with pytest.raises(ValidationError):
            VideoConfig(fps=-1)

    def test_rejects_negative_crf(self):
        from story_video.models import VideoConfig

        with pytest.raises(ValidationError):
            VideoConfig(crf=-1)

    def test_serialization_roundtrip(self):
        from story_video.models import VideoConfig

        config = VideoConfig(fps=60, ken_burns_zoom=1.12)
        data = config.model_dump()
        restored = VideoConfig(**data)
        assert restored == config


class TestSubtitleConfig:
    """SubtitleConfig — subtitle rendering parameters."""

    def test_defaults(self):
        from story_video.models import SubtitleConfig

        config = SubtitleConfig()
        assert config.font == "Montserrat"
        assert config.font_fallback == "Arial"
        assert config.font_size == 48
        assert config.color == "#FFFFFF"
        assert config.outline_color == "#000000"
        assert config.outline_width == 3
        assert config.position_bottom == 80
        assert config.max_chars_per_line == 42
        assert config.max_lines == 2

    def test_custom_font(self):
        from story_video.models import SubtitleConfig

        config = SubtitleConfig(font="Roboto", font_size=36)
        assert config.font == "Roboto"
        assert config.font_size == 36

    def test_rejects_non_positive_font_size(self):
        from story_video.models import SubtitleConfig

        with pytest.raises(ValidationError):
            SubtitleConfig(font_size=0)

    def test_rejects_non_positive_max_lines(self):
        from story_video.models import SubtitleConfig

        with pytest.raises(ValidationError):
            SubtitleConfig(max_lines=0)

    def test_serialization_roundtrip(self):
        from story_video.models import SubtitleConfig

        config = SubtitleConfig(font="Helvetica")
        data = config.model_dump()
        restored = SubtitleConfig(**data)
        assert restored == config


class TestPipelineConfig:
    """PipelineConfig — pipeline behavior parameters."""

    def test_defaults(self):
        from story_video.models import PipelineConfig

        config = PipelineConfig()
        assert config.autonomous is False
        assert config.max_retries == 3
        assert config.retry_base_delay == 2
        assert config.save_originals_on_revision is True

    def test_autonomous_mode(self):
        from story_video.models import PipelineConfig

        config = PipelineConfig(autonomous=True)
        assert config.autonomous is True

    def test_rejects_negative_retries(self):
        from story_video.models import PipelineConfig

        with pytest.raises(ValidationError):
            PipelineConfig(max_retries=-1)

    def test_serialization_roundtrip(self):
        from story_video.models import PipelineConfig

        config = PipelineConfig(autonomous=True, max_retries=5)
        data = config.model_dump()
        restored = PipelineConfig(**data)
        assert restored == config


class TestOutputConfig:
    """OutputConfig — output directory configuration."""

    def test_default_directory(self):
        from story_video.models import OutputConfig

        config = OutputConfig()
        assert config.directory == Path("./output")

    def test_custom_directory(self):
        from story_video.models import OutputConfig

        config = OutputConfig(directory=Path("/custom/output"))
        assert config.directory == Path("/custom/output")

    def test_serialization_roundtrip(self):
        from story_video.models import OutputConfig

        config = OutputConfig(directory=Path("/tmp/out"))
        data = config.model_dump()
        restored = OutputConfig(**data)
        assert restored == config


class TestAppConfig:
    """AppConfig — top-level config combining all sections."""

    def test_all_defaults(self):
        from story_video.models import AppConfig

        config = AppConfig()
        assert config.story.target_duration_minutes == 30
        assert config.tts.voice == "nova"
        assert config.images.model == "dall-e-3"
        assert config.video.fps == 30
        assert config.subtitles.font == "Montserrat"
        assert config.pipeline.autonomous is False
        assert config.output.directory == Path("./output")

    def test_partial_override(self):
        from story_video.models import AppConfig, StoryConfig

        config = AppConfig(story=StoryConfig(target_duration_minutes=60))
        assert config.story.target_duration_minutes == 60
        # Other sections use defaults
        assert config.tts.voice == "nova"

    def test_serialization_roundtrip(self):
        from story_video.models import AppConfig

        config = AppConfig()
        data = config.model_dump()
        restored = AppConfig(**data)
        assert restored == config

    def test_json_roundtrip(self):
        from story_video.models import AppConfig

        config = AppConfig()
        json_str = config.model_dump_json()
        restored = AppConfig.model_validate_json(json_str)
        assert restored == config


# ---------------------------------------------------------------------------
# Scene asset status tests
# ---------------------------------------------------------------------------


class TestSceneAssetStatus:
    """SceneAssetStatus — per-asset status tracking for a scene."""

    def test_all_default_to_pending(self):
        from story_video.models import SceneAssetStatus, SceneStatus

        status = SceneAssetStatus()
        assert status.text == SceneStatus.PENDING
        assert status.narration_text == SceneStatus.PENDING
        assert status.audio == SceneStatus.PENDING
        assert status.image == SceneStatus.PENDING
        assert status.captions == SceneStatus.PENDING
        assert status.video_segment == SceneStatus.PENDING

    def test_individual_status_update(self):
        from story_video.models import SceneAssetStatus, SceneStatus

        status = SceneAssetStatus(text=SceneStatus.COMPLETED)
        assert status.text == SceneStatus.COMPLETED
        assert status.audio == SceneStatus.PENDING

    def test_serialization_roundtrip(self):
        from story_video.models import SceneAssetStatus, SceneStatus

        status = SceneAssetStatus(
            text=SceneStatus.COMPLETED,
            audio=SceneStatus.FAILED,
        )
        data = status.model_dump()
        restored = SceneAssetStatus(**data)
        assert restored == status

    def test_asset_status_fields_match_asset_type_members(self):
        from story_video.models import AssetType, SceneAssetStatus

        expected_fields = {member.value for member in AssetType}
        actual_fields = set(SceneAssetStatus.model_fields.keys())
        assert actual_fields == expected_fields


# ---------------------------------------------------------------------------
# Scene tests
# ---------------------------------------------------------------------------


class TestScene:
    """Scene — content and metadata for a single story scene."""

    def test_creation_with_required_fields(self):
        from story_video.models import Scene

        scene = Scene(
            scene_number=1,
            title="The Lighthouse",
            prose="The waves crashed against the rocks...",
        )
        assert scene.scene_number == 1
        assert scene.title == "The Lighthouse"
        assert scene.prose == "The waves crashed against the rocks..."

    def test_optional_fields_default_to_none(self):
        from story_video.models import Scene

        scene = Scene(
            scene_number=1,
            title="Opening",
            prose="Once upon a time...",
        )
        assert scene.narration_text is None
        assert scene.image_prompt is None

    def test_asset_status_defaults_to_all_pending(self):
        from story_video.models import Scene, SceneStatus

        scene = Scene(
            scene_number=1,
            title="Opening",
            prose="Once upon a time...",
        )
        assert scene.asset_status.text == SceneStatus.PENDING

    def test_all_fields_populated(self):
        from story_video.models import Scene, SceneAssetStatus, SceneStatus

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
        from story_video.models import Scene

        with pytest.raises(ValidationError):
            Scene(scene_number=0, title="Bad", prose="No")

    def test_rejects_empty_title(self):
        from story_video.models import Scene

        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="", prose="Some text")

    def test_rejects_empty_prose(self):
        from story_video.models import Scene

        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="Title", prose="")

    def test_serialization_roundtrip(self):
        from story_video.models import Scene

        scene = Scene(
            scene_number=1,
            title="Opening",
            prose="Once upon a time...",
            narration_text="Once upon a time.",
            image_prompt="A castle on a hill at sunset",
        )
        data = scene.model_dump()
        restored = Scene(**data)
        assert restored == scene

    def test_json_roundtrip(self):
        from story_video.models import Scene

        scene = Scene(
            scene_number=2,
            title="The Journey",
            prose="They walked for miles...",
        )
        json_str = scene.model_dump_json()
        restored = Scene.model_validate_json(json_str)
        assert restored == scene


# ---------------------------------------------------------------------------
# ProjectMetadata tests
# ---------------------------------------------------------------------------


class TestProjectMetadata:
    """ProjectMetadata — project-level tracking information."""

    def test_creation_with_required_fields(self):
        from story_video.models import InputMode, ProjectMetadata

        project = ProjectMetadata(
            project_id="lighthouse-2026-02-11-abc123",
            mode=InputMode.ORIGINAL,
        )
        assert project.project_id == "lighthouse-2026-02-11-abc123"
        assert project.mode == InputMode.ORIGINAL

    def test_created_at_defaults_to_now(self):
        from story_video.models import InputMode, ProjectMetadata

        before = datetime.now(timezone.utc)
        project = ProjectMetadata(
            project_id="test-project",
            mode=InputMode.ADAPT,
        )
        after = datetime.now(timezone.utc)
        assert before <= project.created_at <= after

    def test_current_phase_defaults_to_none(self):
        from story_video.models import InputMode, ProjectMetadata

        project = ProjectMetadata(
            project_id="test-project",
            mode=InputMode.ORIGINAL,
        )
        assert project.current_phase is None

    def test_status_defaults_to_pending(self):
        from story_video.models import InputMode, PhaseStatus, ProjectMetadata

        project = ProjectMetadata(
            project_id="test-project",
            mode=InputMode.ORIGINAL,
        )
        assert project.status == PhaseStatus.PENDING

    def test_scenes_defaults_to_empty_list(self):
        from story_video.models import InputMode, ProjectMetadata

        project = ProjectMetadata(
            project_id="test-project",
            mode=InputMode.ORIGINAL,
        )
        assert project.scenes == []

    def test_config_defaults_to_app_config_defaults(self):
        from story_video.models import InputMode, ProjectMetadata

        project = ProjectMetadata(
            project_id="test-project",
            mode=InputMode.ORIGINAL,
        )
        assert project.config.story.target_duration_minutes == 30
        assert project.config.tts.voice == "nova"

    def test_rejects_empty_project_id(self):
        from story_video.models import InputMode, ProjectMetadata

        with pytest.raises(ValidationError):
            ProjectMetadata(project_id="", mode=InputMode.ORIGINAL)

    def test_full_creation(self):
        from story_video.models import (
            AppConfig,
            InputMode,
            PhaseStatus,
            PipelinePhase,
            ProjectMetadata,
            Scene,
            StoryConfig,
        )

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

    def test_serialization_roundtrip(self):
        from story_video.models import (
            InputMode,
            PhaseStatus,
            PipelinePhase,
            ProjectMetadata,
            Scene,
        )

        project = ProjectMetadata(
            project_id="roundtrip-test",
            mode=InputMode.ADAPT,
            current_phase=PipelinePhase.SCENE_SPLITTING,
            status=PhaseStatus.IN_PROGRESS,
            scenes=[
                Scene(scene_number=1, title="Part One", prose="The story begins..."),
            ],
        )
        data = project.model_dump()
        restored = ProjectMetadata(**data)
        assert restored.project_id == project.project_id
        assert restored.mode == project.mode
        assert restored.current_phase == project.current_phase
        assert restored.status == project.status
        assert len(restored.scenes) == 1

    def test_json_roundtrip(self):
        from story_video.models import InputMode, ProjectMetadata

        project = ProjectMetadata(
            project_id="json-test",
            mode=InputMode.ORIGINAL,
        )
        json_str = project.model_dump_json()
        restored = ProjectMetadata.model_validate_json(json_str)
        assert restored.project_id == project.project_id
        assert restored.mode == project.mode
