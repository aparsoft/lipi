"""Tests for cleaning already-extracted raw text."""

from lipi import clean_extracted_text


def test_clean_extracted_text_repairs_unicode_artifacts_in_safe_mode():
    raw_text = "भाषा संंगम\nशब््दोों की सूची"

    result = clean_extracted_text(raw_text, correction_mode="safe")

    assert result["artifact_count_after"] < result["artifact_count_before"]
    assert "भाषा संगम" in result["cleaned_text"]
    assert "शब्दों" in result["cleaned_text"]
    assert result["stages_applied"] == ["post_process", "lexicon:safe"]


def test_clean_extracted_text_converts_legacy_font_input():
    raw_text = "eSaus gSjku gksdj ns[kk osQ dk Fk esa Hk"

    result = clean_extracted_text(raw_text, correction_mode="none")

    assert result["detected_font_type"] == "krutidev"
    assert result["has_encoding_issues"] is True
    assert result["stages_applied"] == ["convert:krutidev", "post_process"]
    assert any("\u0900" <= ch <= "\u097f" for ch in result["cleaned_text"])


def test_clean_extracted_text_collapses_duplicated_auxiliary_tokens():
    raw_text = "यह सही हैहै और वह वहाँ थाथा"

    result = clean_extracted_text(raw_text, correction_mode="none")

    assert result["cleaned_text"] == "यह सही है और वह वहाँ था"
    assert result["stages_applied"] == ["post_process"]
