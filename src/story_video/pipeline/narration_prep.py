"""LLM-based TTS text preparation.

Replaces regex-based narration prep with Claude API calls for context-aware
pronunciation preparation. Handles abbreviation expansion, number pronunciation,
punctuation smoothing, and contextual decisions.

See design doc: docs/plans/2026-02-17-llm-tts-text-prep-design.md
"""

import json
import logging
from pathlib import Path

from story_video.pipeline.claude_client import ClaudeClient
from story_video.utils.narration_tags import extract_tags

__all__ = ["NarrationPrepError", "prepare_narration_llm", "write_narration_changelog"]

logger = logging.getLogger(__name__)


class NarrationPrepError(Exception):
    """Raised when LLM-based narration preparation fails for a scene."""


def _validate_tags_preserved(original_text: str, modified_text: str) -> bool:
    """Check that modified text preserves all tags from original in same order.

    Args:
        original_text: Text before LLM processing.
        modified_text: Text after LLM processing.

    Returns:
        True if tags match exactly (same tags, same order).
    """
    return extract_tags(original_text) == extract_tags(modified_text)


_SYSTEM_PROMPT = (
    "You are a TTS text preparation specialist. Your job is to rewrite narration "
    "text so it sounds natural when read aloud by a text-to-speech engine. You must:\n"
    '- Expand abbreviations contextually (e.g., "Dr." → "Doctor" before a name, '
    '"Drive" in an address)\n'
    '- Convert numbers to spoken form (e.g., "1847" → "eighteen forty-seven" for years, '
    '"one thousand eight hundred forty-seven" for quantities)\n'
    "- Smooth punctuation for speech flow (e.g., em dashes → commas or pauses)\n"
    "- Handle unusual names or terms using the pronunciation guide\n"
    "- Preserve all **voice:X** and **mood:X** tags exactly as they appear — "
    "do not move, add, remove, or modify any tag"
)

_TOOL_NAME = "tts_text_prep"

_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "modified_text": {
            "type": "string",
            "description": (
                "The full narration text rewritten for TTS, "
                "with all voice/mood tags preserved exactly"
            ),
        },
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "replacement": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["original", "replacement", "reason"],
            },
        },
        "pronunciation_guide_additions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "pronunciation": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["term", "pronunciation", "context"],
            },
        },
    },
    "required": ["modified_text", "changes", "pronunciation_guide_additions"],
}


def _build_user_message(
    text: str,
    *,
    pronunciation_guide: list[dict[str, str]],
    story_title: str,
    scene_number: int,
    total_scenes: int,
) -> str:
    """Build the user message for the TTS prep Claude call.

    Args:
        text: Scene narration text (with voice/mood tags).
        pronunciation_guide: Accumulated guide from previous scenes.
        story_title: Story title for context.
        scene_number: Current scene number (1-based).
        total_scenes: Total number of scenes.

    Returns:
        Formatted user message string.
    """
    parts = [
        f"Story: {story_title}",
        f"Scene {scene_number} of {total_scenes}",
        "",
    ]

    if pronunciation_guide:
        parts.append("Pronunciation guide from previous scenes:")
        for entry in pronunciation_guide:
            parts.append(f"  - {entry['term']}: {entry['pronunciation']} ({entry['context']})")
        parts.append("")

    parts.append("Narration text to prepare for TTS:")
    parts.append("")
    parts.append(text)

    return "\n".join(parts)


def prepare_narration_llm(
    text: str,
    claude_client: ClaudeClient,
    *,
    pronunciation_guide: list[dict[str, str]] | None = None,
    story_title: str = "Untitled",
    scene_number: int = 1,
    total_scenes: int = 1,
) -> dict:
    """Prepare narration text for TTS using Claude.

    Sends scene text to Claude with instructions to rewrite it for natural
    TTS delivery. Validates that voice/mood tags are preserved. Retries
    once on tag corruption before failing.

    Args:
        text: Scene narration text (may contain voice/mood tags).
        claude_client: Claude API client for generate_structured calls.
        pronunciation_guide: Accumulated guide entries from previous scenes.
        story_title: Story title for context in the prompt.
        scene_number: Current scene number (1-based).
        total_scenes: Total number of scenes in the story.

    Returns:
        Dict with keys: modified_text (str), changes (list),
        pronunciation_guide_additions (list).

    Raises:
        NarrationPrepError: If modified_text is empty or tags are corrupted
            after retry.
    """
    guide = pronunciation_guide or []

    user_message = _build_user_message(
        text,
        pronunciation_guide=guide,
        story_title=story_title,
        scene_number=scene_number,
        total_scenes=total_scenes,
    )

    result = claude_client.generate_structured(
        system=_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name=_TOOL_NAME,
        tool_schema=_TOOL_SCHEMA,
    )

    modified_text = result.get("modified_text", "")
    if not modified_text:
        msg = f"Scene {scene_number}: Claude returned empty modified_text"
        raise NarrationPrepError(msg)

    # Validate tags preserved
    if not _validate_tags_preserved(text, modified_text):
        logger.warning("Scene %d: tags not preserved, retrying with correction", scene_number)
        corrective = (
            user_message + "\n\nIMPORTANT: Your previous response modified the voice/mood tags. "
            "You must preserve ALL **voice:X** and **mood:X** tags exactly as they "
            "appear in the original text — same tags, same positions, same order."
        )
        result = claude_client.generate_structured(
            system=_SYSTEM_PROMPT,
            user_message=corrective,
            tool_name=_TOOL_NAME,
            tool_schema=_TOOL_SCHEMA,
        )
        modified_text = result.get("modified_text", "")
        if not modified_text or not _validate_tags_preserved(text, modified_text):
            msg = f"Scene {scene_number}: tags corrupted after retry"
            raise NarrationPrepError(msg)

    return {
        "modified_text": modified_text,
        "changes": result.get("changes", []),
        "pronunciation_guide_additions": result.get("pronunciation_guide_additions", []),
    }


def write_narration_changelog(
    changelog: list[dict],
    project_dir: Path,
) -> Path:
    """Write narration prep changelog to project directory as JSON.

    Args:
        changelog: List of change dicts from all scenes.
            Each dict has keys: scene, original, replacement, reason.
        project_dir: Project directory path.

    Returns:
        Path to the written changelog file.
    """
    path = project_dir / "narration_prep_changelog.json"
    path.write_text(
        json.dumps(changelog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
