"""
Lipi — Legacy Hindi font (KrutiDev/Chanakya) to Unicode Devanagari toolkit.

Part of the Aparsoft EdTech toolchain — https://aparsoft.com
"""

from lipi.correction import HindiLexiconCorrector
from lipi.preprocessor import HindiPreprocessor
from lipi.regression import run_regression_harness
from lipi.text_pipeline import clean_extracted_text

__version__ = "1.0.9"
__all__ = [
    "HindiPreprocessor",
    "HindiLexiconCorrector",
    "clean_extracted_text",
    "run_regression_harness",
]
