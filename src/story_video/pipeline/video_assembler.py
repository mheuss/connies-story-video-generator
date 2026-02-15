"""Video assembly orchestration for scene rendering and final concatenation.

Provides two public functions:
    assemble_scene: Render a single scene into a video segment (image + audio + subtitles).
    assemble_video: Concatenate all scene segments into the final video with crossfade transitions.

Both functions delegate to ``story_video.ffmpeg.commands`` for FFmpeg execution
and ``story_video.ffmpeg.subtitles`` for ASS subtitle generation.
"""

from pathlib import Path

from story_video.ffmpeg.commands import (
    build_concat_command,
    build_segment_command,
    probe_duration,
    run_ffmpeg,
)
from story_video.ffmpeg.subtitles import generate_ass_content
from story_video.models import AssetType, Scene, SceneStatus
from story_video.pipeline.caption_generator import CaptionResult
from story_video.state import ProjectState

__all__ = [
    "assemble_scene",
    "assemble_video",
]


def assemble_scene(scene: Scene, state: ProjectState) -> None:
    """Render a single scene into a video segment.

    Validates that all prerequisite files exist (audio, image, caption JSON),
    generates ASS subtitles, and calls FFmpeg to produce a video segment
    combining the image, audio, and burned-in subtitles.

    Does NOT mark the scene as IN_PROGRESS — that is the orchestrator's
    responsibility.

    Args:
        scene: The scene to render.
        state: Project state for config access and persistence.

    Raises:
        FileNotFoundError: If audio, image, or caption JSON file is missing.
        FFmpegError: If FFmpeg exits with a non-zero return code.
    """
    config = state.metadata.config
    tts_config = config.tts
    video_config = config.video
    subtitle_config = config.subtitles
    nn = f"{scene.scene_number:02d}"

    # Resolve prerequisite file paths
    audio_path = state.project_dir / "audio" / f"scene_{nn}.{tts_config.output_format}"
    image_path = state.project_dir / "images" / f"scene_{nn}.png"
    caption_json_path = state.project_dir / "captions" / f"scene_{nn}.json"

    # Validate prerequisites
    if not audio_path.exists():
        msg = f"Audio file not found: {audio_path}"
        raise FileNotFoundError(msg)
    if not image_path.exists():
        msg = f"Image file not found: {image_path}"
        raise FileNotFoundError(msg)
    if not caption_json_path.exists():
        msg = f"Caption JSON file not found: {caption_json_path}"
        raise FileNotFoundError(msg)

    # Load caption data
    caption_json = caption_json_path.read_text(encoding="utf-8")
    caption_result = CaptionResult.model_validate_json(caption_json)

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
        image_path=image_path,
        audio_path=audio_path,
        ass_path=ass_path,
        output_path=output_path,
        duration=caption_result.duration,
        scene_number=scene.scene_number,
        video_config=video_config,
    )
    run_ffmpeg(cmd)

    # Update state
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

    # Collect segments in scene order
    scenes_sorted = sorted(state.metadata.scenes, key=lambda s: s.scene_number)
    segment_paths: list[Path] = []
    for scene in scenes_sorted:
        nn = f"{scene.scene_number:02d}"
        segment_path = state.project_dir / "segments" / f"scene_{nn}.mp4"
        segment_paths.append(segment_path)

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
