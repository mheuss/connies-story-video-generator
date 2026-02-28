"""TTS audio generation with provider abstraction.

Converts scene narration text to audio files using a pluggable TTS provider.
Ships with OpenAI and ElevenLabs implementations.
"""

import logging
import math
from typing import Protocol

import elevenlabs
import openai

from story_video.models import AssetType, Scene, SceneStatus, StoryHeader
from story_video.state import ProjectState
from story_video.utils.narration_tags import has_narration_tags, parse_narration_segments
from story_video.utils.openai_compat import OPENAI_TRANSIENT
from story_video.utils.retry import with_retry

logger = logging.getLogger(__name__)

__all__ = [
    "ELEVENLABS_TRANSIENT_ERRORS",
    "ElevenLabsTTSProvider",
    "OpenAITTSProvider",
    "TTSProvider",
    "generate_audio",
    "generate_mp3_silence",
]

# Formats that support raw byte concatenation (independently decodable frames).
# Prefixes, not exact matches — ElevenLabs uses e.g. "mp3_44100_128".
_CONCAT_SAFE_PREFIXES = ("mp3", "opus")

# A single valid silent MP3 frame: MPEG-1 Layer III, 128kbps, 44100Hz, stereo.
# 417 bytes per frame, ~26.12ms duration per frame.
_SILENT_MP3_FRAME = (
    b"\xff\xfb\x90\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00" + b"\x00" * 381
)

_SILENT_FRAME_DURATION = 0.02612  # seconds per frame (1152 samples / 44100 Hz)


def generate_mp3_silence(duration: float) -> bytes:
    """Generate silent MP3 audio of approximately the specified duration.

    Repeats a valid silent MP3 frame enough times to cover the requested
    duration. The actual duration may exceed the request by up to ~26ms
    due to MP3 frame granularity. The output can be concatenated with
    other MP3 bytes.

    Args:
        duration: Silence duration in seconds (must be positive).

    Returns:
        Raw MP3 bytes containing silence.

    Raises:
        ValueError: If duration is not positive.
    """
    if duration <= 0:
        msg = f"Silence duration must be positive, got {duration}"
        raise ValueError(msg)
    frame_count = math.ceil(duration / _SILENT_FRAME_DURATION)
    return _SILENT_MP3_FRAME * frame_count


class TTSProvider(Protocol):
    """Interface for text-to-speech providers."""

    def synthesize(
        self,
        text: str,
        voice: str,
        model: str,
        speed: float,
        output_format: str,
        instructions: str | None = None,
        mood: str | None = None,
    ) -> bytes:
        """Convert text to audio bytes.

        Args:
            text: The text to convert to speech.
            voice: Voice identifier for the TTS engine.
            model: TTS model identifier.
            speed: Playback speed multiplier.
            output_format: Audio format (mp3, wav, etc.).
            instructions: Optional style/mood instruction for the TTS engine.
            mood: Optional raw mood keyword (used by ElevenLabs for audio tags).

        Returns:
            Raw audio bytes.
        """
        ...


class OpenAITTSProvider:
    """OpenAI TTS provider using the audio.speech API.

    Reads OPENAI_API_KEY from the environment.
    """

    def __init__(self) -> None:
        self._client = openai.OpenAI()

    @with_retry(max_retries=3, base_delay=2.0, retry_on=OPENAI_TRANSIENT)
    def synthesize(
        self,
        text: str,
        voice: str,
        model: str,
        speed: float,
        output_format: str,
        instructions: str | None = None,
        mood: str | None = None,
    ) -> bytes:
        """Convert text to audio bytes via OpenAI TTS.

        Args:
            text: The text to convert to speech.
            voice: OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer).
            model: OpenAI TTS model (tts-1, tts-1-hd, gpt-4o-mini-tts).
            speed: Playback speed multiplier (0.25 to 4.0).
            output_format: Audio format (mp3, opus, aac, flac).
            instructions: Optional style/mood instruction for the TTS engine.
            mood: Optional raw mood keyword (unused by OpenAI, uses instructions instead).

        Returns:
            Raw audio bytes from the full API response.
        """
        kwargs = {
            "model": model,
            "voice": voice,
            "input": text,
            "speed": speed,
            "response_format": output_format,
        }
        if instructions is not None:
            kwargs["instructions"] = instructions
        response = self._client.audio.speech.create(**kwargs)
        return response.content


def _mood_to_elevenlabs_text(text: str, mood: str | None) -> str:
    """Prepend an Eleven v3 audio tag for the mood keyword.

    Eleven v3 supports freeform audio tags like ``[thoughtful]``,
    ``[whispers]``, ``[excited]``. The mood keyword is passed through
    directly as a tag — no mapping table needed.
    """
    if mood is None:
        return text
    return f"[{mood.strip().lower()}] {text}"


# ElevenLabs transient errors: network failures only.
# The with_retry decorator uses type-based filtering, so we can only
# retry on exception types, not status codes. Network errors are the
# most common transient failure; ElevenLabs API errors (4xx, 5xx) are
# not retried to avoid masking auth or bad-request errors.
ELEVENLABS_TRANSIENT_ERRORS = (ConnectionError, TimeoutError)


class ElevenLabsTTSProvider:
    """ElevenLabs TTS provider using the standard text-to-speech API.

    Reads ELEVENLABS_API_KEY from the environment (the SDK default).
    """

    def __init__(self) -> None:
        self._client = elevenlabs.ElevenLabs()
        self._speed_warned = False

    @with_retry(max_retries=3, base_delay=2.0, retry_on=ELEVENLABS_TRANSIENT_ERRORS)
    def synthesize(
        self,
        text: str,
        voice: str,
        model: str,
        speed: float,
        output_format: str,
        instructions: str | None = None,
        mood: str | None = None,
    ) -> bytes:
        """Convert text to audio bytes via ElevenLabs TTS.

        Args:
            text: The text to convert to speech.
            voice: ElevenLabs voice ID (hash string).
            model: ElevenLabs model ID.
            speed: Playback speed (not supported by ElevenLabs API).
            output_format: ElevenLabs output format (mp3_44100_128, etc.).
            instructions: Optional mood instruction (unused by ElevenLabs, uses mood instead).
            mood: Optional raw mood keyword, translated to audio tag.

        Returns:
            Raw audio bytes from the streaming response.
        """
        if speed != 1.0 and not self._speed_warned:
            logger.warning(
                "ElevenLabs does not support speed parameter (got %.1f); ignoring",
                speed,
            )
            self._speed_warned = True
        tagged_text = _mood_to_elevenlabs_text(text, mood)
        audio_iter = self._client.text_to_speech.convert(
            voice_id=voice,
            model_id=model,
            text=tagged_text,
            output_format=output_format,
        )
        return b"".join(audio_iter)


def _mood_to_instructions(mood: str | None) -> str | None:
    """Convert a mood tag to a natural language TTS instruction.

    Used by OpenAI TTS (``instructions`` parameter). ElevenLabs receives the
    raw mood keyword directly via the ``mood`` parameter instead.
    """
    if not mood:
        return None
    article = "an" if mood[0].lower() in "aeiou" else "a"
    return f"Speak in {article} {mood} tone"


def generate_audio(
    scene: Scene,
    state: ProjectState,
    provider: TTSProvider,
    story_header: StoryHeader | None = None,
) -> None:
    """Generate audio for a single scene.

    When a story_header is provided, parses the narration text into
    segments by voice/mood tags and makes one TTS call per segment.
    Audio bytes are concatenated into a single scene file.

    When no story_header is provided, behaves identically to the
    original single-call-per-scene path (backward compatible).

    Args:
        scene: The scene to generate audio for.
        state: Project state for config access and persistence.
        provider: TTS provider implementation.
        story_header: Optional parsed story header with voice mappings.

    Raises:
        ValueError: If the scene has no text content, or if voice/mood
            tags are present but no story header was provided.
    """
    text = scene.narration_text if scene.narration_text is not None else scene.prose
    if not text.strip():
        msg = f"Scene {scene.scene_number} has no text for TTS"
        raise ValueError(msg)

    tts_config = state.metadata.config.tts

    # Fail fast if tags are present but no header defines the voice mappings.
    # Without this check, tags would be spoken aloud as literal text.
    if story_header is None and has_narration_tags(text):
        msg = (
            f"Voice/mood tag found in scene {scene.scene_number} text but no "
            "voices header defined. Add a YAML header with voice mappings."
        )
        raise ValueError(msg)

    if story_header is not None:
        # Multi-segment path
        segments = parse_narration_segments(
            text,
            voice_map=story_header.voices,
            default_voice=story_header.default_voice,
            scene_number=scene.scene_number,
        )
        # Guard: raw byte concat only works for streaming formats
        if len(segments) > 1 and not tts_config.output_format.startswith(_CONCAT_SAFE_PREFIXES):
            msg = (
                f"Multi-voice audio concatenation requires mp3 or opus format, "
                f"got '{tts_config.output_format}'. "
                f"Set tts.output_format to 'mp3' or 'opus'."
            )
            raise ValueError(msg)
        audio_chunks: list[bytes] = []
        for segment in segments:
            if segment.pause_duration is not None:
                chunk = generate_mp3_silence(segment.pause_duration)
            else:
                chunk = provider.synthesize(
                    segment.text,
                    voice=segment.voice,
                    model=tts_config.model,
                    speed=tts_config.speed,
                    output_format=tts_config.output_format,
                    instructions=_mood_to_instructions(segment.mood),
                    mood=segment.mood,
                )
            audio_chunks.append(chunk)
        audio_bytes = b"".join(audio_chunks)
    else:
        # Backward-compatible single-segment path
        audio_bytes = provider.synthesize(
            text,
            voice=tts_config.voice,
            model=tts_config.model,
            speed=tts_config.speed,
            output_format=tts_config.output_format,
        )

    if not audio_bytes:
        msg = f"Scene {scene.scene_number}: TTS provider returned empty audio"
        raise ValueError(msg)

    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    ext = tts_config.file_extension
    filename = f"scene_{scene.scene_number:03d}.{ext}"
    audio_path = audio_dir / filename
    audio_path.write_bytes(audio_bytes)

    state.update_scene_asset(scene.scene_number, AssetType.AUDIO, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(scene.scene_number, AssetType.AUDIO, SceneStatus.COMPLETED)
    state.save()
