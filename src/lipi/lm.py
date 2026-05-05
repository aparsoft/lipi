"""
Optional KenLM character-LM tiebreaker for token candidates.

This is a thin, opt-in wrapper around ``kenlm`` for use as a final scorer in
:mod:`lipi.candidates`. It loads a 3- or 5-gram **character-level** ARPA / BIN
model trained on clean Hindi text and exposes a single ``score(token) -> float``
callable that integrates with :class:`lipi.candidates.ScoringContext`.

Install the optional dependency::

    pip install "lipi-aparsoft[lm]"

Auto-download the bundled small model::

    from lipi.lm import load_default_char_lm
    lm = load_default_char_lm(auto_download=True)

The default model URL is configurable via the ``LIPI_LM_URL`` environment
variable. To train your own (recommended for production), see
``tools/train_kenlm.py``.

The KenLM model itself is **not bundled** with the wheel — it is downloaded on
first use into ``~/.cache/lipi/`` (override with ``LIPI_CACHE_DIR``).
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_LM_URL = os.environ.get(
    "LIPI_LM_URL",
    "",  # intentionally empty — opt in by setting env or passing url=
)
DEFAULT_LM_FILENAME = "hindi_char_3gram.arpa"


class KenLMNotInstalled(ImportError):
    """Raised when the optional ``kenlm`` dependency is missing."""


def _cache_dir() -> Path:
    base = os.environ.get("LIPI_CACHE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "lipi"
    )
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_kenlm():
    try:
        import kenlm  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guarded
        raise KenLMNotInstalled(
            "kenlm is not installed. Install with: " 'pip install "lipi-aparsoft[lm]"'
        ) from exc
    return kenlm


def _download(url: str, destination: Path, expected_sha256: Optional[str] = None) -> Path:
    try:
        import requests  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guarded
        raise ImportError(
            "requests is required for auto-download. Install with: "
            'pip install "lipi-aparsoft[lm]"'
        ) from exc

    logger.info("Downloading LM model from %s -> %s", url, destination)
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)

    if expected_sha256:
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != expected_sha256:
            destination.unlink(missing_ok=True)
            raise IOError(
                f"SHA256 mismatch for {destination.name}: got {digest}, "
                f"expected {expected_sha256}"
            )
    return destination


class CharKenLM:
    """Character-level KenLM wrapper that returns per-token log-prob scores."""

    def __init__(self, model_path: str, weight: float = 0.05) -> None:
        kenlm = _load_kenlm()
        self.model_path = model_path
        self.weight = weight
        self._model = kenlm.Model(model_path)

    def char_log_prob(self, token: str) -> float:
        """Mean per-character log-prob (length-normalised)."""
        if not token:
            return 0.0
        spaced = " ".join(token)
        return self._model.score(spaced, bos=False, eos=False) / max(len(token), 1)

    def __call__(self, token: str) -> float:
        return self.weight * self.char_log_prob(token)


def load_default_char_lm(
    url: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    expected_sha256: Optional[str] = None,
    auto_download: bool = True,
    weight: float = 0.05,
) -> CharKenLM:
    """
    Load (and optionally download) the default character LM.

    Set ``LIPI_LM_URL`` in the environment, or pass ``url=...`` explicitly.
    """
    cache = cache_dir or _cache_dir()
    destination = cache / DEFAULT_LM_FILENAME

    if not destination.exists():
        if not auto_download:
            raise FileNotFoundError(
                f"LM model not found at {destination}. Pass auto_download=True or "
                f"set LIPI_LM_URL and re-run."
            )
        download_url = url or DEFAULT_LM_URL
        if not download_url:
            raise RuntimeError(
                "No LM download URL configured. Train one with tools/train_kenlm.py "
                "and either set LIPI_LM_URL or pass url=..."
            )
        _download(download_url, destination, expected_sha256)

    return CharKenLM(str(destination), weight=weight)


def make_lm_score_callback(lm: CharKenLM) -> Callable[[str], float]:
    """Adapter: return a function suitable for :attr:`ScoringContext.lm_score`."""
    return lm
