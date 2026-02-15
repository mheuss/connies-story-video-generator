"""FFmpeg filter expression builders for video assembly.

Provides pure functions that return FFmpeg filter expression strings for
Ken Burns (zoompan) effects and blurred background layers. These functions
produce deterministic output -- same inputs always yield the same string.
"""

__all__ = ["ken_burns_filter", "blur_background_filter"]

_ZOOMPAN_FPS = 25
"""Internal frame rate used by the zoompan filter."""


def ken_burns_filter(duration: float, zoom: float, direction: int, resolution: str) -> str:
    """Build a zoompan filter expression for a Ken Burns effect.

    Args:
        duration: Scene duration in seconds.
        zoom: Maximum zoom factor (e.g. 1.3 means 130% of original size).
        direction: Motion direction derived from scene_number % 5:
            0 -- zoom in (center), zoom interpolates 1.0 -> zoom
            1 -- zoom out (center), zoom interpolates zoom -> 1.0
            2 -- pan left, slight zoom, x drifts right-to-left
            3 -- pan right, slight zoom, x drifts left-to-right
            4 -- diagonal drift, slight zoom, both axes drift
        resolution: Output resolution as "WxH" (e.g. "1920x1080").

    Returns:
        A zoompan filter expression string ready for FFmpeg ``-vf``.

    Raises:
        ValueError: If direction is not in the range 0-4.
    """
    if direction < 0 or direction > 4:
        msg = f"direction must be 0-4, got {direction}"
        raise ValueError(msg)

    frames = int(duration * _ZOOMPAN_FPS)

    # Build zoom and position expressions per direction.
    # In zoompan, 'on' is the current frame index (0-based).
    # 'iw' and 'ih' are the input width/height.
    # x and y define the top-left corner of the visible region.
    # zoom defines the current zoom level (1.0 = no zoom).
    if direction == 0:
        # Zoom in from center: zoom ramps from 1.0 to target zoom
        z_expr = f"1.0+({zoom}-1.0)*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == 1:
        # Zoom out from center: zoom ramps from target zoom to 1.0
        z_expr = f"{zoom}-({zoom}-1.0)*on/{frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == 2:
        # Pan left (right-to-left): slight zoom, x decreases over time
        slight_zoom = 1.0 + (zoom - 1.0) * 0.3
        z_expr = f"{slight_zoom}"
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif direction == 3:
        # Pan right (left-to-right): slight zoom, x increases over time
        slight_zoom = 1.0 + (zoom - 1.0) * 0.3
        z_expr = f"{slight_zoom}"
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Diagonal drift: slight zoom, both axes drift
        slight_zoom = 1.0 + (zoom - 1.0) * 0.3
        z_expr = f"{slight_zoom}"
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = f"(ih-ih/zoom)*on/{frames}"

    return (
        f"zoompan=z='{z_expr}'"
        f":x='{x_expr}'"
        f":y='{y_expr}'"
        f":d={frames}"
        f":s={resolution}"
        f":fps={_ZOOMPAN_FPS}"
    )


def blur_background_filter(blur_radius: int, resolution: str) -> str:
    """Build a filter chain for a blurred background layer.

    Produces a filter chain that scales the input to cover the target
    resolution (preserving aspect ratio), crops to the exact dimensions,
    and applies a Gaussian blur.

    Args:
        blur_radius: Gaussian blur sigma value (higher = more blur).
        resolution: Target resolution as "WxH" (e.g. "1920x1080").

    Returns:
        A comma-separated filter chain string ready for FFmpeg ``-vf``.
    """
    w, h = resolution.split("x")

    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma={blur_radius}"
    )
