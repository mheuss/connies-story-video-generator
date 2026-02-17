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
