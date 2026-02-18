"""Story writer pipeline — adaptation flow.

Provides scene splitting and narration flagging for the adapt input mode.
Scene splitting divides a source story into scenes at natural boundaries.
Narration flagging identifies TTS-unfriendly content in scene texts.
"""

import json
import logging

from story_video.models import AssetType, SceneStatus
from story_video.pipeline.claude_client import ClaudeClient
from story_video.state import ProjectState
from story_video.utils.narration_tags import parse_story_header, strip_narration_tags

__all__ = [
    "analyze_source",
    "create_outline",
    "create_story_bible",
    "critique_and_revise",
    "flag_narration",
    "split_scenes",
    "write_scene_prose",
]

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
    "- For stories under 1000 words, create at least 2 scenes at the"
    " strongest narrative shift\n"
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

ANALYSIS_SYSTEM = (
    "You are a literary analyst examining a story to extract its writing style"
    " and thematic essence.\n\n"
    "Your goal is to capture three things:\n"
    "1. CRAFT NOTES — How the story is written. Concrete observations about"
    " sentence structure, vocabulary choices, tone, pacing, and narrative voice."
    " Be specific: quote patterns, note tendencies, describe rhythms.\n"
    "2. THEMATIC BRIEF — What the story is about at a deeper level. Themes,"
    " emotional arc, central tension, overall mood.\n"
    "3. SOURCE STATS — Word count and estimated number of natural scenes.\n\n"
    "This analysis will be used to write a NEW, completely different story"
    " that captures the same feel. Focus on transferable qualities, not"
    " plot-specific details."
)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "craft_notes": {
            "type": "object",
            "properties": {
                "sentence_structure": {"type": "string"},
                "vocabulary": {"type": "string"},
                "tone": {"type": "string"},
                "pacing": {"type": "string"},
                "narrative_voice": {"type": "string"},
            },
            "required": [
                "sentence_structure",
                "vocabulary",
                "tone",
                "pacing",
                "narrative_voice",
            ],
        },
        "thematic_brief": {
            "type": "object",
            "properties": {
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "emotional_arc": {"type": "string"},
                "central_tension": {"type": "string"},
                "mood": {"type": "string"},
            },
            "required": ["themes", "emotional_arc", "central_tension", "mood"],
        },
        "source_stats": {
            "type": "object",
            "properties": {
                "word_count": {"type": "integer"},
                "scene_count_estimate": {"type": "integer"},
            },
            "required": ["word_count", "scene_count_estimate"],
        },
    },
    "required": ["craft_notes", "thematic_brief", "source_stats"],
}

STORY_BIBLE_SYSTEM = (
    "You are creating the foundation for a new, original story.\n\n"
    "Use the thematic brief as inspiration — same emotional territory,"
    " completely different characters and world. The craft notes describe"
    " the writing style you will use later.\n\n"
    "Create:\n"
    "- Characters: name, role (protagonist/antagonist/supporting),"
    " physical and personality description (2-3 sentences), emotional arc\n"
    "- Setting: place, time period, atmosphere\n"
    "- Premise: one-paragraph story summary\n"
    "- Rules: world-building constraints (e.g. 'no magic')\n\n"
    "Keep it compact — this context is included in every subsequent API call."
)

STORY_BIBLE_SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": ["protagonist", "antagonist", "supporting"],
                    },
                    "description": {"type": "string"},
                    "arc": {"type": "string"},
                },
                "required": ["name", "role", "description", "arc"],
            },
            "minItems": 1,
        },
        "setting": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "time_period": {"type": "string"},
                "atmosphere": {"type": "string"},
            },
            "required": ["place", "time_period", "atmosphere"],
        },
        "premise": {"type": "string"},
        "rules": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["characters", "setting", "premise", "rules"],
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

    # 1b. Strip YAML front matter (voice definitions) — Claude should only
    #     see the story body, and the preservation check must compare against
    #     the body without the header.
    _, body_text = parse_story_header(source_text)
    source_text = body_text

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

    # 2. Build user message with numbered scenes.
    #    Strip voice/mood tags — they're TTS metadata, not content for
    #    Claude to evaluate or flag.
    parts = []
    for scene in scenes:
        parts.append(f"=== Scene {scene.scene_number}: {scene.title} ===")
        parts.append(strip_narration_tags(scene.prose))
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

    # 8. Update NARRATION_TEXT status for all scenes.
    # In semi-auto mode narration_text may still be None — downstream TTS
    # falls back to scene.prose when narration_text is unset, so marking
    # the phase complete is correct regardless of mode.
    for scene in scenes:
        state.update_scene_asset(
            scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS
        )
        state.update_scene_asset(
            scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED
        )

    # 9. Persist state
    state.save()


def analyze_source(state: ProjectState, client: ClaudeClient) -> None:
    """Analyze source material to extract craft notes and thematic brief.

    Reads source_story.txt, sends it to Claude for analysis, and writes
    the result to analysis.json in the project directory.

    Args:
        state: Project state (must be in inspired_by mode).
        client: Claude API client.

    Raises:
        FileNotFoundError: If source_story.txt doesn't exist.
    """
    source_path = state.project_dir / "source_story.txt"
    if not source_path.exists():
        msg = f"source_story.txt not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    source_text = source_path.read_text(encoding="utf-8")

    # Strip YAML front matter if present
    _, body_text = parse_story_header(source_text)

    result = client.generate_structured(
        system=ANALYSIS_SYSTEM,
        user_message=body_text,
        tool_name="analyze_source",
        tool_schema=ANALYSIS_SCHEMA,
    )

    # Write analysis.json
    analysis_path = state.project_dir / "analysis.json"
    analysis_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    state.save()


def create_story_bible(state: ProjectState, client: ClaudeClient) -> None:
    """Create story bible with characters, setting, and world rules.

    Reads analysis.json for craft notes and thematic brief. Optionally
    reads premise.txt for user creative direction. Writes story_bible.json.

    Args:
        state: Project state.
        client: Claude API client.

    Raises:
        FileNotFoundError: If analysis.json doesn't exist.
    """
    analysis_path = state.project_dir / "analysis.json"
    if not analysis_path.exists():
        msg = f"analysis.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    # Build user message
    parts = [
        "## Craft Notes\n",
        json.dumps(analysis["craft_notes"], indent=2),
        "\n## Thematic Brief\n",
        json.dumps(analysis["thematic_brief"], indent=2),
    ]

    # Optional premise
    premise_path = state.project_dir / "premise.txt"
    if premise_path.exists():
        premise = premise_path.read_text(encoding="utf-8").strip()
        if premise:
            parts.append(f"\n## Author Direction\n\nThe author has requested: '{premise}'")

    user_message = "\n".join(parts)

    result = client.generate_structured(
        system=STORY_BIBLE_SYSTEM,
        user_message=user_message,
        tool_name="create_story_bible",
        tool_schema=STORY_BIBLE_SCHEMA,
    )

    bible_path = state.project_dir / "story_bible.json"
    bible_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    state.save()


def create_outline(state: ProjectState, client: ClaudeClient) -> None:
    """Create scene-by-scene outline with beats and word targets."""
    raise NotImplementedError("create_outline not yet implemented")


def write_scene_prose(state: ProjectState, client: ClaudeClient) -> None:
    """Write prose for each scene from the outline."""
    raise NotImplementedError("write_scene_prose not yet implemented")


def critique_and_revise(state: ProjectState, client: ClaudeClient) -> None:
    """Review and revise each scene's prose in a single pass."""
    raise NotImplementedError("critique_and_revise not yet implemented")


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
