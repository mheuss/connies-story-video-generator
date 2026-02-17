"""LLM-based TTS text preparation.

Replaces regex-based narration prep with Claude API calls for context-aware
pronunciation preparation. Handles abbreviation expansion, number pronunciation,
punctuation smoothing, and contextual decisions.

See design doc: docs/plans/2026-02-17-llm-tts-text-prep-design.md
"""

import re

__all__ = ["NarrationPrepError"]

_TAG_PATTERN = re.compile(r"\*\*(?:voice|mood):[^*]+\*\*")


class NarrationPrepError(Exception):
    """Raised when LLM-based narration preparation fails for a scene."""


def _extract_tags(text: str) -> list[str]:
    """Extract all voice/mood tags from text in order of appearance.

    Args:
        text: Narration text possibly containing **voice:X** and **mood:X** tags.

    Returns:
        List of tag strings in order of appearance.
    """
    return _TAG_PATTERN.findall(text)


def _validate_tags_preserved(original_text: str, modified_text: str) -> bool:
    """Check that modified text preserves all tags from original in same order.

    Args:
        original_text: Text before LLM processing.
        modified_text: Text after LLM processing.

    Returns:
        True if tags match exactly (same tags, same order).
    """
    return _extract_tags(original_text) == _extract_tags(modified_text)


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
