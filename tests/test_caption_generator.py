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
    _tokenize_prose,
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

    def test_word_count(self, caption_result):
        """Result contains the expected number of words."""
        assert len(caption_result.words) == 4

    def test_first_word_text(self, caption_result):
        """First word text matches the Whisper response."""
        assert caption_result.words[0].word == "The"

    def test_first_word_timing(self, caption_result):
        """First word start and end times match the Whisper response."""
        assert caption_result.words[0].start == 0.0
        assert caption_result.words[0].end == 0.3

    def test_last_word_text(self, caption_result):
        """Last word text matches the Whisper response."""
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
        from tests.error_factories import make_openai_connection_error

        whisper_response = _make_whisper_response()

        mock_openai.audio.transcriptions.create.side_effect = [
            make_openai_connection_error(),
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
        from tests.error_factories import make_openai_rate_limit_error

        whisper_response = _make_whisper_response()

        mock_openai.audio.transcriptions.create.side_effect = [
            make_openai_rate_limit_error(),
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
        from tests.error_factories import make_openai_server_error

        whisper_response = _make_whisper_response()

        mock_openai.audio.transcriptions.create.side_effect = [
            make_openai_server_error(),
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
        reconciled = _reconcile_punctuation(result, "The storm raged on.")
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
        reconciled = _reconcile_punctuation(result, "Hello, world.")
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
        reconciled = _reconcile_punctuation(result, "The storm raged on.")
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
        reconciled = _reconcile_punctuation(result, "Hello, world. How are you?")
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
        reconciled = _reconcile_punctuation(result, "The storm.")
        assert reconciled.words[0].word == "Da"

    def test_empty_words_returns_unchanged(self):
        """Empty word list returns the result unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello.", start=0.0, end=1.0)],
            words=[],
            language="en",
            duration=1.0,
        )
        reconciled = _reconcile_punctuation(result, "Hello.")
        assert reconciled.words == []

    def test_exclamation_mark(self):
        """Exclamation mark from segment is appended."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Run!", start=0.0, end=0.5)],
            words=[CaptionWord(word="Run", start=0.0, end=0.5)],
            language="en",
            duration=0.5,
        )
        reconciled = _reconcile_punctuation(result, "Run!")
        assert reconciled.words[0].word == "Run!"

    def test_appends_comma_to_dialogue_tag(self):
        """Comma after dialogue tag 'said' is appended from prose."""
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
        reconciled = _reconcile_punctuation(result, 'She said, "hello" \u2014')
        assert reconciled.words[1].word == "said,"


# ---------------------------------------------------------------------------
# _tokenize_prose — splits prose into (leading, bare, trailing) tuples
# ---------------------------------------------------------------------------


class TestTokenizeProse:
    """_tokenize_prose splits prose words into (leading, bare, trailing) tuples."""

    def test_plain_word(self):
        """Word with no punctuation returns empty leading and trailing."""
        tokens = _tokenize_prose("hello")
        assert tokens == [("", "hello", "")]

    def test_trailing_period(self):
        """Trailing period is captured."""
        tokens = _tokenize_prose("hello.")
        assert tokens == [("", "hello", ".")]

    def test_trailing_comma(self):
        """Trailing comma is captured."""
        tokens = _tokenize_prose("hello,")
        assert tokens == [("", "hello", ",")]

    def test_leading_double_quote(self):
        """Leading double quote is captured."""
        tokens = _tokenize_prose('"Hello')
        assert tokens == [('"', "Hello", "")]

    def test_trailing_double_quote(self):
        """Trailing double quote is captured."""
        tokens = _tokenize_prose('world"')
        assert tokens == [("", "world", '"')]

    def test_both_leading_and_trailing(self):
        """Leading quote and trailing comma are both captured."""
        tokens = _tokenize_prose('"Hello, world."')
        assert tokens == [('"', "Hello", ","), ("", "world", '."')]

    def test_curly_quotes(self):
        """Curly quotes are captured."""
        tokens = _tokenize_prose("\u201cHello\u201d")
        assert tokens == [("\u201c", "Hello", "\u201d")]

    def test_em_dash_trailing(self):
        """Em dash as trailing punctuation is captured."""
        tokens = _tokenize_prose("wait\u2014")
        assert tokens == [("", "wait", "\u2014")]

    def test_multiple_trailing(self):
        """Multiple trailing punctuation characters are captured together."""
        tokens = _tokenize_prose('said."')
        assert tokens == [("", "said", '."')]

    def test_empty_string(self):
        """Empty string returns empty list."""
        tokens = _tokenize_prose("")
        assert tokens == []

    def test_full_sentence(self):
        """Full sentence with mixed punctuation."""
        tokens = _tokenize_prose('He said "hello" to her.')
        assert tokens == [
            ("", "He", ""),
            ("", "said", ""),
            ('"', "hello", '"'),
            ("", "to", ""),
            ("", "her", "."),
        ]


# ---------------------------------------------------------------------------
# _reconcile_punctuation (prose-based) — quote restoration
# ---------------------------------------------------------------------------


class TestReconcilePunctuationQuotes:
    """_reconcile_punctuation restores quotation marks from prose."""

    def test_restores_opening_and_closing_double_quotes(self):
        """Double quotes around dialogue are restored from prose."""
        result = CaptionResult(
            segments=[CaptionSegment(text="She said hello.", start=0.0, end=2.0)],
            words=[
                CaptionWord(word="She", start=0.0, end=0.3),
                CaptionWord(word="said", start=0.4, end=0.7),
                CaptionWord(word="hello", start=0.8, end=1.5),
            ],
            language="en",
            duration=2.0,
        )
        prose = 'She said "hello."'
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[2].word == '"hello."'

    def test_restores_quotes_on_multi_word_dialogue(self):
        """Quotes around multi-word dialogue span correct words."""
        result = CaptionResult(
            segments=[CaptionSegment(text="He said I need to leave now.", start=0.0, end=3.0)],
            words=[
                CaptionWord(word="He", start=0.0, end=0.2),
                CaptionWord(word="said", start=0.3, end=0.5),
                CaptionWord(word="I", start=0.6, end=0.7),
                CaptionWord(word="need", start=0.8, end=1.0),
                CaptionWord(word="to", start=1.1, end=1.2),
                CaptionWord(word="leave", start=1.3, end=1.6),
                CaptionWord(word="now", start=1.7, end=2.0),
            ],
            language="en",
            duration=3.0,
        )
        prose = 'He said "I need to leave now."'
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[2].word == '"I'
        assert reconciled.words[6].word == 'now."'

    def test_restores_curly_quotes(self):
        """Curly quotes are restored from prose."""
        result = CaptionResult(
            segments=[CaptionSegment(text="She whispered hello.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="She", start=0.0, end=0.3),
                CaptionWord(word="whispered", start=0.4, end=0.8),
                CaptionWord(word="hello", start=0.9, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        prose = "She whispered \u201chello.\u201d"
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[2].word == "\u201chello.\u201d"

    def test_inline_dialogue_with_comma(self):
        """Inline dialogue: 'said, "hello,"' gets comma and quotes."""
        result = CaptionResult(
            segments=[CaptionSegment(text="She said hello and left.", start=0.0, end=3.0)],
            words=[
                CaptionWord(word="She", start=0.0, end=0.3),
                CaptionWord(word="said", start=0.4, end=0.6),
                CaptionWord(word="hello", start=0.7, end=1.0),
                CaptionWord(word="and", start=1.1, end=1.3),
                CaptionWord(word="left", start=1.4, end=1.8),
            ],
            language="en",
            duration=3.0,
        )
        prose = 'She said, "hello," and left.'
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[1].word == "said,"
        assert reconciled.words[2].word == '"hello,"'
        assert reconciled.words[4].word == "left."

    def test_no_prose_returns_unchanged(self):
        """Empty prose string returns result unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello.", start=0.0, end=1.0)],
            words=[CaptionWord(word="Hello", start=0.0, end=1.0)],
            language="en",
            duration=1.0,
        )
        reconciled = _reconcile_punctuation(result, "")
        assert reconciled.words[0].word == "Hello"

    def test_standalone_dialogue_line(self):
        """Full dialogue line starting with quote."""
        result = CaptionResult(
            segments=[CaptionSegment(text="I need to leave she said.", start=0.0, end=3.0)],
            words=[
                CaptionWord(word="I", start=0.0, end=0.2),
                CaptionWord(word="need", start=0.3, end=0.5),
                CaptionWord(word="to", start=0.6, end=0.7),
                CaptionWord(word="leave", start=0.8, end=1.2),
                CaptionWord(word="she", start=1.3, end=1.5),
                CaptionWord(word="said", start=1.6, end=2.0),
            ],
            language="en",
            duration=3.0,
        )
        prose = '"I need to leave," she said.'
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[0].word == '"I'
        assert reconciled.words[3].word == 'leave,"'
        assert reconciled.words[5].word == "said."


# ---------------------------------------------------------------------------
# _reconcile_punctuation — alignment edge cases
# ---------------------------------------------------------------------------


class TestReconcilePunctuationAlignment:
    """_reconcile_punctuation handles word mismatches from narration prep."""

    def test_skipped_prose_word_resyncs(self):
        """Prose has extra word that Whisper didn't hear — alignment resyncs."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The cat sat.", start=0.0, end=2.0)],
            words=[
                CaptionWord(word="The", start=0.0, end=0.3),
                CaptionWord(word="cat", start=0.4, end=0.8),
                CaptionWord(word="sat", start=0.9, end=2.0),
            ],
            language="en",
            duration=2.0,
        )
        # Prose has an extra adjective that narration prep removed
        prose = "The big cat sat."
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[2].word == "sat."

    def test_case_insensitive_matching(self):
        """Matching is case-insensitive."""
        result = CaptionResult(
            segments=[CaptionSegment(text="the storm.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="the", start=0.0, end=0.3),
                CaptionWord(word="storm", start=0.4, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        prose = "The storm."
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[1].word == "storm."

    def test_preserves_word_timing(self):
        """Punctuation restoration does not alter word timestamps."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello world.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="Hello", start=0.0, end=0.5),
                CaptionWord(word="world", start=0.6, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        reconciled = _reconcile_punctuation(result, "Hello, world.")
        assert reconciled.words[0].start == 0.0
        assert reconciled.words[0].end == 0.5
        assert reconciled.words[1].start == 0.6
        assert reconciled.words[1].end == 1.5

    def test_multiple_quoted_sections(self):
        """Multiple dialogue sections in one scene are all restored."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hi he said. Bye she replied.", start=0.0, end=4.0)],
            words=[
                CaptionWord(word="Hi", start=0.0, end=0.3),
                CaptionWord(word="he", start=0.4, end=0.5),
                CaptionWord(word="said", start=0.6, end=0.9),
                CaptionWord(word="Bye", start=1.0, end=1.3),
                CaptionWord(word="she", start=1.4, end=1.6),
                CaptionWord(word="replied", start=1.7, end=2.5),
            ],
            language="en",
            duration=4.0,
        )
        prose = '"Hi," he said. "Bye," she replied.'
        reconciled = _reconcile_punctuation(result, prose)
        assert reconciled.words[0].word == '"Hi,"'
        assert reconciled.words[2].word == "said."
        assert reconciled.words[3].word == '"Bye,"'
        assert reconciled.words[5].word == "replied."

    def test_empty_words_with_prose(self):
        """Empty word list returns unchanged even with prose."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello.", start=0.0, end=1.0)],
            words=[],
            language="en",
            duration=1.0,
        )
        reconciled = _reconcile_punctuation(result, "Hello.")
        assert reconciled.words == []
