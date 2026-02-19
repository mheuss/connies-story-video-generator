# ORIGINAL Mode — Design

**Date:** 2026-02-18
**Status:** Approved

## Overview

The `original` input mode takes a creative brief (topic, outline, character sketch — anything from a single sentence to a detailed treatment) and generates a complete story with narration, illustrations, and video. No source story required. The brief is the sole creative input.

## Approach

Minimal delta from `inspired_by`. Same 11-phase `CREATIVE_FLOW_PHASES` pipeline. The only behavioral difference is in the ANALYSIS phase, which interprets a brief instead of analyzing a full story.

## Phase Flow

Same as `inspired_by`:

```
ANALYSIS → STORY_BIBLE → OUTLINE → SCENE_PROSE → CRITIQUE_REVISION
    ↓ (converges with adapt flow)
IMAGE_PROMPTS → NARRATION_PREP → TTS → IMAGES → CAPTIONS → VIDEO
```

All five creative phases are checkpoint phases (pause for human review in semi-auto mode).

## ANALYSIS Phase

`analyze_source()` handles both modes:

- **INSPIRED_BY:** Reads source story, uses `ANALYSIS_SYSTEM` prompt ("analyze this story's craft and themes"). Claude returns craft_notes, thematic_brief, and source_stats.
- **ORIGINAL:** Reads creative brief, uses `BRIEF_ANALYSIS_SYSTEM` prompt ("interpret this brief to extract themes, tone, and style direction"). Claude returns craft_notes and thematic_brief. source_stats are computed from config, not from Claude.

### BRIEF_ANALYSIS_SYSTEM prompt

Tells Claude: interpret the creative brief to extract implied themes, emotional arc, and style/tone guidance. For craft_notes, infer appropriate writing style from the subject matter and any explicit style direction in the brief. If no style is specified, choose something fitting for the content.

### source_stats computation

Derived from `StoryConfig.target_duration_minutes`:

- `word_count = target_duration_minutes * 150` (narration pace ~150 wpm)
- `scene_count_estimate = max(2, word_count // 600)` (~600 words per scene, minimum 2 scenes)

Injected into the analysis result after the Claude call. Claude doesn't compute these for ORIGINAL mode.

### Output

Same `analysis.json` schema as INSPIRED_BY:

```json
{
  "craft_notes": {
    "sentence_structure": "...",
    "vocabulary": "...",
    "tone": "...",
    "pacing": "...",
    "narrative_voice": "..."
  },
  "thematic_brief": {
    "themes": ["..."],
    "emotional_arc": "...",
    "central_tension": "...",
    "mood": "..."
  },
  "source_stats": {
    "word_count": 750,
    "scene_count_estimate": 2
  }
}
```

## CLI Changes

### Flag rename

`--source-material` renamed to `--input`. Clean break, no deprecation alias (pre-release).

`--input` is required for all three modes:
- **adapt:** the finished story
- **inspired_by:** the source story for style/theme extraction
- **original:** the creative brief

### Guard removal

Remove the "not yet implemented" error for `InputMode.ORIGINAL`.

### No new flags

`--premise`, `--autonomous`, `--verbose`, `--config`, `--output-dir` work unchanged.

## What Doesn't Change

- `create_story_bible` — reads `analysis.json`, works identically
- `create_outline` — reads `analysis.json` + `story_bible.json`, works identically
- `write_scene_prose` — unchanged
- `critique_and_revise` — unchanged
- Orchestrator dispatch — already routes correctly for ORIGINAL
- Models — no new fields (one new constant for words-per-minute)
- State — `get_phase_sequence()` already returns `CREATIVE_FLOW_PHASES` for ORIGINAL
- All media phases — untouched

## File Changes

| File | Change |
|------|--------|
| `story_writer.py` | New `BRIEF_ANALYSIS_SYSTEM` constant, mode check in `analyze_source()` |
| `cli.py` | Rename `--source-material` to `--input`, remove ORIGINAL guard |
| `models.py` | Add `NARRATION_WORDS_PER_MINUTE` constant |
| Test files | Update `--source-material` to `--input`, new ORIGINAL mode tests |

## Testing

- `analyze_source` with ORIGINAL mode — brief text + correct prompt + config-derived source_stats
- `analyze_source` with INSPIRED_BY mode — existing tests unchanged
- CLI — all `--source-material` references become `--input`, ORIGINAL mode accepted and runs
- Integration — full ORIGINAL creative flow with mocked Claude

## Decisions

- **Same phase sequence** — ORIGINAL uses identical `CREATIVE_FLOW_PHASES` as INSPIRED_BY
- **Config-driven length** — `target_duration_minutes` determines story length, not brief analysis
- **One function, mode check** — `analyze_source()` branches on mode for the prompt, not separate functions
- **Clean flag rename** — `--source-material` to `--input`, no backward compatibility (pre-release)
- **Style from brief** — Claude infers style from brief content; no presets or defaults
