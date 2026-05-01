"""
Text quality gate for PDF extraction results.

Detects garbage text produced by font encoding failures in Hindi/Indic PDFs
using character ratio analysis.
"""

from typing import Tuple


def is_garbage_text(text: str) -> Tuple[bool, float, str]:
    """
    Detect if extracted text is garbage (font encoding issues).

    Common with Hindi/Indic PDFs that have custom font mappings.

    Args:
        text: Extracted text to analyze.

    Returns:
        (is_garbage, quality_score, reason)
    """
    if not text or len(text.strip()) < 50:
        return (True, 0.0, "Text too short (< 50 chars)")

    total_chars = 0
    punctuation_chars = 0
    garbage_chars = 0
    letter_chars = 0

    for char in text:
        if not char.strip():
            continue
        total_chars += 1
        code = ord(char)

        # Punctuation / separators
        if char in ".,!?;:()[]{}\"'-=/)" or (0x2000 <= code <= 0x206F):
            punctuation_chars += 1
            continue

        # Digits
        if 0x0030 <= code <= 0x0039:
            continue

        # Valid letter ranges (Latin + Indic scripts)
        is_valid_letter = (
            (0x0041 <= code <= 0x005A)  # Uppercase Latin
            or (0x0061 <= code <= 0x007A)  # Lowercase Latin
            or (0x0900 <= code <= 0x097F)  # Devanagari
            or (0x0980 <= code <= 0x09FF)  # Bengali
            or (0x0A00 <= code <= 0x0A7F)  # Gurmukhi
            or (0x0A80 <= code <= 0x0AFF)  # Gujarati
            or (0x0B00 <= code <= 0x0B7F)  # Oriya
            or (0x0B80 <= code <= 0x0BFF)  # Tamil
            or (0x0C00 <= code <= 0x0C7F)  # Telugu
            or (0x0C80 <= code <= 0x0CFF)  # Kannada
            or (0x0D00 <= code <= 0x0D7F)  # Malayalam
        )

        if is_valid_letter:
            letter_chars += 1
        else:
            garbage_chars += 1

    if total_chars == 0:
        return (True, 0.0, "No characters found")

    punctuation_ratio = punctuation_chars / total_chars
    letter_ratio = letter_chars / total_chars
    garbage_ratio = garbage_chars / total_chars

    if punctuation_ratio > 0.5:
        return (True, 1.0 - punctuation_ratio, f"Too much punctuation: {punctuation_ratio:.1%}")

    if letter_ratio < 0.4:
        return (True, letter_ratio, f"Too few letters: {letter_ratio:.1%}")

    if garbage_ratio > 0.3:
        return (True, 1.0 - garbage_ratio, f"Too many unreadable characters: {garbage_ratio:.1%}")

    quality_score = (
        letter_ratio * 0.7
        + (1.0 - garbage_ratio) * 0.2
        + (1.0 - punctuation_ratio) * 0.1
    )

    return (False, quality_score, "Text quality acceptable")
