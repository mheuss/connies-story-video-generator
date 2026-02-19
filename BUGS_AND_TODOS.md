# Bugs and Todos

## Active

Items committed to the current sprint/cycle.

## Backlog

Acknowledged items not yet scheduled.

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
- [x] [docs] `critique_and_revise` resume heuristic is fragile — already documented in code comments at line 815-817; no further action needed (PR4-8)
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
- [ ] [limitation] write_scene_prose resume: running summary for skipped scenes uses title-only context instead of full prose summary — weaker context for Claude on subsequent scenes after resume (story_writer.py)
- [ ] [enhancement] Image prompt character consistency — image generation models have no cross-image memory, so character appearances often drift from story descriptions (e.g. female soldiers rendered as male). Extract a character reference sheet (name, appearance, clothing, distinguishing features) from the story bible and inject it into every image prompt. This would give the image model explicit visual anchors instead of relying on narrative context alone. (pipeline/image_prompt_writer.py, pipeline/story_writer.py)
- [x] [feature] Implement original mode — same creative flow as inspired_by but with brief/prompt input. ANALYSIS phase uses BRIEF_ANALYSIS_SYSTEM prompt, source_stats from config. CLI --source-material renamed to --input. (story_writer.py, cli.py)
- [ ] [feature] Add marker-based scene splitting as early-exit path in split_scenes (pre-split input support)
- [ ] [feature] Inline image tags — define image prompts in YAML header, reference with `**image:tag**` in story text. Decouples image transitions from scene boundaries, gives authors direct control over visuals. Requires video assembler refactor for multiple images per scene.
- [ ] [feature] Pause tags — `**pause:0.5**` inserts silence into narration audio. Useful for pacing and poetry. Inject silent audio bytes between TTS segments. Caption timing must account for gaps.
- [ ] [feature] Background music / sound effects — overlay audio tracks at specified points in narration with volume and duration control. Music files supplied by user. FFmpeg amix filter for mixing. Most complex of the three inline tag features.
- [x] [bug] Captions missing quotation marks around spoken dialogue — replaced segment-based `_reconcile_punctuation` with prose-based two-pointer alignment that restores all punctuation including quotation marks from `scene.prose` (pipeline/caption_generator.py)
- [ ] [feature] FFmpeg concat fallback for non-MP3/opus audio formats — when audio_transition_duration uses WAV, FLAC, or other formats that don't support raw byte concatenation, use `ffmpeg -f concat` to join segment audio files. Low priority: MP3 and opus (the only realistic TTS output formats) support byte concatenation natively.
- [x] [chore] Add ElevenLabs TTS provider option (merged to main)
- [x] [test] Boundary value tests for `_int_to_words` and `_year_to_words` — no longer applicable, regex code deleted (T8)
- [ ] [feature] Add async retry support when async API calls are introduced (R4)
- [ ] [chore] Consider exporting rate constants in cost.py `__all__` if needed by CLI layer (C4)
- [ ] [docs] Update design.md TTS cost example ($7.41 → $7.42) to match mathematically correct rounding (C5)
- [ ] [test] Add tests for partial override behavior in estimate_cost (only scene_count or only character_count) (C7)
- [ ] [test] Strengthen adapt mode format test to verify Claude rate range, not just string containment (C8)
- [ ] [test] Add retry exhaustion test for ClaudeClient (4 consecutive transient errors → original exception) (CC-S2)
- [ ] [chore] Consider exporting `TRANSIENT_ERRORS` in claude_client.py `__all__` if needed by orchestrator (CC-S3)
- [ ] [test] Add explicit encoding="utf-8" to test fixture source file writes for consistency (SW-S1)
- [ ] [test] Add Unicode content test for preservation check (accented chars, em dashes, curly quotes) (SW-S3)
- [ ] [refactor] Consider defensive access for missing "scenes" key in Claude response (SW-S4)
- [ ] [test] Add test for original_text not found in scene narration_text during autonomous fix (FN-S2)
- [ ] [refactor] Extract flags file writing into `_write_flags_report()` helper if format grows (FN-S3)
- [ ] [feature] Batched concatenation for 60+ segment videos — group segments into chapters of 10-15, concat each chapter, then concat chapters. Only needed if single-pass xfade chain hits FFmpeg limits with very long videos. Current single-pass approach works fine for 25-scene videos. (VA-D1)
- [ ] [test] Add @pytest.mark.slow integration tests that run actual FFmpeg on tiny inputs (1s silent audio, 10x10 image) to catch filter graph syntax errors and codec issues. Requires FFmpeg installed. (VA-D2)
- [x] [refactor] Extract `_make_tts_provider()` helper to deduplicate provider instantiation in create/resume commands (CLI-S1)
- [ ] [chore] `_find_most_recent_project` compares ISO 8601 timestamp strings lexicographically — fragile if hand-edited project.json uses non-ISO format (CLI-S2)
- [ ] [chore] Add `exists=True` to `--config` Typer option in create and estimate commands for immediate path validation (CLI-S4)
- [ ] [test] Add direct unit tests for `_status_icon` covering all 4 statuses and fallback path (CLI-S5)
- [x] [refactor] Narrow `create` command exception handler from bare `Exception` to `FileExistsError` for `ProjectState.create()` (CLI-S7)
- [ ] [chore] Verify GPT Image 1.5 pricing — current rates (low: $0.011, medium: $0.050, high: $0.167) are from early documentation and may have changed (CR-8)
- [ ] [refactor] Cost rate table key collision risk — IMAGE_COST_PER_IMAGE dict merges GPT Image tiers (low/medium/high) and DALL-E tiers (standard/hd) in one flat dict; if a future model reuses a tier name, values would collide. Consider nested dict keyed by model family. (CR-9)

## Resolved

Completed items awaiting migration to VERSION_HISTORY.md at next release.

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
