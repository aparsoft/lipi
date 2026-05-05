"""
Optional ML fallback for low-confidence Hindi token corrections.

Routes a small fraction (default ~5%) of tokens that the deterministic and
SymSpell layers could not confidently correct to a transformer model
(``ai4bharat/IndicBART`` by default). Designed for the production scenario
where you want to squeeze the last percent of quality out of a pipeline that
processes lakhs of pages.

This is **opt-in** and heavy. Install with::

    pip install "lipi-aparsoft[ml]"

Usage::

    from lipi.ml_fallback import IndicBARTSpellCorrector
    fallback = IndicBARTSpellCorrector()  # downloads model on first call
    corrected = fallback.correct_token("परराधीनता", context_left="महान राष्ट्र की", context_right="के दीन दिनों")

The fallback is plugged into the candidate scorer by registering it as the
``lm_score`` callable on a :class:`lipi.candidates.ScoringContext`.

Performance reality check: on CPU you should expect ~50 tokens/sec with
IndicBART. Use this only on the small subset of tokens flagged as low-
confidence by the upstream layers, never on every token.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ai4bharat/IndicBART"


class TransformersNotInstalled(ImportError):
    """Raised when the optional transformers / torch dependencies are missing."""


def _load_transformers():
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # type: ignore
        import torch  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guarded
        raise TransformersNotInstalled(
            "transformers / torch not installed. Install with: "
            'pip install "lipi-aparsoft[ml]"'
        ) from exc
    return AutoModelForSeq2SeqLM, AutoTokenizer, torch


class IndicBARTSpellCorrector:
    """
    IndicBART-based contextual spell-corrector for Hindi tokens.

    The first instantiation downloads the model (~500 MB) into the local
    HuggingFace cache. Subsequent runs reuse it.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
        max_length: int = 64,
    ) -> None:
        AutoModelForSeq2SeqLM, AutoTokenizer, torch = _load_transformers()
        self._torch = torch
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        logger.info("Loading %s on %s ...", model_name, device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(device)
        self.model.eval()

    def correct_token(
        self,
        token: str,
        context_left: str = "",
        context_right: str = "",
    ) -> str:
        """
        Predict a correction for *token* using surrounding context.

        Uses a simple "fill-in-the-blank" prompt; for production-grade
        correction quality, fine-tune the model on (corrupted, clean) pairs
        from your own corpus.
        """
        prompt = f"{context_left} <mask> {context_right}".strip()
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=self.max_length)
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self._torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=8,
                num_beams=4,
                early_stopping=True,
            )
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip() or token

    def batch_correct(
        self,
        tokens: List[str],
        contexts_left: Optional[List[str]] = None,
        contexts_right: Optional[List[str]] = None,
    ) -> List[str]:
        """Correct a batch of tokens. Slow on CPU; use for low-confidence subset only."""
        contexts_left = contexts_left or [""] * len(tokens)
        contexts_right = contexts_right or [""] * len(tokens)
        return [
            self.correct_token(token, left, right)
            for token, left, right in zip(tokens, contexts_left, contexts_right)
        ]
