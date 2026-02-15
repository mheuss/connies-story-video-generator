"""TTS audio generation with provider abstraction.

Converts scene narration text to audio files using a pluggable TTS provider.
Ships with an OpenAI implementation; designed for easy addition of ElevenLabs
or other providers.
"""

from typing import Protocol

import openai

from story_video.models import AssetType, Scene, SceneStatus
from story_video.state import ProjectState
from story_video.utils.retry import OPENAI_TRANSIENT_ERRORS, with_retry

__all__ = ["OpenAITTSProvider", "TTSProvider", "generate_audio"]


class TTSProvider(Protocol):
    """Interface for text-to-speech providers."""

    def synthesize(
        self,
        text: str,
        voice: str,
        model: str,
        speed: float,
        output_format: str,
    ) -> bytes:
        """Convert text to audio bytes.

        Args:
            text: The text to convert to speech.
            voice: Voice identifier for the TTS engine.
            model: TTS model identifier.
            speed: Playback speed multiplier.
            output_format: Audio format (mp3, wav, etc.).

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

    @with_retry(max_retries=3, base_delay=2.0, retry_on=OPENAI_TRANSIENT_ERRORS)
    def synthesize(
        self,
        text: str,
        voice: str,
        model: str,
        speed: float,
        output_format: str,
    ) -> bytes:
        """Convert text to audio bytes via OpenAI TTS.

        Args:
            text: The text to convert to speech.
            voice: OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer).
            model: OpenAI TTS model (tts-1, tts-1-hd).
            speed: Playback speed multiplier (0.25 to 4.0).
            output_format: Audio format (mp3, opus, aac, flac).

        Returns:
            Raw audio bytes from the full API response.
        """
        response = self._client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            speed=speed,
            response_format=output_format,
        )
        return response.content


def generate_audio(scene: Scene, state: ProjectState, provider: TTSProvider) -> None:
    """Generate audio for a single scene.

    Reads narration text (falling back to prose), calls the TTS provider,
    writes the audio file, and updates project state.

    Args:
        scene: The scene to generate audio for.
        state: Project state for config access and persistence.
        provider: TTS provider implementation.

    Raises:
        ValueError: If the scene has no text content.
    """
    text = scene.narration_text if scene.narration_text is not None else scene.prose
    if not text.strip():
        msg = f"Scene {scene.scene_number} has no text for TTS"
        raise ValueError(msg)

    tts_config = state.metadata.config.tts
    audio_bytes = provider.synthesize(
        text,
        voice=tts_config.voice,
        model=tts_config.model,
        speed=tts_config.speed,
        output_format=tts_config.output_format,
    )

    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    filename = f"scene_{scene.scene_number:03d}.{tts_config.output_format}"
    audio_path = audio_dir / filename
    audio_path.write_bytes(audio_bytes)

    state.update_scene_asset(scene.scene_number, AssetType.AUDIO, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(scene.scene_number, AssetType.AUDIO, SceneStatus.COMPLETED)
    state.save()
