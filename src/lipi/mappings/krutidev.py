"""
KrutiDev -> Unicode Devanagari mapping table.

KrutiDev is a glyph-based encoding where characters are stored in visual
(left-to-right) order.  Consonants have a "half form" (consonant + halant)
used before another consonant in a conjunct.  The i-matra appears *before*
the consonant in the encoded text but must be placed *after* in Unicode.

Sources: KrutiDev 010 glyph table, OLD PDF reverse-engineering.
"""

KRUTIDEV_TO_UNICODE: dict[str, str] = {
    # -- Standalone vowels --
    "v": "\u0905",  # अ
    "vk": "\u0906",  # आ
    "b": "\u0907",  # इ
    "bZ": "\u0908",  # ई
    "m": "\u0909",  # उ
    "\u00c5": "\u090a",  # Å → ऊ
    "\u00bd": "\u090b",  # ½ → ऋ
    ",": "\u090f",  # ए
    ",s": "\u0910",  # ऐ
    "vks": "\u0913",  # ओ
    "vkS": "\u0914",  # औ
    "va": "\u0905\u0902",  # अं
    "v%": "\u0905\u0903",  # अः
    "vkW": "\u0911",  # ऑ
    # -- Consonants --
    "d": "\u0915",  # क
    "[k": "\u0916",  # ख
    "x": "\u0917",  # ग
    "?k": "\u0918",  # घ
    "\u00b3": "\u0919",  # ³ → ङ
    "p": "\u091a",  # च
    "N": "\u091b",  # छ
    "t": "\u091c",  # ज
    ">": "\u091d",  # झ
    "\u00a5": "\u091e",  # ¥ → ञ
    "V": "\u091f",  # ट
    "B": "\u0920",  # ठ
    "M": "\u0921",  # ड
    "<": "\u0922",  # ढ
    ".k": "\u0923",  # ण
    "r": "\u0924",  # त
    "Fk": "\u0925",  # थ
    "n": "\u0926",  # द
    "/k": "\u0927",  # ध
    "u": "\u0928",  # न
    "i": "\u092a",  # प
    "Q": "\u092b",  # फ
    "c": "\u092c",  # ब
    "Hk": "\u092d",  # भ
    "e": "\u092e",  # म
    ";": "\u092f",  # य
    "j": "\u0930",  # र
    "y": "\u0932",  # ल
    "o": "\u0935",  # व
    "'k": "\u0936",  # श
    "\u201ck": "\u0937",  # "k → ष
    "l": "\u0938",  # स
    "g": "\u0939",  # ह
    # -- Conjuncts / special forms --
    "\u00e2": "\u0924\u094d\u0930",  # â → त्र
    "K": "\u091c\u094d\u091e",  # ज्ञ
    "J": "\u0936\u094d\u0930",  # श्र
    "D;": "\u0915\u094d\u092f",  # क्य
    "{k": "\u0915\u094d\u0937",  # क्ष
    # -- Vowel matras (dependent vowel signs) --
    "k": "\u093e",  # ा (aa-matra)
    "f": "\u093f",  # ि (i-matra, PRE-BASE)
    "h": "\u0940",  # ी (ii-matra)
    "q": "\u0941",  # ु (u-matra)
    "w": "\u0942",  # ू (uu-matra)
    "`": "\u094d",  # ् (halant / virama)
    "s": "\u0947",  # े (e-matra)
    "S": "\u0948",  # ै (ai-matra)
    "ks": "\u094b",  # ो (o-matra)
    "kS": "\u094c",  # ौ (au-matra)
    "W": "\u0949",  # ॉ (candra-o matra)
    "a": "\u0902",  # ं (anusvara)
    "%": "\u0903",  # ः (visarga)
    "\u00a1": "\u0901",  # ¡ → ँ (chandrabindu)
    "~": "\u094d",  # ् (halant alternate)
    # -- Half-forms (consonant + halant) --
    "D": "\u0915\u094d",  # क्
    "[": "\u0916\u094d",  # ख्
    "X": "\u0917\u094d",  # ग्
    "?": "\u0918\u094d",  # घ्
    "P": "\u091a\u094d",  # च्
    "T": "\u091c\u094d",  # ज्
    "U": "\u0928\u094d",  # न्
    "I": "\u092a\u094d",  # प्
    "C": "\u092c\u094d",  # ब्
    "H": "\u092d\u094d",  # भ्
    "E": "\u092e\u094d",  # म्
    "\xb8": "\u092f\u094d",  # ¸ → य्
    "Y": "\u0932\u094d",  # ल्
    "O": "\u0935\u094d",  # व्
    "'": "\u0936\u094d",  # श्
    '"': "\u0937\u094d",  # ष्
    "L": "\u0938\u094d",  # स्
    "\xbb": "\u0939\u094d",  # » → ह्
    "=": "\u0924\u094d",  # त्
    "F": "\u0925\u094d",  # थ्
    "/": "\u0926\u094d",  # द्
    # -- Common high-frequency patterns --
    "osQ": "\u0915\u0947",  # के
    "kjk": "\u093e\u0930\u093e",  # ारा
    "dh": "\u0915\u0940",  # की
    "dk": "\u0915\u093e",  # का
    "esa": "\u092e\u0947\u0902",  # में
    "sa": "\u0947\u0902",  # ें
    "ksa": "\u094b\u0902",  # ों
    # -- Devanagari digits --
    "0": "\u0966",  # ०
    "1": "\u0967",  # १
    "2": "\u0968",  # २
    "3": "\u0969",  # ३
    "4": "\u096a",  # ४
    "5": "\u096b",  # ५
    "6": "\u096c",  # ६
    "7": "\u096d",  # ७
    "8": "\u096e",  # ८
    "9": "\u096f",  # ९
    # -- Misc --
    "vkbZ": "\u0906\u0908",  # आई
    "kbZ": "\u093e\u0908",  # ाई
    "vkfn": "\u0906\u0926\u093f",  # आदि
    "\xd8e": "\u0915\u094d\u0930\u092e",  # Øe → क्रम
    "\xe8": "\u0927",  # è → ध
    "---": "\u2026",  # …
    "Z": "\u093c",  # ़ (nukta)
    # -- Mixed-mode PDF characters --
    "R": "\u090b",  # ऋ
    "+": "\u093c",  # ़ (nukta)
    "z": "\u094d\u0930",  # ्र (reph)
    "&": "-",  # compound joiner
    "\xb5": " ",  # µ — clause separator
    "A": "\u0964",  # । (danda)
}
