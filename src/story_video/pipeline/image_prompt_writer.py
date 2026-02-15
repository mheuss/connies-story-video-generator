"""Image prompt generation via Claude structured output.

Generates DALL-E image prompts for all scenes in a single Claude call.
Each prompt describes the key visual moment of its scene for illustration.
"""

import logging

from story_video.models import AssetType, SceneStatus
from story_video.pipeline.claude_client import ClaudeClient
from story_video.state import ProjectState

__all__ = ["generate_image_prompts"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMAGE_PROMPT_SYSTEM = (
    "You are a visual director creating DALL-E image prompts for story scenes.\n\n"
    "For each scene, write a single detailed image prompt that captures the key "
    "visual moment. The prompt should be:\n"
    "- Visually specific: describe setting, lighting, composition, mood\n"
    "- Self-contained: include all character descriptions (DALL-E has no memory "
    "between images)\n"
    "- Cinematic: frame it like a movie still or painting\n"
    "- 1-3 sentences long\n\n"
    "Do NOT include text overlays, watermarks, or UI elements in prompts."
)

IMAGE_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "description": "1-based scene number"},
                    "image_prompt": {"type": "string", "description": "DALL-E image prompt"},
                },
                "required": ["scene_number", "image_prompt"],
            },
            "minItems": 1,
        }
    },
    "required": ["prompts"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_image_prompts(state: ProjectState, client: ClaudeClient) -> None:
    """Generate image prompts for all scenes via a single Claude call.

    Sends all scene prose to Claude in a single structured output call.
    Claude returns a DALL-E prompt per scene. Updates scene.image_prompt
    and marks IMAGE_PROMPT asset as COMPLETED for each scene.

    Args:
        state: Project state with populated scenes.
        client: Claude API client.

    Raises:
        ValueError: If no scenes exist.
    """
    scenes = state.metadata.scenes
    if not scenes:
        msg = "No scenes in project"
        raise ValueError(msg)

    # Build user message with numbered scenes
    parts = []
    for scene in scenes:
        parts.append(f"=== Scene {scene.scene_number}: {scene.title} ===")
        parts.append(scene.prose)
        parts.append("")
    scene_text = "\n".join(parts)

    # Call Claude for image prompt generation
    result = client.generate_structured(
        system=IMAGE_PROMPT_SYSTEM,
        user_message=scene_text,
        tool_name="generate_image_prompts",
        tool_schema=IMAGE_PROMPT_SCHEMA,
    )

    # Apply prompts to matching scenes
    scene_map = {s.scene_number: s for s in scenes}
    for prompt_entry in result["prompts"]:
        scene_num = prompt_entry["scene_number"]
        scene = scene_map.get(scene_num)
        if scene is None:
            logger.warning("Prompt references scene %d which does not exist; skipping", scene_num)
            continue
        scene.image_prompt = prompt_entry["image_prompt"]
        state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

    # Persist state
    state.save()
