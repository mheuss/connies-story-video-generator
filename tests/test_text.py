"""Tests for story_video.utils.text — Text utilities and narration prep.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the text transformation functions.
"""

from story_video.utils.text import (
    expand_abbreviations,
    insert_pause_markers,
    numbers_to_words,
    prepare_narration,
    smooth_punctuation,
)

# ---------------------------------------------------------------------------
# expand_abbreviations tests
# ---------------------------------------------------------------------------


class TestExpandAbbreviations:
    """expand_abbreviations — Expand common abbreviations for TTS clarity."""

    def test_empty_string(self):
        assert expand_abbreviations("") == ""

    def test_no_abbreviations(self):
        assert expand_abbreviations("The quick brown fox.") == "The quick brown fox."

    def test_dr_expanded(self):
        assert expand_abbreviations("Dr. Smith arrived.") == "Doctor Smith arrived."

    def test_mr_expanded(self):
        assert expand_abbreviations("Mr. Jones left.") == "Mister Jones left."

    def test_mrs_expanded(self):
        assert expand_abbreviations("Mrs. Jones left.") == "Missus Jones left."

    def test_ms_expanded(self):
        assert expand_abbreviations("Ms. Jones left.") == "Mizz Jones left."

    def test_st_expanded(self):
        assert expand_abbreviations("St. Patrick's Day.") == "Saint Patrick's Day."

    def test_vs_expanded(self):
        assert expand_abbreviations("Good vs. evil.") == "Good versus evil."

    def test_etc_expanded(self):
        assert expand_abbreviations("Cats, dogs, etc.") == "Cats, dogs, et cetera."

    def test_eg_expanded(self):
        assert expand_abbreviations("Animals (e.g. cats) are cute.") == (
            "Animals (for example cats) are cute."
        )

    def test_ie_expanded(self):
        assert expand_abbreviations("The best one (i.e. mine) won.") == (
            "The best one (that is mine) won."
        )

    def test_multiple_abbreviations_in_one_string(self):
        result = expand_abbreviations("Dr. Smith vs. Mr. Jones.")
        assert result == "Doctor Smith versus Mister Jones."

    def test_preserves_case_of_surrounding_text(self):
        result = expand_abbreviations("Meet Dr. SMITH today.")
        assert result == "Meet Doctor SMITH today."

    def test_does_not_modify_original(self):
        original = "Dr. Smith arrived."
        _ = expand_abbreviations(original)
        assert original == "Dr. Smith arrived."

    def test_idempotent(self):
        """Running twice should produce the same result as running once."""
        text = "Dr. Smith vs. Mr. Jones."
        once = expand_abbreviations(text)
        twice = expand_abbreviations(once)
        assert once == twice


# ---------------------------------------------------------------------------
# numbers_to_words tests
# ---------------------------------------------------------------------------


class TestNumbersToWords:
    """numbers_to_words — Convert numeric values to spoken-word equivalents."""

    def test_empty_string(self):
        assert numbers_to_words("") == ""

    def test_no_numbers(self):
        assert numbers_to_words("Hello world.") == "Hello world."

    def test_single_digit(self):
        assert numbers_to_words("She had 3 cats.") == "She had three cats."

    def test_zero(self):
        assert numbers_to_words("He had 0 friends.") == "He had zero friends."

    def test_two_digit_number(self):
        assert numbers_to_words("There were 42 people.") == "There were forty-two people."

    def test_hundred(self):
        assert numbers_to_words("The army had 100 soldiers.") == (
            "The army had one hundred soldiers."
        )

    def test_three_digit_number(self):
        assert numbers_to_words("He ran 500 miles.") == "He ran five hundred miles."

    def test_complex_three_digit_number(self):
        assert numbers_to_words("Page 347 was missing.") == (
            "Page three hundred forty-seven was missing."
        )

    def test_year_four_digits(self):
        result = numbers_to_words("It was 1920 when it happened.")
        assert result == "It was nineteen-twenty when it happened."

    def test_year_2000(self):
        result = numbers_to_words("In 2000, things changed.")
        assert result == "In two thousand, things changed."

    def test_year_2001(self):
        result = numbers_to_words("In 2001 the towers fell.")
        assert result == "In two thousand one the towers fell."

    def test_year_2010(self):
        result = numbers_to_words("By 2010 everything was digital.")
        assert result == "By twenty-ten everything was digital."

    def test_decade(self):
        result = numbers_to_words("The 1920s were roaring.")
        assert result == "The nineteen-twenties were roaring."

    def test_ordinal_1st(self):
        assert numbers_to_words("The 1st place winner.") == "The first place winner."

    def test_ordinal_2nd(self):
        assert numbers_to_words("The 2nd attempt.") == "The second attempt."

    def test_ordinal_3rd(self):
        assert (
            numbers_to_words("The 3rd time.") == "The third attempt."
            or numbers_to_words("The 3rd time.") == "The third time."
        )

    def test_ordinal_3rd_correct(self):
        assert numbers_to_words("The 3rd time.") == "The third time."

    def test_ordinal_11th(self):
        assert numbers_to_words("The 11th hour.") == "The eleventh hour."

    def test_ordinal_21st(self):
        assert numbers_to_words("The 21st century.") == "The twenty-first century."

    def test_dollar_amount_integer(self):
        result = numbers_to_words("It cost $5 to enter.")
        assert result == "It cost five dollars to enter."

    def test_dollar_amount_with_cents(self):
        result = numbers_to_words("It cost $5.50 to enter.")
        assert result == "It cost five dollars and fifty cents to enter."

    def test_dollar_amount_with_single_cent_digit(self):
        """$3.05 should be 'three dollars and five cents'."""
        result = numbers_to_words("It cost $3.05 to buy.")
        assert result == "It cost three dollars and five cents to buy."

    def test_multiple_numbers_in_one_string(self):
        result = numbers_to_words("He had 3 cats and 7 dogs.")
        assert result == "He had three cats and seven dogs."

    def test_does_not_modify_original(self):
        original = "There are 3 cats."
        _ = numbers_to_words(original)
        assert original == "There are 3 cats."

    def test_number_at_start_of_string(self):
        assert numbers_to_words("5 cats ran away.") == "five cats ran away."

    def test_number_at_end_of_string(self):
        assert numbers_to_words("She scored 10") == "She scored ten"


# ---------------------------------------------------------------------------
# insert_pause_markers tests
# ---------------------------------------------------------------------------


class TestInsertPauseMarkers:
    """insert_pause_markers — Insert pause markers at natural dramatic breaks."""

    def test_empty_string(self):
        assert insert_pause_markers("") == ""

    def test_no_paragraphs(self):
        """Single paragraph text should be unchanged."""
        text = "The cat sat on the mat."
        assert insert_pause_markers(text) == text

    def test_paragraph_break_gets_pause(self):
        """Double newline paragraph breaks should get a pause marker."""
        text = "First paragraph.\n\nSecond paragraph."
        result = insert_pause_markers(text)
        assert "..." in result or "\u2026" in result

    def test_multiple_paragraph_breaks(self):
        text = "One.\n\nTwo.\n\nThree."
        result = insert_pause_markers(text)
        # Each paragraph break should have a pause marker
        parts = result.split("\n\n")
        # The first paragraph should end with a pause indicator
        assert parts[0].rstrip().endswith("...")

    def test_preserves_single_newlines(self):
        """Single newlines (within a paragraph) should not get pause markers."""
        text = "Line one.\nLine two."
        assert insert_pause_markers(text) == text

    def test_does_not_modify_original(self):
        original = "First.\n\nSecond."
        _ = insert_pause_markers(original)
        assert original == "First.\n\nSecond."

    def test_idempotent(self):
        """Running twice should not add extra pause markers."""
        text = "First paragraph.\n\nSecond paragraph."
        once = insert_pause_markers(text)
        twice = insert_pause_markers(once)
        assert once == twice


# ---------------------------------------------------------------------------
# smooth_punctuation tests
# ---------------------------------------------------------------------------


class TestSmoothPunctuation:
    """smooth_punctuation — Smooth punctuation that trips up TTS engines."""

    def test_empty_string(self):
        assert smooth_punctuation("") == ""

    def test_no_problem_punctuation(self):
        assert smooth_punctuation("Hello, world.") == "Hello, world."

    def test_em_dash_replaced(self):
        """Em dash should be replaced with comma-space for natural speech."""
        result = smooth_punctuation("The house\u2014the old one\u2014was empty.")
        assert "\u2014" not in result
        # Should have comma or pause instead
        assert ", " in result or "..." in result

    def test_triple_dot_normalized(self):
        """Three dots should be normalized to a unicode ellipsis."""
        result = smooth_punctuation("Wait... what?")
        assert "\u2026" in result
        assert "..." not in result

    def test_unicode_ellipsis_preserved(self):
        """Existing unicode ellipsis should stay."""
        result = smooth_punctuation("Wait\u2026 what?")
        assert "\u2026" in result

    def test_parenthetical_simplified(self):
        """Nested parentheticals should be simplified."""
        result = smooth_punctuation("The cat (a very old one (maybe 15)) slept.")
        assert "((" not in result
        assert "))" not in result

    def test_footnote_markers_removed(self):
        """Footnote markers like [1] should be removed."""
        result = smooth_punctuation("The theory[1] was proven.")
        assert "[1]" not in result
        assert "The theory" in result
        assert "was proven." in result

    def test_multiple_footnote_markers(self):
        result = smooth_punctuation("First[1] and second[2] points.")
        assert "[1]" not in result
        assert "[2]" not in result

    def test_does_not_modify_original(self):
        original = "Wait... what?"
        _ = smooth_punctuation(original)
        assert original == "Wait... what?"

    def test_idempotent(self):
        """Running twice should produce the same result as running once."""
        text = "The house\u2014the old one\u2014was empty... right?"
        once = smooth_punctuation(text)
        twice = smooth_punctuation(once)
        assert once == twice


# ---------------------------------------------------------------------------
# prepare_narration integration tests
# ---------------------------------------------------------------------------


class TestPrepareNarration:
    """prepare_narration — Full pipeline integration test."""

    def test_empty_string(self):
        assert prepare_narration("") == ""

    def test_no_transformations_needed(self):
        """Plain text without abbreviations, numbers, or special punctuation."""
        text = "The quick brown fox jumped over the lazy dog."
        assert prepare_narration(text) == text

    def test_combines_all_transformations(self):
        """A string needing all four transformations."""
        text = "Dr. Smith had 3 cats... He left\u2014forever.\n\nThe end."
        result = prepare_narration(text)
        # Abbreviation expanded
        assert "Doctor" in result
        # Number converted
        assert "three" in result
        # Ellipsis normalized
        assert "..." not in result or "\u2026" in result
        # Em dash handled
        assert "\u2014" not in result
        # Paragraph pause marker present
        assert "..." in result or "\u2026" in result

    def test_does_not_modify_original(self):
        original = "Dr. Smith had 3 cats."
        _ = prepare_narration(original)
        assert original == "Dr. Smith had 3 cats."

    def test_abbreviation_then_number(self):
        """Abbreviations and numbers co-occur."""
        result = prepare_narration("Mr. Brown ate 5 apples.")
        assert "Mister" in result
        assert "five" in result

    def test_year_and_abbreviation(self):
        result = prepare_narration("In 1920, Dr. Lee discovered it.")
        assert "nineteen-twenty" in result
        assert "Doctor" in result

    def test_dollar_and_abbreviation(self):
        result = prepare_narration("Mr. Jones paid $10 for it.")
        assert "Mister" in result
        assert "ten dollars" in result

    def test_complex_narration(self):
        """A more realistic passage requiring multiple transformations."""
        text = (
            "Dr. Smith arrived on the 1st of May, 1920. "
            'He said, "The cost is $5.50 vs. the usual price."\n\n'
            "Mrs. Jones disagreed... She thought it was too much."
        )
        result = prepare_narration(text)
        assert "Doctor" in result
        assert "first" in result
        assert "nineteen-twenty" in result
        assert "five dollars and fifty cents" in result
        assert "versus" in result
        assert "Missus" in result

    def test_transformation_order_matters(self):
        """Verify that transformations are applied in the correct order.

        Abbreviation expansion must happen before number conversion, because
        abbreviation patterns like 'Dr.' could otherwise be mangled if numbers
        were converted first in adjacent text.
        """
        text = "Dr. 3rd Street."
        result = prepare_narration(text)
        assert "Doctor" in result
        assert "third" in result
