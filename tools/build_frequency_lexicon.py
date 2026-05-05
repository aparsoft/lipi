#!/usr/bin/env python3
"""
Build a SymSpell frequency dictionary from a clean Hindi corpus.

The output is a UTF-8 text file with ``<word> <count>`` per line, suitable
for ``SymSpellHindiCorrector.load_dictionary``.

Recommended sources (download separately, MIT/CC-licensed):

* IndicCorp v2 — https://ai4bharat.iitm.ac.in/datasets/indiccorp
* OSCAR-2301 (hi)  — https://huggingface.co/datasets/oscar-corpus/OSCAR-2301
* Samanantar (hi side) — https://ai4bharat.iitm.ac.in/datasets/samanantar
* Wikipedia hi dump — https://dumps.wikimedia.org/hiwiki/

Usage::

    # plain text files
    python tools/build_frequency_lexicon.py corpus/*.txt -o hindi_freq.txt

    # gzipped or HuggingFace JSONL with a "text" field
    python tools/build_frequency_lexicon.py shard.jsonl.gz \\
        --jsonl-field text --min-count 5 -o hindi_freq.txt

    # ship as default with: cp hindi_freq.txt src/lipi/data/hindi_freq_small.txt
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterator

WORD_RE = re.compile(r"[\u0900-\u0963\u0970-\u097f]+")


def _open_text(path: Path) -> io.TextIOBase:
    if path.suffix == ".gz":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def iter_lines(paths: list[Path], jsonl_field: str | None) -> Iterator[str]:
    for path in paths:
        with _open_text(path) as handle:
            for line in handle:
                if jsonl_field:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = record.get(jsonl_field)
                    if isinstance(text, str):
                        yield text
                else:
                    yield line


def build_counter(
    paths: list[Path],
    jsonl_field: str | None = None,
    min_token_length: int = 2,
) -> Counter:
    counter: Counter[str] = Counter()
    for line in iter_lines(paths, jsonl_field):
        for token in WORD_RE.findall(line):
            if len(token) < min_token_length:
                continue
            counter[token] += 1
    return counter


def write_dictionary(counter: Counter, output_path: Path, min_count: int) -> int:
    written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for word, count in counter.most_common():
            if count < min_count:
                break
            handle.write(f"{word} {count}\n")
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("inputs", nargs="+", help="Plain text or .gz / .jsonl(.gz) files")
    parser.add_argument("-o", "--output", required=True, help="Output dictionary path")
    parser.add_argument(
        "--jsonl-field",
        help="Treat inputs as JSONL and extract this field (e.g. 'text' for OSCAR).",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=5,
        help="Drop tokens occurring fewer than this many times (default: 5).",
    )
    parser.add_argument(
        "--min-token-length",
        type=int,
        default=2,
        help="Skip tokens shorter than this (default: 2).",
    )
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.inputs]
    for path in paths:
        if not path.exists():
            print(f"Input not found: {path}", file=sys.stderr)
            return 1

    counter = build_counter(paths, args.jsonl_field, args.min_token_length)
    written = write_dictionary(counter, Path(args.output), args.min_count)

    total_tokens = sum(counter.values())
    unique_tokens = len(counter)
    print(
        f"Read {total_tokens:,} tokens, {unique_tokens:,} unique. "
        f"Wrote {written:,} entries (min_count={args.min_count}) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
