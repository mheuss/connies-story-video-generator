"""Tests for story_video.pipeline.tts_generator — TTS audio generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the TTS generator module.
"""

from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, AssetType, InputMode, SceneStatus, StoryHeader, TTSConfig
from story_video.pipeline.tts_generator import (
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
    TTSProvider,
    _mood_to_elevenlabs_text,
    _mood_to_instructions,
    generate_audio,
    generate_mp3_silence,
)
from story_video.state import ProjectState
from tests.error_factories import (
    make_openai_connection_error,
    make_openai_rate_limit_error,
    make_openai_server_error,
)

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

    def test_params_shape(self, mock_openai):
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

        kwargs = mock_openai.audio.speech.create.call_args.kwargs
        assert kwargs["model"] == "tts-1"
        assert kwargs["voice"] == "echo"
        assert kwargs["input"] == "Once upon a time"
        assert kwargs["speed"] == 1.5
        assert kwargs["response_format"] == "opus"


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

    @pytest.mark.parametrize(
        "error_factory",
        [make_openai_connection_error, make_openai_rate_limit_error, make_openai_server_error],
        ids=["connection", "rate_limit", "server"],
    )
    def test_synthesize_retries_on_transient_error(self, mock_openai, error_factory):
        """synthesize() retries on transient error then succeeds."""
        response = MagicMock()
        response.content = b"recovered-audio"

        mock_openai.audio.speech.create.side_effect = [error_factory(), response]

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

    @pytest.mark.parametrize(
        "error_name,status,message",
        [
            ("AuthenticationError", 401, "invalid key"),
            ("BadRequestError", 400, "bad request"),
            ("PermissionDeniedError", 403, "permission denied"),
        ],
        ids=["auth", "bad_request", "permission"],
    )
    def test_synthesize_no_retry_on_permanent_error(self, mock_openai, error_name, status, message):
        """synthesize() does not retry on permanent error."""
        import openai

        error_cls = getattr(openai, error_name)
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.json.return_value = {"error": {"message": message}}

        mock_openai.audio.speech.create.side_effect = error_cls(
            message=message,
            response=mock_response,
            body={"error": {"message": message}},
        )

        provider = OpenAITTSProvider()

        with pytest.raises(error_cls):
            provider.synthesize(
                text="test",
                voice="nova",
                model="tts-1-hd",
                speed=1.0,
                output_format="mp3",
            )

        assert mock_openai.audio.speech.create.call_count == 1


# ---------------------------------------------------------------------------
# OpenAITTSProvider — instructions parameter
# ---------------------------------------------------------------------------


class TestOpenAITTSProviderInstructions:
    """OpenAI provider forwards instructions to the API."""

    def test_instructions_passed_to_api(self, mock_openai):
        mock_response = MagicMock()
        mock_response.content = b"audio-bytes"
        mock_openai.audio.speech.create.return_value = mock_response

        provider = OpenAITTSProvider()
        provider.synthesize(
            "Hello",
            "nova",
            "gpt-4o-mini-tts",
            1.0,
            "mp3",
            instructions="Speak sadly",
        )

        call_kwargs = mock_openai.audio.speech.create.call_args.kwargs
        assert call_kwargs["instructions"] == "Speak sadly"

    def test_instructions_omitted_when_none(self, mock_openai):
        mock_response = MagicMock()
        mock_response.content = b"audio-bytes"
        mock_openai.audio.speech.create.return_value = mock_response

        provider = OpenAITTSProvider()
        provider.synthesize("Hello", "nova", "gpt-4o-mini-tts", 1.0, "mp3", instructions=None)

        call_kwargs = mock_openai.audio.speech.create.call_args.kwargs
        assert "instructions" not in call_kwargs


# ---------------------------------------------------------------------------
# generate_audio — happy path
# ---------------------------------------------------------------------------


class TestGenerateAudioHappyPath:
    """generate_audio() writes audio file and updates state."""

    def test_happy_path(self, state_with_scene, mock_provider):
        """Audio file is created with correct bytes and state is updated."""
        scene = state_with_scene.metadata.scenes[0]
        generate_audio(scene, state_with_scene, mock_provider)

        audio_path = state_with_scene.project_dir / "audio" / "scene_001.mp3"
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"fake-audio-bytes"
        assert scene.asset_status.audio == SceneStatus.COMPLETED


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

        audio_path = state.project_dir / "audio" / "scene_001.opus"
        assert audio_path.exists()


# ---------------------------------------------------------------------------
# generate_audio — config params passed to provider
# ---------------------------------------------------------------------------


class TestGenerateAudioConfigParamsPassedToProvider:
    """generate_audio() passes TTS config values to the provider."""

    def test_config_params_shape(self, tmp_path, mock_provider):
        """All TTS config values are forwarded to the provider."""
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

        kwargs = mock_provider.synthesize.call_args.kwargs
        assert kwargs["voice"] == "echo"
        assert kwargs["model"] == "tts-1"
        assert kwargs["speed"] == 1.5
        assert kwargs["output_format"] == "aac"


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
        """Scene 12 produces scene_012.mp3."""
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

        audio_path = state.project_dir / "audio" / "scene_012.mp3"
        assert audio_path.exists()


# ---------------------------------------------------------------------------
# ElevenLabsTTSProvider — mood prepended as audio tag
# ---------------------------------------------------------------------------


class TestElevenLabsTTSProvider:
    """ElevenLabs provider translates mood to audio tags."""

    @pytest.fixture()
    def mock_elevenlabs(self, monkeypatch):
        """Patch elevenlabs.ElevenLabs to return a mock client."""
        mock_client = MagicMock()
        mock_class = MagicMock(return_value=mock_client)
        monkeypatch.setattr("story_video.pipeline.tts_generator.elevenlabs.ElevenLabs", mock_class)
        return mock_client

    def test_mood_prepended_as_audio_tag(self, mock_elevenlabs):
        """Any mood is passed through as a freeform v3 audio tag."""
        mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])

        provider = ElevenLabsTTSProvider()
        provider.synthesize(
            "Hello",
            "voice-id",
            "eleven_v3",
            1.0,
            "mp3_44100_128",
            mood="sad",
        )

        call_kwargs = mock_elevenlabs.text_to_speech.convert.call_args.kwargs
        text_sent = call_kwargs["text"]
        assert text_sent == "[sad] Hello"

    def test_freeform_mood_passed_through(self, mock_elevenlabs):
        """Freeform moods like 'thoughtful' are passed directly as tags."""
        mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])

        provider = ElevenLabsTTSProvider()
        provider.synthesize(
            "Hello",
            "voice-id",
            "eleven_v3",
            1.0,
            "mp3_44100_128",
            mood="thoughtful",
        )

        call_kwargs = mock_elevenlabs.text_to_speech.convert.call_args.kwargs
        text_sent = call_kwargs["text"]
        assert text_sent == "[thoughtful] Hello"

    def test_no_mood_sends_plain_text(self, mock_elevenlabs):
        mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])

        provider = ElevenLabsTTSProvider()
        provider.synthesize("Hello", "voice-id", "eleven_v3", 1.0, "mp3_44100_128", mood=None)

        call_kwargs = mock_elevenlabs.text_to_speech.convert.call_args.kwargs
        text_sent = call_kwargs["text"]
        assert text_sent == "Hello"

    def test_speed_warning_logged(self, mock_elevenlabs, caplog):
        """Non-1.0 speed logs a warning since ElevenLabs ignores it."""
        import logging

        mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])

        provider = ElevenLabsTTSProvider()
        with caplog.at_level(logging.WARNING):
            provider.synthesize("Hello", "voice-id", "eleven_v3", 1.5, "mp3_44100_128")

        assert any("speed" in r.message.lower() for r in caplog.records)

    def test_no_speed_warning_at_default(self, mock_elevenlabs, caplog):
        """Speed 1.0 does not log a warning."""
        import logging

        mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])

        provider = ElevenLabsTTSProvider()
        with caplog.at_level(logging.WARNING):
            provider.synthesize("Hello", "voice-id", "eleven_v3", 1.0, "mp3_44100_128")

        assert not any("speed" in r.message.lower() for r in caplog.records)

    def test_speed_warning_logged_once(self, mock_elevenlabs, caplog):
        """Speed warning is only logged on the first call, not subsequent ones."""
        import logging

        mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])

        provider = ElevenLabsTTSProvider()
        with caplog.at_level(logging.WARNING):
            provider.synthesize("Hello", "voice-id", "eleven_v3", 1.5, "mp3_44100_128")
            caplog.clear()
            mock_elevenlabs.text_to_speech.convert.return_value = iter([b"audio-bytes"])
            provider.synthesize("Hello", "voice-id", "eleven_v3", 1.5, "mp3_44100_128")

        assert not any("speed" in r.message.lower() for r in caplog.records)

    def test_retry_on_connection_error(self, mock_elevenlabs):
        """ElevenLabs retries on ConnectionError then succeeds."""
        mock_elevenlabs.text_to_speech.convert.side_effect = [
            ConnectionError("network failed"),
            iter([b"recovered-audio"]),
        ]

        provider = ElevenLabsTTSProvider()
        result = provider.synthesize("Hello", "voice-id", "eleven_v3", 1.0, "mp3_44100_128")

        assert result == b"recovered-audio"
        assert mock_elevenlabs.text_to_speech.convert.call_count == 2

    def test_no_retry_on_auth_error(self, mock_elevenlabs):
        """ElevenLabs auth error (4xx) is not retried."""
        from elevenlabs import UnauthorizedError

        mock_elevenlabs.text_to_speech.convert.side_effect = UnauthorizedError(body="unauthorized")

        provider = ElevenLabsTTSProvider()
        with pytest.raises(UnauthorizedError):
            provider.synthesize("Hello", "voice-id", "eleven_v3", 1.0, "mp3_44100_128")

        assert mock_elevenlabs.text_to_speech.convert.call_count == 1


# ---------------------------------------------------------------------------
# _mood_to_elevenlabs_text — freeform v3 audio tags
# ---------------------------------------------------------------------------


class TestMoodToElevenLabsText:
    """_mood_to_elevenlabs_text passes any mood through as a v3 audio tag."""

    def test_none_mood_returns_plain_text(self):
        """None mood returns text unchanged."""
        result = _mood_to_elevenlabs_text("Hello world", None)
        assert result == "Hello world"

    def test_all_story_moods_produce_tags(self):
        """All moods used in the two-voice test story produce audio tags."""
        story_moods = ["dry", "thoughtful", "warm", "surprised", "gentle", "amused"]
        for mood in story_moods:
            result = _mood_to_elevenlabs_text("Hello", mood)
            assert result == f"[{mood}] Hello", f"Failed for mood={mood}"


# ---------------------------------------------------------------------------
# _mood_to_instructions — mood to natural language
# ---------------------------------------------------------------------------


class TestMoodToInstructions:
    """_mood_to_instructions converts mood tags to instruction strings."""

    def test_none_returns_none(self):
        assert _mood_to_instructions(None) is None

    def test_mood_returns_instruction(self):
        assert _mood_to_instructions("sad") == "Speak in a sad tone"

    def test_vowel_mood_uses_an(self):
        assert _mood_to_instructions("excited") == "Speak in an excited tone"

    def test_angry_mood_uses_an(self):
        assert _mood_to_instructions("angry") == "Speak in an angry tone"


# ---------------------------------------------------------------------------
# generate_audio — multi-segment narration
# ---------------------------------------------------------------------------


class TestGenerateAudioMultiSegment:
    """generate_audio handles multi-segment narration."""

    @pytest.fixture()
    def state_with_header(self, tmp_path):
        """Create project state for multi-segment testing."""
        state = ProjectState.create(
            project_id="multi-seg-test",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(1, "The Storm", "The storm raged on.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        return state

    def test_single_segment_backward_compat(self, state_with_header, mock_provider):
        """Scene without story_header produces one synthesize call."""
        scene = state_with_header.metadata.scenes[0]
        generate_audio(scene, state_with_header, mock_provider)
        assert mock_provider.synthesize.call_count == 1

    def test_multi_segment_multiple_calls(self, state_with_header, mock_provider):
        """Scene with voice tags produces one synthesize call per segment."""
        scene = state_with_header.metadata.scenes[0]
        scene.narration_text = 'Hello. **voice:jane** "Hi!" she said.'
        header = StoryHeader(voices={"narrator": "nova", "jane": "shimmer"})
        generate_audio(scene, state_with_header, mock_provider, story_header=header)
        assert mock_provider.synthesize.call_count == 2

    def test_multi_segment_concatenates_bytes(self, state_with_header, mock_provider):
        """Multiple segments produce concatenated audio file."""
        mock_provider.synthesize.side_effect = [b"chunk1", b"chunk2"]
        scene = state_with_header.metadata.scenes[0]
        scene.narration_text = "Hello. **voice:jane** Bye."
        header = StoryHeader(voices={"narrator": "nova", "jane": "shimmer"})
        generate_audio(scene, state_with_header, mock_provider, story_header=header)

        audio_path = state_with_header.project_dir / "audio" / "scene_001.mp3"
        assert audio_path.read_bytes() == b"chunk1chunk2"

    def test_mood_passed_as_instructions_and_mood(self, state_with_header, mock_provider):
        """Mood tag is converted to instructions and mood is passed directly."""
        scene = state_with_header.metadata.scenes[0]
        scene.narration_text = "**mood:sad** Goodbye."
        header = StoryHeader(voices={"narrator": "nova"})
        generate_audio(scene, state_with_header, mock_provider, story_header=header)

        call_kwargs = mock_provider.synthesize.call_args.kwargs
        assert call_kwargs["instructions"] == "Speak in a sad tone"
        assert call_kwargs["mood"] == "sad"

    def test_no_header_uses_config_voice(self, state_with_header, mock_provider):
        """Scene without story header uses config default voice."""
        scene = state_with_header.metadata.scenes[0]
        generate_audio(scene, state_with_header, mock_provider, story_header=None)

        call_kwargs = mock_provider.synthesize.call_args.kwargs
        assert call_kwargs["voice"] == "nova"  # AppConfig default

    def test_non_concat_safe_format_with_multi_segment_raises(self, tmp_path, mock_provider):
        """Multi-segment with non-concatenatable format raises ValueError."""
        config = AppConfig(tts=TTSConfig(output_format="aac"))
        state = ProjectState.create("fmt-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Scene", "Hello. **voice:jane** Bye.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]
        header = StoryHeader(voices={"narrator": "nova", "jane": "shimmer"})

        with pytest.raises(ValueError, match="[Cc]oncatenat"):
            generate_audio(scene, state, mock_provider, story_header=header)

    def test_header_no_tags_uses_default_voice(self, state_with_header, mock_provider):
        """Story header with no tags in text uses the header's default voice."""
        scene = state_with_header.metadata.scenes[0]
        scene.narration_text = "Just plain narration text."
        header = StoryHeader(voices={"narrator": "alloy"})
        generate_audio(scene, state_with_header, mock_provider, story_header=header)

        call_kwargs = mock_provider.synthesize.call_args.kwargs
        assert call_kwargs["voice"] == "alloy"

    def test_single_segment_non_concat_format_allowed(self, tmp_path, mock_provider):
        """Single segment with any format is fine (no concatenation needed)."""
        config = AppConfig(tts=TTSConfig(output_format="aac"))
        state = ProjectState.create("fmt-single", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Scene", "Just one voice speaking.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]
        header = StoryHeader(voices={"narrator": "nova"})

        generate_audio(scene, state, mock_provider, story_header=header)
        assert mock_provider.synthesize.call_count == 1


# ---------------------------------------------------------------------------
# generate_audio — tags without header raises ValueError
# ---------------------------------------------------------------------------


class TestGenerateAudioTagsWithoutHeader:
    """generate_audio raises when text has voice/mood tags but no header."""

    def test_voice_tag_without_header_raises(self, tmp_path):
        """Voice tag in text with story_header=None raises ValueError."""
        provider = MagicMock(spec=TTSProvider)
        state = ProjectState.create("tag-check", InputMode.ADAPT, AppConfig(), tmp_path)
        state.add_scene(1, "Scene", "Hello. **voice:jane** Hi!")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]

        with pytest.raises(ValueError, match="[Vv]oice.*tag.*found.*no.*header"):
            generate_audio(scene, state, provider, story_header=None)

    def test_mood_tag_without_header_raises(self, tmp_path):
        """Mood tag in text with story_header=None raises ValueError."""
        provider = MagicMock(spec=TTSProvider)
        state = ProjectState.create("tag-check-2", InputMode.ADAPT, AppConfig(), tmp_path)
        state.add_scene(1, "Scene", "**mood:sad** Goodbye.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]

        with pytest.raises(ValueError, match="[Vv]oice.*tag.*found.*no.*header"):
            generate_audio(scene, state, provider, story_header=None)

    def test_no_tags_without_header_works(self, tmp_path):
        """Plain text without tags and no header works fine."""
        provider = MagicMock(spec=TTSProvider)
        provider.synthesize.return_value = b"audio"
        state = ProjectState.create("no-tags", InputMode.ADAPT, AppConfig(), tmp_path)
        state.add_scene(1, "Scene", "Just plain text.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]

        generate_audio(scene, state, provider, story_header=None)
        assert provider.synthesize.call_count == 1


# ---------------------------------------------------------------------------
# generate_mp3_silence — silent MP3 generation
# ---------------------------------------------------------------------------


class TestGenerateMp3Silence:
    """generate_mp3_silence produces valid silent MP3 bytes."""

    def test_returns_non_empty_bytes(self):
        """Returns non-empty bytes object."""
        result = generate_mp3_silence(0.5)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_longer_duration_produces_more_bytes(self):
        """2 seconds produces more bytes than 0.5 seconds."""
        short = generate_mp3_silence(0.5)
        long = generate_mp3_silence(2.0)
        assert len(long) > len(short)

    def test_starts_with_mp3_sync(self):
        """First two bytes contain MP3 frame sync (0xFF followed by 0xE0+ mask)."""
        result = generate_mp3_silence(0.5)
        assert result[0] == 0xFF
        assert (result[1] & 0xE0) == 0xE0

    def test_zero_duration_raises(self):
        """Zero duration raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            generate_mp3_silence(0.0)

    def test_negative_duration_raises(self):
        """Negative duration raises ValueError."""
        with pytest.raises(ValueError, match="must be positive"):
            generate_mp3_silence(-1.0)


# ---------------------------------------------------------------------------
# generate_audio — pause segments insert silence
# ---------------------------------------------------------------------------


class TestGenerateAudioWithPause:
    """generate_audio handles pause segments by inserting silence."""

    @pytest.fixture()
    def state_for_pause(self, tmp_path):
        """Create project state for pause tag testing."""
        state = ProjectState.create(
            project_id="pause-test",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(1, "The Pause", "Text with a pause.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        return state

    def test_pause_segment_not_sent_to_provider(self, state_for_pause, mock_provider):
        """Pause segments do not call provider.synthesize."""
        scene = state_for_pause.metadata.scenes[0]
        scene.narration_text = "Hello. **pause:0.5** Goodbye."
        header = StoryHeader(voices={"narrator": "nova"})
        generate_audio(scene, state_for_pause, mock_provider, story_header=header)
        # 2 speech segments, 0 pause calls
        assert mock_provider.synthesize.call_count == 2

    def test_pause_produces_audio_file(self, state_for_pause, mock_provider):
        """Audio file is created even with pause segments."""
        scene = state_for_pause.metadata.scenes[0]
        scene.narration_text = "Hello. **pause:0.5** Goodbye."
        header = StoryHeader(voices={"narrator": "nova"})
        generate_audio(scene, state_for_pause, mock_provider, story_header=header)
        audio_path = state_for_pause.project_dir / "audio" / "scene_001.mp3"
        assert audio_path.exists()

    def test_pause_audio_contains_silence_bytes(self, state_for_pause, mock_provider):
        """Audio file contains provider bytes AND silence bytes concatenated."""
        mock_provider.synthesize.side_effect = [b"speech1", b"speech2"]
        scene = state_for_pause.metadata.scenes[0]
        scene.narration_text = "Hello. **pause:0.5** Goodbye."
        header = StoryHeader(voices={"narrator": "nova"})
        generate_audio(scene, state_for_pause, mock_provider, story_header=header)
        audio_path = state_for_pause.project_dir / "audio" / "scene_001.mp3"
        data = audio_path.read_bytes()
        # Should be speech1 + silence + speech2
        assert data.startswith(b"speech1")
        assert data.endswith(b"speech2")
        assert len(data) > len(b"speech1") + len(b"speech2")

    def test_pause_tag_without_header_raises(self, tmp_path):
        """Pause tag without story header raises ValueError (same as voice/mood)."""
        provider = MagicMock(spec=TTSProvider)
        state = ProjectState.create("pause-no-header", InputMode.ADAPT, AppConfig(), tmp_path)
        state.add_scene(1, "Scene", "Hello. **pause:0.5** Goodbye.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]
        with pytest.raises(ValueError, match="tag.*found.*no.*header"):
            generate_audio(scene, state, provider, story_header=None)


# ---------------------------------------------------------------------------
# generate_audio — empty provider response
# ---------------------------------------------------------------------------


class TestGenerateAudioEmptyProviderResponse:
    """generate_audio() raises ValueError when provider returns empty bytes."""

    def test_empty_audio_bytes_raises(self, state_with_scene):
        """Provider returning b'' raises ValueError."""
        provider = MagicMock(spec=TTSProvider)
        provider.synthesize.return_value = b""

        scene = state_with_scene.metadata.scenes[0]
        with pytest.raises(ValueError, match="TTS provider returned empty audio"):
            generate_audio(scene, state_with_scene, provider)


# ---------------------------------------------------------------------------
# _mood_to_elevenlabs_text — non-standard instruction format
# ---------------------------------------------------------------------------


class TestGenerateAudioMultiSegmentEmptyResponse:
    """generate_audio raises ValueError when all multi-segment chunks are empty."""

    def test_multi_segment_empty_bytes_raises(self, tmp_path):
        """All segments returning b'' produces empty concat, caught by guard."""
        state = ProjectState.create(
            project_id="empty-multi",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(1, "Test", "Hello. **voice:jane** Bye.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        scene = state.metadata.scenes[0]
        scene.narration_text = "Hello. **voice:jane** Bye."

        provider = MagicMock(spec=TTSProvider)
        provider.synthesize.return_value = b""
        header = StoryHeader(voices={"narrator": "nova", "jane": "shimmer"})

        with pytest.raises(ValueError, match="TTS provider returned empty audio"):
            generate_audio(scene, state, provider, story_header=header)


class TestMoodToElevenLabsTextNonStandard:
    """_mood_to_elevenlabs_text with non-standard mood strings."""

    def test_mood_word_produces_tag(self):
        """A mood word is wrapped as an audio tag."""
        result = _mood_to_elevenlabs_text("Hello", "excited")
        assert result == "[excited] Hello"

    def test_multi_word_mood_produces_tag(self):
        """Multi-word moods are lowercased and wrapped as a tag."""
        result = _mood_to_elevenlabs_text("Hello", "Deeply Sorrowful")
        assert result == "[deeply sorrowful] Hello"
