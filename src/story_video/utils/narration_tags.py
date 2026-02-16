"""Narration tag parsing for multi-voice TTS.

Parses YAML front matter (voice mappings) from story text.

Public items:
    parse_story_header: Extract YAML front matter from story text.
"""

import yaml
from pydantic import ValidationError

from story_video.models import StoryHeader

__all__ = ["parse_story_header"]


def parse_story_header(text: str) -> tuple[StoryHeader | None, str]:
    """Extract YAML front matter from story text.

    Front matter is delimited by ``---`` on its own line at the start
    and end of the header block.

    Args:
        text: Full story text, possibly with front matter.

    Returns:
        Tuple of (parsed header or None, body text with header stripped).

    Raises:
        ValueError: If the YAML is malformed or voices map is empty.
    """
    stripped = text.strip()
    if not stripped.startswith("---"):
        return None, text

    # Find closing delimiter
    rest = stripped[3:].lstrip("\n")
    closing_idx = rest.find("\n---")
    if closing_idx == -1:
        return None, text

    yaml_block = rest[:closing_idx]
    body = rest[closing_idx + 4 :].strip()

    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        msg = f"Failed to parse story header: {exc}"
        raise ValueError(msg) from exc

    if not isinstance(data, dict) or not data.get("voices"):
        msg = "Voices header is empty. Define at least one voice mapping."
        raise ValueError(msg)

    try:
        header = StoryHeader(**data)
    except ValidationError as exc:
        msg = f"Invalid story header: {exc}"
        raise ValueError(msg) from exc

    return header, body
