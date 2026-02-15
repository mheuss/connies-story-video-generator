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

from story_video.models import PhaseStatus, PipelinePhase, Scene
from story_video.pipeline.caption_generator import CaptionProvider, generate_captions
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import ImageProvider, generate_image
from story_video.pipeline.image_prompt_writer import generate_image_prompts
from story_video.pipeline.story_writer import flag_narration, split_scenes
from story_video.pipeline.tts_generator import TTSProvider, generate_audio
from story_video.pipeline.video_assembler import assemble_scene, assemble_video
from story_video.state import ProjectState
from story_video.utils.text import prepare_narration

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


def _dispatch_phase(
    phase: PipelinePhase,
    state: ProjectState,
    *,
    claude_client: ClaudeClient | None,
    tts_provider: TTSProvider | None,
    image_provider: ImageProvider | None,
    caption_provider: CaptionProvider | None,
) -> None:
    """Route a phase to the appropriate pipeline module.

    Args:
        phase: The pipeline phase to execute.
        state: Project state.
        claude_client: Claude API client.
        tts_provider: TTS provider.
        image_provider: Image provider.
        caption_provider: Caption provider.

    Raises:
        ValueError: If the phase is unknown.
    """
    if phase == PipelinePhase.SCENE_SPLITTING:
        split_scenes(state, claude_client)

    elif phase == PipelinePhase.NARRATION_FLAGGING:
        flag_narration(state, claude_client)

    elif phase == PipelinePhase.IMAGE_PROMPTS:
        generate_image_prompts(state, claude_client)

    elif phase == PipelinePhase.NARRATION_PREP:
        _run_narration_prep(state)

    elif phase == PipelinePhase.TTS_GENERATION:
        _run_per_scene(state, lambda scene: generate_audio(scene, state, tts_provider))

    elif phase == PipelinePhase.IMAGE_GENERATION:
        _run_per_scene(state, lambda scene: generate_image(scene, state, image_provider))

    elif phase == PipelinePhase.CAPTION_GENERATION:
        _run_per_scene(state, lambda scene: generate_captions(scene, state, caption_provider))

    elif phase == PipelinePhase.VIDEO_ASSEMBLY:
        _run_per_scene(state, lambda scene: assemble_scene(scene, state))
        assemble_video(state)

    else:
        msg = f"Unknown phase: {phase}"
        raise ValueError(msg)


def _run_narration_prep(state: ProjectState) -> None:
    """Apply narration preparation transforms to all scenes.

    Narration prep runs on ALL scenes (not just pending ones) because
    flag_narration already marked NARRATION_TEXT as COMPLETED during the
    flagging phase. Using ``get_scenes_for_processing()`` would return
    an empty list since all assets are already completed.

    This phase transforms the narration text content (abbreviation
    expansion, number-to-words, pause markers, punctuation smoothing)
    without changing asset status -- the NARRATION_TEXT assets remain
    COMPLETED from the flagging phase.

    When ``narration_text`` is None (semi-auto mode where flag_narration
    did not set it), falls back to ``prose`` as the text source.
    """
    for scene in state.metadata.scenes:
        if scene.narration_text:
            scene.narration_text = prepare_narration(scene.narration_text)
        elif scene.prose:
            scene.narration_text = prepare_narration(scene.prose)


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
