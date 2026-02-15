"""Pydantic data models for the Story Video Generator.

This module defines all data shapes used across the application:
- Enums for input modes, statuses, asset types, and pipeline phases
- Config models for each subsystem (story, TTS, images, video, subtitles, pipeline, output)
- Scene and project metadata models

Pure data definitions only — no file I/O, no business logic.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ADAPT_FLOW_PHASES",
    "CREATIVE_FLOW_PHASES",
    "AppConfig",
    "AssetType",
    "CaptionResult",
    "CaptionSegment",
    "CaptionWord",
    "ImageConfig",
    "InputMode",
    "OutputConfig",
    "PhaseStatus",
    "PipelineConfig",
    "PipelinePhase",
    "ProjectMetadata",
    "Scene",
    "SceneAssetStatus",
    "SceneStatus",
    "StoryConfig",
    "SubtitleConfig",
    "TTSConfig",
    "VideoConfig",
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

    Each scene tracks the status of these six asset types independently.
    """

    TEXT = "text"
    NARRATION_TEXT = "narration_text"
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
        scene_splitting -> narration_flagging -> image_prompts -> narration_prep
        -> tts_generation -> image_generation -> caption_generation -> video_assembly
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

    model_config = ConfigDict(frozen=True)

    target_duration_minutes: int = Field(default=30, gt=0)
    words_per_minute: int = Field(default=150, gt=0)
    scene_word_target: int = Field(default=1800, gt=0)
    scene_word_min: int = Field(default=500, gt=0)
    scene_word_max: int = Field(default=3000, gt=0)


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

    model_config = ConfigDict(frozen=True)

    provider: str = Field(default="openai")
    model: str = Field(default="tts-1-hd")
    voice: str = Field(default="nova")
    speed: float = Field(default=1.0, gt=0)
    output_format: str = Field(default="mp3")


class ImageConfig(BaseModel):
    """Image generation parameters.

    Controls the image provider, model, dimensions, quality, and style prefix
    prepended to each DALL-E prompt.

    Fields:
        provider: Image generation service provider name.
        model: Specific image model identifier.
        size: Image dimensions as "WIDTHxHEIGHT".
        quality: Image quality tier.
        style: DALL-E style parameter.
        style_prefix: Text prepended to every image prompt.
    """

    model_config = ConfigDict(frozen=True)

    provider: str = Field(default="openai")
    model: str = Field(default="dall-e-3")
    size: str = Field(default="1024x1024")
    quality: str = Field(default="standard")
    style: str = Field(default="vivid")
    style_prefix: str = Field(default="Cinematic digital painting, dramatic lighting:")


class VideoConfig(BaseModel):
    """Video assembly parameters.

    Controls resolution, encoding, Ken Burns effect, background treatment,
    and transition timing for FFmpeg video assembly.

    Fields:
        resolution: Video dimensions as "WIDTHxHEIGHT".
        fps: Frames per second.
        codec: FFmpeg video codec.
        crf: Constant Rate Factor for encoding quality (lower = better).
        background_mode: Background treatment mode ("blur" or "custom").
        background_blur_radius: Gaussian blur radius for blurred background.
        background_image: Optional path to a custom background image.
        ken_burns_zoom: Maximum zoom factor for Ken Burns effect.
        transition_duration: Crossfade duration between scenes in seconds.
        fade_in_duration: Fade-from-black duration at video start in seconds.
        fade_out_duration: Fade-to-black duration at video end in seconds.
    """

    model_config = ConfigDict(frozen=True)

    resolution: str = Field(default="1920x1080")
    fps: int = Field(default=30, gt=0)
    codec: str = Field(default="libx264")
    crf: int = Field(default=18, ge=0)
    background_mode: str = Field(default="blur")
    background_blur_radius: int = Field(default=40, ge=0)
    background_image: Optional[Path] = Field(default=None)
    ken_burns_zoom: float = Field(default=1.08, gt=0)
    transition_duration: float = Field(default=1.5, ge=0)
    fade_in_duration: float = Field(default=2.0, ge=0)
    fade_out_duration: float = Field(default=3.0, ge=0)


class SubtitleConfig(BaseModel):
    """Subtitle rendering parameters.

    Controls font, color, positioning, and line wrapping for burned-in subtitles.

    Fields:
        font: Primary font name.
        font_fallback: Fallback font if primary is unavailable.
        font_size: Font size in pixels at 1080p.
        color: Text color as hex string.
        outline_color: Outline color as hex string.
        outline_width: Outline width in pixels.
        position_bottom: Distance from bottom edge in pixels.
        max_chars_per_line: Maximum characters per subtitle line.
        max_lines: Maximum number of subtitle lines.
    """

    model_config = ConfigDict(frozen=True)

    font: str = Field(default="Montserrat")
    font_fallback: str = Field(default="Arial")
    font_size: int = Field(default=48, gt=0)
    color: str = Field(default="#FFFFFF")
    outline_color: str = Field(default="#000000")
    outline_width: int = Field(default=3, ge=0)
    position_bottom: int = Field(default=80, ge=0)
    max_chars_per_line: int = Field(default=42, gt=0)
    max_lines: int = Field(default=2, gt=0)


class PipelineConfig(BaseModel):
    """Pipeline behavior parameters.

    Controls whether the pipeline runs autonomously or pauses for review,
    retry behavior, and whether originals are preserved during revision.

    Fields:
        autonomous: If True, skip human review checkpoints.
        max_retries: Maximum retry attempts for failed API calls.
        retry_base_delay: Base delay in seconds for exponential backoff.
        save_originals_on_revision: If True, save original files before revision.
    """

    model_config = ConfigDict(frozen=True)

    autonomous: bool = Field(default=False)
    max_retries: int = Field(default=3, ge=0)
    retry_base_delay: float = Field(default=2.0, gt=0)
    save_originals_on_revision: bool = Field(default=True)


class OutputConfig(BaseModel):
    """Output directory configuration.

    Fields:
        directory: Base directory where project outputs are stored.
    """

    model_config = ConfigDict(frozen=True)

    directory: Path = Field(default=Path("./output"))


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
        output: Output directory configuration.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    story: StoryConfig = Field(default_factory=StoryConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    images: ImageConfig = Field(default_factory=ImageConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    subtitles: SubtitleConfig = Field(default_factory=SubtitleConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


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
        audio: Status of the generated audio file.
        image: Status of the generated scene image.
        captions: Status of the generated caption data.
        video_segment: Status of the rendered video segment.
    """

    model_config = ConfigDict(validate_assignment=True)

    text: SceneStatus = Field(default=SceneStatus.PENDING)
    narration_text: SceneStatus = Field(default=SceneStatus.PENDING)
    audio: SceneStatus = Field(default=SceneStatus.PENDING)
    image: SceneStatus = Field(default=SceneStatus.PENDING)
    captions: SceneStatus = Field(default=SceneStatus.PENDING)
    video_segment: SceneStatus = Field(default=SceneStatus.PENDING)


# ---------------------------------------------------------------------------
# Caption data models
# ---------------------------------------------------------------------------


class CaptionWord(BaseModel):
    """A single transcribed word with timing."""

    word: str
    start: float  # seconds
    end: float  # seconds


class CaptionSegment(BaseModel):
    """A transcribed segment (roughly sentence-level) with timing."""

    text: str
    start: float
    end: float


class CaptionResult(BaseModel):
    """Complete transcription result with segments and word timestamps."""

    segments: list[CaptionSegment]
    words: list[CaptionWord]
    language: str
    duration: float


class Scene(BaseModel):
    """Content and metadata for a single story scene.

    Represents one scene in a story, containing the prose text,
    optional TTS-optimized narration, image prompt, and per-asset
    production status.

    Fields:
        scene_number: 1-based scene index.
        title: Scene title or beat description.
        prose: The actual story text for this scene.
        narration_text: TTS-optimized version of the prose (set during narration prep).
        image_prompt: DALL-E prompt for scene illustration (set during image prompt generation).
        asset_status: Per-asset production status tracking.
    """

    model_config = ConfigDict(validate_assignment=True)

    scene_number: int = Field(gt=0)
    title: str = Field(min_length=1)
    prose: str = Field(min_length=1)
    narration_text: Optional[str] = Field(default=None)
    image_prompt: Optional[str] = Field(default=None)
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

    model_config = ConfigDict(validate_assignment=True)

    project_id: str = Field(min_length=1)
    mode: InputMode
    created_at: datetime = Field(default_factory=_utc_now)
    current_phase: Optional[PipelinePhase] = Field(default=None)
    status: PhaseStatus = Field(default=PhaseStatus.PENDING)
    config: AppConfig = Field(default_factory=AppConfig)
    scenes: list[Scene] = Field(default_factory=list)
