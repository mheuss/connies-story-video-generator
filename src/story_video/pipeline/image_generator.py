"""Image generation with provider abstraction.

Generates scene illustrations from text prompts using a pluggable image provider.
Ships with an OpenAI DALL-E 3 implementation.
"""

import base64
from typing import Protocol

import openai
from openai import APIConnectionError, InternalServerError, RateLimitError

from story_video.models import AssetType, Scene, SceneStatus
from story_video.state import ProjectState
from story_video.utils.retry import with_retry

__all__ = ["ImageProvider", "OpenAIImageProvider", "generate_image"]

TRANSIENT_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)


class ImageProvider(Protocol):
    """Interface for image generation providers."""

    def generate(self, prompt: str, size: str, quality: str, style: str) -> bytes:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate.
            size: Image dimensions (e.g. "1024x1024").
            quality: Quality tier (e.g. "standard", "hd").
            style: Style parameter (e.g. "vivid", "natural").

        Returns:
            Raw image bytes (PNG).
        """
        ...


class OpenAIImageProvider:
    """OpenAI DALL-E 3 image provider.

    Reads OPENAI_API_KEY from the environment.
    Uses b64_json response format to avoid a second HTTP fetch.
    """

    def __init__(self) -> None:
        self._client = openai.OpenAI()

    @with_retry(max_retries=3, base_delay=2.0, retry_on=TRANSIENT_ERRORS)
    def generate(self, prompt: str, size: str, quality: str, style: str) -> bytes:
        """Generate an image via DALL-E 3.

        Args:
            prompt: Text description of the image.
            size: Image dimensions.
            quality: Quality tier.
            style: DALL-E style parameter.

        Returns:
            Raw PNG image bytes decoded from the base64 API response.
        """
        response = self._client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            style=style,
            response_format="b64_json",
            n=1,
        )
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
    full_prompt = f"{img_config.style_prefix} {scene.image_prompt}"

    image_bytes = provider.generate(
        full_prompt,
        size=img_config.size,
        quality=img_config.quality,
        style=img_config.style,
    )

    images_dir = state.project_dir / "images"
    images_dir.mkdir(exist_ok=True)
    filename = f"scene_{scene.scene_number:02d}.png"
    image_path = images_dir / filename
    image_path.write_bytes(image_bytes)

    state.update_scene_asset(scene.scene_number, AssetType.IMAGE, SceneStatus.COMPLETED)
    state.save()
