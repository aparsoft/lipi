"""
Backward-compatibility shim for hindi_preprocessor.py.

All functionality has been moved to the ``lipi`` package.
Existing imports like ``from hindi_preprocessor import HindiPreprocessor``
will continue to work.
"""

from lipi.preprocessor import HindiPreprocessor
from lipi.mappings import FONT_MAPPINGS

# Aliases matching the old module-level names
_KRUTIDEV_TO_UNICODE = FONT_MAPPINGS["krutidev"]
_CHANAKYA_TO_UNICODE = FONT_MAPPINGS["chanakya"]

__version__ = "1.0.0"
__all__ = [
    "HindiPreprocessor",
    "_KRUTIDEV_TO_UNICODE",
    "_CHANAKYA_TO_UNICODE",
]
