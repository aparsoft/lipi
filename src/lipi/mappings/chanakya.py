"""
Chanakya -> Unicode Devanagari mapping table.

Chanakya is a legacy Hindi font encoding used in older government and
educational PDFs.  Unlike KrutiDev, it does not require i-matra reordering.
"""

CHANAKYA_TO_UNICODE: dict[str, str] = {
    # -- Standalone vowels --
    "A": "अ",
    "Aa": "आ",
    "ao": "ओ",
    "AO": "औ",
    # -- Consonants --
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
    # -- Matras --
    "a": "ा",
    "f": "ि",
    "i": "ि",
    "I": "ी",
    "u": "ु",
    "U": "ू",
    "o": "े",
    "O": "ै",
    # -- Special characters --
    "\xb1": "ड़",  # ±
    "\xb2": "ढ़",  # ²
    # -- Additional consonants --
    "D": "ड",
    "Z": "ढ",
    "B": "भ",
    "e": "ए",
    "E": "ऐ",
    # -- Halant / Anusvara / Visarga / Chandrabindu / Nukta --
    "\xa4": "्",  # ¤ — halant
    "M": "ं",
    "H": "ः",
    "`": "ँ",
    "q": "़",
    # -- Numbers --
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
