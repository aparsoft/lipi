"""Unit tests for the optional lexicon-based second-stage corrector."""

from lipi.correction import HindiLexiconCorrector, build_contextual_lexicon


class TestHindiLexiconCorrector:
    def test_corrects_using_normalized_lexicon_distance(self):
        corrector = HindiLexiconCorrector(
            lexicon_words={"वर्तमान", "प्रार्थना", "सिर्फ", "सफेद", "बर्फ"}
        )

        result = corrector.correct_text("वत़मान प्राथ़ना सिप़्ा़फ सप़्ोफद बप़्ा़फ")

        assert "वर्तमान" in result["text"]
        assert "प्रार्थना" in result["text"]
        assert result["stats"]["corrected_tokens"] >= 2

    def test_leaves_short_tokens_unchanged(self):
        corrector = HindiLexiconCorrector(lexicon_words={"और", "था"})
        result = corrector.correct_text("और था", min_token_length=4)
        assert result["text"] == "और था"
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