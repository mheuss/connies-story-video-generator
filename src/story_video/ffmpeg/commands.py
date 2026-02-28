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
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from story_video.ffmpeg.filters import blur_background_filter, still_image_filter
from story_video.ffmpeg.subtitles import subtitle_filter
from story_video.models import VideoConfig

logger = logging.getLogger(__name__)

__all__ = [
    "AudioCueSpec",
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
            f"FFmpeg failed (exit {returncode})\nCommand: {shlex.join(cmd)}\nStderr: {stderr}"
        )


@dataclass(frozen=True)
class AudioCueSpec:
    """Parameters for mixing a single music/SFX track into a scene.

    Attributes:
        file_path: Path to the audio file.
        start_time: When to start playing in seconds.
        volume: Playback volume (0.0-1.0).
        loop: Whether to loop the audio.
        fade_in: Fade-in duration in seconds.
        fade_out: Fade-out duration in seconds.
        scene_duration: Total scene duration for looping/trimming.
    """

    file_path: Path
    start_time: float
    volume: float
    loop: bool
    fade_in: float
    fade_out: float
    scene_duration: float


def _build_audio_mix_filters(
    cues: list[AudioCueSpec],
    *,
    narration_label: str,
    first_cue_index: int,
) -> tuple[list[str], str]:
    """Build FFmpeg filter chain for mixing music/SFX tracks with narration.

    Each cue becomes a filter chain: adelay -> volume -> [aloop] -> [afade].
    All processed tracks are combined with the narration using amix.

    Args:
        cues: Audio cue specifications.
        narration_label: FFmpeg stream label for narration audio (e.g. "[1:a]").
        first_cue_index: FFmpeg input index of the first music file.

    Returns:
        Tuple of (filter parts list, output stream label).
        If no cues, returns ([], narration_label).
    """
    if not cues:
        return [], narration_label

    filter_parts: list[str] = []
    cue_labels: list[str] = []

    for i, cue in enumerate(cues):
        input_index = first_cue_index + i
        input_label = f"[{input_index}:a]"
        output_label = f"[mus{i}]"
        cue_labels.append(output_label)

        remaining = cue.scene_duration - cue.start_time

        # Build the comma-separated filter chain for this cue
        chain: list[str] = []

        # adelay: offset start time in milliseconds (both channels)
        if cue.start_time > 0:
            delay_ms = int(cue.start_time * 1000)
            chain.append(f"adelay={delay_ms}|{delay_ms}")

        # volume: scale the track level
        chain.append(f"volume={cue.volume}")

        # aloop + atrim: loop the audio and trim to remaining scene duration
        if cue.loop:
            chain.append("aloop=loop=-1:size=2e+09")
            chain.append(f"atrim=0:{remaining}")

        # afade: fade in and/or fade out
        if cue.fade_in > 0:
            chain.append(f"afade=t=in:st=0:d={cue.fade_in}")
        if cue.fade_out > 0:
            fade_out_start = remaining - cue.fade_out
            if fade_out_start < 0:
                logger.warning(
                    "Music cue %d fade_out (%.2fs) exceeds remaining duration (%.2fs); "
                    "fade_out_start clamped to 0.0",
                    i,
                    cue.fade_out,
                    remaining,
                )
                fade_out_start = 0.0
            chain.append(f"afade=t=out:st={fade_out_start}:d={cue.fade_out}")

        filter_parts.append(f"{input_label}{','.join(chain)}{output_label}")

    # amix: combine narration + all cue tracks
    num_inputs = 1 + len(cues)  # narration + cues
    all_labels = narration_label + "".join(cue_labels)
    amix_label = "[amix]"
    filter_parts.append(
        f"{all_labels}amix=inputs={num_inputs}:duration=first:dropout_transition=0{amix_label}"
    )

    return filter_parts, amix_label


def run_ffmpeg(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    """Execute an FFmpeg command and return the result.

    Args:
        cmd: Full command as a list of strings (e.g. ["ffmpeg", "-i", ...]).
        timeout: Maximum seconds to wait before killing the process.

    Returns:
        The CompletedProcess on success.

    Raises:
        FFmpegError: If the process exits with a non-zero return code or
            exceeds the timeout.
    """
    try:
        # cmd is built programmatically from validated config; shell=False (default)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # noqa: S603
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(
            cmd=cmd, returncode=-1, stderr=f"Process timed out after {timeout}s"
        ) from exc
    if result.returncode != 0:
        raise FFmpegError(cmd=cmd, returncode=result.returncode, stderr=result.stderr)
    return result


def build_segment_command(
    image_paths: list[Path],
    image_timings: list[tuple[float, float]],
    audio_path: Path,
    ass_path: Path,
    output_path: Path,
    video_config: VideoConfig,
    audio_cues: list[AudioCueSpec] | None = None,
) -> list[str]:
    """Build an FFmpeg command for rendering a single scene segment.

    For a single image, produces a single-pass filtergraph that combines:
    - Blurred background layer from the scene image
    - Still image scaled and centered on the background
    - Subtitle burn-in from an ASS file
    Audio is muxed directly. The ``-shortest`` flag ensures the segment
    length matches the audio duration.

    For multiple images, produces a filtergraph that:
    - Creates a blur+foreground composite for each image
    - Chains composites with xfade crossfade transitions
    - Burns subtitles on the final composited stream
    Each image input is looped and trimmed to its display duration.
    No ``-shortest`` flag; durations are pre-calculated.

    Args:
        image_paths: Ordered list of image file paths (at least one).
        image_timings: List of ``(start_time, end_time)`` tuples, one per image.
        audio_path: Path to the scene audio file.
        ass_path: Path to the ASS subtitle file.
        output_path: Path for the output segment video.
        video_config: Video configuration parameters.
        audio_cues: Optional list of music/SFX tracks to mix with narration.

    Returns:
        FFmpeg command as a list of strings.

    Raises:
        ValueError: If image_paths is empty or if image_paths and
            image_timings have different lengths.
    """
    if not image_paths:
        msg = "image_paths must contain at least one image"
        raise ValueError(msg)
    if len(image_paths) != len(image_timings):
        msg = (
            f"image_paths ({len(image_paths)}) and "
            f"image_timings ({len(image_timings)}) must have the same length"
        )
        raise ValueError(msg)

    bg_filter = blur_background_filter(
        blur_radius=video_config.background_blur_radius,
        resolution=video_config.resolution,
    )
    sub_filter = subtitle_filter(ass_path)
    fg_filter = still_image_filter(video_config.resolution)

    if len(image_paths) == 1:
        return _build_single_image_command(
            image_path=image_paths[0],
            audio_path=audio_path,
            output_path=output_path,
            video_config=video_config,
            bg_filter=bg_filter,
            fg_filter=fg_filter,
            sub_filter=sub_filter,
            audio_cues=audio_cues,
        )

    return _build_multi_image_command(
        image_paths=image_paths,
        image_timings=image_timings,
        audio_path=audio_path,
        output_path=output_path,
        video_config=video_config,
        bg_filter=bg_filter,
        fg_filter=fg_filter,
        sub_filter=sub_filter,
        audio_cues=audio_cues,
    )


def _build_single_image_command(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    video_config: VideoConfig,
    bg_filter: str,
    fg_filter: str,
    sub_filter: str,
    audio_cues: list[AudioCueSpec] | None = None,
) -> list[str]:
    """Build segment command for a single image (original behavior)."""
    # FFmpeg auto-splits [0:v] into two branches: one for the blurred background
    # (scale-to-cover + crop + blur) and one for the sharp foreground (scale-to-fit).
    # The two branches are overlaid, then subtitles are burned in.
    filtergraph = (
        f"[0:v]{bg_filter}[bg];"
        f"[0:v]{fg_filter}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
        f"[comp]{sub_filter}[out]"
    )

    # Narration audio is input 1 (input 0 is the looped image).
    # Music files start at input index 2.
    audio_map = "1:a"
    music_inputs: list[str] = []

    if audio_cues:
        for cue in audio_cues:
            music_inputs.extend(["-i", str(cue.file_path)])
        audio_filter_parts, audio_label = _build_audio_mix_filters(
            audio_cues, narration_label="[1:a]", first_cue_index=2
        )
        filtergraph += ";" + ";".join(audio_filter_parts)
        audio_map = audio_label

    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        *music_inputs,
        "-filter_complex",
        filtergraph,
        "-map",
        "[out]",
        "-map",
        audio_map,
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


def _build_multi_image_command(
    image_paths: list[Path],
    image_timings: list[tuple[float, float]],
    audio_path: Path,
    output_path: Path,
    video_config: VideoConfig,
    bg_filter: str,
    fg_filter: str,
    sub_filter: str,
    audio_cues: list[AudioCueSpec] | None = None,
) -> list[str]:
    """Build segment command for multiple images with xfade transitions."""
    n = len(image_paths)
    transition_dur = video_config.transition_duration

    # Build input arguments: each image looped and trimmed to its duration
    inputs: list[str] = []
    durations: list[float] = []
    for i, (img_path, (start, end)) in enumerate(zip(image_paths, image_timings)):
        raw_dur = end - start
        dur = max(0.0, raw_dur)
        if raw_dur < 0:
            logger.warning(
                "Image %d duration is negative (%.2fs); clamped to 0.0",
                i,
                raw_dur,
            )
        durations.append(dur)
        inputs.extend(["-loop", "1", "-t", str(dur), "-i", str(img_path)])

    # Audio is the last input (index N)
    audio_index = n
    inputs.extend(["-i", str(audio_path)])

    # Music files start after the audio input
    music_inputs: list[str] = []
    if audio_cues:
        for cue in audio_cues:
            music_inputs.extend(["-i", str(cue.file_path)])

    # Build per-image blur+foreground composites
    filter_parts: list[str] = []
    for i in range(n):
        filter_parts.append(f"[{i}:v]{bg_filter}[bg{i}]")
        filter_parts.append(f"[{i}:v]{fg_filter}[fg{i}]")
        filter_parts.append(f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2[comp{i}]")

    # Chain composites with xfade transitions
    prev_label = "[comp0]"
    for i in range(n - 1):
        offset = max(0.0, durations[i] - transition_dur)
        if i > 0:
            # After first xfade, offset is relative to accumulated timeline.
            # The accumulated output duration after xfade i-1 is:
            # sum(durations[0..i]) - i * transition_dur
            # The next xfade offset is that minus transition_dur from the
            # start of the next image, which is:
            # sum(durations[0..i]) - i * transition_dur - transition_dur
            # = sum(durations[0..i]) - (i+1) * transition_dur
            cumulative = sum(durations[: i + 1])
            offset = max(0.0, cumulative - (i + 1) * transition_dur)

        out_label = f"[xf{i}]"
        filter_parts.append(
            f"{prev_label}[comp{i + 1}]"
            f"xfade=transition=fade:duration={transition_dur}:offset={offset}"
            f"{out_label}"
        )
        prev_label = out_label

    # Burn subtitles on the final composited stream
    filter_parts.append(f"{prev_label}{sub_filter}[out]")

    # Mix audio cues with narration if present
    audio_map = f"{audio_index}:a"
    if audio_cues:
        audio_filter_parts, audio_label = _build_audio_mix_filters(
            audio_cues,
            narration_label=f"[{audio_index}:a]",
            first_cue_index=audio_index + 1,
        )
        filter_parts.extend(audio_filter_parts)
        audio_map = audio_label

    filtergraph = ";".join(filter_parts)

    return [
        "ffmpeg",
        "-y",
        *inputs,
        *music_inputs,
        "-filter_complex",
        filtergraph,
        "-map",
        "[out]",
        "-map",
        audio_map,
        "-c:v",
        video_config.codec,
        "-crf",
        str(video_config.crf),
        "-r",
        str(video_config.fps),
        "-pix_fmt",
        "yuv420p",
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

    Note:
        If a segment duration is shorter than the transition duration,
        the xfade offset is clamped to 0.0 and a warning is logged.
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
    end_hold = video_config.end_hold_duration
    lead_in = video_config.lead_in_duration

    # Build input arguments
    inputs: list[str] = []
    for path in segment_paths:
        inputs.extend(["-i", str(path)])

    # Ensure the end hold is at least as long as the fade-out so the
    # fade never overlaps narration audio.
    effective_hold = max(end_hold, fade_out_dur)

    if n == 1:
        # Single segment: fade in/out only.
        # Add lead_in so the image can fade in before narration starts,
        # and effective_hold so the last frame lingers through the fade-out.
        total_dur = lead_in + segment_durations[0] + effective_hold
        # Clamp fades so they don't exceed half the total duration
        fade_in_dur = min(fade_in_dur, total_dur / 2)
        fade_out_dur = min(fade_out_dur, total_dur / 2)
        fade_out_start = max(0.0, total_dur - fade_out_dur)

        lead_in_video = f"tpad=start_mode=clone:start_duration={lead_in}," if lead_in > 0 else ""
        lead_in_ms = int(lead_in * 1000)
        lead_in_audio = f"adelay={lead_in_ms}|{lead_in_ms}," if lead_in > 0 else ""

        end_hold_video = (
            f"tpad=stop_mode=clone:stop_duration={effective_hold}," if effective_hold > 0 else ""
        )
        end_hold_audio = f"apad=pad_dur={effective_hold}," if effective_hold > 0 else ""

        filtergraph = (
            f"[0:v]{lead_in_video}{end_hold_video}"
            f"fade=t=in:st=0:d={fade_in_dur},"
            f"fade=t=out:st={fade_out_start}:d={fade_out_dur}[outv];"
            f"[0:a]{lead_in_audio}{end_hold_audio}"
            f"afade=t=in:st=0:d={fade_in_dur},"
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
        actual_offsets: list[float] = []
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
            actual_offsets.append(offset)
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

        # Video xfade compresses by (n-1)*transition_dur, but audio acrossfade
        # only compresses by (n-1)*audio_transition_dur. When transition_dur >>
        # audio_transition_dur the video stream ends before the narrator finishes.
        # Pad the video with repeated last frame so both streams have equal length,
        # plus end_hold so the last frame lingers before the fade-out.
        last_offset = actual_offsets[-1] if actual_offsets else 0.0
        video_total = max(0.0, last_offset + segment_durations[-1])
        audio_total = max(0.0, sum(segment_durations) - (n - 1) * audio_transition_dur)

        # Pad video to match audio + effective_hold; pad audio with silence.
        video_pad = audio_total - video_total + effective_hold
        if video_pad > 0:
            pad_label = "[vpad]"
            video_parts.append(
                f"{prev_video_label}tpad=stop_mode=clone:stop_duration={video_pad}{pad_label}"
            )
            prev_video_label = pad_label
        if effective_hold > 0:
            hold_label = "[ahold]"
            audio_parts.append(f"{prev_audio_label}apad=pad_dur={effective_hold}{hold_label}")
            prev_audio_label = hold_label

        # Lead-in: pad video at start (clone first frame) and delay audio.
        if lead_in > 0:
            lead_label_v = "[vlead]"
            video_parts.append(
                f"{prev_video_label}tpad=start_mode=clone:start_duration={lead_in}{lead_label_v}"
            )
            prev_video_label = lead_label_v

            lead_label_a = "[alead]"
            lead_in_ms = int(lead_in * 1000)
            audio_parts.append(f"{prev_audio_label}adelay={lead_in_ms}|{lead_in_ms}{lead_label_a}")
            prev_audio_label = lead_label_a

        # Use lead_in + audio_total + effective_hold for both fades.
        total_dur = lead_in + audio_total + effective_hold
        fade_in_dur = min(fade_in_dur, total_dur / 2)
        fade_out_dur = min(fade_out_dur, total_dur / 2)
        fade_out_start = max(0.0, total_dur - fade_out_dur)

        # Fade in/out on the final composited stream. xfade produces a single
        # output whose timeline starts at 0, so st=0 correctly targets the video start.
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
        "-r",
        str(video_config.fps),
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
    result = run_ffmpeg(cmd, timeout=30)
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise FFmpegError(
            cmd=cmd,
            returncode=0,
            stderr=f"ffprobe returned non-numeric duration '{raw}' for {path}",
        ) from exc
