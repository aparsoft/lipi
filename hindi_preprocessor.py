#!/usr/bin/env python3
"""
Hindi Text Preprocessor
========================
Converts text encoded in legacy Hindi fonts (KrutiDev, Chanakya, DevLys)
to Unicode Devanagari.

Designed for use with pypdf-extracted text from old NCERT, government,
and newspaper PDFs that use KrutiDev or Chanakya font encoding.

Part of the Aparsoft EdTech toolchain — https://aparsoft.in

Usage::

    from hindi_preprocessor import HindiPreprocessor

    hp = HindiPreprocessor()
    unicode_text = hp.convert("eSaus gSjku gksdj ns[kk")
    # → "मैंने हैरान होकर देखा"

    # Or use the auto-detect flow:
    result = hp.convert("bfUnz;ksa ls ijs", font_type="auto")
    # → "इन्द्रियों से परे"
"""

__version__ = "1.0.0"
__author__ = "Aparsoft Private Limited"
__license__ = "MIT"

import re
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# ===================================================================== #
#  KrutiDev → Unicode mapping                                           #
# ===================================================================== #
#
# KrutiDev is a glyph-based encoding where characters are stored in
# *visual* (left-to-right) order.  Consonants have a "half form"
# (consonant + halant) used before another consonant in a conjunct.
# The i-matra (ि) appears *before* the consonant in the encoded text
# but must be placed *after* in Unicode — handled by the reordering
# pass in ``convert()``.
#
# Sources: KrutiDev 010 glyph table, NCERT PDF reverse-engineering.

_KRUTIDEV_TO_UNICODE: Dict[str, str] = {
    # ── Standalone vowels ──────────────────────────────────────────
    "v": "अ",
    "vk": "आ",
    "b": "इ",
    "bZ": "ई",
    "m": "उ",
    "Å": "ऊ",
    "½": "ऋ",
    ",": "ए",
    ",s": "ऐ",
    "vks": "ओ",
    "vkS": "औ",
    "va": "अं",
    "v%": "अः",
    "vkW": "ऑ",
    # ── Consonants ─────────────────────────────────────────────────
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
    # ── Conjuncts / special forms ──────────────────────────────────
    "â": "त्र",
    "K": "ज्ञ",
    "J": "श्र",
    "D;": "क्य",
    "{k": "क्ष",
    # ── Vowel matras (dependent vowel signs) ───────────────────────
    "k": "ा",  # aa-matra
    "f": "ि",  # i-matra (PRE-BASE — needs reordering!)
    "h": "ी",  # ii-matra
    "q": "ु",  # u-matra
    "w": "ू",  # uu-matra
    "`": "्",  # halant / virama
    "s": "े",  # e-matra
    "S": "ै",  # ai-matra
    "ks": "ो",  # o-matra
    "kS": "ौ",  # au-matra
    "W": "ॉ",  # candra-o matra
    "a": "ं",  # anusvara
    "%": "ः",  # visarga
    "¡": "ँ",  # chandrabindu
    "~": "्",  # halant (alternate)
    # ── Half-forms (consonant + halant) ────────────────────────────
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
    "\xb8": "य्",  # ¸ (cedilla)
    "Y": "ल्",
    "O": "व्",
    "'": "श्",
    '"': "ष्",
    "L": "स्",
    "\xbb": "ह्",  # » (right-pointing double angle quote)
    "=": "त्",
    "F": "थ्",
    "/": "द्",
    # ── Walkman-Chanakya905 multi-char tokens ──────────────────────
    # These font-specific trigraphs/digraphs appear when pypdf extracts
    # text from PDFs that use Walkman-Chanakya905 (a Chanakya-variant
    # font with KrutiDev-like keyboard layout).  The 'o' glyph in this
    # font combines with following matra + Q to form क-based tokens,
    # and 'iQ' forms फ (replacing standalone Q=फ for this font).
    "oaQ": "कं",  # oaQputa?kk → कंचनजंघा (Kanchenjunga), oaQcy → कंचनगर
    "oqQ": "कु",  # oqQN → कुछ (kuch)
    "owQ": "कू",  # LowQy → स्कूल (school)
    "oQ": "कु",  # eqloQjkus → मुस्कुराने (smile)
    "iQ": "फ",  # fiQj → फिर (again), fiQYe → फिल्म (film)
    "iwQ": "फू",  # iwQy → फूल (flower), iwQys → फूलों
    "m¡Q": "ऊँ",  # m¡QpkbZ → ऊँचाई (height)
    # ── Common high-frequency patterns ─────────────────────────────
    "osQ": "के",
    "kjk": "ारा",
    "dh": "की",
    "dk": "का",
    "esa": "में",
    "sa": "ें",
    "ksa": "ों",
    # ── Devanagari digits ──────────────────────────────────────────
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
    # ── Misc ───────────────────────────────────────────────────────
    "vkbZ": "आई",
    "kbZ": "ाई",
    "vkfn": "आदि",
    "\xd8e": "क्रम",  # Øe
    "\xe8": "ध",  # è
    "---": "…",
    "Z": "़",  # nukta
    # ── Mixed-mode PDF characters ──────────────────────────────────
    # These appear in PDFs where pypdf partially decodes KrutiDev glyphs.
    "R": "ऋ",
    "+": "़",  # nukta (ड+ा → ड़ा)
    "z": "\u094d\u0930",  # reph / eyelash ra (्र)
    "&": "-",  # compound joiner
    "\xb5": " ",  # µ — clause separator
    "A": "।",  # danda (sentence terminator)
    # ── Walkman-Chanakya905 single-char overrides ──────────────────
    # Font-specific WinAnsi codepoints extracted by pypdf.
    "\u00d8": "क्र",  # Ø — pØ → चक्र (chakra)
    "\u00d1": "कृ",  # Ñ — izÑfr → प्रकृति (nature)
    "\u00cd": "ऋ",  # Í — Íf"k → ऋषि (sage)
    "\u00b6": "\u201c",  # ¶ — opening dialog quote
    "\u00af": "\u093f\u0902",  # ¯ — िं (i-matra + anusvara), reordering handles placement
    "\u00bc": "\u0926\u094d\u0927",  # ¼ — द्ध (ddha conjunct for बौद्ध=Buddhist)
    "\u00b1": "एं",  # ± — xb± → गएं (went)
    "\u00b8": ",",  # ¸ — comma (sentence punctuation)
    "\u00aa": "\u094d\u0930",  # ª — र् (half-ra for conjuncts like ड्राइवर)
    "\u00dd": "\u0941\u0915",  # Ý — ुक (uk compound for रुकता=stopping)
    "\u201dk": "ज",  # "k (right double quote + k) — ज (ja) in Walkman-Chanakya905
    "\u201d": "ज",  # " (right double quote) — ज fallback
    "\u00d9": "ट",  # Ù — replaces standalone Q/फ in certain contexts
    "\u00e3": "ं",  # ã — anusvara (appears in ब्रांड)
    "\u00ed": "ख",  # í — ख (appears in शिखर context)
}


# ===================================================================== #
#  Chanakya → Unicode mapping                                           #
# ===================================================================== #

_CHANAKYA_TO_UNICODE: Dict[str, str] = {
    # ── Standalone vowels ──────────────────────────────────────────
    "A": "अ",
    "Aa": "आ",
    "ao": "ओ",
    "AO": "औ",
    # ── Consonants ─────────────────────────────────────────────────
    "k": "क",
    "K": "ख",
    "g": "ग",
    "G": "घ",
    "|": "ङ",
    "c": "च",
    "C": "छ",
    "j": "ज",
    "J": "झ",
    "\xac": "ञ",  # ¬
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
    # ── Matras ─────────────────────────────────────────────────────
    "a": "ा",
    "f": "ि",
    "i": "ि",
    "I": "ी",
    "u": "ु",
    "U": "ू",
    "o": "े",
    "O": "ै",
    # ── Special characters ─────────────────────────────────────────
    "\xb1": "ड़",  # ±
    "\xb2": "ढ़",  # ²
    # ── Additional consonants ───────────────────────────────────────
    "D": "ड",
    "Z": "ढ",
    "B": "भ",
    "e": "ए",
    "E": "ऐ",
    # ── Halant / Anusvara / Visarga / Chandrabindu / Nukta ──────────
    "\xa4": "्",  # ¤ — halant
    "M": "ं",
    "H": "ः",
    "`": "ँ",
    "q": "़",
    # ── Numbers ────────────────────────────────────────────────────
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


# ===================================================================== #
#  Pre-computed lookup tables (sorted longest-match-first)              #
# ===================================================================== #

_KRUTIDEV_KEYS: List[str] = sorted(_KRUTIDEV_TO_UNICODE.keys(), key=len, reverse=True)
_CHANAKYA_KEYS: List[str] = sorted(_CHANAKYA_TO_UNICODE.keys(), key=len, reverse=True)

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
_IMATRA_REORDER_REPL = r"\1\2" + _IMATRA
_IMATRA_ANUSVARA_REORDER_REPL = r"\1\2" + _IMATRA_ANUSVARA


def _reorder_imatra(match: re.Match) -> str:
    """Move ि or िं from before consonant cluster to after it."""
    if match.group(1):
        # िं + consonant(s) → consonant(s) + िं
        return match.group(1) + _IMATRA_ANUSVARA
    else:
        # ि + consonant(s) → consonant(s) + ि
        return match.group(2) + _IMATRA


class HindiPreprocessor:
    """
    Convert legacy Hindi font-encoded text to Unicode Devanagari.

    Handles KrutiDev and Chanakya fonts.  Uses longest-match token
    substitution with an i-matra reordering post-pass.
    """

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
            text:      Raw text (typically from ``pypdf`` extraction).
            font_type: ``"krutidev"``, ``"chanakya"``, or ``"auto"``.

        The converter:

        1. **Skips Devanagari Unicode** already present in the text
           (for mixed-mode PDFs where pypdf partially decodes glyphs).
        2. **Longest-match tokenisation** avoids partial replacements.
        3. **i-matra reordering** moves ``ि`` from KrutiDev visual
           position (before consonant) to Unicode position (after).
        """
        if not text:
            return text

        # Auto-detect font type when not specified
        if font_type == "auto":
            _, detected = HindiPreprocessor.detect_encoding(text)
            font_type = detected if detected != "unknown" else "krutidev"

        # Select mapping table
        if font_type == "chanakya":
            mapping = _CHANAKYA_TO_UNICODE
            keys = _CHANAKYA_KEYS
        else:
            mapping = _KRUTIDEV_TO_UNICODE
            keys = _KRUTIDEV_KEYS

        # ── Pass 1: Token-by-token substitution ────────────────────
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

            # Try longest KrutiDev/Chanakya match at current position
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

        # ── Pass 2: Reorder i-matra (ि and िं) ──────────────────────
        # Only needed for KrutiDev (Chanakya doesn't have this issue)
        if font_type == "krutidev":
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

        corrections = [
            # ── Remove doubled matras ──────────────────────────────
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
            # ── Walkman-Chanakya905 artifacts ───────────────────────
            # Font encodes एं as 'b±' giving इएं instead of एं
            ("इएं", "एं"),
            ("आइएं", "आएं"),
            # Halant + aa-matra is invalid; the aa-matra wins
            ("\u094d\u093e", "\u093e"),  # ् + ा → ा
            # ── Common word-level corrections ──────────────────────
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
        if font_type == "chanakya":
            return _CHANAKYA_TO_UNICODE
        return _KRUTIDEV_TO_UNICODE
