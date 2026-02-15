"""Tests for story_video.pipeline.tts_generator — TTS audio generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the TTS generator module.
"""

from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, AssetType, InputMode, SceneStatus, TTSConfig
from story_video.pipeline.tts_generator import (
    OpenAITTSProvider,
    TTSProvider,
    generate_audio,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_openai(monkeypatch):
    """Patch openai.OpenAI to return a mock client."""
    mock_client = MagicMock()
    mock_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("story_video.pipeline.tts_generator.openai.OpenAI", mock_class)
    return mock_client


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch):
    """Eliminate retry delays so tests run instantly."""
    monkeypatch.setattr("time.sleep", lambda _: None)


@pytest.fixture()
def mock_provider():
    """Create a mock TTS provider that returns dummy audio bytes."""
    provider = MagicMock(spec=TTSProvider)
    provider.synthesize.return_value = b"fake-audio-bytes"
    return provider


@pytest.fixture()
def state_with_scene(tmp_path):
    """Create a project state with one scene ready for TTS.

    The scene has TEXT and NARRATION_TEXT both COMPLETED (audio dependency).
    """
    state = ProjectState.create(
        project_id="tts-test",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    state.add_scene(1, "The Storm", "The storm raged on through the night.")
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
    return state


@pytest.fixture()
def state_with_narration_text(tmp_path):
    """Create a project state with a scene that has narration_text set."""
    state = ProjectState.create(
        project_id="tts-narration",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    state.add_scene(1, "The Storm", "The storm raged on through the night.")
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    # Set narration_text on the scene
    scene = state.metadata.scenes[0]
    scene.narration_text = "The storm raged on through the long, dark night."
    state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
    return state


# ---------------------------------------------------------------------------
# OpenAITTSProvider — returns bytes
# ---------------------------------------------------------------------------


class TestOpenAITTSProviderReturnsBytes:
    """OpenAITTSProvider.synthesize() returns audio bytes from the SDK."""

    def test_synthesize_returns_bytes(self, mock_openai):
        """synthesize() returns the response content as bytes."""
        response = MagicMock()
        response.content = b"audio-data-from-openai"
        mock_openai.audio.speech.create.return_value = response

        provider = OpenAITTSProvider()
        result = provider.synthesize(
            text="Hello world",
            voice="nova",
            model="tts-1-hd",
            speed=1.0,
            output_format="mp3",
        )

        assert result == b"audio-data-from-openai"


# ---------------------------------------------------------------------------
# OpenAITTSProvider — passes correct params
# ---------------------------------------------------------------------------


class TestOpenAITTSProviderPassesParams:
    """OpenAITTSProvider.synthesize() passes correct parameters to the SDK."""

    def test_synthesize_passes_params_to_sdk(self, mock_openai):
        """synthesize() forwards all parameters to audio.speech.create."""
        response = MagicMock()
        response.content = b"audio-bytes"
        mock_openai.audio.speech.create.return_value = response

        provider = OpenAITTSProvider()
        provider.synthesize(
            text="Once upon a time",
            voice="echo",
            model="tts-1",
            speed=1.5,
            output_format="opus",
        )

        call_kwargs = mock_openai.audio.speech.create.call_args.kwargs
        assert call_kwargs["model"] == "tts-1"
        assert call_kwargs["voice"] == "echo"
        assert call_kwargs["input"] == "Once upon a time"
        assert call_kwargs["speed"] == 1.5
        assert call_kwargs["response_format"] == "opus"


# ---------------------------------------------------------------------------
# OpenAITTSProvider — reads API key from env
# ---------------------------------------------------------------------------


class TestOpenAITTSProviderReadsApiKeyFromEnv:
    """OpenAITTSProvider reads OPENAI_API_KEY from the environment."""

    def test_client_reads_api_key_from_env(self, monkeypatch):
        """OpenAI() is called without explicit API key (reads from env)."""
        mock_client = MagicMock()
        mock_class = MagicMock(return_value=mock_client)
        monkeypatch.setattr("story_video.pipeline.tts_generator.openai.OpenAI", mock_class)

        _ = OpenAITTSProvider()

        mock_class.assert_called_once_with()


# ---------------------------------------------------------------------------
# OpenAITTSProvider — retry on transient errors
# ---------------------------------------------------------------------------


class TestOpenAITTSProviderRetryOnTransientErrors:
    """OpenAITTSProvider.synthesize() retries on transient API errors."""

    def test_synthesize_retries_on_connection_error(self, mock_openai):
        """synthesize() retries on APIConnectionError then succeeds."""
        from openai import APIConnectionError

        response = MagicMock()
        response.content = b"recovered-audio"

        mock_openai.audio.speech.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            response,
        ]

        provider = OpenAITTSProvider()
        result = provider.synthesize(
            text="test",
            voice="nova",
            model="tts-1-hd",
            speed=1.0,
            output_format="mp3",
        )

        assert result == b"recovered-audio"
        assert mock_openai.audio.speech.create.call_count == 2

    def test_synthesize_retries_on_rate_limit(self, mock_openai):
        """synthesize() retries on RateLimitError then succeeds."""
        from openai import RateLimitError

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.json.return_value = {"error": {"message": "rate limited"}}

        audio_response = MagicMock()
        audio_response.content = b"recovered-audio"

        mock_openai.audio.speech.create.side_effect = [
            RateLimitError(
                message="rate limited",
                response=response_429,
                body={"error": {"message": "rate limited"}},
            ),
            audio_response,
        ]

        provider = OpenAITTSProvider()
        result = provider.synthesize(
            text="test",
            voice="nova",
            model="tts-1-hd",
            speed=1.0,
            output_format="mp3",
        )

        assert result == b"recovered-audio"
        assert mock_openai.audio.speech.create.call_count == 2

    def test_synthesize_retries_on_server_error(self, mock_openai):
        """synthesize() retries on InternalServerError then succeeds."""
        from openai import InternalServerError

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.json.return_value = {"error": {"message": "server error"}}

        audio_response = MagicMock()
        audio_response.content = b"recovered-audio"

        mock_openai.audio.speech.create.side_effect = [
            InternalServerError(
                message="server error",
                response=response_500,
                body={"error": {"message": "server error"}},
            ),
            audio_response,
        ]

        provider = OpenAITTSProvider()
        result = provider.synthesize(
            text="test",
            voice="nova",
            model="tts-1-hd",
            speed=1.0,
            output_format="mp3",
        )

        assert result == b"recovered-audio"
        assert mock_openai.audio.speech.create.call_count == 2


# ---------------------------------------------------------------------------
# OpenAITTSProvider — no retry on permanent errors
# ---------------------------------------------------------------------------


class TestOpenAITTSProviderNoRetryOnPermanentErrors:
    """OpenAITTSProvider.synthesize() does NOT retry on permanent API errors."""

    def test_synthesize_no_retry_on_auth_error(self, mock_openai):
        """synthesize() does not retry on AuthenticationError."""
        from openai import AuthenticationError

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.json.return_value = {"error": {"message": "invalid key"}}

        mock_openai.audio.speech.create.side_effect = AuthenticationError(
            message="invalid key",
            response=response_401,
            body={"error": {"message": "invalid key"}},
        )

        provider = OpenAITTSProvider()

        with pytest.raises(AuthenticationError):
            provider.synthesize(
                text="test",
                voice="nova",
                model="tts-1-hd",
                speed=1.0,
                output_format="mp3",
            )

        assert mock_openai.audio.speech.create.call_count == 1

    def test_synthesize_no_retry_on_bad_request(self, mock_openai):
        """synthesize() does not retry on BadRequestError."""
        from openai import BadRequestError

        response_400 = MagicMock()
        response_400.status_code = 400
        response_400.json.return_value = {"error": {"message": "bad request"}}

        mock_openai.audio.speech.create.side_effect = BadRequestError(
            message="bad request",
            response=response_400,
            body={"error": {"message": "bad request"}},
        )

        provider = OpenAITTSProvider()

        with pytest.raises(BadRequestError):
            provider.synthesize(
                text="test",
                voice="nova",
                model="tts-1-hd",
                speed=1.0,
                output_format="mp3",
            )

        assert mock_openai.audio.speech.create.call_count == 1

    def test_synthesize_no_retry_on_permission_error(self, mock_openai):
        """synthesize() does not retry on PermissionDeniedError."""
        from openai import PermissionDeniedError

        response_403 = MagicMock()
        response_403.status_code = 403
        response_403.json.return_value = {"error": {"message": "permission denied"}}

        mock_openai.audio.speech.create.side_effect = PermissionDeniedError(
            message="permission denied",
            response=response_403,
            body={"error": {"message": "permission denied"}},
        )

        provider = OpenAITTSProvider()

        with pytest.raises(PermissionDeniedError):
            provider.synthesize(
                text="test",
                voice="nova",
                model="tts-1-hd",
                speed=1.0,
                output_format="mp3",
            )

        assert mock_openai.audio.speech.create.call_count == 1


# ---------------------------------------------------------------------------
# generate_audio — happy path
# ---------------------------------------------------------------------------


class TestGenerateAudioHappyPath:
    """generate_audio() writes audio file and updates state."""

    def test_generate_audio_writes_file_and_updates_state(self, state_with_scene, mock_provider):
        """Audio file written, status updated to COMPLETED, state saved."""
        scene = state_with_scene.metadata.scenes[0]
        generate_audio(scene, state_with_scene, mock_provider)

        # File written
        audio_path = state_with_scene.project_dir / "audio" / "scene_01.mp3"
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"fake-audio-bytes"

        # Status updated
        assert scene.asset_status.audio == SceneStatus.COMPLETED

        # State persisted — reload from disk
        reloaded = ProjectState.load(state_with_scene.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.audio == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_audio — narration_text preferred over prose
# ---------------------------------------------------------------------------


class TestGenerateAudioNarrationTextPreferred:
    """generate_audio() uses narration_text when available."""

    def test_generate_audio_prefers_narration_text(self, state_with_narration_text, mock_provider):
        """narration_text is passed to provider instead of prose."""
        scene = state_with_narration_text.metadata.scenes[0]
        generate_audio(scene, state_with_narration_text, mock_provider)

        call_args = mock_provider.synthesize.call_args
        assert call_args[0][0] == "The storm raged on through the long, dark night."


# ---------------------------------------------------------------------------
# generate_audio — prose fallback
# ---------------------------------------------------------------------------


class TestGenerateAudioProseFallback:
    """generate_audio() falls back to prose when narration_text is None."""

    def test_generate_audio_falls_back_to_prose(self, state_with_scene, mock_provider):
        """When narration_text is None, prose is used."""
        scene = state_with_scene.metadata.scenes[0]
        assert scene.narration_text is None

        generate_audio(scene, state_with_scene, mock_provider)

        call_args = mock_provider.synthesize.call_args
        assert call_args[0][0] == "The storm raged on through the night."


# ---------------------------------------------------------------------------
# generate_audio — empty text raises ValueError
# ---------------------------------------------------------------------------


class TestGenerateAudioEmptyTextRaises:
    """generate_audio() raises ValueError when text is empty."""

    def test_generate_audio_empty_narration_text_raises(self, state_with_scene, mock_provider):
        """Empty narration_text raises ValueError."""
        scene = state_with_scene.metadata.scenes[0]
        scene.narration_text = "   "

        with pytest.raises(ValueError, match="Scene 1 has no text for TTS"):
            generate_audio(scene, state_with_scene, mock_provider)


# ---------------------------------------------------------------------------
# generate_audio — config output_format used for file extension
# ---------------------------------------------------------------------------


class TestGenerateAudioConfigOutputFormat:
    """generate_audio() uses config output_format for file extension."""

    def test_generate_audio_uses_config_output_format(self, tmp_path, mock_provider):
        """File extension matches tts.output_format from config."""
        config = AppConfig(tts=TTSConfig(output_format="opus"))
        state = ProjectState.create(
            project_id="format-test",
            mode=InputMode.ADAPT,
            config=config,
            output_dir=tmp_path,
        )
        state.add_scene(1, "Scene One", "Some text for testing.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_audio(scene, state, mock_provider)

        audio_path = state.project_dir / "audio" / "scene_01.opus"
        assert audio_path.exists()


# ---------------------------------------------------------------------------
# generate_audio — config params passed to provider
# ---------------------------------------------------------------------------


class TestGenerateAudioConfigParamsPassedToProvider:
    """generate_audio() passes TTS config values to the provider."""

    def test_generate_audio_passes_config_to_provider(self, tmp_path, mock_provider):
        """voice, model, speed, output_format from config are passed to synthesize."""
        config = AppConfig(
            tts=TTSConfig(voice="echo", model="tts-1", speed=1.5, output_format="aac")
        )
        state = ProjectState.create(
            project_id="config-params-test",
            mode=InputMode.ADAPT,
            config=config,
            output_dir=tmp_path,
        )
        state.add_scene(1, "Scene One", "Text for testing config params.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_audio(scene, state, mock_provider)

        call_kwargs = mock_provider.synthesize.call_args.kwargs
        assert call_kwargs["voice"] == "echo"
        assert call_kwargs["model"] == "tts-1"
        assert call_kwargs["speed"] == 1.5
        assert call_kwargs["output_format"] == "aac"


# ---------------------------------------------------------------------------
# generate_audio — state saved
# ---------------------------------------------------------------------------


class TestGenerateAudioStateSaved:
    """generate_audio() persists state via state.save()."""

    def test_generate_audio_state_saved(self, state_with_scene, mock_provider):
        """Verify state.save() is called by reloading from disk."""
        scene = state_with_scene.metadata.scenes[0]
        generate_audio(scene, state_with_scene, mock_provider)

        reloaded = ProjectState.load(state_with_scene.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.audio == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_audio — multi-digit scene number
# ---------------------------------------------------------------------------


class TestGenerateAudioMultiDigitSceneNumber:
    """generate_audio() zero-pads scene numbers in filenames."""

    def test_generate_audio_zero_pads_scene_number(self, tmp_path, mock_provider):
        """Scene 12 produces scene_12.mp3."""
        state = ProjectState.create(
            project_id="multi-digit-test",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(12, "Scene Twelve", "The twelfth scene of the story.")
        state.update_scene_asset(12, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(12, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_audio(scene, state, mock_provider)

        audio_path = state.project_dir / "audio" / "scene_12.mp3"
        assert audio_path.exists()
