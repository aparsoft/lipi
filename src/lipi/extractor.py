"""
PDF text extraction with legacy Hindi font auto-conversion.

Uses pypdf as the default extractor.  When PyMuPDF (fitz) is available,
offers span-level extraction that routes text by font name for more
accurate font-type detection.
"""

import os
import re
import logging
from typing import Dict, Any, Optional, Tuple

from pypdf import PdfReader

from lipi.preprocessor import HindiPreprocessor
from lipi._quality import is_garbage_text

logger = logging.getLogger(__name__)

# Optional fitz (PyMuPDF) for span-level extraction
try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


def _detect_font_from_name(font_name: str) -> Optional[str]:
    """Guess font encoding type from the font name string."""
    name_lower = font_name.lower()
    if "krutidev" in name_lower or "krutidev" in name_lower.replace(" ", ""):
        return "krutidev"
    if "chanakya" in name_lower:
        return "chanakya"
    if "walkman" in name_lower:
        return "walkman_chanakya"
    return None


def extract_unicode_text(
    pdf_path: str,
    page_range: Optional[Tuple[int, int]] = None,
    font_type: str = "auto",
    post_process: bool = True,
) -> Dict[str, Any]:
    """
    Extract text from *pdf_path*, auto-correcting legacy Hindi font
    encoding to Unicode Devanagari where detected.

    Args:
        pdf_path:    Path to the PDF file.
        page_range:  Optional ``(start, end)`` tuple (1-indexed, inclusive).
        font_type:   ``"auto"`` (default), ``"krutidev"``, ``"chanakya"``, or ``"none"``.
        post_process: Apply post-processing after conversion.

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
        "pages": {},
        "full_text": "",
    }

    try:
        with open(pdf_path, "rb") as fh:
            reader = PdfReader(fh)
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

            if font_type == "auto":
                font_type = detected_font

            pages_text: Dict[int, str] = {}
            for pg_idx in range(start_0, end_0):
                page_num = pg_idx + 1
                try:
                    raw = reader.pages[pg_idx].extract_text() or ""
                except Exception as exc:
                    logger.warning("Page %d extract failed: %s", page_num, exc)
                    raw = ""

                if raw and font_type not in ("unknown", "none"):
                    raw = HindiPreprocessor.convert(raw, font_type)
                    if post_process:
                        raw = HindiPreprocessor.post_process(raw)

                pages_text[page_num] = raw

            result["pages"] = pages_text
            result["processed_pages"] = len(pages_text)
            result["full_text"] = "\n\n".join(pages_text.values())

    except FileNotFoundError:
        logger.error("File not found: %s", pdf_path)
        result["error"] = f"File not found: {pdf_path}"
    except Exception as exc:
        logger.error("Error extracting text from %s: %s", pdf_path, exc)
        result["error"] = str(exc)

    return result


def extract_unicode_text_fitz(
    pdf_path: str,
    page_range: Optional[Tuple[int, int]] = None,
    post_process: bool = True,
) -> Dict[str, Any]:
    """
    Extract text using PyMuPDF span-level font routing.

    Routes text spans by font name for accurate per-span conversion.
    Falls back to ``extract_unicode_text()`` if fitz is unavailable.
    """
    if not FITZ_AVAILABLE:
        logger.info("fitz not available, using pypdf extraction")
        return extract_unicode_text(pdf_path, page_range=page_range)

    result: Dict[str, Any] = {
        "filename": os.path.basename(pdf_path),
        "total_pages": 0,
        "processed_pages": 0,
        "has_encoding_issues": False,
        "detected_font_type": "unknown",
        "pages": {},
        "full_text": "",
    }

    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        result["total_pages"] = total

        start_0 = (page_range[0] - 1) if page_range else 0
        end_0 = page_range[1] if page_range else total
        start_0 = max(0, min(start_0, total - 1))
        end_0 = max(start_0 + 1, min(end_0, total))

        pages_text: Dict[int, str] = {}
        detected_fonts = set()

        for pg_idx in range(start_0, end_0):
            page_num = pg_idx + 1
            page = doc[pg_idx]
            try:
                page_dict = page.get_text("dict")
            except Exception as exc:
                logger.warning("Page %d dict extraction failed: %s", page_num, exc)
                pages_text[page_num] = page.get_text("text") or ""
                continue

            span_texts = []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # text blocks only
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        font_name = span.get("font", "")
                        detected_type = _detect_font_from_name(font_name)
                        if detected_type and text:
                            detected_fonts.add(detected_type)
                            text = HindiPreprocessor.convert(text, detected_type)
                            if post_process:
                                text = HindiPreprocessor.post_process(text)
                        span_texts.append(text)

            pages_text[page_num] = "".join(span_texts)

        result["pages"] = pages_text
        result["processed_pages"] = len(pages_text)
        result["full_text"] = "\n\n".join(pages_text.values())

        if detected_fonts:
            result["has_encoding_issues"] = True
            result["detected_font_type"] = ", ".join(sorted(detected_fonts))

        doc.close()

    except FileNotFoundError:
        logger.error("File not found: %s", pdf_path)
        result["error"] = f"File not found: {pdf_path}"
    except Exception as exc:
        logger.error("Error extracting text from %s: %s", pdf_path, exc)
        result["error"] = str(exc)

    return result
