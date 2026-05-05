#!/usr/bin/env python3
"""
Train a character-level KenLM 3-gram model on clean Hindi text.

Requires the KenLM CLI tools (``lmplz``, ``build_binary``) to be on PATH.
Install them once on Debian/Ubuntu::

    sudo apt-get install build-essential cmake libboost-all-dev
    git clone https://github.com/kpu/kenlm.git && cd kenlm
    mkdir -p build && cd build && cmake .. && make -j

Usage::

    python tools/train_kenlm.py corpus.txt --order 3 -o hindi_char_3gram.arpa

Then host the resulting ``.arpa`` (or compiled ``.bin``) somewhere reachable
and point users at it via ``LIPI_LM_URL=https://your.cdn/hindi_char_3gram.arpa``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

WORD_RE = re.compile(r"[\u0900-\u0963\u0970-\u097f]+")


def char_tokenize_corpus(input_paths: list[Path], output_path: Path) -> int:
    """Convert a token corpus into a *space-separated character* corpus."""
    written = 0
    with output_path.open("w", encoding="utf-8") as out:
        for path in input_paths:
            with path.open("r", encoding="utf-8", errors="replace") as inp:
                for line in inp:
                    for token in WORD_RE.findall(line):
                        out.write(" ".join(token))
                        out.write("\n")
                        written += 1
    return written


def run_lmplz(char_corpus: Path, arpa_path: Path, order: int, lmplz_bin: str) -> None:
    cmd = [lmplz_bin, "-o", str(order), "--text", str(char_corpus), "--arpa", str(arpa_path)]
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="Plain-text corpus files")
    parser.add_argument("-o", "--output", required=True, help="Output ARPA path")
    parser.add_argument("--order", type=int, default=3, help="N-gram order (default: 3)")
    parser.add_argument(
        "--char-corpus",
        default="char_corpus.txt",
        help="Intermediate space-separated char corpus path (default: char_corpus.txt)",
    )
    parser.add_argument("--lmplz-bin", default="lmplz", help="Path to KenLM lmplz binary")
    args = parser.parse_args(argv)

    inputs = [Path(p) for p in args.inputs]
    for path in inputs:
        if not path.exists():
            print(f"Input not found: {path}", file=sys.stderr)
            return 1

    char_corpus = Path(args.char_corpus)
    written = char_tokenize_corpus(inputs, char_corpus)
    print(f"Wrote {written:,} char-tokenised lines to {char_corpus}")
    run_lmplz(char_corpus, Path(args.output), args.order, args.lmplz_bin)
    print(f"ARPA written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
