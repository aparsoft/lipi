"""Unit tests for lipi.extractor and lipi._quality."""

from pathlib import Path

import pytest
from lipi._quality import is_garbage_text
from lipi.extractor import extract_unicode_text


ROOT = Path(__file__).resolve().parent.parent


class TestIsGarbageText:
    """Tests for the is_garbage_text quality gate."""

    def test_clean_devanagari_is_not_garbage(self):
        text = "यह एक साफ़ हिंदी वाक्य है जिसमें कोई समस्या नहीं है" * 5
        is_garb, score, reason = is_garbage_text(text)
        assert is_garb is False
        assert score > 0.5

    def test_short_text_is_garbage(self):
        is_garb, score, reason = is_garbage_text("short")
        assert is_garb is True
        assert "too short" in reason.lower()

    def test_empty_text_is_garbage(self):
        is_garb, score, reason = is_garbage_text("")
        assert is_garb is True

    def test_mostly_punctuation_is_garbage(self):
        text = "!!! ??? ... ,,, ;;; ::: ((( )))" * 10
        is_garb, score, reason = is_garbage_text(text)
        assert is_garb is True
        assert "punctuation" in reason.lower()

    def test_garbage_unicode_is_detected(self):
        """Text with lots of non-letter, non-punctuation chars should be flagged."""
        text = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0b\x0c\x0e\x0f" * 10
        is_garb, score, reason = is_garbage_text(text)
        assert is_garb is True


class TestExtractUnicodeText:
    """Tests for extract_unicode_text (pypdf-based)."""

    def test_file_not_found(self):
        result = extract_unicode_text("/nonexistent/file.pdf")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_returns_expected_keys(self):
        """Even on error, result should have standard keys."""
        result = extract_unicode_text("/nonexistent/file.pdf")
        assert "filename" in result
        assert "total_pages" in result
        assert "pages" in result
        assert "full_text" in result

    def test_font_type_none_skips_conversion(self):
        """font_type='none' should skip all conversion."""
        # Just verify it doesn't crash
        result = extract_unicode_text("/nonexistent/file.pdf", font_type="none")
        assert isinstance(result, dict)

    def test_unknown_font_still_applies_generic_cleanup(self):
        pdf_path = ROOT / "temp" / "ihkr101.pdf"

        raw = extract_unicode_text(
            str(pdf_path),
            page_range=(1, 1),
            font_type="none",
            post_process=False,
        )
        cleaned = extract_unicode_text(
            str(pdf_path),
            page_range=(1, 1),
            font_type="auto",
            post_process=True,
        )

        assert cleaned["has_encoding_issues"] is False
        assert raw["pages"][1] != cleaned["pages"][1]
        assert "पश्श्िम" in raw["pages"][1]
        assert "पश्चिम" in cleaned["pages"][1]
