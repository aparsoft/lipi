"""
Walkman-Chanakya905 overrides for the KrutiDev mapping table.

These font-specific entries appear when pypdf extracts text from PDFs that
use Walkman-Chanakya905 (a Chanakya-variant font with KrutiDev-like keyboard
layout).  They are *additions* to the KrutiDev base table, merged at runtime
by ``lipi.mappings``.
"""

WALKMAN_CHANAKYA_OVERRIDES: dict[str, str] = {
    # -- Multi-char tokens --
    # The 'o' glyph in this font combines with following matra + Q to form
    # क-based tokens, and 'iQ' forms फ.
    "oaQ": "कं",  # oaQputa?kk → कंचनजंघा (Kanchenjunga)
    "oqQ": "कु",  # oqQN → कुछ (kuch)
    "owQ": "कू",  # LowQy → स्कूल (school)
    "oQ": "कु",  # eqloQjkus → मुस्कुराने (smile)
    "iQ": "फ",  # fiQj → फिर (again)
    "iwQ": "फू",  # iwQy → फूल (flower)
    "m¡Q": "ऊँ",  # m¡QpkbZ → ऊँचाई (height)
    # -- Single-char overrides --
    # Font-specific WinAnsi codepoints extracted by pypdf.
    "\u00d8": "क्र",  # Ø — pØ → चक्र (chakra)
    "\u00d1": "कृ",  # Ñ — izÑfr → प्रकृति (nature)
    "\u00cd": "ऋ",  # Í — Íf"k → ऋषि (sage)
    "\u00b6": "\u201c",  # ¶ — opening dialog quote
    "\u00af": "\u093f\u0902",  # ¯ — िं (i-matra + anusvara)
    "\u00bc": "\u0926\u094d\u0927",  # ¼ — द्ध (ddha conjunct)
    "\u00b1": "एं",  # ± — xb± → गएं (went)
    "\u00b8": ",",  # ¸ — comma (sentence punctuation)
    "\u00aa": "\u094d\u0930",  # ª — र् (half-ra for conjuncts)
    "\u00dd": "\u0941\u0915",  # Ý — ुक (uk compound)
    "\u201dk": "ज",  # "k (right double quote + k) — ज
    "\u201d": "ज",  # " (right double quote) — ज fallback
    "\u00d9": "ट",  # Ù — replaces standalone Q/फ in certain contexts
    "\u00e3": "ं",  # ã — anusvara
    "\u00ed": "ख",  # í — ख
}
