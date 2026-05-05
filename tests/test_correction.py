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

    def test_repairs_structural_duplication_when_exact_candidate_exists(self):
        corrector = HindiLexiconCorrector(lexicon_words={"वाक्यों", "जन्म", "यात्रा", "किया", "वृत्तांत"})
        result = corrector.correct_text("वाक््यों जन््मम ययात्रा कियया वृत््ताांांत")

        assert result["text"] == "वाक्यों जन्म यात्रा किया वृत्तांत"
        assert result["stats"]["corrected_tokens"] == 5

    def test_structural_duplication_without_exact_match_does_not_fuzzy_jump(self):
        corrector = HindiLexiconCorrector(lexicon_words={"वादियों", "स्थगित", "स्थल"})
        result = corrector.correct_text("वाक््यों")

        assert result["text"] == "वाक््यों"
        assert result["stats"]["corrected_tokens"] == 0

    def test_repairs_exact_stray_imatra_insertions(self):
        corrector = HindiLexiconCorrector(
            lexicon_words={"शब्द", "शब्दों", "यह", "यही", "यथार्थता", "आनंद"},
            max_distance=0,
        )
        result = corrector.correct_text(
            "शिब्द शिब्दों यिह यिही यिथार्थता आनिंद",
            min_token_length=1,
        )

        assert result["text"] == "शब्द शब्दों यह यही यथार्थता आनंद"
        assert result["stats"]["corrected_tokens"] == 6

    def test_does_not_drop_imatra_from_clean_words(self):
        corrector = HindiLexiconCorrector(
            lexicon_words={"व्यक्त", "बना", "यह", "व्यक्ति", "बिना"},
            max_distance=0,
        )
        result = corrector.correct_text("व्यक्ति बिना", min_token_length=1)

        assert result["text"] == "व्यक्ति बिना"
        assert result["stats"]["corrected_tokens"] == 0

    def test_default_lexicon_preserves_vyakti_but_fixes_common_textbook_noise(self):
        corrector = HindiLexiconCorrector(max_distance=0)
        result = corrector.correct_text("व्यक्ति दीववार चुनावव गौरवव", min_token_length=1)

        assert result["text"] == "व्यक्ति दीवार चुनाव गौरव"
        assert result["stats"]["corrected_tokens"] == 3

    def test_full_range_repeated_consonants_can_resolve_by_exact_match(self):
        corrector = HindiLexiconCorrector(
            lexicon_words={"विशेष", "शब्द", "शब्दों", "संपूर्ण", "नागार्जुन", "आठ"},
            max_distance=0,
        )
        result = corrector.correct_text(
            "विशशेष शशब््दद शशब््दोों ससंपूर्ण ननागार्जजुनन आठठ",
            min_token_length=1,
        )

        assert result["text"] == "विशेष शब्द शब्दों संपूर्ण नागार्जुन आठ"
        assert result["stats"]["corrected_tokens"] == 6


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
