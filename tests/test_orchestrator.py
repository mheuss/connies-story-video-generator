"""Tests for story_video.pipeline.orchestrator — pipeline orchestration.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the orchestrator module.
All pipeline module functions are mocked — no real API calls.
"""

import logging
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
    StoryHeader,
)
from story_video.pipeline.orchestrator import (
    _CHECKPOINT_PHASES,
    _determine_start_phase,
    _dispatch_phase,
    _parse_source_header,
    _run_narration_prep,
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
                PipelinePhase.ANALYSIS,
                PipelinePhase.STORY_BIBLE,
                PipelinePhase.OUTLINE,
                PipelinePhase.SCENE_PROSE,
                PipelinePhase.CRITIQUE_REVISION,
                PipelinePhase.SCENE_SPLITTING,
                PipelinePhase.NARRATION_FLAGGING,
                PipelinePhase.IMAGE_PROMPTS,
                PipelinePhase.NARRATION_PREP,
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
        import json

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
        import json

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

        run_pipeline(state, claude_client=MagicMock())

        # Verify by reloading from disk
        reloaded = ProjectState.load(state.project_dir)
        assert reloaded.metadata.status == PhaseStatus.AWAITING_REVIEW


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
# TestRunPipelineAutonomousCompleted — final status verification
# ---------------------------------------------------------------------------


class TestRunPipelineAutonomousCompleted:
    """Autonomous pipeline ends with COMPLETED status."""

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
    @patch("story_video.pipeline.orchestrator.generate_image_prompts")
    @patch("story_video.pipeline.orchestrator.flag_narration")
    @patch("story_video.pipeline.orchestrator.split_scenes")
    def test_autonomous_ends_with_completed_status(
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
        """Autonomous mode completes all 8 phases — final status is COMPLETED."""
        state = _make_adapt_state(tmp_path, autonomous=True)
        _add_scenes_with_assets(state, count=2, up_to_asset=AssetType.TEXT)

        run_pipeline(
            state,
            claude_client=MagicMock(),
            tts_provider=MagicMock(),
            image_provider=MagicMock(),
            caption_provider=MagicMock(),
        )

        assert state.metadata.current_phase == PipelinePhase.VIDEO_ASSEMBLY
        assert state.metadata.status == PhaseStatus.COMPLETED


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

    def test_scene_splitting_requires_claude_client(self, adapt_state):
        with pytest.raises(ValueError, match="claude_client"):
            _dispatch_phase(
                PipelinePhase.SCENE_SPLITTING,
                adapt_state,
                claude_client=None,
                tts_provider=MagicMock(),
                image_provider=MagicMock(),
                caption_provider=MagicMock(),
            )

    def test_narration_flagging_requires_claude_client(self, adapt_state):
        with pytest.raises(ValueError, match="claude_client"):
            _dispatch_phase(
                PipelinePhase.NARRATION_FLAGGING,
                adapt_state,
                claude_client=None,
                tts_provider=MagicMock(),
                image_provider=MagicMock(),
                caption_provider=MagicMock(),
            )

    def test_image_prompts_requires_claude_client(self, adapt_state):
        with pytest.raises(ValueError, match="claude_client"):
            _dispatch_phase(
                PipelinePhase.IMAGE_PROMPTS,
                adapt_state,
                claude_client=None,
                tts_provider=MagicMock(),
                image_provider=MagicMock(),
                caption_provider=MagicMock(),
            )

    def test_tts_generation_requires_tts_provider(self, adapt_state):
        with pytest.raises(ValueError, match="tts_provider"):
            _dispatch_phase(
                PipelinePhase.TTS_GENERATION,
                adapt_state,
                claude_client=MagicMock(),
                tts_provider=None,
                image_provider=MagicMock(),
                caption_provider=MagicMock(),
            )

    def test_image_generation_requires_image_provider(self, adapt_state):
        with pytest.raises(ValueError, match="image_provider"):
            _dispatch_phase(
                PipelinePhase.IMAGE_GENERATION,
                adapt_state,
                claude_client=MagicMock(),
                tts_provider=MagicMock(),
                image_provider=None,
                caption_provider=MagicMock(),
            )

    def test_caption_generation_requires_caption_provider(self, adapt_state):
        with pytest.raises(ValueError, match="caption_provider"):
            _dispatch_phase(
                PipelinePhase.CAPTION_GENERATION,
                adapt_state,
                claude_client=MagicMock(),
                tts_provider=MagicMock(),
                image_provider=MagicMock(),
                caption_provider=None,
            )

    def test_narration_prep_requires_claude_client(self, adapt_state):
        with pytest.raises(ValueError, match="claude_client is required for NARRATION_PREP"):
            _dispatch_phase(
                PipelinePhase.NARRATION_PREP,
                adapt_state,
                claude_client=None,
                tts_provider=MagicMock(),
                image_provider=MagicMock(),
                caption_provider=MagicMock(),
            )


# ---------------------------------------------------------------------------
# TestDispatchCreativePhases — creative phase dispatch routing
# ---------------------------------------------------------------------------


class TestDispatchCreativePhases:
    """_dispatch_phase routes creative phases to story_writer functions."""

    def test_dispatches_analysis(self, mocker):
        """ANALYSIS phase calls story_writer.analyze_source."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.analyze_source")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.ANALYSIS,
            state,
            claude_client=client,
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_story_bible(self, mocker):
        """STORY_BIBLE phase calls story_writer.create_story_bible."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.create_story_bible")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.STORY_BIBLE,
            state,
            claude_client=client,
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_outline(self, mocker):
        """OUTLINE phase calls story_writer.create_outline."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.create_outline")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.OUTLINE,
            state,
            claude_client=client,
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_scene_prose(self, mocker):
        """SCENE_PROSE phase calls story_writer.write_scene_prose."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.write_scene_prose")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.SCENE_PROSE,
            state,
            claude_client=client,
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_critique_revision(self, mocker):
        """CRITIQUE_REVISION phase calls story_writer.critique_and_revise."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.critique_and_revise")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.CRITIQUE_REVISION,
            state,
            claude_client=client,
            tts_provider=None,
            image_provider=None,
            caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    @pytest.mark.parametrize(
        "phase",
        [
            PipelinePhase.ANALYSIS,
            PipelinePhase.STORY_BIBLE,
            PipelinePhase.OUTLINE,
            PipelinePhase.SCENE_PROSE,
            PipelinePhase.CRITIQUE_REVISION,
        ],
    )
    def test_creative_phases_require_claude_client(self, phase):
        """Each creative phase raises ValueError when claude_client is None."""
        state = MagicMock()
        with pytest.raises(ValueError, match="claude_client is required"):
            _dispatch_phase(
                phase,
                state,
                claude_client=None,
                tts_provider=None,
                image_provider=None,
                caption_provider=None,
            )


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
        import subprocess as _subprocess

        from story_video.models import CaptionResult, CaptionSegment, CaptionWord

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
            "split_into_scenes": {
                "scenes": [
                    {"title": "The Storm", "text": scene1_text},
                    {"title": "The Dawn", "text": scene2_text},
                ],
            },
            "flag_narration_issues": {"flags": []},
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

        def _claude_dispatch_with_narration(**kwargs):
            """Route mock Claude calls, echoing narration text back for tts_text_prep."""
            tool_name = kwargs.get("tool_name", "")
            if tool_name == "tts_text_prep":
                # Echo the input narration text back as modified_text (no changes)
                user_msg = kwargs.get("user_message", "")
                # The narration text is the last block after the blank line
                lines = user_msg.split("\n")
                # Find the text after "Narration text to prepare for TTS:" header
                text_start = None
                for i, line in enumerate(lines):
                    if line.startswith("Narration text to prepare for TTS:"):
                        text_start = i + 2  # skip header + blank line
                        break
                narration_text = "\n".join(lines[text_start:]) if text_start else ""
                return {
                    "modified_text": narration_text,
                    "changes": [],
                    "pronunciation_guide_additions": [],
                }
            return claude_responses[tool_name]

        mock_claude = MagicMock()
        mock_claude.generate_structured = MagicMock(side_effect=_claude_dispatch_with_narration)

        # --- Mock TTS provider ---
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=b"\xff" * 100)

        # --- Mock image provider ---
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_image = MagicMock()
        mock_image.generate = MagicMock(return_value=fake_png)

        # --- Mock caption provider ---
        def _make_caption_result(text):
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
        real_subprocess_run = _subprocess.run

        def _mock_subprocess_run(cmd, **kwargs):
            cmd_str = cmd[0] if cmd else ""

            if "ffprobe" in cmd_str:
                return _subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="5.0\n", stderr=""
                )

            if "ffmpeg" in cmd_str:
                from pathlib import Path

                output_path = Path(cmd[-1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"\x00" * 50)
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

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

        assert "lighthouse" in scene1.prose.lower()
        assert "dawn" in scene2.prose.lower()
        assert scene1.narration_text is not None
        assert scene2.narration_text is not None
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
        assert (pd / "scenes" / "scene_001.md").exists()
        assert (pd / "scenes" / "scene_002.md").exists()
        assert (pd / "audio" / "scene_001.mp3").exists()
        assert (pd / "audio" / "scene_002.mp3").exists()
        assert (pd / "images" / "scene_001.png").exists()
        assert (pd / "images" / "scene_002.png").exists()
        assert (pd / "captions" / "scene_001.json").exists()
        assert (pd / "captions" / "scene_002.json").exists()
        assert (pd / "captions" / "scene_001.ass").exists()
        assert (pd / "captions" / "scene_002.ass").exists()
        assert (pd / "segments" / "scene_001.mp4").exists()
        assert (pd / "segments" / "scene_002.mp4").exists()
        assert (pd / "final.mp4").exists()

        # --- Verify external APIs were called ---
        # 3 original calls (split + flag + prompts) + 2 narration prep (one per scene)
        assert mock_claude.generate_structured.call_count == 5
        assert mock_tts.synthesize.call_count == 2
        assert mock_image.generate.call_count == 2
        assert mock_caption.transcribe.call_count == 2

        # --- Verify state was persisted to disk ---
        reloaded = ProjectState.load(pd)
        assert reloaded.metadata.status == PhaseStatus.COMPLETED
        assert len(reloaded.metadata.scenes) == 2

    def test_full_creative_flow_data_flow(self, tmp_path, monkeypatch):
        """Full creative flow (inspired_by) creates expected files and state transitions."""
        import subprocess as _subprocess

        from story_video.models import CaptionResult, CaptionSegment, CaptionWord

        scene1_prose = "The old woman sat alone in the empty theater, listening to silence."
        scene2_prose = "She rose from her seat and walked toward the stage, footsteps echoing."

        # --- Mock Claude client ---
        def _claude_dispatch(**kwargs):
            tool_name = kwargs.get("tool_name", "")
            if tool_name == "analyze_source":
                return {
                    "craft_notes": {"style": "literary fiction", "tone": "melancholic"},
                    "thematic_brief": {"themes": ["solitude", "memory"]},
                    "source_stats": {"word_count": 200, "scene_count_estimate": 2},
                }
            if tool_name == "create_story_bible":
                return {
                    "characters": [{"name": "The Old Woman", "role": "protagonist"}],
                    "setting": "An abandoned theater",
                    "world_rules": [],
                }
            if tool_name == "create_outline":
                return {
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
                }
            if tool_name == "write_scene":
                user_msg = kwargs.get("user_message", "")
                if "## Current Scene: The Silence" in user_msg:
                    return {"prose": scene1_prose, "summary": "Old woman sits in theater."}
                return {"prose": scene2_prose, "summary": "She walks to the stage."}
            if tool_name == "critique_scene":
                user_msg = kwargs.get("user_message", "")
                # Return prose unchanged (no revisions needed)
                if "theater" in user_msg and "listening" in user_msg:
                    return {"revised_prose": scene1_prose, "changes": []}
                return {"revised_prose": scene2_prose, "changes": []}
            if tool_name == "generate_image_prompts":
                return {
                    "prompts": [
                        {"scene_number": 1, "image_prompt": "Empty theater with one person."},
                        {"scene_number": 2, "image_prompt": "Woman walking toward lit stage."},
                    ]
                }
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
            msg = f"Unexpected tool_name: {tool_name}"
            raise ValueError(msg)

        mock_claude = MagicMock()
        mock_claude.generate_structured = MagicMock(side_effect=_claude_dispatch)

        # --- Mock TTS provider ---
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=b"\xff" * 100)

        # --- Mock image provider ---
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_image = MagicMock()
        mock_image.generate = MagicMock(return_value=fake_png)

        # --- Mock caption provider ---
        def _make_caption_result(text):
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
        real_subprocess_run = _subprocess.run

        def _mock_subprocess_run(cmd, **kwargs):
            cmd_str = cmd[0] if cmd else ""
            if "ffprobe" in cmd_str:
                return _subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="5.0\n", stderr=""
                )
            if "ffmpeg" in cmd_str:
                from pathlib import Path as P

                output_path = P(cmd[-1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"\x00" * 50)
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return real_subprocess_run(cmd, **kwargs)

        monkeypatch.setattr("subprocess.run", _mock_subprocess_run)

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
        assert (pd / "images" / "scene_001.png").exists()
        assert (pd / "images" / "scene_002.png").exists()
        assert (pd / "final.mp4").exists()

        # --- Verify external APIs were called ---
        # analyze + bible + outline + 2 prose + 2 critique + prompts + 2 narration prep = 10
        assert mock_claude.generate_structured.call_count == 10
        assert mock_tts.synthesize.call_count == 2
        assert mock_image.generate.call_count == 2
        assert mock_caption.transcribe.call_count == 2

        # --- Verify state was persisted to disk ---
        reloaded = ProjectState.load(pd)
        assert reloaded.metadata.status == PhaseStatus.COMPLETED
        assert len(reloaded.metadata.scenes) == 2
