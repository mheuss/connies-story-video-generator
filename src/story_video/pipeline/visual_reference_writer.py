"""Visual reference generation via Claude structured output.

Produces visual_reference.json with image-focused character descriptions and a
setting summary. Creative modes distill from story_bible.json; adapt mode
invents from analysis.json + source material.
"""

import json
import logging
from pathlib import Path

from story_video.models import InputMode
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.story_writer import _load_json_artifact
from story_video.state import ProjectState

__all__ = ["ADAPT_SYSTEM", "CREATIVE_SYSTEM", "VISUAL_REF_SCHEMA", "generate_visual_reference"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VISUAL_REF_SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "visual_description": {
                        "type": "string",
                        "description": "Concrete visual details for image generation",
                    },
                },
                "required": ["name", "visual_description"],
            },
            "minItems": 1,
        },
        "setting": {
            "type": "object",
            "properties": {
                "visual_summary": {
                    "type": "string",
                    "description": "Visual setting description for image generation",
                },
            },
            "required": ["visual_summary"],
        },
    },
    "required": ["characters", "setting"],
}

CREATIVE_SYSTEM = (
    "You are a visual director creating a character reference sheet for an "
    "illustrator.\n\n"
    "You have a story bible with character descriptions and a setting. Your job "
    "is to translate narrative descriptions into concrete visual details an "
    "image generator can use.\n\n"
    "For each character:\n"
    "- Physical appearance: age, ethnicity, build, hair, eyes, distinguishing "
    "features\n"
    "- Default clothing and accessories\n"
    "- Posture, body language, how they carry themselves\n"
    "- Any visual details implied but not stated (infer from role, arc, "
    "setting)\n\n"
    "For the setting:\n"
    "- Key visual elements: architecture, landscape, lighting, weather, color "
    "palette\n"
    "- Atmosphere as visual direction (not narrative mood)\n\n"
    'Be specific and concrete. "Tired-looking" → "dark circles under sunken '
    'eyes, hollow cheeks, shoulders slumped forward." Every detail should be '
    "something visible in a still image."
)

ADAPT_SYSTEM = (
    "You are a visual director creating a character reference sheet for an "
    "illustrator.\n\n"
    "You have a story with characters who may or may not be physically "
    "described. Your job is to create concrete, detailed visual descriptions "
    "for every character, inventing plausible visual details where the source "
    "material is silent.\n\n"
    "For each character:\n"
    "- Physical appearance: age, ethnicity, build, hair, eyes, distinguishing "
    "features\n"
    "- Default clothing and accessories appropriate to the setting and time "
    "period\n"
    "- Posture, body language, how they carry themselves\n"
    "- If the source describes them, honor those details exactly\n"
    "- If the source is silent, invent specific, grounded visual details that "
    "fit the character's role and the story's world\n\n"
    "For the setting:\n"
    "- Key visual elements: architecture, landscape, lighting, weather, color "
    "palette\n"
    "- Atmosphere as visual direction\n\n"
    'Be specific and concrete. Never say "no description provided" — always '
    "commit to a visual identity. Every detail should be something visible in "
    "a still image."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_creative_message(project_dir: Path) -> str:
    """Build user message for creative modes from story_bible.json + analysis.json.

    Args:
        project_dir: Path to the project directory.

    Returns:
        User message string with craft notes, character, and setting data.
    """
    bible = _load_json_artifact(project_dir, "story_bible.json")
    analysis = _load_json_artifact(project_dir, "analysis.json")

    parts = []

    # Craft notes for style context
    craft_notes = analysis.get("craft_notes", {})
    if craft_notes:
        parts.append("## Craft Notes\n")
        parts.append(json.dumps(craft_notes, indent=2))
        parts.append("")

    # Characters section
    parts.append("## Characters\n")
    for char in bible.get("characters", []):
        name = char.get("name", "Unknown")
        role = char.get("role", "unknown")
        desc = char.get("description", "No description")
        arc = char.get("arc", "")
        parts.append(f"**{name}** ({role})")
        parts.append(f"Description: {desc}")
        if arc:
            parts.append(f"Arc: {arc}")
        parts.append("")

    # Setting section
    setting = bible.get("setting", {})
    if isinstance(setting, dict):
        parts.append("## Setting\n")
        for key in ("place", "time_period", "atmosphere"):
            value = setting.get(key)
            if value:
                parts.append(f"**{key.replace('_', ' ').title()}:** {value}")
        parts.append("")

    return "\n".join(parts)


def _build_adapt_message(project_dir: Path) -> str:
    """Build user message for adapt mode from analysis.json + source material.

    Args:
        project_dir: Path to the project directory.

    Returns:
        User message string with character data and source text.
    """
    analysis = _load_json_artifact(project_dir, "analysis.json")

    parts = []

    # Characters from analysis
    characters = analysis.get("characters", [])
    if characters:
        parts.append("## Characters from Analysis\n")
        for char in characters:
            name = char.get("name", "Unknown")
            desc = char.get("visual_description", "No description")
            parts.append(f"**{name}:** {desc}")
        parts.append("")

    # Source material for context
    source_path = project_dir / "source_story.txt"
    if source_path.exists():
        source_text = source_path.read_text(encoding="utf-8")
        parts.append("## Source Material\n")
        parts.append(source_text)
        parts.append("")

    # Craft notes for setting context
    craft_notes = analysis.get("craft_notes", {})
    if craft_notes:
        parts.append("## Craft Notes\n")
        parts.append(json.dumps(craft_notes, indent=2))
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_visual_reference(state: ProjectState, client: ClaudeClient) -> None:
    """Generate visual reference with character descriptions and setting summary.

    For creative modes (original/inspired_by): distills story_bible.json into
    image-focused visual descriptions.
    For adapt mode: invents concrete visual details from analysis.json and
    source material.

    Writes visual_reference.json to the project directory.

    Args:
        state: Project state.
        client: Claude API client.

    Raises:
        FileNotFoundError: If required input files are missing.
    """
    is_adapt = state.metadata.mode == InputMode.ADAPT

    if is_adapt:
        system_prompt = ADAPT_SYSTEM
        user_message = _build_adapt_message(state.project_dir)
    else:
        system_prompt = CREATIVE_SYSTEM
        user_message = _build_creative_message(state.project_dir)

    result = client.generate_structured(
        system=system_prompt,
        user_message=user_message,
        tool_name="generate_visual_reference",
        tool_schema=VISUAL_REF_SCHEMA,
    )

    ref_path = state.project_dir / "visual_reference.json"
    ref_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Visual reference complete — wrote visual_reference.json")

    state.save()
