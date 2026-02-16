"""Cost estimation for the Story Video Generator.

Calculates projected costs for all API services used in video generation:
- Claude API (story generation)
- OpenAI TTS (text-to-speech)
- OpenAI Image generation (GPT Image / DALL-E)
- Whisper (caption generation)

Can operate in two modes:
1. Projected — calculates scene/character counts from config duration settings
2. Actual — uses real scene/character counts from finalized text

Pure computation only — no I/O, no API calls.
"""

import math
from dataclasses import dataclass

from story_video.models import AppConfig, InputMode

__all__ = [
    "CostEstimate",
    "ServiceCost",
    "estimate_cost",
    "format_cost_estimate",
]

# ---------------------------------------------------------------------------
# Cost rate constants
# ---------------------------------------------------------------------------

# Average characters per word including spaces (English text approximation)
CHARS_PER_WORD: float = 5.5

# Reference scene count for Claude API cost rates.
# All Claude rates below are calibrated for this many scenes.
REFERENCE_SCENE_COUNT: int = 25

# Claude API costs for story generation at REFERENCE_SCENE_COUNT scenes.
# original/inspired_by: 3 setup calls + N scenes + N critique + 0.5N revision + ~4 utility calls
CLAUDE_ORIGINAL_LOW_PER_REF: float = 2.00  # dollars for 25 scenes (low end)
CLAUDE_ORIGINAL_HIGH_PER_REF: float = 5.00  # dollars for 25 scenes (high end)
# adapt: ~6 calls total (scene splitting + narration flagging)
CLAUDE_ADAPT_LOW_PER_REF: float = 0.20  # dollars for 25 scenes (low end)
CLAUDE_ADAPT_HIGH_PER_REF: float = 0.50  # dollars for 25 scenes (high end)

# OpenAI TTS cost per 1,000,000 characters by model
TTS_COST_PER_MILLION_CHARS: dict[str, float] = {
    "gpt-4o-mini-tts": 0.60,
    "tts-1": 15.00,
    "tts-1-hd": 30.00,
}

# Image generation cost per image by quality tier.
# Covers GPT Image 1.5 (low/medium/high) and DALL-E 3 (standard/hd).
IMAGE_COST_PER_IMAGE: dict[str, float] = {
    # GPT Image 1.5
    "low": 0.020,
    "medium": 0.050,
    "high": 0.200,
    # DALL-E 3
    "standard": 0.040,
    "hd": 0.080,
}

# Whisper (caption generation) cost per minute of audio
WHISPER_COST_PER_MINUTE: float = 0.006


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceCost:
    """Cost for a single API service.

    When a service has an exact known cost, low and high are equal.
    When a service has a cost range (e.g., Claude API), low < high.

    Attributes:
        service: Service display name (e.g., "Claude", "OpenAI TTS").
        description: Additional detail (e.g., model name, quality tier).
        low: Lower bound cost estimate in dollars.
        high: Upper bound cost estimate in dollars.
    """

    service: str
    description: str
    low: float
    high: float


@dataclass(frozen=True)
class CostEstimate:
    """Complete cost breakdown for a video project.

    Contains per-service cost entries and metadata about the estimation
    parameters. The total_low and total_high properties aggregate all
    service costs.

    Attributes:
        mode: Input mode used for this estimate.
        duration_minutes: Target video duration in minutes.
        scene_count: Number of scenes (projected or actual).
        character_count: Total character count (projected or actual).
        services: Ordered list of per-service cost entries.
    """

    mode: InputMode
    duration_minutes: int
    scene_count: int
    character_count: int
    services: list[ServiceCost]

    @property
    def total_low(self) -> float:
        """Sum of all service low-end costs."""
        return sum(s.low for s in self.services)

    @property
    def total_high(self) -> float:
        """Sum of all service high-end costs."""
        return sum(s.high for s in self.services)


# ---------------------------------------------------------------------------
# Cost calculation helpers
# ---------------------------------------------------------------------------


def _calculate_claude_cost(mode: InputMode, scene_count: int) -> ServiceCost:
    """Calculate Claude API cost for story generation.

    Costs scale linearly with scene count relative to the reference of 25 scenes.
    original and inspired_by share the same rate (both use the full creative flow).
    adapt uses a much lower rate (fewer API calls).

    Args:
        mode: Input mode determining which rate table to use.
        scene_count: Number of scenes to estimate for.

    Returns:
        ServiceCost with the Claude API cost range.
    """
    scale = scene_count / REFERENCE_SCENE_COUNT

    if mode in (InputMode.ORIGINAL, InputMode.INSPIRED_BY):
        low = CLAUDE_ORIGINAL_LOW_PER_REF * scale
        high = CLAUDE_ORIGINAL_HIGH_PER_REF * scale
        description = f"story generation, {mode.value}"
    else:
        # InputMode.ADAPT
        low = CLAUDE_ADAPT_LOW_PER_REF * scale
        high = CLAUDE_ADAPT_HIGH_PER_REF * scale
        description = f"story generation, {mode.value}"

    return ServiceCost(service="Claude", description=description, low=low, high=high)


def _calculate_tts_cost(tts_model: str, character_count: int) -> ServiceCost:
    """Calculate OpenAI TTS cost.

    Formula: character_count / 1,000,000 * rate_per_million_chars

    Args:
        tts_model: TTS model identifier (e.g., "tts-1-hd").
        character_count: Total characters to synthesize.

    Returns:
        ServiceCost with the exact TTS cost.

    Raises:
        ValueError: If tts_model is not in the known rate table.
    """
    if tts_model not in TTS_COST_PER_MILLION_CHARS:
        raise ValueError(
            f"Unknown TTS model: {tts_model!r}. "
            f"Known models: {', '.join(sorted(TTS_COST_PER_MILLION_CHARS))}"
        )

    rate = TTS_COST_PER_MILLION_CHARS[tts_model]
    cost = character_count / 1_000_000 * rate

    return ServiceCost(service="OpenAI TTS", description=tts_model, low=cost, high=cost)


def _calculate_image_cost(quality: str, scene_count: int) -> ServiceCost:
    """Calculate image generation cost.

    Formula: scene_count * per_image_rate (one image per scene)

    Args:
        quality: Image quality tier (e.g. "medium", "high", "standard", "hd").
        scene_count: Number of images to generate.

    Returns:
        ServiceCost with the exact image generation cost.

    Raises:
        ValueError: If quality is not in the known rate table.
    """
    if quality not in IMAGE_COST_PER_IMAGE:
        raise ValueError(
            f"Unknown image quality: {quality!r}. "
            f"Known qualities: {', '.join(sorted(IMAGE_COST_PER_IMAGE))}"
        )

    rate = IMAGE_COST_PER_IMAGE[quality]
    cost = scene_count * rate

    return ServiceCost(service="Images", description=quality, low=cost, high=cost)


def _calculate_whisper_cost(duration_minutes: int) -> ServiceCost:
    """Calculate Whisper caption generation cost.

    Formula: duration_minutes * $0.006

    Args:
        duration_minutes: Target audio duration in minutes.

    Returns:
        ServiceCost with the exact Whisper cost.
    """
    cost = duration_minutes * WHISPER_COST_PER_MINUTE

    return ServiceCost(service="Whisper", description="captions", low=cost, high=cost)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def estimate_cost(
    mode: InputMode,
    config: AppConfig,
    scene_count: int | None = None,
    character_count: int | None = None,
) -> CostEstimate:
    """Calculate cost estimate for a story video project.

    Can be called in two modes:
    1. Projected (scene_count and character_count are None): calculates from
       config duration/word settings using the formula.
    2. Actual (scene_count and character_count provided): uses real numbers
       from finalized text for more accurate estimates.

    Scene count formula (projected mode):
        scene_count = ceil(target_duration_minutes * words_per_minute / scene_word_target)

    Character count formula (projected mode):
        character_count = scene_count * scene_word_target * 5.5

    Note:
        scene_count and character_count can be provided independently. When only
        scene_count is given, character_count is projected from it. When only
        character_count is given, scene_count is still calculated from config.

    Args:
        mode: Input mode (affects Claude API cost estimate).
        config: Application configuration (TTS model, image quality, duration).
        scene_count: Actual scene count (if known). Calculated from config if None.
        character_count: Actual character count (if known). Calculated if None.

    Returns:
        CostEstimate with per-service breakdown.
    """
    duration = config.story.target_duration_minutes

    # Calculate scene count from config if not provided
    if scene_count is None:
        # scene_count = ceil(duration * wpm / scene_word_target)
        scene_count = math.ceil(
            duration * config.story.words_per_minute / config.story.scene_word_target
        )

    # Calculate character count from config if not provided
    if character_count is None:
        # character_count = scene_count * scene_word_target * 5.5 (chars per word)
        character_count = int(scene_count * config.story.scene_word_target * CHARS_PER_WORD)

    # Build per-service cost entries in display order
    services = [
        _calculate_claude_cost(mode, scene_count),
        _calculate_tts_cost(config.tts.model, character_count),
        _calculate_image_cost(config.images.quality, scene_count),
        _calculate_whisper_cost(duration),
    ]

    return CostEstimate(
        mode=mode,
        duration_minutes=duration,
        scene_count=scene_count,
        character_count=character_count,
        services=services,
    )


def format_cost_estimate(estimate: CostEstimate) -> str:
    """Format a cost estimate for display.

    Produces the formatted output shown in design.md section 12.
    Uses box-drawing characters for horizontal rules.
    Output is plain text (no Rich markup) — Rich formatting is added by the CLI layer.

    Args:
        estimate: The cost estimate to format.

    Returns:
        Formatted string ready for terminal display.
    """
    lines: list[str] = []

    # Header
    lines.append("Story Video Cost Estimate")
    lines.append("\u2500" * 40)

    # Metadata
    lines.append(f"Mode:     {estimate.mode.value}")
    lines.append(f"Duration: {estimate.duration_minutes} minutes (~{estimate.scene_count} scenes)")
    lines.append("")

    # Per-service costs
    for svc in estimate.services:
        label = f"  {svc.service} ({svc.description})"
        cost_str = _format_cost_value(svc.low, svc.high)
        lines.append(f"{label:<40} {cost_str}")

    # Separator before total
    separator = "\u2500" * 13
    lines.append(f"{'':>40} {separator}")

    # Total
    total_str = _format_cost_value(estimate.total_low, estimate.total_high)
    lines.append(f"{'  Estimated total':<40} {total_str}")

    return "\n".join(lines)


def _format_cost_value(low: float, high: float) -> str:
    """Format a cost value as either a single amount or a range.

    Args:
        low: Lower bound cost.
        high: Upper bound cost.

    Returns:
        "$X.XX" if low == high, otherwise "$X.XX - $Y.YY".
    """
    if abs(low - high) < 0.005:
        # Exact cost (low and high are effectively equal)
        return f"${low:.2f}"
    return f"${low:.2f} - ${high:.2f}"
