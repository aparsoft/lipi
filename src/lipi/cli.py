"""
Command-line interface for lipi.

Usage::

    lipi extract <pdf_path> [--font-type auto] [--page-range 1-10] [--no-post-process]
    lipi split <pdf_path> --ranges "1-10:Part1,11-20:Part2" [--output-dir output]
    lipi info <pdf_path>
"""

import argparse
import json
import sys
import logging

from lipi import __version__

logger = logging.getLogger(__name__)


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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
