# Bugs and Todos

## Active

Items committed to the current sprint/cycle.

## Backlog

Acknowledged items not yet scheduled.

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
- [ ] [bug] Sentence-ending period lost after abbreviations — `"cats, dogs, etc. She left."` becomes `"...et cetera She left."` missing the period. `_make_replacer` only preserves trailing period at end-of-string or before `\n`. Known limitation — will be superseded by LLM-based TTS text prep feature. (PR-10)
- [x] [test] Orchestrator integration test gap — `test_runs_all_phases_without_pausing` mocks 9 internal functions, can't detect wiring mistakes. Add integration test that only mocks external APIs and exercises actual data flow between phases. (PR-11)
- [x] [refactor] `_patch_sleep` fixture duplicated in three test files — move to `conftest.py`. (PR-12)

**Low priority:**

- [ ] [chore] Delete dead file `ffmpeg/transitions.py` — empty, transition logic merged into `commands.py`. (PR-13)
- [ ] [bug] `_hex_to_ass_color` does not validate input format — silently produces garbage for malformed hex like `"#FFF"` or `"red"`. (PR-14)
- [ ] [bug] No cross-field validation on scene word count bounds — `scene_word_min`, `scene_word_target`, `scene_word_max` can be set in contradictory order. Add `@model_validator`. (PR-15)
- [ ] [bug] `SubtitleConfig.color` and `outline_color` lack hex format validation — bare `str` type, invalid values produce opaque FFmpeg errors. (PR-16)
- [ ] [docs] Stale docstring in `state.py:418` lists IMAGE_PROMPTS as having no per-scene asset — contradicts `PHASE_ASSET_MAP`. (PR-17)
- [ ] [bug] `--voice` option on `estimate` command is misleading — help text says "(affects cost)" but voice has no effect on cost calculation. Remove option or fix help text. (PR-18)
- [ ] [chore] `api_retry` exported but never used in production code — zero consumers in `src/`. Consider removing. (PR-19)
- [ ] [bug] `with_retry` default `retry_on=(Exception,)` is overly broad — catches `ValueError`, `TypeError`, etc. All callers specify explicitly, but default is a footgun for new callers. (PR-20)
- [ ] [chore] Inline regex not pre-compiled in `text.py:495` — `re.sub(r"  +", " ", result)` breaks file convention of module-level compiled patterns. (PR-21)
- [ ] [chore] Missing `logging.getLogger(__name__)` in `image_generator.py`, `video_assembler.py`, `caption_generator.py` — every other pipeline module has one. (PR-22)
- [ ] [chore] No logging configuration in CLI — logger created but no handler configured, debug logs vanish silently. Add `--verbose` flag. (PR-23)
- [ ] [test] Multiple test gaps: `_check_preservation` edge cases, `_strip_narration_tags` dedicated tests, `_format_to_extension` direct tests, CLI `_make_tts_provider` unknown provider path, `_apply_dotted_overrides` error path, `parse_narration_segments` with empty input, `build_concat_command` with short/zero-duration segments, `subtitle_filter` with special-character paths, `probe_duration` with non-numeric output. (PR-24)
- [ ] [test] Multiple-assertions-per-test convention violations in `test_caption_generator.py`, `test_image_generator.py`, `test_tts_generator.py` — split composite assertions into focused tests. (PR-25)

---

- [ ] [feature] LLM-based TTS text prep — optional pipeline phase that runs narration text through Claude for context-aware pronunciation preparation. Handles abbreviation expansion, number pronunciation (dates vs quantities), unusual name phonetics, and other contextual decisions that regex rules can't get right. Produces a changelog of all modifications with locations for human review. Supersedes PR-10 and the regex-based `expand_abbreviations` approach. Slots in after narration text finalization, before TTS generation.
- [ ] [feature] Implement story writer creative flow — analysis, bible, outline, prose, critique (pipeline/story_writer.py)
- [ ] [feature] Add marker-based scene splitting as early-exit path in split_scenes (pre-split input support)
- [ ] [feature] Inline image tags — define image prompts in YAML header, reference with `**image:tag**` in story text. Decouples image transitions from scene boundaries, gives authors direct control over visuals. Requires video assembler refactor for multiple images per scene.
- [ ] [feature] Pause tags — `**pause:0.5**` inserts silence into narration audio. Useful for pacing and poetry. Inject silent audio bytes between TTS segments. Caption timing must account for gaps.
- [ ] [feature] Background music / sound effects — overlay audio tracks at specified points in narration with volume and duration control. Music files supplied by user. FFmpeg amix filter for mixing. Most complex of the three inline tag features.
- [ ] [feature] FFmpeg concat fallback for non-MP3/opus audio formats — when audio_transition_duration uses WAV, FLAC, or other formats that don't support raw byte concatenation, use `ffmpeg -f concat` to join segment audio files. Low priority: MP3 and opus (the only realistic TTS output formats) support byte concatenation natively.
- [x] [chore] Add ElevenLabs TTS provider option (merged to main)
- [ ] [test] Add boundary value tests for `_int_to_words` and `_year_to_words` private helpers (T8)
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
- [ ] [refactor] Narrow `create` command exception handler from bare `Exception` to `FileExistsError` for `ProjectState.create()` (CLI-S7)
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

## Session Notes

### Session — 2026-02-16

**Stopped after:** Completed multi-voice TTS feature (8 tasks) and hardening pass (7 tasks). Both merged to main. 753 tests passing.

**Next up:** The multi-voice TTS pipeline is complete. Next logical steps are either: (1) implement the creative flow (story_writer.py — analysis, bible, outline, prose, critique), or (2) run a second end-to-end test with a multi-voice source story to exercise the new feature in production.

**Open questions:** None
