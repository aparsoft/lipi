"""
Parallel batch text-cleaning helpers.

Wraps :func:`lipi.text_pipeline.clean_extracted_text` in a process pool so a
directory of pre-extracted Hindi text files can be cleaned in one call.

The corrector is heavy to construct (lexicon index build, optional SymSpell
dictionary load, optional KenLM model load) but cheap to call. We therefore
build it **once per worker process** in an initialiser and reuse it for every
file the worker processes — this is the dominant speedup vs naive ``Pool.map``
that re-imports for each task.

Public API:

* :class:`BatchConfig` — typed config for a batch job.
* :func:`process_path` — single-file worker entrypoint (also usable directly).
* :func:`run_batch` — top-level launcher; returns an iterator of result dicts.
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """Configuration for a parallel batch run."""

    correction_mode: str = "safe"  # "none" | "safe" | "aggressive"
    font_type: str = "auto"
    use_symspell: bool = False
    symspell_dictionary_path: Optional[str] = None
    symspell_max_edit_distance: int = 2
    file_extensions: Sequence[str] = field(default_factory=lambda: (".txt",))
    workers: int = max(1, (os.cpu_count() or 2) - 1)
    file_encoding: str = "utf-8"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Worker-global corrector cache. Each process initialises its own instance
# inside ``_init_worker`` and keeps it for the lifetime of the worker.
_WORKER_STATE: Dict[str, Any] = {}


def _init_worker(config_dict: Dict[str, Any]) -> None:
    """Pool initialiser: build per-worker heavy objects once."""
    config = BatchConfig(**config_dict)
    _WORKER_STATE["config"] = config
    if config.use_symspell:
        # Lazy import so workers without SymSpell installed still work in the
        # non-SymSpell path.
        from lipi.symspell_corrector import SymSpellHindiCorrector

        corrector = SymSpellHindiCorrector(
            max_dictionary_edit_distance=config.symspell_max_edit_distance,
        )
        if config.symspell_dictionary_path:
            corrector.load_dictionary(config.symspell_dictionary_path)
        else:
            corrector = SymSpellHindiCorrector.from_default_dictionary(
                max_dictionary_edit_distance=config.symspell_max_edit_distance,
            )
        _WORKER_STATE["symspell"] = corrector


def _clean_one(text: str, config: BatchConfig) -> Dict[str, Any]:
    """Apply the deterministic pipeline + optional SymSpell layer."""
    from lipi.text_pipeline import clean_extracted_text

    result = clean_extracted_text(
        text,
        font_type=config.font_type,
        correction_mode=config.correction_mode,
    )

    if config.use_symspell and "symspell" in _WORKER_STATE:
        corrector = _WORKER_STATE["symspell"]
        corrected, ss_stats = corrector.correct(result["cleaned_text"])
        result["cleaned_text"] = corrected
        result["symspell_stats"] = {
            "tokens_seen": ss_stats.tokens_seen,
            "tokens_considered": ss_stats.tokens_considered,
            "tokens_corrected": ss_stats.tokens_corrected,
            "dictionary_size": ss_stats.dictionary_size,
            "corrections": ss_stats.corrections,
        }
        result["stages_applied"].append("symspell")
    return result


def process_path(path_str: str) -> Dict[str, Any]:
    """Worker entrypoint for a single file path."""
    config: BatchConfig = _WORKER_STATE.get("config") or BatchConfig()
    path = Path(path_str)
    try:
        text = path.read_text(encoding=config.file_encoding, errors="replace")
    except OSError as exc:
        return {"input_path": str(path), "error": f"read_error: {exc}"}

    try:
        result = _clean_one(text, config)
    except Exception as exc:  # noqa: BLE001 - report all failures
        logger.exception("Cleaning failed for %s", path)
        return {"input_path": str(path), "error": f"clean_error: {exc!r}"}

    return {
        "input_path": str(path),
        "char_count_in": len(text),
        "char_count_out": len(result["cleaned_text"]),
        "detected_font_type": result["detected_font_type"],
        "stages_applied": result["stages_applied"],
        "artifact_count_before": result["artifact_count_before"],
        "artifact_count_after": result["artifact_count_after"],
        "correction_mode": result["correction_mode"],
        "correction_stats": result["correction_stats"],
        "symspell_stats": result.get("symspell_stats"),
        "cleaned_text": result["cleaned_text"],
    }


def discover_files(root: Path, extensions: Sequence[str]) -> List[Path]:
    """Recursively list files under *root* whose suffix matches."""
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in extensions)


def run_batch(
    inputs: Iterable[Path],
    config: BatchConfig,
    chunksize: int = 4,
) -> Iterator[Dict[str, Any]]:
    """
    Process every file in *inputs* using a worker pool.

    Yields one result dict per file. Raises nothing — errors are reported in
    the result dict under the ``error`` key.
    """
    inputs_list = [str(p) for p in inputs]
    if not inputs_list:
        return iter(())

    if config.workers <= 1:
        _init_worker(config.to_dict())
        return (process_path(p) for p in inputs_list)

    pool = mp.Pool(
        processes=config.workers,
        initializer=_init_worker,
        initargs=(config.to_dict(),),
    )

    def _iter() -> Iterator[Dict[str, Any]]:
        try:
            yield from pool.imap_unordered(process_path, inputs_list, chunksize=chunksize)
        finally:
            pool.close()
            pool.join()

    return _iter()


def write_jsonl(results: Iterable[Dict[str, Any]], output_path: Path) -> int:
    """Stream batch results to a JSONL file. Returns row count."""
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


def summarise(jsonl_path: Path) -> Dict[str, Any]:
    """Build a summary report from a JSONL output file."""
    file_count = 0
    error_count = 0
    artifacts_removed = 0
    tokens_corrected = 0
    symspell_corrected = 0
    font_types: Dict[str, int] = {}

    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            file_count += 1
            if "error" in row:
                error_count += 1
                continue
            artifacts_removed += row["artifact_count_before"] - row["artifact_count_after"]
            tokens_corrected += row["correction_stats"].get("corrected_tokens", 0)
            if row.get("symspell_stats"):
                symspell_corrected += row["symspell_stats"].get("tokens_corrected", 0)
            ft = row.get("detected_font_type", "unknown")
            font_types[ft] = font_types.get(ft, 0) + 1

    return {
        "files": file_count,
        "errors": error_count,
        "artifacts_removed": artifacts_removed,
        "tokens_corrected_lexicon": tokens_corrected,
        "tokens_corrected_symspell": symspell_corrected,
        "font_types": font_types,
    }
