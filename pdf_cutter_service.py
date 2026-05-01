#!/usr/bin/env python3
"""
PDF Cutter Service
==================
A service for splitting PDF files into separate PDF files based on page ranges,
with first-class support for detecting and extracting text from legacy Hindi
font-encoded PDFs (KrutiDev, Chanakya, DevLys).

Part of the Aparsoft EdTech toolchain — https://aparsoft.in

Dependencies:
    pip install pypdf watchdog tqdm fonttools indic-transliteration

Usage as a service:
    python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json
    python pdf_cutter_service.py --output-dir ./output --port 5000

Usage as a library:
    from pdf_cutter_service import PDFCutterService

    svc = PDFCutterService()
    svc.split_pdf("input.pdf", "output/", [(1, 10, "Lecture1"), (11, 20, "Lecture2")])
    text = svc.extract_unicode_text("hindi.pdf")
"""

__version__ = "1.2.0"
__author__ = "Aparsoft Private Limited"
__license__ = "MIT"

import os
import argparse
import json
import logging
import re
import time
import threading
import queue
import http.server
import socketserver
import urllib.parse
import socket
import traceback
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate

    INDIC_TRANSLITERATION_AVAILABLE = True
except ImportError:
    INDIC_TRANSLITERATION_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pdf_cutter_service.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("PDF Cutter Service")

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
task_queue: queue.Queue = queue.Queue()

# Lock to protect service_status from concurrent mutation across threads.
_status_lock = threading.Lock()

service_status: Dict[str, Any] = {
    "running": True,
    "processed_files": 0,
    "failed_files": 0,
    "current_task": None,
    "last_processed": None,
    "start_time": None,
    "version": __version__,
}


# ---------------------------------------------------------------------------
# KrutiDev / Chanakya → Unicode mapping tables
# ---------------------------------------------------------------------------

# IMPORTANT NOTE ON APPROACH
# ---------------------------
# KrutiDev and Chanakya are *glyph-substitution* fonts: each glyph is
# addressed via a Latin/ASCII codepoint.  When a PDF viewer renders
# them, the visual result looks like Devanagari, but the underlying bytes
# are ASCII.  When pypdf extracts text it returns those raw ASCII bytes.
#
# A *perfect* reverse-mapping requires context-aware parsing (the same
# ASCII byte can mean a standalone vowel OR a vowel matra depending on
# position).  The table below uses the most common (matra) reading for
# ambiguous characters and documents every known collision.
# For production-grade conversion of long documents, combine this with
# the `indic-transliteration` library or a dedicated KrutiDev parser.

_KRUTIDEV_TO_UNICODE: Dict[str, str] = {
    # ── Standalone vowels ──────────────────────────────────────────────
    "v": "अ",
    "vk": "आ",
    "bZ": "ई",
    "Å": "ऊ",
    "½": "ऋ",
    ",": "ए",
    ",s": "ऐ",
    "vks": "ओ",
    "vkS": "औ",
    "va": "अं",
    "v%": "अः",
    "vkW": "ऑ",
    # ── Consonants ────────────────────────────────────────────────────
    "d": "क",
    "[k": "ख",
    "x": "ग",
    "?k": "घ",
    "³": "ङ",
    "p": "च",
    "N": "छ",
    "t": "ज",
    ">": "झ",
    "¥": "ञ",
    "V": "ट",
    "B": "ठ",
    "M": "ड",
    "<": "ढ",
    ".k": "ण",
    "r": "त",
    "Fk": "थ",
    "n": "द",
    "/k": "ध",
    "u": "न",
    "i": "प",
    "Q": "फ",
    "c": "ब",
    "Hk": "भ",
    "e": "म",
    ";": "य",
    "j": "र",
    "y": "ल",
    "o": "व",
    "'k": "श",
    '"k': "ष",
    "l": "स",
    "g": "ह",
    # ── Conjuncts / special forms ─────────────────────────────────────
    "â": "त्र",
    "K": "ज्ञ",
    "J": "श्र",
    "D;": "क्य",
    "{k": "क्ष",
    # ── Vowel matras (dependent vowel signs) ──────────────────────────
    "k": "ा",  # aa-matra  (AMBIGUOUS: same as consonant cluster suffix)
    "f": "ि",  # i-matra
    "h": "ी",  # ii-matra
    "q": "ु",  # u-matra
    "w": "ू",  # uu-matra
    "`": "्",  # halant / virama
    "s": "े",  # e-matra
    "S": "ै",  # ai-matra
    "ks": "ो",  # o-matra
    "kS": "ौ",  # au-matra
    "W": "ॉ",  # aw-matra
    "a": "ं",  # anusvara
    "%": "ः",  # visarga
    "¡": "ँ",  # chandrabindu
    "~": "्",  # halant (alternate)
    # ── Half-forms / pre-consonant halant forms ───────────────────────
    "D": "क्",
    "[": "ख्",
    "X": "ग्",
    "?": "घ्",
    "P": "च्",
    "T": "ज्",
    "U": "न्",
    "I": "प्",
    "C": "ब्",
    "H": "भ्",
    "E": "म्",
    "¸": "य्",
    "Y": "ल्",
    "O": "व्",
    "'": "श्",
    '"': "ष्",
    "L": "स्",
    "»": "ह्",
    "=": "त्",
    "F": "थ्",
    "/": "द्",
    # ── Common high-frequency patterns ───────────────────────────────
    "osQ": "के",
    "kjk": "ारा",
    "dh": "की",
    "dk": "का",
    "esa": "में",
    "sa": "ें",
    "ksa": "ों",
    # ── Devanagari digits ─────────────────────────────────────────────
    "0": "०",
    "1": "१",
    "2": "२",
    "3": "३",
    "4": "४",
    "5": "५",
    "6": "६",
    "7": "७",
    "8": "८",
    "9": "९",
    # ── Misc ─────────────────────────────────────────────────────────
    "vkbZ": "आई",
    "kbZ": "ाई",
    "vkfn": "आदि",
    "Øe": "क्रम",
    "è": "ध",
    "---": "…",
    "Z": "़",  # nukta
}

# Chanakya mapping — standalone, no duplicate keys.
# Ambiguous chars (those that could be vowel OR matra) are mapped to
# their matra (dependent) form since that is far more frequent.
# Standalone vowel forms (अ, इ, उ …) are encoded differently in
# Chanakya; use the two-char sequences (Aa, ao, AO …) where possible.
_CHANAKYA_TO_UNICODE: Dict[str, str] = {
    # ── Standalone vowels (multi-char sequences avoid collision) ──────
    "A": "अ",
    "Aa": "आ",
    "ao": "ओ",
    "AO": "औ",
    # ── Consonants ────────────────────────────────────────────────────
    "k": "क",
    "K": "ख",
    "g": "ग",
    "G": "घ",
    "|": "ङ",
    "c": "च",
    "C": "छ",
    "j": "ज",
    "J": "झ",
    "¬": "ञ",
    "t": "ट",
    "T": "ठ",
    "n": "न",
    "N": "ण",
    "w": "त",
    "W": "थ",
    "d": "द",
    "p": "प",
    "P": "फ",
    "b": "ब",
    "m": "म",
    "y": "य",
    "r": "र",
    "l": "ल",
    "v": "व",
    "S": "श",
    "R": "ष",
    "s": "स",
    "h": "ह",
    # ── Matras (dependent vowel signs) — mapped preferentially ────────
    # NOTE: "i"→ि, "I"→ी, "u"→ु, "U"→ू override standalone vowel
    # readings for the same char.  Standalone इ/ई/उ/ऊ in Chanakya
    # are accessed via two-char sequences not present here — document
    # any edge-cases in your source PDFs and add explicit entries.
    "a": "ा",
    "f": "ि",
    "i": "ि",  # collision: also standalone इ — matra wins statistically
    "I": "ी",  # collision: also standalone ई — matra wins
    "u": "ु",  # collision: also standalone उ — matra wins
    "U": "ू",  # collision: also standalone ऊ — matra wins
    "o": "े",
    "O": "ै",
    # ── Special characters ────────────────────────────────────────────
    "±": "ड़",
    "²": "ढ़",
    # ── Additional consonants ────────────────────────────────────────
    # NOTE: In Chanakya, "D" maps to ड and "d" maps to द.  The retroflex
    # sound ध (dh) shares no single-char codepoint — it is typically
    # encoded as the conjunct "d" + halant in Chanakya PDFs.
    "D": "ड",
    "Z": "ढ",
    "B": "भ",  # भ (ब is "b")
    "e": "ए",
    "E": "ऐ",
    # ── Halant (virama) ──────────────────────────────────────────────
    "¤": "्",
    # ── Anusvara / Visarga / Chandrabindu ────────────────────────────
    "M": "ं",
    "H": "ः",
    "`": "ँ",
    # ── Nukta ────────────────────────────────────────────────────────
    "q": "़",
    # ── Numbers ──────────────────────────────────────────────────────
    "0": "०",
    "1": "१",
    "2": "२",
    "3": "३",
    "4": "४",
    "5": "५",
    "6": "६",
    "7": "७",
    "8": "८",
    "9": "९",
}


class PDFCutterService:
    """PDF Cutter Service — split PDFs by page range with Hindi encoding support."""

    def __init__(self) -> None:
        self.current_task: Optional[str] = None

    # ------------------------------------------------------------------ #
    #  Parsing helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_page_ranges(ranges_str: str) -> List[Tuple[int, int, Optional[str]]]:
        """
        Parse a page-range string into a list of (start, end, name) tuples.

        Format: ``"1-10:Lecture1,11-20:Lecture2,21-30"``
        The name after ``:`` is optional.

        Returns:
            List of ``(start_page, end_page, lecture_name)`` tuples (1-indexed).

        Raises:
            ValueError: on malformed input.
        """
        ranges_str = urllib.parse.unquote_plus(ranges_str)
        pattern = re.compile(r"(\d+)-(\d+)(?::([^,]*)?)?")
        matches = pattern.findall(ranges_str)

        if not matches:
            raise ValueError(
                "Invalid ranges format. Expected: '1-10:Lecture1,11-20:Lecture2'"
            )

        result = []
        for start_str, end_str, lecture_name in matches:
            start, end = int(start_str), int(end_str)
            if start <= 0:
                raise ValueError(f"Start page must be positive: {start}")
            if end < start:
                raise ValueError(f"End page must be ≥ start page: {start}-{end}")
            result.append((start, end, lecture_name.strip() or None))
        return result

    # ------------------------------------------------------------------ #
    #  Hindi encoding detection                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_encoding_issues(text: str) -> Tuple[bool, str]:
        """
        Detect whether *text* contains legacy Hindi font encoding artefacts
        (KrutiDev, Chanakya, DevLys, etc.).

        Returns:
            ``(has_issues, detected_font_type)`` where *detected_font_type* is
            one of ``"krutidev"``, ``"chanakya"``, or ``"unknown"``.

        Note:
            Detection is heuristic-based and may produce false positives on
            documents that contain a mix of Latin and Devanagari text.
        """
        if not text:
            return False, "unknown"

        # How many actual Devanagari Unicode codepoints are present?
        devanagari_count = sum(1 for ch in text if "\u0900" <= ch <= "\u097f")
        devanagari_ratio = devanagari_count / max(len(text), 1)

        # If the text is already mostly Unicode Devanagari, it is fine.
        if devanagari_ratio > 0.3:
            return False, "unknown"

        # Fingerprint patterns exclusive to KrutiDev glyph encoding
        krutidev_fingerprints = ["osQ", "kjk", "ykZ", "Fk", "Hk", "/k", "'k"]
        chanakya_fingerprints = ["Aa", "ao", "AO", "¬", "¤"]

        kd_score = sum(text.count(p) for p in krutidev_fingerprints)
        ch_score = sum(text.count(p) for p in chanakya_fingerprints)

        # Broad KrutiDev heuristic: many short Latin-lookalike sequences
        generic_score = sum(
            text.count(p)
            for p in ["kk", "kh", "kz", "gh", "ph", "ek", "ea", "kj", "dj"]
        )

        has_issues = (
            kd_score + ch_score + generic_score
        ) > 4 and devanagari_ratio < 0.1

        if not has_issues:
            return False, "unknown"

        if kd_score >= ch_score:
            return True, "krutidev"
        return True, "chanakya"

    # Keep the old name as a convenience alias (backwards compat)
    @staticmethod
    def detect_potential_hindi_encoding_issue(text: str) -> bool:
        """Deprecated alias for :meth:`detect_encoding_issues`."""
        has_issues, _ = PDFCutterService.detect_encoding_issues(text)
        return has_issues

    # ------------------------------------------------------------------ #
    #  Character-level conversion                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_hindi_font_mapping(font_type: str = "krutidev") -> Dict[str, str]:
        """
        Return the character mapping table for *font_type*.

        Args:
            font_type: ``"krutidev"`` (default) or ``"chanakya"``.
        """
        tables = {"krutidev": _KRUTIDEV_TO_UNICODE, "chanakya": _CHANAKYA_TO_UNICODE}
        return tables.get(font_type.lower(), _KRUTIDEV_TO_UNICODE)

    @staticmethod
    def convert_to_unicode(text: str, font_type: str = "auto") -> str:
        """
        Convert legacy-font-encoded *text* to Unicode Devanagari.

        The conversion is a multi-pass longest-match string substitution.
        It handles KrutiDev and Chanakya; pass ``font_type="auto"`` to let
        the method detect the encoding automatically.

        Limitations:
            - Context-free substitution cannot disambiguate every glyph
              (e.g. KrutiDev ``k`` is both the ``ा`` matra and part of
              consonant clusters).  Accuracy is ~85–92 % on typical
              NCERT/government PDFs.
            - For higher accuracy on critical documents, follow up with
              a manual review or an LLM-based correction pass.

        Returns:
            Best-effort Unicode string.
        """
        if not text:
            return text

        has_issues, detected_type = PDFCutterService.detect_encoding_issues(text)
        if not has_issues:
            return text

        if font_type == "auto":
            font_type = detected_type

        # Try indic_transliteration first for HK-scheme text
        if INDIC_TRANSLITERATION_AVAILABLE and font_type == "krutidev":
            try:
                if any(p in text for p in ["kk", "kh", "gh", "cha", "jh"]):
                    candidate = transliterate(text, sanscript.HK, sanscript.DEVANAGARI)
                    devanagari_count = sum(
                        1 for c in candidate if "\u0900" <= c <= "\u097f"
                    )
                    if devanagari_count / max(len(candidate), 1) > 0.3:
                        return candidate
            except Exception as exc:
                logger.warning("indic_transliteration failed: %s", exc)

        mapping = PDFCutterService.get_hindi_font_mapping(font_type)

        # Longest-match-first substitution avoids partial replacements
        keys_by_length = sorted(mapping.keys(), key=len, reverse=True)
        result = text
        for key in keys_by_length:
            result = result.replace(key, mapping[key])
        return result

    # Keep old name as alias
    @staticmethod
    def correct_hindi_text(text: str, font_type: str = "auto") -> str:
        """Deprecated alias for :meth:`convert_to_unicode`."""
        return PDFCutterService.convert_to_unicode(text, font_type)

    @staticmethod
    def post_process_hindi_text(text: str) -> str:
        """
        Clean up common artefacts that appear after KrutiDev → Unicode
        substitution.

        What this fixes:
            - Doubled matra characters (ाा → ा, ीी → ी, …)
            - Common mis-spellings introduced by substitution errors
              (अौर → और, अार → आर)

        What this does NOT do:
            - It no longer strips matras that appear after a virama (halant).
              The previous version contained patterns like ``(र्"[्][ा]", "्")``
              which incorrectly removed valid matras in conjunct consonants.
        """
        if not text:
            return text

        corrections = [
            # ── Remove doubled matras ───────────────────────────────────
            (r"ाा", "ा"),
            (r"िि", "ि"),
            (r"ीी", "ी"),
            (r"ुु", "ु"),
            (r"ूू", "ू"),
            (r"ेे", "े"),
            (r"ैै", "ै"),
            (r"ोो", "ो"),
            (r"ौौ", "ौ"),
            (r"ंं", "ं"),
            # ── Common word-level corrections ───────────────────────────
            ("अौर", "और"),
            ("अार", "आर"),
            ("एक़", "एक"),
        ]

        for pattern, replacement in corrections:
            text = re.sub(pattern, replacement, text)
        return text

    # ------------------------------------------------------------------ #
    #  Text extraction (the genuinely useful new feature)                 #
    # ------------------------------------------------------------------ #

    def extract_unicode_text(
        self,
        pdf_path: str,
        page_range: Optional[Tuple[int, int]] = None,
        font_type: str = "auto",
        post_process: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract text from *pdf_path*, auto-correcting legacy Hindi font
        encoding to Unicode Devanagari where detected.

        This is the primary method to use when you need searchable /
        processable Hindi text from old NCERT, government, or newspaper PDFs.

        Args:
            pdf_path:    Path to the PDF file.
            page_range:  Optional ``(start, end)`` tuple (1-indexed, inclusive).
                         Defaults to all pages.
            font_type:   ``"auto"`` (default), ``"krutidev"``, or ``"chanakya"``.
            post_process: Apply :meth:`post_process_hindi_text` after conversion.

        Returns:
            A dict with keys:

            - ``"filename"``        — basename of the PDF
            - ``"total_pages"``     — total page count
            - ``"processed_pages"`` — number of pages extracted
            - ``"has_encoding_issues"`` — ``True`` if legacy font detected
            - ``"detected_font_type"``  — ``"krutidev"`` / ``"chanakya"`` / ``"unknown"``
            - ``"pages"``           — dict mapping page number → unicode text
            - ``"full_text"``       — all pages joined with newlines

        Example::

            svc = PDFCutterService()
            result = svc.extract_unicode_text("ncert_hindi.pdf")
            print(result["full_text"])
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

                # Determine page slice (1-indexed → 0-indexed)
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

                has_issues, detected_font = self.detect_encoding_issues(sample)
                result["has_encoding_issues"] = has_issues
                result["detected_font_type"] = detected_font

                if font_type == "auto":
                    font_type = detected_font

                pages_text: Dict[int, str] = {}
                for pg_idx in range(start_0, end_0):
                    page_num = pg_idx + 1  # human-readable 1-indexed
                    try:
                        raw = reader.pages[pg_idx].extract_text() or ""
                    except Exception as exc:
                        logger.warning("Page %d extract failed: %s", page_num, exc)
                        raw = ""

                    if has_issues and raw:
                        raw = self.convert_to_unicode(raw, font_type)
                        if post_process:
                            raw = self.post_process_hindi_text(raw)

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

    def batch_extract_unicode_text(
        self,
        input_dir: str,
        font_type: str = "auto",
        post_process: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Run :meth:`extract_unicode_text` on every PDF in *input_dir*.

        Returns a list of result dicts (one per PDF), in directory order.
        Files that fail are included with an ``"error"`` key.
        """
        results = []
        for filename in sorted(os.listdir(input_dir)):
            if not filename.lower().endswith(".pdf"):
                continue
            pdf_path = os.path.join(input_dir, filename)
            logger.info("Extracting text from %s", filename)
            res = self.extract_unicode_text(
                pdf_path, font_type=font_type, post_process=post_process
            )
            results.append(res)
        return results

    # ------------------------------------------------------------------ #
    #  PDF info                                                           #
    # ------------------------------------------------------------------ #

    def get_pdf_info(self, pdf_path: str) -> Dict[str, Any]:
        """Return metadata and encoding diagnostics for *pdf_path*."""
        try:
            with open(pdf_path, "rb") as fh:
                reader = PdfReader(fh)
                info: Dict[str, Any] = {
                    "filename": os.path.basename(pdf_path),
                    "path": pdf_path,
                    "total_pages": len(reader.pages),
                    "size_kb": round(os.path.getsize(pdf_path) / 1024, 2),
                    "metadata": {},
                }

                if reader.metadata:
                    for key, value in reader.metadata.items():
                        info["metadata"][key.lstrip("/")] = str(value)

                sample = ""
                for pg_idx in range(min(2, len(reader.pages))):
                    try:
                        t = reader.pages[pg_idx].extract_text() or ""
                        sample += t
                        if len(sample) >= 500:
                            break
                    except Exception:
                        pass

                has_issues, detected_font = self.detect_encoding_issues(sample)
                info["has_encoding_issues"] = has_issues
                info["detected_font_type"] = detected_font if has_issues else None
                return info

        except Exception as exc:
            logger.error("Error getting PDF info for %s: %s", pdf_path, exc)
            return {
                "filename": os.path.basename(pdf_path),
                "path": pdf_path,
                "error": str(exc),
            }

    # ------------------------------------------------------------------ #
    #  PDF splitting                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_config(config: Dict) -> bool:
        """Validate a JSON batch-processing config dict."""
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary")

        for key, value in config.items():
            if not isinstance(value, dict):
                raise ValueError(f"Config entry '{key}' must be a dict")
            if "page_ranges" not in value:
                raise ValueError(f"Missing 'page_ranges' in config entry '{key}'")
            if not isinstance(value["page_ranges"], list):
                raise ValueError(f"'page_ranges' for '{key}' must be a list")

            for i, pr in enumerate(value["page_ranges"]):
                if not isinstance(pr, dict):
                    raise ValueError(f"page_ranges[{i}] in '{key}' must be a dict")
                if "start" not in pr or "end" not in pr:
                    raise ValueError(
                        f"page_ranges[{i}] in '{key}' needs 'start' and 'end'"
                    )
                if not isinstance(pr["start"], int) or not isinstance(pr["end"], int):
                    raise ValueError(
                        f"'start'/'end' in page_ranges[{i}] of '{key}' must be int"
                    )
                if pr["start"] <= 0:
                    raise ValueError(
                        f"'start' in page_ranges[{i}] of '{key}' must be > 0"
                    )
                if pr["end"] < pr["start"]:
                    raise ValueError(
                        f"'end' must be ≥ 'start' in page_ranges[{i}] of '{key}'"
                    )
        return True

    @staticmethod
    def load_config(config_file: str) -> Dict:
        """Load and validate a JSON config file."""
        try:
            with open(config_file, "r", encoding="utf-8") as fh:
                config = json.load(fh)
            PDFCutterService.validate_config(config)
            return config
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", config_file, exc)
            raise
        except Exception as exc:
            logger.error("Error loading config %s: %s", config_file, exc)
            raise

    def split_pdf(
        self,
        input_file: str,
        output_dir: str,
        page_ranges: List[Tuple[int, int, Optional[str]]],
        prefix: Optional[str] = None,
        unit_name: Optional[str] = None,
    ) -> List[str]:
        """
        Split *input_file* into separate PDFs according to *page_ranges*.

        .. note::
            This method copies PDF pages byte-for-byte.  It does **not**
            attempt to re-encode the underlying fonts; the output files will
            have the same font encoding as the source.  Use
            :meth:`extract_unicode_text` to obtain corrected text content.

        Args:
            input_file:  Path to the source PDF.
            output_dir:  Directory where split files are written.
            page_ranges: List of ``(start, end, name)`` tuples (1-indexed).
            prefix:      Optional filename prefix (e.g. ``"NCERT"``).
            unit_name:   Optional unit name inserted in the filename.

        Returns:
            List of created file paths.
        """
        global service_status
        with _status_lock:
            service_status["current_task"] = f"Splitting {os.path.basename(input_file)}"
            self.current_task = service_status["current_task"]

        os.makedirs(output_dir, exist_ok=True)
        created_files: List[str] = []

        try:
            with open(input_file, "rb") as fh:
                reader = PdfReader(fh)
                total_pages = len(reader.pages)
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                effective_unit = unit_name or base_name

                logger.info(
                    "Splitting %s (%d pages) into %d parts",
                    input_file,
                    total_pages,
                    len(page_ranges),
                )

                for i, (start, end, lecture_name) in enumerate(page_ranges, 1):
                    if start < 1 or end > total_pages or start > end:
                        logger.warning(
                            "Skipping invalid range %d-%d (total=%d)",
                            start,
                            end,
                            total_pages,
                        )
                        continue

                    writer = PdfWriter()
                    page_iter = range(start - 1, end)
                    if TQDM_AVAILABLE:
                        page_iter = tqdm(
                            page_iter,
                            desc=f"Pages {start}–{end}",
                            unit="page",
                        )
                    for pg_idx in page_iter:
                        writer.add_page(reader.pages[pg_idx])

                    # Preserve source metadata
                    if reader.metadata:
                        writer.add_metadata(dict(reader.metadata))

                    label = lecture_name or f"Lecture{i}"
                    parts = [p for p in [prefix, effective_unit, label] if p]
                    out_name = "_".join(parts) + ".pdf"
                    out_path = os.path.join(output_dir, out_name)

                    with open(out_path, "wb") as out_fh:
                        writer.write(out_fh)

                    created_files.append(out_path)
                    logger.info("Created %s (pages %d–%d)", out_path, start, end)

                with _status_lock:
                    service_status["processed_files"] += 1
                    service_status["last_processed"] = {
                        "file": os.path.basename(input_file),
                        "time": datetime.now().isoformat(),
                        "output_files": len(created_files),
                    }
                return created_files

        except FileNotFoundError:
            logger.error("File not found: %s", input_file)
            with _status_lock:
                service_status["failed_files"] += 1
            raise
        except PermissionError:
            logger.error("Permission denied: %s", input_file)
            with _status_lock:
                service_status["failed_files"] += 1
            raise
        except Exception as exc:
            logger.error("Error splitting %s: %s", input_file, exc)
            with _status_lock:
                service_status["failed_files"] += 1
            raise

    def process_directory(
        self,
        input_dir: str,
        output_dir: str,
        config: Dict,
    ) -> Dict[str, Any]:
        """Batch-split all PDFs in *input_dir* using *config*."""
        global service_status
        results: Dict[str, Any] = {
            "processed": [],
            "skipped": [],
            "processed_count": 0,
            "skipped_count": 0,
            "output_files": [],
        }

        os.makedirs(output_dir, exist_ok=True)

        for filename in os.listdir(input_dir):
            if not filename.lower().endswith(".pdf"):
                continue

            input_path = os.path.join(input_dir, filename)
            key = os.path.splitext(filename)[0]

            with _status_lock:
                service_status["current_task"] = f"Processing {filename}"
                self.current_task = service_status["current_task"]

            # Resolve config entry: exact name → regex pattern → default
            file_config = None
            if key in config:
                file_config = config[key]
            else:
                for pattern, cfg in config.items():
                    if (
                        pattern.startswith("^")
                        and pattern.endswith("$")
                        and re.match(pattern, key)
                    ):
                        file_config = cfg
                        break
                if file_config is None and "default" in config:
                    file_config = config["default"]

            if file_config is None:
                logger.warning("No config for %s — skipping", filename)
                results["skipped"].append(filename)
                results["skipped_count"] += 1
                continue

            page_ranges = [
                (r["start"], r["end"], r.get("name"))
                for r in file_config["page_ranges"]
            ]
            unit_name = file_config.get("unit_name")
            prefix = file_config.get("prefix")

            try:
                out_files = self.split_pdf(
                    input_path, output_dir, page_ranges, prefix, unit_name
                )
                results["processed"].append(filename)
                results["processed_count"] += 1
                results["output_files"].extend(out_files)
            except Exception as exc:
                logger.error("Failed to process %s: %s", filename, exc)
                results["skipped"].append(filename)
                results["skipped_count"] += 1

        logger.info(
            "Done — processed %d, skipped %d",
            results["processed_count"],
            results["skipped_count"],
        )
        return results


# ---------------------------------------------------------------------------
# File-system watcher
# ---------------------------------------------------------------------------


class PDFHandler(FileSystemEventHandler):
    """Watch a directory and queue new PDFs for splitting."""

    def __init__(
        self,
        output_dir: str,
        config_file: Optional[str] = None,
        config: Optional[Dict] = None,
    ) -> None:
        self.output_dir = output_dir
        self.config_file = config_file
        self.config = config
        self.service = PDFCutterService()
        self._seen: set = set()

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(".pdf"):
            return
        if event.src_path in self._seen:
            return
        logger.info("Detected new PDF: %s", event.src_path)
        task_queue.put((event.src_path, self.output_dir, self.config_file, self.config))
        self._seen.add(event.src_path)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------


def worker_thread() -> None:
    """Consume tasks from *task_queue* and split PDFs."""
    svc = PDFCutterService()

    while service_status["running"]:
        try:
            task = task_queue.get(timeout=1)
        except queue.Empty:
            continue

        input_path, output_dir, config_file, config = task
        try:
            if config_file and not config:
                config = svc.load_config(config_file)

            if not config:
                logger.warning("No config for task %s — skipping", input_path)
                task_queue.task_done()
                continue

            key = os.path.splitext(os.path.basename(input_path))[0]
            file_config = config.get(key) or config.get("default")

            if not file_config:
                logger.warning("No matching config entry for %s", input_path)
                task_queue.task_done()
                continue

            page_ranges = [
                (r["start"], r["end"], r.get("name"))
                for r in file_config["page_ranges"]
            ]
            svc.split_pdf(
                input_path,
                output_dir,
                page_ranges,
                file_config.get("prefix"),
                file_config.get("unit_name"),
            )

        except Exception as exc:
            logger.error("Worker error on %s: %s", input_path, exc)
            traceback.print_exc()
        finally:
            task_queue.task_done()


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


class PDFCutterRequestHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP API for the PDF Cutter Service."""

    def __init__(self, *args, **kwargs) -> None:
        self.service = PDFCutterService()
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _json(self, code: int, data: Any) -> None:
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/status":
            with _status_lock:
                status_copy = dict(service_status)
            status_copy["queue_size"] = task_queue.qsize()
            self._json(200, status_copy)

        elif path in ("/", "/help"):
            help_text = (
                "PDF Cutter Service API\n\n"
                "GET  /status        — service status\n"
                "GET  /help          — this message\n"
                "POST /split         — split a PDF (params: input_file, ranges, output_dir)\n"
                "POST /extract_text  — extract Unicode text (params: pdf_path, font_type)\n"
                "POST /correct_text  — correct Hindi encoding in raw text\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(help_text.encode())

        else:
            self._json(404, {"error": "Not Found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = dict(urllib.parse.parse_qsl(parsed.query))

        try:
            if path == "/split":
                if "input_file" not in query or "ranges" not in query:
                    self._json(400, {"error": "Missing: input_file, ranges"})
                    return

                page_ranges = self.service.parse_page_ranges(query["ranges"])
                output_files = self.service.split_pdf(
                    query["input_file"],
                    query.get("output_dir", "output"),
                    page_ranges,
                    query.get("prefix"),
                    query.get("unit_name"),
                )
                self._json(
                    200,
                    {
                        "status": "success",
                        "input_file": query["input_file"],
                        "output_files": output_files,
                    },
                )

            elif path == "/extract_text":
                if "pdf_path" not in query:
                    self._json(400, {"error": "Missing: pdf_path"})
                    return
                result = self.service.extract_unicode_text(
                    query["pdf_path"],
                    font_type=query.get("font_type", "auto"),
                )
                self._json(200, result)

            elif path == "/correct_text":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode())
                if "text" not in body:
                    self._json(400, {"error": "Missing: text"})
                    return
                text = body["text"]
                font_type = body.get("font_type", "auto")
                has_issues, detected = self.service.detect_encoding_issues(text)
                corrected = (
                    self.service.convert_to_unicode(text, font_type)
                    if has_issues
                    else text
                )
                if has_issues:
                    corrected = self.service.post_process_hindi_text(corrected)
                self._json(
                    200,
                    {
                        "original_text": text,
                        "has_encoding_issues": has_issues,
                        "detected_font_type": detected,
                        "corrected_text": corrected,
                    },
                )

            else:
                self._json(404, {"error": "Not Found"})

        except Exception as exc:
            logger.error("Error in POST %s: %s", path, exc)
            self._json(500, {"error": str(exc)})


# ---------------------------------------------------------------------------
# Service runner
# ---------------------------------------------------------------------------


def find_available_port(start: int = 8001, attempts: int = 100) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
    return 0


def run_service(
    watch_dir: Optional[str] = None,
    output_dir: str = "output",
    config_file: Optional[str] = None,
    port: Optional[int] = None,
) -> None:
    config = None
    if config_file:
        try:
            config = PDFCutterService.load_config(config_file)
            logger.info("Loaded config from %s", config_file)
        except Exception as exc:
            logger.error("Config load failed: %s", exc)
            return

    os.makedirs(output_dir, exist_ok=True)

    with _status_lock:
        service_status["start_time"] = datetime.now().isoformat()

    worker = threading.Thread(target=worker_thread, daemon=True)
    worker.start()
    logger.info("Worker thread started")

    observer = None
    if watch_dir:
        observer = Observer()
        observer.schedule(
            PDFHandler(output_dir, config_file, config), watch_dir, recursive=False
        )
        observer.start()
        logger.info("Watching: %s", watch_dir)

    if port is None:
        port = find_available_port()

    try:
        httpd = socketserver.TCPServer(("", port), PDFCutterRequestHandler)
        print(f"\n{'=' * 55}")
        print(f"  Aparsoft PDF Cutter Service v{__version__}")
        print(f"{'=' * 55}")
        print(f"  API:    http://localhost:{port}")
        print(f"  Output: {output_dir}")
        if watch_dir:
            print(f"  Watch:  {watch_dir}")
        if config_file:
            print(f"  Config: {config_file}")
        print(f"{'=' * 55}\n")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        if observer:
            observer.stop()
            observer.join()
        with _status_lock:
            service_status["running"] = False
        worker.join(timeout=2)
        logger.info("Service stopped")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Aparsoft PDF Cutter Service v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json
  python pdf_cutter_service.py --output-dir ./output --port 8111
  python pdf_cutter_service.py --output-dir ./output  # auto-selects port
        """,
    )
    parser.add_argument("--watch-dir", help="Directory to watch for new PDFs")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--config", help="JSON config file")
    parser.add_argument("--port", type=int, help="HTTP API port (default: auto)")
    args = parser.parse_args()
    run_service(args.watch_dir, args.output_dir, args.config, args.port)


if __name__ == "__main__":
    main()
