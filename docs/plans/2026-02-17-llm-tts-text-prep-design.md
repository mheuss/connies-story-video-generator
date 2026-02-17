# LLM-Based TTS Text Prep — Design

**Status:** Approved

**Date:** 2026-02-17

## Overview

Replace the regex-based `prepare_narration()` pipeline with a single Claude API call per scene. The NARRATION_PREP phase keeps its name — its implementation changes from four regex transforms to one `generate_structured()` call that handles abbreviation expansion, number pronunciation, punctuation smoothing, and contextual decisions that regex can't get right.

The existing regex code (`expand_abbreviations`, `numbers_to_words`, `smooth_punctuation`, `insert_pause_markers`, and all their helpers in `text.py`) gets deleted. Less code to maintain, better results. Always on — no config flag.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Replaces or augments regex? | Replaces entirely | Running both is redundant; regex could undo Claude's choices |
| Activation | Always on | API calls are cheap; no reason to maintain two code paths |
| Phase identity | Keep NARRATION_PREP | Same phase, new implementation; no pipeline changes needed |
| Granularity | One call per scene | Scenes are natural breakpoints; fits context window easily |
| Tag handling | Send full text with tags, validate afterward | Mid-sentence voice switches make strip-and-reinsert fragile |
| Pronunciation guide | Accumulates across scenes | Scene 1's guide entries feed into scene 2's prompt |
| Changelog format | Structured JSON | Machine-readable, easy to review |
| Review flow | Changelog + autonomous | Autonomous continues; semi-auto pauses for review |
| Error on tag corruption | Retry once, then fail the scene | Prevents silent corruption of voice assignments |
| Dead regex code | Remove now | No reason to keep unused code |

## Data Flow

```
For each scene (sequential):

  scene.narration_text (or scene.prose)
       │
       ├── pronunciation_guide (accumulated from prior scenes)
       ├── story_title (from project state)
       │
       ▼
  ClaudeClient.generate_structured()
       │
       ▼
  Response: {
    modified_text: str,
    changes: [{original, replacement, reason}],
    pronunciation_guide_additions: [{term, pronunciation, context}]
  }
       │
       ├── Validate: tags preserved (same tags, same order)
       │   ├── Pass → accept
       │   └── Fail → retry once with corrective prompt → fail scene
       │
       ├── scene.narration_text = modified_text
       ├── Merge pronunciation_guide_additions into running guide
       └── Append changes to changelog

After all scenes:
  Write changelog JSON to project directory
  In semi-auto mode: pause for review
  In autonomous mode: continue
```

## Tag Handling

Voice and mood tags (`**voice:label**`, `**mood:emotion**`) appear anywhere in the text, including mid-sentence around dialogue. Example:

```
**voice:old_man** "I've seen worse," **voice:narrator** he muttered.
```

We send the full text with tags to Claude and instruct it to preserve them exactly. After each call, we validate:

1. Extract all tags from input text (regex: `\*\*(?:voice|mood):\w+\*\*`)
2. Extract all tags from output text
3. Compare: same tags, same order
4. On mismatch: retry once with explicit corrective instruction
5. Second failure: raise `NarrationPrepError` that fails the scene

## Claude Prompt & Tool Schema

### System Prompt

> You are a TTS text preparation specialist. Your job is to rewrite narration text so it sounds natural when read aloud by a text-to-speech engine. You must:
> - Expand abbreviations contextually (e.g., "Dr." → "Doctor" before a name, "Drive" in an address)
> - Convert numbers to spoken form (e.g., "1847" → "eighteen forty-seven" for years, "one thousand eight hundred forty-seven" for quantities)
> - Smooth punctuation for speech flow (e.g., em dashes → commas or pauses)
> - Handle unusual names or terms using the pronunciation guide
> - Preserve all `**voice:X**` and `**mood:X**` tags exactly as they appear — do not move, add, remove, or modify any tag

### Tool Schema

```json
{
    "name": "tts_text_prep",
    "description": "Prepared narration text optimized for TTS",
    "input_schema": {
        "type": "object",
        "properties": {
            "modified_text": {
                "type": "string",
                "description": "The full narration text rewritten for TTS, with all voice/mood tags preserved exactly"
            },
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "original": {"type": "string"},
                        "replacement": {"type": "string"},
                        "reason": {"type": "string"}
                    },
                    "required": ["original", "replacement", "reason"]
                }
            },
            "pronunciation_guide_additions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "pronunciation": {"type": "string"},
                        "context": {"type": "string"}
                    },
                    "required": ["term", "pronunciation", "context"]
                }
            }
        },
        "required": ["modified_text", "changes", "pronunciation_guide_additions"]
    }
}
```

### User Message Contents

- The scene's narration text (full, with tags)
- Accumulated pronunciation guide (empty list for scene 1)
- Story title for context
- Scene number and total scene count

## File Layout

| Action | File | Purpose |
|--------|------|---------|
| Create | `src/story_video/pipeline/narration_prep.py` | `prepare_narration_llm()`, prompt building, tag validation, changelog writing |
| Modify | `src/story_video/pipeline/orchestrator.py` | `_run_narration_prep()` calls new function instead of `prepare_narration()` |
| Modify | `src/story_video/utils/text.py` | Delete `prepare_narration()` and all regex transform functions/helpers/patterns |
| Modify | `src/story_video/models.py` | Add changelog/pronunciation guide fields if needed |
| Create | `tests/test_narration_prep.py` | Tests for new module |
| Delete | Tests for removed regex functions | Clean up dead test code |

## Error Handling

| Scenario | Action |
|----------|--------|
| Claude API error (transient) | Normal retry via `with_retry` on the Claude call |
| Tag validation fails | Retry once with corrective prompt, then raise `NarrationPrepError` |
| Empty `modified_text` returned | Raise `NarrationPrepError` |
| Scene has no narration_text and no prose | Skip scene (existing behavior) |

`NarrationPrepError` is a new exception with scene number and failure description.

## Testing Strategy

**Unit tests:**
- Tag extraction from text
- Tag validation (same, different, reordered, missing, extra)
- Prompt building with/without pronunciation guide
- Changelog JSON structure
- Pronunciation guide accumulation across scenes

**Integration test:**
- Mock `ClaudeClient.generate_structured()` with canned response
- Verify full flow through `_run_narration_prep()`: text updated, changelog written, guide accumulated

**Edge cases:**
- Scene with no tags
- Scene with adjacent tags
- Scene with only tags and no prose
- Empty pronunciation guide vs guide with prior entries
- Scene with no narration_text and no prose (skip)
