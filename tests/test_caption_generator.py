"""Tests for story_video.pipeline.caption_generator — caption generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the caption generator module.
"""

import json
from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, AssetType, InputMode, SceneStatus, TTSConfig
from story_video.pipeline.caption_generator import (
    CaptionProvider,
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    OpenAIWhisperProvider,
    _reconcile_punctuation,
    generate_captions,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


def _make_whisper_response():
    """Return a mock Whisper API response with segments, words, language, duration."""
    seg = MagicMock()
    seg.text = "The storm raged on."
    seg.start = 0.0
    seg.end = 2.5

    word1 = MagicMock()
    word1.word = "The"
    word1.start = 0.0
    word1.end = 0.3

    word2 = MagicMock()
    word2.word = "storm"
    word2.start = 0.4
    word2.end = 0.8

    word3 = MagicMock()
    word3.word = "raged"
    word3.start = 0.9
    word3.end = 1.4

    word4 = MagicMock()
    word4.word = "on."
    word4.start = 1.5
    word4.end = 2.5

    response = MagicMock()
    response.segments = [seg]
    response.words = [word1, word2, word3, word4]
    response.language = "en"
    response.duration = 2.5

    return response


def _make_caption_result():
    """Return a CaptionResult matching the Whisper mock response."""
    return CaptionResult(
        segments=[CaptionSegment(text="The storm raged on.", start=0.0, end=2.5)],
        words=[
            CaptionWord(word="The", start=0.0, end=0.3),
            CaptionWord(word="storm", start=0.4, end=0.8),
            CaptionWord(word="raged", start=0.9, end=1.4),
            CaptionWord(word="on.", start=1.5, end=2.5),
        ],
        language="en",
        duration=2.5,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_openai(monkeypatch):
    """Patch openai.OpenAI to return a mock client."""
    mock_client = MagicMock()
    mock_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("story_video.pipeline.caption_generator.openai.OpenAI", mock_class)
    return mock_client


@pytest.fixture()
def fake_caption_provider():
    """Create a mock caption provider that returns a CaptionResult."""
    provider = MagicMock(spec=CaptionProvider)
    provider.transcribe.return_value = _make_caption_result()
    return provider


@pytest.fixture()
def project_state(tmp_path):
    """Create a project state with one scene ready for caption generation.

    Has a fake audio file in audio/ so generate_captions can find it.
    """
    config = AppConfig(tts=TTSConfig(output_format="mp3"))
    state = ProjectState.create("test-project", InputMode.ADAPT, config, tmp_path)
    state.add_scene(scene_number=1, title="Test Scene", prose="Story text.")
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.AUDIO, SceneStatus.COMPLETED)
    state.save()

    # Create a fake audio file
    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    audio_path = audio_dir / "scene_001.mp3"
    audio_path.write_bytes(b"fake audio content")

    return state


# ---------------------------------------------------------------------------
# OpenAIWhisperProvider — maps response to CaptionResult
# ---------------------------------------------------------------------------


class TestTranscribeReturnsCaptionResult:
    """OpenAIWhisperProvider.transcribe() maps Whisper response to CaptionResult."""

    @pytest.fixture()
    def caption_result(self, mock_openai, tmp_path):
        """Transcribe a fake audio file and return the CaptionResult."""
        whisper_response = _make_whisper_response()
        mock_openai.audio.transcriptions.create.return_value = whisper_response

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()
        return provider.transcribe(audio_file)

    def test_returns_caption_result_instance(self, caption_result):
        """transcribe() returns a CaptionResult instance."""
        assert isinstance(caption_result, CaptionResult)

    def test_segment_count(self, caption_result):
        """Result contains the expected number of segments."""
        assert len(caption_result.segments) == 1

    def test_segment_text_and_timing(self, caption_result):
        """Segment text and start/end times match the Whisper response."""
        seg = caption_result.segments[0]
        assert seg.text == "The storm raged on."
        assert seg.start == 0.0
        assert seg.end == 2.5

    def test_word_count_and_timing(self, caption_result):
        """Word count and representative word timings match the Whisper response."""
        assert len(caption_result.words) == 4
        assert caption_result.words[0].word == "The"
        assert caption_result.words[0].start == 0.0
        assert caption_result.words[0].end == 0.3
        assert caption_result.words[3].word == "on."

    def test_language(self, caption_result):
        """Detected language matches the Whisper response."""
        assert caption_result.language == "en"

    def test_duration(self, caption_result):
        """Duration matches the Whisper response."""
        assert caption_result.duration == 2.5


# ---------------------------------------------------------------------------
# OpenAIWhisperProvider — API key from environment
# ---------------------------------------------------------------------------


class TestOpenAIWhisperProviderReadsApiKeyFromEnv:
    """OpenAIWhisperProvider reads OPENAI_API_KEY from the environment."""

    def test_client_reads_api_key_from_env(self, monkeypatch):
        """OpenAI() is called without explicit API key (reads from env)."""
        mock_client = MagicMock()
        mock_class = MagicMock(return_value=mock_client)
        monkeypatch.setattr("story_video.pipeline.caption_generator.openai.OpenAI", mock_class)

        _ = OpenAIWhisperProvider()

        mock_class.assert_called_once_with()


# ---------------------------------------------------------------------------
# OpenAIWhisperProvider — passes correct params
# ---------------------------------------------------------------------------


class TestTranscribePassesCorrectParams:
    """OpenAIWhisperProvider.transcribe() passes correct parameters to the SDK."""

    def test_passes_model_and_format(self, mock_openai, tmp_path):
        """transcribe() passes whisper-1, verbose_json, and timestamp_granularities."""
        whisper_response = _make_whisper_response()
        mock_openai.audio.transcriptions.create.return_value = whisper_response

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()
        provider.transcribe(audio_file)

        call_kwargs = mock_openai.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["response_format"] == "verbose_json"
        assert call_kwargs["timestamp_granularities"] == ["word", "segment"]


# ---------------------------------------------------------------------------
# OpenAIWhisperProvider — retry on transient errors
# ---------------------------------------------------------------------------


class TestTranscribeRetryBehavior:
    """OpenAIWhisperProvider.transcribe() retries on transient API errors."""

    def test_retries_on_connection_error(self, mock_openai, tmp_path):
        """transcribe() retries on APIConnectionError then succeeds."""
        from openai import APIConnectionError

        whisper_response = _make_whisper_response()

        mock_openai.audio.transcriptions.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            whisper_response,
        ]

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()
        result = provider.transcribe(audio_file)

        assert isinstance(result, CaptionResult)
        assert mock_openai.audio.transcriptions.create.call_count == 2

    def test_retries_on_rate_limit(self, mock_openai, tmp_path):
        """transcribe() retries on RateLimitError then succeeds."""
        from openai import RateLimitError

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.json.return_value = {"error": {"message": "rate limited"}}

        whisper_response = _make_whisper_response()

        mock_openai.audio.transcriptions.create.side_effect = [
            RateLimitError(
                message="rate limited",
                response=response_429,
                body={"error": {"message": "rate limited"}},
            ),
            whisper_response,
        ]

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()
        result = provider.transcribe(audio_file)

        assert isinstance(result, CaptionResult)
        assert mock_openai.audio.transcriptions.create.call_count == 2

    def test_retries_on_server_error(self, mock_openai, tmp_path):
        """transcribe() retries on InternalServerError then succeeds."""
        from openai import InternalServerError

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.json.return_value = {"error": {"message": "server error"}}

        whisper_response = _make_whisper_response()

        mock_openai.audio.transcriptions.create.side_effect = [
            InternalServerError(
                message="server error",
                response=response_500,
                body={"error": {"message": "server error"}},
            ),
            whisper_response,
        ]

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()
        result = provider.transcribe(audio_file)

        assert isinstance(result, CaptionResult)
        assert mock_openai.audio.transcriptions.create.call_count == 2

    def test_no_retry_on_auth_error(self, mock_openai, tmp_path):
        """transcribe() does not retry on AuthenticationError."""
        from openai import AuthenticationError

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.json.return_value = {"error": {"message": "invalid key"}}

        mock_openai.audio.transcriptions.create.side_effect = AuthenticationError(
            message="invalid key",
            response=response_401,
            body={"error": {"message": "invalid key"}},
        )

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()

        with pytest.raises(AuthenticationError):
            provider.transcribe(audio_file)

        assert mock_openai.audio.transcriptions.create.call_count == 1

    def test_no_retry_on_permission_error(self, mock_openai, tmp_path):
        """transcribe() does not retry on PermissionDeniedError."""
        from openai import PermissionDeniedError

        response_403 = MagicMock()
        response_403.status_code = 403
        response_403.json.return_value = {"error": {"message": "permission denied"}}

        mock_openai.audio.transcriptions.create.side_effect = PermissionDeniedError(
            message="permission denied",
            response=response_403,
            body={"error": {"message": "permission denied"}},
        )

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        provider = OpenAIWhisperProvider()

        with pytest.raises(PermissionDeniedError):
            provider.transcribe(audio_file)

        assert mock_openai.audio.transcriptions.create.call_count == 1


# ---------------------------------------------------------------------------
# CaptionResult model — serialization
# ---------------------------------------------------------------------------


class TestCaptionResultModel:
    """CaptionResult Pydantic model serialization tests."""

    def test_round_trip_preserves_equality(self):
        """CaptionResult survives serialize → deserialize round trip with equality."""
        original = _make_caption_result()
        json_str = original.model_dump_json(indent=2)
        restored = CaptionResult.model_validate_json(json_str)

        assert restored == original

    def test_round_trip_preserves_segment_text(self):
        """Segment text survives serialize → deserialize round trip."""
        original = _make_caption_result()
        json_str = original.model_dump_json(indent=2)
        restored = CaptionResult.model_validate_json(json_str)

        assert restored.segments[0].text == "The storm raged on."

    def test_round_trip_preserves_word(self):
        """Word text survives serialize → deserialize round trip."""
        original = _make_caption_result()
        json_str = original.model_dump_json(indent=2)
        restored = CaptionResult.model_validate_json(json_str)

        assert restored.words[0].word == "The"

    def test_round_trip_preserves_language(self):
        """Language survives serialize → deserialize round trip."""
        original = _make_caption_result()
        json_str = original.model_dump_json(indent=2)
        restored = CaptionResult.model_validate_json(json_str)

        assert restored.language == "en"

    def test_round_trip_preserves_duration(self):
        """Duration survives serialize → deserialize round trip."""
        original = _make_caption_result()
        json_str = original.model_dump_json(indent=2)
        restored = CaptionResult.model_validate_json(json_str)

        assert restored.duration == 2.5

    def test_empty_segments_and_words(self):
        """CaptionResult accepts empty segment and word lists."""
        result = CaptionResult(
            segments=[],
            words=[],
            language="en",
            duration=0.0,
        )

        assert result.segments == []
        assert result.words == []
        assert result.language == "en"
        assert result.duration == 0.0


# ---------------------------------------------------------------------------
# generate_captions — happy path
# ---------------------------------------------------------------------------


class TestGenerateCaptionsHappyPath:
    """generate_captions() writes caption JSON and updates state."""

    def test_writes_caption_json_creates_file(self, project_state, fake_caption_provider):
        """Caption JSON file is created on disk."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        caption_path = project_state.project_dir / "captions" / "scene_001.json"
        assert caption_path.exists()

    def test_writes_caption_json_language(self, project_state, fake_caption_provider):
        """Caption JSON contains correct language."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        caption_path = project_state.project_dir / "captions" / "scene_001.json"
        content = json.loads(caption_path.read_text(encoding="utf-8"))
        assert content["language"] == "en"

    def test_writes_caption_json_duration(self, project_state, fake_caption_provider):
        """Caption JSON contains correct duration."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        caption_path = project_state.project_dir / "captions" / "scene_001.json"
        content = json.loads(caption_path.read_text(encoding="utf-8"))
        assert content["duration"] == 2.5

    def test_writes_caption_json_segments(self, project_state, fake_caption_provider):
        """Caption JSON contains correct segments."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        caption_path = project_state.project_dir / "captions" / "scene_001.json"
        content = json.loads(caption_path.read_text(encoding="utf-8"))
        assert len(content["segments"]) == 1
        assert content["segments"][0]["text"] == "The storm raged on."

    def test_writes_caption_json_words(self, project_state, fake_caption_provider):
        """Caption JSON contains correct words."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        caption_path = project_state.project_dir / "captions" / "scene_001.json"
        content = json.loads(caption_path.read_text(encoding="utf-8"))
        assert len(content["words"]) == 4
        assert content["words"][0]["word"] == "The"

    def test_updates_asset_status(self, project_state, fake_caption_provider):
        """Scene asset_status.captions is COMPLETED after generation."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        assert scene.asset_status.captions == SceneStatus.COMPLETED

    def test_saves_state(self, project_state, fake_caption_provider):
        """State is persisted — reload from disk, verify status."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        reloaded = ProjectState.load(project_state.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.captions == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_captions — provider call
# ---------------------------------------------------------------------------


class TestGenerateCaptionsProviderCall:
    """generate_captions() passes the correct audio path to the provider."""

    def test_passes_correct_audio_path(self, project_state, fake_caption_provider):
        """Provider receives the correct Path to the audio file."""
        scene = project_state.metadata.scenes[0]
        generate_captions(scene, project_state, fake_caption_provider)

        expected_path = project_state.project_dir / "audio" / "scene_001.mp3"
        fake_caption_provider.transcribe.assert_called_once_with(expected_path)


# ---------------------------------------------------------------------------
# generate_captions — validation
# ---------------------------------------------------------------------------


class TestGenerateCaptionsValidation:
    """generate_captions() raises when audio file is missing."""

    def test_raises_when_audio_file_missing(self, tmp_path, fake_caption_provider):
        """FileNotFoundError raised when the audio file does not exist."""
        config = AppConfig(tts=TTSConfig(output_format="mp3"))
        state = ProjectState.create("missing-audio", InputMode.ADAPT, config, tmp_path)
        state.add_scene(scene_number=1, title="Test Scene", prose="Story text.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.AUDIO, SceneStatus.COMPLETED)
        state.save()

        # Intentionally do NOT create the audio file
        scene = state.metadata.scenes[0]

        with pytest.raises(FileNotFoundError):
            generate_captions(scene, state, fake_caption_provider)


# ---------------------------------------------------------------------------
# generate_captions — multi-digit scene number
# ---------------------------------------------------------------------------


class TestGenerateCaptionsMultiDigitScene:
    """generate_captions() zero-pads scene numbers in filenames."""

    def test_scene_number_zero_padded(self, tmp_path, fake_caption_provider):
        """Scene 12 reads scene_012.mp3 and writes scene_012.json."""
        config = AppConfig(tts=TTSConfig(output_format="mp3"))
        state = ProjectState.create("multi-digit-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(scene_number=12, title="Scene Twelve", prose="The twelfth scene.")
        state.update_scene_asset(12, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(12, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(12, AssetType.AUDIO, SceneStatus.COMPLETED)
        state.save()

        # Create a fake audio file with the correct name
        audio_dir = state.project_dir / "audio"
        audio_dir.mkdir(exist_ok=True)
        (audio_dir / "scene_012.mp3").write_bytes(b"fake audio")

        scene = state.metadata.scenes[0]
        generate_captions(scene, state, fake_caption_provider)

        caption_path = state.project_dir / "captions" / "scene_012.json"
        assert caption_path.exists()


# ---------------------------------------------------------------------------
# _reconcile_punctuation — restores punctuation from segments to words
# ---------------------------------------------------------------------------


class TestReconcilePunctuation:
    """_reconcile_punctuation restores punctuation from segments to words."""

    def test_appends_period_to_final_word(self):
        """Period from segment text is appended to matching word."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The storm raged on.", start=0.0, end=2.5)],
            words=[
                CaptionWord(word="The", start=0.0, end=0.3),
                CaptionWord(word="storm", start=0.4, end=0.8),
                CaptionWord(word="raged", start=0.9, end=1.4),
                CaptionWord(word="on", start=1.5, end=2.5),
            ],
            language="en",
            duration=2.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[3].word == "on."

    def test_appends_comma(self):
        """Comma from segment text is appended to matching word."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello, world.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="Hello", start=0.0, end=0.5),
                CaptionWord(word="world", start=0.6, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Hello,"
        assert reconciled.words[1].word == "world."

    def test_preserves_existing_punctuation(self):
        """Words that already have punctuation are left unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The storm raged on.", start=0.0, end=2.5)],
            words=[
                CaptionWord(word="The", start=0.0, end=0.3),
                CaptionWord(word="storm", start=0.4, end=0.8),
                CaptionWord(word="raged", start=0.9, end=1.4),
                CaptionWord(word="on.", start=1.5, end=2.5),
            ],
            language="en",
            duration=2.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[3].word == "on."

    def test_multiple_segments(self):
        """Punctuation reconciliation works across multiple segments."""
        result = CaptionResult(
            segments=[
                CaptionSegment(text="Hello, world.", start=0.0, end=1.5),
                CaptionSegment(text="How are you?", start=2.0, end=3.5),
            ],
            words=[
                CaptionWord(word="Hello", start=0.0, end=0.5),
                CaptionWord(word="world", start=0.6, end=1.5),
                CaptionWord(word="How", start=2.0, end=2.3),
                CaptionWord(word="are", start=2.4, end=2.7),
                CaptionWord(word="you", start=2.8, end=3.5),
            ],
            language="en",
            duration=3.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Hello,"
        assert reconciled.words[1].word == "world."
        assert reconciled.words[4].word == "you?"

    def test_unmatched_word_left_unchanged(self):
        """Words that can't be found in segment text stay unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The storm.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="Da", start=0.0, end=0.5),
                CaptionWord(word="storm", start=0.6, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Da"

    def test_empty_words_returns_unchanged(self):
        """Empty word list returns the result unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello.", start=0.0, end=1.0)],
            words=[],
            language="en",
            duration=1.0,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words == []

    def test_exclamation_mark(self):
        """Exclamation mark from segment is appended."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Run!", start=0.0, end=0.5)],
            words=[CaptionWord(word="Run", start=0.0, end=0.5)],
            language="en",
            duration=0.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Run!"

    def test_em_dash_and_quotes(self):
        """Trailing punctuation like comma after 'said' is appended."""
        result = CaptionResult(
            segments=[CaptionSegment(text='She said, "hello" \u2014', start=0.0, end=2.0)],
            words=[
                CaptionWord(word="She", start=0.0, end=0.3),
                CaptionWord(word="said", start=0.4, end=0.7),
                CaptionWord(word="hello", start=0.8, end=1.2),
            ],
            language="en",
            duration=2.0,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[1].word == "said,"
