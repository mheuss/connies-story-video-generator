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
from story_video.utils.openai_compat import OPENAI_TRANSIENT
from story_video.utils.retry import with_retry

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

    @with_retry(max_retries=3, base_delay=2.0, retry_on=OPENAI_TRANSIENT)
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


def _strip_punctuation(word: str) -> tuple[str, str, str]:
    """Split a word into (leading_punct, bare_word, trailing_punct).

    Walks inward from each end until an alphanumeric character is found.
    Internal punctuation (e.g. apostrophes in contractions) is preserved
    in the bare component.

    Args:
        word: A single whitespace-free token.

    Returns:
        Tuple of (leading, bare, trailing). If the word is entirely
        punctuation, bare will be an empty string.
    """
    i = 0
    while i < len(word) and not word[i].isalnum():
        i += 1
    j = len(word)
    while j > i and not word[j - 1].isalnum():
        j -= 1
    return word[:i], word[i:j], word[j:]


def _tokenize_prose(prose: str) -> list[tuple[str, str, str]]:
    """Split prose into tokens of (leading_punct, bare_word, trailing_punct).

    Each whitespace-delimited word is decomposed via ``_strip_punctuation``.

    Args:
        prose: The prose text to tokenize.

    Returns:
        List of (leading, bare, trailing) tuples. Words that are entirely
        punctuation (e.g. ``—``) are skipped.
    """
    tokens: list[tuple[str, str, str]] = []
    for raw_word in prose.split():
        leading, bare, trailing = _strip_punctuation(raw_word)
        if bare:
            tokens.append((leading, bare, trailing))

    return tokens


def _reconcile_punctuation(result: CaptionResult, prose: str) -> CaptionResult:
    """Restore punctuation from prose text to caption word timestamps.

    Whisper strips punctuation from word-level timestamps. This function
    aligns caption words against the original prose using a two-pointer
    walk, transferring leading and trailing punctuation (including
    quotation marks) from prose tokens to caption words.

    Falls back gracefully — unmatched words keep their existing text.
    The lookahead window is 3 tokens. If Whisper output drifts more than
    3 tokens from the prose (e.g. due to hallucination), subsequent words
    in that passage will not receive punctuation.

    Args:
        result: CaptionResult with words (possibly missing punctuation).
        prose: The original prose text with correct punctuation.

    Returns:
        A new CaptionResult with punctuation restored on words.
    """
    if not result.words or not prose:
        return result

    tokens = _tokenize_prose(prose)
    if not tokens:
        return result

    new_words = list(result.words)
    token_idx = 0
    lookahead = 3  # How far ahead to search for a match on mismatch

    for word_idx in range(len(new_words)):
        if token_idx >= len(tokens):
            break

        word = new_words[word_idx]
        _, bare_caption, _ = _strip_punctuation(word.word)
        if not bare_caption:
            continue

        bare_caption_lower = bare_caption.lower()

        # Try to match at current token position, then lookahead
        matched_offset = None
        for offset in range(min(lookahead + 1, len(tokens) - token_idx)):
            _, prose_bare, _ = tokens[token_idx + offset]
            if prose_bare.lower() == bare_caption_lower:
                matched_offset = offset
                break

        if matched_offset is None:
            # No match found in lookahead window — skip this caption word
            continue

        # Apply punctuation from matched prose token
        leading, _, trailing = tokens[token_idx + matched_offset]
        new_word_text = leading + bare_caption + trailing

        if new_word_text != word.word:
            new_words[word_idx] = CaptionWord(
                word=new_word_text,
                start=word.start,
                end=word.end,
            )

        # Advance token pointer past the match
        token_idx = token_idx + matched_offset + 1

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
    # Use narration_text (what TTS actually spoke) for punctuation reconciliation
    # when available. Falls back to prose for pre-narration-prep projects.
    reconciliation_source = (
        scene.narration_text if scene.narration_text is not None else scene.prose
    )
    result = _reconcile_punctuation(result, reconciliation_source)

    captions_dir = state.project_dir / "captions"
    captions_dir.mkdir(exist_ok=True)
    caption_filename = f"scene_{scene.scene_number:03d}.json"
    caption_path = captions_dir / caption_filename
    caption_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    state.update_scene_asset(scene.scene_number, AssetType.CAPTIONS, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(scene.scene_number, AssetType.CAPTIONS, SceneStatus.COMPLETED)
    state.save()
