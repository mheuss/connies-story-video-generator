"""Tests for story_video.cost -- Cost estimation logic.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the cost estimation module.
"""

import math

import pytest

from story_video.cost import (
    CostEstimate,
    ServiceCost,
    estimate_cost,
    format_cost_estimate,
)
from story_video.models import AppConfig, ImageConfig, InputMode, StoryConfig, TTSConfig

# ---------------------------------------------------------------------------
# Helpers — build configs with specific overrides
# ---------------------------------------------------------------------------


def _config(**overrides) -> AppConfig:
    """Build an AppConfig with optional sub-config overrides.

    Accepts keyword arguments matching AppConfig sub-config names.
    Example: _config(tts=TTSConfig(model="tts-1"))
    """
    return AppConfig(**overrides)


# ---------------------------------------------------------------------------
# ServiceCost data class
# ---------------------------------------------------------------------------


class TestServiceCost:
    """ServiceCost frozen dataclass -- single service cost entry."""

    def test_creates_with_required_fields(self):
        sc = ServiceCost(service="TTS", description="tts-1-hd", low=7.41, high=7.41)
        assert sc.service == "TTS"
        assert sc.description == "tts-1-hd"
        assert sc.low == 7.41
        assert sc.high == 7.41

    def test_is_frozen(self):
        sc = ServiceCost(service="TTS", description="tts-1-hd", low=7.41, high=7.41)
        with pytest.raises(AttributeError):
            sc.low = 0.0  # type: ignore[misc]

    def test_exact_cost_has_equal_low_and_high(self):
        sc = ServiceCost(service="Whisper", description="captions", low=0.18, high=0.18)
        assert sc.low == sc.high


# ---------------------------------------------------------------------------
# CostEstimate data class
# ---------------------------------------------------------------------------


class TestCostEstimate:
    """CostEstimate frozen dataclass -- complete cost breakdown."""

    def test_total_low_sums_service_lows(self):
        services = [
            ServiceCost(service="A", description="a", low=1.0, high=2.0),
            ServiceCost(service="B", description="b", low=3.0, high=5.0),
        ]
        ce = CostEstimate(
            mode=InputMode.ORIGINAL,
            duration_minutes=30,
            scene_count=25,
            character_count=247500,
            services=services,
        )
        assert ce.total_low == pytest.approx(4.0)

    def test_total_high_sums_service_highs(self):
        services = [
            ServiceCost(service="A", description="a", low=1.0, high=2.0),
            ServiceCost(service="B", description="b", low=3.0, high=5.0),
        ]
        ce = CostEstimate(
            mode=InputMode.ORIGINAL,
            duration_minutes=30,
            scene_count=25,
            character_count=247500,
            services=services,
        )
        assert ce.total_high == pytest.approx(7.0)

    def test_is_frozen(self):
        ce = CostEstimate(
            mode=InputMode.ORIGINAL,
            duration_minutes=30,
            scene_count=25,
            character_count=247500,
            services=[],
        )
        with pytest.raises(AttributeError):
            ce.scene_count = 10  # type: ignore[misc]

    def test_empty_services_total_is_zero(self):
        ce = CostEstimate(
            mode=InputMode.ORIGINAL,
            duration_minutes=30,
            scene_count=25,
            character_count=247500,
            services=[],
        )
        assert ce.total_low == 0.0
        assert ce.total_high == 0.0


# ---------------------------------------------------------------------------
# Scene count formula
# ---------------------------------------------------------------------------


class TestSceneCountFormula:
    """Scene count = ceil(target_duration_minutes * words_per_minute / scene_word_target)."""

    def test_default_config_yields_3_scenes(self):
        """30 min * 150 wpm / 1800 words = 2.5, ceil -> 3 scenes."""
        config = _config()
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.scene_count == math.ceil(30 * 150 / 1800)  # 3

    def test_60_minutes_yields_5_scenes(self):
        """60 min * 150 wpm / 1800 = 5.0, ceil -> 5 scenes."""
        config = _config(story=StoryConfig(target_duration_minutes=60))
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.scene_count == 5

    def test_non_integer_result_rounds_up(self):
        """45 min * 150 wpm / 1800 = 3.75, ceil -> 4 scenes."""
        config = _config(story=StoryConfig(target_duration_minutes=45))
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.scene_count == 4

    def test_custom_wpm_and_word_target(self):
        """20 min * 120 wpm / 600 = 4.0, ceil -> 4 scenes."""
        config = _config(
            story=StoryConfig(
                target_duration_minutes=20,
                words_per_minute=120,
                scene_word_target=600,
            )
        )
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.scene_count == 4

    def test_1_minute_duration(self):
        """1 min * 150 wpm / 1800 = 0.083..., ceil -> 1 scene (minimum)."""
        config = _config(story=StoryConfig(target_duration_minutes=1))
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.scene_count == 1


# ---------------------------------------------------------------------------
# Character count formula
# ---------------------------------------------------------------------------


class TestCharacterCountFormula:
    """character_count = scene_count * scene_word_target * 5.5."""

    def test_default_config_character_count(self):
        """3 scenes * 1800 words * 5.5 = 29700 chars."""
        config = _config()
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        expected_scenes = math.ceil(30 * 150 / 1800)  # 3
        assert est.character_count == int(expected_scenes * 1800 * 5.5)

    def test_custom_word_target_character_count(self):
        """4 scenes * 600 words * 5.5 = 13200 chars."""
        config = _config(
            story=StoryConfig(
                target_duration_minutes=20,
                words_per_minute=120,
                scene_word_target=600,
            )
        )
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.character_count == int(4 * 600 * 5.5)


# ---------------------------------------------------------------------------
# Actual mode (providing scene_count and character_count directly)
# ---------------------------------------------------------------------------


class TestActualMode:
    """When scene_count and character_count are provided, use them directly."""

    def test_uses_provided_scene_count(self):
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        assert est.scene_count == 25
        assert est.character_count == 247500
        assert est.duration_minutes == 30


# ---------------------------------------------------------------------------
# Claude API cost
# ---------------------------------------------------------------------------


class TestClaudeCost:
    """Claude API cost varies by mode, scales linearly with scene count."""

    @pytest.mark.parametrize(
        "mode,expected_low,expected_high",
        [
            (InputMode.ORIGINAL, 2.00, 5.00),
            (InputMode.INSPIRED_BY, 2.00, 5.00),
            (InputMode.ADAPT, 0.20, 0.50),
        ],
        ids=["original", "inspired_by", "adapt"],
    )
    def test_mode_25_scenes(self, mode, expected_low, expected_high):
        """Cost varies by mode at 25 scenes."""
        config = _config()
        est = estimate_cost(
            mode=mode,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(expected_low)
        assert claude.high == pytest.approx(expected_high)

    @pytest.mark.parametrize(
        "mode,expected_low,expected_high",
        [
            (InputMode.ORIGINAL, 4.00, 10.00),
            (InputMode.ADAPT, 0.40, 1.00),
        ],
        ids=["original", "adapt"],
    )
    def test_mode_scales_linearly(self, mode, expected_low, expected_high):
        """50 scenes should be 2x the cost of 25 scenes."""
        config = _config()
        est = estimate_cost(
            mode=mode,
            config=config,
            scene_count=50,
            character_count=495000,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(expected_low)
        assert claude.high == pytest.approx(expected_high)

    def test_original_mode_1_scene(self):
        """1 scene: cost = 1/25 of the 25-scene rate."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=1,
            character_count=9900,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(2.00 / 25)
        assert claude.high == pytest.approx(5.00 / 25)

    def test_claude_description_includes_mode(self):
        """Service description mentions the mode for clarity."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert "original" in claude.description.lower()


# ---------------------------------------------------------------------------
# TTS cost
# ---------------------------------------------------------------------------


class TestTTSCost:
    """TTS cost = character_count / 1_000_000 * rate_per_million_chars."""

    def test_tts_1_standard(self):
        """tts-1 at 247500 chars: 247500 / 1e6 * 15.00 = $3.7125."""
        config = _config(tts=TTSConfig(model="tts-1"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        tts = next(s for s in est.services if s.service == "TTS")
        expected = 247500 / 1_000_000 * 15.00
        assert tts.low == pytest.approx(expected)

    def test_gpt_4o_mini_tts(self):
        """gpt-4o-mini-tts at 247500 chars: 247500 / 1e6 * 0.60 = $0.1485."""
        config = _config(tts=TTSConfig(model="gpt-4o-mini-tts"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        tts = next(s for s in est.services if s.service == "TTS")
        expected = 247500 / 1_000_000 * 0.60
        assert tts.low == pytest.approx(expected)

    def test_tts_description_includes_model(self):
        config = _config(tts=TTSConfig(model="tts-1"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        tts = next(s for s in est.services if s.service == "TTS")
        assert "tts-1" in tts.description

    def test_unknown_tts_model_returns_zero_cost(self):
        """Unknown TTS model returns $0.00 with descriptive note instead of crashing."""
        config = _config(tts=TTSConfig(model="eleven_multilingual_v2"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        tts = next(s for s in est.services if s.service == "TTS")
        assert tts.low == 0.0
        assert tts.high == 0.0
        assert "not estimated" in tts.description
        assert len(est.services) == 4


# ---------------------------------------------------------------------------
# Image cost
# ---------------------------------------------------------------------------


class TestImageCost:
    """Image cost = scene_count * per_image_rate."""

    def test_medium_quality_25_scenes(self):
        """medium (GPT Image 1.5): 25 * $0.050 = $1.25."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        images = next(s for s in est.services if s.service == "Images")
        assert images.low == pytest.approx(25 * 0.050)
        assert images.high == pytest.approx(25 * 0.050)

    def test_hd_quality_25_scenes(self):
        """hd (DALL-E 3): 25 * $0.080 = $2.00."""
        config = _config(images=ImageConfig(quality="hd"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        images = next(s for s in est.services if s.service == "Images")
        assert images.low == pytest.approx(25 * 0.080)
        assert images.high == pytest.approx(25 * 0.080)

    def test_1_scene_medium(self):
        """1 scene medium: 1 * $0.050 = $0.05."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=1,
            character_count=9900,
        )
        images = next(s for s in est.services if s.service == "Images")
        assert images.low == pytest.approx(0.050)

    def test_image_description_includes_quality(self):
        config = _config(images=ImageConfig(quality="hd"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        images = next(s for s in est.services if s.service == "Images")
        assert "hd" in images.description.lower()

    def test_unknown_quality_raises(self):
        """Unknown image quality should raise ValueError."""
        config = _config(images=ImageConfig(quality="ultra"))
        with pytest.raises(ValueError, match="Unknown image quality"):
            estimate_cost(
                mode=InputMode.ORIGINAL,
                config=config,
                scene_count=25,
                character_count=247500,
            )


# ---------------------------------------------------------------------------
# Whisper cost
# ---------------------------------------------------------------------------


class TestWhisperCost:
    """Whisper cost = duration_minutes * $0.006."""

    @pytest.mark.parametrize(
        "duration,scene_count,char_count,expected",
        [
            (30, 25, 247500, 30 * 0.006),
            (60, 25, 247500, 60 * 0.006),
            (1, 1, 825, 0.006),
        ],
        ids=["30_minutes", "60_minutes", "1_minute"],
    )
    def test_whisper_cost(self, duration, scene_count, char_count, expected):
        """Whisper cost = duration_minutes * $0.006."""
        config = _config(story=StoryConfig(target_duration_minutes=duration))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=scene_count,
            character_count=char_count,
        )
        whisper = next(s for s in est.services if s.service == "Whisper")
        assert whisper.low == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Total cost
# ---------------------------------------------------------------------------


class TestTotalCost:
    """Total is the sum of all individual service costs."""

    def test_total_equals_sum_of_services(self):
        """Verify total_low and total_high equal sum of all service costs."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        assert est.total_low == pytest.approx(sum(s.low for s in est.services))
        assert est.total_high == pytest.approx(sum(s.high for s in est.services))

    def test_default_original_mode_total_range(self):
        """Sanity check: default original mode total should be reasonable.

        With default config (30 min, 3 scenes calculated):
        - Claude: $0.24 - $0.60 (3/25 * 2.00, 3/25 * 5.00)
        - TTS (tts-1-hd): 29700/1e6 * 30 = $0.891
        - Images (medium): 3 * 0.05 = $0.15
        - Whisper: 30 * 0.006 = $0.18
        Total low:  ~$1.43
        Total high: ~$1.79
        """
        config = _config()
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        # Just ensure the totals are in a sane range
        assert est.total_low > 0
        assert est.total_high >= est.total_low


# ---------------------------------------------------------------------------
# Service order
# ---------------------------------------------------------------------------


class TestServiceOrder:
    """Services appear in a consistent order in the estimate."""

    def test_services_in_expected_order(self):
        """Claude, then TTS, then Images, then Whisper."""
        config = _config()
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        names = [s.service for s in est.services]
        assert names == ["Claude", "TTS", "Images", "Whisper"]


# ---------------------------------------------------------------------------
# format_cost_estimate
# ---------------------------------------------------------------------------


class TestFormatCostEstimate:
    """format_cost_estimate produces the display format from the design doc."""

    @pytest.fixture()
    def format_output(self):
        """Shared formatted output for the default original-mode estimate."""
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        return format_cost_estimate(est)

    @pytest.mark.parametrize(
        "expected_substrings",
        [
            ["Story Video Cost Estimate"],
            ["original"],
            ["30 minutes", "25 scenes"],
            ["Claude", "TTS", "Images", "Whisper"],
            ["Estimated total"],
        ],
        ids=["header", "mode", "duration_and_scenes", "service_names", "total"],
    )
    def test_format_contains(self, format_output, expected_substrings):
        """Formatted output contains expected content."""
        for substring in expected_substrings:
            assert substring in format_output

    def test_range_format_for_claude(self):
        """When low != high, show as range: $X.XX - $Y.YY."""
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "$2.00 - $5.00" in output

    def test_exact_format_for_whisper(self):
        """When low == high, show single value: $X.XX."""
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "$0.18" in output

    def test_total_range_shown(self):
        """Total should show range when there's a range service."""
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        # Total includes the Claude range, so it should be a range
        total_low = est.total_low
        total_high = est.total_high
        assert f"${total_low:.2f}" in output
        assert f"${total_high:.2f}" in output

    def test_adapt_mode_format(self):
        """Adapt mode should show adapt in the output."""
        est = estimate_cost(
            mode=InputMode.ADAPT,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "adapt" in output

    def test_contains_horizontal_rules(self):
        """Output contains separator lines using box-drawing characters."""
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        # Should have at least two horizontal rule lines
        lines_with_rules = [line for line in output.split("\n") if "\u2500" in line]
        assert len(lines_with_rules) >= 2

    def test_unknown_model_format(self):
        """Unknown TTS model shows 'not estimated' in formatted output."""
        config = _config(tts=TTSConfig(model="eleven_multilingual_v2"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "not estimated" in output
        assert "$0.00" in output

    def test_is_plain_text(self):
        """Output should be plain text, not Rich markup."""
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        # Rich markup uses square brackets like [bold], [green], etc.
        assert "[bold]" not in output
        assert "[green]" not in output
        assert "[/]" not in output


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_all_modes_produce_valid_estimate(self):
        """All three modes should produce a valid estimate without error."""
        config = _config()
        for mode in InputMode:
            est = estimate_cost(mode=mode, config=config)
            assert est.total_low > 0
            assert est.total_high >= est.total_low

    def test_large_scene_count(self):
        """100 scenes should not cause errors, costs scale linearly."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=100,
            character_count=990000,
        )
        assert est.scene_count == 100
        claude = next(s for s in est.services if s.service == "Claude")
        # 100/25 * 2.00 = 8.00
        assert claude.low == pytest.approx(8.00)
