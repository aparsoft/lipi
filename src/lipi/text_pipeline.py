"""Helpers for cleaning already-extracted Hindi text without re-reading PDFs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from lipi.correction import HindiLexiconCorrector, build_contextual_lexicon
from lipi.preprocessor import HindiPreprocessor


def clean_extracted_text(
    text: str,
    font_type: str = "auto",
    correction_mode: str = "safe",
    lexicon_path: Optional[str] = None,
    contextual_texts: Optional[Sequence[str]] = None,
    bootstrap_lexicon: bool = False,
    min_token_length: int = 4,
) -> Dict[str, Any]:
    """
    Clean already-extracted Hindi text using the same pipeline as PDF extraction.

    This is intended for corpora where the PDFs have already been processed once
    and only the extracted raw text is available.

    Args:
        text: Raw extracted text.
        font_type: ``"auto"``, ``"krutidev"``, ``"chanakya"``, or ``"none"``.
        correction_mode: ``"none"``, ``"safe"`` (exact normalized matches only),
            or ``"aggressive"`` (bounded fuzzy lexicon correction).
        lexicon_path: Optional file with extra Hindi lexicon words.
        contextual_texts: Optional related texts from the same corpus/book used to
            bootstrap repeated clean words into the lexicon.
        bootstrap_lexicon: When true, bootstrap a contextual lexicon from
            ``contextual_texts`` or from ``text`` itself if no context is supplied.
        min_token_length: Minimum token length considered by the lexicon stage.

    Returns:
        Dict with diagnostics and the final ``cleaned_text``.
    """
    if correction_mode not in {"none", "safe", "aggressive"}:
        raise ValueError("correction_mode must be one of: none, safe, aggressive")

    has_legacy_encoding, detected_font_type = HindiPreprocessor.detect_encoding(text)
    is_scrambled_devanagari = (
        detected_font_type == "unknown" and HindiPreprocessor.detect_scrambled_devanagari(text)
    )
    reported_font_type = "scrambled_devanagari" if is_scrambled_devanagari else detected_font_type

    effective_font_type = font_type
    if font_type == "auto":
        effective_font_type = reported_font_type

    stages_applied: list[str] = []
    cleaned_text = text
    artifact_count_before = HindiPreprocessor.count_artifacts(text)["total"]

    if cleaned_text and effective_font_type not in ("unknown", "none", "scrambled_devanagari"):
        cleaned_text = HindiPreprocessor.convert(cleaned_text, effective_font_type)
        stages_applied.append(f"convert:{effective_font_type}")

    if cleaned_text and effective_font_type != "none":
        # The CC -> Cि repair is correct ONLY for legacy-font extraction where
        # a lost ि-matra surfaces as a doubled consonant. For clean / scrambled
        # Devanagari it damages real Hindi (रुककर, महाकुंभ, समझ, हमला) — leave
        # those tokens to the lexicon stage.
        legacy_font_path = effective_font_type in ("krutidev", "chanakya", "walkman_chanakya")
        cleaned_text = HindiPreprocessor.post_process(
            cleaned_text,
            repair_doubled_consonant_imatra=legacy_font_path,
        )
        stages_applied.append("post_process")

    correction_stats = {
        "tokens_seen": 0,
        "tokens_considered": 0,
        "corrected_tokens": 0,
        "corrections": [],
        "lexicon_size": 0,
    }
    contextual_lexicon_size = 0

    if cleaned_text and correction_mode != "none":
        max_distance = 0 if correction_mode == "safe" else 2
        corrector = HindiLexiconCorrector(
            lexicon_path=lexicon_path,
            max_distance=max_distance,
        )

        if contextual_texts is not None or bootstrap_lexicon:
            seed_texts = list(contextual_texts or [cleaned_text])
            contextual_words = build_contextual_lexicon(
                seed_texts,
                base_lexicon=set(corrector.lexicon),
            )
            corrector.add_words(contextual_words)
            contextual_lexicon_size = len(contextual_words)

        correction = corrector.correct_text(
            cleaned_text,
            min_token_length=min_token_length,
        )
        cleaned_text = correction["text"]
        correction_stats = correction["stats"]
        stages_applied.append(f"lexicon:{correction_mode}")

    artifact_count_after = HindiPreprocessor.count_artifacts(cleaned_text)["total"]

    return {
        "has_encoding_issues": has_legacy_encoding or is_scrambled_devanagari,
        "detected_font_type": reported_font_type,
        "effective_font_type": effective_font_type,
        "is_scrambled_devanagari": is_scrambled_devanagari,
        "input_char_count": len(text),
        "output_char_count": len(cleaned_text),
        "artifact_count_before": artifact_count_before,
        "artifact_count_after": artifact_count_after,
        "artifacts_removed": artifact_count_before - artifact_count_after,
        "correction_mode": correction_mode,
        "contextual_lexicon_size": contextual_lexicon_size,
        "correction_stats": correction_stats,
        "stages_applied": stages_applied,
        "cleaned_text": cleaned_text,
    }
