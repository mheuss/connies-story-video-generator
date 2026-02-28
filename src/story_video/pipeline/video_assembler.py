"""Video assembly orchestration for scene rendering and final concatenation.

Provides two public functions:
    assemble_scene: Render a single scene into a video segment (image + audio + subtitles).
    assemble_video: Concatenate all scene segments into the final video with crossfade transitions.

Both functions delegate to ``story_video.ffmpeg.commands`` for FFmpeg execution
and ``story_video.ffmpeg.subtitles`` for ASS subtitle generation.
"""

import logging
from pathlib import Path

from story_video.ffmpeg.commands import (
    AudioCueSpec,
    build_concat_command,
    build_segment_command,
    probe_duration,
    run_ffmpeg,
)
from story_video.ffmpeg.subtitles import generate_ass_content
from story_video.models import (
    AssetType,
    AudioAsset,
    CaptionResult,
    Scene,
    SceneAudioCue,
    SceneStatus,
    StoryHeader,
)
from story_video.pipeline.image_timing import (
    build_word_char_offsets,
    char_position_to_timestamp,
    compute_image_timings,
    validate_image_timings,
)
from story_video.state import ProjectState

__all__ = [
    "assemble_scene",
    "assemble_video",
]

logger = logging.getLogger(__name__)


def _resolve_audio_cues(
    audio_cues: list[SceneAudioCue],
    audio_map: dict[str, AudioAsset],
    captions: CaptionResult,
    source_dir: Path,
) -> list[AudioCueSpec]:
    """Resolve audio cues into FFmpeg-ready AudioCueSpec objects.

    Maps each cue's character position to a timestamp using caption word
    offsets (same bisect approach as image timing). Resolves audio file
    paths relative to source_dir and validates they exist.

    Args:
        audio_cues: Audio cues from the scene.
        audio_map: Audio asset definitions from the story header.
        captions: Whisper caption result with word-level timestamps.
        source_dir: Directory to resolve audio file paths from.

    Returns:
        List of AudioCueSpec objects ready for FFmpeg.

    Raises:
        ValueError: If an audio cue key is not found in the audio map.
        FileNotFoundError: If an audio file doesn't exist.
    """
    scene_duration = captions.duration
    word_char_offsets = build_word_char_offsets(captions)

    specs: list[AudioCueSpec] = []
    for cue in audio_cues:
        if cue.key not in audio_map:
            msg = (
                f"Audio cue key '{cue.key}' not found in story header audio map. "
                f"Available keys: {', '.join(sorted(audio_map.keys())) or 'none'}"
            )
            raise ValueError(msg)
        asset = audio_map[cue.key]

        # Resolve and validate audio file path.
        # Guard against path traversal — audio files must stay within source_dir.
        file_path = (source_dir / asset.file).resolve()
        if not file_path.is_relative_to(source_dir.resolve()):
            msg = f"Audio file path escapes project directory: {asset.file}"
            raise ValueError(msg)
        if not file_path.exists():
            msg = f"Audio file not found: {file_path}"
            raise FileNotFoundError(msg)

        # Compute start time from caption word offsets.
        # Position 0 means "start of scene" — no word alignment needed.
        start_time = 0.0
        if cue.position > 0 and word_char_offsets:
            start_time = char_position_to_timestamp(cue.position, captions, word_char_offsets)

        specs.append(
            AudioCueSpec(
                file_path=file_path,
                start_time=start_time,
                volume=asset.volume,
                loop=asset.loop,
                fade_in=asset.fade_in,
                fade_out=asset.fade_out,
                scene_duration=scene_duration,
            )
        )

    return specs


def assemble_scene(
    scene: Scene, state: ProjectState, *, story_header: StoryHeader | None = None
) -> None:
    """Render a single scene into a video segment.

    For single-image scenes, produces the same output as before.
    For multi-image scenes (from inline image tags), computes caption-aligned
    image timings and builds a crossfade filter graph.

    Args:
        scene: The scene to render.
        state: Project state for config access and persistence.
        story_header: Parsed story header for audio asset resolution, or None.

    Raises:
        FileNotFoundError: If audio, image, or caption JSON file is missing.
        FFmpegError: If FFmpeg exits with a non-zero return code.
        ValueError: If image timings fail validation (display too short).
    """
    config = state.metadata.config
    tts_config = config.tts
    video_config = config.video
    subtitle_config = config.subtitles
    nn = f"{scene.scene_number:03d}"

    # Resolve prerequisite file paths
    ext = tts_config.file_extension
    audio_path = state.project_dir / "audio" / f"scene_{nn}.{ext}"
    caption_json_path = state.project_dir / "captions" / f"scene_{nn}.json"

    # Resolve image paths — one per image prompt (or one default)
    num_images = max(1, len(scene.image_prompts))
    image_paths = [
        state.project_dir / "images" / f"scene_{nn}_{i:03d}.png" for i in range(num_images)
    ]

    # Validate prerequisites
    if not audio_path.exists():
        msg = f"Audio file not found: {audio_path}"
        raise FileNotFoundError(msg)
    for img_path in image_paths:
        if not img_path.exists():
            msg = f"Image file not found: {img_path}"
            raise FileNotFoundError(msg)
    if not caption_json_path.exists():
        msg = f"Caption JSON file not found: {caption_json_path}"
        raise FileNotFoundError(msg)

    # Load caption data
    caption_json = caption_json_path.read_text(encoding="utf-8")
    caption_result = CaptionResult.model_validate_json(caption_json)

    # Resolve audio cues if present
    audio_cue_specs: list[AudioCueSpec] | None = None
    if scene.audio_cues:
        audio_map = story_header.audio if story_header else {}
        audio_cue_specs = _resolve_audio_cues(
            scene.audio_cues,
            audio_map,
            caption_result,
            state.project_dir,
        )

    # Compute image timings
    if len(image_paths) > 1:
        timings = compute_image_timings(scene.image_prompts, caption_result)
        validate_image_timings(
            timings,
            min_display=4.0,
            crossfade_duration=video_config.transition_duration,
        )
        image_timings = [(t.start, t.end) for t in timings]
    else:
        # Sentinel value — _build_single_image_command ignores timings entirely
        # and relies on -shortest to match video length to audio duration.
        image_timings = [(0.0, 0.0)]

    # Generate ASS subtitle content and write to file
    ass_content = generate_ass_content(caption_result, subtitle_config, video_config)
    ass_path = state.project_dir / "captions" / f"scene_{nn}.ass"
    ass_path.write_text(ass_content, encoding="utf-8")

    # Create segments directory
    segments_dir = state.project_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    # Build and run FFmpeg segment command
    output_path = segments_dir / f"scene_{nn}.mp4"
    cmd = build_segment_command(
        image_paths=image_paths,
        image_timings=image_timings,
        audio_path=audio_path,
        ass_path=ass_path,
        output_path=output_path,
        video_config=video_config,
        audio_cues=audio_cue_specs,
    )

    state.update_scene_asset(scene.scene_number, AssetType.VIDEO_SEGMENT, SceneStatus.IN_PROGRESS)
    state.save()

    run_ffmpeg(cmd)

    state.update_scene_asset(scene.scene_number, AssetType.VIDEO_SEGMENT, SceneStatus.COMPLETED)
    state.save()


def assemble_video(state: ProjectState) -> Path:
    """Concatenate all scene segments into the final video.

    Collects completed segment files in scene order, probes each for duration,
    and calls FFmpeg to produce the final video with crossfade transitions.

    Args:
        state: Project state with completed scene segments.

    Returns:
        Path to the final concatenated video (``{project_dir}/final.mp4``).

    Raises:
        FFmpegError: If FFmpeg exits with a non-zero return code.
    """
    video_config = state.metadata.config.video

    # Collect completed segments in scene order
    scenes_sorted = sorted(state.metadata.scenes, key=lambda s: s.scene_number)
    segment_paths: list[Path] = []
    for scene in scenes_sorted:
        if scene.asset_status.video_segment != SceneStatus.COMPLETED:
            continue
        nn = f"{scene.scene_number:03d}"
        segment_path = state.project_dir / "segments" / f"scene_{nn}.mp4"
        segment_paths.append(segment_path)

    if not segment_paths:
        msg = "No completed video segments to assemble"
        raise ValueError(msg)

    # Validate segment files exist
    for path in segment_paths:
        if not path.exists():
            msg = f"Segment file not found: {path}"
            raise FileNotFoundError(msg)

    # Probe durations
    segment_durations: list[float] = []
    for path in segment_paths:
        duration = probe_duration(path)
        segment_durations.append(duration)

    # Build and run concat command
    output_path = state.project_dir / "final.mp4"
    cmd = build_concat_command(
        segment_paths=segment_paths,
        segment_durations=segment_durations,
        output_path=output_path,
        video_config=video_config,
    )
    run_ffmpeg(cmd)

    return output_path
