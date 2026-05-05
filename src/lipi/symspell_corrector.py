"""
Optional SymSpell-backed corrector for Hindi text.

This is an **opt-in** alternative to :class:`lipi.correction.HindiLexiconCorrector`.
It uses the SymSpell algorithm (Wolf Garbe, 2012) for O(1) lookups against a
frequency-weighted dictionary — typically 10×-100× faster than bounded
Levenshtein and with much higher recall on inflected forms.

Install the optional dependency::

    pip install "lipi-aparsoft[symspell]"

Usage::

    from lipi.symspell_corrector import SymSpellHindiCorrector

    corrector = SymSpellHindiCorrector.from_default_dictionary()
    cleaned, stats = corrector.correct("परराधीनता के दीन दिनोों में")

The default dictionary path is :data:`DEFAULT_FREQ_DICTIONARY`, which can be
overridden by setting the ``LIPI_FREQ_DICT`` environment variable or by
passing ``dictionary_path=...`` to :meth:`from_default_dictionary`.

A separate ``hunspell-hi`` dictionary may be merged in via
:meth:`SymSpellHindiCorrector.add_lexicon_words` for additional recall.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[\u0900-\u0963\u0970-\u097f]+")
DEFAULT_FREQ_DICTIONARY = "data/hindi_freq_small.txt"


class SymSpellNotInstalled(ImportError):
    """Raised when the optional ``symspellpy`` dependency is missing."""


def _load_symspell():
    try:
        from symspellpy import SymSpell, Verbosity  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guarded
        raise SymSpellNotInstalled(
            "symspellpy is not installed. Install with: " 'pip install "lipi-aparsoft[symspell]"'
        ) from exc
    return SymSpell, Verbosity


def _resolve_default_dictionary_path(override: Optional[str] = None) -> str:
    """Resolve the bundled default frequency dictionary path."""
    env_override = os.environ.get("LIPI_FREQ_DICT")
    if override:
        return override
    if env_override:
        return env_override
    with resources.as_file(resources.files("lipi").joinpath(DEFAULT_FREQ_DICTIONARY)) as path:
        return str(path)


@dataclass
class SymSpellCorrectionStats:
    tokens_seen: int = 0
    tokens_considered: int = 0
    tokens_corrected: int = 0
    corrections: List[Dict[str, str]] = field(default_factory=list)
    dictionary_size: int = 0


class SymSpellHindiCorrector:
    """SymSpell-backed Hindi token corrector with frequency tiebreak."""

    def __init__(
        self,
        max_dictionary_edit_distance: int = 2,
        prefix_length: int = 7,
        min_token_length: int = 3,
    ) -> None:
        SymSpell, Verbosity = _load_symspell()
        self._SymSpell = SymSpell
        self._Verbosity = Verbosity
        self._symspell = SymSpell(
            max_dictionary_edit_distance=max_dictionary_edit_distance,
            prefix_length=prefix_length,
        )
        self.max_dictionary_edit_distance = max_dictionary_edit_distance
        self.min_token_length = min_token_length
        self._dictionary_size = 0

    # ----- dictionary loading -------------------------------------------------

    def load_dictionary(
        self,
        dictionary_path: str,
        term_index: int = 0,
        count_index: int = 1,
        encoding: str = "utf-8",
    ) -> int:
        """Load a SymSpell-format frequency dictionary file (``word<sep>count``)."""
        ok = self._symspell.load_dictionary(
            dictionary_path,
            term_index=term_index,
            count_index=count_index,
            encoding=encoding,
        )
        if not ok:
            raise FileNotFoundError(f"Could not load dictionary: {dictionary_path}")
        self._dictionary_size = len(self._symspell.words)
        return self._dictionary_size

    def add_lexicon_words(self, words: Iterable[str], default_count: int = 1) -> int:
        """Add extra lexicon words (e.g. from hunspell-hi) with a default count."""
        added = 0
        for word in words:
            word = word.strip()
            if not word:
                continue
            self._symspell.create_dictionary_entry(word, default_count)
            added += 1
        self._dictionary_size = len(self._symspell.words)
        return added

    @property
    def dictionary_size(self) -> int:
        return self._dictionary_size

    @classmethod
    def from_default_dictionary(
        cls,
        dictionary_path: Optional[str] = None,
        max_dictionary_edit_distance: int = 2,
        min_token_length: int = 3,
    ) -> "SymSpellHindiCorrector":
        """Build a corrector from the bundled small frequency dictionary."""
        corrector = cls(
            max_dictionary_edit_distance=max_dictionary_edit_distance,
            min_token_length=min_token_length,
        )
        corrector.load_dictionary(_resolve_default_dictionary_path(dictionary_path))
        return corrector

    # ----- correction --------------------------------------------------------

    def suggest(self, token: str) -> Optional[Tuple[str, float, int]]:
        """
        Return the best ``(suggestion, frequency, edit_distance)`` for *token*,
        or ``None`` if no candidate within the configured edit distance exists.
        """
        results = self._symspell.lookup(
            token,
            self._Verbosity.TOP,
            max_edit_distance=self.max_dictionary_edit_distance,
            include_unknown=False,
            transfer_casing=False,
        )
        if not results:
            return None
        best = results[0]
        return best.term, float(best.count), int(best.distance)

    def correct(
        self,
        text: str,
        max_recorded_corrections: int = 20,
    ) -> Tuple[str, SymSpellCorrectionStats]:
        """Correct every Devanagari token in *text* using SymSpell."""
        stats = SymSpellCorrectionStats(dictionary_size=self._dictionary_size)
        if not text:
            return text, stats

        def replace(match: re.Match) -> str:
            token = match.group(0)
            stats.tokens_seen += 1
            if len(token) < self.min_token_length:
                return token
            # Already-known words are returned by lookup with distance=0;
            # only count "considered" when token is NOT exactly in dictionary.
            if token in self._symspell.words:
                return token
            stats.tokens_considered += 1
            suggestion = self.suggest(token)
            if not suggestion or suggestion[0] == token:
                return token
            stats.tokens_corrected += 1
            if len(stats.corrections) < max_recorded_corrections:
                stats.corrections.append(
                    {
                        "from": token,
                        "to": suggestion[0],
                        "distance": str(suggestion[2]),
                    }
                )
            return suggestion[0]

        return _WORD_RE.sub(replace, text), stats
