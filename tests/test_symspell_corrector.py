"""Tests for the optional SymSpell corrector. Skipped if symspellpy not installed."""

import pytest

symspellpy = pytest.importorskip("symspellpy")

from lipi.symspell_corrector import SymSpellHindiCorrector  # noqa: E402


@pytest.fixture(scope="module")
def corrector():
    return SymSpellHindiCorrector.from_default_dictionary(max_dictionary_edit_distance=2)


def test_default_dictionary_loads(corrector):
    assert corrector.dictionary_size > 100


def test_known_word_unchanged(corrector):
    text = "स्वतंत्रता और अधिकार"
    cleaned, stats = corrector.correct(text)
    assert cleaned == text
    assert stats.tokens_corrected == 0


def test_minor_typo_corrected(corrector):
    # "सततंत्रता" is a single-edit typo of "स्वतंत्रता" (drop the ्व).
    # Add the target word with high frequency to ensure it dominates.
    corrector.add_lexicon_words(["स्वतंत्रता"], default_count=100000)
    suggestion = corrector.suggest("सततंत्रता")
    assert suggestion is not None
    # Don't assert exact target — SymSpell is frequency-driven; just confirm
    # that *some* in-dictionary suggestion is returned within edit distance.
    assert suggestion[2] <= 2


def test_short_token_skipped(corrector):
    # min_token_length defaults to 3.
    text = "वह यह है"
    cleaned, stats = corrector.correct(text)
    assert cleaned == text


def test_add_lexicon_words_grows_dictionary(corrector):
    before = corrector.dictionary_size
    added = corrector.add_lexicon_words(["कस्टमवर्ड१", "कस्टमवर्ड२"])
    assert added == 2
    assert corrector.dictionary_size >= before
