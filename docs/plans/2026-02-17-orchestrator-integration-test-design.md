# Orchestrator Integration Test Design (PR-11)

**Status:** Approved

## Problem

`test_runs_all_phases_without_pausing` mocks all 9 internal pipeline functions. It verifies they get called but can't detect wiring mistakes: wrong phase ordering, broken data flow between phases, incorrect provider routing, or missing state updates.

## Solution

Add an integration test that exercises the full 8-phase adapt pipeline with only external API boundaries mocked. Internal code runs for real.

## Mocking Strategy

Mock at external boundaries only:

| Mock | Returns |
|------|---------|
| `ClaudeClient.generate_structured` | Structured dicts for scene splitting, narration flagging, image prompts |
| `TTSProvider.synthesize` | Fake audio bytes |
| `ImageProvider.generate` | Fake PNG bytes |
| `CaptionProvider.transcribe` | Caption segment objects |
| `subprocess.run` | Success + duration string for ffprobe, success + creates output files for ffmpeg |

The `subprocess.run` mock creates expected output files on disk so downstream phases find them naturally.

## What Runs for Real

- Orchestrator phase sequencing and dispatch (`run_pipeline`, `_dispatch_phase`)
- State management (scene creation, asset tracking, phase transitions)
- Story writer (scene parsing, narration text assignment)
- Narration prep (abbreviation expansion, number conversion)
- TTS generator (file writing, multi-voice segment handling)
- Image generator (file writing)
- Caption generator (file writing)
- Video assembler (command construction, file path resolution)
- FFmpeg command building (filter graphs, concat commands)

## Verification

The test asserts:

1. **Files created on disk** — scene markdown, audio files, image files, video segments, final.mp4
2. **State correctness** — phase progression, asset statuses all COMPLETED, correct scene count
3. **Data flow** — scene prose flows to narration_text, narration_text flows to audio, etc.
4. **Final status** — pipeline status is COMPLETED

## Test Structure

- New `TestPipelineIntegration` class in `tests/test_orchestrator.py`
- Single test function: `test_full_adapt_pipeline_data_flow`
- Uses `tmp_path` for isolation
- Autonomous mode (skips review checkpoints)
- Not marked `@pytest.mark.slow` — no real FFmpeg execution, should run in < 2 seconds

## Constraints

- Mock responses must be realistic enough for downstream phases to consume
- The `subprocess.run` mock must distinguish between ffprobe (return duration) and ffmpeg (create output file) based on the command arguments
- Claude mock must return different structured responses depending on which phase is calling (scene splitting vs narration flagging vs image prompts)
