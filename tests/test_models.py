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
    AudioAsset,
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    ImageConfig,
    ImageTag,
    InputMode,
    MusicTag,
    NarrationSegment,
    PhaseStatus,
    PipelinePhase,
    ProjectMetadata,
    Scene,
    SceneAssetStatus,
    SceneAudioCue,
    SceneImagePrompt,
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

    def test_construction_defaults_roundtrip_and_field_match(self):
        """Individual status, defaults, serialization roundtrip, and field-AssetType match."""
        status = SceneAssetStatus(text=SceneStatus.COMPLETED)
        assert status.text == SceneStatus.COMPLETED
        assert status.audio == SceneStatus.PENDING

        # Serialization roundtrip
        full = SceneAssetStatus(
            text=SceneStatus.COMPLETED,
            audio=SceneStatus.FAILED,
        )
        data = full.model_dump()
        restored = SceneAssetStatus(**data)
        assert restored == full

        # Fields match AssetType members
        expected_fields = {member.value for member in AssetType}
        actual_fields = set(SceneAssetStatus.model_fields.keys())
        assert actual_fields == expected_fields


# ---------------------------------------------------------------------------
# Scene tests
# ---------------------------------------------------------------------------


class TestScene:
    """Scene — content and metadata for a single story scene."""

    def test_valid_construction_and_roundtrip(self):
        """All fields, summary defaults/provided, JSON roundtrip with and without summary."""
        scene = Scene(
            scene_number=3,
            title="The Confrontation",
            prose="She stood her ground...",
            narration_text="She stood her ground.",
            image_prompts=[
                SceneImagePrompt(
                    key=None,
                    prompt="A woman standing firm in a dark alley, cinematic lighting",
                    position=0,
                ),
            ],
            asset_status=SceneAssetStatus(
                text=SceneStatus.COMPLETED,
                narration_text=SceneStatus.COMPLETED,
            ),
        )
        assert scene.scene_number == 3
        assert scene.narration_text == "She stood her ground."
        assert len(scene.image_prompts) == 1
        assert scene.asset_status.text == SceneStatus.COMPLETED

        # Summary defaults to None
        simple = Scene(scene_number=1, title="Opening", prose="The story begins.")
        assert simple.summary is None

        # Summary stored when provided
        with_summary = Scene(
            scene_number=1,
            title="Opening",
            prose="The story begins.",
            summary="Hero arrives at the castle.",
        )
        assert with_summary.summary == "Hero arrives at the castle."

        # JSON roundtrip
        json_str = simple.model_dump_json()
        restored = Scene.model_validate_json(json_str)
        assert restored == simple

        # JSON roundtrip with summary
        json_str2 = with_summary.model_dump_json()
        restored2 = Scene.model_validate_json(json_str2)
        assert restored2.summary == "Hero arrives at the castle."

    def test_rejects_non_positive_scene_number(self):
        with pytest.raises(ValidationError):
            Scene(scene_number=0, title="Bad", prose="No")

    def test_rejects_empty_title(self):
        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="", prose="Some text")

    def test_rejects_empty_prose(self):
        with pytest.raises(ValidationError):
            Scene(scene_number=1, title="Title", prose="")


# ---------------------------------------------------------------------------
# ProjectMetadata tests
# ---------------------------------------------------------------------------


class TestProjectMetadata:
    """ProjectMetadata — project-level tracking information."""

    def test_valid_construction_and_roundtrip(self):
        """Required fields, full creation, and JSON roundtrip."""
        project = ProjectMetadata(
            project_id="lighthouse-2026-02-11-abc123",
            mode=InputMode.ORIGINAL,
        )
        assert project.project_id == "lighthouse-2026-02-11-abc123"
        assert project.mode == InputMode.ORIGINAL

        # Full creation with all fields
        full = ProjectMetadata(
            project_id="my-story-2026",
            mode=InputMode.INSPIRED_BY,
            current_phase=PipelinePhase.ANALYSIS,
            status=PhaseStatus.IN_PROGRESS,
            config=AppConfig(story=StoryConfig(target_duration_minutes=60)),
            scenes=[
                Scene(scene_number=1, title="Opening", prose="It began..."),
            ],
        )
        assert full.mode == InputMode.INSPIRED_BY
        assert full.current_phase == PipelinePhase.ANALYSIS
        assert full.status == PhaseStatus.IN_PROGRESS
        assert len(full.scenes) == 1
        assert full.config.story.target_duration_minutes == 60

        # JSON roundtrip
        json_str = project.model_dump_json()
        restored = ProjectMetadata.model_validate_json(json_str)
        assert restored.project_id == project.project_id
        assert restored.mode == project.mode

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

    def test_valid_construction_and_roundtrip(self):
        """Defaults, custom default_voice, and serialization roundtrip."""
        header = StoryHeader(voices={"narrator": "nova"})
        assert header.default_voice == "narrator"

        custom = StoryHeader(
            voices={"narrator": "nova", "bob": "echo"},
            default_voice="bob",
        )
        assert custom.default_voice == "bob"

        # Serialization roundtrip
        full = StoryHeader(voices={"jane": "nova", "bob": "alloy"}, default_voice="jane")
        data = full.model_dump()
        restored = StoryHeader(**data)
        assert restored == full

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

    def test_allows_extra_fields(self):
        """Extra YAML fields are silently ignored, not rejected."""
        header = StoryHeader(
            voices={"narrator": "nova"},
            title="My Story",  # extra field not in schema
        )
        assert header.voices == {"narrator": "nova"}


# ---------------------------------------------------------------------------
# NarrationSegment tests
# ---------------------------------------------------------------------------


class TestNarrationSegment:
    """NarrationSegment model for parsed text chunks."""

    def test_valid_construction(self):
        """Valid segment with mood and pause_duration; serialization roundtrip."""
        seg = NarrationSegment(
            text="Hello",
            voice="nova",
            voice_label="narrator",
            scene_number=1,
            segment_index=0,
        )
        assert seg.text == "Hello"
        assert seg.mood is None

        seg_mood = NarrationSegment(
            text="Goodbye",
            voice="nova",
            voice_label="narrator",
            mood="sad",
            scene_number=1,
            segment_index=0,
        )
        assert seg_mood.mood == "sad"

        seg_pause = NarrationSegment(
            text="[pause]",
            voice="nova",
            voice_label="narrator",
            scene_number=1,
            segment_index=0,
            pause_duration=0.5,
        )
        assert seg_pause.pause_duration == 0.5

        # Serialization roundtrip
        seg_full = NarrationSegment(
            text="Hello world",
            voice="nova",
            voice_label="narrator",
            mood="happy",
            scene_number=2,
            segment_index=3,
        )
        data = seg_full.model_dump()
        restored = NarrationSegment(**data)
        assert restored == seg_full

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

    def test_accepts_valid_lowercase_hex(self):
        """Lowercase hex passes."""
        config = SubtitleConfig(color="#ff0000")
        assert config.color == "#ff0000"


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


# ---------------------------------------------------------------------------
# ImageTag tests
# ---------------------------------------------------------------------------


class TestImageTag:
    """ImageTag stores tag key and character offset."""

    def test_construction(self):
        tag = ImageTag(key="lighthouse", position=42)
        assert tag.key == "lighthouse"
        assert tag.position == 42

    def test_position_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            ImageTag(key="x", position=-1)


# ---------------------------------------------------------------------------
# SceneImagePrompt tests
# ---------------------------------------------------------------------------


class TestSceneImagePrompt:
    """SceneImagePrompt stores key, prompt text, and position."""

    def test_construction_with_key(self):
        sip = SceneImagePrompt(
            key="lighthouse", prompt="A weathered lighthouse at dawn", position=42
        )
        assert sip.key == "lighthouse"
        assert sip.prompt == "A weathered lighthouse at dawn"
        assert sip.position == 42

    def test_construction_auto_generated(self):
        sip = SceneImagePrompt(key=None, prompt="Auto-generated prompt", position=0)
        assert sip.key is None
        assert sip.position == 0

    def test_prompt_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            SceneImagePrompt(key=None, prompt="", position=0)


# ---------------------------------------------------------------------------
# AudioAsset tests
# ---------------------------------------------------------------------------


class TestAudioAsset:
    """AudioAsset stores audio file path and mixing parameters."""

    def test_construction_with_defaults(self):
        asset = AudioAsset(file="sounds/rain.mp3")
        assert asset.file == "sounds/rain.mp3"
        assert asset.volume == 0.3
        assert asset.loop is False
        assert asset.fade_in == 0.0
        assert asset.fade_out == 0.0

    def test_construction_with_all_fields(self):
        asset = AudioAsset(file="sounds/rain.mp3", volume=0.5, loop=True, fade_in=2.0, fade_out=1.5)
        assert asset.volume == 0.5
        assert asset.loop is True
        assert asset.fade_in == 2.0
        assert asset.fade_out == 1.5

    def test_empty_file_rejected(self):
        with pytest.raises(ValidationError):
            AudioAsset(file="")

    def test_volume_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            AudioAsset(file="x.mp3", volume=-0.1)

    def test_volume_above_one_rejected(self):
        with pytest.raises(ValidationError):
            AudioAsset(file="x.mp3", volume=1.1)

    def test_volume_boundary_zero_accepted(self):
        asset = AudioAsset(file="x.mp3", volume=0.0)
        assert asset.volume == 0.0

    def test_volume_boundary_one_accepted(self):
        asset = AudioAsset(file="x.mp3", volume=1.0)
        assert asset.volume == 1.0

    def test_negative_fade_in_rejected(self):
        with pytest.raises(ValidationError):
            AudioAsset(file="x.mp3", fade_in=-1.0)

    def test_negative_fade_out_rejected(self):
        with pytest.raises(ValidationError):
            AudioAsset(file="x.mp3", fade_out=-0.5)


# ---------------------------------------------------------------------------
# MusicTag tests
# ---------------------------------------------------------------------------


class TestMusicTag:
    """MusicTag stores tag key and character offset."""

    def test_construction(self):
        tag = MusicTag(key="rain", position=42)
        assert tag.key == "rain"
        assert tag.position == 42

    def test_position_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            MusicTag(key="x", position=-1)

    def test_empty_key_rejected(self):
        with pytest.raises(ValidationError):
            MusicTag(key="", position=0)


# ---------------------------------------------------------------------------
# SceneAudioCue tests
# ---------------------------------------------------------------------------


class TestSceneAudioCue:
    """SceneAudioCue stores key, position, and computed start time."""

    def test_construction_with_defaults(self):
        cue = SceneAudioCue(key="rain", position=100)
        assert cue.key == "rain"
        assert cue.position == 100
        assert cue.start_time == 0.0

    def test_construction_with_start_time(self):
        cue = SceneAudioCue(key="thunder", position=50, start_time=4.5)
        assert cue.start_time == 4.5


# ---------------------------------------------------------------------------
# StoryHeader audio map tests
# ---------------------------------------------------------------------------


class TestStoryHeaderAudio:
    """StoryHeader accepts optional audio map."""

    def test_audio_defaults_to_empty(self):
        h = StoryHeader(voices={"narrator": "nova"})
        assert h.audio == {}

    def test_audio_with_entries(self):
        h = StoryHeader(
            voices={"narrator": "nova"},
            audio={"rain": AudioAsset(file="rain.mp3", volume=0.2)},
        )
        assert "rain" in h.audio
        assert h.audio["rain"].file == "rain.mp3"


# ---------------------------------------------------------------------------
# Scene audio_cues tests
# ---------------------------------------------------------------------------


class TestSceneAudioCues:
    """Scene accepts optional audio_cues list."""

    def test_audio_cues_defaults_to_empty(self):
        s = Scene(scene_number=1, title="Test", prose="Some text.")
        assert s.audio_cues == []

    def test_audio_cues_populated(self):
        cue = SceneAudioCue(key="rain", position=10, start_time=2.0)
        s = Scene(scene_number=1, title="Test", prose="Some text.", audio_cues=[cue])
        assert len(s.audio_cues) == 1
        assert s.audio_cues[0].key == "rain"
