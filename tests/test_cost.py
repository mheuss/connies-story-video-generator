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

    def test_uses_provided_character_count(self):
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        assert est.character_count == 247500

    def test_duration_still_from_config(self):
        """Duration always comes from config, even in actual mode."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        assert est.duration_minutes == 30


# ---------------------------------------------------------------------------
# Claude API cost
# ---------------------------------------------------------------------------


class TestClaudeCost:
    """Claude API cost varies by mode, scales linearly with scene count."""

    def test_original_mode_25_scenes(self):
        """original mode at 25 scenes: $2.00 - $5.00."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(2.00)
        assert claude.high == pytest.approx(5.00)

    def test_inspired_by_mode_25_scenes(self):
        """inspired_by mode at 25 scenes: $2.00 - $5.00 (same as original)."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.INSPIRED_BY,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(2.00)
        assert claude.high == pytest.approx(5.00)

    def test_adapt_mode_25_scenes(self):
        """adapt mode at 25 scenes: $0.20 - $0.50."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ADAPT,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(0.20)
        assert claude.high == pytest.approx(0.50)

    def test_original_mode_scales_linearly(self):
        """50 scenes should be 2x the cost of 25 scenes."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=50,
            character_count=495000,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(4.00)
        assert claude.high == pytest.approx(10.00)

    def test_adapt_mode_scales_linearly(self):
        """50 scenes should be 2x the cost of 25 scenes for adapt."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ADAPT,
            config=config,
            scene_count=50,
            character_count=495000,
        )
        claude = next(s for s in est.services if s.service == "Claude")
        assert claude.low == pytest.approx(0.40)
        assert claude.high == pytest.approx(1.00)

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

    def test_tts_1_hd_default(self):
        """tts-1-hd at 247500 chars: 247500 / 1e6 * 30.00 = $7.425."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        tts = next(s for s in est.services if s.service == "OpenAI TTS")
        expected = 247500 / 1_000_000 * 30.00
        assert tts.low == pytest.approx(expected)
        assert tts.high == pytest.approx(expected)  # Exact cost, low == high

    def test_tts_1_standard(self):
        """tts-1 at 247500 chars: 247500 / 1e6 * 15.00 = $3.7125."""
        config = _config(tts=TTSConfig(model="tts-1"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        tts = next(s for s in est.services if s.service == "OpenAI TTS")
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
        tts = next(s for s in est.services if s.service == "OpenAI TTS")
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
        tts = next(s for s in est.services if s.service == "OpenAI TTS")
        assert "tts-1" in tts.description

    def test_unknown_tts_model_raises(self):
        """Unknown TTS model should raise ValueError."""
        config = _config(tts=TTSConfig(model="unknown-model"))
        with pytest.raises(ValueError, match="Unknown TTS model"):
            estimate_cost(
                mode=InputMode.ORIGINAL,
                config=config,
                scene_count=25,
                character_count=247500,
            )


# ---------------------------------------------------------------------------
# DALL-E cost
# ---------------------------------------------------------------------------


class TestDALLECost:
    """DALL-E cost = scene_count * per_image_rate."""

    def test_standard_quality_25_scenes(self):
        """standard 1024x1024: 25 * $0.040 = $1.00."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        dalle = next(s for s in est.services if s.service == "DALL-E 3")
        assert dalle.low == pytest.approx(25 * 0.040)
        assert dalle.high == pytest.approx(25 * 0.040)

    def test_hd_quality_25_scenes(self):
        """hd 1024x1024: 25 * $0.080 = $2.00."""
        config = _config(images=ImageConfig(quality="hd"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        dalle = next(s for s in est.services if s.service == "DALL-E 3")
        assert dalle.low == pytest.approx(25 * 0.080)
        assert dalle.high == pytest.approx(25 * 0.080)

    def test_1_scene_standard(self):
        """1 scene standard: 1 * $0.040 = $0.04."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=1,
            character_count=9900,
        )
        dalle = next(s for s in est.services if s.service == "DALL-E 3")
        assert dalle.low == pytest.approx(0.040)

    def test_dalle_description_includes_quality(self):
        config = _config(images=ImageConfig(quality="hd"))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        dalle = next(s for s in est.services if s.service == "DALL-E 3")
        assert "hd" in dalle.description.lower()

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

    def test_30_minutes(self):
        """30 min * $0.006 = $0.18."""
        config = _config()
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        whisper = next(s for s in est.services if s.service == "Whisper")
        assert whisper.low == pytest.approx(30 * 0.006)
        assert whisper.high == pytest.approx(30 * 0.006)

    def test_60_minutes(self):
        """60 min * $0.006 = $0.36."""
        config = _config(story=StoryConfig(target_duration_minutes=60))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=25,
            character_count=247500,
        )
        whisper = next(s for s in est.services if s.service == "Whisper")
        assert whisper.low == pytest.approx(60 * 0.006)

    def test_1_minute(self):
        """1 min * $0.006 = $0.006."""
        config = _config(story=StoryConfig(target_duration_minutes=1))
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=config,
            scene_count=1,
            character_count=825,
        )
        whisper = next(s for s in est.services if s.service == "Whisper")
        assert whisper.low == pytest.approx(0.006)


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

    def test_has_four_services(self):
        """Estimate should contain exactly 4 services: Claude, TTS, DALL-E, Whisper."""
        config = _config()
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert len(est.services) == 4
        service_names = {s.service for s in est.services}
        assert service_names == {"Claude", "OpenAI TTS", "DALL-E 3", "Whisper"}

    def test_default_original_mode_total_range(self):
        """Sanity check: default original mode total should be reasonable.

        With default config (30 min, 3 scenes calculated):
        - Claude: $0.24 - $0.60 (3/25 * 2.00, 3/25 * 5.00)
        - TTS (tts-1-hd): 29700/1e6 * 30 = $0.891
        - DALL-E (standard): 3 * 0.04 = $0.12
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
        """Claude, then TTS, then DALL-E, then Whisper."""
        config = _config()
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        names = [s.service for s in est.services]
        assert names == ["Claude", "OpenAI TTS", "DALL-E 3", "Whisper"]


# ---------------------------------------------------------------------------
# format_cost_estimate
# ---------------------------------------------------------------------------


class TestFormatCostEstimate:
    """format_cost_estimate produces the display format from the design doc."""

    def test_contains_header(self):
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "Story Video Cost Estimate" in output

    def test_contains_mode(self):
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "original" in output

    def test_contains_duration_and_scene_count(self):
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "30 minutes" in output
        assert "25 scenes" in output

    def test_contains_all_service_names(self):
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "Claude" in output
        assert "OpenAI TTS" in output
        assert "DALL-E 3" in output
        assert "Whisper" in output

    def test_contains_estimated_total(self):
        est = estimate_cost(
            mode=InputMode.ORIGINAL,
            config=_config(),
            scene_count=25,
            character_count=247500,
        )
        output = format_cost_estimate(est)
        assert "Estimated total" in output

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

    def test_scene_count_never_zero(self):
        """Even with tiny duration, at least 1 scene."""
        config = _config(story=StoryConfig(target_duration_minutes=1))
        est = estimate_cost(mode=InputMode.ORIGINAL, config=config)
        assert est.scene_count >= 1

    def test_mode_stored_on_estimate(self):
        """The mode is preserved on the estimate object."""
        for mode in InputMode:
            est = estimate_cost(mode=mode, config=_config())
            assert est.mode == mode

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
