# Project Review High-Priority Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two high-severity issues found in the 2026-02-17 project review: ElevenLabs cost estimation crash (PR-1) and FFmpeg subtitle path injection (PR-2).

**Architecture:** Both fixes are surgical. PR-1 adds provider-aware TTS cost calculation that handles unknown models gracefully instead of crashing. PR-2 escapes special characters in file paths before interpolation into FFmpeg filter expressions.

**Tech Stack:** Python, Pydantic, pytest, FFmpeg filter syntax

**Status:** Complete

---

## Task 1: Handle unknown TTS models gracefully in cost estimation (PR-1)

**Files:**
- Modify: `src/story_video/cost.py:162-186` (`_calculate_tts_cost`)
- Modify: `src/story_video/cost.py:48-52` (`TTS_COST_PER_MILLION_CHARS`)
- Test: `tests/test_cost.py`

**Context:** The `_calculate_tts_cost` function raises `ValueError` for any model not in `TTS_COST_PER_MILLION_CHARS`. ElevenLabs models (e.g., `eleven_multilingual_v2`) are not in the table. The `estimate` CLI command passes `config.tts.model` directly, so ElevenLabs users get an unhandled crash.

The right fix: return a `ServiceCost` with `$0.00` and a description noting the model is not in the rate table. This is better than adding specific ElevenLabs pricing that will go stale, because ElevenLabs pricing is per-character with tiers that depend on the user's subscription plan.

**Step 1: Write the failing test — unknown TTS model returns zero-cost entry**

Replace the existing `test_unknown_tts_model_raises` test with a new behavior. Add a new test in the `TestTTSCost` class:

```python
# In tests/test_cost.py, class TestTTSCost

def test_unknown_tts_model_returns_zero_cost(self):
    """Unknown TTS model returns $0.00 with descriptive note instead of crashing."""
    config = _config(tts=TTSConfig(model="eleven_multilingual_v2"))
    est = estimate_cost(
        mode=InputMode.ORIGINAL,
        config=config,
        scene_count=25,
        character_count=247500,
    )
    tts = next(s for s in est.services if s.service == "TTS")
    assert tts.low == 0.0
    assert tts.high == 0.0
    assert "not estimated" in tts.description
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cost.py::TestTTSCost::test_unknown_tts_model_returns_zero_cost -v`
Expected: FAIL — `ValueError: Unknown TTS model: 'eleven_multilingual_v2'`

**Step 3: Update the existing raises test to match new behavior**

Delete the `test_unknown_tts_model_raises` test from `TestTTSCost` — it asserts the old crashing behavior we're removing.

**Step 4: Write minimal implementation — handle unknown models gracefully**

In `src/story_video/cost.py`, modify `_calculate_tts_cost`:

```python
def _calculate_tts_cost(tts_model: str, character_count: int) -> ServiceCost:
    """Calculate TTS cost.

    Formula: character_count / 1,000,000 * rate_per_million_chars

    For models not in the rate table (e.g., ElevenLabs models with
    subscription-dependent pricing), returns a zero-cost entry with
    a descriptive note instead of raising.

    Args:
        tts_model: TTS model identifier (e.g., "tts-1-hd").
        character_count: Total characters to synthesize.

    Returns:
        ServiceCost with the TTS cost (exact or zero if unknown).
    """
    if tts_model not in TTS_COST_PER_MILLION_CHARS:
        return ServiceCost(
            service="TTS",
            description=f"{tts_model} (not estimated — pricing not in rate table)",
            low=0.0,
            high=0.0,
        )

    rate = TTS_COST_PER_MILLION_CHARS[tts_model]
    cost = character_count / 1_000_000 * rate

    return ServiceCost(service="TTS", description=tts_model, low=cost, high=cost)
```

Note: The service name changes from `"OpenAI TTS"` to `"TTS"` since it's no longer OpenAI-specific. This affects existing tests that filter by `s.service == "OpenAI TTS"`.

**Wait — that's a bigger change.** Keep the service name as `"OpenAI TTS"` for known OpenAI models and use `"TTS"` only for unknown models. This avoids breaking existing tests and keeps the display accurate:

```python
def _calculate_tts_cost(tts_model: str, character_count: int) -> ServiceCost:
    """Calculate TTS cost.

    Formula: character_count / 1,000,000 * rate_per_million_chars

    For models not in the rate table (e.g., ElevenLabs models with
    subscription-dependent pricing), returns a zero-cost entry with
    a descriptive note instead of raising.

    Args:
        tts_model: TTS model identifier (e.g., "tts-1-hd").
        character_count: Total characters to synthesize.

    Returns:
        ServiceCost with the TTS cost (exact or zero if unknown).
    """
    if tts_model not in TTS_COST_PER_MILLION_CHARS:
        return ServiceCost(
            service="TTS",
            description=f"{tts_model} (not estimated — pricing not in rate table)",
            low=0.0,
            high=0.0,
        )

    rate = TTS_COST_PER_MILLION_CHARS[tts_model]
    cost = character_count / 1_000_000 * rate

    return ServiceCost(service="OpenAI TTS", description=tts_model, low=cost, high=cost)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_cost.py::TestTTSCost -v`
Expected: All TTS tests PASS

**Step 6: Fix downstream tests that depend on service name**

The `TestTotalCost::test_has_four_services` and `TestServiceOrder::test_services_in_expected_order` tests check for `"OpenAI TTS"` in the service names. These tests use `_config()` which defaults to `gpt-4o-mini-tts` (a known model), so they should still pass. Verify:

Run: `pytest tests/test_cost.py -v`
Expected: All tests PASS (the deleted `test_unknown_tts_model_raises` is gone, replaced by `test_unknown_tts_model_returns_zero_cost`)

**Step 7: Add test — unknown model still included in total and service count**

```python
# In tests/test_cost.py, class TestTTSCost

def test_unknown_tts_model_included_in_service_list(self):
    """Unknown TTS model still appears as a service entry (not silently dropped)."""
    config = _config(tts=TTSConfig(model="eleven_multilingual_v2"))
    est = estimate_cost(
        mode=InputMode.ORIGINAL,
        config=config,
        scene_count=25,
        character_count=247500,
    )
    assert len(est.services) == 4
    service_names = [s.service for s in est.services]
    assert "TTS" in service_names
```

Run: `pytest tests/test_cost.py::TestTTSCost::test_unknown_tts_model_included_in_service_list -v`
Expected: PASS (implementation already handles this)

**Step 8: Add test — format_cost_estimate renders unknown model gracefully**

```python
# In tests/test_cost.py, class TestFormatCostEstimate

def test_unknown_model_format(self):
    """Unknown TTS model shows 'not estimated' in formatted output."""
    config = _config(tts=TTSConfig(model="eleven_multilingual_v2"))
    est = estimate_cost(
        mode=InputMode.ORIGINAL,
        config=config,
        scene_count=25,
        character_count=247500,
    )
    output = format_cost_estimate(est)
    assert "not estimated" in output
    assert "$0.00" in output
```

Run: `pytest tests/test_cost.py::TestFormatCostEstimate::test_unknown_model_format -v`
Expected: PASS

**Step 9: Run full test suite**

Run: `pytest tests/test_cost.py -v`
Expected: All PASS

**Step 10: Commit**

```bash
git add src/story_video/cost.py tests/test_cost.py
git commit -m "fix: handle unknown TTS models gracefully in cost estimation (PR-1)

Return $0.00 with descriptive note instead of crashing with ValueError
when the TTS model is not in the rate table. ElevenLabs models have
subscription-dependent pricing that can't be hardcoded."
```

---

## Task 2: Escape special characters in subtitle filter path (PR-2)

**Files:**
- Modify: `src/story_video/ffmpeg/subtitles.py:230-241` (`subtitle_filter`)
- Test: `tests/test_subtitles.py`

**Context:** `subtitle_filter` builds the FFmpeg filter string `f"ass='{ass_path}'"`. If the path contains single quotes, backslashes, colons, or semicolons, the FFmpeg filter graph parser will break or misinterpret the expression. FFmpeg uses `\` as its escape character within filter strings — single quotes, backslashes, colons, and semicolons all need escaping.

FFmpeg filter escaping rules (from FFmpeg docs): within a quoted option value, `\` escapes the next character. Special characters that need escaping: `'`, `\`, `:`, `;`, `[`, `]`.

**Step 1: Write the failing test — path with single quote**

```python
# In tests/test_subtitles.py, class TestSubtitleFilter

def test_escapes_single_quote_in_path(self):
    """Single quotes in path are escaped to prevent filter graph breakage."""
    result = subtitle_filter(Path("/tmp/user's project/scene.ass"))
    # The single quote must be escaped so FFmpeg doesn't see it as a delimiter
    assert "\\'" in result
    assert result == "ass='/tmp/user\\'s project/scene.ass'"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_subtitles.py::TestSubtitleFilter::test_escapes_single_quote_in_path -v`
Expected: FAIL — unescaped single quote in output

**Step 3: Write implementation — escape FFmpeg special characters**

In `src/story_video/ffmpeg/subtitles.py`, modify `subtitle_filter`:

```python
def subtitle_filter(ass_path: Path) -> str:
    """Return the FFmpeg filter fragment for ASS subtitle overlay.

    Escapes backslashes and single quotes in the path to prevent
    FFmpeg filter graph injection or parse errors.

    Args:
        ass_path: Path to the ASS subtitle file.

    Returns:
        Filter string in the form ``ass='/path/to/file.ass'``
        with special characters escaped.
    """
    escaped = str(ass_path).replace("\\", "\\\\").replace("'", "\\'")
    return f"ass='{escaped}'"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_subtitles.py::TestSubtitleFilter::test_escapes_single_quote_in_path -v`
Expected: PASS

**Step 5: Add test — path with backslash**

```python
# In tests/test_subtitles.py, class TestSubtitleFilter

def test_escapes_backslash_in_path(self):
    """Backslashes in path are escaped for FFmpeg filter safety."""
    result = subtitle_filter(Path("/tmp/back\\slash/scene.ass"))
    assert result == "ass='/tmp/back\\\\slash/scene.ass'"
```

Run: `pytest tests/test_subtitles.py::TestSubtitleFilter::test_escapes_backslash_in_path -v`
Expected: PASS (implementation already handles this)

**Step 6: Add test — clean path unchanged**

```python
# In tests/test_subtitles.py, class TestSubtitleFilter

def test_clean_path_unchanged(self):
    """Normal paths without special characters pass through unchanged."""
    result = subtitle_filter(Path("/tmp/subs.ass"))
    assert result == "ass='/tmp/subs.ass'"
```

Run: `pytest tests/test_subtitles.py::TestSubtitleFilter::test_clean_path_unchanged -v`
Expected: PASS (this duplicates the existing `test_returns_ass_filter`, confirming no regression)

**Step 7: Run full subtitle test suite**

Run: `pytest tests/test_subtitles.py -v`
Expected: All PASS (existing tests for clean paths should still work)

**Step 8: Commit**

```bash
git add src/story_video/ffmpeg/subtitles.py tests/test_subtitles.py
git commit -m "fix: escape special characters in subtitle filter path (PR-2)

Escape backslashes and single quotes in ASS file paths before
interpolation into FFmpeg filter expressions. Prevents filter graph
parse errors or injection when paths contain special characters."
```

---

## Task 3: Update backlog and docs

**Files:**
- Modify: `BUGS_AND_TODOS.md`

**Step 1: Mark PR-1 and PR-2 as resolved**

Move the two items from Backlog to Resolved:

```markdown
## Resolved

- [x] [bug] `estimate_cost` crashes with ElevenLabs TTS models — returns $0.00 with descriptive note instead of raising (PR-1)
- [x] [security] Path injection in `subtitle_filter` — escape backslashes and single quotes in ASS file paths (PR-2)
```

**Step 2: Commit**

```bash
git add BUGS_AND_TODOS.md
git commit -m "docs: mark PR-1 and PR-2 as resolved"
```
