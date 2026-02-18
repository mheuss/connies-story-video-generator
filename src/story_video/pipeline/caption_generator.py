"""Caption generation with Whisper provider abstraction.

Transcribes scene audio files to produce word-level and segment-level timestamps
for subtitle rendering. Ships with an OpenAI Whisper implementation; designed for
easy addition of alternative transcription providers.
"""

import logging
from pathlib import Path
from typing import Protocol

import openai

from story_video.models import (
    AssetType,
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    Scene,
    SceneStatus,
)
from story_video.state import ProjectState
from story_video.utils.retry import with_retry

_OPENAI_TRANSIENT = (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)

__all__ = [
    "CaptionProvider",
    "OpenAIWhisperProvider",
    "generate_captions",
]

logger = logging.getLogger(__name__)


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

    @with_retry(max_retries=3, base_delay=2.0, retry_on=_OPENAI_TRANSIENT)
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
# Punctuation reconciliation
# ---------------------------------------------------------------------------


def _reconcile_punctuation(result: CaptionResult) -> CaptionResult:
    """Restore punctuation from segment text to word timestamps.

    Whisper word-level timestamps strip punctuation, but segment text
    preserves it. This function walks each segment's text with a cursor,
    matching words by position, and appends any trailing non-alphanumeric
    characters to the word.

    Fails gracefully — unmatched words are left unchanged.

    Args:
        result: CaptionResult with segments (punctuated) and words (bare).

    Returns:
        A new CaptionResult with punctuation restored on words.
    """
    if not result.words:
        return result

    new_words = list(result.words)

    for segment in result.segments:
        seg_text = segment.text.strip()
        cursor = 0

        for i, word in enumerate(new_words):
            # Only process words within this segment's time range
            if word.start < segment.start - 0.01 or word.start > segment.end + 0.01:
                continue

            # Strip any existing punctuation from the word for matching
            bare_word = word.word.rstrip(".,!?;:\u2014\"'\u201c\u201d\u2018\u2019\u2026-")
            if not bare_word:
                continue

            # Find the word in segment text starting from cursor
            pos = seg_text.find(bare_word, cursor)
            if pos == -1:
                # Try case-insensitive match
                pos = seg_text.lower().find(bare_word.lower(), cursor)
            if pos == -1:
                continue

            # Advance past the word
            end_of_word = pos + len(bare_word)

            # Grab trailing non-alphanumeric, non-space characters
            trailing = ""
            j = end_of_word
            while j < len(seg_text) and not seg_text[j].isalnum() and seg_text[j] != " ":
                trailing += seg_text[j]
                j += 1

            # Update word with punctuation if it doesn't already have it
            if trailing and not word.word.endswith(trailing):
                new_words[i] = CaptionWord(
                    word=bare_word + trailing,
                    start=word.start,
                    end=word.end,
                )

            # Advance cursor past matched content
            cursor = j

    return CaptionResult(
        segments=result.segments,
        words=new_words,
        language=result.language,
        duration=result.duration,
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
    ext = tts_config.file_extension
    filename = f"scene_{scene.scene_number:03d}.{ext}"
    audio_path = state.project_dir / "audio" / filename

    if not audio_path.exists():
        msg = f"Audio file not found: {audio_path}"
        raise FileNotFoundError(msg)

    result = provider.transcribe(audio_path)
    result = _reconcile_punctuation(result)

    captions_dir = state.project_dir / "captions"
    captions_dir.mkdir(exist_ok=True)
    caption_filename = f"scene_{scene.scene_number:03d}.json"
    caption_path = captions_dir / caption_filename
    caption_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    state.update_scene_asset(scene.scene_number, AssetType.CAPTIONS, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(scene.scene_number, AssetType.CAPTIONS, SceneStatus.COMPLETED)
    state.save()
