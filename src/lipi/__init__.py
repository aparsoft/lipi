"""
Lipi — Legacy Hindi font (KrutiDev/Chanakya) to Unicode Devanagari toolkit.

Part of the Aparsoft EdTech toolchain — https://aparsoft.in
"""

from lipi.correction import HindiLexiconCorrector
from lipi.preprocessor import HindiPreprocessor
from lipi.regression import run_regression_harness

__version__ = "1.0.3"
__all__ = ["HindiPreprocessor", "HindiLexiconCorrector", "run_regression_harness"]
