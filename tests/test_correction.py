"""Unit tests for the optional lexicon-based second-stage corrector."""

from lipi.correction import HindiLexiconCorrector, build_contextual_lexicon


class TestHindiLexiconCorrector:
    def test_corrects_using_normalized_lexicon_distance(self):
        corrector = HindiLexiconCorrector(lexicon_words={"वर्तमान", "प्रार्थना", "सिर्फ", "सफेद", "बर्फ"})

        result = corrector.correct_text("वत़मान प्राथ़ना सिप़्ा़फ सप़्ोफद बप़्ा़फ")

        assert "वर्तमान" in result["text"]
        assert "प्रार्थना" in result["text"]
        assert result["stats"]["corrected_tokens"] >= 2

    def test_leaves_short_tokens_unchanged(self):
        corrector = HindiLexiconCorrector(lexicon_words={"और", "था"})
        result = corrector.correct_text("और था", min_token_length=4)
        assert result["text"] == "और था"
        assert result["stats"]["corrected_tokens"] == 0

    def test_repairs_safe_j_imatra_swap_when_exact_candidate_exists(self):
        corrector = HindiLexiconCorrector(lexicon_words={"किसी", "जानवरों", "निश्चय", "जाता"})
        result = corrector.correct_text("जकसी िानवरों जनश्चय िाता")

        assert result["text"] == "किसी जानवरों निश्चय जाता"
        assert result["stats"]["corrected_tokens"] == 4

    def test_does_not_fuzzy_correct_unconfirmed_j_imatra_swap(self):
        corrector = HindiLexiconCorrector(lexicon_words={"क्या", "कथा"})
        result = corrector.correct_text("जकया", min_token_length=4)

        assert result["text"] == "जकया"
        assert result["stats"]["corrected_tokens"] == 0

    def test_normalizes_broken_ematra_sequences_before_lookup(self):
        corrector = HindiLexiconCorrector(lexicon_words={"मारती", "मारता", "मोती"})
        result = corrector.correct_text("मेारती मेारता मेोती")

        assert result["text"] == "मारती मारता मोती"
        assert result["stats"]["corrected_tokens"] == 3

    def test_broken_ematra_without_exact_match_does_not_fuzzy_jump(self):
        corrector = HindiLexiconCorrector(lexicon_words={"मार्ग", "मेरा"})
        result = corrector.correct_text("मेारो")

        assert result["text"] == "मेारो"
        assert result["stats"]["corrected_tokens"] == 0


class TestBuildContextualLexicon:
    def test_collects_repeated_clean_tokens(self):
        contextual = build_contextual_lexicon(
            [
                "गैंगटॉक एक सुंदर शहर है",
                "गैंगटॉक की रात सुंदर है",
                "व्फतिका जैसे शोर वाले शब्द नहीं लेने चाहिए",
            ],
            base_lexicon={"एक", "सुंदर", "शहर", "रात", "है"},
        )

        assert "गैंगटॉक" in contextual
        assert "व्फतिका" not in contextual
