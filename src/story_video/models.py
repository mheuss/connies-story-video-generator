"""Pydantic data models for the Story Video Generator.

This module defines all data shapes used across the application:
- Enums for input modes, statuses, asset types, and pipeline phases
- Config models for each subsystem (story, TTS, images, video, subtitles, pipeline)
- Scene and project metadata models

Pure data definitions only — no file I/O, no business logic.
"""

import re
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
RESOLUTION_RE = re.compile(r"^\d+x\d+$")
# Adapt-mode heuristic for scene splitting — not used for cost/duration estimation
WORDS_PER_SCENE_ESTIMATE = 600

__all__ = [
    "ADAPT_FLOW_PHASES",
    "AppConfig",
    "AssetType",
    "AudioAsset",
    "CREATIVE_FLOW_PHASES",
    "CaptionResult",
    "CaptionSegment",
    "CaptionWord",
    "HEX_COLOR_RE",
    "ImageConfig",
    "ImageTag",
    "InputMode",
    "KNOWN_TTS_PROVIDERS",
    "MusicTag",
    "NarrationSegment",
    "PhaseStatus",
    "PipelineConfig",
    "PipelinePhase",
    "ProjectMetadata",
    "RESOLUTION_RE",
    "Scene",
    "SceneAssetStatus",
    "SceneAudioCue",
    "SceneImagePrompt",
    "SceneStatus",
    "StoryConfig",
    "StoryHeader",
    "SubtitleConfig",
    "TTSConfig",
    "VideoConfig",
    "WORDS_PER_SCENE_ESTIMATE",
]

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InputMode(str, Enum):
    """Three input modes for story generation.

    - ORIGINAL: topic/premise input, AI writes from scratch
    - INSPIRED_BY: existing story as inspiration, AI writes a different story
    - ADAPT: finished story, AI narrates word-for-word
    """

    ORIGINAL = "original"
    INSPIRED_BY = "inspired_by"
    ADAPT = "adapt"


class PhaseStatus(str, Enum):
    """Phase-level status tracking.

    Transitions:
        pending -> in_progress -> completed
        pending -> in_progress -> awaiting_review (semi-automated mode)
        pending -> in_progress -> failed
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"


class SceneStatus(str, Enum):
    """Scene-level status tracking (per asset).

    Transitions:
        pending -> in_progress -> completed
        pending -> in_progress -> failed
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(str, Enum):
    """Per-scene asset types tracked in status.

    Each scene tracks the status of these seven asset types independently.
    """

    TEXT = "text"
    NARRATION_TEXT = "narration_text"
    IMAGE_PROMPT = "image_prompt"
    AUDIO = "audio"
    IMAGE = "image"
    CAPTIONS = "captions"
    VIDEO_SEGMENT = "video_segment"


class PipelinePhase(str, Enum):
    """All pipeline phases across both creative and adaptation flows.

    Creative flow (original/inspired_by):
        analysis -> story_bible -> outline -> scene_prose -> critique_revision
        -> image_prompts -> narration_prep -> tts_generation -> image_generation
        -> caption_generation -> video_assembly

    Adaptation flow (adapt):
        analysis -> scene_splitting -> narration_flagging -> image_prompts
        -> narration_prep -> tts_generation -> image_generation
        -> caption_generation -> video_assembly
    """

    # Creative flow phases (original / inspired_by)
    ANALYSIS = "analysis"
    STORY_BIBLE = "story_bible"
    OUTLINE = "outline"
    SCENE_PROSE = "scene_prose"
    CRITIQUE_REVISION = "critique_revision"

    # Adaptation flow phases (adapt)
    SCENE_SPLITTING = "scene_splitting"
    NARRATION_FLAGGING = "narration_flagging"

    # Shared phases (both flows)
    IMAGE_PROMPTS = "image_prompts"
    NARRATION_PREP = "narration_prep"
    TTS_GENERATION = "tts_generation"
    IMAGE_GENERATION = "image_generation"
    CAPTION_GENERATION = "caption_generation"
    VIDEO_ASSEMBLY = "video_assembly"


# ---------------------------------------------------------------------------
# Phase sequences — ordered tuples of phases for each input mode
# ---------------------------------------------------------------------------


CREATIVE_FLOW_PHASES: tuple[PipelinePhase, ...] = (
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
"""Phase sequence for original and inspired_by modes (immutable)."""

ADAPT_FLOW_PHASES: tuple[PipelinePhase, ...] = (
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
"""Phase sequence for adapt mode (immutable)."""


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class StoryConfig(BaseModel):
    """Story generation parameters.

    Controls target duration, pacing, and scene sizing for the story writer.

    Fields:
        target_duration_minutes: Target video duration in minutes.
        words_per_minute: Assumed narration speed for duration calculations.
        scene_word_target: Ideal word count per scene.
        scene_word_min: Minimum acceptable word count per scene.
        scene_word_max: Maximum acceptable word count per scene.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_duration_minutes: int = Field(default=30, gt=0)
    words_per_minute: int = Field(default=150, gt=0)
    scene_word_target: int = Field(default=1800, gt=0)
    scene_word_min: int = Field(default=500, gt=0)
    scene_word_max: int = Field(default=3000, gt=0)

    @model_validator(mode="after")
    def _validate_word_count_bounds(self) -> "StoryConfig":
        if self.scene_word_min > self.scene_word_max:
            msg = (
                f"scene_word_min ({self.scene_word_min}) must not exceed "
                f"scene_word_max ({self.scene_word_max})"
            )
            raise ValueError(msg)
        if self.scene_word_target < self.scene_word_min:
            msg = (
                f"scene_word_target ({self.scene_word_target}) must not be below "
                f"scene_word_min ({self.scene_word_min})"
            )
            raise ValueError(msg)
        if self.scene_word_target > self.scene_word_max:
            msg = (
                f"scene_word_target ({self.scene_word_target}) must not exceed "
                f"scene_word_max ({self.scene_word_max})"
            )
            raise ValueError(msg)
        return self


KNOWN_TTS_PROVIDERS = {"openai", "elevenlabs"}


class TTSConfig(BaseModel):
    """Text-to-speech generation parameters.

    Controls which TTS provider, model, voice, and output settings to use.

    Fields:
        provider: TTS service provider name.
        model: Specific TTS model identifier.
        voice: Voice name for narration.
        speed: Playback speed multiplier.
        output_format: Audio file format.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4o-mini-tts")
    voice: str = Field(default="nova")
    speed: float = Field(default=1.0, gt=0)
    output_format: str = Field(default="mp3")

    @field_validator("provider")
    @classmethod
    def _validate_tts_provider(cls, v: str) -> str:
        if v not in KNOWN_TTS_PROVIDERS:
            msg = f"Unknown TTS provider: {v!r}. Choose from: {sorted(KNOWN_TTS_PROVIDERS)}"
            raise ValueError(msg)
        return v

    @property
    def file_extension(self) -> str:
        """Extract file extension from output_format.

        ElevenLabs uses compound format strings like ``mp3_44100_128``.
        Returns just the codec portion for use as a file extension.
        """
        return self.output_format.split("_")[0]


class AudioAsset(BaseModel):
    """An audio asset defined in the story header for background music/SFX.

    Fields:
        file: Path to audio file, relative to the source story directory.
        volume: Playback volume from 0.0 (silent) to 1.0 (full).
        loop: If True, loop the audio to fill remaining scene duration.
        fade_in: Fade-in duration in seconds.
        fade_out: Fade-out duration in seconds.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(min_length=1)
    volume: float = Field(default=0.3, ge=0.0, le=1.0)
    loop: bool = Field(default=False)
    fade_in: float = Field(default=0.0, ge=0.0)
    fade_out: float = Field(default=0.0, ge=0.0)


class StoryHeader(BaseModel):
    """Parsed front matter from a story file.

    Fields:
        voices: Mapping from character labels to provider-specific voice IDs.
        default_voice: Label used for text without an explicit voice tag.
        images: Mapping from image tag keys to image prompt strings.
        audio: Mapping from music tag keys to AudioAsset configs.
    """

    model_config = ConfigDict(frozen=True)

    voices: dict[str, str] = Field(min_length=1)
    default_voice: str = Field(default="narrator")
    images: dict[str, str] = Field(default_factory=dict)
    audio: dict[str, AudioAsset] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_default_voice_in_voices(self) -> "StoryHeader":
        """Ensure default_voice refers to a label defined in voices."""
        if self.default_voice not in self.voices:
            msg = (
                f"default_voice '{self.default_voice}' is not defined in voices. "
                f"Defined voices: {', '.join(sorted(self.voices.keys()))}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_image_prompts_non_empty(self) -> "StoryHeader":
        """Ensure no image prompt is empty or whitespace-only."""
        for key, prompt in self.images.items():
            if not prompt.strip():
                msg = f"Image prompt for '{key}' is empty or whitespace-only."
                raise ValueError(msg)
        return self


class NarrationSegment(BaseModel):
    """A chunk of narration text with voice and mood metadata.

    Fields:
        text: Actual text to speak (tags stripped).
        voice: Resolved voice ID (e.g., "nova").
        voice_label: Original label from the tag (e.g., "jane").
        mood: Emotion instruction or None.
        pause_duration: Seconds of silence (set for pause segments, None for speech).
        scene_number: Which scene this segment belongs to.
        segment_index: Order within the scene.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    voice_label: str = Field(min_length=1)
    mood: str | None = Field(default=None)
    pause_duration: float | None = Field(default=None, gt=0)
    scene_number: int = Field(ge=1)
    segment_index: int = Field(ge=0)


class ImageTag(BaseModel):
    """An inline image tag parsed from story text.

    Fields:
        key: Tag key referencing an entry in the YAML images map.
        position: Character offset in the original scene text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    position: int = Field(ge=0)


class MusicTag(BaseModel):
    """An inline music tag parsed from story text.

    Fields:
        key: Tag key referencing an entry in the YAML audio map.
        position: Character offset in the text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    position: int = Field(ge=0)


class SceneAudioCue(BaseModel):
    """A music/SFX cue for a scene, mapped from an inline music tag.

    Fields:
        key: Tag key referencing an entry in the YAML audio map.
        position: Character offset in stripped text (for caption alignment).
        start_time: Computed timestamp in seconds (set during video assembly).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    position: int = Field(ge=0)
    start_time: float = Field(default=0.0, ge=0.0)


class SceneImagePrompt(BaseModel):
    """An image prompt for a scene, either YAML-defined or auto-generated.

    Fields:
        key: Tag key from YAML header, or None for auto-generated prompts.
        prompt: The full image prompt text.
        position: Character offset in the original scene text (for ordering).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str | None
    prompt: str = Field(min_length=1)
    position: int = Field(ge=0, default=0)


class ImageConfig(BaseModel):
    """Image generation parameters.

    Controls the image provider, model, dimensions, quality, and style prefix
    prepended to each image prompt.

    Fields:
        provider: Image generation service provider name.
        model: Specific image model identifier.
        size: Image dimensions as "WIDTHxHEIGHT".
        quality: Image quality tier (model-dependent).
        style: DALL-E style parameter (None for GPT Image models).
        style_prefix: Text prepended to every image prompt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(default="openai")
    model: str = Field(default="gpt-image-1.5")
    size: str = Field(default="1536x1024")
    quality: str = Field(default="medium")
    style: str | None = Field(default=None)
    style_prefix: str = Field(default="Cinematic, dramatic lighting:")

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: str) -> str:
        """Validate size is in WIDTHxHEIGHT format."""
        if not RESOLUTION_RE.match(v):
            msg = f"Size must be 'WIDTHxHEIGHT', got '{v}'"
            raise ValueError(msg)
        return v


class VideoConfig(BaseModel):
    """Video assembly parameters.

    Controls resolution, encoding, background treatment, and transition
    timing for FFmpeg video assembly.

    Fields:
        resolution: Video dimensions as "WIDTHxHEIGHT".
        fps: Frames per second.
        codec: FFmpeg video codec.
        crf: Constant Rate Factor for encoding quality (lower = better).
        background_blur_radius: Gaussian blur radius for blurred background.
        transition_duration: Video crossfade duration between scenes in seconds.
        audio_transition_duration: Audio crossfade duration between scenes in seconds.
        fade_in_duration: Fade-from-black duration at video start in seconds.
        fade_out_duration: Fade-to-black duration at video end in seconds.
        end_hold_duration: Minimum seconds to hold the last frame after narration
            ends. The actual hold is at least as long as fade_out_duration so the
            fade never overlaps narration audio.
        lead_in_duration: Seconds of silence before narration starts, giving the
            opening image time to fade in from black.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolution: str = Field(default="1920x1080")
    fps: int = Field(default=30, gt=0)
    codec: str = Field(default="libx264")
    crf: int = Field(default=18, ge=0)
    background_blur_radius: int = Field(default=40, ge=0)
    transition_duration: float = Field(default=1.5, ge=0)
    audio_transition_duration: float = Field(default=0.05, ge=0)
    fade_in_duration: float = Field(default=2.0, ge=0)
    fade_out_duration: float = Field(default=3.0, ge=0)
    end_hold_duration: float = Field(default=2.0, ge=0)
    lead_in_duration: float = Field(default=2.0, ge=0)

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v: str) -> str:
        """Validate resolution is in WIDTHxHEIGHT format."""
        if not RESOLUTION_RE.match(v):
            msg = f"Resolution must be 'WIDTHxHEIGHT', got '{v}'"
            raise ValueError(msg)
        return v


class SubtitleConfig(BaseModel):
    """Subtitle rendering parameters.

    Controls font, color, positioning, and line wrapping for burned-in subtitles.

    Fields:
        font: Primary font name.
        font_size: Font size in pixels at 1080p.
        color: Text color as hex string.
        outline_color: Outline color as hex string.
        outline_width: Outline width in pixels.
        position_bottom: Distance from bottom edge in pixels.
        max_chars_per_line: Maximum characters per subtitle line.
        max_lines: Maximum number of subtitle lines.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    font: str = Field(default="Montserrat")
    font_size: int = Field(default=48, gt=0)
    color: str = Field(default="#FFFFFF")
    outline_color: str = Field(default="#000000")
    outline_width: int = Field(default=3, ge=0)
    position_bottom: int = Field(default=80, ge=0)
    max_chars_per_line: int = Field(default=42, gt=0)
    max_lines: int = Field(default=2, gt=0)

    @field_validator("color", "outline_color")
    @classmethod
    def _validate_hex_color(cls, v: str) -> str:
        if not HEX_COLOR_RE.match(v):
            msg = f"Invalid hex color: {v!r} (expected #RRGGBB format)"
            raise ValueError(msg)
        return v


class PipelineConfig(BaseModel):
    """Pipeline behavior parameters.

    Controls whether the pipeline runs autonomously or pauses for review.

    Fields:
        autonomous: If True, skip human review checkpoints.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    autonomous: bool = Field(default=False)


class AppConfig(BaseModel):
    """Top-level application configuration combining all subsystem configs.

    Each section has sensible defaults per the design document (section 13).
    Extra fields are forbidden to catch config typos at load time.

    Fields:
        story: Story generation parameters.
        tts: Text-to-speech parameters.
        images: Image generation parameters.
        video: Video assembly parameters.
        subtitles: Subtitle rendering parameters.
        pipeline: Pipeline behavior parameters.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    story: StoryConfig = Field(default_factory=StoryConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    images: ImageConfig = Field(default_factory=ImageConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    subtitles: SubtitleConfig = Field(default_factory=SubtitleConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)


# ---------------------------------------------------------------------------
# Scene and project models
# ---------------------------------------------------------------------------


class SceneAssetStatus(BaseModel):
    """Per-asset status tracking for a single scene.

    Tracks the production status of each asset type independently,
    allowing partial completion and targeted retries.

    Fields:
        text: Status of the prose text asset.
        narration_text: Status of the TTS-optimized narration text.
        image_prompt: Status of the generated image prompt.
        audio: Status of the generated audio file.
        image: Status of the generated scene image.
        captions: Status of the generated caption data.
        video_segment: Status of the rendered video segment.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    text: SceneStatus = Field(default=SceneStatus.PENDING)
    narration_text: SceneStatus = Field(default=SceneStatus.PENDING)
    image_prompt: SceneStatus = Field(default=SceneStatus.PENDING)
    audio: SceneStatus = Field(default=SceneStatus.PENDING)
    image: SceneStatus = Field(default=SceneStatus.PENDING)
    captions: SceneStatus = Field(default=SceneStatus.PENDING)
    video_segment: SceneStatus = Field(default=SceneStatus.PENDING)


# ---------------------------------------------------------------------------
# Caption data models
# ---------------------------------------------------------------------------


class CaptionWord(BaseModel):
    """A single transcribed word with timing.

    Fields:
        word: The transcribed word text.
        start: Start time in seconds (non-negative).
        end: End time in seconds (non-negative, >= start).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    word: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_start_before_end(self) -> "CaptionWord":
        if self.start > self.end:
            msg = f"start ({self.start}) must not exceed end ({self.end})"
            raise ValueError(msg)
        return self


class CaptionSegment(BaseModel):
    """A transcribed segment (roughly sentence-level) with timing.

    Fields:
        text: The transcribed segment text.
        start: Start time in seconds (non-negative).
        end: End time in seconds (non-negative, >= start).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_start_before_end(self) -> "CaptionSegment":
        if self.start > self.end:
            msg = f"start ({self.start}) must not exceed end ({self.end})"
            raise ValueError(msg)
        return self


class CaptionResult(BaseModel):
    """Complete transcription result with segments and word timestamps.

    Fields:
        segments: Sentence-level transcription segments.
        words: Word-level timestamps for subtitle generation.
        language: Detected language code (e.g. "en").
        duration: Total audio duration in seconds (non-negative).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    segments: list[CaptionSegment]
    words: list[CaptionWord]
    language: str
    duration: float = Field(ge=0)


class Scene(BaseModel):
    """Content and metadata for a single story scene.

    Represents one scene in a story, containing the prose text,
    optional TTS-optimized narration, image prompts, and per-asset
    production status.

    Fields:
        scene_number: 1-based scene index.
        title: Scene title or beat description.
        prose: The actual story text for this scene.
        summary: Brief summary for running context across scenes (set during prose generation).
        narration_text: TTS-optimized version of the prose (set during narration prep).
        image_prompts: Image generation prompts for scene illustrations
            (set during image prompt generation). Each entry is a
            SceneImagePrompt with optional tag key and position.
        audio_cues: Music/SFX cues for this scene (set during music tag parsing).
        asset_status: Per-asset production status tracking.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    scene_number: int = Field(gt=0)
    title: str = Field(min_length=1)
    prose: str = Field(min_length=1)
    summary: str | None = Field(default=None)
    narration_text: str | None = Field(default=None)
    image_prompts: list[SceneImagePrompt] = Field(default_factory=list)
    audio_cues: list[SceneAudioCue] = Field(default_factory=list)
    asset_status: SceneAssetStatus = Field(default_factory=SceneAssetStatus)


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class ProjectMetadata(BaseModel):
    """Project-level tracking information.

    Represents the top-level state of a story video project, including
    its mode, current pipeline phase, overall status, configuration,
    and all scenes.

    Fields:
        project_id: Unique project identifier string.
        mode: Input mode (original, inspired_by, or adapt).
        created_at: UTC timestamp when the project was created.
        current_phase: The pipeline phase currently being executed (None if not started).
        status: Overall project status.
        config: Full application configuration used for this project.
        scenes: List of scenes in the project.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    project_id: str = Field(min_length=1)
    mode: InputMode
    created_at: datetime = Field(default_factory=_utc_now)
    current_phase: PipelinePhase | None = Field(default=None)
    status: PhaseStatus = Field(default=PhaseStatus.PENDING)
    config: AppConfig = Field(default_factory=AppConfig)
    scenes: list[Scene] = Field(default_factory=list)
