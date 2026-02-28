"""Image prompt generation via Claude structured output.

Generates image prompts for scenes that don't already have them. Scenes with
image_prompts set (from YAML image tags) are skipped. Remaining scenes are
sent to Claude in a single call. Each prompt describes the key visual moment
of its scene for illustration.
"""

import json
import logging

from story_video.models import AssetType, SceneImagePrompt, SceneStatus
from story_video.pipeline.claude_client import ClaudeClient
from story_video.state import ProjectState

__all__ = ["generate_image_prompts"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMAGE_PROMPT_SYSTEM = (
    "You are a visual director creating image prompts for story scenes.\n\n"
    "For each scene, write a single detailed image prompt that captures the key "
    "visual moment. The prompt should be:\n"
    "- Visually specific: describe setting, lighting, composition, mood\n"
    "- Character-consistent: use the character reference (when provided) to"
    " describe characters accurately. Include visual details in every prompt"
    " — image models have no memory between images\n"
    "- Cinematic: frame it like a movie still or painting\n"
    "- 1-3 sentences long\n\n"
    "Do NOT include text overlays, watermarks, or UI elements in prompts.\n\n"
    "IMPORTANT: Generate exactly one prompt per scene provided. Do not create"
    " prompts for scene numbers that are not in the input."
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
                    "image_prompt": {"type": "string", "description": "Image generation prompt"},
                },
                "required": ["scene_number", "image_prompt"],
            },
            "minItems": 1,
        }
    },
    "required": ["prompts"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_characters(state: ProjectState) -> list[dict]:
    """Load character descriptions from analysis.json if available.

    Returns an empty list if analysis.json doesn't exist, contains
    malformed JSON, or has no characters key. This provides backward
    compatibility with projects created before character extraction
    was added.
    """
    analysis_path = state.project_dir / "analysis.json"
    if not analysis_path.exists():
        return []
    try:
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Malformed analysis.json; skipping character reference")
        return []
    return analysis.get("characters", [])


def _format_character_reference(characters: list[dict]) -> str:
    """Format character list into a text block for the image prompt context.

    Args:
        characters: List of character dicts, each with 'name' and
            'visual_description' keys.

    Returns:
        Multi-line string with a header and one ``Name: Description`` line
        per character, ending with a blank line.
    """
    lines = ["=== Character Reference ==="]
    for char in characters:
        name = char.get("name", "Unknown")
        desc = char.get("visual_description", "No description")
        lines.append(f"{name}: {desc}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_image_prompts(state: ProjectState, client: ClaudeClient) -> None:
    """Generate image prompts for scenes.

    Scenes with image_prompts already set (from YAML image tags) are skipped.
    Remaining scenes are sent to Claude in a single structured output call.

    Args:
        state: Project state with populated scenes.
        client: Claude API client.

    Raises:
        ValueError: If no scenes exist, or if Claude omits prompts for
            requested scenes.
    """
    scenes = state.metadata.scenes
    if not scenes:
        msg = "No scenes in project"
        raise ValueError(msg)

    # Separate tagged (already have prompts) from untagged (need Claude)
    tagged_scenes = [s for s in scenes if s.image_prompts]
    untagged_scenes = [s for s in scenes if not s.image_prompts]

    # Mark tagged scenes as completed
    for scene in tagged_scenes:
        scene_num = scene.scene_number
        state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

    if untagged_scenes:
        # Load character descriptions from analysis (if available)
        characters = _load_characters(state)

        # Build user message with optional character reference and numbered scenes.
        # NOTE: All scenes are sent in a single Claude call. For very large stories
        # (25+ scenes), this could approach context limits. Acceptable for typical
        # use (5-15 scenes). If this becomes an issue, batch scenes into groups.
        parts = []
        if characters:
            parts.append(_format_character_reference(characters))
        for scene in untagged_scenes:
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
        scene_map = {s.scene_number: s for s in untagged_scenes}
        for prompt_entry in result["prompts"]:
            scene_num = prompt_entry["scene_number"]
            scene = scene_map.get(scene_num)
            if scene is None:
                logger.warning(
                    "Prompt references scene %d which does not exist; skipping",
                    scene_num,
                )
                continue
            scene.image_prompts = [
                SceneImagePrompt(key=None, prompt=prompt_entry["image_prompt"], position=0)
            ]
            state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
            state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        # Double duty: validates Claude returned prompts for every scene AND
        # marks missing scenes as FAILED so they're visible in status output.
        # Failing early here avoids wasting API calls on image generation
        # for scenes that would fail anyway due to missing prompts.
        scenes_in_response = {p["scene_number"] for p in result["prompts"]}
        missing = sorted(set(scene_map.keys()) - scenes_in_response)
        if missing:
            for scene_num in missing:
                state.update_scene_asset(scene_num, AssetType.IMAGE_PROMPT, SceneStatus.FAILED)
            state.save()
            msg = f"Claude did not return prompts for scenes: {missing}"
            raise ValueError(msg)

    state.save()
