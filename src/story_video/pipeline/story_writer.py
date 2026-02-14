"""Story writer pipeline — adaptation flow.

Provides scene splitting and narration flagging for the adapt input mode.
Scene splitting divides a source story into scenes at natural boundaries.
Narration flagging identifies TTS-unfriendly content in scene texts.
"""

from story_video.models import AssetType, SceneStatus
from story_video.pipeline.claude_client import ClaudeClient
from story_video.state import ProjectState

__all__ = ["split_scenes"]

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
            scene_number=scene_number, asset=AssetType.TEXT, status=SceneStatus.COMPLETED
        )

    # 8. Write markdown files
    scenes_dir = state.project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    for i, scene in enumerate(scenes):
        scene_number = i + 1
        filename = f"scene_{scene_number:02d}.md"
        content = f"# Scene {scene_number}: {scene['title']}\n\n{scene['text']}\n"
        (scenes_dir / filename).write_text(content, encoding="utf-8")

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
