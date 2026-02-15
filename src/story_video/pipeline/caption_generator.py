"""Caption generation with Whisper provider abstraction.

Transcribes scene audio files to produce word-level and segment-level timestamps
for subtitle rendering. Ships with an OpenAI Whisper implementation; designed for
easy addition of alternative transcription providers.
"""

from pathlib import Path
from typing import Protocol

import openai
from openai import APIConnectionError, InternalServerError, RateLimitError
from pydantic import BaseModel

from story_video.models import AssetType, Scene, SceneStatus
from story_video.state import ProjectState
from story_video.utils.retry import with_retry

__all__ = [
    "CaptionProvider",
    "CaptionResult",
    "CaptionSegment",
    "CaptionWord",
    "OpenAIWhisperProvider",
    "generate_captions",
]

TRANSIENT_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)


# ---------------------------------------------------------------------------
# Data models
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


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class CaptionProvider(Protocol):
    """Interface for audio transcription providers."""

    def transcribe(self, audio_path: Path) -> CaptionResult:
        """Transcribe an audio file and return word-level timestamps.

        Args:
            audio_path: Path to the audio file to transcribe.

        Returns:
            CaptionResult with segments, words, language, and duration.
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI Whisper implementation
# ---------------------------------------------------------------------------


class OpenAIWhisperProvider:
    """OpenAI Whisper transcription provider.

    Reads OPENAI_API_KEY from the environment.
    """

    def __init__(self) -> None:
        self._client = openai.OpenAI()

    @with_retry(max_retries=3, base_delay=2.0, retry_on=TRANSIENT_ERRORS)
    def transcribe(self, audio_path: Path) -> CaptionResult:
        """Transcribe an audio file via OpenAI Whisper.

        Args:
            audio_path: Path to the audio file to transcribe.

        Returns:
            CaptionResult with segments, words, language, and duration
            mapped from the Whisper verbose_json response.
        """
        with open(audio_path, "rb") as audio_file:
            response = self._client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-1",
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
            )

        return CaptionResult(
            segments=[
                CaptionSegment(text=seg.text, start=seg.start, end=seg.end)
                for seg in response.segments
            ],
            words=[CaptionWord(word=w.word, start=w.start, end=w.end) for w in response.words],
            language=response.language,
            duration=response.duration,
        )


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def generate_captions(scene: Scene, state: ProjectState, provider: CaptionProvider) -> None:
    """Generate captions for a single scene by transcribing its audio.

    Reads the audio file, calls the transcription provider, writes the
    caption JSON file, and updates project state.

    Args:
        scene: The scene to generate captions for.
        state: Project state for config access and persistence.
        provider: Caption provider implementation.

    Raises:
        FileNotFoundError: If the scene's audio file does not exist.
    """
    tts_config = state.metadata.config.tts
    filename = f"scene_{scene.scene_number:02d}.{tts_config.output_format}"
    audio_path = state.project_dir / "audio" / filename

    if not audio_path.exists():
        msg = f"Audio file not found: {audio_path}"
        raise FileNotFoundError(msg)

    result = provider.transcribe(audio_path)

    captions_dir = state.project_dir / "captions"
    captions_dir.mkdir(exist_ok=True)
    caption_filename = f"scene_{scene.scene_number:02d}.json"
    caption_path = captions_dir / caption_filename
    caption_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    state.update_scene_asset(scene.scene_number, AssetType.CAPTIONS, SceneStatus.COMPLETED)
    state.save()
