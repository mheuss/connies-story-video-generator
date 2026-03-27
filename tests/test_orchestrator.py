"""Tests for story_video.pipeline.orchestrator — pipeline orchestration.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the orchestrator module.
All pipeline module functions are mocked — no real API calls.
"""

import json
import logging
import subprocess as _subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from story_video.models import (
    AppConfig,
    AssetType,
    AudioAsset,
    CaptionResult,
    CaptionSegment,
    CaptionWord,
    InputMode,
    PhaseStatus,
    PipelineConfig,
    PipelinePhase,
    Scene,
    SceneAudioCue,
    SceneImagePrompt,
    SceneStatus,
    StoryHeader,
)
from story_video.pipeline.orchestrator import (
    _CHECKPOINT_PHASES,
    _determine_start_phase,
    _dispatch_phase,
    _parse_source_header,
    _populate_image_tags,
    _populate_music_tags,
    _run_narration_prep,
    _run_per_scene,
    run_pipeline,
)
from story_video.state import ProjectState

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_adapt_state(tmp_path, *, autonomous=False):
    """Create a fresh adapt-mode project state with no current phase."""
    config = AppConfig(pipeline=PipelineConfig(autonomous=autonomous))
    state = ProjectState.create("orch-test", InputMode.ADAPT, config, tmp_path)
    return state


def _add_scenes_with_assets(state, count=2, *, up_to_asset=None):
    """Add scenes and complete assets up to a given type.

    Asset progression: TEXT -> NARRATION_TEXT -> IMAGE_PROMPT -> AUDIO -> IMAGE
                       -> CAPTIONS -> VIDEO_SEGMENT

    Args:
        state: Project state to add scenes to.
        count: Number of scenes to add.
        up_to_asset: Complete assets up through this type (inclusive).
            None means only add scenes without completing any assets.
    """
    asset_order = [
        AssetType.TEXT,
        AssetType.NARRATION_TEXT,
        AssetType.IMAGE_PROMPT,
        AssetType.AUDIO,
        AssetType.IMAGE,
        AssetType.CAPTIONS,
        AssetType.VIDEO_SEGMENT,
    ]

    for i in range(1, count + 1):
        state.add_scene(scene_number=i, title=f"Scene {i}", prose=f"Prose for scene {i}.")

    if up_to_asset is not None:
        stop_idx = asset_order.index(up_to_asset) + 1
        for i in range(1, count + 1):
            for asset in asset_order[:stop_idx]:
                state.update_scene_asset(i, asset, SceneStatus.IN_PROGRESS)
                state.update_scene_asset(i, asset, SceneStatus.COMPLETED)


def _set_phase_state(state, phase, status):
    """Set a project state to a specific phase and status.

    Uses start_phase + appropriate transition method to reach the
    desired status legally through the state machine.
    """
    state.start_phase(phase)
    if status == PhaseStatus.COMPLETED:
        state.complete_phase()
    elif status == PhaseStatus.FAILED:
        state.fail_phase()
    elif status == PhaseStatus.AWAITING_REVIEW:
        state.await_review()
    # IN_PROGRESS is the default after start_phase — no extra call needed


def _make_claude_dispatch(responses):
    """Create a Claude mock side_effect that routes by tool_name.

    Handles tts_text_prep automatically by echoing narration text back.
    All other tool names are looked up in *responses*.
    """

    def _dispatch(**kwargs):
        tool_name = kwargs.get("tool_name", "")
        if tool_name == "tts_text_prep":
            user_msg = kwargs.get("user_message", "")
            lines = user_msg.split("\n")
            text_start = None
            for i, line in enumerate(lines):
                if line.startswith("Narration text to prepare for TTS:"):
                    text_start = i + 2
                    break
            narration_text = "\n".join(lines[text_start:]) if text_start else ""
            return {
                "modified_text": narration_text,
                "changes": [],
                "pronunciation_guide_additions": [],
            }
        return responses[tool_name]

    return _dispatch


def _make_simple_caption_result(text):
    """Build a CaptionResult from plain text with 0.5s per word timing."""
    words = text.split()
    duration = len(words) * 0.5
    return CaptionResult(
        segments=[CaptionSegment(text=text, start=0.0, end=duration)],
        words=[CaptionWord(word=w, start=i * 0.5, end=(i + 1) * 0.5) for i, w in enumerate(words)],
        language="en",
        duration=duration,
    )


def _make_timed_caption_result(words, duration):
    """Build a CaptionResult with evenly spaced words over *duration* seconds."""
    per_word = duration / len(words)
    return CaptionResult(
        segments=[CaptionSegment(text=" ".join(words), start=0.0, end=duration)],
        words=[
            CaptionWord(word=w, start=i * per_word, end=(i + 1) * per_word)
            for i, w in enumerate(words)
        ],
        language="en",
        duration=duration,
    )


def _make_mock_subprocess_run(duration="5.0", capture_commands=None):
    """Create a subprocess.run mock that handles ffprobe and ffmpeg.

    Args:
        duration: ffprobe duration response string.
        capture_commands: Optional list to append ffmpeg commands to.
    """
    real_run = _subprocess.run

    def _mock(cmd, **kwargs):
        cmd_str = cmd[0] if cmd else ""
        if "ffprobe" in cmd_str:
            return _subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=f"{duration}\n", stderr=""
            )
        if "ffmpeg" in cmd_str:
            if capture_commands is not None:
                capture_commands.append(list(cmd))
            output_path = Path(cmd[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x00" * 50)
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return real_run(cmd, **kwargs)

    return _mock


def _make_mock_providers():
    """Create mock TTS, image, and caption providers with sensible defaults.

    Returns (mock_tts, mock_image, mock_caption) tuple.
    """
    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"\xff" * 100)

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_image = MagicMock()
    mock_image.generate = MagicMock(return_value=fake_png)

    mock_caption = MagicMock()

    return mock_tts, mock_image, mock_caption


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapt_state(tmp_path):
    """Fresh adapt-mode project state — no current phase, no scenes."""
    return _make_adapt_state(tmp_path)


# ---------------------------------------------------------------------------
# TestDetermineStartPhase — resume logic
# ---------------------------------------------------------------------------


class TestDetermineStartPhase:
    """_determine_start_phase() correctly identifies where to start or resume."""

    def test_fresh_project_starts_at_first_phase(self, adapt_state):
        """State with current_phase=None -> first phase (ANALYSIS)."""
        phases = adapt_state.get_phase_sequence()
        result = _determine_start_phase(adapt_state, phases)

        assert result == PipelinePhase.ANALYSIS

    def test_completed_phase_advances_to_next(self, adapt_state):
        """COMPLETED current phase -> next phase in sequence."""
        _set_phase_state(adapt_state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.COMPLETED)
        phases = adapt_state.get_phase_sequence()

        result = _determine_start_phase(adapt_state, phases)

        assert result == PipelinePhase.NARRATION_FLAGGING

    def test_failed_phase_retries_current(self, adapt_state):
        """FAILED current phase -> retry same phase."""
        _set_phase_state(adapt_state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.FAILED)
        phases = adapt_state.get_phase_sequence()

        result = _determine_start_phase(adapt_state, phases)

        assert result == PipelinePhase.SCENE_SPLITTING

    def test_awaiting_review_advances_to_next(self, adapt_state):
        """AWAITING_REVIEW current phase -> next phase (user approved by resuming)."""
        _set_phase_state(adapt_state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.AWAITING_REVIEW)
        phases = adapt_state.get_phase_sequence()

        result = _determine_start_phase(adapt_state, phases)

        assert result == PipelinePhase.NARRATION_FLAGGING

    def test_in_progress_retries_current(self, adapt_state):
        """IN_PROGRESS current phase -> retry same phase (crash recovery)."""
        _set_phase_state(adapt_state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.IN_PROGRESS)
        phases = adapt_state.get_phase_sequence()

        result = _determine_start_phase(adapt_state, phases)

        assert result == PipelinePhase.SCENE_SPLITTING

    def test_last_phase_completed_returns_none(self, adapt_state):
        """VIDEO_ASSEMBLY completed -> None (pipeline complete)."""
        _set_phase_state(adapt_state, PipelinePhase.VIDEO_ASSEMBLY, PhaseStatus.COMPLETED)
        phases = adapt_state.get_phase_sequence()

        result = _determine_start_phase(adapt_state, phases)

        assert result is None

    def test_after_invalidation_starts_at_next_phase(self, adapt_state):
        """After invalidate_from(), orchestrator starts at the next phase."""
        # Complete first two phases
        _set_phase_state(adapt_state, PipelinePhase.ANALYSIS, PhaseStatus.COMPLETED)
        _set_phase_state(adapt_state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.COMPLETED)

        # Invalidate from analysis — sets current_phase=ANALYSIS, status=COMPLETED
        adapt_state.invalidate_from(PipelinePhase.ANALYSIS)

        phases = adapt_state.get_phase_sequence()
        result = _determine_start_phase(adapt_state, phases)

        # Should pick up from scene_splitting (next after analysis)
        assert result == PipelinePhase.SCENE_SPLITTING


# ---------------------------------------------------------------------------
# TestRunPipelineAlreadyComplete — no-op when pipeline is done
# ---------------------------------------------------------------------------


class TestRunPipelineAlreadyComplete:
    """run_pipeline() returns immediately when there's nothing to do."""

    def test_returns_immediately_when_complete(self, adapt_state):
        """Pipeline done (last phase COMPLETED) -> no phases dispatched."""
        _set_phase_state(adapt_state, PipelinePhase.VIDEO_ASSEMBLY, PhaseStatus.COMPLETED)

        # Should not raise and not call any pipeline functions
        run_pipeline(adapt_state)

        # Status unchanged
        assert adapt_state.metadata.current_phase == PipelinePhase.VIDEO_ASSEMBLY
        assert adapt_state.metadata.status == PhaseStatus.COMPLETED


# ---------------------------------------------------------------------------
# TestRunPipelineSemiAutoCheckpoints — checkpoint pausing behavior
# ---------------------------------------------------------------------------


class TestRunPipelineSemiAutoCheckpoints:
    """run_pipeline() pauses at checkpoint phases in semi-auto mode."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_pauses_after_scene_splitting(self, mock_split, tmp_path):
        """Semi-auto mode pauses after SCENE_SPLITTING with AWAITING_REVIEW."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.SCENE_SPLITTING
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_split.assert_called_once()

    @patch("story_video.pipeline.orchestrator.generate_image_prompts")
    @patch("story_video.pipeline.orchestrator.flag_narration")
    def test_pauses_after_narration_flagging(self, mock_flag, mock_prompts, tmp_path):
        """Semi-auto resumes at NARRATION_FLAGGING, pauses after it."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        # Set state to resume from NARRATION_FLAGGING
        _set_phase_state(state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.NARRATION_FLAGGING
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_flag.assert_called_once()
        mock_prompts.assert_not_called()

    @patch("story_video.pipeline.orchestrator.generate_image_prompts")
    @patch("story_video.pipeline.orchestrator.generate_visual_reference")
    def test_pauses_after_image_prompts(self, mock_vr, mock_prompts, tmp_path):
        """Semi-auto resumes at IMAGE_PROMPTS, pauses after it."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.NARRATION_FLAGGING, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.IMAGE_PROMPTS
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_prompts.assert_called_once()

    def test_checkpoint_phases_are_correct(self):
        """Verify the checkpoint phases set contains the expected phases."""
        assert _CHECKPOINT_PHASES == frozenset(
            {
                PipelinePhase.ANALYSIS,
                PipelinePhase.STORY_BIBLE,
                PipelinePhase.OUTLINE,
                PipelinePhase.SCENE_PROSE,
                PipelinePhase.CRITIQUE_REVISION,
                PipelinePhase.SCENE_SPLITTING,
                PipelinePhase.NARRATION_FLAGGING,
                PipelinePhase.IMAGE_PROMPTS,
                PipelinePhase.NARRATION_PREP,
                PipelinePhase.TTS_GENERATION,
            }
        )

    @patch("story_video.pipeline.orchestrator.analyze_source")
    def test_creative_flow_pauses_after_analysis(self, mock_analyze, tmp_path):
        """Creative flow (INSPIRED_BY) pauses at ANALYSIS in semi-auto mode."""
        config = AppConfig(pipeline=PipelineConfig(autonomous=False))
        state = ProjectState.create("creative-test", InputMode.INSPIRED_BY, config, tmp_path)

        run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.ANALYSIS
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_analyze.assert_called_once()

    @patch("story_video.pipeline.orchestrator.create_story_bible")
    def test_creative_flow_pauses_after_story_bible(self, mock_bible, tmp_path):
        """Creative flow resumes from ANALYSIS and pauses at STORY_BIBLE."""
        config = AppConfig(pipeline=PipelineConfig(autonomous=False))
        state = ProjectState.create("creative-test", InputMode.INSPIRED_BY, config, tmp_path)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.STORY_BIBLE
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_bible.assert_called_once()

    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    def test_narration_prep_pauses_in_semi_auto(self, mock_prep, tmp_path):
        """NARRATION_PREP pauses for review in semi-auto mode."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.TEXT)

        # Set narration_text on the scene
        scene = state.metadata.scenes[0]
        scene.narration_text = scene.prose
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        # Resume from IMAGE_PROMPTS AWAITING_REVIEW — next is NARRATION_PREP
        _set_phase_state(state, PipelinePhase.IMAGE_PROMPTS, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.NARRATION_PREP
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_prep.assert_called_once()

    @patch("story_video.pipeline.orchestrator.generate_audio")
    def test_pauses_after_tts_generation(self, mock_audio, tmp_path):
        """Semi-auto resumes from NARRATION_PREP and pauses after TTS_GENERATION."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.IMAGE_PROMPT)

        # Set narration_text on the scene (required for TTS)
        scene = state.metadata.scenes[0]
        scene.narration_text = scene.prose

        # Resume from NARRATION_PREP AWAITING_REVIEW — next is TTS_GENERATION
        _set_phase_state(state, PipelinePhase.NARRATION_PREP, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, tts_provider=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.TTS_GENERATION
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_audio.assert_called_once()


# ---------------------------------------------------------------------------
# TestRunPipelineAutonomous — autonomous mode skips checkpoints
# ---------------------------------------------------------------------------


class TestRunPipelineAutonomous:
    """run_pipeline() runs straight through in autonomous mode."""

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped text",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    @patch("story_video.pipeline.orchestrator.generate_image_prompts")
    @patch("story_video.pipeline.orchestrator.generate_visual_reference")
    @patch("story_video.pipeline.orchestrator.flag_narration")
    @patch("story_video.pipeline.orchestrator.split_scenes")
    @patch("story_video.pipeline.orchestrator.analyze_source")
    def test_runs_all_phases_without_pausing(
        self,
        mock_analyze,
        mock_split,
        mock_flag,
        mock_vr,
        mock_prompts,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """Autonomous mode runs all phases without pausing."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        # Add scenes so per-scene phases have something to process
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.TEXT)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # All phases were dispatched (no checkpoint pause)
        mock_analyze.assert_called_once()
        mock_split.assert_called_once()
        mock_flag.assert_called_once()
        mock_vr.assert_called_once()
        mock_prompts.assert_called_once()
        # assemble_video called once at end
        mock_assemble_video.assert_called_once()
        # Final status is COMPLETED
        assert state.metadata.current_phase == PipelinePhase.VIDEO_ASSEMBLY
        assert state.metadata.status == PhaseStatus.COMPLETED


# ---------------------------------------------------------------------------
# TestRunPipelinePhaseFailure — error handling
# ---------------------------------------------------------------------------


class TestRunPipelinePhaseFailure:
    """run_pipeline() handles exceptions from phase dispatch."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_fail_phase_on_exception(self, mock_split, tmp_path):
        """Exception in dispatch -> fail_phase() + save() + re-raise."""
        mock_split.side_effect = RuntimeError("Claude API down")
        state = _make_adapt_state(tmp_path, autonomous=True)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.COMPLETED)

        with pytest.raises(RuntimeError, match="Claude API down"):
            run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.SCENE_SPLITTING
        assert state.metadata.status == PhaseStatus.FAILED

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_state_saved_on_failure(self, mock_split, tmp_path):
        """State persisted to disk after failure — reload confirms FAILED."""
        mock_split.side_effect = RuntimeError("boom")
        state = _make_adapt_state(tmp_path, autonomous=True)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.COMPLETED)

        with pytest.raises(RuntimeError):
            run_pipeline(state, claude_client=MagicMock())

        reloaded = ProjectState.load(state.project_dir)
        assert reloaded.metadata.status == PhaseStatus.FAILED


# ---------------------------------------------------------------------------
# TestRunPipelineResume — resume from various states
# ---------------------------------------------------------------------------


class TestRunPipelineResume:
    """run_pipeline() resumes correctly from different phase states."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_resume_from_failed_phase_retries(self, mock_split, tmp_path):
        """FAILED SCENE_SPLITTING -> retry SCENE_SPLITTING."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.FAILED)

        run_pipeline(state, claude_client=MagicMock())

        mock_split.assert_called_once()
        # In semi-auto, it pauses again after the checkpoint
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW

    @patch("story_video.pipeline.orchestrator.flag_narration")
    def test_resume_from_awaiting_review_advances(self, mock_flag, tmp_path):
        """AWAITING_REVIEW on SCENE_SPLITTING -> proceed to NARRATION_FLAGGING."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        mock_flag.assert_called_once()
        assert state.metadata.current_phase == PipelinePhase.NARRATION_FLAGGING


# ---------------------------------------------------------------------------
# TestRunPipelineNarrationPrep — inline narration prep logic
# ---------------------------------------------------------------------------


class TestRunPipelineNarrationPrep:
    """NARRATION_PREP phase applies prepare_narration_llm to all scenes."""

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_transforms_all_scenes(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """NARRATION_PREP applies prepare_narration_llm to every scene's narration_text."""
        mock_prep.return_value = {
            "modified_text": "transformed text",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.TEXT)

        # Set narration_text on scenes (flag_narration would have done this)
        for scene in state.metadata.scenes:
            scene.narration_text = scene.prose
            state.update_scene_asset(
                scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS
            )
            state.update_scene_asset(
                scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED
            )

        # Skip earlier phases by starting at IMAGE_PROMPTS completed
        _set_phase_state(state, PipelinePhase.IMAGE_PROMPTS, PhaseStatus.COMPLETED)
        # Complete IMAGE_PROMPT assets too
        for scene in state.metadata.scenes:
            state.update_scene_asset(
                scene.scene_number, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS
            )
            state.update_scene_asset(
                scene.scene_number, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED
            )

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # prepare_narration called once per scene
        assert mock_prep.call_count == 2
        # narration_text updated to transformed text
        for scene in state.metadata.scenes:
            assert scene.narration_text == "transformed text"

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_uses_prose_when_no_narration_text(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """When narration_text is None, prepare_narration_llm uses prose instead."""
        mock_prep.return_value = {
            "modified_text": "from prose",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.TEXT)

        # Complete NARRATION_TEXT asset but leave narration_text as None
        scene = state.metadata.scenes[0]
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        _set_phase_state(state, PipelinePhase.IMAGE_PROMPTS, PhaseStatus.COMPLETED)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # prepare_narration_llm called with the prose since narration_text was None
        assert mock_prep.call_args[0][0] == scene.prose
        assert scene.narration_text == "from prose"

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_does_not_change_asset_status(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """NARRATION_PREP does not touch NARRATION_TEXT asset status."""
        mock_prep.return_value = {
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.TEXT)

        scene = state.metadata.scenes[0]
        scene.narration_text = "original"
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        _set_phase_state(state, PipelinePhase.IMAGE_PROMPTS, PhaseStatus.COMPLETED)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # NARRATION_TEXT status still COMPLETED (not changed by narration_prep)
        assert scene.asset_status.narration_text == SceneStatus.COMPLETED

    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_logs_warning_for_empty_text(self, mock_prep, tmp_path, caplog):
        """Scene with no narration_text or prose logs a warning and is skipped."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.TEXT)

        # Clear both narration_text and prose so the scene has no text.
        # Bypass Pydantic's min_length=1 validator on prose via
        # object.__setattr__ — this simulates a corrupted/incomplete scene.
        scene = state.metadata.scenes[0]
        scene.narration_text = None
        object.__setattr__(scene, "prose", "")

        with caplog.at_level(logging.WARNING, logger="story_video.pipeline.orchestrator"):
            _run_narration_prep(state, MagicMock())

        assert "Scene 1 has no narration_text or prose" in caplog.text
        mock_prep.assert_not_called()

    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_skips_scenes_in_done_file(self, mock_prep, tmp_path):
        """Scenes listed in narration_prep_done.json are skipped on retry."""
        mock_prep.return_value = {
            "modified_text": "prepped scene 2",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.TEXT)

        # Set narration_text on both scenes
        for scene in state.metadata.scenes:
            scene.narration_text = f"Original scene {scene.scene_number}."
            state.update_scene_asset(
                scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS
            )
            state.update_scene_asset(
                scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED
            )

        # Write done file marking scene 1 as already processed
        done_path = state.project_dir / "narration_prep_done.json"
        done_path.write_text(json.dumps([1]), encoding="utf-8")

        _run_narration_prep(state, MagicMock())

        # Only scene 2 was processed
        assert mock_prep.call_count == 1
        assert mock_prep.call_args[0][0] == "Original scene 2."
        # Scene 1 narration_text unchanged
        assert state.metadata.scenes[0].narration_text == "Original scene 1."
        # Scene 2 narration_text updated
        assert state.metadata.scenes[1].narration_text == "prepped scene 2"

    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_writes_done_file_per_scene(self, mock_prep, tmp_path):
        """narration_prep_done.json is updated after each scene is processed."""
        mock_prep.return_value = {
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.TEXT)

        for scene in state.metadata.scenes:
            scene.narration_text = scene.prose

        _run_narration_prep(state, MagicMock())

        done_path = state.project_dir / "narration_prep_done.json"
        assert done_path.exists()
        done_scenes = json.loads(done_path.read_text(encoding="utf-8"))
        assert sorted(done_scenes) == [1, 2]

    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_narration_prep_saves_state_after_processing(self, mock_prep, tmp_path):
        """State is saved to disk after narration prep so modifications persist."""
        mock_prep.return_value = {
            "modified_text": "prepped narration",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.TEXT)

        scene = state.metadata.scenes[0]
        scene.narration_text = scene.prose

        _run_narration_prep(state, MagicMock())

        # Read project.json from disk and verify the modified narration_text persisted
        project_json = json.loads((state.project_dir / "project.json").read_text(encoding="utf-8"))
        saved_narration = project_json["scenes"][0]["narration_text"]
        assert saved_narration == "prepped narration"


class TestRunPipelineNarrationPrepCorruptDoneFile:
    """_run_narration_prep recovers from a corrupt done file."""

    @patch("story_video.pipeline.orchestrator.prepare_narration_llm")
    def test_corrupt_done_file_processes_all_scenes(self, mock_prep, tmp_path, caplog):
        """Corrupt narration_prep_done.json triggers warning and full reprocessing."""
        mock_prep.return_value = {
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        }

        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.TEXT)

        for scene in state.metadata.scenes:
            scene.narration_text = scene.prose

        # Write corrupt done file
        done_path = state.project_dir / "narration_prep_done.json"
        done_path.write_text("not valid json{{{", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            _run_narration_prep(state, MagicMock())

        assert mock_prep.call_count == 2
        assert "Corrupt narration_prep_done.json" in caplog.text


# ---------------------------------------------------------------------------
# TestRunPipelineDispatch — phase dispatch routing
# ---------------------------------------------------------------------------


class TestRunPipelineDispatch:
    """run_pipeline() dispatches to the correct pipeline module per phase."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_scene_splitting_calls_split_scenes(self, mock_split, tmp_path):
        """SCENE_SPLITTING dispatches to split_scenes(state, client)."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.AWAITING_REVIEW)
        client = MagicMock()

        run_pipeline(state, claude_client=client)

        mock_split.assert_called_once_with(state, client)

    @patch("story_video.pipeline.orchestrator.flag_narration")
    def test_narration_flagging_calls_flag_narration(self, mock_flag, tmp_path):
        """NARRATION_FLAGGING dispatches to flag_narration(state, client)."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.SCENE_SPLITTING, PhaseStatus.AWAITING_REVIEW)
        client = MagicMock()

        run_pipeline(state, claude_client=client)

        mock_flag.assert_called_once_with(state, client)

    @patch("story_video.pipeline.orchestrator.generate_image_prompts")
    @patch("story_video.pipeline.orchestrator.generate_visual_reference")
    def test_image_prompts_calls_generate_image_prompts(self, mock_vr, mock_prompts, tmp_path):
        """IMAGE_PROMPTS dispatches to generate_image_prompts(state, client)."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.NARRATION_FLAGGING, PhaseStatus.AWAITING_REVIEW)
        client = MagicMock()

        run_pipeline(state, claude_client=client)

        mock_prompts.assert_called_once_with(state, client)

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    def test_tts_generation_calls_generate_audio_per_scene(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """TTS_GENERATION dispatches generate_audio per scene."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.NARRATION_TEXT)
        # Also complete IMAGE_PROMPT
        for i in range(1, 3):
            state.update_scene_asset(i, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
            state.update_scene_asset(i, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)

        _set_phase_state(state, PipelinePhase.NARRATION_PREP, PhaseStatus.COMPLETED)

        tts_provider = MagicMock()
        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=tts_provider,
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # generate_audio called for each scene
        assert mock_audio.call_count == 2

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    def test_video_assembly_calls_per_scene_and_final(self, mock_scene, mock_video, tmp_path):
        """VIDEO_ASSEMBLY calls assemble_scene per scene + assemble_video."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.CAPTIONS)
        _set_phase_state(state, PipelinePhase.CAPTION_GENERATION, PhaseStatus.COMPLETED)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        assert mock_scene.call_count == 2
        mock_video.assert_called_once_with(state)


# ---------------------------------------------------------------------------
# TestRunPipelineStateSaved — state persisted at completion
# ---------------------------------------------------------------------------


class TestRunPipelineStateSaved:
    """run_pipeline() saves state at end of run and at checkpoints."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_state_saved_at_checkpoint(self, mock_split, tmp_path):
        """State is saved to disk at checkpoint pause."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.AWAITING_REVIEW)

        run_pipeline(state, claude_client=MagicMock())

        # Verify by reloading from disk
        reloaded = ProjectState.load(state.project_dir)
        assert reloaded.metadata.status == PhaseStatus.AWAITING_REVIEW


# ---------------------------------------------------------------------------
# TestRunPipelineProgressCallbacks — on_progress callback invocation
# ---------------------------------------------------------------------------


class TestRunPipelineProgressCallbacks:
    """run_pipeline() invokes on_progress callback at phase and scene boundaries."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_on_progress_called_at_phase_start(self, mock_split, tmp_path):
        """on_progress receives phase_started event when a phase begins."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.AWAITING_REVIEW)

        events = []
        run_pipeline(
            state,
            claude_client=MagicMock(),
            on_progress=lambda t, d: events.append((t, d)),
        )

        assert any(t == "phase_started" and d["phase"] == "scene_splitting" for t, d in events)

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    def test_on_progress_reports_scene_progress(self, mock_scene, mock_video, tmp_path):
        """on_progress receives scene_progress events during per-scene phases."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.CAPTIONS)
        _set_phase_state(state, PipelinePhase.CAPTION_GENERATION, PhaseStatus.COMPLETED)

        events = []
        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
            on_progress=lambda t, d: events.append((t, d)),
        )

        scene_events = [(t, d) for t, d in events if t == "scene_progress"]
        assert len(scene_events) == 2
        assert scene_events[0][1]["scene_number"] == 1
        assert scene_events[1][1]["scene_number"] == 2


# ---------------------------------------------------------------------------
# TestRunPerSceneCallback — on_scene_done callback invocation
# ---------------------------------------------------------------------------


class TestRunPerSceneCallback:
    """_run_per_scene invokes on_scene_done after each scene."""

    def test_callback_receives_scene_number_and_total(self, tmp_path):
        """on_scene_done called with (scene_number, total) for each scene."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=3, up_to_asset=AssetType.IMAGE_PROMPT)
        _set_phase_state(state, PipelinePhase.IMAGE_GENERATION, PhaseStatus.IN_PROGRESS)

        calls = []
        _run_per_scene(state, lambda scene: None, on_scene_done=lambda n, t: calls.append((n, t)))

        assert calls == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------------------
# TestRunPipelinePerSceneSkip — completed scenes are skipped
# ---------------------------------------------------------------------------


class TestRunPipelinePerSceneSkip:
    """Per-scene phases skip scenes whose asset is already completed."""

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    def test_tts_skips_completed_scenes(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """Scene 1 audio COMPLETED, scene 2 PENDING -> only scene 2 processed."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.IMAGE_PROMPT)

        # Scene 1: complete audio (skippable)
        state.update_scene_asset(1, AssetType.AUDIO, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.AUDIO, SceneStatus.COMPLETED)
        # Scene 2: audio stays PENDING (needs processing)

        _set_phase_state(state, PipelinePhase.NARRATION_PREP, PhaseStatus.COMPLETED)

        tts_provider = MagicMock()
        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=tts_provider,
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # generate_audio called only for scene 2 (scene 1 was skipped)
        assert mock_audio.call_count == 1
        scene_arg = mock_audio.call_args[0][0]
        assert scene_arg.scene_number == 2


# ---------------------------------------------------------------------------
# TestRunPipelineLazyProviders — providers not needed at checkpoints
# ---------------------------------------------------------------------------


class TestRunPipelineLazyProviders:
    """Provider arguments are not required when the pipeline pauses early."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_providers_not_created_at_checkpoint(self, mock_split, tmp_path):
        """Semi-auto pauses at SCENE_SPLITTING — no TTS/image/caption provider needed."""
        state = _make_adapt_state(tmp_path, autonomous=False)
        _set_phase_state(state, PipelinePhase.ANALYSIS, PhaseStatus.AWAITING_REVIEW)

        # Pass None for all providers — they shouldn't be touched
        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )

        # Pipeline paused at checkpoint without needing providers
        assert state.metadata.current_phase == PipelinePhase.SCENE_SPLITTING
        assert state.metadata.status == PhaseStatus.AWAITING_REVIEW
        mock_split.assert_called_once()


# ---------------------------------------------------------------------------
# TestDispatchPhaseUnknown — defensive ValueError for unknown phases
# ---------------------------------------------------------------------------


class TestDispatchPhaseUnknown:
    """_dispatch_phase raises ValueError for unrecognized phases."""

    def test_unknown_phase_raises_value_error(self, tmp_path):
        """Passing an unrecognized phase raises ValueError."""
        state = _make_adapt_state(tmp_path)
        sentinel = object()
        with pytest.raises(ValueError, match="Unknown phase"):
            _dispatch_phase(
                sentinel,  # type: ignore[arg-type]
                state,
                claude_client=None,
                tts_provider=None,
                image_provider=None,
                caption_provider=None,
            )


# ---------------------------------------------------------------------------
# TestDispatchPhaseProviderGuards — fail-fast when required provider is None
# ---------------------------------------------------------------------------


class TestDispatchPhaseProviderGuards:
    """_dispatch_phase raises ValueError when required provider is None."""

    @pytest.mark.parametrize(
        "phase,missing_provider",
        [
            (PipelinePhase.SCENE_SPLITTING, "claude_client"),
            (PipelinePhase.NARRATION_FLAGGING, "claude_client"),
            (PipelinePhase.VISUAL_REFERENCE, "claude_client"),
            (PipelinePhase.IMAGE_PROMPTS, "claude_client"),
            (PipelinePhase.TTS_GENERATION, "tts_provider"),
            (PipelinePhase.IMAGE_GENERATION, "image_provider"),
            (PipelinePhase.CAPTION_GENERATION, "caption_provider"),
            (PipelinePhase.NARRATION_PREP, "claude_client"),
            (PipelinePhase.ANALYSIS, "claude_client"),
            (PipelinePhase.STORY_BIBLE, "claude_client"),
            (PipelinePhase.OUTLINE, "claude_client"),
            (PipelinePhase.SCENE_PROSE, "claude_client"),
            (PipelinePhase.CRITIQUE_REVISION, "claude_client"),
        ],
    )
    def test_phase_requires_provider(self, adapt_state, phase, missing_provider):
        providers = {
            "claude_client": MagicMock(),
            "tts_provider": MagicMock(),
            "image_provider": MagicMock(),
            "caption_provider": MagicMock(),
        }
        providers[missing_provider] = None
        with pytest.raises(ValueError, match=missing_provider):
            _dispatch_phase(phase, adapt_state, **providers)


# ---------------------------------------------------------------------------
# TestDispatchCreativePhases — creative phase dispatch routing
# ---------------------------------------------------------------------------


class TestDispatchCreativePhases:
    """_dispatch_phase routes creative phases to story_writer functions."""

    @pytest.mark.parametrize(
        "phase,func_name",
        [
            (PipelinePhase.ANALYSIS, "analyze_source"),
            (PipelinePhase.STORY_BIBLE, "create_story_bible"),
            (PipelinePhase.OUTLINE, "create_outline"),
            (PipelinePhase.SCENE_PROSE, "write_scene_prose"),
            (PipelinePhase.CRITIQUE_REVISION, "critique_and_revise"),
        ],
    )
    def test_dispatches_creative_phase(self, mocker, phase, func_name):
        """Creative phases dispatch to the correct story_writer function."""
        mock_fn = mocker.patch(f"story_video.pipeline.orchestrator.{func_name}")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            phase,
            state,
            claude_client=client,
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)


# ---------------------------------------------------------------------------
# TestDispatchVisualReference — VISUAL_REFERENCE dispatch routing
# ---------------------------------------------------------------------------


class TestDispatchVisualReference:
    """_dispatch_phase dispatches VISUAL_REFERENCE to generate_visual_reference."""

    def test_dispatches_visual_reference(self, tmp_path):
        """VISUAL_REFERENCE phase calls generate_visual_reference(state, client)."""
        state = _make_adapt_state(tmp_path)
        mock_claude = MagicMock()

        with patch("story_video.pipeline.orchestrator.generate_visual_reference") as mock_fn:
            _dispatch_phase(
                state=state,
                phase=PipelinePhase.VISUAL_REFERENCE,
                claude_client=mock_claude,
                tts_provider=None,
                image_provider=None,
                caption_provider=None,
                story_header=None,
            )

        mock_fn.assert_called_once_with(state, mock_claude)


# ---------------------------------------------------------------------------
# TestVisualReferencePhaseOrder — VISUAL_REFERENCE position in phase sequences
# ---------------------------------------------------------------------------


class TestVisualReferencePhaseOrder:
    """VISUAL_REFERENCE phase appears in the correct position in both flows."""

    def test_creative_flow_order(self):
        """VISUAL_REFERENCE comes after CRITIQUE_REVISION and before IMAGE_PROMPTS."""
        from story_video.models import CREATIVE_FLOW_PHASES, PipelinePhase

        phases = list(CREATIVE_FLOW_PHASES)
        vr_idx = phases.index(PipelinePhase.VISUAL_REFERENCE)
        cr_idx = phases.index(PipelinePhase.CRITIQUE_REVISION)
        ip_idx = phases.index(PipelinePhase.IMAGE_PROMPTS)
        assert cr_idx < vr_idx < ip_idx

    def test_adapt_flow_order(self):
        """VISUAL_REFERENCE comes after NARRATION_FLAGGING and before IMAGE_PROMPTS."""
        from story_video.models import ADAPT_FLOW_PHASES, PipelinePhase

        phases = list(ADAPT_FLOW_PHASES)
        vr_idx = phases.index(PipelinePhase.VISUAL_REFERENCE)
        nf_idx = phases.index(PipelinePhase.NARRATION_FLAGGING)
        ip_idx = phases.index(PipelinePhase.IMAGE_PROMPTS)
        assert nf_idx < vr_idx < ip_idx


# ---------------------------------------------------------------------------
# TestVisualReferenceDownstream — visual_reference feeds into image_prompt_writer
# ---------------------------------------------------------------------------


class TestVisualReferenceDownstream:
    """image_prompt_writer reads visual_reference.json produced by visual_reference_writer."""

    def test_image_prompts_use_visual_reference(self, tmp_path):
        """Run visual_reference then image_prompts — image prompts include character data."""
        import json
        from unittest.mock import MagicMock

        from story_video.models import AppConfig, AssetType, InputMode, SceneStatus
        from story_video.pipeline.image_prompt_writer import generate_image_prompts
        from story_video.pipeline.visual_reference_writer import generate_visual_reference

        state = ProjectState.create("integ-test", InputMode.ADAPT, AppConfig(), tmp_path)
        state.add_scene(1, "The Forest", "Sim ran through the dark forest.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        # Write analysis.json for visual_reference_writer
        analysis = {
            "craft_notes": {"tone": "Dark"},
            "thematic_brief": {"themes": ["Survival"]},
            "source_stats": {"word_count": 100, "scene_count_estimate": 1},
            "characters": [{"name": "Sim", "visual_description": "A teenage girl."}],
        }
        (state.project_dir / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")

        # Mock Claude for visual reference generation
        vr_client = MagicMock()
        vr_client.generate_structured.return_value = {
            "characters": [
                {"name": "Sim", "visual_description": "15-year-old girl with dark braids."}
            ],
            "setting": {"visual_summary": "Post-apocalyptic suburban ruins."},
        }
        generate_visual_reference(state, vr_client)

        # Mock Claude for image prompt generation
        ip_client = MagicMock()
        ip_client.generate_structured.return_value = {
            "prompts": [{"scene_number": 1, "image_prompt": "A girl runs through a forest."}]
        }
        generate_image_prompts(state, ip_client)

        # Verify image prompt writer received the visual reference data
        call_kwargs = ip_client.generate_structured.call_args.kwargs
        user_msg = call_kwargs["user_message"]
        assert "Sim" in user_msg
        assert "dark braids" in user_msg
        assert "Post-apocalyptic" in user_msg


# ---------------------------------------------------------------------------
# TestStoryHeaderParsing — orchestrator parses story header before TTS phase
# ---------------------------------------------------------------------------


class TestStoryHeaderParsing:
    """Orchestrator parses story header before TTS phase."""

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    def test_header_parsed_and_passed_to_generate_audio(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """When source_story.txt has a YAML header, story_header is passed to generate_audio."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.IMAGE_PROMPT)

        # Set narration_text so narration prep has something to transform
        scene = state.metadata.scenes[0]
        scene.narration_text = "Some narration text."

        # Write source_story.txt with YAML header
        source_path = state.project_dir / "source_story.txt"
        header_yaml = (
            "---\n"
            "voices:\n"
            "  narrator: alloy\n"
            "  villain: echo\n"
            "default_voice: narrator\n"
            "---\n"
            "The story body."
        )
        source_path.write_text(header_yaml, encoding="utf-8")

        _set_phase_state(state, PipelinePhase.NARRATION_PREP, PhaseStatus.COMPLETED)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        # generate_audio should have been called with the parsed StoryHeader
        assert mock_audio.call_count == 1
        # story_header passed as keyword arg in the lambda
        story_header_arg = mock_audio.call_args.kwargs.get("story_header")
        assert story_header_arg is not None
        assert isinstance(story_header_arg, StoryHeader)
        assert story_header_arg.voices == {"narrator": "alloy", "villain": "echo"}
        assert story_header_arg.default_voice == "narrator"

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    def test_no_header_passes_none(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """When source_story.txt has no header, story_header=None is passed."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.IMAGE_PROMPT)

        scene = state.metadata.scenes[0]
        scene.narration_text = "Some narration text."

        # Write source_story.txt without YAML header
        source_path = state.project_dir / "source_story.txt"
        source_path.write_text("Just a plain story without a header.", encoding="utf-8")

        _set_phase_state(state, PipelinePhase.NARRATION_PREP, PhaseStatus.COMPLETED)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        assert mock_audio.call_count == 1
        assert mock_audio.call_args.kwargs.get("story_header") is None

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch(
        "story_video.pipeline.orchestrator.prepare_narration_llm",
        return_value={
            "modified_text": "prepped",
            "changes": [],
            "pronunciation_guide_additions": [],
        },
    )
    def test_no_source_file_passes_none(
        self,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """When source_story.txt doesn't exist, story_header=None is passed."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=1, up_to_asset=AssetType.IMAGE_PROMPT)

        scene = state.metadata.scenes[0]
        scene.narration_text = "Some narration text."

        # Don't write source_story.txt at all

        _set_phase_state(state, PipelinePhase.NARRATION_PREP, PhaseStatus.COMPLETED)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        assert mock_audio.call_count == 1
        assert mock_audio.call_args.kwargs.get("story_header") is None

    def test_malformed_header_raises_descriptive_error(self, tmp_path):
        """Malformed YAML in source_story.txt raises ValueError with clear message."""
        state = _make_adapt_state(tmp_path, autonomous=True)

        source_path = state.project_dir / "source_story.txt"
        source_path.write_text("---\n: bad: yaml: {{{\n---\nBody.", encoding="utf-8")

        with pytest.raises(ValueError, match="[Ss]tory header"):
            _parse_source_header(state)


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
        # Scene texts — source_story.txt must equal these joined by "\n\n"
        scene1_text = (
            "The lighthouse keeper watched the storm approach. "
            "Dark clouds gathered on the horizon, and the waves grew tall."
        )
        scene2_text = (
            "By morning the storm had passed. The keeper climbed the tower "
            "and lit the lamp, its beam cutting through the dawn mist."
        )
        source_text = scene1_text + "\n\n" + scene2_text

        # --- Mock Claude client ---
        claude_responses = {
            "analyze_source": {
                "craft_notes": {
                    "sentence_structure": "Simple declarative.",
                    "vocabulary": "Concrete and nautical.",
                    "tone": "Quiet, observational.",
                    "pacing": "Measured.",
                    "narrative_voice": "Third person limited.",
                },
                "thematic_brief": {
                    "themes": ["isolation", "duty"],
                    "emotional_arc": "Tension to relief",
                    "central_tension": "Nature vs. responsibility",
                    "mood": "Atmospheric",
                },
                "source_stats": {
                    "word_count": len(source_text.split()),
                    "scene_count_estimate": 2,
                },
                "characters": [
                    {
                        "name": "The Keeper",
                        "visual_description": (
                            "A weathered man in his sixties, grey stubble, navy peacoat."
                        ),
                    },
                ],
            },
            "split_into_scenes": {
                "scenes": [
                    {"title": "The Storm", "text": scene1_text},
                    {"title": "The Dawn", "text": scene2_text},
                ],
            },
            "flag_narration_issues": {"flags": []},
            "generate_visual_reference": {
                "characters": [
                    {
                        "name": "The Keeper",
                        "visual_description": (
                            "A weathered man in his sixties, grey stubble, navy peacoat."
                        ),
                    },
                ],
                "setting": {"visual_summary": "A lonely lighthouse on a rocky coast."},
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
        mock_claude.generate_structured = MagicMock(
            side_effect=_make_claude_dispatch(claude_responses)
        )

        # --- Mock providers ---
        mock_tts, mock_image, mock_caption = _make_mock_providers()
        mock_caption.transcribe = MagicMock(
            side_effect=lambda path: _make_simple_caption_result("Transcribed narration text.")
        )

        # --- Mock subprocess.run (FFmpeg/ffprobe) ---
        monkeypatch.setattr("subprocess.run", _make_mock_subprocess_run())

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

        assert "lighthouse" in scene1.prose.lower()
        assert "dawn" in scene2.prose.lower()
        assert scene1.narration_text is not None
        assert scene2.narration_text is not None
        assert "lighthouse" in scene1.image_prompts[0].prompt.lower()
        assert "dawn" in scene2.image_prompts[0].prompt.lower()

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
        assert (pd / "scenes" / "scene_001.md").exists()
        assert (pd / "scenes" / "scene_002.md").exists()
        assert (pd / "audio" / "scene_001.mp3").exists()
        assert (pd / "audio" / "scene_002.mp3").exists()
        assert (pd / "images" / "scene_001_000.png").exists()
        assert (pd / "images" / "scene_002_000.png").exists()
        assert (pd / "captions" / "scene_001.json").exists()
        assert (pd / "captions" / "scene_002.json").exists()
        assert (pd / "captions" / "scene_001.ass").exists()
        assert (pd / "captions" / "scene_002.ass").exists()
        assert (pd / "segments" / "scene_001.mp4").exists()
        assert (pd / "segments" / "scene_002.mp4").exists()
        assert (pd / "final.mp4").exists()

        # --- Verify analysis.json exists ---
        assert (pd / "analysis.json").exists()

        # --- Verify external APIs were called ---
        # 5 calls (analysis + split + flag + visual_ref + prompts) + 2 narration prep
        assert mock_claude.generate_structured.call_count == 7
        assert mock_tts.synthesize.call_count == 2
        assert mock_image.generate.call_count == 2
        assert mock_caption.transcribe.call_count == 2

        # --- Verify state was persisted to disk ---
        reloaded = ProjectState.load(pd)
        assert reloaded.metadata.status == PhaseStatus.COMPLETED
        assert len(reloaded.metadata.scenes) == 2

    def test_adapt_pipeline_with_inline_image_tags(self, tmp_path, monkeypatch):
        """Adapt pipeline with YAML-defined image tags flows through full pipeline.

        Verifies end-to-end: YAML header parsing -> tag extraction ->
        narration text stripping -> multi-image generation (indexed files) ->
        caption-aligned timing -> multi-image FFmpeg command -> final assembly.
        """
        # --- Source story with YAML header and image tags ---
        # Scene 1 has two image tags; scene 2 has one (will get Claude-generated prompt).
        source_text = (
            "---\n"
            "voices:\n"
            "  narrator: nova\n"
            "images:\n"
            "  lighthouse: A weathered stone lighthouse on a rocky cliff\n"
            "  harbor: A small fishing harbor with colorful boats at dawn\n"
            "---\n"
            "**voice:narrator** The lighthouse keeper watched the storm "
            "approach. **image:lighthouse** Dark clouds gathered on the "
            "horizon, and the waves grew tall.\n"
            "\n"
            "By morning the storm had passed. The keeper climbed the "
            "tower and lit the lamp. **image:harbor** The harbor below "
            "came alive with fishing boats."
        )

        # Expected scene texts after split (Claude returns these)
        scene1_text = (
            "**voice:narrator** The lighthouse keeper watched the storm "
            "approach. **image:lighthouse** Dark clouds gathered on the "
            "horizon, and the waves grew tall."
        )
        scene2_text = (
            "By morning the storm had passed. The keeper climbed the "
            "tower and lit the lamp. **image:harbor** The harbor below "
            "came alive with fishing boats."
        )

        # --- Mock Claude client ---
        claude_responses = {
            "analyze_source": {
                "craft_notes": {
                    "sentence_structure": "Simple declarative.",
                    "vocabulary": "Concrete and nautical.",
                    "tone": "Quiet, observational.",
                    "pacing": "Measured.",
                    "narrative_voice": "Third person limited.",
                },
                "thematic_brief": {
                    "themes": ["isolation", "duty"],
                    "emotional_arc": "Tension to relief",
                    "central_tension": "Nature vs. responsibility",
                    "mood": "Atmospheric",
                },
                "source_stats": {
                    "word_count": 50,
                    "scene_count_estimate": 2,
                },
                "characters": [
                    {
                        "name": "The Keeper",
                        "visual_description": "A weathered man in navy peacoat.",
                    },
                ],
            },
            "split_into_scenes": {
                "scenes": [
                    {"title": "The Storm", "text": scene1_text},
                    {"title": "The Dawn", "text": scene2_text},
                ],
            },
            "flag_narration_issues": {"flags": []},
            "generate_visual_reference": {
                "characters": [
                    {
                        "name": "The Keeper",
                        "visual_description": (
                            "A weathered man in his sixties, grey stubble, navy peacoat."
                        ),
                    },
                ],
                "setting": {"visual_summary": "A lonely lighthouse on a rocky coast."},
            },
            # Claude only generates prompts for untagged scenes — scene 2 has
            # one image tag, so it's tagged. Scene 1 also has a tag.
            # But generate_image_prompts sends untagged scenes to Claude.
            # Both scenes have tags, so Claude should NOT be called for prompts.
            "generate_image_prompts": {
                "prompts": [],
            },
        }

        mock_claude = MagicMock()
        mock_claude.generate_structured = MagicMock(
            side_effect=_make_claude_dispatch(claude_responses)
        )

        # --- Mock providers ---
        mock_tts, mock_image, mock_caption = _make_mock_providers()
        # Captions need enough words and duration for image timing validation.
        # min_display=4.0 + crossfade=1.5 = 5.5s per image. Two images need ~11s.
        _image_tag_words = [
            "The",
            "lighthouse",
            "keeper",
            "watched",
            "the",
            "storm",
            "approach",
            "dark",
            "clouds",
            "gathered",
            "on",
            "the",
            "horizon",
            "and",
            "the",
            "waves",
            "grew",
            "tall",
            "the",
            "harbor",
            "below",
            "came",
            "alive",
        ]
        mock_caption.transcribe = MagicMock(
            side_effect=lambda path: _make_timed_caption_result(_image_tag_words, 15.0)
        )

        # --- Mock subprocess.run (FFmpeg/ffprobe) ---
        ffmpeg_commands: list[list[str]] = []
        monkeypatch.setattr(
            "subprocess.run",
            _make_mock_subprocess_run(duration="15.0", capture_commands=ffmpeg_commands),
        )

        # --- Create project state and run pipeline ---
        state = _make_adapt_state(tmp_path, autonomous=True)
        source_path = state.project_dir / "source_story.txt"
        source_path.write_text(source_text, encoding="utf-8")

        run_pipeline(
            state,
            claude_client=mock_claude,
            tts_provider=mock_tts,
            image_provider=mock_image,
            caption_provider=mock_caption,
        )

        # --- Verify pipeline completed ---
        assert state.metadata.status == PhaseStatus.COMPLETED
        assert len(state.metadata.scenes) == 2

        # --- Verify image tags were extracted and prompts populated ---
        scene1 = state.metadata.scenes[0]
        scene2 = state.metadata.scenes[1]
        assert len(scene1.image_prompts) == 1
        assert scene1.image_prompts[0].key == "lighthouse"
        assert "lighthouse" in scene1.image_prompts[0].prompt.lower()
        assert len(scene2.image_prompts) == 1
        assert scene2.image_prompts[0].key == "harbor"
        assert "harbor" in scene2.image_prompts[0].prompt.lower()

        # --- Verify image tags stripped from narration text ---
        assert "**image:" not in (scene1.narration_text or "")
        assert "**image:" not in (scene2.narration_text or "")
        # Voice tags should still be present (stripped by TTS, not here)
        assert "**voice:narrator**" in (scene1.narration_text or "")

        # --- Verify indexed image files created ---
        pd = state.project_dir
        assert (pd / "images" / "scene_001_000.png").exists()
        assert (pd / "images" / "scene_002_000.png").exists()

        # --- Verify Claude was NOT called for image prompts ---
        # Both scenes have image tags, so generate_image_prompts should
        # skip Claude entirely. Calls: analysis + split + flag + visual_ref + 2x narration_prep = 6
        prompt_calls = [
            c
            for c in mock_claude.generate_structured.call_args_list
            if c.kwargs.get("tool_name") == "generate_image_prompts"
        ]
        assert len(prompt_calls) == 0

        # --- Verify image provider was called for each image ---
        assert mock_image.generate.call_count == 2  # 1 per scene (1 tag each)

        # --- Verify final video assembled ---
        assert (pd / "final.mp4").exists()
        assert (pd / "segments" / "scene_001.mp4").exists()
        assert (pd / "segments" / "scene_002.mp4").exists()

    def test_adapt_pipeline_with_background_music(self, tmp_path, monkeypatch):
        """Adapt pipeline with YAML audio map and music tags flows through full pipeline.

        Verifies end-to-end: YAML header parsing -> music tag extraction ->
        narration text stripping -> audio file resolution -> caption-aligned
        timing -> amix FFmpeg filter -> final assembly.
        """
        # --- Source story with YAML header including audio map and music tags ---
        source_text = (
            "---\n"
            "voices:\n"
            "  narrator: nova\n"
            "audio:\n"
            "  rain:\n"
            "    file: sounds/rain.mp3\n"
            "    volume: 0.2\n"
            "    loop: true\n"
            "  thunder:\n"
            "    file: sounds/thunder.mp3\n"
            "    volume: 0.6\n"
            "---\n"
            "The rain began to fall. **music:rain** The lighthouse keeper "
            "pulled his coat tighter. **music:thunder** A crack of "
            "lightning split the sky.\n"
            "\n"
            "By morning the storm had passed. The keeper climbed the "
            "tower and lit the lamp."
        )

        # Expected scene texts after split (Claude returns these)
        scene1_text = (
            "The rain began to fall. **music:rain** The lighthouse keeper "
            "pulled his coat tighter. **music:thunder** A crack of "
            "lightning split the sky."
        )
        scene2_text = (
            "By morning the storm had passed. The keeper climbed the tower and lit the lamp."
        )

        # --- Mock Claude client ---
        claude_responses = {
            "analyze_source": {
                "craft_notes": {
                    "sentence_structure": "Simple declarative.",
                    "vocabulary": "Concrete and nautical.",
                    "tone": "Quiet, observational.",
                    "pacing": "Measured.",
                    "narrative_voice": "Third person limited.",
                },
                "thematic_brief": {
                    "themes": ["isolation", "duty"],
                    "emotional_arc": "Tension to relief",
                    "central_tension": "Nature vs. responsibility",
                    "mood": "Atmospheric",
                },
                "source_stats": {
                    "word_count": 50,
                    "scene_count_estimate": 2,
                },
                "characters": [
                    {
                        "name": "The Keeper",
                        "visual_description": "A weathered man in navy peacoat.",
                    },
                ],
            },
            "split_into_scenes": {
                "scenes": [
                    {"title": "The Storm", "text": scene1_text},
                    {"title": "The Dawn", "text": scene2_text},
                ],
            },
            "flag_narration_issues": {"flags": []},
            "generate_visual_reference": {
                "characters": [
                    {
                        "name": "The Keeper",
                        "visual_description": "A weathered man in navy peacoat.",
                    },
                ],
                "setting": {"visual_summary": "A lonely lighthouse on a rocky coast."},
            },
            "generate_image_prompts": {
                "prompts": [
                    {
                        "scene_number": 1,
                        "image_prompt": "A lighthouse in a storm with rain and lightning.",
                    },
                    {
                        "scene_number": 2,
                        "image_prompt": "Golden dawn light through lighthouse glass.",
                    },
                ],
            },
        }

        mock_claude = MagicMock()
        mock_claude.generate_structured = MagicMock(
            side_effect=_make_claude_dispatch(claude_responses)
        )

        # --- Mock providers ---
        mock_tts, mock_image, mock_caption = _make_mock_providers()
        _music_words = [
            "The",
            "rain",
            "began",
            "to",
            "fall",
            "the",
            "lighthouse",
            "keeper",
            "pulled",
            "his",
            "coat",
            "tighter",
            "a",
            "crack",
            "of",
            "lightning",
            "split",
            "the",
            "sky",
        ]
        mock_caption.transcribe = MagicMock(
            side_effect=lambda path: _make_timed_caption_result(_music_words, 12.0)
        )

        # --- Mock subprocess.run (FFmpeg/ffprobe) ---
        ffmpeg_commands: list[list[str]] = []
        monkeypatch.setattr(
            "subprocess.run",
            _make_mock_subprocess_run(duration="12.0", capture_commands=ffmpeg_commands),
        )

        # --- Create project state ---
        state = _make_adapt_state(tmp_path, autonomous=True)
        source_path = state.project_dir / "source_story.txt"
        source_path.write_text(source_text, encoding="utf-8")

        # --- Create audio files on disk ---
        sounds_dir = state.project_dir / "sounds"
        sounds_dir.mkdir()
        (sounds_dir / "rain.mp3").write_bytes(b"\xff" * 50)
        (sounds_dir / "thunder.mp3").write_bytes(b"\xff" * 50)

        # --- Run the full pipeline ---
        run_pipeline(
            state,
            claude_client=mock_claude,
            tts_provider=mock_tts,
            image_provider=mock_image,
            caption_provider=mock_caption,
        )

        # --- Verify pipeline completed ---
        assert state.metadata.status == PhaseStatus.COMPLETED
        assert len(state.metadata.scenes) == 2

        # --- Verify audio cues extracted on scene 1 ---
        scene1 = state.metadata.scenes[0]
        scene2 = state.metadata.scenes[1]
        assert len(scene1.audio_cues) == 2
        assert scene1.audio_cues[0].key == "rain"
        assert scene1.audio_cues[1].key == "thunder"
        # Scene 2 has no music tags
        assert scene2.audio_cues == []

        # --- Verify music tags stripped from narration text ---
        assert "**music:" not in (scene1.narration_text or "")
        assert "**music:" not in (scene2.narration_text or "")

        # --- Verify FFmpeg scene 1 command includes amix ---
        # Scene 1 has audio cues, scene 2 does not.
        # ffmpeg_commands[0] = scene 1 segment, [1] = scene 2 segment, [2] = concat
        scene1_cmd_str = " ".join(str(c) for c in ffmpeg_commands[0])
        assert "amix" in scene1_cmd_str
        assert "rain.mp3" in scene1_cmd_str
        assert "thunder.mp3" in scene1_cmd_str

        # --- Verify scene 2 command does NOT include amix ---
        scene2_cmd_str = " ".join(str(c) for c in ffmpeg_commands[1])
        assert "amix" not in scene2_cmd_str

        # --- Verify final video assembled ---
        pd = state.project_dir
        assert (pd / "final.mp4").exists()

    def test_full_creative_flow_data_flow(self, tmp_path, monkeypatch):
        """Full creative flow (inspired_by) creates expected files and state transitions."""
        scene1_prose = "The old woman sat alone in the empty theater, listening to silence."
        scene2_prose = "She rose from her seat and walked toward the stage, footsteps echoing."

        # --- Mock Claude client ---
        # Creative flow needs write_scene and critique_scene to branch on user_message
        # content, so we wrap _make_claude_dispatch with a custom side_effect.
        claude_responses = {
            "analyze_source": {
                "craft_notes": {"style": "literary fiction", "tone": "melancholic"},
                "thematic_brief": {"themes": ["solitude", "memory"]},
                "source_stats": {"word_count": 200, "scene_count_estimate": 2},
            },
            "create_story_bible": {
                "characters": [{"name": "The Old Woman", "role": "protagonist"}],
                "setting": {
                    "place": "An abandoned theater",
                    "time_period": "Modern",
                    "atmosphere": "Eerie",
                },
                "world_rules": [],
            },
            "create_outline": {
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "The Silence",
                        "beat": "Introduction",
                        "target_words": 100,
                    },
                    {
                        "scene_number": 2,
                        "title": "The Stage",
                        "beat": "Rising action",
                        "target_words": 100,
                    },
                ]
            },
            "generate_visual_reference": {
                "characters": [
                    {
                        "name": "The Old Woman",
                        "visual_description": "An elderly woman in a worn shawl.",
                    },
                ],
                "setting": {"visual_summary": "An abandoned theater."},
            },
            "generate_image_prompts": {
                "prompts": [
                    {"scene_number": 1, "image_prompt": "Empty theater with one person."},
                    {"scene_number": 2, "image_prompt": "Woman walking toward lit stage."},
                ]
            },
        }

        _base_dispatch = _make_claude_dispatch(claude_responses)

        def _creative_dispatch(**kwargs):
            tool_name = kwargs.get("tool_name", "")
            if tool_name == "write_scene":
                user_msg = kwargs.get("user_message", "")
                if "## Current Scene: The Silence" in user_msg:
                    return {"prose": scene1_prose, "summary": "Old woman sits in theater."}
                return {"prose": scene2_prose, "summary": "She walks to the stage."}
            if tool_name == "critique_scene":
                user_msg = kwargs.get("user_message", "")
                if "theater" in user_msg and "listening" in user_msg:
                    return {"revised_prose": scene1_prose, "changes": []}
                return {"revised_prose": scene2_prose, "changes": []}
            return _base_dispatch(**kwargs)

        mock_claude = MagicMock()
        mock_claude.generate_structured = MagicMock(side_effect=_creative_dispatch)

        # --- Mock providers ---
        mock_tts, mock_image, mock_caption = _make_mock_providers()
        mock_caption.transcribe = MagicMock(
            side_effect=lambda path: _make_simple_caption_result("Transcribed narration text.")
        )

        # --- Mock subprocess.run (FFmpeg/ffprobe) ---
        monkeypatch.setattr("subprocess.run", _make_mock_subprocess_run())

        # --- Create project state (INSPIRED_BY mode) ---
        config = AppConfig(pipeline=PipelineConfig(autonomous=True))
        state = ProjectState.create("creative-test", InputMode.INSPIRED_BY, config, tmp_path)

        # Write source story
        source_path = state.project_dir / "source_story.txt"
        source_path.write_text("A short story about an old woman in a theater.", encoding="utf-8")

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

        # --- Verify creative flow artifacts ---
        pd = state.project_dir
        assert (pd / "analysis.json").exists()
        assert (pd / "story_bible.json").exists()
        assert (pd / "outline.json").exists()
        assert (pd / "critique" / "scene_001_changes.md").exists()
        assert (pd / "critique" / "scene_002_changes.md").exists()

        # --- Verify scene data ---
        scene1 = state.metadata.scenes[0]
        scene2 = state.metadata.scenes[1]
        assert "theater" in scene1.prose.lower()
        assert "stage" in scene2.prose.lower()

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
        assert (pd / "scenes" / "scene_001.md").exists()
        assert (pd / "scenes" / "scene_002.md").exists()
        assert (pd / "audio" / "scene_001.mp3").exists()
        assert (pd / "audio" / "scene_002.mp3").exists()
        assert (pd / "images" / "scene_001_000.png").exists()
        assert (pd / "images" / "scene_002_000.png").exists()
        assert (pd / "final.mp4").exists()

        # --- Verify external APIs were called ---
        # analyze + bible + outline + 2 prose + 2 critique
        # + visual_ref + prompts + 2 narration prep = 11
        assert mock_claude.generate_structured.call_count == 11
        assert mock_tts.synthesize.call_count == 2
        assert mock_image.generate.call_count == 2
        assert mock_caption.transcribe.call_count == 2

        # --- Verify state was persisted to disk ---
        reloaded = ProjectState.load(pd)
        assert reloaded.metadata.status == PhaseStatus.COMPLETED
        assert len(reloaded.metadata.scenes) == 2

    def test_full_original_mode_data_flow(self, tmp_path, monkeypatch):
        """Full creative flow (original) uses brief prompt and config-derived source_stats."""
        scene1_prose = "The old woman sat alone in the empty theater, listening to silence."
        scene2_prose = "She rose from her seat and walked toward the stage, footsteps echoing."

        # --- Mock Claude client ---
        # Same creative flow dispatch as inspired_by, reuses _make_claude_dispatch
        # with write_scene/critique_scene branching on user_message content.
        claude_responses = {
            "analyze_source": {
                "craft_notes": {"style": "literary fiction", "tone": "melancholic"},
                "thematic_brief": {"themes": ["solitude", "memory"]},
                "source_stats": {"word_count": 200, "scene_count_estimate": 2},
            },
            "create_story_bible": {
                "characters": [{"name": "The Old Woman", "role": "protagonist"}],
                "setting": {
                    "place": "An abandoned theater",
                    "time_period": "Modern",
                    "atmosphere": "Eerie",
                },
                "world_rules": [],
            },
            "create_outline": {
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "The Silence",
                        "beat": "Introduction",
                        "target_words": 100,
                    },
                    {
                        "scene_number": 2,
                        "title": "The Stage",
                        "beat": "Rising action",
                        "target_words": 100,
                    },
                ]
            },
            "generate_visual_reference": {
                "characters": [
                    {
                        "name": "The Old Woman",
                        "visual_description": "An elderly woman in a worn shawl.",
                    },
                ],
                "setting": {"visual_summary": "An abandoned theater."},
            },
            "generate_image_prompts": {
                "prompts": [
                    {"scene_number": 1, "image_prompt": "Empty theater with one person."},
                    {"scene_number": 2, "image_prompt": "Woman walking toward lit stage."},
                ]
            },
        }

        _base_dispatch = _make_claude_dispatch(claude_responses)

        def _creative_dispatch(**kwargs):
            tool_name = kwargs.get("tool_name", "")
            if tool_name == "write_scene":
                user_msg = kwargs.get("user_message", "")
                if "## Current Scene: The Silence" in user_msg:
                    return {"prose": scene1_prose, "summary": "Old woman sits in theater."}
                return {"prose": scene2_prose, "summary": "She walks to the stage."}
            if tool_name == "critique_scene":
                user_msg = kwargs.get("user_message", "")
                if "theater" in user_msg and "listening" in user_msg:
                    return {"revised_prose": scene1_prose, "changes": []}
                return {"revised_prose": scene2_prose, "changes": []}
            return _base_dispatch(**kwargs)

        mock_claude = MagicMock()
        mock_claude.generate_structured = MagicMock(side_effect=_creative_dispatch)

        # --- Mock providers ---
        mock_tts, mock_image, mock_caption = _make_mock_providers()
        mock_caption.transcribe = MagicMock(
            side_effect=lambda path: _make_simple_caption_result("Transcribed narration text.")
        )

        # --- Mock subprocess.run (FFmpeg/ffprobe) ---
        monkeypatch.setattr("subprocess.run", _make_mock_subprocess_run())

        # --- Create project state (ORIGINAL mode) ---
        config = AppConfig(pipeline=PipelineConfig(autonomous=True))
        state = ProjectState.create("original-test", InputMode.ORIGINAL, config, tmp_path)

        # Write creative brief (not a full story)
        source_path = state.project_dir / "source_story.txt"
        source_path.write_text(
            "A story about love and sacrifice between a married couple.",
            encoding="utf-8",
        )

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

        # --- Verify creative flow artifacts ---
        pd = state.project_dir
        assert (pd / "analysis.json").exists()
        assert (pd / "story_bible.json").exists()
        assert (pd / "outline.json").exists()
        assert (pd / "critique" / "scene_001_changes.md").exists()
        assert (pd / "critique" / "scene_002_changes.md").exists()

        # --- Verify scene data ---
        scene1 = state.metadata.scenes[0]
        scene2 = state.metadata.scenes[1]
        assert "theater" in scene1.prose.lower()
        assert "stage" in scene2.prose.lower()

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
        assert (pd / "scenes" / "scene_001.md").exists()
        assert (pd / "scenes" / "scene_002.md").exists()
        assert (pd / "audio" / "scene_001.mp3").exists()
        assert (pd / "audio" / "scene_002.mp3").exists()
        assert (pd / "images" / "scene_001_000.png").exists()
        assert (pd / "images" / "scene_002_000.png").exists()
        assert (pd / "final.mp4").exists()

        # --- Verify external APIs were called ---
        # analyze + bible + outline + 2 prose + 2 critique
        # + visual_ref + prompts + 2 narration prep = 11
        assert mock_claude.generate_structured.call_count == 11
        assert mock_tts.synthesize.call_count == 2
        assert mock_image.generate.call_count == 2
        assert mock_caption.transcribe.call_count == 2

        # --- Verify state was persisted to disk ---
        reloaded = ProjectState.load(pd)
        assert reloaded.metadata.status == PhaseStatus.COMPLETED
        assert len(reloaded.metadata.scenes) == 2

        # --- Verify ORIGINAL mode specifics ---
        # First Claude call should use BRIEF_ANALYSIS_SYSTEM prompt
        first_call_kwargs = mock_claude.generate_structured.call_args_list[0].kwargs
        assert "creative brief" in first_call_kwargs["system"].lower()

        # source_stats should be config-derived, not from Claude
        analysis = json.loads((pd / "analysis.json").read_text(encoding="utf-8"))
        assert analysis["source_stats"]["word_count"] == 4500
        assert analysis["source_stats"]["scene_count_estimate"] == 7


# ---------------------------------------------------------------------------
# TestPopulateImageTags — image tag extraction and prompt population
# ---------------------------------------------------------------------------


class TestPopulateImageTags:
    """_populate_image_tags extracts image tags and populates scene.image_prompts."""

    def test_scene_with_image_tags_gets_prompts(self, tmp_path):
        """Scene prose with image tags gets image_prompts populated from YAML."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        prose = "The lighthouse stood tall. **image:lighthouse** The harbor below."
        state.add_scene(1, "Test Scene", prose)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        header = StoryHeader(
            voices={"narrator": "alloy"},
            images={"lighthouse": "A tall lighthouse at dawn"},
        )

        _populate_image_tags(state, header)

        scene = state.metadata.scenes[0]
        assert len(scene.image_prompts) == 1
        assert scene.image_prompts[0].key == "lighthouse"
        assert scene.image_prompts[0].prompt == "A tall lighthouse at dawn"

    def test_scene_without_tags_unchanged(self, tmp_path):
        """Scene without image tags keeps empty image_prompts."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Test Scene", "The lighthouse stood tall. The harbor below.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        header = StoryHeader(voices={"narrator": "alloy"}, images={"lighthouse": "A lighthouse"})

        _populate_image_tags(state, header)

        scene = state.metadata.scenes[0]
        assert scene.image_prompts == []

    def test_undefined_tag_key_raises(self, tmp_path):
        """Image tag referencing undefined key raises ValueError."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Test", "Text **image:castle** more text")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        header = StoryHeader(voices={"narrator": "alloy"}, images={"lighthouse": "A lighthouse"})

        with pytest.raises(ValueError, match="castle"):
            _populate_image_tags(state, header)

    def test_no_header_with_tags_raises(self, tmp_path):
        """Image tags without a story header raises ValueError."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        state.add_scene(1, "Test", "Text **image:lighthouse** more")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        with pytest.raises(ValueError, match="no images defined"):
            _populate_image_tags(state, None)

    def test_strips_image_tags_from_narration_text(self, tmp_path):
        """_populate_image_tags strips image tags from scene.narration_text."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        prose = "The lighthouse stood tall. **image:lighthouse** The harbor below."
        state.add_scene(1, "Test Scene", prose)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        # Set narration_text with image tags (as adapt mode would)
        scene = state.metadata.scenes[0]
        scene.narration_text = "The lighthouse stood tall. **image:lighthouse** The harbor below."

        header = StoryHeader(
            voices={"narrator": "alloy"},
            images={"lighthouse": "A tall lighthouse at dawn"},
        )

        _populate_image_tags(state, header)

        assert "**image:" not in scene.narration_text
        assert scene.narration_text == "The lighthouse stood tall. The harbor below."

    def test_sets_narration_text_from_stripped_prose_when_none(self, tmp_path):
        """When narration_text is None, sets it to prose with image tags stripped."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        prose = "The lighthouse stood tall. **image:lighthouse** The harbor below."
        state.add_scene(1, "Test Scene", prose)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        # narration_text is None (creative flow)
        assert state.metadata.scenes[0].narration_text is None

        header = StoryHeader(
            voices={"narrator": "alloy"},
            images={"lighthouse": "A tall lighthouse at dawn"},
        )

        _populate_image_tags(state, header)

        scene = state.metadata.scenes[0]
        assert scene.narration_text == "The lighthouse stood tall. The harbor below."
        assert "**image:" not in scene.narration_text

    def test_uses_stripped_positions_for_image_prompts(self, tmp_path):
        """Image prompt positions use the tag-stripped coordinate system."""

        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        # Voice tag before image tag — image position must account for stripped voice tag
        prose = "**voice:narrator** Before **image:lighthouse** after"
        state.add_scene(1, "Test Scene", prose)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        header = StoryHeader(
            voices={"narrator": "alloy"},
            images={"lighthouse": "A tall lighthouse at dawn"},
        )

        _populate_image_tags(state, header)

        scene = state.metadata.scenes[0]
        # Stripped text: "Before after" — image tag at position 7 ("Before ")
        assert scene.image_prompts[0].position == 7

    def test_skips_scenes_with_existing_prompts(self, tmp_path):
        """Scenes that already have image_prompts are not modified."""
        config = AppConfig()
        state = ProjectState.create("tag-test", InputMode.ADAPT, config, tmp_path)
        prose = "The lighthouse stood tall. **image:lighthouse** The harbor."
        state.add_scene(1, "Test Scene", prose)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        # Pre-populate image_prompts
        existing_prompt = SceneImagePrompt(
            key="lighthouse",
            prompt="Existing prompt",
            position=0,
        )
        state.metadata.scenes[0].image_prompts = [existing_prompt]

        header = StoryHeader(
            voices={"narrator": "alloy"},
            images={"lighthouse": "New prompt from YAML"},
        )

        _populate_image_tags(state, header)

        scene = state.metadata.scenes[0]
        assert len(scene.image_prompts) == 1
        assert scene.image_prompts[0].prompt == "Existing prompt"


# ---------------------------------------------------------------------------
# TestPopulateMusicTags — music tag extraction and audio_cues population
# ---------------------------------------------------------------------------


class TestPopulateMusicTags:
    """_populate_music_tags extracts music tags and populates audio_cues."""

    def test_extracts_music_tags(self, tmp_path):
        """Scenes with music tags get audio_cues populated."""
        state = _make_adapt_state(tmp_path)
        state.metadata.scenes = [
            Scene(
                scene_number=1,
                title="Test",
                prose="Rain fell. **music:rain** Thunder. **music:thunder** End.",
            )
        ]
        header = StoryHeader(
            voices={"narrator": "nova"},
            audio={
                "rain": AudioAsset(file="rain.mp3"),
                "thunder": AudioAsset(file="thunder.mp3"),
            },
        )
        _populate_music_tags(state, header)
        assert len(state.metadata.scenes[0].audio_cues) == 2
        assert state.metadata.scenes[0].audio_cues[0].key == "rain"
        assert state.metadata.scenes[0].audio_cues[1].key == "thunder"

    def test_strips_music_tags_from_narration_text(self, tmp_path):
        """Music tags are stripped from narration_text."""
        state = _make_adapt_state(tmp_path)
        state.metadata.scenes = [
            Scene(
                scene_number=1,
                title="Test",
                prose="Hello **music:rain** world.",
            )
        ]
        header = StoryHeader(
            voices={"narrator": "nova"},
            audio={"rain": AudioAsset(file="rain.mp3")},
        )
        _populate_music_tags(state, header)
        assert "**music:" not in (state.metadata.scenes[0].narration_text or "")

    def test_no_tags_leaves_scene_unchanged(self, tmp_path):
        state = _make_adapt_state(tmp_path)
        state.metadata.scenes = [Scene(scene_number=1, title="Test", prose="No tags here.")]
        header = StoryHeader(voices={"narrator": "nova"})
        _populate_music_tags(state, header)
        assert state.metadata.scenes[0].audio_cues == []

    def test_unknown_key_raises(self, tmp_path):
        state = _make_adapt_state(tmp_path)
        state.metadata.scenes = [
            Scene(
                scene_number=1,
                title="Test",
                prose="Hello **music:unknown** world.",
            )
        ]
        header = StoryHeader(
            voices={"narrator": "nova"},
            audio={"rain": AudioAsset(file="rain.mp3")},
        )
        with pytest.raises(ValueError, match="unknown"):
            _populate_music_tags(state, header)

    def test_tags_but_no_audio_map_raises(self, tmp_path):
        state = _make_adapt_state(tmp_path)
        state.metadata.scenes = [
            Scene(
                scene_number=1,
                title="Test",
                prose="Hello **music:rain** world.",
            )
        ]
        header = StoryHeader(voices={"narrator": "nova"})
        with pytest.raises(ValueError, match="no audio"):
            _populate_music_tags(state, header)

    def test_skips_scenes_with_existing_cues(self, tmp_path):
        """Scenes that already have audio_cues are skipped (resume support)."""
        cue = SceneAudioCue(key="rain", position=0, start_time=1.0)
        state = _make_adapt_state(tmp_path)
        state.metadata.scenes = [
            Scene(
                scene_number=1,
                title="Test",
                prose="Hello **music:rain** world.",
                audio_cues=[cue],
            )
        ]
        header = StoryHeader(
            voices={"narrator": "nova"},
            audio={"rain": AudioAsset(file="rain.mp3")},
        )
        _populate_music_tags(state, header)
        # Should not have re-processed — still has the original cue
        assert state.metadata.scenes[0].audio_cues[0].start_time == 1.0
