"""Project state management for the Story Video Generator.

Creates, loads, saves, and manages the lifecycle of a story video project
via project.json. Handles state transitions, scene tracking, dependency
enforcement, and resume logic.

This module owns the business rules for state management:
- Phase transitions with validation
- Scene asset status updates with dependency checking
- Never-overwrite-completed invariant
- Resume logic (skip completed, retry failed, process pending)
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from story_video.models import (
    ADAPT_FLOW_PHASES,
    CREATIVE_FLOW_PHASES,
    AppConfig,
    AssetType,
    InputMode,
    PhaseStatus,
    PipelinePhase,
    ProjectMetadata,
    Scene,
    SceneStatus,
)

__all__ = ["ASSET_DEPENDENCIES", "PHASE_ASSET_MAP", "ProjectState", "generate_project_id"]


def generate_project_id(mode: str, output_dir: Path) -> str:
    """Generate a collision-safe project ID.

    Format: ``{mode}-{YYYY-MM-DD}`` (UTC). When a directory with that name
    already exists in *output_dir*, appends ``-2``, ``-3``, etc. until a
    free name is found.

    Args:
        mode: Input mode string (e.g. "adapt", "original", "inspired_by").
        output_dir: Base output directory where project directories live.

    Returns:
        A project ID string guaranteed not to collide with existing directories.

    Raises:
        RuntimeError: If more than 1000 projects exist for the same date.
    """
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    base = f"{mode}-{date_str}"

    if not output_dir.exists():
        return base

    if not (output_dir / base).exists():
        return base

    suffix = 2
    while (output_dir / f"{base}-{suffix}").exists():
        suffix += 1
        if suffix > 1000:
            msg = f"Could not generate unique project ID after 1000 attempts for base '{base}'"
            raise RuntimeError(msg)
    return f"{base}-{suffix}"


# ---------------------------------------------------------------------------
# Phase-to-asset mapping — which asset type each pipeline phase produces
# ---------------------------------------------------------------------------

PHASE_ASSET_MAP: dict[PipelinePhase, AssetType | None] = {
    PipelinePhase.ANALYSIS: None,  # No per-scene asset
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

# ---------------------------------------------------------------------------
# Asset dependency map — downstream dependency rules for scene assets
# ---------------------------------------------------------------------------
#
# Each asset type lists the prerequisite assets that must be completed before
# this asset can transition to in_progress. The rules enforce the production
# pipeline order:
#   text (no deps) -> narration_text -> audio -> captions
#   text -> image_prompt -> image
#   audio + image + captions -> video_segment
#
# This prevents impossible states like generating audio without narration text,
# or assembling video without all three media assets ready.

ASSET_DEPENDENCIES: dict[AssetType, list[AssetType]] = {
    AssetType.TEXT: [],  # No dependencies — text is the root asset
    AssetType.NARRATION_TEXT: [AssetType.TEXT],
    AssetType.IMAGE_PROMPT: [AssetType.TEXT],
    AssetType.AUDIO: [AssetType.NARRATION_TEXT],
    AssetType.IMAGE: [AssetType.IMAGE_PROMPT],
    AssetType.CAPTIONS: [AssetType.AUDIO],
    AssetType.VIDEO_SEGMENT: [AssetType.AUDIO, AssetType.IMAGE, AssetType.CAPTIONS],
}

# Subdirectories created inside each project directory
_PROJECT_SUBDIRS = ("scenes", "audio", "images", "captions", "video", "segments")


class ProjectState:
    """Manages the lifecycle and state of a story video project.

    Handles creation, persistence, state transitions, and resume logic
    for a project tracked via project.json.

    The class wraps a ProjectMetadata model and provides operations that
    enforce business rules:
    - Legal phase transitions only (pending->in_progress->completed/failed/awaiting_review)
    - Phase validation against the project's input mode
    - Never-overwrite-completed invariant for scene assets
    - Downstream dependency checking before asset status changes
    - Resume logic: skip completed, retry failed, process pending
    """

    def __init__(self, metadata: ProjectMetadata, project_dir: Path) -> None:
        """Initialize ProjectState with metadata and project directory path.

        This is a low-level constructor. Use the class methods ``create()``
        or ``load()`` instead.

        Args:
            metadata: The project metadata model.
            project_dir: Path to the project directory on disk.
        """
        self._metadata = metadata
        self._project_dir = project_dir

    # -------------------------------------------------------------------
    # Class methods: create, load
    # -------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        project_id: str,
        mode: InputMode,
        config: AppConfig,
        output_dir: Path,
    ) -> "ProjectState":
        """Create a new project and save initial state to disk.

        Creates the project directory structure and writes initial project.json.

        Directory structure:
            output_dir/project_id/
                project.json
                scenes/
                audio/
                images/
                captions/
                video/

        Args:
            project_id: Unique identifier for the project.
            mode: Input mode (original, inspired_by, adapt).
            config: Application configuration.
            output_dir: Base output directory (project dir will be output_dir/project_id).

        Returns:
            New ProjectState instance.

        Raises:
            FileExistsError: If the project directory already exists.
        """
        project_dir = output_dir / project_id

        if project_dir.exists():
            msg = f"Project directory already exists: {project_dir}"
            raise FileExistsError(msg)

        # Create directory structure
        project_dir.mkdir(parents=True)
        for subdir in _PROJECT_SUBDIRS:
            (project_dir / subdir).mkdir()

        # Create metadata
        metadata = ProjectMetadata(
            project_id=project_id,
            mode=mode,
            config=config,
        )

        state = cls(metadata=metadata, project_dir=project_dir)
        state.save()
        return state

    @classmethod
    def load(cls, project_dir: Path) -> "ProjectState":
        """Load an existing project from its project.json.

        Args:
            project_dir: Path to the project directory containing project.json.

        Returns:
            Loaded ProjectState instance.

        Raises:
            FileNotFoundError: If project.json doesn't exist.
            ValueError: If project.json contains invalid data.
        """
        json_path = project_dir / "project.json"

        if not json_path.exists():
            msg = f"project.json not found in {project_dir}"
            raise FileNotFoundError(msg)

        content = json_path.read_text(encoding="utf-8")
        try:
            metadata = ProjectMetadata.model_validate_json(content)
        except (ValidationError, ValueError) as exc:
            msg = f"Invalid project.json in {project_dir}: {exc}"
            raise ValueError(msg) from exc

        return cls(metadata=metadata, project_dir=project_dir)

    # -------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------

    def save(self) -> None:
        """Save current state to project.json.

        Writes atomically: data goes to a temporary file in the same directory,
        then is renamed over the target. This prevents a crash during write from
        corrupting the existing project.json.
        """
        json_path = self._project_dir / "project.json"
        content = self._metadata.model_dump_json(indent=2)

        # Atomic write: create temp file in same directory, then rename.
        # Using the same directory ensures the rename is atomic on POSIX
        # (same filesystem).
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".tmp",
            dir=str(json_path.parent),
        )
        os.close(fd)  # Close mkstemp's fd immediately; write_text opens its own.
        tmp_path = Path(tmp_path_str)
        try:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(json_path)
        except BaseException:
            # BaseException (not Exception) ensures cleanup runs even on
            # KeyboardInterrupt or SystemExit — important for atomic write safety.
            tmp_path.unlink(missing_ok=True)
            raise

    # -------------------------------------------------------------------
    # Phase transitions
    # -------------------------------------------------------------------

    def start_phase(self, phase: PipelinePhase) -> None:
        """Begin a pipeline phase. Sets current_phase and status to in_progress.

        Validates that the requested phase belongs to the phase sequence for
        this project's input mode.

        If the current status is AWAITING_REVIEW, it is auto-completed before
        starting the new phase. The caller resuming the pipeline is treated as
        implicit approval of the reviewed phase.

        Note:
            This method validates that the phase belongs to the correct mode
            but does NOT enforce sequential ordering. The caller (orchestrator)
            is responsible for starting phases in the correct sequence.

        Args:
            phase: The pipeline phase to start.

        Raises:
            ValueError: If the phase is not valid for the current input mode,
                or if another phase is currently in progress.
        """
        # Guard: cannot start a new phase while one is in progress
        if self._metadata.status == PhaseStatus.IN_PROGRESS:
            current = self._metadata.current_phase
            phase_name = current.value if current else "unknown"
            msg = (
                f"Cannot start phase '{phase.value}' while phase "
                f"'{phase_name}' is still in progress."
            )
            raise ValueError(msg)

        # Auto-complete a phase that was awaiting review — the caller resuming
        # the pipeline is the implicit approval signal.
        if self._metadata.status == PhaseStatus.AWAITING_REVIEW:
            self._metadata.status = PhaseStatus.COMPLETED

        # State transition validation: only phases in this mode's sequence are
        # allowed. This prevents starting a creative-only phase (e.g. STORY_BIBLE)
        # in adapt mode, or an adapt-only phase (e.g. SCENE_SPLITTING) in
        # original/inspired_by mode.
        valid_phases = self.get_phase_sequence()
        if phase not in valid_phases:
            msg = (
                f"Phase '{phase.value}' is not valid for mode '{self._metadata.mode.value}'. "
                f"Valid phases: {[p.value for p in valid_phases]}"
            )
            raise ValueError(msg)

        self._metadata.current_phase = phase
        self._metadata.status = PhaseStatus.IN_PROGRESS

    def complete_phase(self) -> None:
        """Mark the current phase as completed.

        Raises:
            ValueError: If no phase is currently in progress.
        """
        self._require_phase_in_progress()
        self._metadata.status = PhaseStatus.COMPLETED

    def fail_phase(self) -> None:
        """Mark the current phase as failed.

        Raises:
            ValueError: If no phase is currently in progress.
        """
        self._require_phase_in_progress()
        self._metadata.status = PhaseStatus.FAILED

    def await_review(self) -> None:
        """Mark the current phase as awaiting review (semi-automated mode).

        Raises:
            ValueError: If no phase is currently in progress.
        """
        self._require_phase_in_progress()
        self._metadata.status = PhaseStatus.AWAITING_REVIEW

    def _require_phase_in_progress(self) -> None:
        """Raise ValueError if no phase is currently in progress."""
        if self._metadata.current_phase is None:
            msg = "No phase has been started."
            raise ValueError(msg)
        if self._metadata.status != PhaseStatus.IN_PROGRESS:
            msg = (
                f"Phase '{self._metadata.current_phase.value}' is "
                f"'{self._metadata.status.value}', not 'in_progress'."
            )
            raise ValueError(msg)

    # -------------------------------------------------------------------
    # Scene management
    # -------------------------------------------------------------------

    def add_scene(
        self,
        scene_number: int,
        title: str,
        prose: str,
        summary: str | None = None,
    ) -> None:
        """Add a scene to the project.

        Args:
            scene_number: 1-based scene index.
            title: Scene title or beat description.
            prose: The actual story text for this scene.
            summary: Optional brief summary for running context across scenes.

        Raises:
            ValueError: If a scene with the given number already exists.
        """
        for existing in self._metadata.scenes:
            if existing.scene_number == scene_number:
                msg = f"Scene {scene_number} already exists in project."
                raise ValueError(msg)
        scene = Scene(scene_number=scene_number, title=title, prose=prose, summary=summary)
        self._metadata.scenes.append(scene)

    def update_scene_asset(
        self,
        scene_number: int,
        asset: AssetType,
        status: SceneStatus,
    ) -> None:
        """Update the status of a specific asset for a scene.

        Enforces two critical rules:
        1. Never overwrite a completed asset — if a scene's asset is completed,
           no status change is allowed.
        2. Downstream dependency rules — before allowing a transition to
           in_progress, all prerequisite assets must be completed.

        Args:
            scene_number: The scene to update.
            asset: Which asset type to update.
            status: The new status to set.

        Raises:
            ValueError: If scene not found, trying to overwrite completed, or
                dependency not met.
        """
        scene = self._find_scene(scene_number)
        current_status = getattr(scene.asset_status, asset.value)

        # Rule 1: Never overwrite a completed asset
        if current_status == SceneStatus.COMPLETED:
            msg = (
                f"Cannot change scene {scene_number} asset '{asset.value}' — "
                f"it is already completed. Completed assets must never be overwritten."
            )
            raise ValueError(msg)

        # Rule 2: Check downstream dependencies before allowing in_progress
        # transition. Dependencies are only checked when moving TO in_progress,
        # because that's when work begins. Transitions to failed or completed
        # from in_progress don't need re-checking (the work was already started
        # with valid dependencies).
        if status == SceneStatus.IN_PROGRESS:
            self._check_asset_dependencies(scene, asset)

        setattr(scene.asset_status, asset.value, status)

    def _find_scene(self, scene_number: int) -> Scene:
        """Find a scene by number, raising ValueError if not found."""
        for scene in self._metadata.scenes:
            if scene.scene_number == scene_number:
                return scene
        msg = f"Scene {scene_number} not found in project."
        raise ValueError(msg)

    def _check_asset_dependencies(self, scene: Scene, asset: AssetType) -> None:
        """Verify all prerequisite assets are completed before allowing work.

        Raises:
            ValueError: If any dependency is not completed.
        """
        dependencies = ASSET_DEPENDENCIES[asset]
        for dep in dependencies:
            dep_status = getattr(scene.asset_status, dep.value)
            if dep_status != SceneStatus.COMPLETED:
                msg = (
                    f"Dependency not met for scene {scene.scene_number} "
                    f"asset '{asset.value}': prerequisite '{dep.value}' "
                    f"is '{dep_status.value}', must be 'completed'."
                )
                raise ValueError(msg)

    # -------------------------------------------------------------------
    # Processing queries
    # -------------------------------------------------------------------

    def get_scenes_for_processing(self) -> list[Scene]:
        """Get scenes that need processing in the current phase.

        Returns scenes whose relevant asset is pending or failed (for retry).
        Skips scenes whose asset is completed or in_progress.

        For phases with no per-scene asset (ANALYSIS, STORY_BIBLE, OUTLINE),
        returns an empty list — those phases don't operate on individual
        scene assets.

        Returns:
            List of Scene objects needing work.

        Raises:
            ValueError: If no phase is currently in progress.
        """
        if self._metadata.current_phase is None or self._metadata.status != PhaseStatus.IN_PROGRESS:
            msg = "No phase is currently in progress."
            raise ValueError(msg)

        asset_type = PHASE_ASSET_MAP[self._metadata.current_phase]
        if asset_type is None:
            return []

        result = []
        for scene in self._metadata.scenes:
            asset_status = getattr(scene.asset_status, asset_type.value)
            if asset_status in (SceneStatus.PENDING, SceneStatus.FAILED):
                result.append(scene)

        return result

    # -------------------------------------------------------------------
    # Phase sequence helpers
    # -------------------------------------------------------------------

    def get_phase_sequence(self) -> list[PipelinePhase]:
        """Get the ordered phase sequence for this project's mode.

        Returns:
            List of PipelinePhase values in execution order.
        """
        if self._metadata.mode == InputMode.ADAPT:
            return list(ADAPT_FLOW_PHASES)
        # Both ORIGINAL and INSPIRED_BY use the creative flow
        return list(CREATIVE_FLOW_PHASES)

    def get_next_phase(self) -> PipelinePhase | None:
        """Get the next phase after the current one, or None if done.

        When no phase has been started yet, returns the first phase in the
        sequence. When the current phase is the last one and is completed,
        returns None.

        Returns:
            The next PipelinePhase, or None if the pipeline is complete.
        """
        phases = self.get_phase_sequence()

        if self._metadata.current_phase is None:
            return phases[0] if phases else None

        try:
            current_index = phases.index(self._metadata.current_phase)
        except ValueError:
            return phases[0] if phases else None

        next_index = current_index + 1
        if next_index < len(phases):
            return phases[next_index]
        return None

    # -------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------

    @property
    def project_dir(self) -> Path:
        """Path to the project directory."""
        return self._project_dir

    @property
    def metadata(self) -> ProjectMetadata:
        """The underlying project metadata."""
        return self._metadata
