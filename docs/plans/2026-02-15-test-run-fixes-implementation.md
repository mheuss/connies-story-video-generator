# Test Run Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix four issues discovered during the first end-to-end test run: jerky Ken Burns motion, missing caption punctuation, short story scene count, and wrong success message path.

**Architecture:** Each fix is independent — no shared interfaces or type changes between fixes (except Task 1 which adds `ken_burns_enabled` to `VideoConfig`). All fixes follow the existing provider/filter/pipeline patterns. TDD throughout.

**Tech Stack:** Python, Pydantic, FFmpeg zoompan expressions, Whisper CaptionResult model, pytest

**Status:** Complete

---

### Task 1: Smooth Ken Burns Motion with Sine Easing

**Files:**
- Modify: `src/story_video/models.py:245-277` (VideoConfig)
- Modify: `src/story_video/ffmpeg/filters.py:14-81` (ken_burns_filter)
- Modify: `src/story_video/pipeline/video_assembler.py:29-97` (assemble_scene)
- Modify: `src/story_video/ffmpeg/commands.py:67-149` (build_segment_command)
- Test: `tests/test_filters.py`
- Test: `tests/test_video_assembler.py`
- Test: `tests/test_commands.py`

**Step 1: Write failing tests for eased expressions**

Add a new test class to `tests/test_filters.py`:

```python
class TestKenBurnsEasing:
    """Ken Burns uses sine-based easing instead of linear interpolation."""

    def test_zoom_in_uses_cosine_easing(self):
        """Direction 0 zoom expression contains cos() for easing."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=0, resolution="1920x1080")
        assert "cos(" in result

    def test_pan_left_position_uses_cosine_easing(self):
        """Direction 2 x expression contains cos() for eased drift."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=2, resolution="1920x1080")
        assert "cos(" in result

    def test_pan_right_position_uses_cosine_easing(self):
        """Direction 3 x expression contains cos() for eased drift."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=3, resolution="1920x1080")
        assert "cos(" in result

    def test_diagonal_both_axes_use_cosine_easing(self):
        """Direction 4 both x and y expressions contain cos() for easing."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=4, resolution="1920x1080")
        # Count cos occurrences — should appear in both x and y expressions
        assert result.count("cos(") >= 2

    def test_zoom_out_uses_cosine_easing(self):
        """Direction 1 zoom expression contains cos() for easing."""
        result = ken_burns_filter(duration=5.0, zoom=1.3, direction=1, resolution="1920x1080")
        assert "cos(" in result
```

Add a test for `ken_burns_enabled` config toggle in `tests/test_filters.py` or `tests/test_video_assembler.py`:

```python
class TestKenBurnsConfigToggle:
    """VideoConfig.ken_burns_enabled controls whether Ken Burns is applied."""

    def test_ken_burns_enabled_default_true(self):
        """ken_burns_enabled defaults to True."""
        from story_video.models import VideoConfig
        config = VideoConfig()
        assert config.ken_burns_enabled is True

    def test_ken_burns_disabled(self):
        """ken_burns_enabled can be set to False."""
        from story_video.models import VideoConfig
        config = VideoConfig(ken_burns_enabled=False)
        assert config.ken_burns_enabled is False
```

Add a test for the `build_segment_command` still-image fallback in `tests/test_commands.py`:

```python
class TestBuildSegmentCommandKenBurnsToggle:
    """build_segment_command respects ken_burns_enabled toggle."""

    def test_ken_burns_disabled_no_zoompan(self):
        """When ken_burns_enabled=False, filtergraph has no zoompan."""
        from story_video.models import VideoConfig
        config = VideoConfig(ken_burns_enabled=False)
        cmd = build_segment_command(
            image_path=Path("/tmp/img.png"),
            audio_path=Path("/tmp/audio.mp3"),
            ass_path=Path("/tmp/sub.ass"),
            output_path=Path("/tmp/out.mp4"),
            duration=5.0,
            scene_number=1,
            video_config=config,
        )
        filtergraph = cmd[cmd.index("-filter_complex") + 1]
        assert "zoompan" not in filtergraph

    def test_ken_burns_enabled_has_zoompan(self):
        """When ken_burns_enabled=True (default), filtergraph has zoompan."""
        from story_video.models import VideoConfig
        config = VideoConfig()
        cmd = build_segment_command(
            image_path=Path("/tmp/img.png"),
            audio_path=Path("/tmp/audio.mp3"),
            ass_path=Path("/tmp/sub.ass"),
            output_path=Path("/tmp/out.mp4"),
            duration=5.0,
            scene_number=1,
            video_config=config,
        )
        filtergraph = cmd[cmd.index("-filter_complex") + 1]
        assert "zoompan" in filtergraph
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_filters.py::TestKenBurnsEasing -v`
Expected: FAIL — `cos(` not found in expressions (current code uses linear `on/`)

Run: `pytest tests/test_filters.py::TestKenBurnsConfigToggle -v`
Expected: FAIL — `ken_burns_enabled` attribute does not exist

Run: `pytest tests/test_commands.py::TestBuildSegmentCommandKenBurnsToggle -v`
Expected: FAIL — zoompan still present when disabled

**Step 3: Add `ken_burns_enabled` to VideoConfig**

In `src/story_video/models.py`, add to `VideoConfig` after `ken_burns_zoom`:

```python
ken_burns_enabled: bool = Field(default=True)
```

Update the `VideoConfig` docstring Fields section to include:
```
ken_burns_enabled: Whether to apply Ken Burns zoom/pan effect (False uses still image).
```

**Step 4: Replace linear expressions with sine easing in filters.py**

In `src/story_video/ffmpeg/filters.py`, replace the direction-specific expressions. The easing formula maps linear progress `on/{frames}` to eased progress `(1-cos(on/{frames}*PI))/2`:

```python
def ken_burns_filter(duration: float, zoom: float, direction: int, resolution: str) -> str:
    if direction < 0 or direction > 4:
        msg = f"direction must be 0-4, got {direction}"
        raise ValueError(msg)

    frames = int(duration * _ZOOMPAN_FPS)

    # Eased progress: sine ease-in-out maps linear 0→1 to smooth 0→1.
    # Uses (1-cos(t*PI))/2 where t = on/{frames}.
    ease = f"(1-cos(on/{frames}*PI))/2"

    if direction == 0:
        # Zoom in from center: zoom eases from 1.0 to target zoom
        z_expr = f"1.0+({zoom}-1.0)*{ease}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == 1:
        # Zoom out from center: zoom eases from target zoom to 1.0
        z_expr = f"{zoom}-({zoom}-1.0)*{ease}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == 2:
        # Pan left (right-to-left): slight zoom, x eases right-to-left
        slight_zoom = 1.0 + (zoom - 1.0) * 0.3
        z_expr = f"{slight_zoom}"
        x_expr = f"(iw-iw/zoom)*(1-{ease})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == 3:
        # Pan right (left-to-right): slight zoom, x eases left-to-right
        slight_zoom = 1.0 + (zoom - 1.0) * 0.3
        z_expr = f"{slight_zoom}"
        x_expr = f"(iw-iw/zoom)*{ease}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Diagonal drift: slight zoom, both axes ease
        slight_zoom = 1.0 + (zoom - 1.0) * 0.3
        z_expr = f"{slight_zoom}"
        x_expr = f"(iw-iw/zoom)*{ease}"
        y_expr = f"(ih-ih/zoom)*{ease}"

    return (
        f"zoompan=z='{z_expr}'"
        f":x='{x_expr}'"
        f":y='{y_expr}'"
        f":d={frames}"
        f":s={resolution}"
        f":fps={_ZOOMPAN_FPS}"
    )
```

**Step 5: Add still-image fallback in build_segment_command**

In `src/story_video/ffmpeg/commands.py`, modify `build_segment_command` to check `video_config.ken_burns_enabled`. When disabled, use a simple scale+pad filter instead of zoompan:

```python
if video_config.ken_burns_enabled:
    kb_filter = ken_burns_filter(
        duration=duration,
        zoom=video_config.ken_burns_zoom,
        direction=direction,
        resolution=video_config.resolution,
    )
    filtergraph = (
        f"[0:v]{bg_filter}[bg];"
        f"[0:v]{kb_filter}[kb];"
        f"[bg][kb]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]{sub_filter}[out]"
    )
else:
    # Still image: scale to fit within resolution, pad to exact size
    w, h = video_config.resolution.split("x")
    still_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
    filtergraph = (
        f"[0:v]{bg_filter}[bg];"
        f"[0:v]{still_filter}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]{sub_filter}[out]"
    )
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_filters.py tests/test_commands.py tests/test_video_assembler.py -v`
Expected: ALL PASS

**Step 7: Run full test suite**

Run: `pytest`
Expected: ALL PASS (680+ tests)

**Step 8: Commit**

```bash
git add src/story_video/models.py src/story_video/ffmpeg/filters.py src/story_video/ffmpeg/commands.py tests/test_filters.py tests/test_commands.py
git commit -m "fix(video): replace linear Ken Burns motion with sine easing

Smooth zoom/pan motion using (1-cos(t*PI))/2 ease-in-out curve.
Add ken_burns_enabled config toggle with still-image fallback."
```

---

### Task 2: Reconcile Caption Punctuation from Segments

**Files:**
- Modify: `src/story_video/pipeline/caption_generator.py` — add `_reconcile_punctuation()`, call before JSON write
- Test: `tests/test_caption_generator.py`

**Step 1: Write failing tests for punctuation reconciliation**

Add to `tests/test_caption_generator.py`:

```python
from story_video.pipeline.caption_generator import _reconcile_punctuation


class TestReconcilePunctuation:
    """_reconcile_punctuation restores punctuation from segments to words."""

    def test_appends_period_to_final_word(self):
        """Period from segment text is appended to matching word."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The storm raged on.", start=0.0, end=2.5)],
            words=[
                CaptionWord(word="The", start=0.0, end=0.3),
                CaptionWord(word="storm", start=0.4, end=0.8),
                CaptionWord(word="raged", start=0.9, end=1.4),
                CaptionWord(word="on", start=1.5, end=2.5),
            ],
            language="en",
            duration=2.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[3].word == "on."

    def test_appends_comma(self):
        """Comma from segment text is appended to matching word."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello, world.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="Hello", start=0.0, end=0.5),
                CaptionWord(word="world", start=0.6, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Hello,"
        assert reconciled.words[1].word == "world."

    def test_preserves_existing_punctuation(self):
        """Words that already have punctuation are left unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The storm raged on.", start=0.0, end=2.5)],
            words=[
                CaptionWord(word="The", start=0.0, end=0.3),
                CaptionWord(word="storm", start=0.4, end=0.8),
                CaptionWord(word="raged", start=0.9, end=1.4),
                CaptionWord(word="on.", start=1.5, end=2.5),
            ],
            language="en",
            duration=2.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[3].word == "on."

    def test_multiple_segments(self):
        """Punctuation reconciliation works across multiple segments."""
        result = CaptionResult(
            segments=[
                CaptionSegment(text="Hello, world.", start=0.0, end=1.5),
                CaptionSegment(text="How are you?", start=2.0, end=3.5),
            ],
            words=[
                CaptionWord(word="Hello", start=0.0, end=0.5),
                CaptionWord(word="world", start=0.6, end=1.5),
                CaptionWord(word="How", start=2.0, end=2.3),
                CaptionWord(word="are", start=2.4, end=2.7),
                CaptionWord(word="you", start=2.8, end=3.5),
            ],
            language="en",
            duration=3.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Hello,"
        assert reconciled.words[1].word == "world."
        assert reconciled.words[4].word == "you?"

    def test_unmatched_word_left_unchanged(self):
        """Words that can't be found in segment text stay unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="The storm.", start=0.0, end=1.5)],
            words=[
                CaptionWord(word="Da", start=0.0, end=0.5),
                CaptionWord(word="storm", start=0.6, end=1.5),
            ],
            language="en",
            duration=1.5,
        )
        reconciled = _reconcile_punctuation(result)
        # "Da" doesn't match "The" — left unchanged
        assert reconciled.words[0].word == "Da"

    def test_empty_words_returns_unchanged(self):
        """Empty word list returns the result unchanged."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Hello.", start=0.0, end=1.0)],
            words=[],
            language="en",
            duration=1.0,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words == []

    def test_exclamation_mark(self):
        """Exclamation mark from segment is appended."""
        result = CaptionResult(
            segments=[CaptionSegment(text="Run!", start=0.0, end=0.5)],
            words=[CaptionWord(word="Run", start=0.0, end=0.5)],
            language="en",
            duration=0.5,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[0].word == "Run!"

    def test_em_dash_and_quotes(self):
        """Non-alphanumeric trailing characters like em-dash are appended."""
        result = CaptionResult(
            segments=[CaptionSegment(text='She said, "hello" —', start=0.0, end=2.0)],
            words=[
                CaptionWord(word="She", start=0.0, end=0.3),
                CaptionWord(word="said", start=0.4, end=0.7),
                CaptionWord(word="hello", start=0.8, end=1.2),
            ],
            language="en",
            duration=2.0,
        )
        reconciled = _reconcile_punctuation(result)
        assert reconciled.words[1].word == 'said,'
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_caption_generator.py::TestReconcilePunctuation -v`
Expected: FAIL — `_reconcile_punctuation` does not exist

**Step 3: Implement `_reconcile_punctuation`**

Add to `src/story_video/pipeline/caption_generator.py`:

```python
import re

def _reconcile_punctuation(result: CaptionResult) -> CaptionResult:
    """Restore punctuation from segment text to word timestamps.

    Whisper word-level timestamps strip punctuation, but segment text
    preserves it. This function walks each segment's text with a cursor,
    matching words by position, and appends any trailing non-alphanumeric
    characters to the word.

    Fails gracefully — unmatched words are left unchanged.

    Args:
        result: CaptionResult with segments (punctuated) and words (bare).

    Returns:
        A new CaptionResult with punctuation restored on words.
    """
    if not result.words:
        return result

    # Build a list of (segment_start, segment_end, segment_text) for lookup
    new_words = list(result.words)

    for segment in result.segments:
        seg_text = segment.text.strip()
        cursor = 0

        for i, word in enumerate(new_words):
            # Only process words within this segment's time range
            if word.start < segment.start - 0.01 or word.start > segment.end + 0.01:
                continue

            # Strip any existing punctuation from the word for matching
            bare_word = word.word.rstrip(".,!?;:—\"'""''…-")
            if not bare_word:
                continue

            # Find the word in segment text starting from cursor
            pos = seg_text.find(bare_word, cursor)
            if pos == -1:
                # Try case-insensitive match
                pos = seg_text.lower().find(bare_word.lower(), cursor)
            if pos == -1:
                continue

            # Advance past the word
            end_of_word = pos + len(bare_word)

            # Grab trailing non-alphanumeric, non-space characters
            trailing = ""
            j = end_of_word
            while j < len(seg_text) and not seg_text[j].isalnum() and seg_text[j] != " ":
                trailing += seg_text[j]
                j += 1

            # Update word with punctuation if it doesn't already have it
            if trailing and not word.word.endswith(trailing):
                new_words[i] = CaptionWord(
                    word=bare_word + trailing,
                    start=word.start,
                    end=word.end,
                )

            # Advance cursor past matched content
            cursor = j

    return CaptionResult(
        segments=result.segments,
        words=new_words,
        language=result.language,
        duration=result.duration,
    )
```

**Step 4: Call `_reconcile_punctuation` before JSON serialization**

In `generate_captions()`, after `result = provider.transcribe(audio_path)`, add:

```python
result = _reconcile_punctuation(result)
```

**Step 5: Export `_reconcile_punctuation` for test access**

The function name starts with `_` (private), but tests import it directly. This is fine — it follows the existing pattern in the codebase (e.g., `_check_preservation` in story_writer.py is tested directly).

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_caption_generator.py -v`
Expected: ALL PASS

**Step 7: Run full test suite**

Run: `pytest`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/story_video/pipeline/caption_generator.py tests/test_caption_generator.py
git commit -m "fix(captions): reconcile punctuation from Whisper segments to words

Whisper word timestamps strip punctuation but segment text preserves it.
Add _reconcile_punctuation() post-processing that walks segment text
and appends trailing punctuation to matching words."
```

---

### Task 3: Fix Short Story Scene Count

**Files:**
- Modify: `src/story_video/pipeline/story_writer.py:22-32` (SCENE_SPLIT_SYSTEM)
- Modify: `src/story_video/pipeline/image_prompt_writer.py:21-31` (IMAGE_PROMPT_SYSTEM)
- Test: Prompt text changes — no new tests needed (validated by next end-to-end run). Existing tests still pass.

**Step 1: Update SCENE_SPLIT_SYSTEM prompt**

In `src/story_video/pipeline/story_writer.py`, add short-story guidance to `SCENE_SPLIT_SYSTEM`:

```python
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
```

**Step 2: Update IMAGE_PROMPT_SYSTEM prompt**

In `src/story_video/pipeline/image_prompt_writer.py`, add explicit scene number constraint to `IMAGE_PROMPT_SYSTEM`:

```python
IMAGE_PROMPT_SYSTEM = (
    "You are a visual director creating DALL-E image prompts for story scenes.\n\n"
    "For each scene, write a single detailed image prompt that captures the key "
    "visual moment. The prompt should be:\n"
    "- Visually specific: describe setting, lighting, composition, mood\n"
    "- Self-contained: include all character descriptions (DALL-E has no memory "
    "between images)\n"
    "- Cinematic: frame it like a movie still or painting\n"
    "- 1-3 sentences long\n\n"
    "Do NOT include text overlays, watermarks, or UI elements in prompts.\n\n"
    "IMPORTANT: Generate exactly one prompt per scene provided. Do not create"
    " prompts for scene numbers that are not in the input."
)
```

**Step 3: Run full test suite to confirm no regressions**

Run: `pytest`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/story_video/pipeline/story_writer.py src/story_video/pipeline/image_prompt_writer.py
git commit -m "fix(prompts): add short-story scene guidance and constrain image prompts

Short stories under 1000 words now get at least 2 scenes.
Image prompt writer explicitly constrained to provided scene numbers."
```

---

### Task 4: Fix Wrong Success Message Path

**Files:**
- Modify: `src/story_video/cli.py:151-159` (_display_outcome)
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

Add to `tests/test_cli.py`:

```python
class TestDisplayOutcomeSuccessPath:
    """_display_outcome success message points to final.mp4."""

    def test_success_message_contains_final_mp4(self, tmp_path):
        """Success panel mentions 'final.mp4' not 'video' directory."""
        from unittest.mock import patch
        from io import StringIO
        from story_video.models import AppConfig, InputMode, PhaseStatus
        from story_video.state import ProjectState

        state = ProjectState.create("test-proj", InputMode.ADAPT, AppConfig(), tmp_path)
        state.metadata.status = PhaseStatus.COMPLETED
        state.save()

        with patch("story_video.cli.console") as mock_console:
            _display_outcome(state)
            call_args = str(mock_console.print.call_args)
            assert "final.mp4" in call_args
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestDisplayOutcomeSuccessPath -v`
Expected: FAIL — message says "video" not "final.mp4"

**Step 3: Fix _display_outcome**

In `src/story_video/cli.py`, change the COMPLETED branch:

```python
if status == PhaseStatus.COMPLETED:
    video_path = state.project_dir / "final.mp4"
    console.print(
        Panel(
            f"Project complete! Video is at:\n{video_path}",
            title="Success",
            border_style="green",
        )
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `pytest`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/story_video/cli.py tests/test_cli.py
git commit -m "fix(cli): correct success message to point to final.mp4

_display_outcome was pointing to project_dir/video which is empty.
The actual output is project_dir/final.mp4."
```

---

## Retrospective

(To be filled after implementation)
