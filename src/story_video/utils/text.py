"""Text utilities and narration prep for TTS-optimized delivery.

This module transforms prose into text optimized for text-to-speech engines.
It preserves the original text and produces a parallel narration version with:
- Expanded abbreviations (Dr. -> Doctor)
- Numbers converted to words (3 -> three, 1920s -> nineteen-twenties)
- Pause markers at dramatic breaks (paragraph boundaries)
- Smoothed punctuation (em dashes, ellipsis normalization, footnote removal)

All functions are pure — no state, no side effects. The original input string
is never modified.

See ADR-006 in DEVELOPMENT.md for architectural rationale.
"""

import re
from collections.abc import Callable

__all__ = [
    "expand_abbreviations",
    "insert_pause_markers",
    "numbers_to_words",
    "prepare_narration",
    "smooth_punctuation",
]

# ---------------------------------------------------------------------------
# Abbreviation expansion
# ---------------------------------------------------------------------------

# Mapping of abbreviations to their spoken equivalents.
# Keys include the trailing period as part of the abbreviation.
# Order matters for patterns that might overlap (e.g. "Mrs." before "Mr.").
_ABBREVIATIONS: dict[str, str] = {
    "Mrs.": "Missus",
    "Mr.": "Mister",
    "Ms.": "Mizz",
    "Dr.": "Doctor",
    "St.": "Saint",
    "vs.": "versus",
    "etc.": "et cetera",
    "e.g.": "for example",
    "i.e.": "that is",
}

# Abbreviations where the trailing period can serve double duty as a
# sentence-ending period. When these appear at end of sentence (followed by
# whitespace, newline, or end-of-string), the period must be preserved.
_SENTENCE_ENDING_ABBREVS = {"etc.", "vs.", "e.g.", "i.e."}


# Pre-compiled regex patterns for each abbreviation.
# Each entry is (pattern, expansion, can_end_sentence).
# Uses word boundary (\b) or positional matching to avoid partial replacements.
def _build_abbreviation_patterns() -> list[tuple[re.Pattern[str], str, bool]]:
    """Build pre-compiled regex patterns for abbreviation expansion.

    Returns:
        List of (pattern, expansion, can_end_sentence) tuples.
    """
    patterns: list[tuple[re.Pattern[str], str, bool]] = []
    for abbr, expansion in _ABBREVIATIONS.items():
        # Escape the abbreviation for regex (dots become literal dots)
        escaped = re.escape(abbr)
        can_end = abbr in _SENTENCE_ENDING_ABBREVS
        # Use a pattern that matches the abbreviation with appropriate boundaries.
        # For multi-dot abbreviations like "e.g." and "i.e.", we match them as-is
        # since the dots act as natural delimiters.
        # For single-dot abbreviations, we use word boundary before.
        if abbr in ("e.g.", "i.e."):
            # These are typically preceded by a space or opening paren
            pattern = re.compile(escaped)
        else:
            # Word boundary before, literal match of abbreviation
            pattern = re.compile(r"\b" + escaped)
        patterns.append((pattern, expansion, can_end))
    return patterns


_ABBREVIATION_PATTERNS = _build_abbreviation_patterns()


def _make_replacer(expansion: str, text: str) -> Callable[[re.Match[str]], str]:
    """Create a regex replacement function that preserves sentence-ending periods.

    When an abbreviation that can end a sentence (e.g. "etc.") appears at end of
    string or before a newline, the period is restored after expansion.

    Args:
        expansion: The expanded form to replace the abbreviation with.
        text: The full text being processed (for lookahead).

    Returns:
        A replacement function compatible with re.sub().
    """

    def _replacer(m: re.Match[str]) -> str:
        end_pos = m.end()
        if end_pos >= len(text):
            # End of string — period was sentence-ending
            return expansion + "."
        next_char = text[end_pos]
        if next_char == "\n":
            # Followed by newline — period was sentence-ending
            return expansion + "."
        return expansion

    return _replacer


def expand_abbreviations(text: str) -> str:
    """Expand common abbreviations for TTS clarity.

    Replaces abbreviations like "Dr.", "Mr.", "vs." with their spoken forms
    ("Doctor", "Mister", "versus"). Uses word-boundary-aware matching to avoid
    partial replacements.

    For abbreviations that can end a sentence (etc., vs., e.g., i.e.), the
    trailing period is preserved when the abbreviation appears at a sentence
    boundary (end of string or followed by a newline).

    Args:
        text: Input text possibly containing abbreviations.

    Returns:
        Text with abbreviations expanded. The original string is not modified.
    """
    if not text:
        return text

    result = text
    for pattern, expansion, can_end_sentence in _ABBREVIATION_PATTERNS:
        if can_end_sentence:
            result = pattern.sub(_make_replacer(expansion, result), result)
        else:
            result = pattern.sub(expansion, result)
    return result


# ---------------------------------------------------------------------------
# Numbers to words
# ---------------------------------------------------------------------------

# Single digit and small number words (0-19)
_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]

# Tens words (20, 30, ..., 90)
_TENS = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]

# Ordinal forms for numbers 1-31 (index 0 is unused placeholder)
_ORDINALS = [
    "",  # 0 placeholder
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
    "twentieth",
    "twenty-first",
    "twenty-second",
    "twenty-third",
    "twenty-fourth",
    "twenty-fifth",
    "twenty-sixth",
    "twenty-seventh",
    "twenty-eighth",
    "twenty-ninth",
    "thirtieth",
    "thirty-first",
]


def _int_to_words(n: int) -> str:
    """Convert an integer 0-999 to its spoken English form.

    Args:
        n: Integer in range 0-999.

    Returns:
        English word representation (e.g., 42 -> "forty-two").
    """
    if n < 0 or n > 999:
        return str(n)

    if n < 20:
        return _ONES[n]

    if n < 100:
        tens_word = _TENS[n // 10]
        ones_digit = n % 10
        if ones_digit == 0:
            return tens_word
        return f"{tens_word}-{_ONES[ones_digit]}"

    # 100-999: "X hundred" or "X hundred Y"
    hundreds_digit = n // 100
    remainder = n % 100
    if remainder == 0:
        return f"{_ONES[hundreds_digit]} hundred"
    return f"{_ONES[hundreds_digit]} hundred {_int_to_words(remainder)}"


def _year_to_words(year: int) -> str:
    """Convert a year (1800-2099) to its spoken English form.

    Follows common English pronunciation conventions:
    - 1920 -> "nineteen-twenty"
    - 1900 -> "nineteen hundred"
    - 2000 -> "two thousand"
    - 2001 -> "two thousand one"
    - 2010 -> "twenty-ten"

    Args:
        year: Year in range 1800-2099.

    Returns:
        Spoken English form of the year.
    """
    if year == 2000:
        return "two thousand"
    if 2001 <= year <= 2009:
        return f"two thousand {_ONES[year - 2000]}"
    if 2010 <= year <= 2099:
        # "twenty-ten", "twenty-twenty-six", etc.
        return f"twenty-{_int_to_words(year - 2000)}"

    # 1800-1999: split into two two-digit groups
    # 1920 -> "nineteen" + "twenty"
    first_half = year // 100
    second_half = year % 100
    if second_half == 0:
        return f"{_int_to_words(first_half)} hundred"
    return f"{_int_to_words(first_half)}-{_int_to_words(second_half)}"


def _replace_dollar_amount(match: re.Match[str]) -> str:
    """Replace a dollar amount match with its spoken form.

    Handles formats: $5, $5.50, $3.05
    """
    dollars_str = match.group(1)
    cents_str = match.group(2)  # May be None if no cents part

    dollars = int(dollars_str)

    # _int_to_words only handles 0-999; let TTS handle larger amounts natively
    if dollars > 999:
        return match.group(0)

    dollars_word = _int_to_words(dollars)

    if cents_str is None:
        return f"{dollars_word} dollars"

    cents = int(cents_str)
    if cents == 0:
        return f"{dollars_word} dollars"

    cents_word = _int_to_words(cents)
    return f"{dollars_word} dollars and {cents_word} cents"


def _replace_decade(match: re.Match[str]) -> str:
    """Replace a decade like '1920s' with 'nineteen-twenties'."""
    year = int(match.group(1))
    year_words = _year_to_words(year)
    # Append the plural suffix to the last word
    # "nineteen-twenty" -> "nineteen-twenties"
    if year_words.endswith("y"):
        return year_words[:-1] + "ies"
    return year_words + "s"


def _replace_ordinal(match: re.Match[str]) -> str:
    """Replace an ordinal like '1st', '2nd', '3rd', '21st' with words."""
    num = int(match.group(1))
    if 1 <= num <= 31:
        return _ORDINALS[num]
    # Fallback: return original text for ordinals outside 1-31
    return match.group(0)


def _replace_year(match: re.Match[str]) -> str:
    """Replace a standalone four-digit year with its spoken form."""
    year = int(match.group(1))
    return _year_to_words(year)


def _replace_integer(match: re.Match[str]) -> str:
    """Replace a standalone integer 0-999 with its spoken form."""
    num = int(match.group(0))
    if 0 <= num <= 999:
        return _int_to_words(num)
    return match.group(0)


# Pre-compiled patterns for number conversions, applied in order.
# Order matters: more specific patterns (dollars, decades, ordinals, years)
# must be matched before generic integers.
_DOLLAR_PATTERN = re.compile(r"\$(\d+)(?:\.(\d{2}))?")
_DECADE_PATTERN = re.compile(r"\b(\d{4})s\b")
_ORDINAL_PATTERN = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b")
_YEAR_PATTERN = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_INTEGER_PATTERN = re.compile(r"(?<![\d.])\b(\d{1,3})\b(?![\d.])")


def numbers_to_words(text: str) -> str:
    """Convert numeric values to spoken-word equivalents.

    Handles the following number formats (in order of matching priority):
    1. Dollar amounts: $5, $5.50 -> "five dollars", "five dollars and fifty cents"
    2. Decades: 1920s -> "nineteen-twenties"
    3. Ordinals: 1st, 2nd, 3rd, 11th, 21st (up to 31st)
    4. Years: 1800-2099 -> spoken form (e.g., "nineteen-twenty")
    5. Integers: 0-999 -> word form

    Args:
        text: Input text possibly containing numbers.

    Returns:
        Text with numbers converted to words. The original string is not modified.
    """
    if not text:
        return text

    result = text

    # Apply patterns in order of specificity (most specific first)
    # to prevent generic patterns from consuming parts of specific ones.
    result = _DOLLAR_PATTERN.sub(_replace_dollar_amount, result)
    result = _DECADE_PATTERN.sub(_replace_decade, result)
    result = _ORDINAL_PATTERN.sub(_replace_ordinal, result)
    result = _YEAR_PATTERN.sub(_replace_year, result)
    result = _INTEGER_PATTERN.sub(_replace_integer, result)

    return result


# ---------------------------------------------------------------------------
# Pause markers
# ---------------------------------------------------------------------------


def insert_pause_markers(text: str) -> str:
    """Insert pause markers at natural dramatic breaks.

    Adds a unicode ellipsis ("\u2026") pause marker at the end of each paragraph
    (before double-newline paragraph breaks) to create natural pauses
    in TTS output. When the paragraph ends with sentence-ending punctuation
    (".", "!", "?"), the terminal punctuation is replaced rather than appended.

    Uses unicode ellipsis ("\u2026") instead of three dots ("...") for
    consistency with smooth_punctuation, which normalizes "..." to "\u2026".
    This ensures prepare_narration is idempotent.

    Single newlines within paragraphs are left untouched.

    The function is idempotent: paragraphs already ending with "..." or
    "\u2026" are not given an additional pause marker.

    Args:
        text: Input text with paragraph breaks.

    Returns:
        Text with pause markers inserted. The original string is not modified.
    """
    if not text:
        return text

    # Split on paragraph breaks (double newline)
    paragraphs = text.split("\n\n")

    if len(paragraphs) <= 1:
        return text

    result_parts = []
    for i, paragraph in enumerate(paragraphs):
        if i < len(paragraphs) - 1:
            # Add pause marker to end of paragraph if not already present
            stripped = paragraph.rstrip()
            if not stripped.endswith("...") and not stripped.endswith("\u2026"):
                if stripped.endswith((".", "!", "?")):
                    result_parts.append(stripped[:-1] + "\u2026")
                else:
                    result_parts.append(stripped + "\u2026")
            else:
                result_parts.append(stripped)
        else:
            # Last paragraph: no pause marker needed
            result_parts.append(paragraph)

    return "\n\n".join(result_parts)


# ---------------------------------------------------------------------------
# Smooth punctuation
# ---------------------------------------------------------------------------

# Em dash (U+2014) replaced with comma-space for natural speech flow
_EM_DASH_PATTERN = re.compile(r"\u2014")

# Three consecutive dots normalized to unicode ellipsis (U+2026)
_TRIPLE_DOT_PATTERN = re.compile(r"\.\.\.")

# Nested parentheticals: flatten "(text (inner))" to "(text, inner)"
# This handles one level of nesting.
_NESTED_PAREN_PATTERN = re.compile(r"\(([^()]*)\(([^()]*)\)([^()]*)\)")

# Footnote markers like [1], [2], [42]
_FOOTNOTE_PATTERN = re.compile(r"\[\d+\]")

# Double (or more) spaces collapsed to single space
_DOUBLE_SPACE_PATTERN = re.compile(r"  +")


def smooth_punctuation(text: str) -> str:
    """Smooth punctuation that trips up TTS engines.

    Applies the following transformations:
    1. Replace em dashes (U+2014) with ", " for natural speech pauses
    2. Normalize three dots "..." to unicode ellipsis (U+2026)
    3. Flatten nested parentheticals "(text (inner))" to "(text, inner)"
    4. Remove footnote markers like [1], [2]

    The function is idempotent: running it twice produces the same result.

    Args:
        text: Input text with potentially problematic punctuation.

    Returns:
        Text with smoothed punctuation. The original string is not modified.
    """
    if not text:
        return text

    result = text

    # 1. Replace em dashes with comma-space
    result = _EM_DASH_PATTERN.sub(", ", result)

    # 2. Normalize triple dots to unicode ellipsis
    result = _TRIPLE_DOT_PATTERN.sub("\u2026", result)

    # 3. Flatten nested parentheticals (apply until no more nesting)
    while _NESTED_PAREN_PATTERN.search(result):
        result = _NESTED_PAREN_PATTERN.sub(r"(\1\2\3)", result)

    # 4. Remove footnote markers
    result = _FOOTNOTE_PATTERN.sub("", result)

    # Clean up any double spaces introduced by removals
    result = _DOUBLE_SPACE_PATTERN.sub(" ", result)

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def prepare_narration(text: str) -> str:
    """Apply all narration prep transformations to prose text.

    This is the main entry point for narration preparation. It applies
    transformations in a specific order designed to avoid conflicts:

    1. expand_abbreviations — Must run first so abbreviation patterns
       (which contain dots) are resolved before other transformations.
    2. numbers_to_words — Converts numeric values after abbreviations
       are expanded, preventing interference with abbreviation dots.
    3. smooth_punctuation — Normalizes problematic punctuation after
       content transformations are complete.
    4. insert_pause_markers — Runs last to insert pauses at paragraph
       boundaries in the final text.

    Args:
        text: Original prose text.

    Returns:
        TTS-optimized narration text. The original text is never modified.
    """
    if not text:
        return text

    result = text
    result = expand_abbreviations(result)
    result = numbers_to_words(result)
    result = smooth_punctuation(result)
    result = insert_pause_markers(result)
    return result
