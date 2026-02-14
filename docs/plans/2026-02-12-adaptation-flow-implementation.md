# Adaptation Flow — Implementation Plan

**Date:** 2026-02-12
**Status:** Completed
**Design doc:** `docs/plans/2026-02-12-adaptation-flow-design.md`
**Branch:** `feat/adaptation-flow`

---

## Context

This plan implements the adaptation flow for the story writer pipeline — the first
module that makes Claude API calls. It covers:

- `pipeline/claude_client.py` — Thin Claude API wrapper
- `pipeline/story_writer.py` — `split_scenes()` and `flag_narration()`
- Full test suites for both modules

### Dependencies (already implemented)

- `models.py` — ProjectMetadata, Scene, InputMode, PipelinePhase, AssetType, SceneStatus
- `state.py` — ProjectState.add_scene(), update_scene_asset(), save()
- `utils/retry.py` — with_retry decorator
- `config.py` — load_config, AppConfig (has `pipeline.autonomous` flag)

### Key Patterns to Follow

- **TDD mandatory** — Red/green/refactor for every function
- **Frozen models, `__all__` exports** — Match existing module patterns
- **Mock at boundaries** — Mock `anthropic.Anthropic` for client tests, mock `ClaudeClient` for writer tests
- **Fail fast with descriptive errors** — Never swallow exceptions
- **`with_retry` for transient errors** — Retry APIConnectionError, RateLimitError, InternalServerError

---

## Task 1: ClaudeClient — Core Implementation

**[Completed]**

**File:** `src/story_video/pipeline/claude_client.py`
**Test file:** `tests/test_claude_client.py`

### What to Build

A thin wrapper around the Anthropic Python SDK providing two methods for Claude API
calls. The client is a "dumb pipe" — it handles transport and retries, not prompts.

### Interface

```python
class ClaudeClient:
    """Thin wrapper around the Anthropic Python SDK.

    Provides two methods for Claude API calls: free-text generation and
    structured output via tool_use. Handles retries on transient API errors.

    Args:
        model: Claude model identifier. Defaults to claude-sonnet-4-5-20250929.
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        self._client = anthropic.Anthropic()  # Reads ANTHROPIC_API_KEY from env
        self._model = model

    def generate(self, system: str, user_message: str,
                 max_tokens: int = 4096) -> str:
        """Simple text generation. Returns response text.

        Args:
            system: System prompt.
            user_message: User message content.
            max_tokens: Maximum tokens in response.

        Returns:
            The text content from Claude's response.

        Raises:
            anthropic.AuthenticationError: Invalid API key (no retry).
            anthropic.BadRequestError: Malformed request (no retry).
            anthropic.APIConnectionError: Network issue (retried).
            anthropic.RateLimitError: Rate limited (retried).
            anthropic.InternalServerError: Server error (retried).
        """

    def generate_structured(self, system: str, user_message: str,
                            tool_name: str, tool_schema: dict,
                            max_tokens: int = 4096) -> dict:
        """Structured output via tool_use. Returns parsed tool input dict.

        Forces Claude to use the specified tool via tool_choice, then extracts
        and returns the tool input as a parsed dict.

        Args:
            system: System prompt.
            user_message: User message content.
            tool_name: Name of the tool to force.
            tool_schema: JSON Schema for the tool's input_schema.
            max_tokens: Maximum tokens in response.

        Returns:
            The parsed tool input dict from Claude's response.

        Raises:
            ValueError: If response contains no tool_use block.
            (Same API exceptions as generate())
        """
```

### Module Structure

```python
__all__ = ["ClaudeClient"]
```

### Retry Configuration

Apply `@with_retry` from `utils/retry.py` to both methods, but only retry on
transient errors:

```python
from anthropic import APIConnectionError, InternalServerError, RateLimitError

TRANSIENT_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)
```

Use `with_retry(max_retries=3, base_delay=2.0, retry_on=TRANSIENT_ERRORS)` on
both `generate` and `generate_structured`.

Permanent errors (`AuthenticationError`, `BadRequestError`) propagate immediately
because they are not in the `retry_on` tuple.

### Implementation Details

**`generate()` internals:**
1. Call `self._client.messages.create(model=..., max_tokens=..., system=..., messages=[{"role": "user", "content": user_message}])`
2. Extract text from `response.content[0].text`
3. Return the text string

**`generate_structured()` internals:**
1. Build tool definition: `{"name": tool_name, "description": "Structured output tool", "input_schema": tool_schema}`
2. Call `self._client.messages.create(...)` with `tools=[tool_def]` and `tool_choice={"type": "tool", "name": tool_name}`
3. Find the `tool_use` block in `response.content` (iterate, check `block.type == "tool_use"`)
4. If no tool_use block found, raise `ValueError("No tool_use block in response")`
5. Return `block.input` (already a parsed dict from the SDK)

### TDD Steps

**Red tests first (write all failing tests, then implement):**

1. `test_generate_returns_text` — Mock SDK, verify text extraction from response
2. `test_generate_passes_system_and_user_message` — Verify correct message format sent to SDK
3. `test_generate_passes_model_and_max_tokens` — Verify model/max_tokens forwarded
4. `test_generate_custom_model` — Verify non-default model passed through
5. `test_generate_structured_returns_tool_input` — Mock SDK with tool_use response, verify dict extraction
6. `test_generate_structured_forces_tool_choice` — Verify `tool_choice={"type": "tool", "name": ...}` sent
7. `test_generate_structured_passes_tool_definition` — Verify tools list contains correct tool def
8. `test_generate_structured_no_tool_use_block_raises` — Mock response with no tool_use → ValueError
9. `test_generate_retries_on_connection_error` — Simulate APIConnectionError then success
10. `test_generate_retries_on_rate_limit` — Simulate RateLimitError then success
11. `test_generate_retries_on_server_error` — Simulate InternalServerError then success
12. `test_generate_no_retry_on_auth_error` — Simulate AuthenticationError → immediate propagation
13. `test_generate_no_retry_on_bad_request` — Simulate BadRequestError → immediate propagation
14. `test_generate_structured_retries_on_transient_error` — Same retry behavior for structured calls
15. `test_generate_structured_no_retry_on_permanent_error` — Same no-retry for structured calls
16. `test_default_model_is_sonnet` — Verify default model string
17. `test_client_reads_api_key_from_env` — Verify `anthropic.Anthropic()` called without explicit key

### Mocking Strategy

Mock `anthropic.Anthropic` at the SDK level. Create helper fixtures:

```python
@pytest.fixture
def mock_anthropic(monkeypatch):
    """Patch anthropic.Anthropic to return a mock client."""
    mock_client = MagicMock()
    mock_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("story_video.pipeline.claude_client.anthropic.Anthropic", mock_class)
    return mock_client
```

For tool_use responses, build mock response objects:

```python
def make_text_response(text: str) -> MagicMock:
    """Create a mock Messages response with a text block."""

def make_tool_use_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Create a mock Messages response with a tool_use block."""
```

### Commit Point

After all tests pass: `feat(pipeline): add Claude API client wrapper`

---

## Task 2: split_scenes() — Scene Splitting

**[Completed]**

**File:** `src/story_video/pipeline/story_writer.py`
**Test file:** `tests/test_story_writer.py`

### What to Build

The `split_scenes()` function divides a source story into scenes at natural
boundaries using Claude's tool_use. This is the first phase of the adaptation flow.

### Interface

```python
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
```

### Module Structure

```python
__all__ = ["flag_narration", "split_scenes"]
```

### System Prompt

```
You are a story editor splitting a narrative into scenes for video narration.

Rules:
- Never split mid-paragraph
- Never split mid-dialogue (keep complete dialogue exchanges together)
- Target 1500-2000 words per scene, but prioritize natural boundaries
- Each scene should have a clear beginning, middle, or end
- Preserve every word exactly — do not add, remove, or rephrase anything
- Assign each scene a short, descriptive title (3-6 words)
```

### Tool Schema

```python
SCENE_SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short descriptive scene title"},
                    "text": {"type": "string", "description": "Complete scene text, every word preserved"},
                },
                "required": ["title", "text"],
            },
            "minItems": 1,
        }
    },
    "required": ["scenes"],
}
```

### Implementation Details

1. Read `source_story.txt` from `state.project_dir` — raise `FileNotFoundError` with path if missing
2. Call `client.generate_structured(system=SYSTEM_PROMPT, user_message=source_text, tool_name="split_into_scenes", tool_schema=SCENE_SPLIT_SCHEMA)`
3. Extract scenes list from response dict
4. **Validate zero scenes**: `if not scenes: raise ValueError("Claude returned zero scenes")`
5. **Validate empty text**: For each scene, `if not scene["text"].strip(): raise ValueError(f"Empty text in scene {i+1}: {scene['title']}")`
6. **Preservation check**: Normalize whitespace in original and concatenated scene texts, compare. If mismatch, raise `ValueError` with location of first difference
7. For each scene (1-indexed):
   - `state.add_scene(scene_number=i+1, title=scene["title"], prose=scene["text"])`
   - `state.update_scene_asset(scene_number=i+1, asset=AssetType.TEXT, status=SceneStatus.COMPLETED)`
8. Write `scenes/scene_01.md`, `scene_02.md`, etc. for human review
   - Format: `# Scene {n}: {title}\n\n{text}\n`
9. `state.save()`

### Preservation Check

The preservation check is critical — adapt mode promises verbatim narration.

```python
def _check_preservation(original: str, scenes: list[dict]) -> None:
    """Verify concatenated scene texts match the original source.

    Normalizes whitespace before comparison: strips leading/trailing whitespace,
    collapses multiple whitespace characters to single spaces.

    Args:
        original: The original source story text.
        scenes: List of scene dicts with "text" keys.

    Raises:
        ValueError: If the texts don't match, with context showing where
            the mismatch occurs.
    """
```

Normalization: `" ".join(text.split())` — this collapses all whitespace variants
(newlines, tabs, multiple spaces) into single spaces for comparison. This allows
Claude to adjust paragraph breaks between scenes without failing the check.

### TDD Steps

**Red tests first:**

1. `test_split_scenes_happy_path` — Source → 3 scenes → state has 3 scenes, .md files exist
2. `test_split_scenes_state_updated` — Verify `state.add_scene()` called with correct args
3. `test_split_scenes_asset_status_completed` — Verify TEXT asset set to COMPLETED for each scene
4. `test_split_scenes_md_files_written` — Verify scene_01.md, scene_02.md content
5. `test_split_scenes_state_saved` — Verify `state.save()` called
6. `test_split_scenes_preservation_check_passes` — Exact text preserved
7. `test_split_scenes_preservation_check_fails` — Modified text → ValueError with mismatch info
8. `test_split_scenes_zero_scenes_raises` — Empty scenes list → ValueError
9. `test_split_scenes_empty_scene_text_raises` — Scene with blank text → ValueError
10. `test_split_scenes_source_file_missing` — No source_story.txt → FileNotFoundError
11. `test_split_scenes_reads_source_from_project_dir` — Verify correct file path used
12. `test_split_scenes_calls_claude_with_correct_params` — Verify system prompt, tool name, schema
13. `test_preservation_check_normalizes_whitespace` — Extra newlines/spaces don't cause failure

### Mocking Strategy

Mock `ClaudeClient` entirely — don't use real API calls. Inject a mock that returns
canned scene-split responses.

```python
@pytest.fixture
def mock_client():
    """Create a mock ClaudeClient with canned responses."""
    client = MagicMock(spec=ClaudeClient)
    return client

@pytest.fixture
def sample_state(tmp_path):
    """Create a project state in adapt mode with source_story.txt."""
    state = ProjectState.create(
        project_id="test-project",
        mode=InputMode.ADAPT,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    source = tmp_path / "test-project" / "source_story.txt"
    source.write_text("Once upon a time. ... The end.")
    return state
```

### Commit Point

After all tests pass: `feat(pipeline): add scene splitting for adapt mode`

---

## Task 3: flag_narration() — Narration Flagging

**[Completed]**

**File:** `src/story_video/pipeline/story_writer.py` (same file as Task 2)
**Test file:** `tests/test_story_writer.py` (same file as Task 2)

### What to Build

The `flag_narration()` function identifies TTS-unfriendly content in scene texts
and optionally applies fixes in autonomous mode.

### Interface

```python
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
```

### System Prompt

```
You are a narration quality reviewer preparing story text for text-to-speech.

Identify content that will sound wrong or confusing when read aloud by a TTS engine:
- Footnote references (e.g., "[1]", "as noted in [3]")
- Visual formatting that won't translate to audio (tables, bullet lists, ASCII art)
- Unusual typography (em dashes used decoratively, ellipsis chains)
- Long parentheticals that break speech flow
- Non-prose content (headers, captions, author notes)
- Ambiguous pronunciation (acronyms, abbreviations not caught by text prep)

For each issue, provide:
- The scene number where it occurs
- The location within the scene (paragraph and sentence)
- The category of issue
- The exact original text
- A suggested fix for natural speech
- Severity: "must_fix" for show-stoppers, "should_fix" for noticeable issues
```

### Tool Schema

```python
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
                    "category": {"type": "string", "description": "e.g. footnote, formatting, typography"},
                    "original_text": {"type": "string", "description": "The exact problematic text"},
                    "suggested_fix": {"type": "string", "description": "Suggested replacement for natural speech"},
                    "severity": {"type": "string", "enum": ["must_fix", "should_fix"]},
                },
                "required": ["scene_number", "location", "category", "original_text", "suggested_fix", "severity"],
            },
        }
    },
    "required": ["flags"],
}
```

### Implementation Details

1. Get scenes from `state.metadata.scenes` — raise `ValueError("No scenes in project")` if empty
2. Build user message: all scene texts, numbered:
   ```
   === Scene 1: {title} ===
   {prose}

   === Scene 2: {title} ===
   {prose}
   ```
3. Call `client.generate_structured(system=SYSTEM_PROMPT, user_message=scene_text, tool_name="flag_narration_issues", tool_schema=NARRATION_FLAGS_SCHEMA)`
4. Extract flags list from response
5. Write `narration_flags.md` to `state.project_dir`:
   - If flags exist: formatted table/list of all flags
   - If no flags: `"# Narration Flags\n\nNo TTS issues found. All scenes are narration-ready.\n"`
6. **Autonomous mode** (`state.metadata.config.pipeline.autonomous == True`):
   - For each flag, find the matching scene by `scene_number`
   - Skip flags with invalid scene numbers (log warning, don't crash)
   - Copy `scene.prose` to `scene.narration_text` if not already set
   - Apply `suggested_fix`: replace `original_text` with `suggested_fix` in `scene.narration_text`
7. **Semi-auto mode** (`autonomous == False`):
   - Write flags file only — human reviews and applies fixes on resume
8. `state.save()`

### TDD Steps

**Red tests first:**

1. `test_flag_narration_happy_path_with_flags` — Flags returned → flags file written with content
2. `test_flag_narration_zero_flags` — No issues → "no issues found" written
3. `test_flag_narration_no_scenes_raises` — Empty scenes list → ValueError
4. `test_flag_narration_builds_user_message_correctly` — Verify numbered scene format sent to Claude
5. `test_flag_narration_calls_claude_with_correct_params` — Verify system prompt, tool name, schema
6. `test_flag_narration_autonomous_applies_fixes` — autonomous=True → narration_text updated with fix
7. `test_flag_narration_autonomous_copies_prose_first` — narration_text is None → copies from prose, then applies fix
8. `test_flag_narration_autonomous_preserves_existing_narration_text` — If narration_text already set, applies fix to it (not prose)
9. `test_flag_narration_semi_auto_no_fixes` — autonomous=False → narration_text unchanged
10. `test_flag_narration_invalid_scene_number_skipped` — Flag with scene_number=99 → skipped, no crash
11. `test_flag_narration_flags_file_format` — Verify flags file contains scene number, category, original, fix
12. `test_flag_narration_state_saved` — Verify `state.save()` called
13. `test_flag_narration_multiple_flags_same_scene` — Multiple fixes applied to same scene sequentially

### Mocking Strategy

Same approach as Task 2 — mock `ClaudeClient`, use real `ProjectState` with
`tmp_path`. Pre-populate scenes in state before calling `flag_narration()`.

```python
@pytest.fixture
def state_with_scenes(tmp_path):
    """Create project state with 3 scenes already populated."""
    state = ProjectState.create(
        project_id="test-project",
        mode=InputMode.ADAPT,
        config=AppConfig(),  # autonomous=False by default
        output_dir=tmp_path,
    )
    state.add_scene(1, "The Beginning", "Once upon a time in a land far away.")
    state.add_scene(2, "The Middle", "The hero faced the dragon as noted in [1].")
    state.add_scene(3, "The End", "They lived happily ever after.")
    return state

@pytest.fixture
def autonomous_state(tmp_path):
    """Create project state with autonomous=True."""
    config = AppConfig(pipeline=PipelineConfig(autonomous=True))
    state = ProjectState.create(
        project_id="test-project",
        mode=InputMode.ADAPT,
        config=config,
        output_dir=tmp_path,
    )
    # ... add scenes ...
    return state
```

### Commit Point

After all tests pass: `feat(pipeline): add narration flagging for adapt mode`

---

## Execution Order

Tasks must be executed sequentially:

1. **Task 1** (ClaudeClient) — No dependencies on other new code
2. **Task 2** (split_scenes) — Depends on ClaudeClient from Task 1
3. **Task 3** (flag_narration) — Depends on ClaudeClient + shares story_writer.py with Task 2

### Estimated Test Count

- Task 1: ~17 tests
- Task 2: ~13 tests
- Task 3: ~13 tests
- **Total: ~43 new tests** (running total: ~431)

---

## Retrospective

(To be filled after implementation)

- Process improvements discovered during implementation
- Patterns that worked well or need adjustment
