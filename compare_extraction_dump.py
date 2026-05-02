#!/usr/bin/env python3
"""Dump raw pypdf extraction and lipi-aparsoft output to text files."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lipi.extractor import extract_unicode_text


def _parse_page_range(value: str) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    if "-" in value:
        start, end = value.split("-", 1)
        return int(start), int(end)
    page_num = int(value)
    return page_num, page_num


def _extract_raw_pypdf(pdf_path: Path, page_range: Optional[Tuple[int, int]]) -> dict:
    with pdf_path.open("rb") as handle:
        reader = PdfReader(handle)
        total_pages = len(reader.pages)
        start_0 = (page_range[0] - 1) if page_range else 0
        end_0 = page_range[1] if page_range else total_pages
        start_0 = max(0, min(start_0, total_pages - 1))
        end_0 = max(start_0 + 1, min(end_0, total_pages))

        pages = {}
        for page_index in range(start_0, end_0):
            pages[page_index + 1] = reader.pages[page_index].extract_text() or ""

    return {
        "total_pages": total_pages,
        "processed_pages": len(pages),
        "pages": pages,
        "full_text": "\n\n".join(pages.values()),
    }


def _write_page_dump(target_path: Path, pages: dict[int, str]) -> None:
    with target_path.open("w", encoding="utf-8") as handle:
        for page_num, text in pages.items():
            handle.write(f"===== PAGE {page_num} =====\n")
            handle.write(text)
            handle.write("\n\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump raw pypdf extraction and lipi-aparsoft output to text files",
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "--page-range",
        help="Optional page range, e.g. 1-5 or 3",
    )
    parser.add_argument(
        "--font-type",
        default="auto",
        choices=["auto", "krutidev", "chanakya", "none"],
        help="Font type passed to lipi-aparsoft (default: auto)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(BASE_DIR / "output" / "extraction_compare"),
        help="Directory where the comparison files will be written",
    )
    parser.add_argument(
        "--second-stage",
        default="none",
        choices=["none", "lexicon"],
        help="Optional second-stage lipi-aparsoft correction layer",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).resolve()
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    page_range = _parse_page_range(args.page_range) if args.page_range else None
    raw_result = _extract_raw_pypdf(pdf_path, page_range)
    lipi_result = extract_unicode_text(
        str(pdf_path),
        page_range=page_range,
        font_type=args.font_type,
        post_process=True,
        second_stage=args.second_stage,
    )
    if "error" in lipi_result:
        print(f"Extraction failed: {lipi_result['error']}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) / pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / "raw_pypdf.txt"
    lipi_path = output_dir / "lipi_aparsoft.txt"
    summary_path = output_dir / "summary.json"

    _write_page_dump(raw_path, raw_result["pages"])
    _write_page_dump(lipi_path, lipi_result["pages"])

    summary = {
        "pdf_path": str(pdf_path),
        "page_range": page_range,
        "raw_equals_lipi": raw_result["full_text"] == lipi_result["full_text"],
        "has_encoding_issues": lipi_result.get("has_encoding_issues"),
        "detected_font_type": lipi_result.get("detected_font_type"),
        "processed_pages": lipi_result.get("processed_pages"),
        "second_stage": lipi_result.get("second_stage"),
        "raw_output_file": os.path.relpath(raw_path, BASE_DIR),
        "lipi_output_file": os.path.relpath(lipi_path, BASE_DIR),
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    print(f"Raw pypdf dump: {raw_path}")
    print(f"Lipi-aparsoft dump: {lipi_path}")
    print(f"Summary: {summary_path}")
    print(f"Raw equals Lipi output: {summary['raw_equals_lipi']}")
    print(f"Detected font type: {summary['detected_font_type']}")
    print(f"Has encoding issues: {summary['has_encoding_issues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
