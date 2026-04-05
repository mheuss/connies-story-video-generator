"""Tests for caption-aligned image timing calculation."""

import pytest

from story_video.models import CaptionResult, CaptionSegment, CaptionWord, SceneImagePrompt
from story_video.pipeline.image_timing import (
    ImageTiming,
    build_word_char_offsets,
    char_position_to_timestamp,
    compute_image_timings,
    validate_image_timings,
)


def _make_captions(words_data):
    """Build a CaptionResult from (word, start, end) tuples."""
    words = [CaptionWord(word=w, start=s, end=e) for w, s, e in words_data]
    full_text = " ".join(w for w, _, _ in words_data)
    duration = words_data[-1][2]
    return CaptionResult(
        segments=[CaptionSegment(text=full_text, start=0, end=duration)],
        words=words,
        language="en",
        duration=duration,
    )


class TestBuildWordCharOffsets:
    """build_word_char_offsets computes cumulative character positions."""

    def test_basic_offsets(self):
        captions = _make_captions([("The", 0.0, 0.3), ("cat", 0.4, 0.7), ("sat", 0.8, 1.0)])
        offsets = build_word_char_offsets(captions)
        # "The" starts at 0, "cat" at 4 (3 chars + space), "sat" at 8
        assert offsets == [0, 4, 8]

    def test_single_word(self):
        captions = _make_captions([("hello", 0.0, 0.5)])
        assert build_word_char_offsets(captions) == [0]

    def test_empty_captions(self):
        captions = CaptionResult(segments=[], words=[], language="en", duration=0.0)
        assert build_word_char_offsets(captions) == []


class TestCharPositionToTimestamp:
    """char_position_to_timestamp maps character offset to word start time."""

    def test_exact_match(self):
        captions = _make_captions([("The", 0.0, 0.3), ("cat", 0.5, 0.8), ("sat", 1.0, 1.3)])
        offsets = build_word_char_offsets(captions)
        # Position 4 is exactly "cat" → 0.5s
        assert char_position_to_timestamp(4, captions, offsets) == 0.5

    def test_nearest_left_neighbor(self):
        captions = _make_captions([("The", 0.0, 0.3), ("cat", 0.5, 0.8), ("sat", 1.0, 1.3)])
        offsets = build_word_char_offsets(captions)
        # Position 5 is closer to "cat" (offset 4) than "sat" (offset 8)
        assert char_position_to_timestamp(5, captions, offsets) == 0.5

    def test_nearest_right_neighbor(self):
        captions = _make_captions([("The", 0.0, 0.3), ("cat", 0.5, 0.8), ("sat", 1.0, 1.3)])
        offsets = build_word_char_offsets(captions)
        # Position 7 is closer to "sat" (offset 8) than "cat" (offset 4)
        assert char_position_to_timestamp(7, captions, offsets) == 1.0

    def test_position_past_end(self):
        captions = _make_captions([("The", 0.0, 0.3), ("end", 0.5, 0.8)])
        offsets = build_word_char_offsets(captions)
        # Position 100 is past all words → last word
        assert char_position_to_timestamp(100, captions, offsets) == 0.5

    def test_position_zero(self):
        captions = _make_captions([("The", 0.0, 0.3), ("cat", 0.5, 0.8)])
        offsets = build_word_char_offsets(captions)
        assert char_position_to_timestamp(0, captions, offsets) == 0.0

    def test_raises_on_empty_offsets(self):
        """Empty word_char_offsets raises ValueError with diagnostic hint."""
        captions = CaptionResult(duration=1.0, words=[], segments=[], language="en")
        with pytest.raises(ValueError, match="captions may contain no words"):
            char_position_to_timestamp(0, captions, [])


class TestComputeImageTimings:
    """compute_image_timings maps image tag positions to caption timestamps."""

    def test_empty_prompts_returns_empty(self):
        captions = _make_captions([("hello", 0.0, 0.5)])
        assert compute_image_timings([], captions) == []

    def test_single_image_covers_full_duration(self):
        captions = _make_captions([("hello", 0.0, 0.5), ("world", 0.6, 1.0)])
        prompts = [SceneImagePrompt(key=None, prompt="A prompt", position=0)]
        timings = compute_image_timings(prompts, captions)
        assert len(timings) == 1
        assert timings[0].start == 0.0
        assert timings[0].end == 1.0

    def test_two_images_split_at_tag_position(self):
        captions = _make_captions(
            [
                ("The", 0.0, 0.3),
                ("keeper", 0.4, 0.8),
                ("climbed", 0.9, 1.4),
                ("Below", 1.5, 1.9),
                ("the", 2.0, 2.2),
                ("boats", 2.3, 2.7),
                ("rocked", 2.8, 3.2),
            ]
        )
        prompts = [
            SceneImagePrompt(key="lighthouse", prompt="A lighthouse", position=0),
            SceneImagePrompt(key="harbor", prompt="A harbor", position=20),
        ]
        timings = compute_image_timings(prompts, captions)
        assert len(timings) == 2
        assert timings[0].start == 0.0
        assert timings[1].end == 3.2
        # Second image starts after "climbed" (position ~20 maps to "Below" at 1.5s)
        assert timings[1].start > 1.0
        assert timings[0].end == timings[1].start

    def test_three_images(self):
        captions = _make_captions(
            [
                ("word1", 0.0, 1.0),
                ("word2", 1.0, 2.0),
                ("word3", 2.0, 3.0),
                ("word4", 3.0, 4.0),
                ("word5", 4.0, 5.0),
                ("word6", 5.0, 6.0),
            ]
        )
        prompts = [
            SceneImagePrompt(key="a", prompt="A", position=0),
            SceneImagePrompt(key="b", prompt="B", position=12),
            SceneImagePrompt(key="c", prompt="C", position=24),
        ]
        timings = compute_image_timings(prompts, captions)
        assert len(timings) == 3
        assert timings[0].start == 0.0
        assert timings[2].end == 6.0
        # Each image has a contiguous window
        assert timings[0].end == timings[1].start
        assert timings[1].end == timings[2].start


class TestValidateImageTimings:
    """validate_image_timings raises on images that display too briefly."""

    def test_valid_timings_pass(self):
        timings = [
            ImageTiming(
                prompt=SceneImagePrompt(key="a", prompt="A", position=0),
                start=0.0,
                end=15.0,
            ),
            ImageTiming(
                prompt=SceneImagePrompt(key="b", prompt="B", position=50),
                start=15.0,
                end=30.0,
            ),
        ]
        validate_image_timings(timings, min_display=4.0, crossfade_duration=1.5)

    def test_short_image_raises(self):
        timings = [
            ImageTiming(
                prompt=SceneImagePrompt(key="a", prompt="A", position=0),
                start=0.0,
                end=28.0,
            ),
            ImageTiming(
                prompt=SceneImagePrompt(key="b", prompt="B", position=50),
                start=28.0,
                end=30.0,
            ),
        ]
        with pytest.raises(ValueError, match="2.0s"):
            validate_image_timings(timings, min_display=4.0, crossfade_duration=1.5)

    def test_single_image_no_validation_needed(self):
        timings = [
            ImageTiming(
                prompt=SceneImagePrompt(key=None, prompt="A", position=0),
                start=0.0,
                end=2.0,
            ),
        ]
        # Single image with short duration is fine -- no crossfade to account for
        validate_image_timings(timings, min_display=4.0, crossfade_duration=1.5)

    def test_empty_timings_pass(self):
        validate_image_timings([], min_display=4.0, crossfade_duration=1.5)
