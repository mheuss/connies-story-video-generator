"""Caption-aligned image timing calculation.

Maps image tag character offsets to Whisper caption timestamps
to determine when each image transition occurs during video assembly.
"""

from bisect import bisect_left
from dataclasses import dataclass

from story_video.models import CaptionResult, SceneImagePrompt

__all__ = ["ImageTiming", "compute_image_timings", "validate_image_timings"]


@dataclass(frozen=True)
class ImageTiming:
    """Display window for a single image within a scene.

    Attributes:
        prompt: The image prompt this timing applies to.
        start: Start time in seconds.
        end: End time in seconds.
    """

    prompt: SceneImagePrompt
    start: float
    end: float


def compute_image_timings(
    prompts: list[SceneImagePrompt],
    captions: CaptionResult,
) -> list[ImageTiming]:
    """Compute display windows for each image based on caption timestamps.

    For a single image, it covers the entire scene duration.
    For multiple images, transitions are timed to the nearest word
    boundary after each image tag's character position.

    Args:
        prompts: Image prompts ordered by position.
        captions: Whisper caption result with word-level timestamps.

    Returns:
        List of ImageTiming objects, one per prompt.
    """
    if not prompts:
        return []

    scene_duration = captions.duration

    if len(prompts) == 1:
        return [ImageTiming(prompt=prompts[0], start=0.0, end=scene_duration)]

    # Build cumulative character offsets for caption words.
    # Whisper returns words without position info, so we reconstruct
    # character positions by joining words with spaces.
    word_char_offsets: list[int] = []
    char_pos = 0
    for cw in captions.words:
        word_char_offsets.append(char_pos)
        char_pos += len(cw.word) + 1  # +1 for space separator

    # For each image tag (except the first), find the caption word whose
    # character offset is closest to the tag's position. Use that word's
    # start time as the transition point.
    transition_times = [0.0]
    for prompt in prompts[1:]:
        pos = prompt.position
        idx = bisect_left(word_char_offsets, pos)
        # bisect_left gives the insertion point; compare neighbours to
        # find the closest actual offset.
        if idx >= len(word_char_offsets):
            best_idx = len(word_char_offsets) - 1
        elif idx == 0:
            best_idx = 0
        else:
            left_dist = abs(word_char_offsets[idx - 1] - pos)
            right_dist = abs(word_char_offsets[idx] - pos)
            best_idx = idx - 1 if left_dist <= right_dist else idx
        transition_times.append(captions.words[best_idx].start)

    # Build timing windows
    timings = []
    for i, prompt in enumerate(prompts):
        start = transition_times[i]
        end = transition_times[i + 1] if i + 1 < len(transition_times) else scene_duration
        timings.append(ImageTiming(prompt=prompt, start=start, end=end))

    return timings


def validate_image_timings(
    timings: list[ImageTiming],
    *,
    min_display: float = 4.0,
    crossfade_duration: float = 1.5,
) -> None:
    """Validate that all images display for at least the minimum duration.

    The minimum accounts for the crossfade: an image needs at least
    min_display + crossfade_duration to be visible after the transition.

    A single image has no within-scene crossfades, so validation is
    skipped when there are fewer than two timings.

    Args:
        timings: Image timing windows.
        min_display: Minimum seconds an image must be visible.
        crossfade_duration: Duration of crossfade transitions.

    Raises:
        ValueError: If any image's display window is too short.
    """
    if len(timings) <= 1:
        return  # Single image has no within-scene crossfades to worry about

    required = min_display + crossfade_duration
    for timing in timings:
        display = timing.end - timing.start
        if display < required:
            key = timing.prompt.key or "(auto)"
            msg = (
                f"Scene image '{key}' would display for only {display:.1f}s "
                f"(minimum: {required:.1f}s = {min_display:.1f}s display + "
                f"{crossfade_duration:.1f}s crossfade). "
                f"Move the image tag earlier in the text or remove it."
            )
            raise ValueError(msg)
