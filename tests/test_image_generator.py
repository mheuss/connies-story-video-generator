"""Tests for story_video.pipeline.image_generator — image generation.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the image generator module.
"""

import base64
from unittest.mock import MagicMock

import openai
import pytest

from story_video.models import (
    AppConfig,
    AssetType,
    ImageConfig,
    InputMode,
    SceneImagePrompt,
    SceneStatus,
)
from story_video.pipeline.image_generator import (
    ImageProvider,
    OpenAIImageProvider,
    generate_image,
)
from story_video.state import ProjectState
from tests.error_factories import (
    make_openai_connection_error,
    make_openai_rate_limit_error,
    make_openai_server_error,
)

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
    state.metadata.scenes[0].image_prompts = [
        SceneImagePrompt(key=None, prompt="A dark forest at night", position=0)
    ]
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


class TestDallePassesParams:
    """OpenAIImageProvider.generate() passes correct parameters for DALL-E models."""

    def test_params_shape(self, mock_openai):
        """DALL-E parameters are forwarded correctly to the SDK."""
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

        kwargs = mock_openai.images.generate.call_args.kwargs
        assert kwargs["model"] == "dall-e-3"
        assert kwargs["prompt"] == "A castle on a hill"
        assert kwargs["size"] == "1536x1024"
        assert kwargs["quality"] == "hd"
        assert kwargs["style"] == "natural"
        assert kwargs["response_format"] == "b64_json"
        assert "output_format" not in kwargs
        assert kwargs["n"] == 1


class TestGptImagePassesParams:
    """OpenAIImageProvider.generate() passes correct parameters for GPT Image models."""

    def test_params_shape(self, mock_openai):
        """GPT Image parameters are forwarded correctly to the SDK."""
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

        kwargs = mock_openai.images.generate.call_args.kwargs
        assert kwargs["model"] == "gpt-image-1.5"
        assert kwargs["prompt"] == "A castle on a hill"
        assert kwargs["size"] == "1536x1024"
        assert kwargs["quality"] == "medium"
        assert kwargs["output_format"] == "png"


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

    @pytest.mark.parametrize(
        "error_factory",
        [make_openai_connection_error, make_openai_rate_limit_error, make_openai_server_error],
        ids=["connection", "rate_limit", "server"],
    )
    def test_generate_retries_on_transient_error(self, mock_openai, error_factory):
        """generate() retries on transient error then succeeds."""
        image_data = MagicMock()
        image_data.b64_json = FAKE_B64
        success_response = MagicMock()
        success_response.data = [image_data]

        mock_openai.images.generate.side_effect = [error_factory(), success_response]

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

    @pytest.mark.parametrize(
        "error_name,status,message",
        [
            ("BadRequestError", 400, "bad request"),
            ("AuthenticationError", 401, "invalid key"),
            ("PermissionDeniedError", 403, "permission denied"),
        ],
        ids=["bad_request", "auth", "permission"],
    )
    def test_generate_no_retry_on_permanent_error(self, mock_openai, error_name, status, message):
        """generate() does not retry on permanent error."""
        error_cls = getattr(openai, error_name)
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.json.return_value = {"error": {"message": message}}

        mock_openai.images.generate.side_effect = error_cls(
            message=message,
            response=mock_response,
            body={"error": {"message": message}},
        )

        provider = OpenAIImageProvider()

        with pytest.raises(error_cls):
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
    """generate_image() writes image file, updates state, passes correct params."""

    def test_happy_path(self, project_state, fake_provider):
        """Image file created, state updated, style prefix prepended, config forwarded."""
        scene = project_state.metadata.scenes[0]
        generate_image(scene, project_state, fake_provider)

        # File written with correct bytes
        image_path = project_state.project_dir / "images" / "scene_001_000.png"
        assert image_path.exists()
        assert image_path.read_bytes() == FAKE_PNG

        # Status updated
        assert scene.asset_status.image == SceneStatus.COMPLETED

        # Style prefix prepended to prompt
        call_args = fake_provider.generate.call_args
        assert call_args[0][0] == "Cinematic: A dark forest at night"

        # Config params forwarded
        kwargs = call_args.kwargs
        assert kwargs["size"] == "1536x1024"
        assert kwargs["quality"] == "medium"
        assert kwargs["style"] is None
        assert kwargs["model"] == "gpt-image-1.5"

        # State persisted to disk
        reloaded = ProjectState.load(project_state.project_dir)
        assert reloaded.metadata.scenes[0].asset_status.image == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_image — multi-image scene creates indexed files
# ---------------------------------------------------------------------------


class TestGenerateImageMultiImage:
    """generate_image() creates indexed files for scenes with multiple prompts."""

    def test_creates_all_indexed_files(self, tmp_path, fake_provider):
        """Three prompts produce scene_001_000.png, scene_001_001.png, scene_001_002.png."""
        config = AppConfig(
            images=ImageConfig(style_prefix="Art:", size="1536x1024", quality="medium")
        )
        state = ProjectState.create("multi-img", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Multi Image Scene", "Story text.")
        state.metadata.scenes[0].image_prompts = [
            SceneImagePrompt(key="a", prompt="A lighthouse", position=0),
            SceneImagePrompt(key="b", prompt="A harbor", position=20),
            SceneImagePrompt(key="c", prompt="A sunset", position=40),
        ]
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_image(scene, state, fake_provider)

        images_dir = state.project_dir / "images"
        assert (images_dir / "scene_001_000.png").exists()
        assert (images_dir / "scene_001_001.png").exists()
        assert (images_dir / "scene_001_002.png").exists()

    def test_calls_provider_once_per_prompt(self, tmp_path, fake_provider):
        """Provider.generate() is called once for each image prompt."""
        config = AppConfig(
            images=ImageConfig(style_prefix="Art:", size="1536x1024", quality="medium")
        )
        state = ProjectState.create("multi-img-2", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Multi Image Scene", "Story text.")
        state.metadata.scenes[0].image_prompts = [
            SceneImagePrompt(key="a", prompt="A lighthouse", position=0),
            SceneImagePrompt(key="b", prompt="A harbor", position=20),
        ]
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_image(scene, state, fake_provider)

        assert fake_provider.generate.call_count == 2


# ---------------------------------------------------------------------------
# generate_image — ValueError when no image_prompts
# ---------------------------------------------------------------------------


class TestGenerateImageNoImagePromptRaises:
    """generate_image() raises ValueError when scene has no image prompts."""

    def test_generate_image_no_image_prompts_raises(self, project_state, fake_provider):
        """ValueError raised when image_prompts is empty."""
        scene = project_state.metadata.scenes[0]
        scene.image_prompts = []

        with pytest.raises(ValueError, match="Scene 1 has no image prompts"):
            generate_image(scene, project_state, fake_provider)


# ---------------------------------------------------------------------------
# generate_image — multi-digit scene number zero-padding
# ---------------------------------------------------------------------------


class TestGenerateImageMultiDigitSceneNumber:
    """generate_image() zero-pads scene numbers in filenames."""

    def test_generate_image_zero_pads_scene_number(self, tmp_path, fake_provider):
        """Scene 12 produces scene_012_000.png."""
        config = AppConfig(
            images=ImageConfig(
                style_prefix="Art:",
                size="1536x1024",
                quality="medium",
            )
        )
        state = ProjectState.create("multi-digit-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(12, "Scene Twelve", "The twelfth scene of the story.")
        state.metadata.scenes[0].image_prompts = [
            SceneImagePrompt(key=None, prompt="A mountain landscape", position=0)
        ]
        state.update_scene_asset(12, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(12, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        scene = state.metadata.scenes[0]
        generate_image(scene, state, fake_provider)

        image_path = state.project_dir / "images" / "scene_012_000.png"
        assert image_path.exists()
