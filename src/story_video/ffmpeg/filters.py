"""FFmpeg filter expression builders for video assembly.

Provides pure functions that return FFmpeg filter expression strings for
blurred background layers and still-image foreground scaling. These functions
produce deterministic output -- same inputs always yield the same string.
"""

from story_video.models import RESOLUTION_RE

__all__ = ["blur_background_filter", "parse_resolution", "still_image_filter"]


def parse_resolution(resolution: str) -> tuple[str, str]:
    """Parse a ``WIDTHxHEIGHT`` resolution string into (width, height).

    Args:
        resolution: Resolution string like ``"1920x1080"``.

    Returns:
        Tuple of ``(width, height)`` as strings.

    Raises:
        ValueError: If *resolution* is not in ``WIDTHxHEIGHT`` format.
    """
    if not RESOLUTION_RE.match(resolution):
        msg = f"Invalid resolution format: {resolution!r} (expected 'WIDTHxHEIGHT')"
        raise ValueError(msg)
    w, h = resolution.split("x")
    return w, h


def still_image_filter(resolution: str) -> str:
    """Build a filter chain to scale and pad an image to fit the target resolution.

    Scales the image to fit within the target resolution (preserving aspect
    ratio) then pads to the exact dimensions, centering the image.

    Args:
        resolution: Target resolution as "WxH" (e.g. "1920x1080").

    Returns:
        A comma-separated filter chain string ready for FFmpeg ``-vf``.
    """
    w, h = parse_resolution(resolution)
    return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"


def blur_background_filter(blur_radius: int, resolution: str) -> str:
    """Build a filter chain for a blurred background layer.

    Produces a filter chain that scales the input to cover the target
    resolution (preserving aspect ratio), crops to the exact dimensions,
    and applies a Gaussian blur.

    Args:
        blur_radius: Gaussian blur sigma value (higher = more blur, must be >= 0).
        resolution: Target resolution as "WxH" (e.g. "1920x1080").

    Raises:
        ValueError: If blur_radius is negative.

    Returns:
        A comma-separated filter chain string ready for FFmpeg ``-vf``.
    """
    if blur_radius < 0:
        msg = f"blur_radius must be >= 0, got {blur_radius}"
        raise ValueError(msg)
    w, h = parse_resolution(resolution)

    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma={blur_radius}"
    )
