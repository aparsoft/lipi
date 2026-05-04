"""
Command-line interface for lipi.

Usage::

    lipi extract <pdf_path> [--font-type auto] [--page-range 1-10] [--no-post-process]
    lipi split <pdf_path> --ranges "1-10:Part1,11-20:Part2" [--output-dir output]
    lipi info <pdf_path>
    lipi regress <pdf1> [<pdf2> ...]
"""

import argparse
import json
import sys
import logging

from lipi import __version__

logger = logging.getLogger(__name__)


def _print_regression_report(report: dict) -> None:
    summary = (
        f"Analyzed {report['pdf_count']} PDF(s), {report['total_pages']} page(s), "
        f"improved {report['improved_pages']} page(s), total corrections {report['total_corrections']}, "
        f"avg quality delta {report['average_quality_delta']:+.4f}"
    )
    print(summary)
    print()

    for pdf_report in report["reports"]:
        if "error" in pdf_report:
            print(f"{pdf_report['pdf_path']}: ERROR: {pdf_report['error']}")
            print()
            continue

        print(
            f"{pdf_report['filename']}: pages={pdf_report['pages_analyzed']}, "
            f"font={pdf_report['detected_font_type']}, "
            f"lexicon={pdf_report['effective_lexicon_size']} "
            f"(+{pdf_report['contextual_lexicon_size']} contextual)"
        )
        for page_report in pdf_report["page_reports"]:
            baseline = page_report["baseline_metrics"]
            corrected = page_report["corrected_metrics"]
            correction_stats = page_report["correction_stats"]
            print(
                f"  page {page_report['page_num']}: quality {baseline['quality_index']:.4f}"
                f" -> {corrected['quality_index']:.4f}, lexicon {baseline['lexicon_hit_rate']:.4f}"
                f" -> {corrected['lexicon_hit_rate']:.4f}, artifacts {baseline['artifact_total']}"
                f" -> {corrected['artifact_total']}, corrections={correction_stats.get('corrected_tokens', 0)}"
            )
            if correction_stats.get("corrections"):
                samples = ", ".join(
                    f"{entry['from']}→{entry['to']}"
                    for entry in correction_stats["corrections"][:3]
                )
                print(f"    samples: {samples}")
        print()


def _cmd_extract(args) -> None:
    from lipi.extractor import extract_unicode_text

    page_range = None
    if args.page_range:
        parts = args.page_range.split("-")
        page_range = (int(parts[0]), int(parts[1]))

    result = extract_unicode_text(
        args.pdf_path,
        page_range=page_range,
        font_type=args.font_type,
        post_process=not args.no_post_process,
        second_stage=args.second_stage,
        lexicon_path=args.lexicon_file,
        bootstrap_lexicon=args.bootstrap_lexicon,
        overrides_path=args.overrides_file,
    )

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["full_text"])


def _cmd_split(args) -> None:
    from lipi.splitter import PDFSplitter

    page_ranges = PDFSplitter.parse_page_ranges(args.ranges)

    try:
        files = PDFSplitter.split_pdf(
            args.pdf_path,
            args.output_dir,
            page_ranges,
            prefix=args.prefix,
        )
        print(f"Created {len(files)} file(s):")
        for f in files:
            print(f"  {f}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_info(args) -> None:
    from lipi.splitter import PDFSplitter

    info = PDFSplitter.get_pdf_info(args.pdf_path)
    print(json.dumps(info, indent=2, ensure_ascii=False))


def _cmd_regress(args) -> None:
    from lipi.regression import run_regression_harness

    report = run_regression_harness(
        args.pdf_paths,
        font_type=args.font_type,
        second_stage=args.second_stage,
        lexicon_path=args.lexicon_file,
        bootstrap_lexicon=args.bootstrap_lexicon,
        overrides_path=args.overrides_file,
        page_limit=args.page_limit,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_regression_report(report)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lipi",
        description=f"Lipi v{__version__} — Legacy Hindi font to Unicode toolkit",
    )
    parser.add_argument("--version", action="version", version=f"lipi {__version__}")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # -- extract --
    p_extract = sub.add_parser("extract", help="Extract and convert text from a PDF")
    p_extract.add_argument("pdf_path", help="Path to PDF file")
    p_extract.add_argument(
        "--font-type", default="auto",
        choices=["auto", "krutidev", "chanakya", "none"],
        help="Font encoding type (default: auto)",
    )
    p_extract.add_argument("--page-range", help="Page range, e.g. '1-10'")
    p_extract.add_argument("--no-post-process", action="store_true", help="Skip post-processing")
    p_extract.add_argument(
        "--second-stage",
        default="none",
        choices=["none", "lexicon"],
        help="Optional second-stage correction layer (default: none)",
    )
    p_extract.add_argument("--lexicon-file", help="Optional file with additional Hindi lexicon words")
    p_extract.add_argument(
        "--bootstrap-lexicon",
        action="store_true",
        help="Build a supplemental lexicon from repeated clean tokens in the document",
    )
    p_extract.add_argument(
        "--overrides-file",
        help="Optional JSON file with source/page-specific text replacements",
    )
    p_extract.add_argument("--json", action="store_true", help="Output as JSON")
    p_extract.set_defaults(func=_cmd_extract)

    # -- split --
    p_split = sub.add_parser("split", help="Split a PDF by page ranges")
    p_split.add_argument("pdf_path", help="Path to PDF file")
    p_split.add_argument("--ranges", required=True, help='Page ranges, e.g. "1-10:Part1,11-20:Part2"')
    p_split.add_argument("--output-dir", default="output", help="Output directory")
    p_split.add_argument("--prefix", help="Filename prefix")
    p_split.set_defaults(func=_cmd_split)

    # -- info --
    p_info = sub.add_parser("info", help="Show PDF info and encoding diagnostics")
    p_info.add_argument("pdf_path", help="Path to PDF file")
    p_info.set_defaults(func=_cmd_info)

    # -- regress --
    p_regress = sub.add_parser(
        "regress",
        help="Benchmark one or more PDFs page-by-page with generic quality metrics",
    )
    p_regress.add_argument("pdf_paths", nargs="+", help="One or more PDF paths")
    p_regress.add_argument(
        "--font-type",
        default="auto",
        choices=["auto", "krutidev", "chanakya", "none"],
        help="Font encoding type for extraction (default: auto)",
    )
    p_regress.add_argument(
        "--second-stage",
        default="lexicon",
        choices=["none", "lexicon"],
        help="Optional correction stage to compare against baseline (default: lexicon)",
    )
    p_regress.add_argument("--lexicon-file", help="Optional file with additional Hindi lexicon words")
    p_regress.add_argument(
        "--bootstrap-lexicon",
        action="store_true",
        help="Build a supplemental lexicon from repeated clean tokens in the analyzed pages",
    )
    p_regress.add_argument(
        "--overrides-file",
        help="Optional JSON file with source/page-specific text replacements",
    )
    p_regress.add_argument("--page-limit", type=int, help="Limit analysis to the first N pages")
    p_regress.add_argument("--json", action="store_true", help="Output the report as JSON")
    p_regress.set_defaults(func=_cmd_regress)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
