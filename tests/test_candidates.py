"""Tests for the candidate-generator architecture."""

from lipi.candidates import (
    Candidate,
    DEFAULT_TOKEN_RULES,
    ScoringContext,
    correct_text,
    generate_token_candidates,
    select_best,
)


def test_keep_original_always_present():
    candidates = generate_token_candidates("रुककर")
    assert any(c.text == "रुककर" for c in candidates)


def test_doubled_consonant_yields_both_keep_and_imatra_candidates():
    candidates = generate_token_candidates("रुककर")
    texts = {c.text for c in candidates}
    # baseline (keep) and the legacy-font hypothesis must both be available.
    assert "रुककर" in texts
    assert "रुकिककर" not in texts  # sanity
    assert "रुकिर" in texts  # CC -> Cि candidate exists
    assert "रुकर" in texts  # CC -> C candidate exists


def test_lexicon_vetoes_destructive_imatra_candidate():
    """If the original word is in the lexicon, the i-injection must lose."""
    context = ScoringContext(lexicon={"रुककर"})
    candidates = generate_token_candidates("रुककर")
    winner = select_best(candidates, context)
    assert winner.text == "रुककर"


def test_lexicon_picks_clean_form_over_corrupted_keep():
    """``जन््मम`` is not in lexicon, but ``जन्म`` is — it should win."""
    context = ScoringContext(lexicon={"जन्म"})
    candidates = generate_token_candidates("जन््मम")
    texts = {c.text for c in candidates}
    assert "जन्म" in texts
    winner = select_best(candidates, context)
    assert winner.text == "जन्म"


def test_correct_text_preserves_real_geminates_with_lexicon():
    text = "थोड़ी देर रुककर वह चौंककर उठा। महाकुंभ हो गया।"
    context = ScoringContext(lexicon={"रुककर", "चौंककर", "महाकुंभ"})
    cleaned, stats = correct_text(text, context=context)
    assert "रुककर" in cleaned and "रुकिर" not in cleaned
    assert "चौंककर" in cleaned and "चौंकिर" not in cleaned
    assert "महाकुंभ" in cleaned and "मिहाकुंभ" not in cleaned
    assert stats.tokens_changed == 0


def test_correct_text_records_corrections():
    text = "जन््मम और स््थथित"
    context = ScoringContext(lexicon={"जन्म", "स्थित"})
    cleaned, stats = correct_text(text, context=context)
    assert "जन्म" in cleaned and "स्थित" in cleaned
    assert stats.tokens_changed >= 2
    assert any(c.original == "जन््मम" for c in stats.corrections)


def test_default_rules_include_keep_first():
    # ``keep_original`` must be the first rule so its candidate is the baseline
    # available to every scorer.
    assert DEFAULT_TOKEN_RULES[0].__name__ == "keep_original"


def test_select_best_prefers_higher_confidence_when_no_lexicon():
    candidates = [
        Candidate(text="A", confidence=0.5, reason="keep"),
        Candidate(text="B", confidence=0.9, reason="strong_rule"),
    ]
    assert select_best(candidates).text == "B"


def test_frequency_weight_breaks_ties():
    # Two candidates within the lexicon — frequency should pick the more common.
    context = ScoringContext(
        lexicon={"AB", "CD"},
        frequency={"AB": 1.0, "CD": 10000.0},
    )
    candidates = [
        Candidate(text="AB", confidence=0.8, reason="r1"),
        Candidate(text="CD", confidence=0.8, reason="r2"),
    ]
    assert select_best(candidates, context).text == "CD"
