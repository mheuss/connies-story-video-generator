"""Caption-aligned image timing calculation.

Maps image tag character offsets to Whisper caption timestamps
to determine when each image transition occurs during video assembly.
"""

from bisect import bisect_left
from dataclasses import dataclass

from story_video.models import CaptionResult, SceneImagePrompt

__all__ = [
    "ImageTiming",
    "build_word_char_offsets",
    "char_position_to_timestamp",
    "compute_image_timings",
    "validate_image_timings",
]


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


def build_word_char_offsets(captions: CaptionResult) -> list[int]:
    """Build cumulative character offsets for each caption word.

    Reconstructs character positions by joining words with spaces.
    Used by ``char_position_to_timestamp`` to map inline tag positions
    to audio timestamps.

    Args:
        captions: Whisper caption result with word-level data.

    Returns:
        List of character offsets, one per word.
    """
    offsets: list[int] = []
    char_pos = 0
    for cw in captions.words:
        offsets.append(char_pos)
        char_pos += len(cw.word) + 1  # +1 for space separator
    return offsets


def char_position_to_timestamp(
    position: int,
    captions: CaptionResult,
    word_char_offsets: list[int],
) -> float:
    """Map a character position to the nearest caption word's start time.

    Uses bisect to find the closest word boundary. When the position falls
    between two words, the nearer one wins (left on tie).

    Args:
        position: Character offset in stripped narration text.
        captions: Whisper caption result with word-level timestamps.
        word_char_offsets: Precomputed offsets from ``build_word_char_offsets``.

    Returns:
        Start time in seconds of the nearest caption word.

    Raises:
        ValueError: If *word_char_offsets* is empty.
    """
    if not word_char_offsets:
        msg = (
            "word_char_offsets must not be empty — captions may contain "
            "no words (silent or invalid audio)"
        )
        raise ValueError(msg)
    idx = bisect_left(word_char_offsets, position)
    if idx >= len(word_char_offsets):
        best_idx = len(word_char_offsets) - 1
    elif idx == 0:
        best_idx = 0
    else:
        left_dist = abs(word_char_offsets[idx - 1] - position)
        right_dist = abs(word_char_offsets[idx] - position)
        best_idx = idx - 1 if left_dist <= right_dist else idx
    return captions.words[best_idx].start


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

    word_char_offsets = build_word_char_offsets(captions)

    transition_times = [0.0]
    for prompt in prompts[1:]:
        transition_times.append(
            char_position_to_timestamp(prompt.position, captions, word_char_offsets)
        )

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
