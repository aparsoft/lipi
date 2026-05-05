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


def test_scrambled_devanagari_does_not_inject_imatra_into_real_words():
    """Regression: prose words with naturally doubled consonants must survive.

    The CC -> Cि repair is correct for legacy-font extraction (lost ि-matra
    surfaces as a doubled consonant) but destroys correct Hindi like
    रुककर, महाकुंभ, समझ, हमला when applied to scrambled-Devanagari PDFs.
    """
    raw_text = (
        "थोड़ी देर रुककर वह चौंककर उठा। "
        "जगन मास्टर के घर महाकुंभ हो गया। "
        "किसी ने हमला बोल दिया। "
        "मुझे यह बात समझ आ गई।"
    )

    result = clean_extracted_text(raw_text, correction_mode="safe")

    cleaned = result["cleaned_text"]
    assert "रुककर" in cleaned and "रुकिर" not in cleaned
    assert "चौंककर" in cleaned and "चौंकिर" not in cleaned
    assert "महाकुंभ" in cleaned and "मिहाकुंभ" not in cleaned
    assert "हमला" in cleaned and "हमिला" not in cleaned
    assert "समझ" in cleaned and "समिझ" not in cleaned


def test_scrambled_devanagari_still_collapses_doubled_halants_and_marks():
    """The other artifact repairs (NOT the i-injection) must still run."""
    raw_text = "जन््मम की कथा दृश््योों में स््थथित प्रश््‍ननोोत्तर हैहै।"

    result = clean_extracted_text(raw_text, correction_mode="none")

    cleaned = result["cleaned_text"]
    assert "जन्म" in cleaned
    assert "स्थित" in cleaned
    assert "हैहै" not in cleaned
    assert "है।" in cleaned


def test_legacy_font_path_preserves_imatra_repair():
    """Legacy KrutiDev/Chanakya pipeline still needs the CC -> Cि rule."""
    from lipi.preprocessor import HindiPreprocessor

    # Default (legacy-font) behaviour: rule active.
    assert HindiPreprocessor.post_process("ववक") == "विक"
    assert HindiPreprocessor.post_process("कक ं") == "किं"

    # Scrambled-Devanagari path: rule disabled.
    assert HindiPreprocessor.post_process(
        "रुककर", repair_doubled_consonant_imatra=False
    ) == "रुककर"
    assert HindiPreprocessor.post_process(
        "महाकुंभ", repair_doubled_consonant_imatra=False
    ) == "महाकुंभ"
