# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Text utilities for TTS narration prep — expands abbreviations, converts numbers to words, inserts dramatic pauses, and smooths punctuation
- Retry decorators with exponential backoff for API calls (configurable retries, delays, exception filtering)
- Cost estimation for story video projects — calculates per-service costs (Claude, TTS, DALL-E, Whisper) with projected and actual modes
- Claude API client wrapper — thin wrapper with text generation and structured output via tool_use
- Story writer adaptation flow — scene splitting with text preservation validation, narration flagging with autonomous and semi-auto fix modes
- TTS, image, and caption generators — pluggable media asset generation with OpenAI provider implementations (TTS via audio.speech, images via DALL-E 3, captions via Whisper with word-level timestamps)
- FFmpeg video assembly layer — Ken Burns effect with 5 deterministic directions, blurred background, ASS subtitle generation from word timestamps, per-scene segment rendering with single-pass filtergraph, final video concatenation with crossfade transitions and fade in/out
- Pipeline orchestrator for adapt flow — runs all 8 phases end-to-end with resume from any state, semi-auto review checkpoints at content phases, and autonomous straight-through mode
- Image prompt writer — generates DALL-E prompts for all scenes in a single Claude call with structured output
- CLI commands — create (adapt mode), resume, estimate, status, and list with Rich terminal output

### Changed
- Image generation now requires IMAGE_PROMPT asset (was TEXT) — BREAKING for existing projects

### Deprecated

### Removed

### Fixed

### Security

---

## [0.1.0] — 2026-02-11

### Added
- Initial project bootstrap with CLI framework and pipeline stubs
