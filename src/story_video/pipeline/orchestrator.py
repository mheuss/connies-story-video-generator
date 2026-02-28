"""Pipeline orchestrator.

Drives the adapt flow and creative flow sequentially, delegating all work
to existing pipeline modules. Supports fresh runs and resumes from any state.
See ``ADAPT_FLOW_PHASES`` and ``CREATIVE_FLOW_PHASES`` for the phase lists.

The orchestrator is the single entry point for running a pipeline. It:
- Determines the starting phase (fresh or resume)
- Dispatches each phase to the correct module
- Handles semi-auto checkpoints and autonomous mode
- Manages error recovery (fail_phase + save on exception)

See ADR-001 in DEVELOPMENT.md for architectural rationale.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from story_video.models import (
    AssetType,
    PhaseStatus,
    PipelinePhase,
    Scene,
    SceneAudioCue,
    SceneImagePrompt,
    SceneStatus,
    StoryHeader,
)
from story_video.pipeline.caption_generator import CaptionProvider, generate_captions
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import ImageProvider, generate_image
from story_video.pipeline.image_prompt_writer import generate_image_prompts
from story_video.pipeline.narration_prep import prepare_narration_llm, write_narration_changelog
from story_video.pipeline.story_writer import (
    analyze_source,
    create_outline,
    create_story_bible,
    critique_and_revise,
    flag_narration,
    split_scenes,
    write_scene_prose,
)
from story_video.pipeline.tts_generator import TTSProvider, generate_audio
from story_video.pipeline.video_assembler import assemble_scene, assemble_video
from story_video.state import ProjectState
from story_video.utils.narration_tags import (
    extract_image_tags_stripped,
    extract_music_tags_stripped,
    parse_story_header,
    strip_image_tags,
    strip_music_tags,
    validate_image_tags,
    validate_music_tags,
)

__all__ = ["run_pipeline"]

logger = logging.getLogger(__name__)

# Phases that pause for human review in semi-auto mode.
# These are the creative/editorial phases where human judgment is valuable
# before proceeding to expensive media generation.
_CHECKPOINT_PHASES = frozenset(
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


def run_pipeline(
    state: ProjectState,
    *,
    claude_client: ClaudeClient | None = None,
    tts_provider: TTSProvider | None = None,
    image_provider: ImageProvider | None = None,
    caption_provider: CaptionProvider | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
) -> None:
    """Run the pipeline from current state to completion or checkpoint.

    Drives phases sequentially, delegating to pipeline modules. Supports
    resume from any state -- completed scenes are automatically skipped
    by each module's use of ``get_scenes_for_processing()``.

    Semi-auto mode (default) pauses at checkpoint phases for human review.
    Autonomous mode runs straight through all phases.

    Args:
        state: Project state to drive.
        claude_client: Claude API client (required for content phases).
        tts_provider: TTS provider (required for audio generation).
        image_provider: Image provider (required for image generation).
        caption_provider: Caption provider (required for caption generation).
        on_progress: Optional callback(event_type, data) for progress reporting.
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
        scene_count = len(state.metadata.scenes)
        if on_progress:
            on_progress("phase_started", {"phase": phase.value, "scene_count": scene_count})
        try:
            _dispatch_phase(
                phase,
                state,
                claude_client=claude_client,
                tts_provider=tts_provider,
                image_provider=image_provider,
                caption_provider=caption_provider,
                story_header=story_header,
                on_progress=on_progress,
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
    on_progress: Callable[[str, dict], None] | None = None,
) -> None:
    """Route a phase to the appropriate pipeline module.

    Claude-dependent phases are dispatched via a lookup table. Media phases
    (TTS, image, caption, video) have distinct calling patterns and are
    handled explicitly.

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
    # All phases that require claude_client and call fn(state, claude_client).
    claude_handlers: dict[PipelinePhase, Callable[[ProjectState, ClaudeClient], None]] = {
        PipelinePhase.ANALYSIS: analyze_source,
        PipelinePhase.STORY_BIBLE: create_story_bible,
        PipelinePhase.OUTLINE: create_outline,
        PipelinePhase.SCENE_PROSE: write_scene_prose,
        PipelinePhase.CRITIQUE_REVISION: critique_and_revise,
        PipelinePhase.SCENE_SPLITTING: split_scenes,
        PipelinePhase.NARRATION_FLAGGING: flag_narration,
        # IMAGE_PROMPTS handled explicitly below (needs image tag extraction first)
        PipelinePhase.NARRATION_PREP: _run_narration_prep,
    }

    def _scene_cb(scene_number: int, total: int) -> None:
        if on_progress:
            on_progress("scene_progress", {"scene_number": scene_number, "total": total})

    if phase in claude_handlers:
        if claude_client is None:
            msg = f"claude_client is required for {phase.name} phase"
            raise ValueError(msg)
        claude_handlers[phase](state, claude_client)

    elif phase == PipelinePhase.IMAGE_PROMPTS:
        if claude_client is None:
            msg = "claude_client is required for IMAGE_PROMPTS phase"
            raise ValueError(msg)
        _populate_image_tags(state, story_header)
        _populate_music_tags(state, story_header)
        generate_image_prompts(state, claude_client)

    elif phase == PipelinePhase.TTS_GENERATION:
        if tts_provider is None:
            msg = "tts_provider is required for TTS_GENERATION phase"
            raise ValueError(msg)
        _run_per_scene(
            state,
            lambda scene: generate_audio(scene, state, tts_provider, story_header=story_header),
            on_scene_done=_scene_cb,
        )

    elif phase == PipelinePhase.IMAGE_GENERATION:
        if image_provider is None:
            msg = "image_provider is required for IMAGE_GENERATION phase"
            raise ValueError(msg)
        _run_per_scene(
            state,
            lambda scene: generate_image(scene, state, image_provider),
            on_scene_done=_scene_cb,
        )

    elif phase == PipelinePhase.CAPTION_GENERATION:
        if caption_provider is None:
            msg = "caption_provider is required for CAPTION_GENERATION phase"
            raise ValueError(msg)
        _run_per_scene(
            state,
            lambda scene: generate_captions(scene, state, caption_provider),
            on_scene_done=_scene_cb,
        )

    elif phase == PipelinePhase.VIDEO_ASSEMBLY:
        _run_per_scene(
            state,
            lambda scene: assemble_scene(scene, state, story_header=story_header),
            on_scene_done=_scene_cb,
        )
        final_path = assemble_video(state)
        logger.info("Final video: %s", final_path)

    else:
        msg = f"Unknown phase: {phase}"
        raise ValueError(msg)


def _populate_image_tags(state: ProjectState, story_header: StoryHeader | None) -> None:
    """Extract image tags from scene prose and populate image_prompts from YAML header.

    For each scene, if the prose contains **image:key** tags:
    1. Extract tags with character offsets
    2. Validate all keys exist in the story header's images map
    3. Set scene.image_prompts from the YAML-defined prompts

    Scenes without image tags are left unchanged (image_prompts stays empty).

    Args:
        state: Project state with populated scenes.
        story_header: Parsed story header with images map, or None.
    """
    images = story_header.images if story_header else {}

    for scene in state.metadata.scenes:
        # Skip scenes that already have prompts (e.g., from a previous run)
        if scene.image_prompts:
            continue

        tags = extract_image_tags_stripped(scene.prose)
        if not tags:
            continue

        if not images:
            msg = (
                f"Scene {scene.scene_number} has image tags but no images "
                "defined in the YAML header."
            )
            raise ValueError(msg)

        validate_image_tags(tags, images)

        scene.image_prompts = [
            SceneImagePrompt(key=tag.key, prompt=images[tag.key], position=tag.position)
            for tag in tags
        ]

        # Strip image tags from narration text so TTS doesn't speak them.
        # Also ensures narration_prep doesn't pass image tags to Claude.
        text_to_strip = scene.narration_text if scene.narration_text is not None else scene.prose
        scene.narration_text = strip_image_tags(text_to_strip)


def _populate_music_tags(state: ProjectState, story_header: StoryHeader | None) -> None:
    """Extract music tags from scene prose and populate audio_cues from YAML header.

    For each scene, if the prose contains **music:key** tags:
    1. Extract tags with character offsets (stripped-text coordinates)
    2. Validate all keys exist in the story header's audio map
    3. Set scene.audio_cues from the YAML-defined audio assets

    Scenes without music tags are left unchanged (audio_cues stays empty).

    Args:
        state: Project state with populated scenes.
        story_header: Parsed story header with audio map, or None.
    """
    audio = story_header.audio if story_header else {}

    for scene in state.metadata.scenes:
        # Skip scenes that already have cues (e.g., from a previous run)
        if scene.audio_cues:
            continue

        tags = extract_music_tags_stripped(scene.prose)
        if not tags:
            continue

        if not audio:
            msg = (
                f"Scene {scene.scene_number} has music tags but no audio "
                "defined in the YAML header."
            )
            raise ValueError(msg)

        validate_music_tags(tags, audio)

        scene.audio_cues = [SceneAudioCue(key=tag.key, position=tag.position) for tag in tags]

        # Strip music tags from narration text so TTS doesn't speak them.
        # Also ensures narration_prep doesn't pass music tags to Claude.
        text_to_strip = scene.narration_text if scene.narration_text is not None else scene.prose
        scene.narration_text = strip_music_tags(text_to_strip)


def _run_narration_prep(state: ProjectState, claude_client: ClaudeClient) -> None:
    """Apply LLM-based narration preparation to pending scenes.

    Calls Claude once per scene to rewrite narration text for TTS. Accumulates
    a pronunciation guide across scenes (scene 1's entries feed into scene 2's
    prompt). Writes a changelog of all modifications to the project directory.

    Also marks narration_text assets as COMPLETED. In adapt mode this is
    redundant (flag_narration already set it), but in the creative flow
    there is no flagging phase, so narration_prep is responsible for it.

    On retry after mid-phase failure, already-processed scenes are skipped
    using a ``narration_prep_done.json`` tracker file. The pronunciation guide
    for skipped scenes is lost (it was only in memory during the original run),
    so later scenes may get slightly different pronunciation suggestions. This
    is acceptable — the guide is a quality optimization, not a correctness
    requirement.
    """
    # Load tracker of scenes already processed (for retry support).
    done_path = state.project_dir / "narration_prep_done.json"
    done_scenes: set[int] = set()
    if done_path.exists():
        try:
            done_scenes = set(json.loads(done_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Corrupt narration_prep_done.json; starting fresh")
            done_scenes = set()

    pronunciation_guide: list[dict[str, str]] = []
    changelog: list[dict] = []
    total_scenes = len(state.metadata.scenes)

    for scene in state.metadata.scenes:
        if scene.scene_number in done_scenes:
            logger.info(
                "Scene %d already prepped — skipping",
                scene.scene_number,
            )
            continue

        text = scene.narration_text if scene.narration_text is not None else scene.prose
        if not text:
            logger.warning(
                "Scene %d has no narration_text or prose — skipping narration prep",
                scene.scene_number,
            )
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
        # Mark narration_text COMPLETED if not already set (adapt mode sets it
        # during NARRATION_FLAGGING; creative flow relies on narration_prep).
        if scene.asset_status.narration_text != SceneStatus.COMPLETED:
            state.update_scene_asset(
                scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.IN_PROGRESS
            )
            state.update_scene_asset(
                scene.scene_number, AssetType.NARRATION_TEXT, SceneStatus.COMPLETED
            )

        pronunciation_guide.extend(result["pronunciation_guide_additions"])

        for change in result["changes"]:
            changelog.append({"scene": scene.scene_number, **change})

        # Persist tracker after each scene so mid-phase failures don't re-process.
        done_scenes.add(scene.scene_number)
        done_path.write_text(json.dumps(sorted(done_scenes)), encoding="utf-8")

    if changelog:
        write_narration_changelog(changelog, state.project_dir)

    state.save()


def _run_per_scene(
    state: ProjectState,
    process_fn: Callable[[Scene], None],
    on_scene_done: Callable[[int, int], None] | None = None,
) -> None:
    """Run a processing function on each scene that needs work.

    Uses ``state.get_scenes_for_processing()`` to find scenes whose
    relevant asset is pending or failed (for retry). Completed scenes
    are automatically skipped.

    Args:
        state: Project state (must have a phase in progress).
        process_fn: Callable taking a single Scene argument.
        on_scene_done: Optional callback(scene_number, total) after each scene.
    """
    scenes = state.get_scenes_for_processing()
    total = len(state.metadata.scenes)
    already_done = total - len(scenes)
    for i, scene in enumerate(scenes, already_done + 1):
        process_fn(scene)
        if on_scene_done:
            on_scene_done(i, total)
