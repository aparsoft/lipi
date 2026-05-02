"""
Hindi Text Preprocessor
========================
Converts text encoded in legacy Hindi fonts (KrutiDev, Chanakya)
to Unicode Devanagari.

Usage::

    from lipi.preprocessor import HindiPreprocessor

    hp = HindiPreprocessor()
    unicode_text = hp.convert("eSaus gSjku gksdj ns[kk")
    # → "मैंने हैरान होकर देखा"
"""

import re
import logging
from typing import Dict, List, Tuple

from lipi.mappings import FONT_MAPPINGS

logger = logging.getLogger(__name__)

# Regex for i-matra reordering (compiled once)
_IMATRA = "\u093f"  # ि
_IMATRA_ANUSVARA = "\u093f\u0902"  # िं (i-matra + anusvara)
_HALANT = "\u094d"  # ्
_CONS_RANGE = "\u0915-\u0939"  # क–ह
_IMATRA_REORDER_RE = re.compile(
    _IMATRA_ANUSVARA
    + f"((?:[{_CONS_RANGE}]{_HALANT})*[{_CONS_RANGE}])"
    + "|"
    + _IMATRA
    + f"((?:[{_CONS_RANGE}]{_HALANT})*[{_CONS_RANGE}])"
)
_DEVA_MARKS = "\u093c\u0901\u0902\u0903\u093e\u093f\u0940\u0941\u0942\u0943\u0947\u0948\u0949\u094b\u094c\u094d"
_MARK_SPACING_RE = re.compile(f"([\u0900-\u097f])\\s+([{_DEVA_MARKS}])")
_HALANT_SPACING_RE = re.compile(r"(्)\s+([\u0900-\u097f])")
_DUPLICATE_CONSONANT_I_RE = re.compile(rf"([{_CONS_RANGE}])\1(?=[{_CONS_RANGE}]|[\u0901\u0902\u0903])")
_SHCHA_IMATRA_RE = re.compile(r"श्श्ि")
_NUKTA_BASE_RE = re.compile(r"([डढ])\1़")

_NUKTA_I_REPLACEMENTS = {
    "ड": "ड़",
    "ढ": "ढ़",
}


def _reorder_imatra(match: re.Match) -> str:
    """Move ि or िं from before consonant cluster to after it."""
    if match.group(1):
        return match.group(1) + _IMATRA_ANUSVARA
    else:
        return match.group(2) + _IMATRA


def _fix_decomposed_nukta_i(match: re.Match) -> str:
    """Repair decomposed nukta forms where the i-matra is dropped."""
    return _NUKTA_I_REPLACEMENTS[match.group(1)] + _IMATRA


class HindiPreprocessor:
    """
    Convert legacy Hindi font-encoded text to Unicode Devanagari.

    Handles KrutiDev and Chanakya fonts.  Uses longest-match token
    substitution with an i-matra reordering post-pass.
    """

    # Lazy-computed sorted key lists (longest match first).
    _sorted_keys: Dict[str, List[str]] = {}

    @classmethod
    def _get_sorted_keys(cls, font_type: str) -> List[str]:
        if font_type not in cls._sorted_keys:
            mapping = FONT_MAPPINGS.get(font_type, {})
            cls._sorted_keys[font_type] = sorted(
                mapping.keys(), key=len, reverse=True
            )
        return cls._sorted_keys[font_type]

    # ------------------------------------------------------------------ #
    #  Encoding detection                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_encoding(text: str) -> Tuple[bool, str]:
        """
        Heuristically detect legacy Hindi font encoding in *text*.

        Returns ``(has_legacy_encoding, font_type)`` where *font_type* is
        ``"krutidev"``, ``"chanakya"``, or ``"unknown"``.
        """
        if not text:
            return False, "unknown"

        devanagari_count = sum(1 for ch in text if "\u0900" <= ch <= "\u097f")
        devanagari_ratio = devanagari_count / max(len(text), 1)

        # Already mostly Unicode Devanagari — nothing to do.
        if devanagari_ratio > 0.3:
            return False, "unknown"

        # Fingerprint patterns
        krutidev_fps = ["osQ", "kjk", "ykZ", "Fk", "Hk", "/k", "'k"]
        chanakya_fps = ["Aa", "ao", "AO", "\xac", "\xa4"]

        kd_score = sum(text.count(p) for p in krutidev_fps)
        ch_score = sum(text.count(p) for p in chanakya_fps)

        generic_score = sum(
            text.count(p) for p in ["kk", "kh", "kz", "gh", "ph", "ek", "ea", "kj", "dj"]
        )

        has_issues = (kd_score + ch_score + generic_score) > 4 and devanagari_ratio < 0.1
        if not has_issues:
            return False, "unknown"

        return (True, "krutidev") if kd_score >= ch_score else (True, "chanakya")

    # ------------------------------------------------------------------ #
    #  Core conversion                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert(text: str, font_type: str = "auto") -> str:
        """
        Convert legacy-font-encoded *text* to Unicode Devanagari.

        Args:
            text:      Raw text (typically from pypdf extraction).
            font_type: ``"krutidev"``, ``"chanakya"``, or ``"auto"``.
        """
        if not text:
            return text

        # Auto-detect font type when not specified
        if font_type == "auto":
            _, detected = HindiPreprocessor.detect_encoding(text)
            font_type = detected if detected != "unknown" else "krutidev"

        # Select mapping table
        mapping = FONT_MAPPINGS.get(font_type, FONT_MAPPINGS["krutidev"])
        keys = HindiPreprocessor._get_sorted_keys(font_type)

        # -- Pass 1: Token-by-token substitution --
        result: list[str] = []
        i = 0
        tlen = len(text)
        while i < tlen:
            ch = text[i]

            # Preserve characters already in Devanagari Unicode range
            if "\u0900" <= ch <= "\u097f":
                result.append(ch)
                i += 1
                continue

            # Try longest match at current position
            matched = False
            for key in keys:
                klen = len(key)
                if i + klen <= tlen and text[i : i + klen] == key:
                    result.append(mapping[key])
                    i += klen
                    matched = True
                    break

            if not matched:
                result.append(ch)
                i += 1

        converted = "".join(result)

        # -- Pass 2: Reorder i-matra (ि and िं) --
        # Only needed for KrutiDev (Chanakya doesn't have this issue)
        if font_type in ("krutidev", "walkman_chanakya"):
            converted = _IMATRA_REORDER_RE.sub(_reorder_imatra, converted)

        return converted

    # ------------------------------------------------------------------ #
    #  Post-processing                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def post_process(text: str) -> str:
        """
        Clean up common artefacts after KrutiDev → Unicode conversion.

        Fixes doubled matras and known mis-spellings.
        """
        if not text:
            return text

        # PDFs often insert spaces before dependent vowel signs or after halant.
        text = _MARK_SPACING_RE.sub(r"\1\2", text)
        text = _HALANT_SPACING_RE.sub(r"\1\2", text)
        text = _DUPLICATE_CONSONANT_I_RE.sub(r"\1ि", text)
        text = _SHCHA_IMATRA_RE.sub("श्चि", text)
        text = _NUKTA_BASE_RE.sub(_fix_decomposed_nukta_i, text)

        corrections = [
            # -- Remove doubled matras --
            ("ाा", "ा"),
            ("िि", "ि"),
            ("ीी", "ी"),
            ("ुु", "ु"),
            ("ूू", "ू"),
            ("ेे", "े"),
            ("ैै", "ै"),
            ("ोो", "ो"),
            ("ौौ", "ौ"),
            ("ंं", "ं"),
            # -- Walkman-Chanakya905 artifacts --
            ("इएं", "एं"),
            ("आइएं", "आएं"),
            ("\u094d\u093e", "\u093e"),  # ् + ा → ा
            # -- Common word-level corrections --
            ("अौर", "और"),
            ("अार", "आर"),
            ("एक़", "एक"),
        ]

        for pattern, replacement in corrections:
            text = re.sub(pattern, replacement, text)
        return text

    # ------------------------------------------------------------------ #
    #  Convenience aliases                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def correct_hindi_text(text: str, font_type: str = "auto") -> str:
        """Convert + post-process in one call."""
        converted = HindiPreprocessor.convert(text, font_type)
        return HindiPreprocessor.post_process(converted)

    @staticmethod
    def get_mapping(font_type: str = "krutidev") -> Dict[str, str]:
        """Return the raw character mapping table for *font_type*."""
        return FONT_MAPPINGS.get(font_type, FONT_MAPPINGS["krutidev"])
