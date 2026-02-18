# Inspired By Mode — Design

**Date:** 2026-02-18
**Status:** Approved

## Overview

The `inspired_by` input mode takes an existing story as a style and theme reference, then generates a completely new story with original characters, setting, and plot. The source material provides the *feel* — themes, mood, narrative style — not a world to inhabit.

## Phase Flow

Uses the existing `CREATIVE_FLOW_PHASES` sequence (11 phases):

```
ANALYSIS → STORY_BIBLE → OUTLINE → SCENE_PROSE → CRITIQUE_REVISION
    ↓ (converges with adapt flow)
IMAGE_PROMPTS → NARRATION_PREP → TTS → IMAGES → CAPTIONS → VIDEO
```

All five creative phases are checkpoint phases (pause for human review in semi-auto mode).

## Data Model

No new fields on the Scene model. Phase artifacts are project-level context stored in `state.metadata`:

```python
state.metadata["analysis"] = {"craft_notes": {...}, "thematic_brief": {...}, "source_stats": {...}}
state.metadata["story_bible"] = {"characters": [...], "setting": {...}, "premise": "...", "rules": [...]}
state.metadata["outline"] = {"scenes": [...], "total_target_words": N}
```

SCENE_PROSE creates scenes via `state.add_scene()`. CRITIQUE_REVISION overwrites `scene.prose` in place. Downstream phases work identically to adapt.

## Phase Details

### ANALYSIS

One Claude call via `generate_structured()`. Reads source material, produces craft notes + thematic brief.

**Structured output:**

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
    "word_count": 3200,
    "scene_count_estimate": 5
  }
}
```

`source_stats` captures source dimensions so the outline phase can target matching length. Craft notes fields are free-form strings with concrete observations.

If user provided `--premise`, it's stored in metadata but doesn't affect analysis. Feeds into story bible.

### STORY_BIBLE

One Claude call via `generate_structured()`. Receives craft notes + thematic brief + optional premise. Generates new characters, setting, and world.

**Structured output:**

```json
{
  "characters": [
    {
      "name": "...",
      "role": "protagonist | antagonist | supporting",
      "description": "Physical and personality in 2-3 sentences",
      "arc": "Where they start emotionally → where they end"
    }
  ],
  "setting": {
    "place": "...",
    "time_period": "...",
    "atmosphere": "..."
  },
  "premise": "One-paragraph story summary",
  "rules": ["World-building constraints"]
}
```

Bible is deliberately compact — it's included in every subsequent call as context.

### OUTLINE

One Claude call via `generate_structured()`. Receives bible + craft notes + thematic brief + source stats.

Targets approximately `source_word_count` total words across approximately `source_scene_count` scenes.

**Structured output:**

```json
{
  "scenes": [
    {
      "scene_number": 1,
      "title": "The Arrival",
      "beat": "1-2 sentences describing what happens",
      "target_words": 350
    }
  ],
  "total_target_words": 3200
}
```

Target words are advisory, not enforced. They give the prose phase a sense of proportion.

### SCENE_PROSE

One Claude call per scene via `generate()` (plain text, not structured output). Each call receives craft notes, bible, full outline, running summary of prior scenes, and the current scene beat + target word count.

Running summary: after each scene completes, a 2-3 sentence summary is appended to the running context. Same pattern documented in DEVELOPMENT.md.

Scene creation: `state.add_scene(scene_number, title, prose)` per scene. Written to `scenes/scene_01.md`, etc.

Per-scene resume: if the phase fails mid-way, resume picks up at the failed scene.

No checkpoint between individual scenes — phase checkpoints once after all scenes are written.

### CRITIQUE_REVISION

One Claude call per scene via `generate_structured()`. Reviews prose against craft notes and thematic brief. Returns revised text + change notes.

**Structured output:**

```json
{
  "revised_prose": "Full scene text with revisions...",
  "changes": ["What was changed and why"]
}
```

Revision overwrites `scene.prose` in place. Change notes written to `critique/scene_01_changes.md` for review.

Per-scene resume supported. Checkpoint after all scenes revised.

## CLI

```
story-video create --mode inspired_by --source story.txt --premise "set it in space"
```

- `--premise` is optional. Only meaningful for `inspired_by` and `original` modes. Ignored with warning if used with `--mode adapt`.
- `--source` is required for `inspired_by`.
- Remove "not implemented" guard for `inspired_by`. Keep it for `original`.
- No other new flags. `--autonomous`, `--verbose`, `--config`, `--output-dir` work the same.

Cost estimation already handled — `cost.py` rates apply to both `original` and `inspired_by`.

## Orchestrator Integration

Five new branches in `_dispatch_phase()`:

```
ANALYSIS → story_writer.analyze_source(state, client)
STORY_BIBLE → story_writer.create_story_bible(state, client)
OUTLINE → story_writer.create_outline(state, client)
SCENE_PROSE → story_writer.write_scene_prose(state, client)
CRITIQUE_REVISION → story_writer.critique_and_revise(state, client)
```

All five live in `story_writer.py`. No new module.

All five added to `_CHECKPOINT_PHASES`.

No provider requirements — only `claude_client` needed.

Metadata storage: each function reads/writes its own `state.metadata` keys.

Phase-to-asset mapping already correct in `PHASE_ASSET_MAP`.

## Testing Strategy

**Unit tests** (in `test_story_writer.py`):
- `analyze_source` — verify source in context, output in metadata, both craft notes and thematic brief present
- `create_story_bible` — verify analysis in context, test with/without premise
- `create_outline` — verify bible + analysis in context, scene count and word targets populated
- `write_scene_prose` — verify one call per beat, `add_scene()` called correctly, running summary accumulates
- `critique_and_revise` — verify revised prose overwrites, change notes written to disk

**Resume tests** for `write_scene_prose` and `critique_and_revise` — partial completion, verify only remaining scenes processed.

**Orchestrator dispatch test** — five new phases route correctly.

**CLI test** — `inspired_by` accepted, `--premise` stored.

**Integration test** — full creative flow with mocked Claude. Verify data flows from analysis through critique.

All Claude calls mocked. No slow/live API tests.

## Decisions

- **Creative latitude:** Same themes, new everything. Source is a vibe reference.
- **Analysis output:** Craft notes (style) + thematic brief (substance).
- **User steering:** Optional `--premise` flag.
- **Critique approach:** Single pass for v1. Critic/author loop backlogged.
- **Story length:** Match source material. User-configurable targeting backlogged.
- **Architecture:** One call per phase (Approach A). Simplest, matches existing patterns.

## Backlog Items

- Critic/author revision loop (iterative refinement with separate personas)
- User-configurable story length (`--target-words`, `--target-scenes`)
- Iterative quality validation per phase (Approach C)
