"""FFmpeg command building and execution.

Provides functions to build FFmpeg command-line arguments for rendering
individual scene segments, concatenating segments with crossfade transitions,
and executing FFmpeg/ffprobe as subprocesses.

Public items:
    FFmpegError: Custom exception for FFmpeg failures.
    run_ffmpeg: Execute an FFmpeg command with error handling.
    build_segment_command: Build command for a single scene segment.
    build_concat_command: Build command for concatenating segments with crossfades.
    probe_duration: Extract media duration via ffprobe.
"""

import logging
import subprocess
from pathlib import Path

from story_video.ffmpeg.filters import blur_background_filter, still_image_filter
from story_video.ffmpeg.subtitles import subtitle_filter
from story_video.models import VideoConfig

logger = logging.getLogger(__name__)

__all__ = [
    "FFmpegError",
    "build_concat_command",
    "build_segment_command",
    "probe_duration",
    "run_ffmpeg",
]


class FFmpegError(Exception):
    """Raised when an FFmpeg or ffprobe subprocess exits with a non-zero code.

    Attributes:
        cmd: The full command that was executed.
        returncode: The process exit code.
        stderr: The stderr output from FFmpeg.
    """

    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"FFmpeg failed (exit {returncode})\nCommand: {' '.join(cmd)}\nStderr: {stderr}"
        )


def run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    """Execute an FFmpeg command and return the result.

    Args:
        cmd: Full command as a list of strings (e.g. ["ffmpeg", "-i", ...]).

    Returns:
        The CompletedProcess on success.

    Raises:
        FFmpegError: If the process exits with a non-zero return code.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        raise FFmpegError(cmd=cmd, returncode=result.returncode, stderr=result.stderr)
    return result


def build_segment_command(
    image_path: Path,
    audio_path: Path,
    ass_path: Path,
    output_path: Path,
    video_config: VideoConfig,
) -> list[str]:
    """Build an FFmpeg command for rendering a single scene segment.

    Produces a single-pass filtergraph that combines:
    - Blurred background layer from the scene image
    - Still image scaled and centered on the background
    - Subtitle burn-in from an ASS file

    Audio is muxed directly from the audio file. The ``-shortest`` flag
    ensures the segment length matches the audio duration.

    Args:
        image_path: Path to the scene image file.
        audio_path: Path to the scene audio file.
        ass_path: Path to the ASS subtitle file.
        output_path: Path for the output segment video.
        video_config: Video configuration parameters.

    Returns:
        FFmpeg command as a list of strings.
    """
    bg_filter = blur_background_filter(
        blur_radius=video_config.background_blur_radius,
        resolution=video_config.resolution,
    )
    sub_filter = subtitle_filter(ass_path)
    fg_filter = still_image_filter(video_config.resolution)

    filtergraph = (
        f"[0:v]{bg_filter}[bg];"
        f"[0:v]{fg_filter}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]{sub_filter}[out]"
    )

    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        filtergraph,
        "-map",
        "[out]",
        "-map",
        "1:a",
        "-c:v",
        video_config.codec,
        "-crf",
        str(video_config.crf),
        "-r",
        str(video_config.fps),
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(output_path),
    ]


def build_concat_command(
    segment_paths: list[Path],
    segment_durations: list[float],
    output_path: Path,
    video_config: VideoConfig,
) -> list[str]:
    """Build an FFmpeg command for concatenating segments with crossfade transitions.

    For multiple segments, chains N-1 xfade filters for video and acrossfade
    filters for audio. Adds fade-in at the start and fade-out at the end.

    For a single segment, applies only fade-in and fade-out (no xfade).

    Args:
        segment_paths: Ordered list of segment video file paths.
        segment_durations: Duration of each segment in seconds.
        output_path: Path for the final concatenated video.
        video_config: Video configuration parameters.

    Returns:
        FFmpeg command as a list of strings.

    Raises:
        ValueError: If segment_paths is empty or if segment_paths and
            segment_durations have different lengths.
    """
    if not segment_paths:
        msg = "segment_paths must contain at least one segment"
        raise ValueError(msg)

    if len(segment_paths) != len(segment_durations):
        msg = (
            f"segment_paths ({len(segment_paths)}) and "
            f"segment_durations ({len(segment_durations)}) must have the same length"
        )
        raise ValueError(msg)

    n = len(segment_paths)
    transition_dur = video_config.transition_duration
    audio_transition_dur = video_config.audio_transition_duration
    fade_in_dur = video_config.fade_in_duration
    fade_out_dur = video_config.fade_out_duration

    # Build input arguments
    inputs: list[str] = []
    for path in segment_paths:
        inputs.extend(["-i", str(path)])

    if n == 1:
        # Single segment: fade in/out only
        total_dur = segment_durations[0]
        fade_out_start = max(0.0, total_dur - fade_out_dur)
        filtergraph = (
            f"[0:v]fade=t=in:st=0:d={fade_in_dur},"
            f"fade=t=out:st={fade_out_start}:d={fade_out_dur}[outv];"
            f"[0:a]afade=t=in:st=0:d={fade_in_dur},"
            f"afade=t=out:st={fade_out_start}:d={fade_out_dur}[outa]"
        )
    else:
        # Multiple segments: chain xfade transitions
        video_parts: list[str] = []
        audio_parts: list[str] = []

        # Calculate xfade offsets:
        # offset_i = sum(durations[0..i]) - i * transition_dur
        # Each xfade takes two streams and produces one.
        cumulative_dur = 0.0
        prev_video_label = "[0:v]"
        prev_audio_label = "[0:a]"

        for i in range(n - 1):
            cumulative_dur += segment_durations[i]
            raw_offset = cumulative_dur - (i + 1) * transition_dur
            offset = max(0.0, raw_offset)
            if raw_offset < 0:
                logger.warning(
                    "Segment %d duration (%.2fs) is shorter than transition_duration (%.2fs); "
                    "xfade offset clamped from %.2f to 0.0",
                    i,
                    segment_durations[i],
                    transition_dur,
                    raw_offset,
                )
            next_video = f"[{i + 1}:v]"
            next_audio = f"[{i + 1}:a]"

            out_video = f"[xf{i}]"
            out_audio = f"[axf{i}]"

            video_parts.append(
                f"{prev_video_label}{next_video}"
                f"xfade=transition=fade:duration={transition_dur}:offset={offset}"
                f"{out_video}"
            )
            audio_parts.append(
                f"{prev_audio_label}{next_audio}acrossfade=d={audio_transition_dur}{out_audio}"
            )

            prev_video_label = out_video
            prev_audio_label = out_audio

        # Add final duration for fade calculation
        cumulative_dur += segment_durations[-1]
        total_dur = max(0.0, cumulative_dur - (n - 1) * transition_dur)
        fade_out_start = max(0.0, total_dur - fade_out_dur)

        # Fade in/out on the final composited stream
        video_parts.append(
            f"{prev_video_label}"
            f"fade=t=in:st=0:d={fade_in_dur},"
            f"fade=t=out:st={fade_out_start}:d={fade_out_dur}[outv]"
        )
        audio_parts.append(
            f"{prev_audio_label}"
            f"afade=t=in:st=0:d={fade_in_dur},"
            f"afade=t=out:st={fade_out_start}:d={fade_out_dur}[outa]"
        )

        filtergraph = ";".join(video_parts + audio_parts)

    return [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filtergraph,
        "-map",
        "[outv]",
        "-map",
        "[outa]",
        "-c:v",
        video_config.codec,
        "-crf",
        str(video_config.crf),
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]


def probe_duration(path: Path) -> float:
    """Extract media duration in seconds via ffprobe.

    Args:
        path: Path to the media file.

    Returns:
        Duration as a float in seconds.

    Raises:
        FFmpegError: If ffprobe fails or returns non-numeric output.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        raise FFmpegError(cmd=cmd, returncode=result.returncode, stderr=result.stderr)
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise FFmpegError(
            cmd=cmd,
            returncode=0,
            stderr=f"ffprobe returned non-numeric duration '{raw}' for {path}",
        ) from exc
