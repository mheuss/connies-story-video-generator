"""Tests for story_video.pipeline.image_generator — image generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the image generator module.
"""

import base64
from unittest.mock import MagicMock

import pytest

from story_video.models import AppConfig, AssetType, ImageConfig, InputMode, SceneStatus
from story_video.pipeline.image_generator import (
    ImageProvider,
    OpenAIImageProvider,
    generate_image,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

FAKE_PNG = b"\x89PNG\r\n\x1a\n fake image data"
FAKE_B64 = base64.b64encode(FAKE_PNG).decode()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_openai(monkeypatch):
    """Patch openai.OpenAI to return a mock client."""
    mock_client = MagicMock()
    mock_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("story_video.pipeline.image_generator.openai.OpenAI", mock_class)
    return mock_client


@pytest.fixture()
def fake_provider():
    """Create a mock image provider that returns dummy PNG bytes."""
    provider = MagicMock(spec=ImageProvider)
    provider.generate.return_value = FAKE_PNG
    return provider


@pytest.fixture()
def project_state(tmp_path):
    """Create a project state with one scene ready for image generation."""
    config = AppConfig(
        images=ImageConfig(
            style_prefix="Cinematic:",
            size="1536x1024",
            quality="medium",
        )
    )
    state = ProjectState.create("test-project", InputMode.ADAPT, config, tmp_path)
    state.add_scene(scene_number=1, title="Test Scene", prose="Story text.")
    state.metadata.scenes[0].image_prompt = "A dark forest at night"
    state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
    state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)
    state.save()
    return state


# ---------------------------------------------------------------------------
# OpenAIImageProvider — returns decoded base64 bytes
# ---------------------------------------------------------------------------


class TestOpenAIImageProviderReturnsDecodedBytes:
    """OpenAIImageProvider.generate() returns decoded base64 image bytes."""

    def test_generate_returns_decoded_bytes(self, mock_openai):
        """generate() decodes the b64_json response and returns raw bytes."""
        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        response = MagicMock()
        response.data = [image_data]
        mock_openai.images.generate.return_value = response

        provider = OpenAIImageProvider()
        result = provider.generate(
            prompt="A forest",
            model="gpt-image-1.5",
            size="1536x1024",
            quality="medium",
        )

        assert result == FAKE_PNG


# ---------------------------------------------------------------------------
# OpenAIImageProvider — passes correct params
# ---------------------------------------------------------------------------


class TestOpenAIImageProviderPassesParams:
    """OpenAIImageProvider.generate() passes correct parameters to the SDK."""

    def test_dalle_uses_response_format(self, mock_openai):
        """DALL-E models use response_format=b64_json."""
        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        response = MagicMock()
        response.data = [image_data]
        mock_openai.images.generate.return_value = response

        provider = OpenAIImageProvider()
        provider.generate(
            prompt="A castle on a hill",
            model="dall-e-3",
            size="1536x1024",
            quality="hd",
            style="natural",
        )

        call_kwargs = mock_openai.images.generate.call_args.kwargs
        assert call_kwargs["model"] == "dall-e-3"
        assert call_kwargs["prompt"] == "A castle on a hill"
        assert call_kwargs["size"] == "1536x1024"
        assert call_kwargs["quality"] == "hd"
        assert call_kwargs["style"] == "natural"
        assert call_kwargs["response_format"] == "b64_json"
        assert "output_format" not in call_kwargs
        assert call_kwargs["n"] == 1

    def test_gpt_image_uses_output_format(self, mock_openai):
        """GPT Image models use output_format=png (no response_format, no style)."""
        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        response = MagicMock()
        response.data = [image_data]
        mock_openai.images.generate.return_value = response

        provider = OpenAIImageProvider()
        provider.generate(
            prompt="A castle on a hill",
            model="gpt-image-1.5",
            size="1536x1024",
            quality="medium",
        )

        call_kwargs = mock_openai.images.generate.call_args.kwargs
        assert call_kwargs["output_format"] == "png"
        assert "response_format" not in call_kwargs
        assert "style" not in call_kwargs
        assert call_kwargs["model"] == "gpt-image-1.5"
        assert call_kwargs["quality"] == "medium"


# ---------------------------------------------------------------------------
# OpenAIImageProvider — reads API key from env
# ---------------------------------------------------------------------------


class TestOpenAIImageProviderReadsApiKeyFromEnv:
    """OpenAIImageProvider reads OPENAI_API_KEY from the environment."""

    def test_client_reads_api_key_from_env(self, monkeypatch):
        """OpenAI() is called without explicit API key (reads from env)."""
        mock_client = MagicMock()
        mock_class = MagicMock(return_value=mock_client)
        monkeypatch.setattr("story_video.pipeline.image_generator.openai.OpenAI", mock_class)

        _ = OpenAIImageProvider()

        mock_class.assert_called_once_with()


# ---------------------------------------------------------------------------
# OpenAIImageProvider — retry on transient errors
# ---------------------------------------------------------------------------


class TestOpenAIImageProviderRetryOnTransientErrors:
    """OpenAIImageProvider.generate() retries on transient API errors."""

    def test_generate_retries_on_rate_limit(self, mock_openai):
        """generate() retries on RateLimitError then succeeds."""
        from openai import RateLimitError

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.json.return_value = {"error": {"message": "rate limited"}}

        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        success_response = MagicMock()
        success_response.data = [image_data]

        mock_openai.images.generate.side_effect = [
            RateLimitError(
                message="rate limited",
                response=response_429,
                body={"error": {"message": "rate limited"}},
            ),
            success_response,
        ]

        provider = OpenAIImageProvider()
        result = provider.generate(
            prompt="test",
            model="gpt-image-1.5",
            size="1536x1024",
            quality="medium",
        )

        assert result == FAKE_PNG
        assert mock_openai.images.generate.call_count == 2

    def test_generate_retries_on_connection_error(self, mock_openai):
        """generate() retries on APIConnectionError then succeeds."""
        from openai import APIConnectionError

        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        success_response = MagicMock()
        success_response.data = [image_data]

        mock_openai.images.generate.side_effect = [
            APIConnectionError(request=MagicMock()),
            success_response,
        ]

        provider = OpenAIImageProvider()
        result = provider.generate(
            prompt="test",
            model="gpt-image-1.5",
            size="1536x1024",
            quality="medium",
        )

        assert result == FAKE_PNG
        assert mock_openai.images.generate.call_count == 2

    def test_generate_retries_on_server_error(self, mock_openai):
        """generate() retries on InternalServerError then succeeds."""
        from openai import InternalServerError

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.json.return_value = {"error": {"message": "server error"}}

        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        success_response = MagicMock()
        success_response.data = [image_data]

        mock_openai.images.generate.side_effect = [
            InternalServerError(
                message="server error",
                response=response_500,
                body={"error": {"message": "server error"}},
            ),
            success_response,
        ]

        provider = OpenAIImageProvider()
        result = provider.generate(
            prompt="test",
            model="gpt-image-1.5",
            size="1536x1024",
            quality="medium",
        )

        assert result == FAKE_PNG
        assert mock_openai.images.generate.call_count == 2


# ---------------------------------------------------------------------------
# OpenAIImageProvider — no retry on permanent errors
# ---------------------------------------------------------------------------


class TestOpenAIImageProviderNoRetryOnPermanentErrors:
    """OpenAIImageProvider.generate() does NOT retry on permanent API errors."""

    def test_generate_no_retry_on_bad_request(self, mock_openai):
        """generate() does not retry on BadRequestError."""
        from openai import BadRequestError

        response_400 = MagicMock()
        response_400.status_code = 400
        response_400.json.return_value = {"error": {"message": "bad request"}}

        mock_openai.images.generate.side_effect = BadRequestError(
            message="bad request",
            response=response_400,
            body={"error": {"message": "bad request"}},
        )

        provider = OpenAIImageProvider()

        with pytest.raises(BadRequestError):
            provider.generate(
                prompt="test",
                model="gpt-image-1.5",
                size="1536x1024",
                quality="medium",
            )

        assert mock_openai.images.generate.call_count == 1

    def test_generate_no_retry_on_auth_error(self, mock_openai):
        """generate() does not retry on AuthenticationError."""
        from openai import AuthenticationError

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.json.return_value = {"error": {"message": "invalid key"}}

        mock_openai.images.generate.side_effect = AuthenticationError(
            message="invalid key",
            response=response_401,
            body={"error": {"message": "invalid key"}},
        )

        provider = OpenAIImageProvider()

        with pytest.raises(AuthenticationError):
            provider.generate(
                prompt="test",
                model="gpt-image-1.5",
                size="1536x1024",
                quality="medium",
            )

        assert mock_openai.images.generate.call_count == 1

    def test_generate_no_retry_on_permission_error(self, mock_openai):
        """generate() does not retry on PermissionDeniedError."""
        from openai import PermissionDeniedError

        response_403 = MagicMock()
        response_403.status_code = 403
        response_403.json.return_value = {"error": {"message": "permission denied"}}

        mock_openai.images.generate.side_effect = PermissionDeniedError(
            message="permission denied",
            response=response_403,
            body={"error": {"message": "permission denied"}},
        )

        provider = OpenAIImageProvider()

        with pytest.raises(PermissionDeniedError):
            provider.generate(
                prompt="test",
                model="gpt-image-1.5",
                size="1536x1024",
                quality="medium",
            )

        assert mock_openai.images.generate.call_count == 1


# ---------------------------------------------------------------------------
# generate_image — happy path
# ---------------------------------------------------------------------------


class TestGenerateImageHappyPath:
    """generate_image() writes image file and updates state."""

    def test_generate_image_writes_file_and_updates_state(self, project_state, fake_provider):
        """Image file written, status updated to COMPLETED, state saved."""
        scene = project_state.metadata.scenes[0]
        generate_image(scene, project_state, fake_provider)

        # File written
        image_path = project_state.project_dir / "images" / "scene_001.png"
        assert image_path.exists()
        assert image_path.read_bytes() == FAKE_PNG

        # Status updated
        assert scene.asset_status.image == SceneStatus.COMPLETED

        # State persisted — reload from disk
        reloaded = ProjectState.load(project_state.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.image == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_image — style prefix prepended to prompt
# ---------------------------------------------------------------------------


class TestGenerateImageStylePrefixPrepended:
    """generate_image() prepends the style prefix to the image prompt."""

    def test_generate_image_prepends_style_prefix(self, project_state, fake_provider):
        """The full prompt is style_prefix + space + image_prompt."""
        scene = project_state.metadata.scenes[0]
        generate_image(scene, project_state, fake_provider)

        call_args = fake_provider.generate.call_args
        assert call_args[0][0] == "Cinematic: A dark forest at night"


# ---------------------------------------------------------------------------
# generate_image — config params passed to provider
# ---------------------------------------------------------------------------


class TestGenerateImageConfigParamsPassedToProvider:
    """generate_image() passes image config values to the provider."""

    def test_generate_image_passes_config_to_provider(self, project_state, fake_provider):
        """size, quality, style from config are passed to generate."""
        scene = project_state.metadata.scenes[0]
        generate_image(scene, project_state, fake_provider)

        call_kwargs = fake_provider.generate.call_args.kwargs
        assert call_kwargs["size"] == "1536x1024"
        assert call_kwargs["quality"] == "medium"
        assert call_kwargs["style"] is None


# ---------------------------------------------------------------------------
# generate_image — ValueError when no image_prompt
# ---------------------------------------------------------------------------


class TestGenerateImageNoImagePromptRaises:
    """generate_image() raises ValueError when scene has no image prompt."""

    def test_generate_image_no_image_prompt_raises(self, project_state, fake_provider):
        """ValueError raised when image_prompt is None."""
        scene = project_state.metadata.scenes[0]
        scene.image_prompt = None

        with pytest.raises(ValueError, match="Scene 1 has no image prompt"):
            generate_image(scene, project_state, fake_provider)


# ---------------------------------------------------------------------------
# generate_image — always writes PNG
# ---------------------------------------------------------------------------


class TestGenerateImageAlwaysWritesPng:
    """generate_image() always writes PNG files regardless of config."""

    def test_generate_image_always_writes_png(self, tmp_path, fake_provider):
        """File extension is always .png."""
        config = AppConfig(
            images=ImageConfig(
                style_prefix="Art:",
                size="1536x1024",
                quality="high",
            )
        )
        state = ProjectState.create("png-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Scene One", "Some text.")
        state.metadata.scenes[0].image_prompt = "A sunrise"
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_image(scene, state, fake_provider)

        image_path = state.project_dir / "images" / "scene_001.png"
        assert image_path.exists()


# ---------------------------------------------------------------------------
# generate_image — multi-digit scene number zero-padding
# ---------------------------------------------------------------------------


class TestGenerateImageMultiDigitSceneNumber:
    """generate_image() zero-pads scene numbers in filenames."""

    def test_generate_image_zero_pads_scene_number(self, tmp_path, fake_provider):
        """Scene 12 produces scene_012.png."""
        config = AppConfig(
            images=ImageConfig(
                style_prefix="Art:",
                size="1536x1024",
                quality="medium",
            )
        )
        state = ProjectState.create("multi-digit-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(12, "Scene Twelve", "The twelfth scene of the story.")
        state.metadata.scenes[0].image_prompt = "A mountain landscape"
        state.update_scene_asset(12, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(12, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_image(scene, state, fake_provider)

        image_path = state.project_dir / "images" / "scene_012.png"
        assert image_path.exists()


# ---------------------------------------------------------------------------
# generate_image — state saved
# ---------------------------------------------------------------------------


class TestGenerateImageStateSaved:
    """generate_image() persists state via state.save()."""

    def test_generate_image_state_saved(self, project_state, fake_provider):
        """Verify state.save() is called by reloading from disk."""
        scene = project_state.metadata.scenes[0]
        generate_image(scene, project_state, fake_provider)

        reloaded = ProjectState.load(project_state.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.image == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_image — passes model from config
# ---------------------------------------------------------------------------


class TestGenerateImagePassesModelFromConfig:
    """generate_image() passes the model from ImageConfig to the provider."""

    def test_passes_model_from_config(self, project_state, fake_provider):
        """model kwarg passed to provider.generate matches ImageConfig.model."""
        scene = project_state.metadata.scenes[0]
        generate_image(scene, project_state, fake_provider)

        call_kwargs = fake_provider.generate.call_args.kwargs
        assert call_kwargs["model"] == "gpt-image-1.5"  # default from ImageConfig
