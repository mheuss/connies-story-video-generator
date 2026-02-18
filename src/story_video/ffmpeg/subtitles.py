"""ASS (Advanced SubStation Alpha) subtitle generation from caption data.

Converts word-level timestamps from Whisper transcription into ASS subtitle
file content suitable for burning into video via FFmpeg's ``ass`` filter.

Public functions:
    generate_ass_content: Build complete ASS file content from caption data.
    subtitle_filter: Return the FFmpeg filter fragment for ASS subtitle overlay.
"""

from pathlib import Path

from story_video.ffmpeg.filters import _parse_resolution
from story_video.models import (
    _HEX_COLOR_RE,
    CaptionResult,
    CaptionWord,
    SubtitleConfig,
    VideoConfig,
)

__all__ = [
    "generate_ass_content",
    "subtitle_filter",
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _hex_to_ass_color(hex_color: str) -> str:
    """Convert a ``#RRGGBB`` hex color to ASS ``&H00BBGGRR&`` format.

    ASS stores colors in reversed byte order (BGR) with an alpha prefix byte.

    Args:
        hex_color: Color string in ``#RRGGBB`` format (case-insensitive).

    Returns:
        ASS color string in ``&H00BBGGRR&`` format.
    """
    if not _HEX_COLOR_RE.match(hex_color):
        msg = f"Invalid hex color format: {hex_color!r} (expected #RRGGBB)"
        raise ValueError(msg)
    hex_color = hex_color.lstrip("#")
    rr = hex_color[0:2]
    gg = hex_color[2:4]
    bb = hex_color[4:6]
    return f"&H00{bb}{gg}{rr}&".upper()


def _format_ass_time(seconds: float) -> str:
    """Format a time value in seconds to ASS time format ``H:MM:SS.cc``.

    ASS timestamps use centisecond precision with the format ``H:MM:SS.cc``
    where ``H`` is hours (no leading zero), ``MM`` and ``SS`` are zero-padded
    to two digits, and ``cc`` is centiseconds (hundredths of a second).

    Args:
        seconds: Time value in seconds.

    Returns:
        Formatted ASS timestamp string.
    """
    # Round to centisecond precision
    centiseconds_total = round(seconds * 100)
    cs = centiseconds_total % 100
    total_seconds = centiseconds_total // 100
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    h = total_minutes // 60
    return f"{h}:{mm:02d}:{ss:02d}.{cs:02d}"


def _group_words_into_events(
    words: list[CaptionWord],
    max_chars_per_line: int,
    max_lines: int,
) -> list[list[list[CaptionWord]]]:
    """Group words into subtitle events, each containing up to *max_lines* lines.

    Each line contains words whose combined text length (with spaces) does not
    exceed *max_chars_per_line*. When a line is full, a new line is started.
    When *max_lines* lines are full, the current group is emitted as an event
    and a new group begins.

    A single word longer than *max_chars_per_line* is placed on its own line
    to avoid infinite loops.

    Args:
        words: Ordered list of caption words with timing.
        max_chars_per_line: Maximum character count per subtitle line.
        max_lines: Maximum number of lines per subtitle event.

    Returns:
        List of events. Each event is a list of lines. Each line is a list
        of CaptionWord objects.
    """
    if not words:
        return []

    events: list[list[list[CaptionWord]]] = []
    current_event_lines: list[list[CaptionWord]] = []
    current_line: list[CaptionWord] = []
    current_line_len = 0

    for word in words:
        word_len = len(word.word)

        # Check if adding this word (with a space separator) would overflow the line
        if current_line:
            projected_len = current_line_len + 1 + word_len  # space + word
        else:
            projected_len = word_len

        if projected_len > max_chars_per_line and current_line:
            # Current line is full — push it
            current_event_lines.append(current_line)
            current_line = []
            current_line_len = 0

            if len(current_event_lines) >= max_lines:
                # Current event is full — emit it
                events.append(current_event_lines)
                current_event_lines = []

        current_line.append(word)
        current_line_len = current_line_len + 1 + word_len if current_line_len > 0 else word_len

    # Flush remaining words
    if current_line:
        current_event_lines.append(current_line)
    if current_event_lines:
        events.append(current_event_lines)

    return events


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def generate_ass_content(
    caption_result: CaptionResult,
    subtitle_config: SubtitleConfig,
    video_config: VideoConfig,
) -> str:
    """Generate complete ASS subtitle file content from caption data.

    Builds three sections:

    1. **[Script Info]** — Title, script type, and play resolution from
       the video configuration.
    2. **[V4+ Styles]** — Default style using font, size, colors, outline,
       and vertical position from the subtitle configuration.
    3. **[Events]** — Dialogue lines built by grouping words into subtitle
       events respecting ``max_chars_per_line`` and ``max_lines``.

    Args:
        caption_result: Word-level timestamps from Whisper transcription.
        subtitle_config: Font, color, and layout settings for subtitles.
        video_config: Video resolution for ASS play resolution.

    Returns:
        Complete ASS file content as a string.
    """
    width, height = _parse_resolution(video_config.resolution)

    primary_color = _hex_to_ass_color(subtitle_config.color)
    outline_color = _hex_to_ass_color(subtitle_config.outline_color)

    # MarginV controls vertical position from bottom
    margin_v = subtitle_config.position_bottom

    # --- [Script Info] ---
    script_info = (
        "[Script Info]\n"
        "Title: Story Video Subtitles\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
    )

    # --- [V4+ Styles] ---
    # ASS Style format:
    # Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour,
    # BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing,
    # Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV,
    # Encoding
    style_line = (
        f"Style: Default,{subtitle_config.font},{subtitle_config.font_size},"
        f"{primary_color},&H000000FF&,{outline_color},&H00000000&,"
        f"0,0,0,0,100,100,0,0,1,{subtitle_config.outline_width},0,2,"
        f"10,10,{margin_v},1"
    )

    styles_section = (
        "\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n"
    )

    # --- [Events] ---
    events_header = (
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    dialogue_lines: list[str] = []
    events = _group_words_into_events(
        caption_result.words,
        subtitle_config.max_chars_per_line,
        subtitle_config.max_lines,
    )

    for event_lines in events:
        # Flatten to get first and last word for timing
        all_words_in_event = [w for line in event_lines for w in line]
        start_time = _format_ass_time(all_words_in_event[0].start)
        end_time = _format_ass_time(all_words_in_event[-1].end)

        # Build text with \N line breaks
        text_lines = [" ".join(w.word for w in line) for line in event_lines]
        text = "\\N".join(text_lines)

        dialogue_lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")

    events_section = events_header + "\n".join(dialogue_lines)

    return script_info + styles_section + events_section


def subtitle_filter(ass_path: Path) -> str:
    """Return the FFmpeg filter fragment for ASS subtitle overlay.

    Escapes backslashes and single quotes in the path to prevent
    FFmpeg filter graph injection or parse errors.

    Args:
        ass_path: Path to the ASS subtitle file.

    Returns:
        Filter string in the form ``ass='/path/to/file.ass'``
        with special characters escaped.
    """
    escaped = str(ass_path).replace("\\", "\\\\").replace("'", "\\'")
    return f"ass='{escaped}'"
