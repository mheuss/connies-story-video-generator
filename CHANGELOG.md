# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Original creative flow — generates stories from a creative brief or prompt using the same 5-phase pipeline as inspired_by mode. ANALYSIS phase uses a dedicated brief interpretation prompt; story length derived from config defaults.
- Inspired_by creative flow — 5-phase pipeline (source analysis, story bible, outline, scene prose with running summaries, critique/revision) that creates original stories inspired by existing source material. Includes `--premise` flag for creative direction and semi-auto checkpoints at each creative phase.

### Changed
- CLI flag `--source-material` renamed to `--input` — applies to all three modes (adapt, iWenspired_by, original). Clean break, no deprecated alias.

## [0.4.0] — 2026-02-18

### Added
- `--verbose` / `-v` CLI flag for debug logging output
- Multi-voice narration with inline `**voice:X**` tags and per-story voice mapping via YAML front matter
- Emotion direction with `**mood:X**` tags — maps to OpenAI `instructions` parameter and ElevenLabs audio tags
- ElevenLabs TTS provider with audio tag translation for emotion control
- LLM-based TTS narration prep — context-aware pronunciation preparation via Claude API with tag validation, pronunciation guide accumulation, and structured changelog
- Retry decorators with exponential backoff for API calls (configurable retries, delays, exception filtering)
- Cost estimation for story video projects — calculates per-service costs (Claude, TTS, Images, Whisper) with projected and actual modes
- Claude API client wrapper — thin wrapper with text generation and structured output via tool_use
- Story writer adaptation flow — scene splitting with text preservation validation, narration flagging with autonomous and semi-auto fix modes
- TTS, image, and caption generators — pluggable media asset generation with OpenAI provider implementations (TTS via audio.speech, images via GPT Image 1.5 with DALL-E 3 fallback, captions via Whisper with word-level timestamps)
- FFmpeg video assembly layer — still image scaling, blurred background, ASS subtitle generation from word timestamps, per-scene segment rendering with single-pass filtergraph, final video concatenation with crossfade transitions and fade in/out
- Pipeline orchestrator for adapt flow — runs all 8 phases end-to-end with resume from any state, semi-auto review checkpoints at content phases, and autonomous straight-through mode
- Image prompt writer — generates image prompts for all scenes in a single Claude call with structured output
- CLI commands — create (adapt mode), resume, estimate, status, and list with Rich terminal output

### Changed
- Narration prep now uses Claude API instead of regex transforms — handles abbreviations, numbers, and punctuation contextually. NARRATION_PREP phase pauses for review in semi-auto mode. Produces a JSON changelog of all modifications.
- `with_retry` `retry_on` parameter is now required — all callers already specified it explicitly
- Default TTS model changed from `tts-1-hd` to `gpt-4o-mini-tts` for emotion instruction support
- `TTSProvider.synthesize()` accepts optional `instructions` parameter — BREAKING for custom providers
- Default image model changed from DALL-E 3 to GPT Image 1.5 — better quality, supports `output_format` parameter
- Image generation now requires IMAGE_PROMPT asset (was TEXT) — BREAKING for existing projects

### Deprecated

### Removed
- Regex-based narration prep (`text.py`) — replaced by LLM-based approach
- `--voice` option from `estimate` command — had no effect on cost calculation
- Unused `api_retry` convenience decorator from retry utilities
- Ken Burns zoom/pan effect — replaced with still image scaling for simpler, more reliable video assembly

### Fixed
- Caption subtitles now include punctuation (periods, commas, question marks) reconciled from Whisper segment text
- Short stories (under 1000 words) now produce at least 2 scenes instead of 1
- Success message now correctly points to `final.mp4` instead of empty `video/` directory
- Audio overlap at scene transitions — narration no longer bleeds across scenes during crossfade. Video crossfade (1.5s) and audio crossfade (0.05s) are now independently configurable via `audio_transition_duration`
- Multi-voice TTS with non-MP3/opus format now raises clear error instead of producing corrupt audio files
- Unknown TTS provider in config now fails fast with error message instead of silently defaulting to OpenAI
- `StoryHeader` with `default_voice` not matching any voice label now fails at construction instead of at runtime
- Voice/mood tags in text without a YAML header now raise immediately instead of being spoken as literal text
- Invalid hex colors in `SubtitleConfig` now rejected at construction instead of producing opaque FFmpeg errors
- Contradictory scene word count bounds (`scene_word_min` > `scene_word_max`) now rejected at construction
- Malformed hex input to `_hex_to_ass_color` now raises `ValueError` instead of silently producing garbage

### Security

---

## [0.1.0] — 2026-02-11

### Added
- Initial project bootstrap with CLI framework and pipeline stubs
