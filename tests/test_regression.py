"""Unit tests for regression harness metrics."""

from lipi.regression import measure_text_quality


class TestMeasureTextQuality:
    def test_reports_lexicon_hits_and_artifacts(self):
        metrics = measure_text_quality(
            "वर्तमान प्रार्थना और सिप़्ा़फ A B",
            lexicon_words={"वर्तमान", "प्रार्थना", "और", "सिर्फ"},
        )

        assert metrics["token_count"] >= 3
        assert metrics["lexicon_hit_rate"] > 0
        assert metrics["artifact_counts"]["spurious_nukta"] >= 1
        assert metrics["artifact_counts"]["latin_residue"] >= 2

    def test_quality_index_prefers_cleaner_text(self):
        noisy = measure_text_quality(
            "वत़मान प्राथ़ना सिप़्ा़फ A A",
            lexicon_words={"वर्तमान", "प्रार्थना", "सिर्फ"},
        )
        clean = measure_text_quality(
            "वर्तमान प्रार्थना सिर्फ और रोशनी",
            lexicon_words={"वर्तमान", "प्रार्थना", "सिर्फ", "और", "रोशनी"},
        )

        assert clean["quality_index"] > noisy["quality_index"]