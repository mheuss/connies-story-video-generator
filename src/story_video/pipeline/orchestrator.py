"""Pipeline orchestrator for the adapt flow.

Drives the 8-phase adapt flow sequentially, delegating all work to existing
pipeline modules. Supports fresh runs and resumes from any state.

The orchestrator is the single entry point for running a pipeline. It:
- Determines the starting phase (fresh or resume)
- Dispatches each phase to the correct module
- Handles semi-auto checkpoints and autonomous mode
- Manages error recovery (fail_phase + save on exception)

See ADR-001 in DEVELOPMENT.md for architectural rationale.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from story_video.models import PhaseStatus, PipelinePhase, Scene, StoryHeader
from story_video.pipeline.caption_generator import CaptionProvider, generate_captions
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import ImageProvider, generate_image
from story_video.pipeline.image_prompt_writer import generate_image_prompts
from story_video.pipeline.narration_prep import prepare_narration_llm, write_narration_changelog
from story_video.pipeline.story_writer import flag_narration, split_scenes
from story_video.pipeline.tts_generator import TTSProvider, generate_audio
from story_video.pipeline.video_assembler import assemble_scene, assemble_video
from story_video.state import ProjectState
from story_video.utils.narration_tags import parse_story_header

__all__ = ["run_pipeline"]

logger = logging.getLogger(__name__)

# Phases that pause for human review in semi-auto mode.
# These are the creative/editorial phases where human judgment is valuable
# before proceeding to expensive media generation.
_CHECKPOINT_PHASES = frozenset(
    {
        PipelinePhase.SCENE_SPLITTING,
        PipelinePhase.NARRATION_FLAGGING,
        PipelinePhase.IMAGE_PROMPTS,
        PipelinePhase.NARRATION_PREP,
    }
)


def run_pipeline(
    state: ProjectState,
    *,
    claude_client: ClaudeClient | None = None,
    tts_provider: TTSProvider | None = None,
    image_provider: ImageProvider | None = None,
    caption_provider: CaptionProvider | None = None,
) -> None:
    """Run the adapt flow pipeline from current state to completion or checkpoint.

    Drives phases sequentially, delegating to pipeline modules. Supports
    resume from any state -- completed scenes are automatically skipped
    by each module's use of ``get_scenes_for_processing()``.

    Semi-auto mode (default) pauses at checkpoint phases (scene splitting,
    narration flagging, image prompts) for human review. Autonomous mode
    runs straight through all phases.

    Args:
        state: Project state to drive.
        claude_client: Claude API client (required for content phases).
        tts_provider: TTS provider (required for audio generation).
        image_provider: Image provider (required for image generation).
        caption_provider: Caption provider (required for caption generation).
    """
    phases = state.get_phase_sequence()
    start = _determine_start_phase(state, phases)
    if start is None:
        logger.info("Pipeline already complete")
        return

    start_idx = phases.index(start)
    autonomous = state.metadata.config.pipeline.autonomous

    # Parse story header from source file (if present) for multi-voice TTS.
    # Done once at pipeline start so the header is available when the TTS
    # phase is reached.
    story_header = _parse_source_header(state)

    # State is saved at three points: checkpoint pause, phase failure, and
    # end of full run. Intermediate phase completions accumulate in memory
    # and are persisted together. On failure, the exception handler saves
    # all accumulated state alongside the FAILED status, so completed
    # phases are not lost.
    for phase in phases[start_idx:]:
        state.start_phase(phase)
        try:
            _dispatch_phase(
                phase,
                state,
                claude_client=claude_client,
                tts_provider=tts_provider,
                image_provider=image_provider,
                caption_provider=caption_provider,
                story_header=story_header,
            )
        except Exception:
            state.fail_phase()
            state.save()
            raise

        # Semi-auto checkpoint: pause for human review instead of completing.
        # await_review() sets status to AWAITING_REVIEW. When the user resumes,
        # _determine_start_phase treats AWAITING_REVIEW as "approved" and
        # advances to the next phase.
        if phase in _CHECKPOINT_PHASES and not autonomous:
            state.await_review()
            state.save()
            return

        state.complete_phase()

    state.save()


def _determine_start_phase(
    state: ProjectState, phases: list[PipelinePhase]
) -> PipelinePhase | None:
    """Determine which phase to start or resume from.

    Resume logic handles five cases:
    - No current phase (fresh project) -- first phase
    - FAILED or IN_PROGRESS -- retry current phase
    - COMPLETED -- advance to next phase
    - AWAITING_REVIEW -- advance to next phase (user approved by resuming)
    - No next phase after current -- None (pipeline complete)

    Args:
        state: Project state to inspect.
        phases: Ordered list of phases for this project's mode.

    Returns:
        The phase to start from, or None if the pipeline is complete.
    """
    current = state.metadata.current_phase
    if current is None:
        return phases[0] if phases else None

    status = state.metadata.status
    if status in (PhaseStatus.FAILED, PhaseStatus.IN_PROGRESS):
        return current

    # COMPLETED or AWAITING_REVIEW -- advance to next phase
    return state.get_next_phase()


def _parse_source_header(state: ProjectState) -> StoryHeader | None:
    """Parse the YAML story header from source_story.txt.

    Returns the parsed header if the source file exists and contains
    valid YAML front matter, or None otherwise.

    Args:
        state: Project state with project_dir.

    Returns:
        Parsed StoryHeader, or None if no header is present.

    Raises:
        ValueError: If the source file contains a malformed YAML header.
    """
    source_path = state.project_dir / "source_story.txt"
    if not source_path.exists():
        return None

    source_text = source_path.read_text(encoding="utf-8")
    try:
        header, _ = parse_story_header(source_text)
    except ValueError:
        logger.error("Failed to parse story header from %s", source_path)
        raise
    return header


def _dispatch_phase(
    phase: PipelinePhase,
    state: ProjectState,
    *,
    claude_client: ClaudeClient | None,
    tts_provider: TTSProvider | None,
    image_provider: ImageProvider | None,
    caption_provider: CaptionProvider | None,
    story_header: StoryHeader | None = None,
) -> None:
    """Route a phase to the appropriate pipeline module.

    Args:
        phase: The pipeline phase to execute.
        state: Project state.
        claude_client: Claude API client.
        tts_provider: TTS provider.
        image_provider: Image provider.
        caption_provider: Caption provider.
        story_header: Parsed story header for multi-voice TTS, or None.

    Raises:
        ValueError: If the phase is unknown or a required provider is None.
    """
    if phase == PipelinePhase.SCENE_SPLITTING:
        if claude_client is None:
            msg = "claude_client is required for SCENE_SPLITTING phase"
            raise ValueError(msg)
        split_scenes(state, claude_client)

    elif phase == PipelinePhase.NARRATION_FLAGGING:
        if claude_client is None:
            msg = "claude_client is required for NARRATION_FLAGGING phase"
            raise ValueError(msg)
        flag_narration(state, claude_client)

    elif phase == PipelinePhase.IMAGE_PROMPTS:
        if claude_client is None:
            msg = "claude_client is required for IMAGE_PROMPTS phase"
            raise ValueError(msg)
        generate_image_prompts(state, claude_client)

    elif phase == PipelinePhase.NARRATION_PREP:
        if claude_client is None:
            msg = "claude_client is required for NARRATION_PREP phase"
            raise ValueError(msg)
        _run_narration_prep(state, claude_client)

    elif phase == PipelinePhase.TTS_GENERATION:
        if tts_provider is None:
            msg = "tts_provider is required for TTS_GENERATION phase"
            raise ValueError(msg)
        _run_per_scene(
            state,
            lambda scene: generate_audio(scene, state, tts_provider, story_header=story_header),
        )

    elif phase == PipelinePhase.IMAGE_GENERATION:
        if image_provider is None:
            msg = "image_provider is required for IMAGE_GENERATION phase"
            raise ValueError(msg)
        _run_per_scene(state, lambda scene: generate_image(scene, state, image_provider))

    elif phase == PipelinePhase.CAPTION_GENERATION:
        if caption_provider is None:
            msg = "caption_provider is required for CAPTION_GENERATION phase"
            raise ValueError(msg)
        _run_per_scene(state, lambda scene: generate_captions(scene, state, caption_provider))

    elif phase == PipelinePhase.VIDEO_ASSEMBLY:
        _run_per_scene(state, lambda scene: assemble_scene(scene, state))
        assemble_video(state)

    else:
        msg = f"Unknown phase: {phase}"
        raise ValueError(msg)


def _run_narration_prep(state: ProjectState, claude_client: ClaudeClient) -> None:
    """Apply LLM-based narration preparation to all scenes.

    Calls Claude once per scene to rewrite narration text for TTS. Accumulates
    a pronunciation guide across scenes (scene 1's entries feed into scene 2's
    prompt). Writes a changelog of all modifications to the project directory.

    Runs on ALL scenes (not just pending ones) because narration_text assets
    are already COMPLETED from the flagging phase.
    """
    pronunciation_guide: list[dict[str, str]] = []
    changelog: list[dict] = []
    total_scenes = len(state.metadata.scenes)

    for scene in state.metadata.scenes:
        text = scene.narration_text or scene.prose
        if not text:
            continue

        result = prepare_narration_llm(
            text,
            claude_client,
            pronunciation_guide=pronunciation_guide,
            story_title=state.metadata.project_id,
            scene_number=scene.scene_number,
            total_scenes=total_scenes,
        )

        scene.narration_text = result["modified_text"]

        for addition in result["pronunciation_guide_additions"]:
            pronunciation_guide.append(addition)

        for change in result["changes"]:
            changelog.append({"scene": scene.scene_number, **change})

    if changelog:
        write_narration_changelog(changelog, state.project_dir)


def _run_per_scene(state: ProjectState, process_fn: Callable[[Scene], None]) -> None:
    """Run a processing function on each scene that needs work.

    Uses ``state.get_scenes_for_processing()`` to find scenes whose
    relevant asset is pending or failed (for retry). Completed scenes
    are automatically skipped.

    Args:
        state: Project state (must have a phase in progress).
        process_fn: Callable taking a single Scene argument.
    """
    scenes = state.get_scenes_for_processing()
    for scene in scenes:
        process_fn(scene)
