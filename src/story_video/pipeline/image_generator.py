"""Image generation with provider abstraction.

Generates scene illustrations from text prompts using a pluggable image provider.
Ships with an OpenAI implementation supporting GPT Image and DALL-E models.
"""

import base64
import logging
from typing import Protocol

import openai

from story_video.models import AssetType, Scene, SceneStatus
from story_video.state import ProjectState
from story_video.utils.retry import with_retry

_OPENAI_TRANSIENT = (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)

__all__ = ["ImageProvider", "OpenAIImageProvider", "generate_image"]

logger = logging.getLogger(__name__)


class ImageProvider(Protocol):
    """Interface for image generation providers."""

    def generate(
        self, prompt: str, *, model: str, size: str, quality: str, style: str | None = None
    ) -> bytes:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate.
            model: Model identifier (e.g. "gpt-image-1.5", "dall-e-3").
            size: Image dimensions (e.g. "1792x1024").
            quality: Quality tier (e.g. "medium", "high", "standard").
            style: Style parameter for DALL-E models (None for GPT Image models).

        Returns:
            Raw image bytes (PNG).
        """
        ...


class OpenAIImageProvider:
    """OpenAI image provider supporting GPT Image and DALL-E models.

    Reads OPENAI_API_KEY from the environment.
    GPT Image models always return base64 and use ``output_format``.
    DALL-E models use ``response_format`` to request base64.
    """

    def __init__(self) -> None:
        self._client = openai.OpenAI()

    @with_retry(max_retries=3, base_delay=2.0, retry_on=_OPENAI_TRANSIENT)
    def generate(
        self, prompt: str, *, model: str, size: str, quality: str, style: str | None = None
    ) -> bytes:
        """Generate an image via the specified model.

        Args:
            prompt: Text description of the image.
            model: Model identifier (e.g. "gpt-image-1.5", "dall-e-3").
            size: Image dimensions.
            quality: Quality tier.
            style: DALL-E style parameter (ignored for GPT Image models).

        Returns:
            Raw PNG image bytes decoded from the base64 API response.
        """
        is_gpt_image = model.startswith("gpt-image")
        kwargs: dict = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": 1,
        }
        # GPT Image models always return base64 and use output_format.
        # DALL-E models need response_format to request base64.
        if is_gpt_image:
            kwargs["output_format"] = "png"
        else:
            kwargs["response_format"] = "b64_json"
        if style is not None:
            kwargs["style"] = style

        response = self._client.images.generate(**kwargs)
        if not response.data or not response.data[0].b64_json:
            msg = f"Image API returned empty data for prompt: {prompt[:80]}..."
            raise ValueError(msg)
        return base64.b64decode(response.data[0].b64_json)


def generate_image(scene: Scene, state: ProjectState, provider: ImageProvider) -> None:
    """Generate an illustration for a single scene.

    Reads the scene's image prompt, prepends the configured style prefix,
    calls the image provider, writes the PNG file, and updates project state.

    Args:
        scene: The scene to generate an image for.
        state: Project state for config access and persistence.
        provider: Image provider implementation.

    Raises:
        ValueError: If the scene has no image prompt.
    """
    if scene.image_prompt is None:
        msg = f"Scene {scene.scene_number} has no image prompt"
        raise ValueError(msg)

    img_config = state.metadata.config.images
    full_prompt = f"{img_config.style_prefix} {scene.image_prompt}".strip()

    image_bytes = provider.generate(
        full_prompt,
        model=img_config.model,
        size=img_config.size,
        quality=img_config.quality,
        style=img_config.style,
    )

    if not image_bytes:
        msg = f"Scene {scene.scene_number}: image provider returned empty bytes"
        raise ValueError(msg)

    images_dir = state.project_dir / "images"
    images_dir.mkdir(exist_ok=True)
    filename = f"scene_{scene.scene_number:03d}.png"
    image_path = images_dir / filename
    image_path.write_bytes(image_bytes)

    state.update_scene_asset(scene.scene_number, AssetType.IMAGE, SceneStatus.IN_PROGRESS)
    state.update_scene_asset(scene.scene_number, AssetType.IMAGE, SceneStatus.COMPLETED)
    state.save()
