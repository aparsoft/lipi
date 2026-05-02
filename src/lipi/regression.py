"""Regression harness for page-by-page quality measurement over real PDF samples."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from lipi._quality import is_garbage_text
from lipi.correction import HindiLexiconCorrector, build_contextual_lexicon
from lipi.extractor import extract_unicode_text

_WORD_RE = re.compile(r"[\u0900-\u0963\u0970-\u097f]+")
_MARK_SPACING_RE = re.compile(r"[\u0900-\u097f]\s+[\u093c\u0901\u0902\u0903\u093e\u093f\u0940\u0941\u0942\u0943\u0947\u0948\u0949\u094b\u094c\u094d]")
_HALANT_SPACING_RE = re.compile(r"्\s+[\u0900-\u097f]")
_DUPLICATE_MARKS_RE = re.compile(r"([ँंः़ािीुूृेैोौ्])\1+")
_SPURIOUS_NUKTA_RE = re.compile(r"[क-ह](?:्)?़")
_SUSPICIOUS_MARK_SEQUENCE_RE = re.compile(r"[ािीुूृेैोौॉॅ][ँंः]?[ािीुूृेैोौॉॅ]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def measure_text_quality(text: str, lexicon_words: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Measure generic quality signals for a page of extracted Hindi text."""
    lexicon = set(lexicon_words or [])
    visible_chars = [char for char in text if not char.isspace()]
    total_visible = len(visible_chars)
    devanagari_chars = sum(1 for char in visible_chars if "\u0900" <= char <= "\u097f")
    latin_chars = sum(1 for char in visible_chars if char.isascii() and char.isalpha())
    other_chars = total_visible - devanagari_chars - latin_chars
    tokens = [token for token in _WORD_RE.findall(text) if len(token) >= 3]
    lexicon_hits = sum(1 for token in tokens if token in lexicon)

    artifact_counts = {
        "mark_spacing": len(_MARK_SPACING_RE.findall(text)),
        "halant_spacing": len(_HALANT_SPACING_RE.findall(text)),
        "duplicate_marks": len(_DUPLICATE_MARKS_RE.findall(text)),
        "spurious_nukta": len(_SPURIOUS_NUKTA_RE.findall(text)),
        "suspicious_mark_sequence": len(_SUSPICIOUS_MARK_SEQUENCE_RE.findall(text)),
        "latin_residue": len(_LATIN_RE.findall(text)),
    }
    artifact_total = sum(artifact_counts.values())

    is_garbage, garbage_score, garbage_reason = is_garbage_text(text)
    devanagari_ratio = round(devanagari_chars / max(total_visible, 1), 4)
    lexicon_hit_rate = round(lexicon_hits / max(len(tokens), 1), 4)
    artifact_ratio = artifact_total / max(len(tokens), 1)
    quality_index = round(
        max(
            0.0,
            min(
                1.0,
                garbage_score * 0.45
                + devanagari_ratio * 0.2
                + lexicon_hit_rate * 0.25
                + (1.0 - min(artifact_ratio, 1.0)) * 0.1,
            ),
        ),
        4,
    )

    return {
        "token_count": len(tokens),
        "visible_char_count": total_visible,
        "devanagari_ratio": devanagari_ratio,
        "latin_char_count": latin_chars,
        "other_char_count": other_chars,
        "lexicon_hit_rate": lexicon_hit_rate,
        "artifact_counts": artifact_counts,
        "artifact_total": artifact_total,
        "is_garbage": is_garbage,
        "garbage_score": round(garbage_score, 4),
        "garbage_reason": garbage_reason,
        "quality_index": quality_index,
    }


def run_regression_harness(
    pdf_paths: Sequence[str],
    font_type: str = "auto",
    second_stage: str = "lexicon",
    lexicon_path: Optional[str] = None,
    bootstrap_lexicon: bool = True,
    page_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Run page-by-page quality measurement over one or more sample PDFs."""
    reports: List[Dict[str, Any]] = []
    total_pages = 0
    improved_pages = 0
    total_corrections = 0
    quality_deltas: List[float] = []

    page_range = (1, page_limit) if page_limit else None

    for pdf_path in pdf_paths:
        baseline = extract_unicode_text(
            pdf_path,
            page_range=page_range,
            font_type=font_type,
            post_process=True,
            second_stage="none",
        )
        if "error" in baseline:
            reports.append({
                "pdf_path": pdf_path,
                "error": baseline["error"],
            })
            continue

        corrector = HindiLexiconCorrector(lexicon_path=lexicon_path)
        contextual_words = set()
        if bootstrap_lexicon:
            contextual_words = build_contextual_lexicon(
                baseline["pages"].values(),
                base_lexicon=set(corrector.lexicon),
            )
            corrector.add_words(contextual_words)

        corrected = extract_unicode_text(
            pdf_path,
            page_range=page_range,
            font_type=font_type,
            post_process=True,
            second_stage=second_stage,
            lexicon_path=lexicon_path,
            bootstrap_lexicon=bootstrap_lexicon,
        )

        page_reports: List[Dict[str, Any]] = []
        for page_num, baseline_text in baseline["pages"].items():
            corrected_text = corrected["pages"].get(page_num, "")
            baseline_metrics = measure_text_quality(baseline_text, corrector.lexicon)
            corrected_metrics = measure_text_quality(corrected_text, corrector.lexicon)
            correction_stats = corrected.get("page_correction_stats", {}).get(page_num, {})
            quality_delta = round(
                corrected_metrics["quality_index"] - baseline_metrics["quality_index"], 4
            )
            page_improved = quality_delta > 0 or correction_stats.get("corrected_tokens", 0) > 0

            page_reports.append(
                {
                    "page_num": page_num,
                    "baseline_metrics": baseline_metrics,
                    "corrected_metrics": corrected_metrics,
                    "quality_delta": quality_delta,
                    "lexicon_hit_delta": round(
                        corrected_metrics["lexicon_hit_rate"]
                        - baseline_metrics["lexicon_hit_rate"],
                        4,
                    ),
                    "artifact_delta": corrected_metrics["artifact_total"]
                    - baseline_metrics["artifact_total"],
                    "correction_stats": correction_stats,
                    "improved": page_improved,
                }
            )

            total_pages += 1
            improved_pages += int(page_improved)
            total_corrections += correction_stats.get("corrected_tokens", 0)
            quality_deltas.append(quality_delta)

        reports.append(
            {
                "pdf_path": pdf_path,
                "filename": os.path.basename(pdf_path),
                "detected_font_type": baseline.get("detected_font_type"),
                "pages_analyzed": len(page_reports),
                "contextual_lexicon_size": len(contextual_words),
                "effective_lexicon_size": len(corrector.lexicon),
                "page_reports": page_reports,
            }
        )

    average_quality_delta = round(sum(quality_deltas) / max(len(quality_deltas), 1), 4)
    return {
        "pdf_count": len(pdf_paths),
        "total_pages": total_pages,
        "improved_pages": improved_pages,
        "total_corrections": total_corrections,
        "average_quality_delta": average_quality_delta,
        "reports": reports,
    }