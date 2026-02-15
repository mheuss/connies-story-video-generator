"""Story writer pipeline — adaptation flow.

Provides scene splitting and narration flagging for the adapt input mode.
Scene splitting divides a source story into scenes at natural boundaries.
Narration flagging identifies TTS-unfriendly content in scene texts.
"""

import logging

from story_video.models import AssetType, SceneStatus
from story_video.pipeline.claude_client import ClaudeClient
from story_video.state import ProjectState

__all__ = ["flag_narration", "split_scenes"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCENE_SPLIT_SYSTEM = (
    "You are a story editor splitting a narrative into scenes"
    " for video narration.\n\n"
    "Rules:\n"
    "- Never split mid-paragraph\n"
    "- Never split mid-dialogue (keep complete dialogue exchanges together)\n"
    "- Target 1500-2000 words per scene, but prioritize natural boundaries\n"
    "- Each scene should have a clear beginning, middle, or end\n"
    "- Preserve every word exactly — do not add, remove, or rephrase anything\n"
    "- Assign each scene a short, descriptive title (3-6 words)"
)

SCENE_SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short descriptive scene title"},
                    "text": {
                        "type": "string",
                        "description": "Complete scene text, every word preserved",
                    },
                },
                "required": ["title", "text"],
            },
            "minItems": 1,
        }
    },
    "required": ["scenes"],
}

NARRATION_FLAGS_SYSTEM = (
    "You are a narration quality reviewer preparing story text"
    " for text-to-speech.\n\n"
    "Identify content that will sound wrong or confusing when"
    " read aloud by a TTS engine:\n"
    '- Footnote references (e.g., "[1]", "as noted in [3]")\n'
    "- Visual formatting that won't translate to audio"
    " (tables, bullet lists, ASCII art)\n"
    "- Unusual typography (em dashes used decoratively,"
    " ellipsis chains)\n"
    "- Long parentheticals that break speech flow\n"
    "- Non-prose content (headers, captions, author notes)\n"
    "- Ambiguous pronunciation (acronyms, abbreviations not"
    " caught by text prep)\n\n"
    "For each issue, provide:\n"
    "- The scene number where it occurs\n"
    "- The location within the scene (paragraph and sentence)\n"
    "- The category of issue\n"
    "- The exact original text\n"
    "- A suggested fix for natural speech\n"
    '- Severity: "must_fix" for show-stoppers,'
    ' "should_fix" for noticeable issues'
)

NARRATION_FLAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer", "description": "1-based scene number"},
                    "location": {"type": "string", "description": "e.g. paragraph 2, sentence 1"},
                    "category": {
                        "type": "string",
                        "description": "e.g. footnote, formatting, typography",
                    },
                    "original_text": {
                        "type": "string",
                        "description": "The exact problematic text",
                    },
                    "suggested_fix": {
                        "type": "string",
                        "description": "Suggested replacement for natural speech",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["must_fix", "should_fix"],
                    },
                },
                "required": [
                    "scene_number",
                    "location",
                    "category",
                    "original_text",
                    "suggested_fix",
                    "severity",
                ],
            },
        }
    },
    "required": ["flags"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def split_scenes(state: ProjectState, client: ClaudeClient) -> None:
    """Split a source story into scenes using Claude.

    Reads source_story.txt from the project directory, sends it to Claude
    for scene boundary analysis, validates the result preserves all original
    text, then updates project state with the scenes.

    Args:
        state: Project state (must be in adapt mode).
        client: Claude API client for making calls.

    Raises:
        FileNotFoundError: If source_story.txt doesn't exist in project_dir.
        ValueError: If Claude returns zero scenes, any scene has empty text,
            or the preservation check fails (concatenated scenes != original).
    """
    # 1. Read source story
    source_path = state.project_dir / "source_story.txt"
    if not source_path.exists():
        msg = f"source_story.txt not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    source_text = source_path.read_text(encoding="utf-8")

    # 2. Call Claude for scene splitting
    result = client.generate_structured(
        system=SCENE_SPLIT_SYSTEM,
        user_message=source_text,
        tool_name="split_into_scenes",
        tool_schema=SCENE_SPLIT_SCHEMA,
    )

    # 3. Extract scenes
    scenes = result["scenes"]

    # 4. Validate zero scenes
    if not scenes:
        msg = "Claude returned zero scenes"
        raise ValueError(msg)

    # 5. Validate empty text
    for i, scene in enumerate(scenes):
        if not scene["text"].strip():
            msg = f"Empty text in scene {i + 1}: {scene['title']}"
            raise ValueError(msg)

    # 6. Preservation check
    _check_preservation(source_text, scenes)

    # 7. Update state with scenes
    for i, scene in enumerate(scenes):
        scene_number = i + 1
        state.add_scene(scene_number=scene_number, title=scene["title"], prose=scene["text"])
        state.update_scene_asset(
            scene_number=scene_number, asset=AssetType.TEXT, status=SceneStatus.IN_PROGRESS
        )
        state.update_scene_asset(
            scene_number=scene_number, asset=AssetType.TEXT, status=SceneStatus.COMPLETED
        )

    # 8. Write markdown files
    scenes_dir = state.project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    for i, scene in enumerate(scenes):
        scene_number = i + 1
        filename = f"scene_{scene_number:03d}.md"
        content = f"# Scene {scene_number}: {scene['title']}\n\n{scene['text']}\n"
        (scenes_dir / filename).write_text(content, encoding="utf-8")

    # 9. Persist state
    state.save()


def flag_narration(state: ProjectState, client: ClaudeClient) -> None:
    """Identify TTS-unfriendly content in scene texts.

    Sends all scene texts to Claude for analysis, writes a human-readable
    flags report, and optionally applies fixes in autonomous mode.

    Args:
        state: Project state (must have scenes populated by split_scenes).
        client: Claude API client for making calls.

    Raises:
        ValueError: If no scenes exist in state.
    """
    # 1. Get scenes — raise if empty
    scenes = state.metadata.scenes
    if not scenes:
        msg = "No scenes in project"
        raise ValueError(msg)

    # 2. Build user message with numbered scenes
    parts = []
    for scene in scenes:
        parts.append(f"=== Scene {scene.scene_number}: {scene.title} ===")
        parts.append(scene.prose)
        parts.append("")
    scene_text = "\n".join(parts)

    # 3. Call Claude for narration flagging
    result = client.generate_structured(
        system=NARRATION_FLAGS_SYSTEM,
        user_message=scene_text,
        tool_name="flag_narration_issues",
        tool_schema=NARRATION_FLAGS_SCHEMA,
    )

    # 4. Extract flags
    flags = result["flags"]

    # 5. Write narration_flags.md
    flags_path = state.project_dir / "narration_flags.md"
    if flags:
        lines = ["# Narration Flags\n"]
        for i, flag in enumerate(flags):
            lines.append(f"## Scene {flag['scene_number']}: {flag['category']}\n")
            lines.append(f"**Location:** {flag['location']}")
            lines.append(f"**Severity:** {flag['severity']}")
            lines.append(f"**Original:** {flag['original_text']}")
            lines.append(f"**Suggested fix:** {flag['suggested_fix']}\n")
            if i < len(flags) - 1:
                lines.append("---\n")
        flags_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        flags_path.write_text(
            "# Narration Flags\n\nNo TTS issues found. All scenes are narration-ready.\n",
            encoding="utf-8",
        )

    # 6. Autonomous mode: apply fixes
    if state.metadata.config.pipeline.autonomous:
        # Build a lookup of scene_number -> scene for fast access
        scene_map = {s.scene_number: s for s in scenes}

        for flag in flags:
            scene_num = flag["scene_number"]
            scene = scene_map.get(scene_num)
            if scene is None:
                logger.warning(
                    "Flag references scene %d which does not exist; skipping",
                    scene_num,
                )
                continue

            # Copy prose to narration_text if not already set
            if scene.narration_text is None:
                scene.narration_text = scene.prose

            # Apply fix: replace original_text with suggested_fix.
            # NOTE: str.replace() affects all occurrences. If the same phrase
            # appears multiple times, all instances will be changed. This is
            # acceptable because flagged text patterns are typically unique.
            before = scene.narration_text
            scene.narration_text = scene.narration_text.replace(
                flag["original_text"], flag["suggested_fix"]
            )
            if scene.narration_text == before:
                logger.warning(
                    "Flag original_text not found in scene %d; fix not applied: %r",
                    scene_num,
                    flag["original_text"],
                )

    # 7. Semi-auto mode: flags file only — no narration_text changes

    # 8. Update NARRATION_TEXT status for all scenes
    for scene in scenes:
        state.update_scene_asset(
            scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS
        )
        state.update_scene_asset(
            scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED
        )

    # 9. Persist state
    state.save()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _check_preservation(original: str, scenes: list[dict]) -> None:
    """Verify concatenated scene texts match the original source.

    Normalizes whitespace before comparison: collapses all whitespace to single
    spaces. This allows Claude to adjust paragraph breaks between scenes without
    failing.

    Args:
        original: The original source story text.
        scenes: List of scene dicts with "text" keys.

    Raises:
        ValueError: If the texts don't match, with context showing where
            the mismatch occurs.
    """
    normalized_original = " ".join(original.split())
    concatenated = " ".join(scene["text"] for scene in scenes)
    normalized_concatenated = " ".join(concatenated.split())

    if normalized_original != normalized_concatenated:
        # Find position of first difference for debugging
        pos = _find_first_difference(normalized_original, normalized_concatenated)
        context_start = max(0, pos - 30)
        context_end = pos + 30

        original_snippet = normalized_original[context_start:context_end]
        concatenated_snippet = normalized_concatenated[context_start:context_end]

        msg = (
            f"Text preservation mismatch at position {pos}. "
            f"Original: '...{original_snippet}...' "
            f"Concatenated: '...{concatenated_snippet}...'"
        )
        raise ValueError(msg)


def _find_first_difference(a: str, b: str) -> int:
    """Find the index of the first character where two strings differ.

    Args:
        a: First string.
        b: Second string.

    Returns:
        Index of the first differing character, or the length of the
        shorter string if one is a prefix of the other.
    """
    min_len = min(len(a), len(b))
    for i in range(min_len):
        if a[i] != b[i]:
            return i
    return min_len
