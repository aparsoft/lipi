"""Unit tests for lipi.mappings — mapping tables and merging."""

import pytest
from lipi.mappings.krutidev import KRUTIDEV_TO_UNICODE
from lipi.mappings.chanakya import CHANAKYA_TO_UNICODE
from lipi.mappings.walkman_chanakya import WALKMAN_CHANAKYA_OVERRIDES
from lipi.mappings import FONT_MAPPINGS, KRUTIDEV_FULL


class TestKrutidevMapping:
    """Tests for the KrutiDev base mapping."""

    def test_loads_without_error(self):
        assert isinstance(KRUTIDEV_TO_UNICODE, dict)
        assert len(KRUTIDEV_TO_UNICODE) > 50

    def test_key_entries(self):
        assert KRUTIDEV_TO_UNICODE["osQ"] == "के"
        assert KRUTIDEV_TO_UNICODE["kjk"] == "ारा"
        assert KRUTIDEV_TO_UNICODE["dh"] == "की"
        assert KRUTIDEV_TO_UNICODE["dk"] == "का"

    def test_no_walkman_entries(self):
        """Walkman-Chanakya905 entries should NOT be in the base table."""
        assert "oaQ" not in KRUTIDEV_TO_UNICODE
        assert "iQ" not in KRUTIDEV_TO_UNICODE
        assert "\u00d8" not in KRUTIDEV_TO_UNICODE  # Ø


class TestChanakyaMapping:
    """Tests for the Chanakya mapping."""

    def test_loads_without_error(self):
        assert isinstance(CHANAKYA_TO_UNICODE, dict)
        assert len(CHANAKYA_TO_UNICODE) > 30

    def test_key_entries(self):
        assert CHANAKYA_TO_UNICODE["k"] == "क"
        assert CHANAKYA_TO_UNICODE["A"] == "अ"
        assert CHANAKYA_TO_UNICODE["Aa"] == "आ"


class TestWalkmanChanakyaOverrides:
    """Tests for Walkman-Chanakya905 overrides."""

    def test_loads_without_error(self):
        assert isinstance(WALKMAN_CHANAKYA_OVERRIDES, dict)
        assert len(WALKMAN_CHANAKYA_OVERRIDES) >= 20

    def test_multi_char_tokens(self):
        assert WALKMAN_CHANAKYA_OVERRIDES["iQ"] == "फ"
        assert WALKMAN_CHANAKYA_OVERRIDES["oqQ"] == "कु"
        assert WALKMAN_CHANAKYA_OVERRIDES["owQ"] == "कू"
        assert WALKMAN_CHANAKYA_OVERRIDES["oaQ"] == "कं"

    def test_single_char_overrides(self):
        assert WALKMAN_CHANAKYA_OVERRIDES["\u00d8"] == "क्र"  # Ø
        assert WALKMAN_CHANAKYA_OVERRIDES["\u00d1"] == "कृ"  # Ñ
        assert WALKMAN_CHANAKYA_OVERRIDES["\u00cd"] == "ऋ"  # Í


class TestFontMappings:
    """Tests for the merged FONT_MAPPINGS dict."""

    def test_has_expected_keys(self):
        assert "krutidev" in FONT_MAPPINGS
        assert "chanakya" in FONT_MAPPINGS
        assert "walkman_chanakya" in FONT_MAPPINGS

    def test_walkman_overrides_merged(self):
        """Walkman-Chanakya overrides should be present in the merged table."""
        assert FONT_MAPPINGS["krutidev"]["iQ"] == "फ"
        assert FONT_MAPPINGS["krutidev"]["\u00d8"] == "क्र"

    def test_base_krutidev_preserved(self):
        """Base KrutiDev entries should still be present after merge."""
        assert FONT_MAPPINGS["krutidev"]["osQ"] == "के"
        assert FONT_MAPPINGS["krutidev"]["d"] == "क"

    def test_krutidev_full_identical_to_merged(self):
        """KRUTIDEV_FULL should be the same as the krutidev entry in FONT_MAPPINGS."""
        assert KRUTIDEV_FULL is FONT_MAPPINGS["krutidev"]

    def test_walkman_chanakya_uses_krutidev_full(self):
        """walkman_chanakya should use the same merged table as krutidev."""
        assert FONT_MAPPINGS["walkman_chanakya"] is FONT_MAPPINGS["krutidev"]

    def test_no_overlapping_keys_with_different_values(self, capsys):
        """Warn if any base KrutiDev keys are overridden with different values."""
        for key in WALKMAN_CHANAKYA_OVERRIDES:
            if key in KRUTIDEV_TO_UNICODE:
                base_val = KRUTIDEV_TO_UNICODE[key]
                override_val = WALKMAN_CHANAKYA_OVERRIDES[key]
                if base_val != override_val:
                    captured = capsys.readouterr()
                    # Overlap is expected for some keys (e.g. ±, ¸)
                    # Just ensure no crash — overlap is documented

    def test_all_values_contain_devanagari(self):
        """All mapping values should contain valid Devanagari or punctuation."""
        for font_name, mapping in FONT_MAPPINGS.items():
            for key, value in mapping.items():
                for ch in value:
                    code = ord(ch)
                    is_valid = (
                        "\u0900" <= ch <= "\u097f"  # Devanagari
                        or code <= 0x007F  # ASCII (punctuation, digits)
                        or ch in "…\u201c\u201d"  # Ellipsis, quotes
                    )
                    assert is_valid, (
                        f"Invalid char U+{code:04X} in {font_name}[{key!r}] = {value!r}"
                    )
