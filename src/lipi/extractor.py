"""
PDF text extraction with legacy Hindi font auto-conversion.

Uses pypdf for extraction and applies legacy-font normalization on the
extracted text.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, Tuple

from pypdf import PdfReader

from lipi.correction import HindiLexiconCorrector, build_contextual_lexicon
from lipi.preprocessor import HindiPreprocessor

logger = logging.getLogger(__name__)


def _load_text_overrides(overrides_path: Optional[str]) -> Dict[str, Any]:
    """Load optional source-specific text replacements from JSON."""
    if not overrides_path:
        return {}

    with open(overrides_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Overrides file must contain a JSON object")
    return data


def _apply_replacements(text: str, rules: Dict[str, Any]) -> Tuple[str, int]:
    """Apply literal replacements from one rule set."""
    if not text or not rules:
        return text, 0

    replacements = rules.get("replacements", [])
    if not isinstance(replacements, list):
        raise ValueError("Overrides 'replacements' must be a list of [from, to] pairs")

    updated = text
    applied = 0
    for pair in replacements:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("Each override replacement must be a [from, to] pair")

        source, target = pair
        occurrences = updated.count(source)
        if occurrences:
            updated = updated.replace(source, target)
            applied += occurrences

    return updated, applied


def _apply_text_overrides(
    text: str,
    page_num: int,
    overrides: Dict[str, Any],
) -> Tuple[str, int]:
    """Apply global and page-specific source overrides."""
    if not text or not overrides:
        return text, 0

    updated = text
    applied = 0

    global_rules = overrides.get("global", {})
    if global_rules:
        updated, count = _apply_replacements(updated, global_rules)
        applied += count

    page_rules = overrides.get("pages", {}).get(str(page_num), {})
    if page_rules:
        updated, count = _apply_replacements(updated, page_rules)
        applied += count

    return updated, applied


def _summarize_correction_stats(page_stats: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate page-level second-stage correction stats."""
    total_corrected = 0
    total_considered = 0
    corrections = []
    for stats in page_stats.values():
        total_corrected += stats.get("corrected_tokens", 0)
        total_considered += stats.get("tokens_considered", 0)
        for correction in stats.get("corrections", []):
            if len(corrections) >= 20:
                break
            corrections.append(correction)

    return {
        "corrected_tokens": total_corrected,
        "tokens_considered": total_considered,
        "corrections": corrections,
    }


def extract_unicode_text(
    pdf_path: str,
    page_range: Optional[Tuple[int, int]] = None,
    font_type: str = "auto",
    post_process: bool = True,
    second_stage: str = "none",
    lexicon_path: Optional[str] = None,
    bootstrap_lexicon: bool = False,
    overrides_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract text from *pdf_path*, auto-correcting legacy Hindi font
    encoding to Unicode Devanagari where detected.

    Args:
        pdf_path:    Path to the PDF file.
        page_range:  Optional ``(start, end)`` tuple (1-indexed, inclusive).
        font_type:   ``"auto"`` (default), ``"krutidev"``, ``"chanakya"``, or ``"none"``.
        post_process: Apply post-processing after conversion.
        second_stage: Optional extra correction layer (``"none"`` or ``"lexicon"``).
        lexicon_path: Optional external lexicon file used by the second stage.
        bootstrap_lexicon: Build a supplemental lexicon from repeated clean tokens in the document.
        overrides_path: Optional JSON file with global/page-specific literal replacements.

    Returns:
        Dict with keys: filename, total_pages, processed_pages,
        has_encoding_issues, detected_font_type, pages, full_text.
    """
    result: Dict[str, Any] = {
        "filename": os.path.basename(pdf_path),
        "total_pages": 0,
        "processed_pages": 0,
        "has_encoding_issues": False,
        "detected_font_type": "unknown",
        "is_scrambled_devanagari": False,
        "artifact_count": 0,
        "overrides_applied": 0,
        "pages": {},
        "full_text": "",
        "second_stage": second_stage,
    }

    try:
        with open(pdf_path, "rb") as fh:
            reader = PdfReader(fh)
            overrides = _load_text_overrides(overrides_path)
            total = len(reader.pages)
            result["total_pages"] = total

            # Determine page slice (1-indexed -> 0-indexed)
            start_0 = (page_range[0] - 1) if page_range else 0
            end_0 = page_range[1] if page_range else total
            start_0 = max(0, min(start_0, total - 1))
            end_0 = max(start_0 + 1, min(end_0, total))

            # Sample text to detect encoding
            sample = ""
            for pg_idx in range(min(start_0 + 3, end_0)):
                try:
                    t = reader.pages[pg_idx].extract_text() or ""
                    sample += t
                    if len(sample) >= 1000:
                        break
                except Exception:
                    pass

            has_issues, detected_font = HindiPreprocessor.detect_encoding(sample)
            result["has_encoding_issues"] = has_issues
            result["detected_font_type"] = detected_font

            # "Scrambled Devanagari": text is mostly Devanagari but has corruption
            # artefacts (extracted via a buggy font CMap). post_process still helps.
            scrambled = (
                detected_font == "unknown"
                and HindiPreprocessor.detect_scrambled_devanagari(sample)
            )
            result["is_scrambled_devanagari"] = scrambled
            if scrambled:
                result["has_encoding_issues"] = True
                if result["detected_font_type"] == "unknown":
                    result["detected_font_type"] = "scrambled_devanagari"

            if font_type == "auto":
                font_type = result["detected_font_type"]

            should_apply_second_stage = second_stage == "lexicon" and font_type not in (
                "unknown",
                "none",
            )
            result["second_stage_applied"] = should_apply_second_stage

            pages_text: Dict[int, str] = {}
            for pg_idx in range(start_0, end_0):
                page_num = pg_idx + 1
                try:
                    raw = reader.pages[pg_idx].extract_text() or ""
                except Exception as exc:
                    logger.warning("Page %d extract failed: %s", page_num, exc)
                    raw = ""

                if raw and font_type not in ("unknown", "none", "scrambled_devanagari"):
                    raw = HindiPreprocessor.convert(raw, font_type)

                if raw and post_process and font_type != "none":
                    raw = HindiPreprocessor.post_process(raw)

                if raw and overrides:
                    raw, override_count = _apply_text_overrides(raw, page_num, overrides)
                    result["overrides_applied"] += override_count

                pages_text[page_num] = raw

            if should_apply_second_stage:
                corrector = HindiLexiconCorrector(lexicon_path=lexicon_path)
                contextual_words = set()
                if bootstrap_lexicon:
                    contextual_words = build_contextual_lexicon(
                        pages_text.values(), base_lexicon=set(corrector.lexicon)
                    )
                    corrector.add_words(contextual_words)
                    result["contextual_lexicon_size"] = len(contextual_words)
                result["effective_lexicon_size"] = len(corrector.lexicon)

                page_correction_stats: Dict[int, Dict[str, Any]] = {}
                for page_num, page_text in pages_text.items():
                    correction = corrector.correct_text(page_text)
                    pages_text[page_num] = correction["text"]
                    page_correction_stats[page_num] = correction["stats"]

                result["page_correction_stats"] = page_correction_stats
                result["correction_stats"] = _summarize_correction_stats(page_correction_stats)
            elif second_stage == "lexicon":
                result["correction_stats"] = {
                    "corrected_tokens": 0,
                    "tokens_considered": 0,
                    "corrections": [],
                }

            result["pages"] = pages_text
            result["processed_pages"] = len(pages_text)
            result["full_text"] = "\n\n".join(pages_text.values())
            result["artifact_count"] = sum(
                HindiPreprocessor.count_artifacts(t)["total"]
                for t in pages_text.values()
            )

    except FileNotFoundError:
        logger.error("File not found: %s", pdf_path)
        result["error"] = f"File not found: {pdf_path}"
    except Exception as exc:
        logger.error("Error extracting text from %s: %s", pdf_path, exc)
        result["error"] = str(exc)

    return result
