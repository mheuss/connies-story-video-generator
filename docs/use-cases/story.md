# Story Use-Cases

## Text Preservation Validation After LLM Splitting

**Problem:** After an LLM splits text into segments, need to verify no words were added, removed, or changed.

**Problem indicators:**
- "verify LLM preserved original text"
- "concatenated output doesn't match input"
- "whitespace differences after text splitting"
- "word-for-word preservation check"

**Location:** `src/story_video/pipeline/story_writer.py:_check_preservation`

**Notes:** Normalizes whitespace with `" ".join(text.split())` before comparison, which collapses newlines, tabs, and multiple spaces to single spaces. This is necessary because the LLM may insert different paragraph breaks at scene boundaries while preserving all words. The error message includes the position and surrounding context of the first mismatch for debugging. Called by `split_scenes()` in adapt mode, where verbatim narration is promised.

## Autonomous Content Fix Application

**Problem:** Need to apply LLM-suggested text fixes automatically without human review, with graceful handling of mismatches.

**Problem indicators:**
- "apply suggested fixes autonomously"
- "how to handle fix that doesn't match original"
- "sequential text replacements on same content"
- "autonomous vs manual review mode"

**Location:** `src/story_video/pipeline/story_writer.py:flag_narration`

**Notes:** Controlled by `config.pipeline.autonomous` flag. In autonomous mode, copies `scene.prose` to `scene.narration_text` (if not already set) then applies `str.replace()` sequentially for each flag. Logs a warning when `original_text` is not found in the scene (Claude quoted text imprecisely). `str.replace()` affects all occurrences — acceptable because flagged patterns are typically unique within a scene. In semi-auto mode, writes flags file only for human review.
