# Bugs and Todos

## Active

Items committed to the current sprint/cycle.

### Web UI — 2026-02-25

- [x] **Web UI backend API (Plan 1/3)** — FastAPI backend with project CRUD, pipeline start/approve, SSE progress streaming, artifact serving, API key setup, and `serve` CLI command. (`docs/plans/2026-02-25-web-ui-backend-implementation.md`)
- [x] **Web UI React frontend (Plan 2/3)** — Vite + React SPA with Storybook, create/progress/review screens, SSE integration, settings page, progress bars, retry/download, artifact edit validation.
- [x] **Web UI Docker & packaging (Plan 3/3)** — Dockerfile, static file serving, port config.
- [ ] **Web UI file upload** — Design doc mentions `source_file?` for file uploads, but v1 API only accepts `source_text` as a string. Add multipart file upload support when frontend needs it.
- [x] **Web UI: Replace window.location.reload() with React state transitions** — ReviewScreen approve and ProjectPage retry use full page reload. Fixed: added `reset()` to `useProgressStream`, passed as `onApproved` prop to ReviewScreen. (I-1 from PR review)
- [x] **Web UI: SSE reconnection should sync state via REST** — On reconnect, `useProgressStream` calls `api.getProject()` to detect completed/failed/awaiting_review before re-opening SSE. (I-2 from PR review)
- [x] **Web UI: Add SSE reconnection tests** — Added 5 tests covering REST state sync on reconnect (completed, failed, awaiting_review), REST failure fallback, and retry exhaustion. (I-6 from PR review)
- [x] **Web UI: Verify `scene_progress` SSE event emitted by backend** — Added `on_progress` callback to `run_pipeline` and `_dispatch_phase`, `on_scene_done` to `_run_per_scene`. Wired through `pipeline_runner.py`. (S-1 from PR review)
- [x] **Web UI: Expand Storybook stories** — Fixed ReviewScreen stories for `onApproved` prop, added ZeroProgress ProgressBar story. (S-4 from PR review)
- [x] **Web UI: Server doesn't load existing `.env` at startup** — The `.env` file in the project root has valid API keys, and `_write_env_file()` writes to the same location. But `get_api_key_status` checks `os.environ`, which doesn't have the keys unless something loads the `.env` first. The frontend prompts for credentials even when `.env` already has them. Fix: add explicit `load_dotenv()` call in `create_app()` so existing keys are available immediately.
- [x] **Web UI: Artifact listing returns empty for analysis/bible/outline checkpoints** — `_PHASE_DIRS` in `routes_artifacts.py` maps `analysis` → `scenes/`, but `analysis.json` is written to the project root. Same issue likely affects `story_bible` and `outline` phases. Fix: map phases with project-level files (no per-scene asset in `PHASE_ASSET_MAP`) to the project root directory instead of a subdirectory.
- [x] **Web UI: Review screen shows wrong artifacts for per-scene phases** — Added `_PHASE_FILE_FILTER` for project-root phases (analysis, story_bible, outline, video_assembly) and image_prompts-specific filtering. Per-scene phases still show all files in `scenes/` — acceptable since each phase appends distinct filenames.
- [x] **Web UI: Image prompts not viewable at checkpoint** — Added `_export_image_prompts()` that writes scene image prompts from `project.json` as editable JSON files (`image_prompts_scene_NNN.json`) on demand. Preserves manual edits (skip existing files).
- [x] **Web UI: Video player and download broken on completion screen** — `final.mp4` is written to the project root, but `_PHASE_DIRS` mapped `video_assembly` → `segments/`. Server returned JSON 404, browser showed "Final.json". Fixed: mapped `video_assembly` → project root (empty string).
- [x] **Pipeline: Video fades out before narration ends** — Fixed: `effective_hold = max(end_hold_duration, fade_out_duration)` ensures the end hold is always at least as long as the fade-out, so the fade never overlaps narration audio. Applies to both single-segment and multi-segment videos.
- [x] **Web UI: Progress bar needs activity indicator** — Between `scene_progress` events, the progress screen gives no indication that work is happening. Fixed: ProgressBar now shows indeterminate animated sliding bar with "Working..." text when `scenesTotal === 0`. All phases start indeterminate; only switches to determinate "X / Y" when `scene_progress` events arrive. Phases without per-scene progress (analysis, image_prompts, narration_prep, etc.) stay indeterminate automatically.
- [x] **Web UI: Add ElevenLabs API key to settings** — Added `elevenlabs_api_key` to `ApiKeyUpdate` model, `elevenlabs_configured` to status response, ElevenLabs input to `ApiKeySetup.tsx`, and `.env` file write support.
- [x] **Pipeline: Add lead-in silence before narration starts** — Narration begins at 0.0s but the video fade-in takes 2s (`fade_in_duration`), so the viewer hears narration while the screen is mostly black. Fixed: added `lead_in_duration` field to `VideoConfig` (default 2.0s). `build_concat_command` now prepends `tpad=start_mode=clone` to video and `adelay` to audio, delaying narration until the image has faded in. Works for both single-segment and multi-segment videos.
- [ ] **Web UI: TTS artifact audio playback** — After TTS generation, users should be able to listen to narration audio for each scene before proceeding. Needs: API endpoint to serve TTS audio files, audio player component on the review screen, per-scene playback controls. Would let users catch pronunciation or pacing issues before video assembly.
- [ ] **Web UI: Navigate back to earlier pipeline phases** — Currently the pipeline only moves forward. Users may want to go back to an earlier phase (e.g., re-do narration after hearing TTS output). Requires: phase navigation UI, backend support for resetting a project to an earlier phase, re-running from that point. Significant design work needed — brainstorm when ready.
- [ ] **Web UI: List and resume existing projects** — Home page should show all existing projects with their status. Users should be able to select a project, pick a completed stage, and re-run the pipeline from that point. Enables iterating on a video until it's right. Ties into the "navigate back to earlier phases" item above — both need the same backend support for phase reset. Brainstorm when ready.
- [ ] **Pipeline: Narration still starts too early** — The 2.0s `lead_in_duration` default was added but narration still begins before the image is fully visible. May need a longer default (3-4s), or the lead-in should be tied to `fade_in_duration` so they stay in sync. Test with different values and adjust.
- [ ] **Pipeline: Story bible characters underused in image prompts** — Character descriptions from the story bible (analysis.json) are not sufficiently reflected in the generated image prompts. Images may not match character descriptions established in the bible. Need to brainstorm how to better inject character reference data into the image prompt generation step. Brainstorm when ready.
- [ ] **Web UI: Image review and per-image revision** — After image generation, users should be able to see all generated images at the checkpoint. If an image doesn't look right, they should be able to step back and regenerate specific ones (edit the prompt, regenerate, keep the rest). Needs: image gallery component on review screen, per-image regeneration backend support, prompt editing UI. Brainstorm when ready.
- [ ] **Pipeline: Last caption disappears too early** — The final caption vanishes as soon as the narrator stops speaking. When the last caption is a single word, it barely flashes on screen. The last caption should persist through the end hold / fade-out so viewers can read it. Brainstorm when ready.
- [ ] **Web UI: `approvePipeline` sends empty body when auto is undefined** — Sends `{}` instead of no body. Harmless (FastAPI parses as `ApproveRequest(auto=False)`) but wasteful. Low priority. (S-1 from code review)
- [ ] **Web UI: ProgressBar injects duplicate `<style>` tags** — Each ProgressBar instance injects its own `@keyframes` style block. Fine with one bar, but duplicates if multiple are visible. Consider lifting keyframes to a global stylesheet. Cosmetic only. (S-2 from code review)

## Backlog

Acknowledged items not yet scheduled.

### Seventh-Pass Review (PR7) — 2026-02-28

#### Group A: SSE & Pipeline Thread Lifecycle (3H, 3M)

- [x] [bug] **H-1: SSE generator hangs if pipeline thread dies without terminal event** — Added dead-thread detection: if bridge exists, not done, and `is_running()` is False, yields error event and returns. (routes_pipeline.py)
- [x] [bug] **H-2: Stale bridge and thread never cleared after pipeline finishes** — Added `finally` block in `_run_pipeline_safe` that clears `_active_thread` and `_active_bridge` under the lock. (pipeline_runner.py)
- [x] [bug] **M-1: SSE poll has no timeout when bridge is None** — Added 30s timeout counter; yields error event and returns if no bridge appears. (routes_pipeline.py)
- [x] [bug] **M-3: `_make_tts_provider` silently defaults to OpenAI for unknown providers** — Now raises `ValueError` for unknown provider names. (pipeline_runner.py)
- [x] [bug] **M-4: `_PHASE_DIRS` silently falls back to "scenes" for unmapped phases** — Replaced `.get(phase, "scenes")` with explicit lookup that raises HTTP 500 for unmapped phases. (routes_artifacts.py)
- [x] [test] **H-3: `pipeline_runner.py` has zero test coverage** — Added `test_web_pipeline_runner.py` with 8 tests covering `_make_tts_provider`, global cleanup, concurrent run guard, and `is_running` states.

#### Group B: Web Backend Hardening (2M)

- [x] [bug] **M-2: `_write_env_file` overwrites non-API-key content in `.env`** — Rewrote to parse-and-update: reads existing .env line-by-line, updates managed keys in place, preserves comments and user variables. Unset keys are removed. (routes_settings.py)
- [x] [refactor] **M-5: `_generate_project_id` duplicated between CLI and web** — Extracted `generate_project_id(mode, output_dir)` into `state.py`. Uses UTC consistently. Caps at 1000 attempts. Both CLI and web import from there. Web route converts RuntimeError to HTTP 409.

#### Group C: FFmpeg Edge Cases (2M)

- [x] [bug] **M-7: `fade_out_start` can go negative when music fade_out > remaining duration** — Clamped to non-negative with warning log when clamping occurs. (commands.py)
- [x] [bug] **M-8: Zero/negative image duration silently clamped without warning** — Added warning log in `_build_multi_image_command` when duration is negative, matching `build_concat_command` pattern. (commands.py)

#### Group D: Pipeline Code Quality (2M)

- [x] [bug] **M-6: `char_position_to_timestamp` doesn't guard against empty `word_char_offsets`** — Added ValueError guard at function entry. (image_timing.py)
- [x] [docs] **M-9: Three different undocumented resume strategies in `story_writer.py`** — Added/expanded inline comments explaining each strategy: scene metadata check in `write_scene_prose`, narration_prep_done.json tracker in orchestrator (already documented), changelog file existence in `critique_and_revise`.

#### Group E: Test Quality & Gaps (5M)

- [x] [test] **M-10: ~18 inline imports in `test_orchestrator.py`** — Hoisted all inline imports (json, subprocess, pathlib, CaptionResult/CaptionSegment/CaptionWord) to module level.
- [x] [refactor] **M-11: ~250 lines duplicated integration test boilerplate in `test_orchestrator.py`** — Extracted 5 shared helpers: `_make_claude_dispatch`, `_make_simple_caption_result`, `_make_timed_caption_result`, `_make_mock_subprocess_run`, `_make_mock_providers`. Net reduction of ~166 lines.
- [x] [test] **M-12: `on_progress`/`on_scene_done` callbacks have zero test coverage** — Added `TestRunPipelineProgressCallbacks` (2 tests) and `TestRunPerSceneCallback` (1 test) verifying phase_started, scene_progress, and on_scene_done callbacks.
- [x] [test] **M-13: `ProgressBridge` has no direct unit tests** — Reorganized into `TestProgressEvent` (2 tests) and `TestProgressBridge` (4 tests) covering fields, push/get, timeout, terminal/non-terminal is_done.
- [x] [test] **M-14: `os.environ` mutations leak past monkeypatch in `test_web_settings.py`** — Added autouse `_clean_managed_keys` fixture to both test classes, removed redundant per-test delenv calls.

#### Group E Review Findings (deferred)

- [ ] [test] **E-R1: FIFO ordering test dropped from `test_web_progress.py`** — Old `test_multiple_events_in_order` was removed during reorganization. Restore as `test_events_delivered_in_fifo_order` in `TestProgressBridge`. (test_web_progress.py)
- [ ] [refactor] **E-R2: `_make_claude_dispatch` raises `KeyError` instead of descriptive error** — `responses[tool_name]` gives unhelpful `KeyError`. Add guard: `if tool_name not in responses: raise ValueError(f"Unexpected tool_name: {tool_name}")`. (test_orchestrator.py:~130)
- [ ] [chore] **E-R3: `TERMINAL_EVENTS` not in `__all__` of `progress.py`** — Pre-existing gap exposed by new test imports. Add to `__all__` list. (progress.py:11)
- [ ] [style] **E-R4: Leading underscores on local variables `_image_tag_words` / `_music_words`** — Conventionally signals "private/unused" but these are immediately used. Remove underscores. (test_orchestrator.py)

#### Group F: React Frontend (5M)

- [ ] [bug] **M-15: No 404/catch-all route in React app** — Undefined paths render empty `<main>` with no feedback. Add `<Route path="*">` fallback. (App.tsx)
- [ ] [bug] **M-16: ReviewScreen `handleEdit` bypasses API client** — Uses raw `fetch()` without error handling. Non-200 responses load error HTML into textarea. Add `getArtifactContent` to API client or check `response.ok`. (ReviewScreen.tsx:40-49)
- [ ] [bug] **M-17: Double project creation if `startPipeline` fails** — `createProject` succeeds, `startPipeline` throws, form re-enabled. Clicking again creates a second project. Navigate to project page after create, or detect existing project. (CreatePage.tsx:30-37)
- [ ] [bug] **M-18: ApiKeySetup submit enabled with only one of two required keys** — Pipeline needs both Anthropic and OpenAI. Submit is enabled with just one. Validate both required keys are configured or provided. (ApiKeySetup.tsx:115)
- [ ] [test] **M-19: ReviewScreen test leaves `globalThis.fetch` patched without `afterEach` cleanup** — Mock leaks if assertion fails before restore. Use `vi.stubGlobal` + `vi.unstubAllGlobals`. (ReviewScreen.test.tsx:99-129)

#### Group G: Low-Severity Cleanup (36 items)

**Inline imports in tests (7):**
- [x] [test] `_build_audio_mix_filters` imported inline 7 times in `test_commands.py` — moved to module level
- [x] [test] `import logging` inline in `test_tts_generator.py` (3x) and `test_narration_tags.py` (1x) — moved to module level
- [x] [test] `import openai` inline in `test_tts_generator.py`, `test_image_generator.py`, `test_caption_generator.py` — moved to module level
- [x] [test] `SceneImagePrompt` imported inline in `test_orchestrator.py` — moved to module level
- [x] [test] `import logging` inline in `test_cli.py:1042` — moved to module level
- [x] [test] `from openai import ...` inline in `test_retry.py:275` — replaced by module-level `import openai` during `_OPENAI_TRANSIENT` consolidation
- [x] [test] `from story_video import __version__` inline in `test_models.py:693` — moved to module level

**Duplication (6):**
- [x] [refactor] `_OPENAI_TRANSIENT` defined identically in tts_generator.py, image_generator.py, caption_generator.py — consolidated into `story_video.utils.openai_compat.OPENAI_TRANSIENT`
- [x] [refactor] Web test `output_dir`/`client` fixtures duplicated in 5 test files — extracted to `tests/conftest.py`
- [x] [test] Duplicated `_resolve_project_dir` traversal test in `test_web_artifacts.py` — removed, kept in `test_web_projects.py` only
- [ ] [test] `MockEventSource` duplicated in `ProjectPage.test.tsx` and `useProgressStream.test.ts` — extract shared helper
- [x] [refactor] `_populate_image_tags` and `_populate_music_tags` near-identical — only 2 cases, below extraction threshold; noted for future
- [ ] [refactor] ReviewScreen auto-approve handler duplicates `handleApprove` logic — parameterize with `auto` flag

**Missing tests (4):**
- [x] [test] `with_retry` parameter validation guards untested (retry.py:72-77) — added 3 tests
- [x] [test] `generate_project_id` 1000-attempt safety cap untested (state.py) — added 1 test
- [x] [test] Bracket escaping in `subtitle_filter` untested (subtitles.py:278-279) — added 1 test
- [x] [test] `_export_image_prompts` error and idempotency paths untested (routes_artifacts.py:93-116) — added 2 tests

**Edge cases (4):**
- [x] [low] `AudioCueSpec` fields have no validation — added docstring noting upstream `AudioAsset` validates; `AudioCueSpec` is an internal DTO
- [x] [low] `_scan_project_dirs` does not handle `PermissionError` (cli.py) — wrapped `iterdir()` in try/except `OSError`
- [ ] [low] `useProgressStream` events array grows unboundedly — cap or show only recent phase
- [ ] [low] `ProjectPage` retry catch silently swallows error — show error message

**Consistency (3):**
- [x] [refactor] `_resolve_audio_cues` raises `KeyError` instead of `ValueError` — changed to `ValueError` for consistency
- [x] [low] `state.save()` patterns differ: single-save in TTS/image/caption vs double-save in video_assembler — added comment explaining double-save is intentional (crash recoverability)
- [x] [test] Mixed `@patch` decorator vs `monkeypatch` in `test_commands.py` for same function — accepted as-is; style preference, not a bug

**Documentation & readability (5):**
- [x] [docs] Unused `prose_bare` variable in caption_generator destructuring — replaced with `_` (caption_generator.py)
- [x] [docs] Missing inline comment for `-shortest` flag absence in multi-image command — added comment (commands.py)
- [ ] [docs] `retryCount` scope in `useProgressStream` is correct but non-obvious — add comment
- [x] [docs] `image_prompt_writer.py` missing comment explaining missing-check double duty — added comment
- [x] [docs] Orchestrator module docstring phase counts fragile if phases change — replaced with constant references (orchestrator.py)

**Dead code (4):**
- [x] [chore] Multi-image `i==0` special case in xfade offset is redundant — simplified to unified cumulative formula (commands.py)
- [ ] [chore] Empty `index.css` imported but unused — remove file and import
- [ ] [chore] `getHealth` and `deleteProject` unused by any React component — add comment or remove
- [x] [low] Unreachable empty-event guard in `generate_ass_content` — added defensive comment explaining guard intent (subtitles.py)

**Frontend (4):**
- [ ] [chore] Duplicate `react-router-dom` import in SettingsPage.tsx — combine into one line
- [ ] [test] `act()` warnings in Layout.test.tsx and App.test.tsx — use `waitFor`
- [ ] [chore] `console.log` in Storybook stories instead of `@storybook/addon-actions`
- [ ] [a11y] Missing `aria-label` on ProgressBar, ReviewScreen textarea, video element

**Other (2):**
- [x] [low] `ClaudeClient` hardcodes model default `claude-sonnet-4-5-20250929` — added docstring note explaining why (instantiated before config load)
- [x] [low] Cost estimation assumes 1 image per scene — added docstring note about limitation and future `image_count` param

### Sixth-Pass Review (PR6) — 2026-02-21

- [x] [fix] `_run_narration_prep` missing `state.save()` — data loss risk on crash (orchestrator.py) (PR6-M1)
- [x] [fix] Inconsistent `narration_text` fallback — `or` vs `is not None` (orchestrator.py) (PR6-M2)
- [x] [fix] `parse_narration_segments` accepts whitespace-only text silently (narration_tags.py) (PR6-M3)
- [x] [fix] `create_outline` silent fallback for missing `source_stats` (story_writer.py) (PR6-M4)
- [x] [docs] PR4-8 line reference points to wrong function (BUGS_AND_TODOS.md) (PR6-M5)
- [x] [test] `test_narration_prep.py` tests private symbols directly — removed TestPromptConstants, documented remaining deviations (PR6-M6)
- [x] [test] `test_caption_generator.py` tests private helpers directly — documented deviations (PR6-M7)
- [x] [low] 38 low-severity findings from PR6 review — documentation improvements, defensive guards, unused exports, minor test gaps. Superseded; will be covered by next whole-codebase review.

### Fifth-Pass Review (PR5) — 2026-02-20

- [x] [refactor] `_mood_to_elevenlabs_text` reverse-parses the output of `_mood_to_instructions` — fragile coupling. Added `mood` param to `TTSProvider.synthesize()` Protocol and both providers. ElevenLabs uses `mood` directly; reverse-parsing eliminated. (PR5-1)
- [x] [limitation] `write_scene_prose` resume: running summary for skipped scenes uses title-only context instead of full prose summary — added `summary` field to Scene model, persisted via `add_scene()`, used on resume with title-only fallback for backward compat. (PR5-2)
- [x] [bug] `OutputConfig.directory` is defined in `AppConfig` but never read — removed `OutputConfig` class, `output` field from `AppConfig`, and `output:` section from config.yaml. (PR5-3)

### Third-Pass Review (PR4) — 2026-02-18

**Pipeline orchestrator:**

- [x] [refactor] `_dispatch_phase` is a 70-line if/elif chain with 9x duplicated provider-guard pattern — replaced with dispatch table for Claude phases (orchestrator.py) (PR4-1)
- [x] [bug] `_run_narration_prep` iterates all scenes instead of skipping completed — added `narration_prep_done.json` tracker to skip already-processed scenes on retry (orchestrator.py) (PR4-2) [supersedes PR2-15 doc-only resolution]
- [x] [refactor] `.append()` in loop instead of `.extend()` in `_run_narration_prep` pronunciation_guide accumulation (orchestrator.py) (PR4-3)

**Config / models:**

- [x] [bug] `PipelineConfig.max_retries` and `retry_base_delay` are never read — removed unused fields from PipelineConfig (models.py) (PR4-4)
- [x] [chore] `PipelineConfig.save_originals_on_revision` is never read — removed unused field from PipelineConfig (models.py) (PR4-5)
- [x] [bug] `CaptionResult.duration` missing `ge=0` validator — added `Field(ge=0)` for consistency with CaptionWord/CaptionSegment (models.py) (PR4-6)

**Story writer:**

- [x] [refactor] `split_scenes` and `write_scene_prose` skip IN_PROGRESS transition for TEXT asset — added IN_PROGRESS transition before COMPLETED for consistency (story_writer.py) (PR4-7)
- [x] [docs] `critique_and_revise` resume heuristic is fragile — already documented in code comments at lines 938-940 (critique_and_revise resume heuristic); no further action needed (PR4-8)
- [x] [docs] `flag_narration` `str.replace()` exact match may miss whitespace-variant Claude output — already documented with warning fallback at lines 496-508; no further action needed (PR4-9)

**TTS generator:**

- [x] [refactor] `_mood_to_elevenlabs_text` fragile string prefix/suffix removal — added coupling note comment tying the two functions together; Protocol change deferred as too invasive for the risk (tts_generator.py) (PR4-10)

**FFmpeg:**

- [x] [bug] `subtitle_filter` path escaping — verified single-quote wrapping already handles `:` and `;` correctly; added tests documenting this (subtitles.py) (PR4-11)
- [x] [refactor] `_RESOLUTION_RE` regex consolidated — filters.py now imports from models.py instead of redefining (PR4-12)

**CLI:**

- [x] [bug] `_read_text_input` accepts directories silently — added `is_dir()` check that raises ValueError (cli.py) (PR4-13)
- [x] [bug] `resume` and `status` commands don't catch `ValidationError` — added to except clauses (cli.py) (PR4-14)
- [x] [refactor] Private `_`-prefixed symbols imported cross-module — renamed `_RESOLUTION_RE`→`RESOLUTION_RE`, `_HEX_COLOR_RE`→`HEX_COLOR_RE`, `_parse_resolution`→`parse_resolution` (models.py, filters.py, subtitles.py) (PR4-15)

**Image generation:**

- [x] [limitation] `generate_image_prompts` sends all scene prose in single Claude call — acknowledged scaling limit for 50+ scene stories; not in scope currently (image_prompt_writer.py) (PR4-16)

**Tests — coverage gaps:**

- [x] [test] No orchestrator integration test for creative flow — added `test_full_creative_flow_data_flow` covering all 11 phases with mock Claude/TTS/image/caption providers (test_orchestrator.py) (PR4-17)
- [x] [test] No test for creative-flow checkpoint pauses — added `test_creative_flow_pauses_after_analysis` and `test_creative_flow_pauses_after_story_bible` (test_orchestrator.py) (PR4-18)
- [x] [test] `test_cost.py` boundary test for zero/negative duration — StoryConfig already validates `gt=0` via Pydantic; no separate test needed (PR4-19)

**Tests — structure and cleanup:**

- [x] [test] Duplicated OpenAI error construction boilerplate — extracted `make_openai_rate_limit_error`, `make_openai_server_error`, `make_openai_connection_error` to `tests/error_factories.py` (PR4-20)
- [x] [test] Inline imports in `test_models.py` — moved `CaptionWord`/`CaptionSegment`/`CaptionResult` to module-level imports (PR4-21)
- [x] [test] Heavy mock stacking in orchestrator tests — accepted as deviation; mock count matches provider count, no cleaner alternative without over-abstracting (PR4-22)
- [x] [test] Multi-assertion defaults tests — accepted as deviation for defaults-verification pattern; parametrize would fragment readability without reducing risk (PR4-23)
- [x] [test] Fixture naming inconsistency — accepted; names match what they mock (`mock_openai` for OpenAI client, `mock_client` for generic client), renaming adds churn without value (PR4-24)
- [x] [test] Inline imports in `test_cli.py` — moved `AppConfig`, `InputMode`, `ProjectState`, etc. to module-level imports (PR4-25)
- [x] [test] Chained fixtures need docstrings — accepted; fixture chain is 3 levels deep, not 4, and each fixture has a descriptive name (PR4-26)
- [x] [test] Loop to parametrize — converted `test_creative_phases_require_claude_client` to `@pytest.mark.parametrize` (PR4-27)
- [x] [test] `TestExtractTags` in wrong file — moved from `test_narration_prep.py` to `test_narration_tags.py` (PR4-28)

### Second-Pass Review — 2026-02-18

**Test convention violations:**

- [x] [test] Move 32 inline imports in `test_narration_prep.py` to module level — PR2-6 was marked done but fix did not land (PR3-1)
- [x] [test] Split multi-assertion tests in `test_image_generator.py:103,130` — 8 and 5 assertions, PR-25 not applied here (PR3-2)
- [x] [test] Split multi-assertion tests in `test_tts_generator.py:114,502` — 5 and 4 assertions, PR-25 not applied here (PR3-3)
- [x] [test] Split residual 5-assertion `test_word_count_and_timing` in `test_caption_generator.py:160` — PR2-3 split left this (PR3-4)

**Validation consistency:**

- [x] [bug] `CaptionSegment.start/end` missing `ge=0` — inconsistent with `CaptionWord` which has it (models.py) (PR3-5)

**Duplicated patterns:**

- [x] [refactor] `_HEX_COLOR_RE` duplicated in `filters.py` and `models.py` — consolidate (PR3-6)
- [x] [refactor] Inline resolution regex `r"^\d+x\d+$"` in `models.py` could use `_parse_resolution` from filters.py or shared validator (PR3-7)

**Missing test coverage:**

- [x] [test] Add test for PR2-9 empty-text warning log in `_run_narration_prep` (orchestrator.py) (PR3-8)

**Stale documentation:**

- [x] [docs] `_run_narration_prep` docstring has duplicate paragraph (orchestrator.py) (PR3-9)
- [x] [docs] `retry.py` module docstring still mentions "OpenAI-specific" despite PR2-13 removal (PR3-10)

**Error handling:**

- [x] [bug] `resume` command missing `logger.exception` on pipeline error path (cli.py) (PR3-11)
- [x] [bug] `estimate` command catches bare `Exception` instead of specific types (cli.py) (PR3-12)

**Minor cleanup:**

- [x] [refactor] `strip_narration_tags` uses inline regex instead of compiled `_TAG_PATTERN` (narration_tags.py) (PR3-13)
- [x] [test] `strip_narration_tags` test in `test_story_writer.py` should be in `test_narration_tags.py` (PR3-14)
- [x] [refactor] Inline resolution regex in `models.py` could reference shared helper (PR3-15)

### First-Pass Review — 2026-02-18

**Test quality:**

- [x] [test] Delete redundant `_patch_sleep` fixture in `test_claude_client.py:67-70` — missed by PR-12 cleanup (PR2-1)
- [x] [test] Fix global subprocess patches in `test_commands.py:311,320` — use module-level patch like rest of file (PR2-2)
- [x] [test] Split 12-assertion `test_maps_response_to_caption_result` in `test_caption_generator.py:133-156` — missed by PR-25 (PR2-3)
- [x] [test] Add `start_phase` after `fail_phase` retry test in `test_state.py` (PR2-4a)
- [x] [test] Add `get_next_phase` ValueError fallback branch test in `test_state.py` (PR2-4b)
- [x] [test] Add `_display_outcome` else branch (PENDING/IN_PROGRESS) test in `test_cli.py` (PR2-4c)
- [x] [test] Add direct unit tests for `_group_words_into_events` boundary cases in `test_subtitles.py` (PR2-5)
- [x] [test] Move inline imports in `test_narration_prep.py` to module level to match convention (PR2-6)

**Duplicated logic:**

- [x] [refactor] Consolidate 3 independent tag regex patterns into `narration_tags.py` — export `strip_narration_tags()`, import in `narration_prep.py` and `story_writer.py` (PR2-7)
- [x] [refactor] Extract `_parse_resolution()` helper — `resolution.split("x")` duplicated in `filters.py:23,41` and `subtitles.py:167` (PR2-8)

**Fail-fast / error handling:**

- [x] [bug] `_run_narration_prep` silently skips scenes with no text — should warn or raise (orchestrator.py:276-278) (PR2-9)
- [x] [bug] Negative xfade offset when segment duration < transition_duration — FFmpeg rejects with cryptic error (commands.py:224-226) (PR2-10)
- [x] [refactor] Simplify `start_phase` guard — doesn't catch impossible states like IN_PROGRESS with no phase (state.py:254) (PR2-11)
- [x] [refactor] Narrow bare `Exception` catches in CLI `create` command to documented exception types (cli.py:332-343) — extends CLI-S7 (PR2-12)

**Coupling / consistency:**

- [x] [refactor] Move `OPENAI_TRANSIENT_ERRORS` out of generic `retry.py` into consuming pipeline modules (PR2-13)
- [x] [refactor] Remove model type re-exports from `caption_generator.py` `__all__` — no other pipeline module does this (PR2-14)
- [x] [docs] `_run_narration_prep` processes ALL scenes instead of using `get_scenes_for_processing()` — add documenting comment or track prepped scenes (orchestrator.py:270-298) (PR2-15)

**Small fixes:**

- [x] [bug] `_mood_to_instructions` grammar — "a excited" should be "an excited" for vowel moods (tts_generator.py:190) (PR2-16)
- [x] [chore] ElevenLabs speed warning logged on every call — should log once (tts_generator.py:166-170) (PR2-17)
- [x] [chore] `font_fallback` field in `SubtitleConfig` is never used — remove or wire into ASS output (models.py) (PR2-18)
- [x] [chore] Dead CLI parameters `topic` and `style_reference` — remove until original/inspired_by modes implemented (PR2-19)
- [x] [chore] `_resolve_voice` return value discarded without comment — add `_` assignment or comment (narration_tags.py:141) (PR2-20)
- [x] [docs] `parse_story_header` closing `---` delimiter fragile with YAML containing `---` — add comment noting limitation (narration_tags.py:48-49) (PR2-21)
- [x] [bug] `_format_ass_time` produces garbage for negative timestamps — add `ge=0` validators on `CaptionWord.start/end` (models.py, subtitles.py) (PR2-22)

### Project Review — 2026-02-17

**High priority:**

- [x] [bug] `estimate_cost` crashes with ElevenLabs TTS models — returns $0.00 with descriptive note instead of raising (PR-1)
- [x] [security] Path injection in `subtitle_filter` — escape backslashes and single quotes in ASS file paths (PR-2)

**Medium priority:**

- [x] [bug] `_dispatch_phase` does not validate that providers are non-None — provider-dependent phases produce opaque `AttributeError: NoneType has no attribute 'synthesize'` instead of descriptive error when provider is None. Add fail-fast guards. (PR-3)
- [x] [bug] `ImageConfig.size` lacks format validation — `VideoConfig.resolution` has a `@field_validator` enforcing `WIDTHxHEIGHT` but `ImageConfig.size` does not. Invalid values pass validation and fail at the API. (PR-4)
- [x] [refactor] Provider instantiation duplicated between `create` and `resume` CLI commands — extract `_run_with_providers(state)` helper. (PR-5)
- [x] [refactor] Duplicated format-to-extension logic — `tts_generator.py` has `_format_to_extension()` but `caption_generator.py` and `video_assembler.py` inline `output_format.split("_")[0]`. Move to shared location or add `TTSConfig.file_extension` property. (PR-6)
- [x] [bug] `assemble_video` silently proceeds with zero completed segments — empty segment list passed to `build_concat_command` produces cryptic error. Add explicit guard. (PR-7)
- [x] [bug] `probe_duration` crashes on empty/non-numeric stdout — `float(result.stdout.strip())` raises bare `ValueError` for corrupt files. Wrap and re-raise as `FFmpegError` with file path context. (PR-8)
- [x] [bug] `build_concat_command` does not validate `segment_paths` and `segment_durations` have same length — mismatch causes `IndexError` deep in xfade calculation. Add length guard. (PR-9)
- [x] [bug] Sentence-ending period lost after abbreviations — superseded by LLM-based TTS text prep (regex code deleted). (PR-10)
- [x] [test] Orchestrator integration test gap — `test_runs_all_phases_without_pausing` mocks 9 internal functions, can't detect wiring mistakes. Add integration test that only mocks external APIs and exercises actual data flow between phases. (PR-11)
- [x] [refactor] `_patch_sleep` fixture duplicated in three test files — move to `conftest.py`. (PR-12)

**Low priority:**

- [x] [chore] Delete dead file `ffmpeg/transitions.py` — empty, transition logic merged into `commands.py`. (PR-13)
- [x] [bug] `_hex_to_ass_color` does not validate input format — silently produces garbage for malformed hex like `"#FFF"` or `"red"`. (PR-14)
- [x] [bug] No cross-field validation on scene word count bounds — `scene_word_min`, `scene_word_target`, `scene_word_max` can be set in contradictory order. Add `@model_validator`. (PR-15)
- [x] [bug] `SubtitleConfig.color` and `outline_color` lack hex format validation — bare `str` type, invalid values produce opaque FFmpeg errors. (PR-16)
- [x] [docs] Stale docstring in `state.py:418` lists IMAGE_PROMPTS as having no per-scene asset — contradicts `PHASE_ASSET_MAP`. (PR-17)
- [x] [bug] `--voice` option on `estimate` command is misleading — help text says "(affects cost)" but voice has no effect on cost calculation. Remove option or fix help text. (PR-18)
- [x] [chore] `api_retry` exported but never used in production code — zero consumers in `src/`. Consider removing. (PR-19)
- [x] [bug] `with_retry` default `retry_on=(Exception,)` is overly broad — catches `ValueError`, `TypeError`, etc. All callers specify explicitly, but default is a footgun for new callers. (PR-20)
- [x] [chore] Inline regex not pre-compiled in `text.py:495` — `re.sub(r"  +", " ", result)` breaks file convention of module-level compiled patterns. (PR-21)
- [x] [chore] Missing `logging.getLogger(__name__)` in `image_generator.py`, `video_assembler.py`, `caption_generator.py` — every other pipeline module has one. (PR-22)
- [x] [chore] No logging configuration in CLI — logger created but no handler configured, debug logs vanish silently. Add `--verbose` flag. (PR-23)
- [x] [test] Multiple test gaps: `_check_preservation` edge cases, `_strip_narration_tags` dedicated tests, `_format_to_extension` direct tests, CLI `_make_tts_provider` unknown provider path, `_apply_dotted_overrides` error path, `parse_narration_segments` with empty input, `build_concat_command` with short/zero-duration segments, `subtitle_filter` with special-character paths, `probe_duration` with non-numeric output. (PR-24)
- [x] [test] Multiple-assertions-per-test convention violations in `test_caption_generator.py`, `test_image_generator.py`, `test_tts_generator.py` — split composite assertions into focused tests. (PR-25)

---

- [x] [feature] LLM-based TTS text prep — replaced regex narration prep with Claude API calls for context-aware pronunciation preparation. Single `generate_structured()` call per scene handles abbreviations, numbers, punctuation, and unusual names. Produces JSON changelog. NARRATION_PREP is now a checkpoint phase. Old regex code deleted. (narration_prep.py, orchestrator.py)
- [x] [feature] Implement inspired_by mode — analysis, bible, outline, prose, critique/revision (pipeline/story_writer.py, see docs/plans/2026-02-18-inspired-by-design.md)
- [x] [feature] Inline image tags — define image prompts in YAML header, reference with `**image:tag**` in story text. Decouples image transitions from scene boundaries, gives authors direct control over visuals. Requires video assembler refactor for multiple images per scene.
- [x] [feature] Background music / sound effects — overlay audio tracks at specified points in narration with volume and duration control. Music files supplied by user. FFmpeg amix filter for mixing. YAML `audio:` map defines assets, `**music:key**` tags in story text reference them. Per-track filter chains (adelay, volume, aloop+atrim, afade) mixed via amix. Caption-aligned timing via bisect on word offsets. Per-scene scope only.

- [ ] [feature] FFmpeg concat fallback for non-MP3/opus audio formats — when audio_transition_duration uses WAV, FLAC, or other formats that don't support raw byte concatenation, use `ffmpeg -f concat` to join segment audio files. Low priority: MP3 and opus (the only realistic TTS output formats) support byte concatenation natively.
- [x] [chore] Add ElevenLabs TTS provider option (merged to main)
- [x] [test] Boundary value tests for `_int_to_words` and `_year_to_words` — no longer applicable, regex code deleted (T8)
- [ ] [feature] Add async retry support when async API calls are introduced (R4)
- [x] [chore] Consider exporting rate constants in cost.py `__all__` if needed by CLI layer (C4) — rate constants not imported outside cost.py; no action needed
- [x] [docs] Update design.md TTS cost example ($7.41 → $7.42) to match mathematically correct rounding (C5) — fixed $7.41 → $7.43 in design.md (local-only, file is gitignored)
- [x] [test] Add tests for partial override behavior in estimate_cost (only scene_count or only character_count) (C7)
- [x] [test] Strengthen adapt mode format test to verify Claude rate range, not just string containment (C8)
- [x] [test] Add retry exhaustion test for ClaudeClient (4 consecutive transient errors → original exception) (CC-S2) — already implemented at test_claude_client.py:398-438 (both generate and generate_structured)
- [x] [chore] Consider exporting `TRANSIENT_ERRORS` in claude_client.py `__all__` if needed by orchestrator (CC-S3) — TRANSIENT_ERRORS not imported outside claude_client.py; no action needed
- [x] [test] Add explicit encoding="utf-8" to test fixture source file writes for consistency (SW-S1) — added encoding="utf-8" to all 17 .write_text() calls in test fixtures
- [x] [test] Add Unicode content test for preservation check (accented chars, em dashes, curly quotes) (SW-S3) — added TestPreservationCheckUnicode with accented chars and Unicode punctuation tests
- [x] [refactor] Consider defensive access for missing "scenes" key in Claude response (SW-S4) — direct dict access is fail-fast by design; .get() would mask malformed Claude responses
- [x] [test] Add test for original_text not found in scene narration_text during autonomous fix (FN-S2) — added TestFlagNarrationAutonomousFixNotFound with warning log assertion
- [x] [refactor] Extract flags file writing into `_write_flags_report()` helper if format grows (FN-S3) — 18 lines, 5 fields, no reuse; extraction not warranted yet
- [ ] [feature] Batched concatenation for 60+ segment videos — group segments into chapters of 10-15, concat each chapter, then concat chapters. Only needed if single-pass xfade chain hits FFmpeg limits with very long videos. Current single-pass approach works fine for 25-scene videos. (VA-D1)
- [ ] [test] Add @pytest.mark.slow integration tests that run actual FFmpeg on tiny inputs (1s silent audio, 10x10 image) to catch filter graph syntax errors and codec issues. Requires FFmpeg installed. (VA-D2)
- [x] [refactor] Extract `_make_tts_provider()` helper to deduplicate provider instantiation in create/resume commands (CLI-S1)
- [x] [chore] `_find_most_recent_project` compares ISO 8601 timestamp strings lexicographically — fragile if hand-edited project.json uses non-ISO format (CLI-S2) — ISO 8601 is lexicographically sortable; comparison is correct by design
- [x] [chore] Add `exists=True` to `--config` Typer option in create and estimate commands for immediate path validation (CLI-S4) — added exists=True to both create and estimate --config options
- [x] [test] Add direct unit tests for `_status_icon` covering all 4 statuses and fallback path (CLI-S5) — added test_fallback_for_unknown_status covering unknown status path
- [x] [refactor] Narrow `create` command exception handler from bare `Exception` to `FileExistsError` for `ProjectState.create()` (CLI-S7)
- [x] [chore] Verify GPT Image 1.5 pricing — current code rates (low: $0.020, medium: $0.050, high: $0.200) may not match latest OpenAI pricing (CR-8) — updated low tier from $0.020 to $0.013, added verification date 2026-02-21
- [ ] [refactor] Cost rate table key collision risk — IMAGE_COST_PER_IMAGE dict merges GPT Image tiers (low/medium/high) and DALL-E tiers (standard/hd) in one flat dict; if a future model reuses a tier name, values would collide. Consider nested dict keyed by model family. (CR-9)
- [x] [refactor] `assemble_scene` re-parses story header from `source_story.txt` per scene with audio cues — added `story_header` keyword argument, orchestrator passes the already-parsed header. Removed file I/O and `parse_story_header` import from video_assembler. (BM-1)
- [x] [refactor] Bisect-based timing resolution duplicated between `_resolve_audio_cues` (video_assembler.py) and `compute_image_timings` (image_timing.py) — extracted `build_word_char_offsets()` and `char_position_to_timestamp()` into image_timing.py, both callers now use shared helpers. (BM-2)

## Resolved

Completed items awaiting migration to VERSION_HISTORY.md at next release.

- [x] [enhancement] Image prompt character consistency — added characters array to analysis schema, added ANALYSIS phase to adapt mode, image prompt writer injects character reference from analysis.json (models.py, story_writer.py, image_prompt_writer.py)
- [x] [feature] Implement original mode — same creative flow as inspired_by but with brief/prompt input. ANALYSIS phase uses BRIEF_ANALYSIS_SYSTEM prompt, source_stats from config. CLI --source-material renamed to --input. (story_writer.py, cli.py)
- [x] [feature] Add marker-based scene splitting as early-exit path in split_scenes — `**scene:Title**` tags auto-detected, splits locally without Claude call. Text before first tag → "Opening" scene. (story_writer.py)
- [x] [feature] Pause tags — `**pause:0.5**` inserts silence into narration audio. Variable duration, MP3 silence generation, narration prep preservation. (narration_tags.py, models.py, tts_generator.py, narration_prep.py)
- [x] [bug] Captions missing quotation marks around spoken dialogue — replaced segment-based `_reconcile_punctuation` with prose-based two-pointer alignment that restores all punctuation including quotation marks from `scene.prose` (pipeline/caption_generator.py)
- [x] [bug] Audio overlap at scene transitions — decoupled video xfade (1.5s) from audio acrossfade (0.05s) to prevent narration overlap (ffmpeg/commands.py, models.py)
- [x] [feature] Implement Pydantic data models (models.py)
- [x] [feature] Implement configuration loading and merging (config.py)
- [x] [feature] Implement project state management (state.py)
- [x] [feature] Implement retry decorators with tenacity (utils/retry.py)
- [x] [feature] Implement cost estimation logic (cost.py)
- [x] [feature] Implement text utilities and narration prep (utils/text.py)
- [x] [feature] Implement Claude API client wrapper (pipeline/claude_client.py)
- [x] [feature] Implement story writer adapt flow — scene splitting + narration flagging (pipeline/story_writer.py)
- [x] [feature] Implement TTS generator with provider abstraction (pipeline/tts_generator.py)
- [x] [feature] Implement image generator with GPT Image 1.5 support (pipeline/image_generator.py)
- [x] [feature] Implement caption generator with Whisper (pipeline/caption_generator.py)
- [x] [feature] Implement FFmpeg command building (ffmpeg/commands.py)
- [x] [feature] Implement video filters — blur backgrounds, still image scaling (ffmpeg/filters.py)
- [x] [feature] Implement crossfade transitions (ffmpeg/transitions.py — merged into commands.py)
- [x] [feature] Implement subtitle rendering (ffmpeg/subtitles.py)
- [x] [feature] Implement video assembler — per-scene segments and final assembly (pipeline/video_assembler.py)
- [x] [refactor] Move `_make_replacer` closure out of loop body in text.py (T7)
- [x] [refactor] Wrap module-level abbreviation pattern loop in builder function (T9)
- [x] [chore] Align `PipelineConfig.retry_base_delay` int→float (R3)
- [x] [refactor] Pass `model` through ImageProvider.generate() Protocol (IMG-R1)
- [x] [feature] Implement pipeline orchestrator — phase sequencing, resume, checkpoints (pipeline/orchestrator.py)
- [x] [feature] Implement image prompt writer — Claude structured output for DALL-E prompts (pipeline/image_prompt_writer.py)
- [x] [feature] Add IMAGE_PROMPT asset type to dependency chain (models.py, state.py)
- [x] [feature] Implement CLI commands — create, resume, estimate, status, list with Rich output (cli.py)
- [x] [feature] Multi-voice TTS with inline tags — YAML front matter, voice/mood parsing, per-segment synthesis, ElevenLabs provider (models.py, narration_tags.py, tts_generator.py, orchestrator.py, cli.py)
- [x] [refactor] Extract `_make_tts_provider()` helper to deduplicate provider instantiation in create/resume (cli.py)
- [x] [fix] Validate StoryHeader.default_voice exists in voices map (models.py)
- [x] [fix] Guard multi-voice byte concat for non-MP3/opus formats (tts_generator.py)
- [x] [fix] Validate unknown TTS provider names fail fast (cli.py)
- [x] [fix] Log and re-raise malformed YAML header errors in orchestrator (orchestrator.py)
- [x] [refactor] Extract _resolve_voice helper to deduplicate narration_tags (narration_tags.py)
- [x] [refactor] Deduplicate tag regex — export has_narration_tags() (narration_tags.py, tts_generator.py)
- [x] [bug] `estimate_cost` crashes with ElevenLabs TTS models — returns $0.00 with descriptive note instead of raising (PR-1)
- [x] [security] Path injection in `subtitle_filter` — escape backslashes and single quotes in ASS file paths (PR-2)
- [x] [bug] `_dispatch_phase` does not validate that providers are non-None — add fail-fast guards (PR-3)
- [x] [bug] `ImageConfig.size` lacks format validation — add `@field_validator` enforcing `WIDTHxHEIGHT` (PR-4)
- [x] [refactor] Provider instantiation duplicated between `create` and `resume` — extract `_run_with_providers` helper (PR-5)
- [x] [refactor] Duplicated format-to-extension logic — add `TTSConfig.file_extension` property (PR-6)
- [x] [bug] `assemble_video` silently proceeds with zero completed segments — add explicit guard (PR-7)
- [x] [bug] `probe_duration` crashes on empty/non-numeric stdout — wrap as `FFmpegError` (PR-8)
- [x] [bug] `build_concat_command` does not validate list lengths — add length guard (PR-9)
- [x] [refactor] `_patch_sleep` fixture duplicated in three test files — move to `conftest.py` (PR-12)
- [x] [test] Orchestrator integration test — full pipeline data flow with only external APIs mocked (PR-11)
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
- [x] [feature] Inline image tags — YAML header `images:` map defines image prompts, `**image:key**` tags in story text reference them. Tag parsing with character offsets, caption-aligned image timing, multi-image FFmpeg xfade filter graph, minimum display duration validation. Backward compatible — scenes without tags work identically to before. (models.py, narration_tags.py, image_timing.py, image_prompt_writer.py, image_generator.py, video_assembler.py, commands.py, orchestrator.py)
- [x] [feature] Background music / sound effects — YAML `audio:` map defines assets (`file`, `volume`, `loop`, `fade_in`, `fade_out`), `**music:key**` tags in story text reference them. Per-track FFmpeg filter chains (adelay, volume, aloop+atrim, afade) mixed via amix. Caption-aligned timing via bisect on word offsets. Per-scene scope. (models.py, narration_tags.py, commands.py, video_assembler.py, orchestrator.py)

## Session Notes

### Session — 2026-02-18

**Stopped after:** Implemented ORIGINAL mode (6 tasks via subagent-driven development). Ran full end-to-end pipeline with `original-story.txt` — produced `output/original-2026-02-18/final.mp4`. Completed 4th whole-codebase review (PR4, 28 findings — all resolved). 897 tests passing.

**What was done:** Built ORIGINAL mode as minimal delta from INSPIRED_BY — same 11-phase creative flow, only ANALYSIS prompt and source_stats computation differ. Renamed `--source-material` to `--input` (clean break). Removed ORIGINAL guard in CLI. Added integration test covering full data flow. Updated README and backlog. Also resolved all 28 PR4 findings (dispatch table, narration prep tracker, unused config fields, etc.).

**Next up:** No blocking work. Backlog items of interest: caption quotation marks bug, image prompt character consistency, marker-based scene splitting, inline image tags.

**Open questions:** None

### Session — 2026-02-17

**Stopped after:** Completed LLM-based TTS text prep feature (8 tasks). Project review (25 items — all resolved). On branch `feat/llm-tts-text-prep`, pending merge. 777 tests passing.

**What was done:** Replaced regex-based narration prep (`text.py` — 538 lines) with LLM-based `narration_prep.py` using `ClaudeClient.generate_structured()`. Added NARRATION_PREP as checkpoint phase. Pronunciation guide accumulates across scenes. Tag validation with retry-once-then-fail. Deleted old regex code and tests.

**Open questions:** None

### Session — 2026-02-16

**Stopped after:** Completed multi-voice TTS feature (8 tasks) and hardening pass (7 tasks). Both merged to main. 753 tests passing.

**Next up:** The multi-voice TTS pipeline is complete. Next logical steps are either: (1) implement the creative flow (story_writer.py — analysis, bible, outline, prose, critique), or (2) run a second end-to-end test with a multi-voice source story to exercise the new feature in production.

**Open questions:** None
