"""Unit tests for lipi.preprocessor — HindiPreprocessor class."""

import pytest
from lipi.preprocessor import HindiPreprocessor


class TestDetectEncoding:
    """Tests for HindiPreprocessor.detect_encoding()."""

    def test_detects_krutidev(self):
        text = "eSaus gSjku gksdj ns[kk osQ dk Fk esa Hk"
        has_issues, font_type = HindiPreprocessor.detect_encoding(text)
        assert has_issues is True
        assert font_type == "krutidev"

    def test_clean_unicode_returns_false(self):
        text = "यह एक साफ़ हिंदी वाक्य है"
        has_issues, font_type = HindiPreprocessor.detect_encoding(text)
        assert has_issues is False
        assert font_type == "unknown"

    def test_empty_string(self):
        has_issues, font_type = HindiPreprocessor.detect_encoding("")
        assert has_issues is False
        assert font_type == "unknown"

    def test_mostly_devanagari(self):
        """Text already >30% Devanagari should not be flagged."""
        text = "मैंने xyz हैरान abc होकर pqr देखा"
        has_issues, font_type = HindiPreprocessor.detect_encoding(text)
        assert has_issues is False

    def test_detects_chanakya(self):
        text = "Aa ao AO A \xac \xa4 k g c j t d"
        has_issues, font_type = HindiPreprocessor.detect_encoding(text)
        assert has_issues is True
        assert font_type == "chanakya"


class TestConvert:
    """Tests for HindiPreprocessor.convert()."""

    def test_krutidev_basic_token(self):
        assert HindiPreprocessor.convert("osQ", font_type="krutidev") == "के"

    def test_krutidev_iQ_token(self):
        """Walkman-Chanakya905 override: iQ → फ"""
        assert HindiPreprocessor.convert("iQ", font_type="krutidev") == "फ"

    def test_krutidev_oqQN(self):
        """oqQ is a multi-char Walkman token: oqQN → कु + छ"""
        result = HindiPreprocessor.convert("oqQN", font_type="krutidev")
        assert "कु" in result
        assert "छ" in result

    def test_auto_detect_krutidev(self):
        result = HindiPreprocessor.convert("osQ dk Fk", font_type="auto")
        assert "के" in result
        assert "का" in result

    def test_preserves_devanagari(self):
        """Existing Devanagari characters should pass through unchanged."""
        text = "मैंने xyz हैरान"
        result = HindiPreprocessor.convert(text, font_type="krutidev")
        assert "मैंने" in result
        assert "हैरान" in result

    def test_empty_string(self):
        assert HindiPreprocessor.convert("", font_type="krutidev") == ""

    def test_unknown_passthrough(self):
        """Characters not in the mapping should pass through as-is."""
        result = HindiPreprocessor.convert("@#$^", font_type="krutidev")
        assert "@#$^" == result

    def test_chanakya_conversion(self):
        result = HindiPreprocessor.convert("k", font_type="chanakya")
        assert result == "क"


class TestIMatraReordering:
    """Tests for i-matra reordering in KrutiDev conversion."""

    def test_basic_imatra_reorder(self):
        # ि before क should move after
        result = HindiPreprocessor.convert("fd", font_type="krutidev")
        assert result == "कि"

    def test_imatra_with_anusvara(self):
        # िं before क should move after
        result = HindiPreprocessor.convert("fad", font_type="krutidev")
        assert "किं" in result

    def test_no_reorder_for_chanakya(self):
        """Chanakya should NOT apply i-matra reordering."""
        # Just verify it doesn't crash — Chanakya uses different mapping
        result = HindiPreprocessor.convert("f k", font_type="chanakya")
        assert isinstance(result, str)


class TestPostProcess:
    """Tests for HindiPreprocessor.post_process()."""

    def test_doubled_aa_matra(self):
        assert HindiPreprocessor.post_process("ाा") == "ा"

    def test_doubled_i_matra(self):
        assert HindiPreprocessor.post_process("िि") == "ि"

    def test_doubled_ii_matra(self):
        assert HindiPreprocessor.post_process("ीी") == "ी"

    def test_aur_correction(self):
        assert HindiPreprocessor.post_process("अौर") == "और"

    def test_aar_correction(self):
        assert HindiPreprocessor.post_process("अार") == "आर"

    def test_ek_nukta_correction(self):
        assert HindiPreprocessor.post_process("एक़") == "एक"

    def test_repairs_split_marks_and_conjuncts(self):
        assert HindiPreprocessor.post_process("प्रस् त ुत") == "प्रस्तुत"
        assert HindiPreprocessor.post_process("स् क ूल") == "स्कूल"

    def test_repairs_duplicate_consonant_imatra_patterns(self):
        assert HindiPreprocessor.post_process("कक ं") == "किं"
        assert HindiPreprocessor.post_process("ववक") == "विक"
        assert HindiPreprocessor.post_process("णणय") == "णिय"
        assert HindiPreprocessor.post_process("ससय") == "सिय"

    def test_repairs_generic_conjunct_and_nukta_patterns(self):
        assert HindiPreprocessor.post_process("श्श्िम") == "श्चिम"
        assert HindiPreprocessor.post_process("डड़त") == "ड़ित"

    def test_empty_string(self):
        assert HindiPreprocessor.post_process("") == ""


class TestCorrectHindiText:
    """End-to-end tests for correct_hindi_text()."""

    def test_known_sentence(self):
        result = HindiPreprocessor.correct_hindi_text("osQ dk Fk", font_type="krutidev")
        assert "के" in result
        assert "का" in result

    def test_auto_detect_and_convert(self):
        result = HindiPreprocessor.correct_hindi_text("eSaus gSjku gksdj ns[kk", font_type="auto")
        # Should contain Devanagari characters
        has_devanagari = any("\u0900" <= ch <= "\u097f" for ch in result)
        assert has_devanagari


class TestGetMapping:
    """Tests for HindiPreprocessor.get_mapping()."""

    def test_krutidev_mapping(self):
        mapping = HindiPreprocessor.get_mapping("krutidev")
        assert isinstance(mapping, dict)
        assert mapping["osQ"] == "के"

    def test_chanakya_mapping(self):
        mapping = HindiPreprocessor.get_mapping("chanakya")
        assert isinstance(mapping, dict)
        assert mapping["k"] == "क"

    def test_walkman_overrides_in_mapping(self):
        mapping = HindiPreprocessor.get_mapping("krutidev")
        assert "iQ" in mapping
        assert mapping["iQ"] == "फ"
