"""
PDF splitting and batch directory processing.

Provides ``PDFSplitter`` class for splitting PDFs by page ranges,
batch-processing directories with JSON configs, and querying PDF metadata.
"""

import os
import json
import re
import logging
import urllib.parse
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from pypdf import PdfReader, PdfWriter

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFSplitter:
    """Split PDFs by page range, batch-process directories, and query PDF info."""

    # ------------------------------------------------------------------ #
    #  Parsing helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_page_ranges(ranges_str: str) -> List[Tuple[int, int, Optional[str]]]:
        """
        Parse a page-range string into a list of (start, end, name) tuples.

        Format: ``"1-10:Lecture1,11-20:Lecture2,21-30"``
        The name after ``:`` is optional.

        Returns:
            List of ``(start_page, end_page, lecture_name)`` tuples (1-indexed).
        """
        ranges_str = urllib.parse.unquote_plus(ranges_str)
        pattern = re.compile(r"(\d+)-(\d+)(?::([^,]*)?)?")
        matches = pattern.findall(ranges_str)

        if not matches:
            raise ValueError("Invalid ranges format. Expected: '1-10:Lecture1,11-20:Lecture2'")

        result = []
        for start_str, end_str, lecture_name in matches:
            start, end = int(start_str), int(end_str)
            if start <= 0:
                raise ValueError(f"Start page must be positive: {start}")
            if end < start:
                raise ValueError(f"End page must be >= start page: {start}-{end}")
            result.append((start, end, lecture_name.strip() or None))
        return result

    # ------------------------------------------------------------------ #
    #  PDF info                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_pdf_info(pdf_path: str) -> Dict[str, Any]:
        """Return metadata and encoding diagnostics for *pdf_path*."""
        from lipi.preprocessor import HindiPreprocessor

        try:
            with open(pdf_path, "rb") as fh:
                reader = PdfReader(fh)
                info: Dict[str, Any] = {
                    "filename": os.path.basename(pdf_path),
                    "path": pdf_path,
                    "total_pages": len(reader.pages),
                    "size_kb": round(os.path.getsize(pdf_path) / 1024, 2),
                    "metadata": {},
                }

                if reader.metadata:
                    for key, value in reader.metadata.items():
                        info["metadata"][key.lstrip("/")] = str(value)

                sample = ""
                for pg_idx in range(min(2, len(reader.pages))):
                    try:
                        t = reader.pages[pg_idx].extract_text() or ""
                        sample += t
                        if len(sample) >= 500:
                            break
                    except Exception:
                        pass

                has_issues, detected_font = HindiPreprocessor.detect_encoding(sample)
                info["has_encoding_issues"] = has_issues
                info["detected_font_type"] = detected_font if has_issues else None
                return info

        except Exception as exc:
            logger.error("Error getting PDF info for %s: %s", pdf_path, exc)
            return {
                "filename": os.path.basename(pdf_path),
                "path": pdf_path,
                "error": str(exc),
            }

    # ------------------------------------------------------------------ #
    #  Config validation / loading                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_config(config: Dict) -> bool:
        """Validate a JSON batch-processing config dict."""
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary")

        for key, value in config.items():
            if not isinstance(value, dict):
                raise ValueError(f"Config entry '{key}' must be a dict")
            if "page_ranges" not in value:
                raise ValueError(f"Missing 'page_ranges' in config entry '{key}'")
            if not isinstance(value["page_ranges"], list):
                raise ValueError(f"'page_ranges' for '{key}' must be a list")

            for i, pr in enumerate(value["page_ranges"]):
                if not isinstance(pr, dict):
                    raise ValueError(f"page_ranges[{i}] in '{key}' must be a dict")
                if "start" not in pr or "end" not in pr:
                    raise ValueError(f"page_ranges[{i}] in '{key}' needs 'start' and 'end'")
                if not isinstance(pr["start"], int) or not isinstance(pr["end"], int):
                    raise ValueError(f"'start'/'end' in page_ranges[{i}] of '{key}' must be int")
                if pr["start"] <= 0:
                    raise ValueError(f"'start' in page_ranges[{i}] of '{key}' must be > 0")
                if pr["end"] < pr["start"]:
                    raise ValueError(f"'end' must be >= 'start' in page_ranges[{i}] of '{key}'")
        return True

    @staticmethod
    def load_config(config_file: str) -> Dict:
        """Load and validate a JSON config file."""
        try:
            with open(config_file, "r", encoding="utf-8") as fh:
                config = json.load(fh)
            PDFSplitter.validate_config(config)
            return config
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", config_file, exc)
            raise
        except Exception as exc:
            logger.error("Error loading config %s: %s", config_file, exc)
            raise

    # ------------------------------------------------------------------ #
    #  PDF splitting                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def split_pdf(
        input_file: str,
        output_dir: str,
        page_ranges: List[Tuple[int, int, Optional[str]]],
        prefix: Optional[str] = None,
        unit_name: Optional[str] = None,
    ) -> List[str]:
        """
        Split *input_file* into separate PDFs according to *page_ranges*.

        Copies PDF pages byte-for-byte — does NOT re-encode fonts.

        Args:
            input_file:  Path to the source PDF.
            output_dir:  Directory where split files are written.
            page_ranges: List of ``(start, end, name)`` tuples (1-indexed).
            prefix:      Optional filename prefix.
            unit_name:   Optional unit name for filenames.

        Returns:
            List of created file paths.
        """
        os.makedirs(output_dir, exist_ok=True)
        created_files: List[str] = []

        with open(input_file, "rb") as fh:
            reader = PdfReader(fh)
            total_pages = len(reader.pages)
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            effective_unit = unit_name or base_name

            logger.info(
                "Splitting %s (%d pages) into %d parts",
                input_file, total_pages, len(page_ranges),
            )

            for i, (start, end, lecture_name) in enumerate(page_ranges, 1):
                if start < 1 or end > total_pages or start > end:
                    logger.warning(
                        "Skipping invalid range %d-%d (total=%d)",
                        start, end, total_pages,
                    )
                    continue

                writer = PdfWriter()
                page_iter = range(start - 1, end)
                if TQDM_AVAILABLE:
                    page_iter = tqdm(page_iter, desc=f"Pages {start}\u2013{end}", unit="page")
                for pg_idx in page_iter:
                    writer.add_page(reader.pages[pg_idx])

                if reader.metadata:
                    writer.add_metadata(dict(reader.metadata))

                label = lecture_name or f"Lecture{i}"
                parts = [p for p in [prefix, effective_unit, label] if p]
                out_name = "_".join(parts) + ".pdf"
                out_path = os.path.join(output_dir, out_name)

                with open(out_path, "wb") as out_fh:
                    writer.write(out_fh)

                created_files.append(out_path)
                logger.info("Created %s (pages %d\u2013%d)", out_path, start, end)

        return created_files

    # ------------------------------------------------------------------ #
    #  Batch directory processing                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def process_directory(
        input_dir: str,
        output_dir: str,
        config: Dict,
    ) -> Dict[str, Any]:
        """Batch-split all PDFs in *input_dir* using *config*."""
        results: Dict[str, Any] = {
            "processed": [],
            "skipped": [],
            "processed_count": 0,
            "skipped_count": 0,
            "output_files": [],
        }

        os.makedirs(output_dir, exist_ok=True)

        for filename in os.listdir(input_dir):
            if not filename.lower().endswith(".pdf"):
                continue

            input_path = os.path.join(input_dir, filename)
            key = os.path.splitext(filename)[0]

            # Resolve config entry: exact name -> regex pattern -> default
            file_config = None
            if key in config:
                file_config = config[key]
            else:
                for pattern, cfg in config.items():
                    if pattern.startswith("^") and pattern.endswith("$") and re.match(pattern, key):
                        file_config = cfg
                        break
                if file_config is None and "default" in config:
                    file_config = config["default"]

            if file_config is None:
                logger.warning("No config for %s -- skipping", filename)
                results["skipped"].append(filename)
                results["skipped_count"] += 1
                continue

            page_ranges = [
                (r["start"], r["end"], r.get("name")) for r in file_config["page_ranges"]
            ]
            unit_name = file_config.get("unit_name")
            prefix = file_config.get("prefix")

            try:
                out_files = PDFSplitter.split_pdf(
                    input_path, output_dir, page_ranges, prefix, unit_name
                )
                results["processed"].append(filename)
                results["processed_count"] += 1
                results["output_files"].extend(out_files)
            except Exception as exc:
                logger.error("Failed to process %s: %s", filename, exc)
                results["skipped"].append(filename)
                results["skipped_count"] += 1

        logger.info(
            "Done -- processed %d, skipped %d",
            results["processed_count"],
            results["skipped_count"],
        )
        return results
