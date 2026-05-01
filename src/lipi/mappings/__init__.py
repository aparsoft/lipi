"""
Font mapping tables for legacy Hindi font conversion.

Merges Walkman-Chanakya905 overrides into the KrutiDev base table so that
the combined dict is identical to what the old single-file code produced.
"""

from lipi.mappings.krutidev import KRUTIDEV_TO_UNICODE
from lipi.mappings.chanakya import CHANAKYA_TO_UNICODE
from lipi.mappings.walkman_chanakya import WALKMAN_CHANAKYA_OVERRIDES

# Full KrutiDev table with Walkman-Chanakya905 overrides merged in.
KRUTIDEV_FULL: dict[str, str] = {**KRUTIDEV_TO_UNICODE, **WALKMAN_CHANAKYA_OVERRIDES}

# Top-level lookup used by the preprocessor.
FONT_MAPPINGS: dict[str, dict[str, str]] = {
    "krutidev": KRUTIDEV_FULL,
    "chanakya": CHANAKYA_TO_UNICODE,
    "walkman_chanakya": KRUTIDEV_FULL,
}
