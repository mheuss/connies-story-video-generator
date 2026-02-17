# Orchestrator Integration Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an integration test that exercises the full 8-phase adapt pipeline with only external APIs mocked, catching wiring mistakes that unit tests miss.

**Architecture:** Single test in `tests/test_orchestrator.py` that mocks 4 external boundaries (Claude API, TTS provider, image provider, caption provider) plus `subprocess.run` (for FFmpeg). All internal code runs for real — orchestrator dispatch, state management, file I/O, command building. The `subprocess.run` mock distinguishes ffprobe (returns duration) from ffmpeg (creates output files).

**Tech Stack:** Python, pytest, unittest.mock

**Status:** Pending

---

## Task 1: Write the integration test

**Files:**
- Modify: `tests/test_orchestrator.py`

**Context:** The test needs to mock 4 external boundaries and let 8 internal phases run for real. The tricky parts are:

1. **Claude mock** must return different structured responses depending on the phase calling it: scene splitting returns `{"scenes": [...]}`, narration flagging returns `{"flags": [...]}`, image prompts returns `{"prompts": [...]}`. The mock uses `side_effect` to dispatch based on the `tool_name` argument.

2. **subprocess.run mock** must handle both ffprobe (return a duration string as stdout) and ffmpeg (create the expected output file). The mock inspects `cmd[0]` to distinguish them and uses the `-o` or last positional arg to find the output path.

3. **File prerequisites** — each phase creates files that the next phase reads. TTS writes audio files, image gen writes PNG files, caption gen writes JSON files. These must exist for video assembly to find them.

**Step 1: Write the test**

Add this test class at the bottom of `tests/test_orchestrator.py`, before the closing of the file:

```python
# ---------------------------------------------------------------------------
# TestPipelineIntegration — full data flow with only external APIs mocked
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """Integration test: full 8-phase pipeline with only external APIs mocked.

    Catches wiring mistakes that unit tests miss: wrong phase ordering,
    broken data flow, incorrect provider routing, missing state updates.
    """

    def test_full_adapt_pipeline_data_flow(self, tmp_path, monkeypatch):
        """Full adapt pipeline creates expected files and state transitions."""
        import json
        import subprocess

        from story_video.models import CaptionResult, CaptionSegment, CaptionWord

        # --- Source story ---
        source_text = (
            "The lighthouse keeper watched the storm approach. "
            "Dark clouds gathered on the horizon, and the waves grew tall.\n\n"
            "By morning the storm had passed. The keeper climbed the tower "
            "and lit the lamp, its beam cutting through the dawn mist."
        )

        # --- Mock Claude client ---
        # Claude is called 3 times: split_scenes, flag_narration, image_prompts.
        # Dispatch based on tool_name argument.
        claude_responses = {
            "split_into_scenes": {
                "scenes": [
                    {
                        "title": "The Storm",
                        "text": (
                            "The lighthouse keeper watched the storm approach. "
                            "Dark clouds gathered on the horizon, "
                            "and the waves grew tall."
                        ),
                    },
                    {
                        "title": "The Dawn",
                        "text": (
                            "By morning the storm had passed. "
                            "The keeper climbed the tower "
                            "and lit the lamp, its beam cutting "
                            "through the dawn mist."
                        ),
                    },
                ],
            },
            "flag_narration_issues": {
                "flags": [],
            },
            "generate_image_prompts": {
                "prompts": [
                    {
                        "scene_number": 1,
                        "image_prompt": "A weathered lighthouse on a rocky cliff.",
                    },
                    {
                        "scene_number": 2,
                        "image_prompt": "Golden dawn light through lighthouse glass.",
                    },
                ],
            },
        }

        mock_claude = MagicMock()

        def _claude_dispatch(**kwargs):
            tool_name = kwargs.get("tool_name", "")
            return claude_responses[tool_name]

        mock_claude.generate_structured = MagicMock(side_effect=_claude_dispatch)

        # --- Mock TTS provider ---
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=b"\xff" * 100)

        # --- Mock image provider ---
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_image = MagicMock()
        mock_image.generate = MagicMock(return_value=fake_png)

        # --- Mock caption provider ---
        def _make_caption_result(text: str) -> CaptionResult:
            words = text.split()
            duration = len(words) * 0.5
            return CaptionResult(
                segments=[CaptionSegment(text=text, start=0.0, end=duration)],
                words=[
                    CaptionWord(word=w, start=i * 0.5, end=(i + 1) * 0.5)
                    for i, w in enumerate(words)
                ],
                language="en",
                duration=duration,
            )

        mock_caption = MagicMock()
        mock_caption.transcribe = MagicMock(
            side_effect=lambda path: _make_caption_result("Transcribed narration text.")
        )

        # --- Mock subprocess.run (FFmpeg/ffprobe) ---
        real_subprocess_run = subprocess.run

        def _mock_subprocess_run(cmd, **kwargs):
            cmd_name = cmd[0] if cmd else ""

            if "ffprobe" in cmd_name:
                # Return a fake duration
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="5.0\n", stderr=""
                )

            if "ffmpeg" in cmd_name:
                # Find the output path (last argument to ffmpeg)
                output_path = cmd[-1]
                # Create the output file so downstream code finds it
                from pathlib import Path

                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x00" * 50)
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="", stderr=""
                )

            # Fall through for non-FFmpeg subprocess calls (e.g. pytest internals)
            return real_subprocess_run(cmd, **kwargs)

        monkeypatch.setattr("subprocess.run", _mock_subprocess_run)

        # --- Create project state ---
        state = _make_adapt_state(tmp_path, autonomous=True)

        # Write source story
        source_path = state.project_dir / "source_story.txt"
        source_path.write_text(source_text, encoding="utf-8")

        # --- Run the full pipeline ---
        run_pipeline(
            state,
            claude_client=mock_claude,
            tts_provider=mock_tts,
            image_provider=mock_image,
            caption_provider=mock_caption,
        )

        # --- Verify final state ---
        assert state.metadata.status == PhaseStatus.COMPLETED
        assert state.metadata.current_phase == PipelinePhase.VIDEO_ASSEMBLY
        assert len(state.metadata.scenes) == 2

        # --- Verify scene data flowed between phases ---
        scene1 = state.metadata.scenes[0]
        scene2 = state.metadata.scenes[1]

        # Scene splitting populated prose
        assert "lighthouse" in scene1.prose.lower()
        assert "dawn" in scene2.prose.lower()

        # Narration prep transformed text (narration_text set and not identical to prose)
        assert scene1.narration_text is not None
        assert scene2.narration_text is not None

        # Image prompts assigned
        assert "lighthouse" in scene1.image_prompt.lower()
        assert "dawn" in scene2.image_prompt.lower()

        # --- Verify all asset statuses are COMPLETED ---
        for scene in state.metadata.scenes:
            s = scene.asset_status
            assert s.text == SceneStatus.COMPLETED
            assert s.narration_text == SceneStatus.COMPLETED
            assert s.image_prompt == SceneStatus.COMPLETED
            assert s.audio == SceneStatus.COMPLETED
            assert s.image == SceneStatus.COMPLETED
            assert s.captions == SceneStatus.COMPLETED
            assert s.video_segment == SceneStatus.COMPLETED

        # --- Verify expected files exist on disk ---
        pd = state.project_dir

        # Scene markdown files
        assert (pd / "scenes" / "scene_001.md").exists()
        assert (pd / "scenes" / "scene_002.md").exists()

        # Audio files
        assert (pd / "audio" / "scene_001.mp3").exists()
        assert (pd / "audio" / "scene_002.mp3").exists()

        # Image files
        assert (pd / "images" / "scene_001.png").exists()
        assert (pd / "images" / "scene_002.png").exists()

        # Caption files
        assert (pd / "captions" / "scene_001.json").exists()
        assert (pd / "captions" / "scene_002.json").exists()

        # ASS subtitle files (generated during video assembly)
        assert (pd / "captions" / "scene_001.ass").exists()
        assert (pd / "captions" / "scene_002.ass").exists()

        # Video segments
        assert (pd / "segments" / "scene_001.mp4").exists()
        assert (pd / "segments" / "scene_002.mp4").exists()

        # Final video
        assert (pd / "final.mp4").exists()

        # --- Verify external APIs were called ---
        assert mock_claude.generate_structured.call_count == 3
        assert mock_tts.synthesize.call_count == 2
        assert mock_image.generate.call_count == 2
        assert mock_caption.transcribe.call_count == 2

        # --- Verify state was persisted to disk ---
        reloaded = ProjectState.load(pd)
        assert reloaded.metadata.status == PhaseStatus.COMPLETED
        assert len(reloaded.metadata.scenes) == 2
```

Note: Import `CaptionResult`, `CaptionSegment`, `CaptionWord` inside the test function to avoid polluting the module-level imports (these models aren't used by any other orchestrator test).

**Step 2: Run the test**

Run: `python3 -m pytest tests/test_orchestrator.py::TestPipelineIntegration -v`

This test is NOT TDD in the traditional sense — we're not writing failing code first. We're writing an integration test for existing, working code. The test either passes (proving the wiring works) or fails (revealing a wiring bug we didn't know about).

Expected: PASS (the pipeline is correctly wired — unit tests just couldn't prove it)

If FAIL: The failure message will pinpoint the exact wiring issue. Fix whatever broke and re-run.

**Step 3: Run full test suite**

Run: `python3 -m pytest -v`
Expected: All PASS (789+)

**Step 4: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: add orchestrator integration test for full pipeline data flow (PR-11)"
```

---

## Task 2: Update backlog

**Files:**
- Modify: `BUGS_AND_TODOS.md`

**Step 1: Mark PR-11 as resolved**

Change PR-11 from `[ ]` to `[x]` in the Medium priority section. Add to Resolved section.

**Step 2: Commit**

```bash
git add -f BUGS_AND_TODOS.md
git commit -m "docs: mark PR-11 as resolved"
```
