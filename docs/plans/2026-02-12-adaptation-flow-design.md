# Adaptation Flow — Design Document

**Date:** 2026-02-12
**Status:** Approved
**Scope:** Scene splitting + narration flagging for adapt mode

---

## Overview

Implement the adaptation flow (adapt mode) for the story writer pipeline. This is
the first module that makes Claude API calls. It covers two phases:

1. **Scene Splitting** — Divide a source story into scenes at natural boundaries
2. **Narration Flagging** — Identify TTS-unfriendly content in the scene texts

### Out of Scope

- Creative flow (original/inspired_by) — phases 1-5 (future sprint)
- Image prompt generation — separate module
- Orchestrator wiring — future sprint
- Marker-based scene splitting (pre-split input) — backlogged, design accommodates it

---

## Architecture

### New Files

- **`pipeline/claude_client.py`** — Thin Claude API wrapper, reused by all future
  pipeline modules
- **`pipeline/story_writer.py`** — Two public functions: `split_scenes()` and
  `flag_narration()`

### Dependencies

- `models.py` — ProjectMetadata, Scene, InputMode, PipelinePhase, AssetType, SceneStatus
- `state.py` — ProjectState.add_scene(), update_scene_asset(), save()
- `utils/retry.py` — with_retry for API calls
- `anthropic` SDK — Claude API

### Data Flow

```
source_story.txt (in project_dir)
        │
        ▼
  split_scenes() ──Claude tool_use──► list of {title, text}
        │
        ├──► state.add_scene() for each scene
        ├──► scenes/scene_01.md, scene_02.md, ...
        └──► state.save()

  flag_narration() ──Claude tool_use──► list of {scene_number, flags}
        │
        ├──► narration_flags.md
        ├──► (autonomous) apply fixes to scene.narration_text
        └──► state.save()
```

---

## ClaudeClient

Thin wrapper providing a clean interface for Claude API calls.

```python
class ClaudeClient:
    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        # Reads ANTHROPIC_API_KEY from environment (SDK default)
        self._client = anthropic.Anthropic()
        self._model = model

    def generate(self, system: str, user_message: str,
                 max_tokens: int = 4096) -> str:
        """Simple text generation. Returns response text."""

    def generate_structured(self, system: str, user_message: str,
                            tool_name: str, tool_schema: dict,
                            max_tokens: int = 4096) -> dict:
        """Tool_use generation. Returns parsed tool input dict."""
```

### Design Decisions

- **Two methods**: `generate` for free-text, `generate_structured` for
  schema-validated output via tool_use
- **Retry via `@with_retry`** on both methods — handles transient API failures
- **Model configurable** at init, defaults to Sonnet for cost/speed balance
- **API key from environment** — no keys in code
- **No prompt templates** — the client is a dumb pipe. Each phase function
  assembles its own prompts.
- **`generate_structured` forces tool_use** via
  `tool_choice={"type": "tool", "name": tool_name}`

### Retry Configuration

- Retry on transient errors only: `APIConnectionError`, `RateLimitError`,
  `InternalServerError`
- Do NOT retry on: `AuthenticationError`, `BadRequestError`
- Uses `with_retry` from `utils/retry.py` (3 retries, base delay 2s, cap 60s)

---

## Scene Splitting (Phase 1)

### Function Signature

```python
def split_scenes(state: ProjectState, client: ClaudeClient) -> None:
```

### Input

Reads `source_story.txt` from `state.project_dir`.

### Prompt

- **System**: Scene splitting rules from design doc — never split mid-paragraph,
  never split mid-dialogue, target 1500-2000 words, prefer natural boundaries
- **User message**: The full source story text

### Tool Schema

```json
{
  "scenes": [
    {
      "title": "The Arrival",
      "text": "Full scene text, every word preserved..."
    }
  ]
}
```

### Post-Processing

1. **Preservation check**: Verify concatenation of all scene texts matches the
   original source (word-for-word). This is critical — adapt mode promises
   verbatim narration.
2. For each scene: `state.add_scene(scene_number, title, prose)`
3. For each scene: `state.update_scene_asset(scene_number, AssetType.TEXT, SceneStatus.COMPLETED)`
4. Write `scenes/scene_01.md`, `scene_02.md`, etc. for human review
5. `state.save()`

### Future Enhancement

The function should be structured so a marker-based parser can be added as an
early-exit path. If the source text contains explicit chapter/scene markers
(e.g., `## Chapter 1: Title`), parse them directly instead of calling Claude.
This is backlogged for a future sprint.

---

## Narration Flagging (Phase 2)

### Function Signature

```python
def flag_narration(state: ProjectState, client: ClaudeClient) -> None:
```

### Input

Scene texts from `state.metadata.scenes` (populated by `split_scenes`).

### Prompt

- **System**: Instructions for identifying TTS-unfriendly content — footnotes,
  visual formatting, unusual typography, long parentheticals, non-prose content,
  ambiguous pronunciation
- **User message**: All scene texts, numbered for reference

### Tool Schema

```json
{
  "flags": [
    {
      "scene_number": 3,
      "location": "paragraph 2, sentence 1",
      "category": "footnote",
      "original_text": "as noted in [1]",
      "suggested_fix": "as noted in the previous study",
      "severity": "should_fix"
    }
  ]
}
```

### Post-Processing

1. Write `narration_flags.md` — human-readable report
2. If **autonomous mode** (`config.pipeline.autonomous == True`): apply suggested
   fixes to `scene.narration_text` (copy prose first if narration_text not set)
3. If **semi-auto mode**: write flags file only, human reviews on resume
4. If **zero flags**: write "no issues found" to flags file, skip review checkpoint
5. `state.save()`

### Relationship to Narration Prep

This phase does NOT run `prepare_narration()` from `utils/text.py`. Flagging
identifies Claude-level issues (unusual content). Text.py handles mechanical
transformations (abbreviations, numbers, pauses, punctuation). They are
complementary, not overlapping. Both run at different pipeline phases.

---

## Error Handling

### Transient API Failures

Network timeouts, rate limits, 500 errors. Handled by `@with_retry` — 3 retries
with exponential backoff. After exhaustion, the original exception propagates.
The orchestrator catches it and calls `state.fail_phase()`.

### Permanent API Failures

Invalid API key → `AuthenticationError`. Fails immediately, no retry.

### Logic Errors

| Error | Raised | Context |
|-------|--------|---------|
| Source file missing | `FileNotFoundError` | Descriptive message with path |
| Preservation check fails | `ValueError` | Shows where mismatch occurred |
| Zero scenes returned | `ValueError` | Descriptive message |
| Empty scene text | `ValueError` | Scene number and title |

The story writer never swallows exceptions. It validates, raises on problems,
and lets the orchestrator decide what to do.

---

## Testing Strategy

All tests are Layer 2 — mocked API calls, no real Claude calls.

### ClaudeClient Tests (~15-20 tests)

- Mock `anthropic.Anthropic` at SDK level
- `generate()` returns response text
- `generate_structured()` returns parsed tool input dict
- Retry on transient errors then success
- Permanent errors propagate immediately
- `tool_choice` set correctly for structured calls

### Story Writer Tests (~20-25 tests)

Mock `ClaudeClient` entirely — inject fake with canned responses.

**split_scenes:**
- Happy path: source → 3 scenes → state updated, .md files written
- Preservation check passes when text matches
- Preservation check fails → `ValueError`
- Zero scenes → `ValueError`
- Source file missing → `FileNotFoundError`
- Asset status set to COMPLETED for TEXT

**flag_narration:**
- Happy path with flags: flags file written
- Zero flags: "no issues found" written
- Autonomous mode: fixes applied to narration_text
- Semi-auto mode: flags only, narration_text untouched
- Invalid scene number in flags → handled gracefully

### Estimated Test Count

35-45 new tests. No `@pytest.mark.slow` smoke tests in this sprint.
