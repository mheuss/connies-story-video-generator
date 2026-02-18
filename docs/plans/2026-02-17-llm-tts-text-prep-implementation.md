# LLM-Based TTS Text Prep — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** Completed

**Goal:** Replace regex-based narration prep with Claude API calls for context-aware TTS text preparation.

**Architecture:** One new pipeline module (`narration_prep.py`) provides the LLM-based prep function. The orchestrator's `_run_narration_prep()` calls it per scene, accumulating a pronunciation guide and changelog. All regex transform code in `text.py` is deleted.

**Tech Stack:** Python 3.11+, Pydantic, Anthropic SDK (via existing `ClaudeClient`), pytest

**Design doc:** `docs/plans/2026-02-17-llm-tts-text-prep-design.md`

---

### Task 1: Tag extraction, validation, and NarrationPrepError

Create the new module with pure utility functions and the custom exception.

**Files:**
- Create: `src/story_video/pipeline/narration_prep.py`
- Create: `tests/test_narration_prep.py`

**Step 1: Write the failing tests**

In `tests/test_narration_prep.py`:

```python
"""Tests for story_video.pipeline.narration_prep — LLM-based TTS text preparation."""

import re

import pytest


class TestExtractTags:
    """_extract_tags returns all voice/mood tags in order."""

    def test_no_tags(self):
        from story_video.pipeline.narration_prep import _extract_tags

        assert _extract_tags("Plain text with no tags.") == []

    def test_single_voice_tag(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = "**voice:narrator** He spoke softly."
        assert _extract_tags(text) == ["**voice:narrator**"]

    def test_multiple_tags(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = '**voice:old_man** "I\'ve seen worse," **voice:narrator** he muttered.'
        assert _extract_tags(text) == ["**voice:old_man**", "**voice:narrator**"]

    def test_mood_tag(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = "**mood:somber** The rain fell."
        assert _extract_tags(text) == ["**mood:somber**"]

    def test_mixed_voice_and_mood(self):
        from story_video.pipeline.narration_prep import _extract_tags

        text = "**voice:jane** **mood:excited** She laughed."
        assert _extract_tags(text) == ["**voice:jane**", "**mood:excited**"]


class TestValidateTagsPreserved:
    """_validate_tags_preserved checks tags match between original and modified."""

    def test_identical_tags_valid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:narrator** Hello."
        modified = "**voice:narrator** Greetings."
        assert _validate_tags_preserved(original, modified) is True

    def test_missing_tag_invalid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:narrator** Hello **voice:bob** world."
        modified = "**voice:narrator** Hello world."
        assert _validate_tags_preserved(original, modified) is False

    def test_reordered_tags_invalid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:a** text **voice:b** more."
        modified = "**voice:b** text **voice:a** more."
        assert _validate_tags_preserved(original, modified) is False

    def test_extra_tag_invalid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        original = "**voice:narrator** Hello."
        modified = "**voice:narrator** Hello **mood:sad** world."
        assert _validate_tags_preserved(original, modified) is False

    def test_no_tags_both_sides_valid(self):
        from story_video.pipeline.narration_prep import _validate_tags_preserved

        assert _validate_tags_preserved("Plain text.", "Different plain text.") is True


class TestNarrationPrepError:
    """NarrationPrepError is a distinct exception type."""

    def test_is_exception(self):
        from story_video.pipeline.narration_prep import NarrationPrepError

        with pytest.raises(NarrationPrepError, match="scene 1"):
            raise NarrationPrepError("scene 1: tags corrupted")

    def test_subclass_of_exception(self):
        from story_video.pipeline.narration_prep import NarrationPrepError

        assert issubclass(NarrationPrepError, Exception)
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'story_video.pipeline.narration_prep'`

**Step 3: Write minimal implementation**

In `src/story_video/pipeline/narration_prep.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py -v`
Expected: 12 PASSED

**Step 5: Commit**

```bash
git add tests/test_narration_prep.py src/story_video/pipeline/narration_prep.py
git commit -m "feat: add tag extraction, validation, and NarrationPrepError"
```

---

### Task 2: Prompt building

Add the system prompt, tool schema, and user message builder.

**Files:**
- Modify: `src/story_video/pipeline/narration_prep.py`
- Modify: `tests/test_narration_prep.py`

**Step 1: Write the failing tests**

Append to `tests/test_narration_prep.py`:

```python
class TestBuildUserMessage:
    """_build_user_message constructs the Claude user message."""

    def test_basic_message(self):
        from story_video.pipeline.narration_prep import _build_user_message

        result = _build_user_message(
            "Hello world.",
            pronunciation_guide=[],
            story_title="Test Story",
            scene_number=1,
            total_scenes=3,
        )
        assert "Test Story" in result
        assert "Scene 1 of 3" in result
        assert "Hello world." in result

    def test_includes_pronunciation_guide(self):
        from story_video.pipeline.narration_prep import _build_user_message

        guide = [{"term": "Cthulhu", "pronunciation": "kuh-THOO-loo", "context": "proper noun"}]
        result = _build_user_message(
            "Cthulhu rises.",
            pronunciation_guide=guide,
            story_title="Horror",
            scene_number=2,
            total_scenes=5,
        )
        assert "Cthulhu" in result
        assert "kuh-THOO-loo" in result

    def test_empty_guide_omitted(self):
        from story_video.pipeline.narration_prep import _build_user_message

        result = _build_user_message(
            "Plain text.",
            pronunciation_guide=[],
            story_title="Test",
            scene_number=1,
            total_scenes=1,
        )
        assert "Pronunciation guide" not in result


class TestPromptConstants:
    """Verify prompt constants exist and have expected structure."""

    def test_system_prompt_mentions_tags(self):
        from story_video.pipeline.narration_prep import _SYSTEM_PROMPT

        assert "voice" in _SYSTEM_PROMPT.lower()
        assert "mood" in _SYSTEM_PROMPT.lower()

    def test_tool_schema_has_required_fields(self):
        from story_video.pipeline.narration_prep import _TOOL_SCHEMA

        props = _TOOL_SCHEMA["properties"]
        assert "modified_text" in props
        assert "changes" in props
        assert "pronunciation_guide_additions" in props

    def test_tool_name_is_string(self):
        from story_video.pipeline.narration_prep import _TOOL_NAME

        assert isinstance(_TOOL_NAME, str)
        assert len(_TOOL_NAME) > 0
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py::TestBuildUserMessage -v`
Expected: FAIL — `ImportError: cannot import name '_build_user_message'`

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py::TestPromptConstants -v`
Expected: FAIL — `ImportError: cannot import name '_SYSTEM_PROMPT'`

**Step 3: Write minimal implementation**

Add to `src/story_video/pipeline/narration_prep.py`:

```python
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
            parts.append(
                f"  - {entry['term']}: {entry['pronunciation']} ({entry['context']})"
            )
        parts.append("")

    parts.append("Narration text to prepare for TTS:")
    parts.append("")
    parts.append(text)

    return "\n".join(parts)
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py -v`
Expected: 18 PASSED

**Step 5: Commit**

```bash
git add src/story_video/pipeline/narration_prep.py tests/test_narration_prep.py
git commit -m "feat: add TTS text prep prompt building and tool schema"
```

---

### Task 3: Core LLM function — prepare_narration_llm()

The main function that calls Claude, validates tags, and handles retry.

**Files:**
- Modify: `src/story_video/pipeline/narration_prep.py`
- Modify: `tests/test_narration_prep.py`

**Step 1: Write the failing tests**

Append to `tests/test_narration_prep.py`:

```python
from unittest.mock import MagicMock


class TestPrepareNarrationLlm:
    """prepare_narration_llm calls Claude and returns structured result."""

    def _make_mock_client(self, modified_text="Prepared text.", changes=None, guide=None):
        """Create a mock ClaudeClient returning a canned response."""
        client = MagicMock()
        client.generate_structured.return_value = {
            "modified_text": modified_text,
            "changes": changes or [],
            "pronunciation_guide_additions": guide or [],
        }
        return client

    def test_returns_modified_text(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = self._make_mock_client(modified_text="Rewritten text.")
        result = prepare_narration_llm("Original text.", client)
        assert result["modified_text"] == "Rewritten text."

    def test_returns_changes(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        changes = [{"original": "Dr.", "replacement": "Doctor", "reason": "abbreviation"}]
        client = self._make_mock_client(changes=changes)
        result = prepare_narration_llm("Dr. Smith spoke.", client)
        assert result["changes"] == changes

    def test_returns_pronunciation_guide_additions(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        guide = [{"term": "Cthulhu", "pronunciation": "kuh-THOO-loo", "context": "deity name"}]
        client = self._make_mock_client(guide=guide)
        result = prepare_narration_llm("Cthulhu rises.", client)
        assert result["pronunciation_guide_additions"] == guide

    def test_passes_pronunciation_guide_to_prompt(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = self._make_mock_client()
        guide = [{"term": "Nyarlathotep", "pronunciation": "nyar-LATH-oh-tep", "context": "name"}]
        prepare_narration_llm(
            "Plain text.", client, pronunciation_guide=guide, scene_number=2, total_scenes=3
        )

        call_kwargs = client.generate_structured.call_args
        user_msg = call_kwargs.kwargs.get("user_message") or call_kwargs[1].get("user_message", "")
        # If positional, check args
        if not user_msg:
            # generate_structured(system=..., user_message=..., ...)
            user_msg = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else ""
        assert "Nyarlathotep" in user_msg

    def test_preserves_tags_passes(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = self._make_mock_client(
            modified_text="**voice:narrator** Prepared text."
        )
        result = prepare_narration_llm("**voice:narrator** Original text.", client)
        assert result["modified_text"] == "**voice:narrator** Prepared text."

    def test_corrupted_tags_retries_once(self):
        from story_video.pipeline.narration_prep import prepare_narration_llm

        client = MagicMock()
        # First call: tags missing. Second call: tags correct.
        client.generate_structured.side_effect = [
            {
                "modified_text": "Tags removed.",
                "changes": [],
                "pronunciation_guide_additions": [],
            },
            {
                "modified_text": "**voice:narrator** Tags restored.",
                "changes": [],
                "pronunciation_guide_additions": [],
            },
        ]
        result = prepare_narration_llm("**voice:narrator** Original.", client)
        assert client.generate_structured.call_count == 2
        assert result["modified_text"] == "**voice:narrator** Tags restored."

    def test_corrupted_tags_after_retry_raises(self):
        from story_video.pipeline.narration_prep import (
            NarrationPrepError,
            prepare_narration_llm,
        )

        client = MagicMock()
        # Both calls return corrupted tags
        client.generate_structured.return_value = {
            "modified_text": "No tags here.",
            "changes": [],
            "pronunciation_guide_additions": [],
        }
        with pytest.raises(NarrationPrepError, match="tags corrupted"):
            prepare_narration_llm("**voice:narrator** Original.", client)

    def test_empty_modified_text_raises(self):
        from story_video.pipeline.narration_prep import (
            NarrationPrepError,
            prepare_narration_llm,
        )

        client = self._make_mock_client(modified_text="")
        with pytest.raises(NarrationPrepError, match="empty"):
            prepare_narration_llm("Some text.", client)

    def test_calls_generate_structured_with_tool_schema(self):
        from story_video.pipeline.narration_prep import (
            _TOOL_NAME,
            _TOOL_SCHEMA,
            prepare_narration_llm,
        )

        client = self._make_mock_client()
        prepare_narration_llm("Text.", client)
        client.generate_structured.assert_called_once()
        call_kwargs = client.generate_structured.call_args.kwargs
        assert call_kwargs["tool_name"] == _TOOL_NAME
        assert call_kwargs["tool_schema"] == _TOOL_SCHEMA
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py::TestPrepareNarrationLlm -v`
Expected: FAIL — `ImportError: cannot import name 'prepare_narration_llm'`

**Step 3: Write minimal implementation**

Add to `src/story_video/pipeline/narration_prep.py`, updating `__all__` and imports:

```python
# At top of file, add:
import logging
from story_video.pipeline.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

# Update __all__:
__all__ = ["NarrationPrepError", "prepare_narration_llm"]
```

Then add the function:

```python
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
        Dict with keys: modified_text (str), changes (list), pronunciation_guide_additions (list).

    Raises:
        NarrationPrepError: If modified_text is empty or tags are corrupted after retry.
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
            user_message
            + "\n\nIMPORTANT: Your previous response modified the voice/mood tags. "
            "You must preserve ALL **voice:X** and **mood:X** tags exactly as they appear "
            "in the original text — same tags, same positions, same order."
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py -v`
Expected: 28 PASSED

**Step 5: Commit**

```bash
git add src/story_video/pipeline/narration_prep.py tests/test_narration_prep.py
git commit -m "feat: add prepare_narration_llm with tag validation and retry"
```

---

### Task 4: Changelog writing

Write the narration prep changelog to the project directory as JSON.

**Files:**
- Modify: `src/story_video/pipeline/narration_prep.py`
- Modify: `tests/test_narration_prep.py`

**Step 1: Write the failing tests**

Append to `tests/test_narration_prep.py`:

```python
import json


class TestWriteNarrationChangelog:
    """write_narration_changelog writes JSON to project directory."""

    def test_writes_json_file(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

        changelog = [
            {
                "scene": 1,
                "original": "Dr. Smith",
                "replacement": "Doctor Smith",
                "reason": "abbreviation",
            }
        ]
        path = write_narration_changelog(changelog, tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["original"] == "Dr. Smith"

    def test_file_name(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

        path = write_narration_changelog([], tmp_path)
        assert path.name == "narration_prep_changelog.json"

    def test_empty_changelog(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

        path = write_narration_changelog([], tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []

    def test_multiple_scenes(self, tmp_path):
        from story_video.pipeline.narration_prep import write_narration_changelog

        changelog = [
            {"scene": 1, "original": "5", "replacement": "five", "reason": "number"},
            {"scene": 2, "original": "Mr.", "replacement": "Mister", "reason": "abbreviation"},
        ]
        path = write_narration_changelog(changelog, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["scene"] == 1
        assert data[1]["scene"] == 2
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py::TestWriteNarrationChangelog -v`
Expected: FAIL — `ImportError: cannot import name 'write_narration_changelog'`

**Step 3: Write minimal implementation**

Add to `src/story_video/pipeline/narration_prep.py`, updating imports and `__all__`:

```python
# Add to imports:
import json
from pathlib import Path

# Update __all__:
__all__ = ["NarrationPrepError", "prepare_narration_llm", "write_narration_changelog"]
```

Then add the function:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narration_prep.py -v`
Expected: 32 PASSED

**Step 5: Commit**

```bash
git add src/story_video/pipeline/narration_prep.py tests/test_narration_prep.py
git commit -m "feat: add narration prep changelog writer"
```

---

### Task 5: Wire orchestrator to use LLM narration prep

Replace the old `_run_narration_prep()` with the new LLM-based version. Add NARRATION_PREP to checkpoint phases and require claude_client for the phase.

**Files:**
- Modify: `src/story_video/pipeline/orchestrator.py:16,30,39-45,224-278`
- Modify: `tests/test_orchestrator.py` (multiple mock patches)

**Step 1: Update orchestrator tests**

In `tests/test_orchestrator.py`, all `@patch("story_video.pipeline.orchestrator.prepare_narration", ...)` decorators must change to mock the new function. Since the new `_run_narration_prep` calls `prepare_narration_llm` from the narration_prep module, and the orchestrator imports it at the top level, the mock target changes.

The orchestrator's `_run_narration_prep` will import and call `prepare_narration_llm` directly. We mock it as:
`@patch("story_video.pipeline.orchestrator.prepare_narration_llm")`

**Changes to `tests/test_orchestrator.py`:**

1. **Line 30** — Remove import of `prepare_narration` (it's no longer used by orchestrator). No replacement needed since it's mocked via patch strings.

2. **All mock patches** — Replace every instance of:
   ```python
   @patch("story_video.pipeline.orchestrator.prepare_narration", return_value="prepped text")
   ```
   with:
   ```python
   @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
   ```

   The mock must now return a dict instead of a string. Where `return_value="prepped text"` was used, change to:
   ```python
   @patch("story_video.pipeline.orchestrator.prepare_narration_llm", return_value={
       "modified_text": "prepped text",
       "changes": [],
       "pronunciation_guide_additions": [],
   })
   ```

3. **TestRunPipelineNarrationPrep class** — Update all three tests:
   - `test_narration_prep_transforms_all_scenes`: Check `mock_prep.call_count == 2` still works. The return value's `modified_text` is what gets assigned to `scene.narration_text`.
   - `test_narration_prep_uses_prose_when_no_narration_text`: `mock_prep` is now called with positional args `(text, claude_client, ...)`. Adjust assertion.
   - `test_narration_prep_does_not_change_asset_status`: Same mock return value change.

4. **TestDispatchPhaseProviderGuards** — Add test for NARRATION_PREP requiring claude_client:
   ```python
   def test_narration_prep_requires_claude_client(self, tmp_path):
       state = _make_adapt_state(tmp_path)
       with pytest.raises(ValueError, match="claude_client is required for NARRATION_PREP"):
           _dispatch_phase(PipelinePhase.NARRATION_PREP, state, claude_client=None, ...)
   ```

5. **Add NARRATION_PREP to checkpoint test** — In `TestRunPipelineSemiAutoCheckpoints`, verify NARRATION_PREP pauses for review.

**Step 2: Run tests to verify they fail (old mocks broken)**

Run: `.venv/bin/python -m pytest tests/test_orchestrator.py::TestRunPipelineNarrationPrep -v`
Expected: FAIL (tests still reference old mock)

**Step 3: Update orchestrator implementation**

In `src/story_video/pipeline/orchestrator.py`:

1. **Remove** line 30: `from story_video.utils.text import prepare_narration`

2. **Add import** at top:
   ```python
   from story_video.pipeline.narration_prep import prepare_narration_llm, write_narration_changelog
   ```

3. **Add NARRATION_PREP to checkpoint set** (line 39-45):
   ```python
   _CHECKPOINT_PHASES = frozenset(
       {
           PipelinePhase.SCENE_SPLITTING,
           PipelinePhase.NARRATION_FLAGGING,
           PipelinePhase.IMAGE_PROMPTS,
           PipelinePhase.NARRATION_PREP,
       }
   )
   ```

4. **Update `_dispatch_phase`** (line 224-225):
   ```python
   elif phase == PipelinePhase.NARRATION_PREP:
       if claude_client is None:
           msg = "claude_client is required for NARRATION_PREP phase"
           raise ValueError(msg)
       _run_narration_prep(state, claude_client)
   ```

5. **Replace `_run_narration_prep`** (lines 257-278):
   ```python
   def _run_narration_prep(state: ProjectState, claude_client: ClaudeClient) -> None:
       """Apply LLM-based narration preparation to all scenes.

       Calls Claude once per scene to rewrite narration text for TTS. Accumulates
       a pronunciation guide across scenes (scene 1's entries feed into scene 2's
       prompt). Writes a changelog of all modifications to the project directory.

       Runs on ALL scenes (not just pending ones) because narration_text assets
       are already COMPLETED from the flagging phase.
       """
       pronunciation_guide: list[dict[str, str]] = []
       changelog: list[dict] = []
       total_scenes = len(state.metadata.scenes)

       for scene in state.metadata.scenes:
           text = scene.narration_text or scene.prose
           if not text:
               continue

           result = prepare_narration_llm(
               text,
               claude_client,
               pronunciation_guide=pronunciation_guide,
               story_title=state.metadata.project_id,
               scene_number=scene.scene_number,
               total_scenes=total_scenes,
           )

           scene.narration_text = result["modified_text"]

           for addition in result["pronunciation_guide_additions"]:
               pronunciation_guide.append(addition)

           for change in result["changes"]:
               changelog.append({"scene": scene.scene_number, **change})

       if changelog:
           write_narration_changelog(changelog, state.project_dir)
   ```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: ALL PASSED

**Step 5: Commit**

```bash
git add src/story_video/pipeline/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: wire orchestrator to LLM-based narration prep"
```

---

### Task 6: Delete regex narration prep code

Remove all regex transform functions from `text.py` and their tests. The file becomes empty and is deleted entirely.

**Files:**
- Delete: `src/story_video/utils/text.py`
- Delete: `tests/test_text.py`

**Step 1: Verify no remaining imports of text.py**

Run: `grep -r "from story_video.utils.text import" src/ tests/`
Expected: Zero results (orchestrator import was removed in Task 5).

If any imports remain, they must be addressed before deletion.

**Step 2: Delete the files**

```bash
git rm src/story_video/utils/text.py tests/test_text.py
```

**Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: ALL PASSED (minus the ~63 deleted text.py tests; count should drop by ~63)

**Step 4: Commit**

```bash
git commit -m "refactor: remove regex-based narration prep (replaced by LLM)"
```

---

### Task 7: Update integration test

The integration test `TestPipelineIntegration.test_full_adapt_pipeline_data_flow` runs the full 8-phase pipeline with mocked external APIs. It needs a Claude mock for the new `tts_text_prep` tool call, and updated assertion counts.

**Files:**
- Modify: `tests/test_orchestrator.py:1007-1181`

**Step 1: Update the integration test**

In `tests/test_orchestrator.py`, class `TestPipelineIntegration`:

1. **Add `tts_text_prep` to Claude responses** (after line 1052). The mock dispatches by `tool_name`, so add:
   ```python
   "tts_text_prep": {
       "modified_text": "Prepared narration text.",
       "changes": [],
       "pronunciation_guide_additions": [],
   },
   ```

   However, since each scene sends its own text and the mock returns a static response, `narration_text` will be "Prepared narration text." for all scenes. The existing assertions `assert scene.narration_text is not None` (lines 1140-1141) will still pass.

2. **Update Claude call count assertion** (line 1173):
   ```python
   # Was: assert mock_claude.generate_structured.call_count == 3
   # Now: 3 original (split, flag, prompts) + 2 narration prep = 5
   assert mock_claude.generate_structured.call_count == 5
   ```

3. **Add NARRATION_PREP checkpoint handling**. Since the test runs in autonomous mode (`autonomous=True`), NARRATION_PREP won't pause — the checkpoint is skipped. No change needed here.

**Step 2: Run the integration test**

Run: `.venv/bin/python -m pytest tests/test_orchestrator.py::TestPipelineIntegration -v`
Expected: PASSED

**Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: ALL PASSED

**Step 4: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: update integration test for LLM narration prep"
```

---

### Task 8: Backlog and docs update

Update BUGS_AND_TODOS.md to reflect the completed feature and related items.

**Files:**
- Modify: `BUGS_AND_TODOS.md`

**Step 1: Mark items**

In `BUGS_AND_TODOS.md`:

1. Mark the LLM-based TTS text prep feature as complete (line 49):
   ```
   - [x] [feature] LLM-based TTS text prep — ...
   ```

2. Mark PR-10 (abbreviation period loss) as superseded/resolved (line 27) — it was already noted as superseded by this feature. Ensure it's marked `[x]`:
   ```
   - [x] [bug] Sentence-ending period lost after abbreviations — superseded by LLM-based TTS text prep
   ```

3. Move both items to the Resolved section.

4. Remove backlog items that were about the old regex code:
   - T8 (boundary tests for `_int_to_words` / `_year_to_words`) — code deleted
   - Any other items referencing `text.py` regex functions

**Step 2: Update plan status**

In `docs/plans/2026-02-17-llm-tts-text-prep-implementation.md`, change `**Status:** Pending` to `**Status:** Completed`.

In `docs/plans/2026-02-17-llm-tts-text-prep-design.md`, no change needed (already Approved).

**Step 3: Commit**

```bash
git add BUGS_AND_TODOS.md docs/plans/2026-02-17-llm-tts-text-prep-implementation.md
git commit -m "docs: update backlog for completed LLM text prep feature"
```

---

## Retrospective

(To be filled in after implementation)
