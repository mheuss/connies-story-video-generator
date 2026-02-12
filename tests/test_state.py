"""Tests for story_video.state — Project state management.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the ProjectState class.
"""

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

    def test_covers_all_pipeline_phases(self):
        """Every PipelinePhase must have an entry in PHASE_ASSET_MAP."""
        for phase in PipelinePhase:
            assert phase in PHASE_ASSET_MAP, f"Missing mapping for {phase}"

    def test_scene_prose_maps_to_text(self):
        assert PHASE_ASSET_MAP[PipelinePhase.SCENE_PROSE] == AssetType.TEXT

    def test_tts_generation_maps_to_audio(self):
        assert PHASE_ASSET_MAP[PipelinePhase.TTS_GENERATION] == AssetType.AUDIO

    def test_image_generation_maps_to_image(self):
        assert PHASE_ASSET_MAP[PipelinePhase.IMAGE_GENERATION] == AssetType.IMAGE

    def test_caption_generation_maps_to_captions(self):
        assert PHASE_ASSET_MAP[PipelinePhase.CAPTION_GENERATION] == AssetType.CAPTIONS

    def test_video_assembly_maps_to_video_segment(self):
        assert PHASE_ASSET_MAP[PipelinePhase.VIDEO_ASSEMBLY] == AssetType.VIDEO_SEGMENT

    def test_analysis_maps_to_none(self):
        """Analysis produces no per-scene asset."""
        assert PHASE_ASSET_MAP[PipelinePhase.ANALYSIS] is None

    def test_story_bible_maps_to_none(self):
        assert PHASE_ASSET_MAP[PipelinePhase.STORY_BIBLE] is None

    def test_outline_maps_to_none(self):
        assert PHASE_ASSET_MAP[PipelinePhase.OUTLINE] is None

    def test_image_prompts_maps_to_none(self):
        assert PHASE_ASSET_MAP[PipelinePhase.IMAGE_PROMPTS] is None

    def test_narration_prep_maps_to_narration_text(self):
        assert PHASE_ASSET_MAP[PipelinePhase.NARRATION_PREP] == AssetType.NARRATION_TEXT

    def test_narration_flagging_maps_to_narration_text(self):
        assert PHASE_ASSET_MAP[PipelinePhase.NARRATION_FLAGGING] == AssetType.NARRATION_TEXT

    def test_critique_revision_maps_to_text(self):
        assert PHASE_ASSET_MAP[PipelinePhase.CRITIQUE_REVISION] == AssetType.TEXT

    def test_scene_splitting_maps_to_text(self):
        assert PHASE_ASSET_MAP[PipelinePhase.SCENE_SPLITTING] == AssetType.TEXT


class TestAssetDependencies:
    """ASSET_DEPENDENCIES — downstream dependency rules for assets."""

    def test_covers_all_asset_types(self):
        """Every AssetType must have an entry in ASSET_DEPENDENCIES."""
        for asset in AssetType:
            assert asset in ASSET_DEPENDENCIES, f"Missing dependency for {asset}"

    def test_text_has_no_dependencies(self):
        assert ASSET_DEPENDENCIES[AssetType.TEXT] == []

    def test_narration_text_depends_on_text(self):
        assert ASSET_DEPENDENCIES[AssetType.NARRATION_TEXT] == [AssetType.TEXT]

    def test_audio_depends_on_narration_text(self):
        assert ASSET_DEPENDENCIES[AssetType.AUDIO] == [AssetType.NARRATION_TEXT]

    def test_image_depends_on_text(self):
        assert ASSET_DEPENDENCIES[AssetType.IMAGE] == [AssetType.TEXT]

    def test_captions_depends_on_audio(self):
        assert ASSET_DEPENDENCIES[AssetType.CAPTIONS] == [AssetType.AUDIO]

    def test_video_segment_depends_on_audio_image_captions(self):
        deps = ASSET_DEPENDENCIES[AssetType.VIDEO_SEGMENT]
        assert AssetType.AUDIO in deps
        assert AssetType.IMAGE in deps
        assert AssetType.CAPTIONS in deps
        assert len(deps) == 3


# ---------------------------------------------------------------------------
# ProjectState.create() unit tests
# ---------------------------------------------------------------------------


class TestProjectStateCreate:
    """ProjectState.create() — creates a new project with initial state."""

    def test_returns_project_state_instance(self, output_dir, config):
        output_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState.create("new-project", InputMode.ORIGINAL, config, output_dir)
        assert isinstance(state, ProjectState)

    def test_project_dir_is_under_output_dir(self, output_dir, config):
        output_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState.create("my-project", InputMode.ORIGINAL, config, output_dir)
        assert state.project_dir == output_dir / "my-project"

    def test_metadata_has_correct_project_id(self, project_state):
        assert project_state.metadata.project_id == "test-project"

    def test_metadata_has_correct_mode(self, project_state):
        assert project_state.metadata.mode == InputMode.ORIGINAL

    def test_metadata_status_is_pending(self, project_state):
        assert project_state.metadata.status == PhaseStatus.PENDING

    def test_metadata_current_phase_is_none(self, project_state):
        assert project_state.metadata.current_phase is None

    def test_metadata_scenes_is_empty(self, project_state):
        assert project_state.metadata.scenes == []

    def test_metadata_stores_config(self, project_state, config):
        assert project_state.metadata.config == config

    def test_raises_if_project_dir_already_exists(self, output_dir, config):
        output_dir.mkdir(parents=True, exist_ok=True)
        ProjectState.create("dup-project", InputMode.ORIGINAL, config, output_dir)
        with pytest.raises(FileExistsError):
            ProjectState.create("dup-project", InputMode.ORIGINAL, config, output_dir)

    def test_adapt_mode_is_stored(self, adapt_project_state):
        assert adapt_project_state.metadata.mode == InputMode.ADAPT

    def test_inspired_by_mode_is_stored(self, output_dir, config):
        output_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState.create("inspired", InputMode.INSPIRED_BY, config, output_dir)
        assert state.metadata.mode == InputMode.INSPIRED_BY


# ---------------------------------------------------------------------------
# ProjectState.create() integration tests (disk I/O)
# ---------------------------------------------------------------------------


class TestProjectStateCreateDiskIO:
    """ProjectState.create() writes project.json and creates directories."""

    def test_creates_project_directory(self, project_state):
        assert project_state.project_dir.is_dir()

    def test_creates_project_json(self, project_state):
        assert (project_state.project_dir / "project.json").is_file()

    def test_creates_scenes_directory(self, project_state):
        assert (project_state.project_dir / "scenes").is_dir()

    def test_creates_audio_directory(self, project_state):
        assert (project_state.project_dir / "audio").is_dir()

    def test_creates_images_directory(self, project_state):
        assert (project_state.project_dir / "images").is_dir()

    def test_creates_captions_directory(self, project_state):
        assert (project_state.project_dir / "captions").is_dir()

    def test_creates_video_directory(self, project_state):
        assert (project_state.project_dir / "video").is_dir()

    def test_project_json_contains_valid_data(self, project_state):
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

    def test_loaded_project_id_matches(self, project_state):
        loaded = ProjectState.load(project_state.project_dir)
        assert loaded.metadata.project_id == "test-project"

    def test_loaded_mode_matches(self, project_state):
        loaded = ProjectState.load(project_state.project_dir)
        assert loaded.metadata.mode == InputMode.ORIGINAL

    def test_loaded_status_matches(self, project_state):
        loaded = ProjectState.load(project_state.project_dir)
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

    def test_start_phase_sets_current_phase(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
        assert project_state.metadata.current_phase == PipelinePhase.ANALYSIS

    def test_start_phase_sets_status_to_in_progress(self, project_state):
        project_state.start_phase(PipelinePhase.ANALYSIS)
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

    def test_complete_phase_raises_if_no_phase_in_progress(self, project_state):
        with pytest.raises(ValueError, match="[Nn]o phase"):
            project_state.complete_phase()

    def test_fail_phase_raises_if_no_phase_in_progress(self, project_state):
        with pytest.raises(ValueError, match="[Nn]o phase"):
            project_state.fail_phase()

    def test_await_review_raises_if_no_phase_in_progress(self, project_state):
        with pytest.raises(ValueError, match="[Nn]o phase"):
            project_state.await_review()

    def test_start_phase_rejects_invalid_phase_for_adapt_mode(self, adapt_project_state):
        """Adapt mode does not have an ANALYSIS phase."""
        with pytest.raises(ValueError, match="not valid"):
            adapt_project_state.start_phase(PipelinePhase.ANALYSIS)

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

    def test_rejects_start_phase_while_in_progress(self, project_state):
        """Cannot start a new phase while another is still in progress."""
        project_state.start_phase(PipelinePhase.ANALYSIS)
        with pytest.raises(ValueError, match="still in progress"):
            project_state.start_phase(PipelinePhase.STORY_BIBLE)

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

    def test_adds_scene_to_scenes_list(self, project_state):
        project_state.add_scene(1, "Opening", "The story begins...")
        assert len(project_state.metadata.scenes) == 1

    def test_scene_has_correct_number(self, project_state):
        project_state.add_scene(1, "Opening", "The story begins...")
        assert project_state.metadata.scenes[0].scene_number == 1

    def test_scene_has_correct_title(self, project_state):
        project_state.add_scene(1, "Opening", "The story begins...")
        assert project_state.metadata.scenes[0].title == "Opening"

    def test_scene_has_correct_prose(self, project_state):
        project_state.add_scene(1, "Opening", "The story begins...")
        assert project_state.metadata.scenes[0].prose == "The story begins..."

    def test_scene_assets_default_to_pending(self, project_state):
        project_state.add_scene(1, "Opening", "The story begins...")
        asset_status = project_state.metadata.scenes[0].asset_status
        assert asset_status.text == SceneStatus.PENDING
        assert asset_status.audio == SceneStatus.PENDING

    def test_add_multiple_scenes(self, project_state):
        project_state.add_scene(1, "First", "First scene.")
        project_state.add_scene(2, "Second", "Second scene.")
        project_state.add_scene(3, "Third", "Third scene.")
        assert len(project_state.metadata.scenes) == 3

    def test_rejects_duplicate_scene_number(self, project_state):
        project_state.add_scene(1, "Scene One", "First prose.")
        with pytest.raises(ValueError, match="Scene 1 already exists"):
            project_state.add_scene(1, "Scene One Again", "Different prose.")


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

    def test_never_overwrite_completed_asset(self, project_with_scenes):
        """A completed asset must never be overwritten — this is a critical rule."""
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        with pytest.raises(ValueError, match="[Cc]ompleted"):
            project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)

    def test_never_overwrite_completed_with_failed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        with pytest.raises(ValueError, match="[Cc]ompleted"):
            project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.FAILED)

    def test_never_overwrite_completed_with_pending(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        with pytest.raises(ValueError, match="[Cc]ompleted"):
            project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.PENDING)


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

    def test_image_requires_text_completed(self, project_with_scenes):
        """Cannot start image if text is not completed."""
        with pytest.raises(ValueError, match="[Dd]ependenc"):
            project_with_scenes.update_scene_asset(1, AssetType.IMAGE, SceneStatus.IN_PROGRESS)

    def test_image_allowed_when_text_completed(self, project_with_scenes):
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        project_with_scenes.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
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
        """Full chain: text -> narration_text -> audio, text -> image, audio -> captions.
        Then video_segment requires audio + image + captions."""
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
        assert adapt_project_state.get_next_phase() == PipelinePhase.SCENE_SPLITTING

    def test_get_next_phase_advances_through_adapt_flow(self, adapt_project_state):
        adapt_project_state.start_phase(PipelinePhase.SCENE_SPLITTING)
        adapt_project_state.complete_phase()
        assert adapt_project_state.get_next_phase() == PipelinePhase.NARRATION_FLAGGING


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
# Edge cases and structural invariants
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and structural invariants."""

    def test_project_dir_property_returns_correct_path(self, project_state, output_dir):
        assert project_state.project_dir == output_dir / "test-project"

    def test_metadata_property_returns_project_metadata(self, project_state):
        assert isinstance(project_state.metadata, ProjectMetadata)

    def test_phase_asset_map_keys_match_pipeline_phase_members(self):
        """PHASE_ASSET_MAP must cover exactly the PipelinePhase members."""
        assert set(PHASE_ASSET_MAP.keys()) == set(PipelinePhase)

    def test_asset_dependencies_keys_match_asset_type_members(self):
        """ASSET_DEPENDENCIES must cover exactly the AssetType members."""
        assert set(ASSET_DEPENDENCIES.keys()) == set(AssetType)

    def test_asset_dependency_values_are_valid_asset_types(self):
        """All dependency values must be valid AssetType members."""
        for asset, deps in ASSET_DEPENDENCIES.items():
            for dep in deps:
                assert isinstance(dep, AssetType), f"{asset} has invalid dependency {dep}"
