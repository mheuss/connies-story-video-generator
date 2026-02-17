# Low Priority Fixes Implementation Plan (PR-13 through PR-25)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address all 13 low-priority items from the 2026-02-17 project review in a single implementation pass.

**Architecture:** 8 tasks grouped by logical affinity. Each task is independently committable. TDD where behavior changes; direct fixes where TDD doesn't apply (deletions, docstrings, consistency fixes).

**Tech Stack:** Python, pytest, Pydantic, Typer

**Status:** Pending

---

## Task 1: Trivial housekeeping (PR-13, PR-17, PR-19, PR-21)

Four items requiring no new tests — file deletion, docstring fix, dead code removal, regex pre-compilation.

**Files:**
- Delete: `src/story_video/ffmpeg/transitions.py`
- Modify: `src/story_video/state.py:417-419`
- Modify: `src/story_video/utils/retry.py:33, 92-109`
- Modify: `tests/test_retry.py:13, 263-301, 334-341`
- Modify: `src/story_video/utils/text.py:495` + add module-level pattern

**Step 1: Delete dead file (PR-13)**

Delete `src/story_video/ffmpeg/transitions.py`. It's empty (0 lines) and nothing imports from it. Transition logic was merged into `commands.py`.

**Step 2: Fix stale docstring (PR-17)**

In `src/story_video/state.py`, change lines 417-419 from:

```python
For phases with no per-scene asset (ANALYSIS, STORY_BIBLE, OUTLINE,
IMAGE_PROMPTS), returns an empty list — those phases don't operate
on individual scene assets.
```

to:

```python
For phases with no per-scene asset (ANALYSIS, STORY_BIBLE, OUTLINE),
returns an empty list — those phases don't operate on individual
scene assets.
```

`IMAGE_PROMPTS` maps to `AssetType.IMAGE_PROMPT` in `PHASE_ASSET_MAP` and DOES have per-scene assets.

**Step 3: Remove unused `api_retry` (PR-19)**

In `src/story_video/utils/retry.py`:

1. Remove `"api_retry"` from `__all__` (line 33). New value:
   ```python
   __all__ = ["OPENAI_TRANSIENT_ERRORS", "RetryError", "with_retry"]
   ```

2. Delete the entire `api_retry` function (lines 92-109).

3. Remove `api_retry` from the docstring example (lines 8, 14-15). Update the module docstring to:
   ```python
   """Retry decorators with exponential backoff using tenacity.

   Provides thin wrappers around tenacity for retrying API calls (Claude, OpenAI TTS,
   image generation, Whisper) with configurable exponential backoff. On failure, retries with
   increasing delays capped at 60 seconds.

   Usage:
       from story_video.utils.retry import with_retry, RetryError

       @with_retry(max_retries=3, base_delay=2.0, retry_on=(ConnectionError,))
       def call_api():
           ...
   """
   ```

In `tests/test_retry.py`:

1. Remove `api_retry` from the import (line 13). New import:
   ```python
   from story_video.utils.retry import with_retry
   ```

2. Delete the entire `TestApiRetry` class (lines 262-301).

3. Delete `test_api_retry_preserves_name` from `TestWithRetryMetadata` (lines 334-341).

**Step 4: Pre-compile inline regex (PR-21)**

In `src/story_video/utils/text.py`:

1. Add module-level pattern near the other patterns (around line 456):
   ```python
   _DOUBLE_SPACE_PATTERN = re.compile(r"  +")
   ```

2. Replace line 495:
   ```python
   result = re.sub(r"  +", " ", result)
   ```
   with:
   ```python
   result = _DOUBLE_SPACE_PATTERN.sub(" ", result)
   ```

**Step 5: Run tests**

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add -u && git add src/story_video/ffmpeg/transitions.py
git commit -m "chore: trivial housekeeping — delete dead file, fix docstring, remove unused api_retry, pre-compile regex (PR-13, PR-17, PR-19, PR-21)"
```

Note: use `git rm` for the deleted file if `git add -u` doesn't pick it up.

---

## Task 2: Hex color validation (PR-14, PR-16)

Add hex format validation at both the model level (SubtitleConfig) and the function level (_hex_to_ass_color). PR-16 prevents invalid values from entering the system; PR-14 provides defense-in-depth at the point of use.

**Files:**
- Modify: `src/story_video/models.py:378-379`
- Modify: `src/story_video/ffmpeg/subtitles.py:26-41`
- Modify: `tests/test_models.py`
- Modify: `tests/test_subtitles.py`

**Step 1: Write failing tests**

In `tests/test_models.py`, add:

```python
class TestSubtitleConfigColorValidation:
    """SubtitleConfig rejects invalid hex color formats."""

    def test_rejects_named_color(self):
        """Named colors like 'red' are not valid."""
        with pytest.raises(ValidationError):
            SubtitleConfig(color="red")

    def test_rejects_short_hex(self):
        """Three-digit hex like '#FFF' is not valid."""
        with pytest.raises(ValidationError):
            SubtitleConfig(color="#FFF")

    def test_rejects_outline_named_color(self):
        """outline_color also validates."""
        with pytest.raises(ValidationError):
            SubtitleConfig(outline_color="blue")

    def test_accepts_valid_uppercase_hex(self):
        """Standard #RRGGBB format passes."""
        config = SubtitleConfig(color="#FF0000")
        assert config.color == "#FF0000"

    def test_accepts_valid_lowercase_hex(self):
        """Lowercase hex passes."""
        config = SubtitleConfig(color="#ff0000")
        assert config.color == "#ff0000"
```

Ensure `SubtitleConfig` and `ValidationError` are imported. `ValidationError` comes from `pydantic`.

In `tests/test_subtitles.py`, add:

```python
class TestHexToAssColorValidation:
    """_hex_to_ass_color rejects malformed hex input."""

    def test_rejects_short_hex(self):
        """Three-digit hex is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("#FFF")

    def test_rejects_non_hex_characters(self):
        """Non-hex characters are rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("#GGGGGG")

    def test_rejects_missing_hash(self):
        """Missing '#' prefix is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("FFFFFF")

    def test_rejects_empty_string(self):
        """Empty string is rejected."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            _hex_to_ass_color("")
```

Ensure `_hex_to_ass_color` is imported. Check the existing test file imports — it may already import this function for existing tests.

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_models.py::TestSubtitleConfigColorValidation tests/test_subtitles.py::TestHexToAssColorValidation -v`
Expected: FAIL (no validators yet)

**Step 3: Implement validators**

In `src/story_video/models.py`, add a field validator to `SubtitleConfig` (after line 383):

```python
    @field_validator("color", "outline_color")
    @classmethod
    def _validate_hex_color(cls, v: str) -> str:
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            msg = f"Invalid hex color: {v!r} (expected #RRGGBB format)"
            raise ValueError(msg)
        return v
```

In `src/story_video/ffmpeg/subtitles.py`, add validation at the top of `_hex_to_ass_color` (after the docstring, before `hex_color = hex_color.lstrip("#")`):

```python
import re

# Add near top of file, with other module-level constants
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
```

Then in the function body, before `hex_color = hex_color.lstrip("#")`:

```python
    if not _HEX_COLOR_RE.match(hex_color):
        msg = f"Invalid hex color format: {hex_color!r} (expected #RRGGBB)"
        raise ValueError(msg)
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_models.py::TestSubtitleConfigColorValidation tests/test_subtitles.py::TestHexToAssColorValidation -v`
Expected: All PASS

**Step 5: Run full suite**

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/story_video/models.py src/story_video/ffmpeg/subtitles.py tests/test_models.py tests/test_subtitles.py
git commit -m "fix: add hex color validation to SubtitleConfig and _hex_to_ass_color (PR-14, PR-16)"
```

---

## Task 3: Scene word count cross-validation (PR-15)

Add `@model_validator` to `StoryConfig` enforcing `scene_word_min <= scene_word_target <= scene_word_max`.

**Files:**
- Modify: `src/story_video/models.py:178-198`
- Modify: `tests/test_models.py`

**Step 1: Write failing tests**

In `tests/test_models.py`, add:

```python
class TestStoryConfigWordCountValidation:
    """StoryConfig enforces min <= target <= max for scene word counts."""

    def test_min_exceeds_max_raises(self):
        """scene_word_min > scene_word_max is rejected."""
        with pytest.raises(ValidationError):
            StoryConfig(scene_word_min=3000, scene_word_max=500)

    def test_target_exceeds_max_raises(self):
        """scene_word_target > scene_word_max is rejected."""
        with pytest.raises(ValidationError):
            StoryConfig(scene_word_target=4000, scene_word_max=3000)

    def test_target_below_min_raises(self):
        """scene_word_target < scene_word_min is rejected."""
        with pytest.raises(ValidationError):
            StoryConfig(scene_word_target=100, scene_word_min=500)

    def test_valid_bounds_accepted(self):
        """Valid ordering passes validation."""
        config = StoryConfig(scene_word_min=500, scene_word_target=1800, scene_word_max=3000)
        assert config.scene_word_min == 500
        assert config.scene_word_target == 1800
        assert config.scene_word_max == 3000

    def test_equal_bounds_accepted(self):
        """All three values equal is valid."""
        config = StoryConfig(scene_word_min=1000, scene_word_target=1000, scene_word_max=1000)
        assert config.scene_word_target == 1000
```

Ensure `StoryConfig` and `ValidationError` are imported.

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_models.py::TestStoryConfigWordCountValidation -v`
Expected: FAIL (no validator yet)

**Step 3: Implement validator**

In `src/story_video/models.py`, add a model validator to `StoryConfig` after line 197 (after `scene_word_max` field):

```python
    @model_validator(mode="after")
    def _validate_word_count_bounds(self) -> "StoryConfig":
        if self.scene_word_min > self.scene_word_max:
            msg = (
                f"scene_word_min ({self.scene_word_min}) must not exceed "
                f"scene_word_max ({self.scene_word_max})"
            )
            raise ValueError(msg)
        if self.scene_word_target < self.scene_word_min:
            msg = (
                f"scene_word_target ({self.scene_word_target}) must not be below "
                f"scene_word_min ({self.scene_word_min})"
            )
            raise ValueError(msg)
        if self.scene_word_target > self.scene_word_max:
            msg = (
                f"scene_word_target ({self.scene_word_target}) must not exceed "
                f"scene_word_max ({self.scene_word_max})"
            )
            raise ValueError(msg)
        return self
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_models.py::TestStoryConfigWordCountValidation -v`
Expected: All PASS

**Step 5: Run full suite**

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/story_video/models.py tests/test_models.py
git commit -m "fix: add cross-field validation for scene word count bounds (PR-15)"
```

---

## Task 4: CLI estimate fix and retry default (PR-18, PR-20)

Remove the misleading `--voice` option from the `estimate` command (voice has no effect on cost). Narrow the `with_retry` default by making `retry_on` a required parameter.

**Files:**
- Modify: `src/story_video/cli.py:405, 426-427`
- Modify: `tests/test_cli.py:501-505`
- Modify: `src/story_video/utils/retry.py:40-43, 57-58`

**Step 1: Write failing tests**

In `tests/test_cli.py`, replace `test_estimate_with_voice_override` (lines 501-505) with:

```python
    def test_estimate_rejects_voice_option(self):
        """--voice is not a valid option on estimate."""
        result = runner.invoke(app, ["estimate", "--mode", "adapt", "--voice", "nova"])
        assert result.exit_code != 0
```

No new test needed for PR-20 — removing the default means `with_retry()` (no args) raises `TypeError` at call time. Since `api_retry` (the only caller using defaults) was already removed in Task 1, all callers already specify `retry_on` explicitly. The existing tests for those callers cover this.

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py::TestEstimateCommand::test_estimate_rejects_voice_option -v`
Expected: FAIL (--voice is still accepted)

**Step 3: Implement changes**

In `src/story_video/cli.py`:

1. Remove the `voice` parameter from the `estimate` function signature (line 405):
   Delete: `voice: str | None = typer.Option(None, help="TTS voice name (affects cost)"),`

2. Remove the voice override block (lines 426-427):
   Delete:
   ```python
   if voice is not None:
       cli_overrides["tts.voice"] = voice
   ```

In `src/story_video/utils/retry.py`:

1. Remove the default from `retry_on` parameter (line 43). Change:
   ```python
   retry_on: tuple[type[Exception], ...] = (Exception,),
   ```
   to:
   ```python
   retry_on: tuple[type[Exception], ...],
   ```

2. Update the docstring (line 57-58) to remove "Defaults to (Exception,)":
   ```python
       retry_on: Tuple of exception types to retry on.
   ```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py::TestEstimateCommand tests/test_retry.py -v`
Expected: All PASS

**Step 5: Run full suite**

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/story_video/cli.py src/story_video/utils/retry.py tests/test_cli.py
git commit -m "fix: remove misleading --voice from estimate, make retry_on required (PR-18, PR-20)"
```

---

## Task 5: Logging setup (PR-22, PR-23)

Add `logging.getLogger(__name__)` to the three modules missing it, then add a `--verbose` flag to the CLI for log configuration.

**Files:**
- Modify: `src/story_video/pipeline/image_generator.py`
- Modify: `src/story_video/pipeline/video_assembler.py`
- Modify: `src/story_video/pipeline/caption_generator.py`
- Modify: `src/story_video/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Add loggers to three modules (PR-22)**

In each of the three files, add `import logging` (if not already present) and `logger = logging.getLogger(__name__)` after the imports, matching the convention in `tts_generator.py`, `orchestrator.py`, and `story_writer.py`.

For `src/story_video/pipeline/image_generator.py`:
```python
import logging
# ... other imports ...

logger = logging.getLogger(__name__)
```

For `src/story_video/pipeline/video_assembler.py`:
```python
import logging
# ... other imports ...

logger = logging.getLogger(__name__)
```

For `src/story_video/pipeline/caption_generator.py`:
```python
import logging
# ... other imports ...

logger = logging.getLogger(__name__)
```

Place `import logging` alphabetically among imports. Place `logger = ...` after the `__all__` declaration (if present) or after all imports, matching the pattern in sibling modules.

**Step 2: Write failing test for --verbose (PR-23)**

In `tests/test_cli.py`, add:

```python
class TestVerboseFlag:
    """--verbose flag configures logging level."""

    def test_verbose_flag_accepted(self):
        """--verbose is a valid global option."""
        result = runner.invoke(app, ["--verbose", "estimate", "--mode", "adapt"])
        assert result.exit_code == 0

    def test_short_verbose_flag_accepted(self):
        """-v is a valid shorthand for --verbose."""
        result = runner.invoke(app, ["-v", "estimate", "--mode", "adapt"])
        assert result.exit_code == 0
```

**Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py::TestVerboseFlag -v`
Expected: FAIL (--verbose not recognized)

**Step 4: Implement --verbose flag**

In `src/story_video/cli.py`, add a callback to the app (after the `app = typer.Typer(...)` definition, around line 30):

```python
@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Generate narrated story videos for YouTube."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s: %(message)s",
    )
```

When adding the callback, remove the `help` parameter from `typer.Typer(...)` since the callback's docstring replaces it:

```python
app = typer.Typer(
    name="story-video",
    no_args_is_help=True,
)
```

**Step 5: Run tests**

Run: `python3 -m pytest tests/test_cli.py::TestVerboseFlag -v`
Expected: All PASS

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/story_video/pipeline/image_generator.py src/story_video/pipeline/video_assembler.py src/story_video/pipeline/caption_generator.py src/story_video/cli.py tests/test_cli.py
git commit -m "chore: add missing loggers and CLI --verbose flag (PR-22, PR-23)"
```

---

## Task 6: Test gaps (PR-24)

Add tests for the gaps identified in the project review. Items already covered (per exploration): `_apply_dotted_overrides` error path (tested), `subtitle_filter` special chars (tested), `probe_duration` non-numeric (tested). Remaining gaps: 6.

**Files:**
- Modify: `tests/test_story_writer.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_narration_tags.py`
- Modify: `tests/test_commands.py`

**Step 1: Write tests for `_check_preservation` edge cases**

In `tests/test_story_writer.py`, add:

```python
class TestCheckPreservationEdgeCases:
    """_check_preservation handles edge-case inputs."""

    def test_empty_original_and_scenes(self):
        """Empty original text with no scenes passes."""
        _check_preservation("", [])

    def test_whitespace_only_original(self):
        """Whitespace-only original with no scenes passes."""
        _check_preservation("   \n\t  ", [])
```

Ensure `_check_preservation` is imported from `story_video.pipeline.story_writer`.

**Step 2: Write tests for `_strip_narration_tags`**

In `tests/test_story_writer.py`, add:

```python
class TestStripNarrationTags:
    """_strip_narration_tags removes inline voice/mood markers."""

    def test_strips_voice_tag(self):
        """Voice tags are removed."""
        result = _strip_narration_tags("**voice:Alice** Hello world")
        assert result == "Hello world"

    def test_strips_mood_tag(self):
        """Mood tags are removed."""
        result = _strip_narration_tags("**mood:cheerful** Good morning")
        assert result == "Good morning"

    def test_strips_multiple_tags(self):
        """Multiple tags in one string are all removed."""
        result = _strip_narration_tags("**voice:Bob** **mood:sad** Goodbye")
        assert result == "Goodbye"

    def test_no_tags_unchanged(self):
        """Text without tags passes through unchanged."""
        result = _strip_narration_tags("Plain text here")
        assert result == "Plain text here"
```

Ensure `_strip_narration_tags` is imported from `story_video.pipeline.story_writer`.

**Step 3: Write tests for `TTSConfig.file_extension`**

In `tests/test_models.py`, add:

```python
class TestTTSConfigFileExtension:
    """TTSConfig.file_extension extracts format prefix."""

    def test_mp3_format(self):
        """'mp3' returns 'mp3'."""
        config = TTSConfig(output_format="mp3")
        assert config.file_extension == "mp3"

    def test_opus_format(self):
        """'opus' returns 'opus'."""
        config = TTSConfig(output_format="opus")
        assert config.file_extension == "opus"

    def test_elevenlabs_compound_format(self):
        """'mp3_44100_128' returns 'mp3'."""
        config = TTSConfig(output_format="mp3_44100_128")
        assert config.file_extension == "mp3"
```

Ensure `TTSConfig` is imported.

**Step 4: Write test for `parse_narration_segments` empty input**

In `tests/test_narration_tags.py`, add:

```python
class TestParseNarrationSegmentsEdgeCases:
    """parse_narration_segments handles edge-case inputs."""

    def test_empty_string_returns_empty(self):
        """Empty string produces no segments."""
        result = parse_narration_segments("")
        assert result == []
```

Ensure `parse_narration_segments` is imported from `story_video.utils.narration_tags`.

**Step 5: Write tests for `build_concat_command` short duration**

In `tests/test_commands.py`, add:

```python
class TestBuildConcatCommandShortDuration:
    """build_concat_command handles segments shorter than xfade duration."""

    def test_zero_duration_segment(self):
        """Zero-duration segment in multi-segment concat."""
        from story_video.models import VideoConfig

        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [0.0, 5.0]
        config = VideoConfig()
        # Should not raise — xfade logic must handle gracefully
        cmd = build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert isinstance(cmd, list)

    def test_very_short_duration_segment(self):
        """Segment shorter than xfade transition duration."""
        from story_video.models import VideoConfig

        paths = [Path("/a.mp4"), Path("/b.mp4")]
        durations = [0.5, 5.0]  # 0.5s < typical 1.5s xfade
        config = VideoConfig()
        cmd = build_concat_command(paths, durations, Path("/out.mp4"), config)
        assert isinstance(cmd, list)
```

Ensure `build_concat_command` and `Path` are imported.

**Step 6: Run all new tests**

Run: `python3 -m pytest tests/test_story_writer.py::TestCheckPreservationEdgeCases tests/test_story_writer.py::TestStripNarrationTags tests/test_models.py::TestTTSConfigFileExtension tests/test_narration_tags.py::TestParseNarrationSegmentsEdgeCases tests/test_commands.py::TestBuildConcatCommandShortDuration -v`

Expected: All PASS (these test existing, working code)

If any FAIL: The failure reveals an actual bug. Fix the underlying code and re-run.

**Step 7: Run full suite**

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 8: Commit**

```bash
git add tests/test_story_writer.py tests/test_models.py tests/test_narration_tags.py tests/test_commands.py
git commit -m "test: fill test gaps for preservation, narration tags, file extension, concat duration (PR-24)"
```

---

## Task 7: Multi-assertion test splits (PR-25)

Split tests with multiple independent assertions into focused single-assertion tests. Only split where assertions test genuinely independent behaviors — leave multi-assert tests alone when they test one logical concept.

**Files:**
- Modify: `tests/test_caption_generator.py`
- Modify: `tests/test_image_generator.py`
- Modify: `tests/test_tts_generator.py`

**Approach:** For each composite test, replace it with N focused tests. Each new test name describes exactly what it verifies. The test setup (fixture/mock) may be duplicated — that's fine, clarity over DRY in tests.

**Step 1: Split tests in `test_caption_generator.py`**

Replace `test_writes_caption_json` (which checks file exists + 5 content assertions) with:

```python
    def test_writes_caption_json_creates_file(self, ...):
        """Caption JSON file is created on disk."""
        # ... setup ...
        assert caption_path.exists()

    def test_writes_caption_json_language(self, ...):
        """Caption JSON contains correct language."""
        # ... setup ...
        assert content["language"] == "en"

    def test_writes_caption_json_duration(self, ...):
        """Caption JSON contains correct duration."""
        # ... setup ...
        assert content["duration"] == 2.5

    def test_writes_caption_json_segments(self, ...):
        """Caption JSON contains expected segments."""
        # ... setup ...
        assert len(content["segments"]) == 1
        assert content["segments"][0]["text"] == "The storm raged on."

    def test_writes_caption_json_words(self, ...):
        """Caption JSON contains expected words."""
        # ... setup ...
        assert len(content["words"]) == 4
        assert content["words"][0]["word"] == "The"
```

Replace `test_round_trip_serialization` (5 assertions) with:

```python
    def test_round_trip_preserves_equality(self, ...):
        """Round-trip serialization produces equal object."""
        assert restored == original

    def test_round_trip_preserves_segment_text(self, ...):
        """Round-trip preserves segment text."""
        assert restored.segments[0].text == "The storm raged on."

    def test_round_trip_preserves_word(self, ...):
        """Round-trip preserves word entries."""
        assert restored.words[0].word == "The"

    def test_round_trip_preserves_language(self, ...):
        """Round-trip preserves language."""
        assert restored.language == "en"

    def test_round_trip_preserves_duration(self, ...):
        """Round-trip preserves duration."""
        assert restored.duration == 2.5
```

**Step 2: Split tests in `test_image_generator.py`**

Replace `test_generate_image_writes_file_and_updates_state` (3 assertions) with:

```python
    def test_generate_image_creates_file(self, ...):
        """Image file is created on disk."""
        assert image_path.exists()

    def test_generate_image_writes_correct_bytes(self, ...):
        """Image file contains provider output bytes."""
        assert image_path.read_bytes() == FAKE_PNG

    def test_generate_image_updates_state(self, ...):
        """Asset status transitions to COMPLETED."""
        assert scene.asset_status.image == SceneStatus.COMPLETED
```

Replace `test_generate_image_passes_config_to_provider` (3 assertions) with:

```python
    def test_generate_image_passes_size(self, ...):
        """Provider receives configured image size."""
        assert call_kwargs["size"] == "1536x1024"

    def test_generate_image_passes_quality(self, ...):
        """Provider receives configured quality."""
        assert call_kwargs["quality"] == "medium"

    def test_generate_image_passes_style(self, ...):
        """Provider receives style as None."""
        assert call_kwargs["style"] is None
```

**Step 3: Split tests in `test_tts_generator.py`**

Replace `test_generate_audio_writes_file_and_updates_state` (3 assertions) with:

```python
    def test_generate_audio_creates_file(self, ...):
        """Audio file is created on disk."""
        assert audio_path.exists()

    def test_generate_audio_writes_correct_bytes(self, ...):
        """Audio file contains provider output bytes."""
        assert audio_path.read_bytes() == b"fake-audio-bytes"

    def test_generate_audio_updates_state(self, ...):
        """Asset status transitions to COMPLETED."""
        assert scene.asset_status.audio == SceneStatus.COMPLETED
```

**Important notes for the implementer:**
- Read each composite test first to understand its full setup
- Each split test needs the complete setup (fixture args, mock configuration, state creation)
- Use a shared helper or duplicate the setup — prefer clarity over DRY
- Run the full suite after each file to catch regressions early
- The total test count will increase (composite tests become N tests each)

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_caption_generator.py tests/test_image_generator.py tests/test_tts_generator.py -v`
Expected: All PASS (same behavior, more tests)

**Step 5: Run full suite**

Run: `python3 -m pytest -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add tests/test_caption_generator.py tests/test_image_generator.py tests/test_tts_generator.py
git commit -m "test: split multi-assertion tests into focused single-assertion tests (PR-25)"
```

---

## Task 8: Backlog update

Mark all 13 items as resolved in `BUGS_AND_TODOS.md`.

**Files:**
- Modify: `BUGS_AND_TODOS.md`

**Step 1: Mark items resolved**

In `BUGS_AND_TODOS.md`:

1. Change all 13 items (PR-13 through PR-25) from `- [ ]` to `- [x]` in the Low priority section.

2. Add all 13 items to the Resolved section with brief descriptions:

```markdown
- [x] [chore] Delete dead file `ffmpeg/transitions.py` (PR-13)
- [x] [bug] `_hex_to_ass_color` input validation — reject malformed hex (PR-14)
- [x] [bug] Cross-field validation on scene word count bounds — `@model_validator` (PR-15)
- [x] [bug] `SubtitleConfig.color` and `outline_color` hex format validation (PR-16)
- [x] [docs] Fix stale docstring in `state.py` — remove IMAGE_PROMPTS from no-asset list (PR-17)
- [x] [bug] Remove misleading `--voice` option from `estimate` command (PR-18)
- [x] [chore] Remove unused `api_retry` export and function (PR-19)
- [x] [bug] Make `with_retry` `retry_on` parameter required (PR-20)
- [x] [chore] Pre-compile inline regex in `text.py` (PR-21)
- [x] [chore] Add `logging.getLogger(__name__)` to 3 pipeline modules (PR-22)
- [x] [chore] Add `--verbose` flag to CLI for logging configuration (PR-23)
- [x] [test] Fill test gaps — preservation, narration tags, file extension, concat duration (PR-24)
- [x] [test] Split multi-assertion tests into focused single-assertion tests (PR-25)
```

**Step 2: Commit**

```bash
git add BUGS_AND_TODOS.md
git commit -m "docs: mark PR-13 through PR-25 as resolved"
```
