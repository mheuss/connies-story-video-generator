"""Narration tag parsing for multi-voice TTS.

Parses YAML front matter (voice mappings) and inline voice/mood tags
from story text.

Public items:
    parse_story_header: Extract YAML front matter from story text.
    parse_narration_segments: Split tagged text into narration segments.
"""

import re

import yaml
from pydantic import ValidationError

from story_video.models import NarrationSegment, StoryHeader

__all__ = ["parse_narration_segments", "parse_story_header"]

_TAG_PATTERN = re.compile(r"\*\*(voice|mood):([^*]+)\*\*")


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


def parse_narration_segments(
    text: str,
    voice_map: dict[str, str],
    default_voice: str,
    scene_number: int,
) -> list[NarrationSegment]:
    """Split tagged text into narration segments.

    Walks the text tracking current voice and mood state. Each
    ``**voice:X**`` or ``**mood:X**`` tag closes the current segment
    and starts a new one.

    Args:
        text: Scene narration text with optional inline tags.
        voice_map: Mapping from voice labels to provider voice IDs.
        default_voice: Label to use for text before any voice tag.
        scene_number: Scene number for all produced segments.

    Returns:
        List of NarrationSegment objects in order.

    Raises:
        ValueError: If a voice tag references an undefined label.
    """
    current_voice_label = default_voice
    current_mood: str | None = None
    segments: list[NarrationSegment] = []
    segment_index = 0

    last_end = 0

    for match in _TAG_PATTERN.finditer(text):
        tag_type = match.group(1)
        tag_value = match.group(2).strip()

        # Collect text before this tag
        before_text = text[last_end : match.start()].strip()

        if before_text:
            voice_id = voice_map.get(current_voice_label)
            if voice_id is None:
                msg = (
                    f"Unknown voice label '{current_voice_label}'. "
                    f"Defined voices: {', '.join(sorted(voice_map.keys()))}."
                )
                raise ValueError(msg)

            segments.append(
                NarrationSegment(
                    text=before_text,
                    voice=voice_id,
                    voice_label=current_voice_label,
                    mood=current_mood,
                    scene_number=scene_number,
                    segment_index=segment_index,
                )
            )
            segment_index += 1

        # Apply the tag
        if tag_type == "voice":
            if tag_value not in voice_map:
                msg = (
                    f"Unknown voice label '{tag_value}'. "
                    f"Defined voices: {', '.join(sorted(voice_map.keys()))}."
                )
                raise ValueError(msg)
            current_voice_label = tag_value
            current_mood = None  # Voice change resets mood
        elif tag_type == "mood":
            current_mood = None if tag_value == "neutral" else tag_value

        last_end = match.end()

    # Remaining text after last tag
    remaining = text[last_end:].strip()
    if remaining:
        voice_id = voice_map.get(current_voice_label)
        if voice_id is None:
            msg = (
                f"Unknown voice label '{current_voice_label}'. "
                f"Defined voices: {', '.join(sorted(voice_map.keys()))}."
            )
            raise ValueError(msg)

        segments.append(
            NarrationSegment(
                text=remaining,
                voice=voice_id,
                voice_label=current_voice_label,
                mood=current_mood,
                scene_number=scene_number,
                segment_index=segment_index,
            )
        )

    return segments
