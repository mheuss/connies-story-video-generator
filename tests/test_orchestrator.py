"""Tests for story_video.pipeline.orchestrator — pipeline orchestration.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the orchestrator module.
All pipeline module functions are mocked — no real API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from story_video.models import (
    AppConfig,
    AssetType,
    InputMode,
    PhaseStatus,
    PipelineConfig,
    PipelinePhase,
    SceneStatus,
)
from story_video.pipeline.orchestrator import (
    _CHECKPOINT_PHASES,
    _determine_start_phase,
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
        """State with current_phase=None -> first phase (SCENE_SPLITTING)."""
        phases = adapt_state.get_phase_sequence()
        result = _determine_start_phase(adapt_state, phases)

        assert result == PipelinePhase.SCENE_SPLITTING

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
    def test_pauses_after_image_prompts(self, mock_prompts, tmp_path):
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
                PipelinePhase.SCENE_SPLITTING,
                PipelinePhase.NARRATION_FLAGGING,
                PipelinePhase.IMAGE_PROMPTS,
            }
        )


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
    @patch("story_video.pipeline.orchestrator.prepare_narration", return_value="prepped text")
    @patch("story_video.pipeline.orchestrator.generate_image_prompts")
    @patch("story_video.pipeline.orchestrator.flag_narration")
    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_runs_all_phases_without_pausing(
        self,
        mock_split,
        mock_flag,
        mock_prompts,
        mock_prep,
        mock_audio,
        mock_img,
        mock_captions,
        mock_assemble_scene,
        mock_assemble_video,
        tmp_path,
    ):
        """Autonomous mode runs all 8 phases without pausing."""
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
        mock_split.assert_called_once()
        mock_flag.assert_called_once()
        mock_prompts.assert_called_once()
        # assemble_video called once at end
        mock_assemble_video.assert_called_once()


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

        with pytest.raises(RuntimeError, match="Claude API down"):
            run_pipeline(state, claude_client=MagicMock())

        assert state.metadata.current_phase == PipelinePhase.SCENE_SPLITTING
        assert state.metadata.status == PhaseStatus.FAILED

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_state_saved_on_failure(self, mock_split, tmp_path):
        """State persisted to disk after failure — reload confirms FAILED."""
        mock_split.side_effect = RuntimeError("boom")
        state = _make_adapt_state(tmp_path, autonomous=True)

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
    """NARRATION_PREP phase applies prepare_narration to all scenes."""

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch("story_video.pipeline.orchestrator.prepare_narration")
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
        """NARRATION_PREP applies prepare_narration to every scene's prose."""
        mock_prep.return_value = "transformed text"

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
    @patch("story_video.pipeline.orchestrator.prepare_narration")
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
        """When narration_text is None, prepare_narration uses prose instead."""
        mock_prep.return_value = "from prose"

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

        # prepare_narration called with the prose since narration_text was None
        mock_prep.assert_called_with(scene.prose)
        assert scene.narration_text == "from prose"

    @patch("story_video.pipeline.orchestrator.assemble_video")
    @patch("story_video.pipeline.orchestrator.assemble_scene")
    @patch("story_video.pipeline.orchestrator.generate_captions")
    @patch("story_video.pipeline.orchestrator.generate_image")
    @patch("story_video.pipeline.orchestrator.generate_audio")
    @patch("story_video.pipeline.orchestrator.prepare_narration")
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
        mock_prep.return_value = "prepped"

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


# ---------------------------------------------------------------------------
# TestRunPipelineDispatch — phase dispatch routing
# ---------------------------------------------------------------------------


class TestRunPipelineDispatch:
    """run_pipeline() dispatches to the correct pipeline module per phase."""

    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_scene_splitting_calls_split_scenes(self, mock_split, tmp_path):
        """SCENE_SPLITTING dispatches to split_scenes(state, client)."""
        state = _make_adapt_state(tmp_path, autonomous=False)
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
    def test_image_prompts_calls_generate_image_prompts(self, mock_prompts, tmp_path):
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
    @patch("story_video.pipeline.orchestrator.prepare_narration", return_value="prepped")
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

        run_pipeline(state, claude_client=MagicMock())

        # Verify by reloading from disk
        reloaded = ProjectState.load(state.project_dir)
        assert reloaded.metadata.status == PhaseStatus.AWAITING_REVIEW
