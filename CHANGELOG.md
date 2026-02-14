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

### Changed

### Deprecated

### Removed

### Fixed

### Security

---

## [0.1.0] — 2026-02-11

### Added
- Initial project bootstrap with CLI framework and pipeline stubs
