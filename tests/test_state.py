"""Tests for story_video.state — Project state management.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the ProjectState class.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from story_video.models import (
    ADAPT_FLOW_PHASES,
    CREATIVE_FLOW_PHASES,
    AppConfig,
    AssetType,
    InputMode,
    PhaseStatus,
    PipelinePhase,
    ProjectMetadata,
    SceneStatus,
)
from story_video.state import (
    ASSET_DEPENDENCIES,
    PHASE_ASSET_MAP,
    ProjectState,
    generate_project_id,
    scan_project_dirs,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """A temporary output directory for project creation."""
    return tmp_path / "output"


@pytest.fixture()
def config() -> AppConfig:
    """Default application config."""
    return AppConfig()


@pytest.fixture()
def project_state(output_dir: Path, config: AppConfig) -> ProjectState:
    """A freshly created project state for the 'original' mode."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return ProjectState.create(
        project_id="test-project",
        mode=InputMode.ORIGINAL,
        config=config,
        output_dir=output_dir,
    )


@pytest.fixture()
def adapt_project_state(output_dir: Path, config: AppConfig) -> ProjectState:
    """A freshly created project state for the 'adapt' mode."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return ProjectState.create(
        project_id="adapt-project",
        mode=InputMode.ADAPT,
        config=config,
        output_dir=output_dir,
    )


@pytest.fixture()
def project_with_scenes(project_state: ProjectState) -> ProjectState:
    """A project state with two scenes added."""
    project_state.add_scene(1, "The Beginning", "Once upon a time...")
    project_state.add_scene(2, "The Middle", "And then things happened...")
    return project_state


# ---------------------------------------------------------------------------
# Mapping constant tests
# ---------------------------------------------------------------------------


class TestPhaseAssetMap:
    """PHASE_ASSET_MAP — maps pipeline phases to the asset type they produce."""

    def test_full_mapping(self):
        """Every phase maps to the correct asset type (or None)."""
        expected = {
            PipelinePhase.ANALYSIS: None,
            PipelinePhase.STORY_BIBLE: None,
            PipelinePhase.OUTLINE: None,
            PipelinePhase.SCENE_PROSE: AssetType.TEXT,
            PipelinePhase.CRITIQUE_REVISION: AssetType.TEXT,
            PipelinePhase.SCENE_SPLITTING: AssetType.TEXT,
            PipelinePhase.NARRATION_FLAGGING: AssetType.NARRATION_TEXT,
            PipelinePhase.IMAGE_PROMPTS: AssetType.IMAGE_PROMPT,
            PipelinePhase.NARRATION_PREP: AssetType.NARRATION_TEXT,
            PipelinePhase.TTS_GENERATION: AssetType.AUDIO,
            PipelinePhase.IMAGE_GENERATION: AssetType.IMAGE,
            PipelinePhase.CAPTION_GENERATION: AssetType.CAPTIONS,
            PipelinePhase.VIDEO_ASSEMBLY: AssetType.VIDEO_SEGMENT,
        }
        assert PHASE_ASSET_MAP == expected


class TestAssetDependencies:
    """ASSET_DEPENDENCIES — downstream dependency rules for assets."""

    def test_full_dependency_map(self):
        """Every asset type maps to the correct dependencies."""
        assert set(ASSET_DEPENDENCIES.keys()) == set(AssetType)
        assert ASSET_DEPENDENCIES[AssetType.TEXT] == []
        assert ASSET_DEPENDENCIES[AssetType.NARRATION_TEXT] == [AssetType.TEXT]
        assert ASSET_DEPENDENCIES[AssetType.AUDIO] == [AssetType.NARRATION_TEXT]
        assert ASSET_DEPENDENCIES[AssetType.IMAGE_PROMPT] == [AssetType.TEXT]
        assert ASSET_DEPENDENCIES[AssetType.IMAGE] == [AssetType.IMAGE_PROMPT]
        assert ASSET_DEPENDENCIES[AssetType.CAPTIONS] == [AssetType.AUDIO]
        video_deps = set(ASSET_DEPENDENCIES[AssetType.VIDEO_SEGMENT])
        assert video_deps == {AssetType.AUDIO, AssetType.IMAGE, AssetType.CAPTIONS}


# ---------------------------------------------------------------------------
# ProjectState.create() unit tests
# ---------------------------------------------------------------------------


class TestProjectStateCreate:
    """ProjectState.create() — creates a new project with initial state."""

    def test_creates_project_with_correct_initial_state(self, output_dir, config):
        """Project dir is under output_dir; metadata has correct defaults."""
        output_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState.create("my-project", InputMode.ORIGINAL, config, output_dir)
        assert state.project_dir == output_dir / "my-project"

        m = state.metadata
        assert m.project_id == "my-project"
        assert m.mode == InputMode.ORIGINAL
        assert m.status == PhaseStatus.PENDING
        assert m.current_phase is None
        assert m.scenes == []
        assert m.config == config

    def test_raises_if_project_dir_already_exists(self, output_dir, config):
        output_dir.mkdir(parents=True, exist_ok=True)
        ProjectState.create("dup-project", InputMode.ORIGINAL, config, output_dir)
        with pytest.raises(FileExistsError):
            ProjectState.create("dup-project", InputMode.ORIGINAL, config, output_dir)

    def test_stores_all_input_modes(self, adapt_project_state, output_dir, config):
        """Both adapt and inspired_by modes are stored correctly."""
        assert adapt_project_state.metadata.mode == InputMode.ADAPT

        output_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState.create("inspired", InputMode.INSPIRED_BY, config, output_dir)
        assert state.metadata.mode == InputMode.INSPIRED_BY


# ---------------------------------------------------------------------------
# ProjectState.create() integration tests (disk I/O)
# ---------------------------------------------------------------------------


class TestProjectStateCreateDiskIO:
    """ProjectState.create() writes project.json and creates directories."""

    def test_creates_structure_with_valid_json(self, project_state):
        """Creates directories, subdirs, and valid project.json."""
        assert project_state.project_dir.is_dir()
        assert (project_state.project_dir / "project.json").is_file()
        for subdir in ("scenes", "audio", "images", "captions", "video", "segments"):
            assert (project_state.project_dir / subdir).is_dir(), f"Missing {subdir}/"

        json_path = project_state.project_dir / "project.json"
        content = json_path.read_text(encoding="utf-8")
        loaded = ProjectMetadata.model_validate_json(content)
        assert loaded.project_id == "test-project"
        assert loaded.mode == InputMode.ORIGINAL


# ---------------------------------------------------------------------------
# ProjectState.load() unit tests
# ---------------------------------------------------------------------------


class TestProjectStateLoad:
    """ProjectState.load() — loads an existing project from disk."""

    def test_returns_project_state_instance(self, project_state):
        loaded = ProjectState.load(project_state.project_dir)
        assert isinstance(loaded, ProjectState)

    def test_loaded_state_matches_original(self, project_state):
        """Loaded project preserves project_id, mode, and status."""
        loaded = ProjectState.load(project_state.project_dir)
        assert loaded.metadata.project_id == "test-project"
        assert loaded.metadata.mode == InputMode.ORIGINAL
        assert loaded.metadata.status == PhaseStatus.PENDING

    def test_raises_if_project_json_missing(self, tmp_path):
        empty_dir = tmp_path / "no-project"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            ProjectState.load(empty_dir)

    def test_raises_if_project_json_invalid(self, tmp_path):
        bad_dir = tmp_path / "bad-project"
        bad_dir.mkdir()
        (bad_dir / "project.json").write_text("not valid json")
        with pytest.raises(ValueError):
            ProjectState.load(bad_dir)


# ---------------------------------------------------------------------------
# ProjectState.save() unit tests
# ---------------------------------------------------------------------------


class TestProjectStateSave:
    """ProjectState.save() — persists current state to project.json."""

    def test_save_persists_phase_change(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.save()
        loaded = ProjectState.load(project_state.project_dir)
        assert loaded.metadata.current_phase == PipelinePhase.ANALYSIS
        assert loaded.metadata.status == PhaseStatus.IN_PROGRESS

    def test_save_persists_added_scenes(self, project_state):
        project_state.add_scene(1, "Scene One", "The first scene text.")
        project_state.save()
        loaded = ProjectState.load(project_state.project_dir)
        assert len(loaded.metadata.scenes) == 1
        assert loaded.metadata.scenes[0].title == "Scene One"

    def test_save_persists_scene_asset_status(self, project_with_scenes):
        project_with_scenes.start_phase(PipelinePhase.SCENE_PROSE)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        project_with_scenes.save()
        loaded = ProjectState.load(project_with_scenes.project_dir)
        scene = next(s for s in loaded.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.text == SceneStatus.COMPLETED

    def test_save_is_atomic_writes_temp_then_renames(self, project_state):
        """Save writes to a temp file and renames, so a crash during write
        won't corrupt the existing project.json."""
        # Verify initial file exists
        json_path = project_state.project_dir / "project.json"
        original_content = json_path.read_text(encoding="utf-8")
        # Modify and save
        project_state.add_scene(1, "Test", "Test prose content.")
        project_state.save()
        # Verify file was updated (content changed)
        new_content = json_path.read_text(encoding="utf-8")
        assert new_content != original_content
        # Verify no temp files left behind
        temp_files = list(project_state.project_dir.glob("project.json.*"))
        assert temp_files == []


# ---------------------------------------------------------------------------
# Phase transitions — start, complete, fail, await_review
# ---------------------------------------------------------------------------


class TestPhaseTransitions:
    """Phase transition methods — start, complete, fail, await_review."""

    def test_start_phase_sets_phase_and_status(self, project_state):
        """start_phase sets current_phase and status to IN_PROGRESS."""
        project_state.start_phase(PipelinePhase.ANALYSIS)
        assert project_state.metadata.current_phase == PipelinePhase.ANALYSIS
        assert project_state.metadata.status == PhaseStatus.IN_PROGRESS

    def test_complete_phase_sets_status_to_completed(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.complete_phase()
        assert project_state.metadata.status == PhaseStatus.COMPLETED

    def test_fail_phase_sets_status_to_failed(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.fail_phase()
        assert project_state.metadata.status == PhaseStatus.FAILED

    def test_await_review_sets_status_to_awaiting_review(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.await_review()
        assert project_state.metadata.status == PhaseStatus.AWAITING_REVIEW

    @pytest.mark.parametrize("method", ["complete_phase", "fail_phase", "await_review"])
    def test_raises_if_no_phase_in_progress(self, project_state, method):
        with pytest.raises(ValueError, match="[Nn]o phase"):
            getattr(project_state, method)()

    def test_start_phase_rejects_invalid_phase_for_adapt_mode(self, adapt_project_state):
        """Adapt mode does not have a STORY_BIBLE phase."""
        with pytest.raises(ValueError, match="not valid"):
            adapt_project_state.start_phase(PipelinePhase.STORY_BIBLE)

    def test_start_phase_rejects_invalid_phase_for_creative_mode(self, project_state):
        """Creative mode does not have SCENE_SPLITTING."""
        with pytest.raises(ValueError, match="not valid"):
            project_state.start_phase(PipelinePhase.SCENE_SPLITTING)

    def test_start_phase_allows_valid_phase_for_adapt_mode(self, adapt_project_state):
        adapt_project_state.start_phase(PipelinePhase.SCENE_SPLITTING)
        assert adapt_project_state.metadata.current_phase == PipelinePhase.SCENE_SPLITTING

    def test_start_phase_allows_shared_phase_for_both_modes(
        self, project_state, adapt_project_state
    ):
        project_state.start_phase(PipelinePhase.IMAGE_PROMPTS)
        assert project_state.metadata.current_phase == PipelinePhase.IMAGE_PROMPTS
        adapt_project_state.start_phase(PipelinePhase.IMAGE_PROMPTS)
        assert adapt_project_state.metadata.current_phase == PipelinePhase.IMAGE_PROMPTS

    def test_start_phase_after_fail_allows_retry(self, adapt_project_state):
        """A failed phase can be restarted (retry scenario)."""
        adapt_project_state.start_phase(PipelinePhase.SCENE_SPLITTING)
        adapt_project_state.fail_phase()
        adapt_project_state.start_phase(PipelinePhase.SCENE_SPLITTING)
        assert adapt_project_state.metadata.status == PhaseStatus.IN_PROGRESS

    def test_rejects_start_phase_while_in_progress(self, project_state):
        """Cannot start a new phase while another is still in progress."""
        project_state.start_phase(PipelinePhase.ANALYSIS)
        with pytest.raises(ValueError, match="still in progress"):
            project_state.start_phase(PipelinePhase.STORY_BIBLE)

    def test_start_phase_auto_completes_awaiting_review(self, project_state):
        """Starting a new phase after AWAITING_REVIEW auto-completes the previous one."""
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.await_review()
        assert project_state.metadata.status == PhaseStatus.AWAITING_REVIEW

        project_state.start_phase(PipelinePhase.STORY_BIBLE)
        assert project_state.metadata.current_phase == PipelinePhase.STORY_BIBLE
        assert project_state.metadata.status == PhaseStatus.IN_PROGRESS

    def test_complete_then_start_next_phase(self, project_state):
        """After completing a phase, we can start the next one."""
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.complete_phase()
        project_state.start_phase(PipelinePhase.STORY_BIBLE)
        assert project_state.metadata.current_phase == PipelinePhase.STORY_BIBLE
        assert project_state.metadata.status == PhaseStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# add_scene
# ---------------------------------------------------------------------------


class TestAddScene:
    """ProjectState.add_scene() — adds scenes to the project."""

    def test_adds_scene_with_correct_fields(self, project_state):
        """Added scene has correct fields, pending status, and summary defaults to None."""
        project_state.add_scene(1, "Opening", "The story begins...")
        scene = project_state.metadata.scenes[0]
        assert scene.scene_number == 1
        assert scene.title == "Opening"
        assert scene.prose == "The story begins..."
        assert scene.asset_status.text == SceneStatus.PENDING
        assert scene.summary is None

    def test_add_multiple_scenes(self, project_state):
        project_state.add_scene(1, "First", "First scene.")
        project_state.add_scene(2, "Second", "Second scene.")
        project_state.add_scene(3, "Third", "Third scene.")
        assert len(project_state.metadata.scenes) == 3

    def test_rejects_duplicate_scene_number(self, project_state):
        project_state.add_scene(1, "Scene One", "First prose.")
        with pytest.raises(ValueError, match="Scene 1 already exists"):
            project_state.add_scene(1, "Scene One Again", "Different prose.")

    def test_summary_stored_when_provided(self, project_state):
        project_state.add_scene(1, "Opening", "The story begins.", summary="Hero arrives.")
        scene = project_state.metadata.scenes[0]
        assert scene.summary == "Hero arrives."


# ---------------------------------------------------------------------------
# update_scene_asset — status updates and dependency enforcement
# ---------------------------------------------------------------------------


class TestUpdateSceneAsset:
    """ProjectState.update_scene_asset() — updates asset status with rules."""

    def test_updates_text_to_in_progress(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        scene = next(s for s in project_with_scenes.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.text == SceneStatus.IN_PROGRESS

    def test_updates_text_to_completed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        scene = next(s for s in project_with_scenes.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.text == SceneStatus.COMPLETED

    def test_updates_text_to_failed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.FAILED)
        scene = next(s for s in project_with_scenes.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.text == SceneStatus.FAILED

    def test_raises_if_scene_not_found(self, project_with_scenes):
        with pytest.raises(ValueError, match="[Ss]cene.*99"):
            project_with_scenes.update_scene_asset(99, AssetType.TEXT, SceneStatus.IN_PROGRESS)

    @pytest.mark.parametrize(
        "target_status",
        [SceneStatus.IN_PROGRESS, SceneStatus.FAILED, SceneStatus.PENDING],
    )
    def test_never_overwrite_completed_asset(self, project_with_scenes, target_status):
        """A completed asset must never be overwritten — this is a critical rule."""
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        with pytest.raises(ValueError, match="[Cc]ompleted"):
            project_with_scenes.update_scene_asset(1, AssetType.TEXT, target_status)


class TestAssetDependencyEnforcement:
    """update_scene_asset enforces downstream dependency rules."""

    def test_narration_text_requires_text_completed(self, project_with_scenes):
        """Cannot start narration_text if text is not completed."""
        with pytest.raises(ValueError, match="[Dd]ependenc"):
            project_with_scenes.update_scene_asset(
                1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS
            )

    def test_narration_text_allowed_when_text_completed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        project_with_scenes.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        scene = next(s for s in project_with_scenes.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.narration_text == SceneStatus.IN_PROGRESS

    def test_audio_requires_narration_text_completed(self, project_with_scenes):
        """Cannot start audio if narration_text is not completed."""
        with pytest.raises(ValueError, match="[Dd]ependenc"):
            project_with_scenes.update_scene_asset(1, AssetType.AUDIO, SceneStatus.IN_PROGRESS)

    def test_audio_allowed_when_narration_text_completed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        project_with_scenes.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        project_with_scenes.update_scene_asset(1, AssetType.AUDIO, SceneStatus.IN_PROGRESS)
        scene = next(s for s in project_with_scenes.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.audio == SceneStatus.IN_PROGRESS

    def test_image_requires_image_prompt_completed(self, project_with_scenes):
        """Cannot start image if image_prompt is not completed."""
        with pytest.raises(ValueError, match="[Dd]ependenc"):
            project_with_scenes.update_scene_asset(1, AssetType.IMAGE, SceneStatus.IN_PROGRESS)

    def test_image_allowed_when_image_prompt_completed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        project_with_scenes.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)
        project_with_scenes.update_scene_asset(1, AssetType.IMAGE, SceneStatus.IN_PROGRESS)
        scene = next(s for s in project_with_scenes.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.image == SceneStatus.IN_PROGRESS

    def test_captions_requires_audio_completed(self, project_with_scenes):
        with pytest.raises(ValueError, match="[Dd]ependenc"):
            project_with_scenes.update_scene_asset(1, AssetType.CAPTIONS, SceneStatus.IN_PROGRESS)

    def test_video_segment_requires_all_three_dependencies(self, project_with_scenes):
        """video_segment requires audio, image, and captions all completed."""
        with pytest.raises(ValueError, match="[Dd]ependenc"):
            project_with_scenes.update_scene_asset(
                1, AssetType.VIDEO_SEGMENT, SceneStatus.IN_PROGRESS
            )

    def test_video_segment_allowed_when_all_deps_completed(self, project_with_scenes):
        """Full chain: text -> narration_text -> audio, text -> image_prompt -> image,
        audio -> captions. Then video_segment requires audio + image + captions."""
        ps = project_with_scenes
        # text
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        # narration_text
        ps.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        # audio
        ps.update_scene_asset(1, AssetType.AUDIO, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.AUDIO, SceneStatus.COMPLETED)
        # image_prompt
        ps.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.IMAGE_PROMPT, SceneStatus.COMPLETED)
        # image
        ps.update_scene_asset(1, AssetType.IMAGE, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.IMAGE, SceneStatus.COMPLETED)
        # captions
        ps.update_scene_asset(1, AssetType.CAPTIONS, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.CAPTIONS, SceneStatus.COMPLETED)
        # video_segment now allowed
        ps.update_scene_asset(1, AssetType.VIDEO_SEGMENT, SceneStatus.IN_PROGRESS)
        scene = next(s for s in ps.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.video_segment == SceneStatus.IN_PROGRESS

    def test_dependency_check_skipped_for_failed_transition(self, project_with_scenes):
        """Setting an asset to failed from in_progress should be allowed
        even if the asset's own dependencies might not seem right
        (the point is we tried and it failed)."""
        ps = project_with_scenes
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.FAILED)
        scene = next(s for s in ps.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.text == SceneStatus.FAILED

    def test_failed_asset_can_be_retried(self, project_with_scenes):
        """A failed asset can be set back to in_progress for retry."""
        ps = project_with_scenes
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.FAILED)
        ps.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        scene = next(s for s in ps.metadata.scenes if s.scene_number == 1)
        assert scene.asset_status.text == SceneStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# get_scenes_for_processing
# ---------------------------------------------------------------------------


class TestGetScenesForProcessing:
    """ProjectState.get_scenes_for_processing() — returns scenes needing work."""

    def test_returns_all_pending_scenes(self, project_with_scenes):
        """When starting scene_prose, all scenes with pending text are returned."""
        project_with_scenes.start_phase(PipelinePhase.SCENE_PROSE)
        scenes = project_with_scenes.get_scenes_for_processing()
        assert len(scenes) == 2

    def test_skips_completed_scenes(self, project_with_scenes):
        """Completed scenes are not returned for processing."""
        project_with_scenes.start_phase(PipelinePhase.SCENE_PROSE)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        scenes = project_with_scenes.get_scenes_for_processing()
        assert len(scenes) == 1
        assert scenes[0].scene_number == 2

    def test_includes_failed_scenes_for_retry(self, project_with_scenes):
        """Failed scenes are included so they can be retried."""
        project_with_scenes.start_phase(PipelinePhase.SCENE_PROSE)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.FAILED)
        scenes = project_with_scenes.get_scenes_for_processing()
        assert len(scenes) == 2
        scene_numbers = {s.scene_number for s in scenes}
        assert scene_numbers == {1, 2}

    def test_excludes_in_progress_scenes(self, project_with_scenes):
        """In-progress scenes are already being worked on."""
        project_with_scenes.start_phase(PipelinePhase.SCENE_PROSE)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        scenes = project_with_scenes.get_scenes_for_processing()
        assert len(scenes) == 1
        assert scenes[0].scene_number == 2

    def test_returns_empty_for_phase_with_no_asset(self, project_with_scenes):
        """Phases with no per-scene asset (e.g., ANALYSIS) return empty list."""
        project_with_scenes.start_phase(PipelinePhase.ANALYSIS)
        scenes = project_with_scenes.get_scenes_for_processing()
        assert scenes == []

    def test_returns_empty_when_all_completed(self, project_with_scenes):
        """When all scenes are completed for the phase asset, returns empty."""
        project_with_scenes.start_phase(PipelinePhase.SCENE_PROSE)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        project_with_scenes.update_scene_asset(2, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(2, AssetType.TEXT, SceneStatus.COMPLETED)
        scenes = project_with_scenes.get_scenes_for_processing()
        assert scenes == []

    def test_raises_if_no_phase_in_progress(self, project_with_scenes):
        """Must have a current phase to determine which asset to check."""
        with pytest.raises(ValueError, match="[Nn]o phase"):
            project_with_scenes.get_scenes_for_processing()


# ---------------------------------------------------------------------------
# Phase sequence helpers
# ---------------------------------------------------------------------------


class TestPhaseSequenceHelpers:
    """get_phase_sequence() and get_next_phase() helpers."""

    def test_original_mode_returns_creative_phases(self, project_state):
        phases = project_state.get_phase_sequence()
        assert phases == list(CREATIVE_FLOW_PHASES)

    def test_inspired_by_returns_creative_phases(self, output_dir, config):
        output_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState.create("inspired", InputMode.INSPIRED_BY, config, output_dir)
        assert state.get_phase_sequence() == list(CREATIVE_FLOW_PHASES)

    def test_adapt_mode_returns_adapt_phases(self, adapt_project_state):
        phases = adapt_project_state.get_phase_sequence()
        assert phases == list(ADAPT_FLOW_PHASES)

    def test_get_next_phase_returns_first_when_no_current(self, project_state):
        """When no phase has been started, next phase is the first one."""
        assert project_state.get_next_phase() == PipelinePhase.ANALYSIS

    def test_get_next_phase_returns_second_after_first(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
        project_state.complete_phase()
        assert project_state.get_next_phase() == PipelinePhase.STORY_BIBLE

    def test_get_next_phase_returns_none_after_last(self, project_state):
        """After the last phase, there is no next phase."""
        project_state.start_phase(PipelinePhase.VIDEO_ASSEMBLY)
        project_state.complete_phase()
        assert project_state.get_next_phase() is None

    def test_get_next_phase_for_adapt_mode(self, adapt_project_state):
        assert adapt_project_state.get_next_phase() == PipelinePhase.ANALYSIS

    def test_get_next_phase_advances_through_adapt_flow(self, adapt_project_state):
        adapt_project_state.start_phase(PipelinePhase.ANALYSIS)
        adapt_project_state.complete_phase()
        assert adapt_project_state.get_next_phase() == PipelinePhase.SCENE_SPLITTING

    def test_get_next_phase_falls_back_to_first_when_phase_not_in_sequence(
        self, adapt_project_state
    ):
        """When current_phase is not in the mode's sequence, returns the first phase."""
        # STORY_BIBLE belongs to creative flow, not adapt flow
        adapt_project_state._metadata.current_phase = PipelinePhase.STORY_BIBLE
        assert adapt_project_state.get_next_phase() == PipelinePhase.ANALYSIS


# ---------------------------------------------------------------------------
# Integration test: Resume workflow
# ---------------------------------------------------------------------------


class TestResumeWorkflow:
    """End-to-end resume workflow: create -> modify -> save -> load -> verify."""

    def test_full_resume_workflow(self, output_dir, config):
        """Simulate a workflow that is interrupted and resumed."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Create a new project
        state = ProjectState.create("resume-test", InputMode.ORIGINAL, config, output_dir)

        # Step 2: Start the first phase, add scenes
        state.start_phase(PipelinePhase.ANALYSIS)
        state.complete_phase()
        state.start_phase(PipelinePhase.STORY_BIBLE)
        state.complete_phase()
        state.start_phase(PipelinePhase.OUTLINE)
        state.complete_phase()

        # Add scenes after outline is done
        state.add_scene(1, "The Call", "A mysterious phone call arrives...")
        state.add_scene(2, "The Journey", "She packs her bags and leaves...")
        state.add_scene(3, "The Return", "Coming home changed everything...")

        # Step 3: Start scene_prose, complete some scenes
        state.start_phase(PipelinePhase.SCENE_PROSE)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.update_scene_asset(2, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(2, AssetType.TEXT, SceneStatus.FAILED)
        # Scene 3 is still pending

        # Step 4: Save (simulating crash/exit point)
        state.save()

        # Step 5: Resume by loading from disk
        resumed = ProjectState.load(state.project_dir)

        # Verify state
        assert resumed.metadata.current_phase == PipelinePhase.SCENE_PROSE
        assert resumed.metadata.status == PhaseStatus.IN_PROGRESS

        # Scene 1: completed, should not be in processing list
        scene1 = next(s for s in resumed.metadata.scenes if s.scene_number == 1)
        assert scene1.asset_status.text == SceneStatus.COMPLETED

        # Scene 2: failed, should be in processing list for retry
        scene2 = next(s for s in resumed.metadata.scenes if s.scene_number == 2)
        assert scene2.asset_status.text == SceneStatus.FAILED

        # Scene 3: pending, should be in processing list
        scene3 = next(s for s in resumed.metadata.scenes if s.scene_number == 3)
        assert scene3.asset_status.text == SceneStatus.PENDING

        # get_scenes_for_processing returns failed + pending
        scenes_to_process = resumed.get_scenes_for_processing()
        scene_numbers = {s.scene_number for s in scenes_to_process}
        assert scene_numbers == {2, 3}

        # Verify next phase is correct
        assert resumed.get_next_phase() == PipelinePhase.CRITIQUE_REVISION

    def test_resume_preserves_completed_artifacts(self, output_dir, config):
        """Completed assets are never overwritten after resume."""
        output_dir.mkdir(parents=True, exist_ok=True)

        state = ProjectState.create("preserve-test", InputMode.ORIGINAL, config, output_dir)
        state.add_scene(1, "Scene", "Scene prose content here.")
        state.start_phase(PipelinePhase.SCENE_PROSE)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.save()

        # Resume
        resumed = ProjectState.load(state.project_dir)

        # Cannot overwrite completed
        with pytest.raises(ValueError, match="[Cc]ompleted"):
            resumed.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)

    def test_resume_full_pipeline_through_tts(self, output_dir, config):
        """Walk through multiple phases and verify state persists correctly."""
        output_dir.mkdir(parents=True, exist_ok=True)

        state = ProjectState.create("multi-phase", InputMode.ADAPT, config, output_dir)
        state.add_scene(1, "Part One", "The adapted text begins.")

        # scene_splitting phase
        state.start_phase(PipelinePhase.SCENE_SPLITTING)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.complete_phase()

        # narration_flagging phase
        state.start_phase(PipelinePhase.NARRATION_FLAGGING)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED)
        state.complete_phase()

        state.save()

        # Resume and verify
        resumed = ProjectState.load(state.project_dir)
        assert resumed.metadata.status == PhaseStatus.COMPLETED
        assert resumed.metadata.current_phase == PipelinePhase.NARRATION_FLAGGING
        assert resumed.get_next_phase() == PipelinePhase.IMAGE_PROMPTS

        scene = resumed.metadata.scenes[0]
        assert scene.asset_status.text == SceneStatus.COMPLETED
        assert scene.asset_status.narration_text == SceneStatus.COMPLETED


# ---------------------------------------------------------------------------
# generate_project_id — collision avoidance and safety cap
# ---------------------------------------------------------------------------


class TestGenerateProjectId:
    """generate_project_id handles collision avoidance and safety cap."""

    def test_cap_raises_after_1000_attempts(self, output_dir):
        """RuntimeError when all 1000+ suffixed directories exist."""
        output_dir.mkdir(exist_ok=True)
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        base = f"adapt-{date_str}"

        # Create base directory and suffixed dirs 2..1001
        (output_dir / base).mkdir()
        for i in range(2, 1002):
            (output_dir / f"{base}-{i}").mkdir()

        with pytest.raises(RuntimeError, match="Could not generate unique project ID"):
            generate_project_id("adapt", output_dir)


# ---------------------------------------------------------------------------
# Edge cases and structural invariants
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and structural invariants."""

    def test_asset_dependency_values_are_valid_asset_types(self):
        """All dependency values must be valid AssetType members."""
        for asset, deps in ASSET_DEPENDENCIES.items():
            for dep in deps:
                assert isinstance(dep, AssetType), f"{asset} has invalid dependency {dep}"


# ---------------------------------------------------------------------------
# scan_project_dirs — discovers valid project directories
# ---------------------------------------------------------------------------


class TestScanProjectDirs:
    """scan_project_dirs discovers valid project directories."""

    def test_yields_valid_project_dirs(self, tmp_path):
        """Returns (path, data) tuples for dirs with valid project.json."""
        proj_dir = tmp_path / "adapt-2026-01-01"
        proj_dir.mkdir()
        project_json = (
            '{"project_id": "adapt-2026-01-01",'
            ' "mode": "adapt",'
            ' "created_at": "2026-01-01T00:00:00"}'
        )
        (proj_dir / "project.json").write_text(project_json, encoding="utf-8")

        results = list(scan_project_dirs(tmp_path))

        assert len(results) == 1
        path, data = results[0]
        assert path == proj_dir
        assert data["project_id"] == "adapt-2026-01-01"

    def test_skips_dirs_without_project_json(self, tmp_path):
        """Directories without project.json are silently skipped."""
        (tmp_path / "some-dir").mkdir()

        results = list(scan_project_dirs(tmp_path))

        assert results == []

    def test_skips_corrupted_project_json(self, tmp_path):
        """Directories with invalid JSON are silently skipped."""
        proj_dir = tmp_path / "bad-project"
        proj_dir.mkdir()
        (proj_dir / "project.json").write_text("not json", encoding="utf-8")

        results = list(scan_project_dirs(tmp_path))

        assert results == []

    def test_skips_non_dict_project_json(self, tmp_path):
        """project.json that parses to a non-dict value is skipped."""
        proj_dir = tmp_path / "array-project"
        proj_dir.mkdir()
        (proj_dir / "project.json").write_text("[1, 2, 3]", encoding="utf-8")

        results = list(scan_project_dirs(tmp_path))

        assert results == []

    def test_returns_empty_for_nonexistent_dir(self, tmp_path):
        """A directory that doesn't exist yields nothing."""
        results = list(scan_project_dirs(tmp_path / "nonexistent"))

        assert results == []

    def test_skips_regular_files(self, tmp_path):
        """Regular files in the output dir are not treated as projects."""
        (tmp_path / "not-a-dir.txt").write_text("hello", encoding="utf-8")

        results = list(scan_project_dirs(tmp_path))

        assert results == []
