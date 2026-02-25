"""Narration tag parsing for multi-voice TTS.

Parses YAML front matter (voice mappings) and inline voice/mood/pause tags
from story text.

Public items:
    extract_tags: Extract all voice/mood/pause tags from text.
    has_narration_tags: Check whether text contains inline tags.
    parse_narration_segments: Split tagged text into narration segments.
    parse_story_header: Extract YAML front matter from story text.
    strip_narration_tags: Remove inline tags from text.
"""

import logging
import re

import yaml
from pydantic import ValidationError

from story_video.models import ImageTag, MusicTag, NarrationSegment, StoryHeader

logger = logging.getLogger(__name__)

__all__ = [
    "extract_image_tags",
    "extract_image_tags_stripped",
    "extract_music_tags",
    "extract_music_tags_stripped",
    "extract_tags",
    "has_narration_tags",
    "parse_narration_segments",
    "parse_story_header",
    "strip_image_tags",
    "strip_music_tags",
    "strip_narration_tags",
    "validate_image_tags",
    "validate_music_tags",
]

_TAG_PATTERN = re.compile(r"\*\*(voice|mood|pause):([^*]+)\*\*")


def has_narration_tags(text: str) -> bool:
    """Check whether text contains inline voice, mood, or pause tags."""
    return bool(_TAG_PATTERN.search(text))


def extract_tags(text: str) -> list[str]:
    """Extract all voice/mood/pause tags from text in order of appearance.

    Args:
        text: Narration text possibly containing **voice:X**, **mood:X**, and **pause:N** tags.

    Returns:
        List of tag strings in order of appearance.
    """
    return [m.group(0) for m in _TAG_PATTERN.finditer(text)]


_IMAGE_TAG_PATTERN = re.compile(r"\*\*image:([^*]+)\*\*")


def extract_image_tags(text: str) -> list[ImageTag]:
    """Extract image tags from text with their character offsets.

    Args:
        text: Story text possibly containing **image:key** tags.

    Returns:
        List of ImageTag objects ordered by position.
    """
    return [
        ImageTag(key=m.group(1).strip(), position=m.start())
        for m in _IMAGE_TAG_PATTERN.finditer(text)
    ]


_IMAGE_STRIP_PATTERN = re.compile(r"\*\*image:[^*]+\*\*\s*")


def strip_image_tags(text: str) -> str:
    """Remove inline image tags (and trailing whitespace) from text.

    Strips only ``**image:key**`` tags, leaving ``**voice:X**``,
    ``**mood:X**``, and ``**pause:N**`` tags intact. Use this to clean
    narration text before TTS so image tags are not spoken aloud.
    """
    return _IMAGE_STRIP_PATTERN.sub("", text)


_MUSIC_TAG_PATTERN = re.compile(r"\*\*music:([^*]+)\*\*")


def extract_music_tags(text: str) -> list[MusicTag]:
    """Extract music tags from text with their character offsets.

    Args:
        text: Story text possibly containing **music:key** tags.

    Returns:
        List of MusicTag objects ordered by position.
    """
    return [
        MusicTag(key=m.group(1).strip(), position=m.start())
        for m in _MUSIC_TAG_PATTERN.finditer(text)
    ]


_MUSIC_STRIP_PATTERN = re.compile(r"\*\*music:[^*]+\*\*\s*")


def strip_music_tags(text: str) -> str:
    """Remove inline music tags (and trailing whitespace) from text.

    Strips only ``**music:key**`` tags, leaving voice, mood, pause,
    and image tags intact.
    """
    return _MUSIC_STRIP_PATTERN.sub("", text)


def extract_music_tags_stripped(text: str) -> list[MusicTag]:
    """Extract music tags with positions relative to the all-tags-stripped text.

    Positions are computed against the text after ALL tags (voice, mood,
    pause, image, music) are stripped, matching the coordinate system
    of the Whisper transcript.
    """
    all_stripped = list(_STRIP_PATTERN.finditer(text))
    music_matches = list(_MUSIC_TAG_PATTERN.finditer(text))

    result = []
    for m in music_matches:
        chars_removed = sum(len(s.group(0)) for s in all_stripped if s.start() < m.start())
        stripped_pos = m.start() - chars_removed
        result.append(MusicTag(key=m.group(1).strip(), position=stripped_pos))

    return result


def validate_music_tags(tags: list[MusicTag], audio_map: dict[str, object]) -> None:
    """Validate that all music tag keys exist in the audio map.

    Args:
        tags: Music tags extracted from scene text.
        audio_map: YAML-defined audio asset map from story header.

    Raises:
        ValueError: If any tag references a key not in the audio map.
    """
    defined_keys = set(audio_map.keys())
    for tag in tags:
        if tag.key not in defined_keys:
            msg = (
                f"Music tag '**music:{tag.key}**' references undefined audio. "
                f"Defined audio: {', '.join(sorted(defined_keys)) or '(none)'}"
            )
            raise ValueError(msg)


def extract_image_tags_stripped(text: str) -> list[ImageTag]:
    """Extract image tags with positions relative to the all-tags-stripped text.

    Positions are computed against the text after ALL tags (voice, mood,
    pause, image) are stripped, matching the coordinate system of the Whisper
    transcript.
    """
    all_stripped = list(_STRIP_PATTERN.finditer(text))
    image_matches = list(_IMAGE_TAG_PATTERN.finditer(text))

    result = []
    for img in image_matches:
        chars_removed = sum(len(m.group(0)) for m in all_stripped if m.start() < img.start())
        stripped_pos = img.start() - chars_removed
        result.append(ImageTag(key=img.group(1).strip(), position=stripped_pos))

    return result


def validate_image_tags(tags: list[ImageTag], images: dict[str, str]) -> None:
    """Validate that all image tag keys exist in the images map.

    Args:
        tags: Image tags extracted from scene text.
        images: YAML-defined image prompt map from story header.

    Raises:
        ValueError: If any tag references a key not in the images map.
    """
    defined_keys = set(images.keys())
    for tag in tags:
        if tag.key not in defined_keys:
            msg = (
                f"Image tag '**image:{tag.key}**' references undefined image. "
                f"Defined images: {', '.join(sorted(defined_keys)) or '(none)'}"
            )
            raise ValueError(msg)


_STRIP_PATTERN = re.compile(r"\*\*(?:voice|mood|pause|image|music):[^*]+\*\*\s*")


def strip_narration_tags(text: str) -> str:
    """Remove inline voice/mood/pause/image/music tags (and trailing whitespace) from text.

    Tags like ``**voice:narrator**``, ``**mood:dry**``, ``**pause:0.5**``,
    ``**image:key**``, and ``**music:key**`` are metadata for the TTS and
    video pipelines and should be stripped before content analysis.
    """
    return _STRIP_PATTERN.sub("", text)


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
    # Known limitation: does not handle --- inside YAML values
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


def _resolve_voice(label: str, voice_map: dict[str, str]) -> str:
    """Look up a voice label in the voice map, raising on unknown labels."""
    voice_id = voice_map.get(label)
    if voice_id is None:
        msg = (
            f"Unknown voice label '{label}'. Defined voices: {', '.join(sorted(voice_map.keys()))}."
        )
        raise ValueError(msg)
    return voice_id


def parse_narration_segments(
    text: str,
    voice_map: dict[str, str],
    default_voice: str,
    scene_number: int,
) -> list[NarrationSegment]:
    """Split tagged text into narration segments.

    Args:
        text: Tagged narration text to parse.
        voice_map: Mapping of voice labels to provider voice IDs.
            Must not be empty.
        default_voice: Voice label to use when no voice tag is active.
        scene_number: Scene number assigned to each segment (1-based).

    Walks the text tracking current voice and mood state. Each
    ``**voice:X**`` or ``**mood:X**`` tag closes the current segment
    and starts a new one. ``**pause:N**`` tags emit a pause segment
    with the specified duration in seconds.

    Returns:
        List of NarrationSegment objects in order.

    Raises:
        ValueError: If a voice tag references an undefined label,
            or if a pause tag has a non-numeric duration.
    """
    if not voice_map:
        msg = "voice_map must not be empty"
        raise ValueError(msg)

    if not text.strip():
        msg = f"Scene {scene_number}: narration text is empty or whitespace-only"
        raise ValueError(msg)

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
            voice_id = _resolve_voice(current_voice_label, voice_map)

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
            _resolve_voice(tag_value, voice_map)  # validate label exists in voice_map
            current_voice_label = tag_value
            current_mood = None  # Voice change resets mood
        elif tag_type == "mood":
            current_mood = None if tag_value == "neutral" else tag_value
        elif tag_type == "pause":
            try:
                duration = float(tag_value)
            except ValueError as exc:
                msg = (
                    f"Invalid pause duration '{tag_value}' — must be a number (e.g., **pause:0.5**)"
                )
                raise ValueError(msg) from exc
            if duration > 30:
                logger.warning(
                    "Scene %d: pause duration %.1fs is unusually long (>30s)",
                    scene_number,
                    duration,
                )
            segments.append(
                NarrationSegment(
                    text="_pause",
                    voice="_pause",
                    voice_label="_pause",
                    pause_duration=duration,
                    scene_number=scene_number,
                    segment_index=segment_index,
                )
            )
            segment_index += 1

        last_end = match.end()

    # Remaining text after last tag
    remaining = text[last_end:].strip()
    if remaining:
        voice_id = _resolve_voice(current_voice_label, voice_map)

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
