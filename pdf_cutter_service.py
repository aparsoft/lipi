#!/usr/bin/env python3
"""
PDF Cutter Service

This service splits PDF files into separate PDF files based on specified page ranges.
It can be run as a standalone service or imported for use in other applications.

Dependencies:
    - pypdf: pip install pypdf
    - watchdog: pip install watchdog
    - tqdm: pip install tqdm
    - fontTools: pip install fonttools
    - indic-transliteration: pip install indic-transliteration

Usage as a service:
    # Run as a service watching a directory
    python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json

    # Run as a service with a specific port for API access
    python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --port 5000

Usage as a library:
    from pdf_cutter_service import PDFCutterService

    service = PDFCutterService()
    service.split_pdf(input_file, output_dir, page_ranges)
"""

import os
import argparse
import json
import logging
import re
import time
import threading
import queue
import http.server
import socketserver
import urllib.parse
import socket
import traceback
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from datetime import datetime
from pypdf import PdfReader, PdfWriter
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Try to import indic_transliteration for better Hindi text processing
try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import SchemeMap, SCHEMES, transliterate

    INDIC_TRANSLITERATION_AVAILABLE = True
except ImportError:
    INDIC_TRANSLITERATION_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("pdf_cutter_service.log"), logging.StreamHandler()],
)
logger = logging.getLogger("PDF Cutter Service")

# Global task queue for processing PDFs
task_queue = queue.Queue()

# Global service status
service_status = {
    "running": True,
    "processed_files": 0,
    "failed_files": 0,
    "current_task": None,
    "last_processed": None,
    "start_time": datetime.now().isoformat(),
}


class PDFCutterService:
    """PDF Cutter Service class for splitting PDFs by page ranges"""

    def __init__(self):
        """Initialize the service"""
        self.current_task = None

    @staticmethod
    def parse_page_ranges(ranges_str: str) -> List[Tuple[int, int, Optional[str]]]:
        """
        Parse page ranges string into a list of tuples (start_page, end_page, name)

        Args:
            ranges_str: String containing page ranges in format "1-10:Lecture1,11-20:Lecture2"
                    The lecture name after colon is optional

        Returns:
            List of tuples containing (start_page, end_page, lecture_name)

        Example:
            >>> parse_page_ranges("1-10:Intro,11-20:Basics,21-30")
            [(1, 10, 'Intro'), (11, 20, 'Basics'), (21, 30, None)]
        """
        ranges = []

        # First, we'll URL decode the ranges string to handle spaces and special characters
        ranges_str = urllib.parse.unquote_plus(ranges_str)

        # Split by commas, (There may be lecture names that contain commas)
        pattern = re.compile(r"(\d+)-(\d+)(?::([^,]*)?)?")
        matches = pattern.findall(ranges_str)

        if not matches:
            raise ValueError(
                "Invalid ranges format. Expected format: '1-10:Lecture1,11-20:Lecture2'"
            )

        for match in matches:
            start_str, end_str, lecture_name = match

            try:
                start = int(start_str)
                end = int(end_str)

                if start <= 0:
                    raise ValueError(f"Start page must be positive: {start}")
                if end < start:
                    raise ValueError(
                        f"End page must be greater than or equal to start page: {start}-{end}"
                    )

                # Lecture name might be empty
                if not lecture_name.strip():
                    lecture_name = None

                ranges.append((start, end, lecture_name))
            except Exception as e:
                raise ValueError(
                    f"Error parsing page range '{start_str}-{end_str}': {str(e)}"
                )

        return ranges

    @staticmethod
    def detect_potential_hindi_encoding_issue(text: str) -> bool:
        """
        Detect if the text likely contains incorrectly encoded Hindi text

        Args:
            text: The text to check

        Returns:
            True if incorrectly encoded Hindi is detected, False otherwise
        """
        # Patterns that commonly appear in incorrectly encoded Hindi (Kruti Dev, Chanakya, etc.)
        hindi_markers = [
            "kk",
            "kh",
            "kz",
            "k`",
            "gh",
            "ph",
            "Fk",
            "Hk",
            "ek",
            "ea",
            "ykZ",
            "kjk",
            "osQ",
            "ksa",
            "kksa",
            "ksaa",
            "kksa",
            "rk",
            "eksa",
            "r%",
            "kj",
            "esa",
            "kr",
            "dj",
            "kr",
            "dj",
            "kr",
            "dj",
            "kkr",
            "dkj",
            "kkj",
        ]

        # Patterns common in Kruti Dev font encoding
        kruti_dev_patterns = [
            "M+",
            "iQ",
            "<+",
            "z",
            "vks",
            "vkS",
            "vk",
            "bZ",
            "b",
            "mQ",
            "m",
            ",s",
            ",",
            "ks",
            "kS",
            "k",
            "h",
            "q",
            "w",
            "`",
            "s",
            "S",
            "a",
            "a",
            "gzZ",
            "ha",
            "hz",
            "£",
            "L+",
            "nzZ",
            "ï",
        ]

        # Check for the typical Kruti Dev / non-Unicode patterns
        pattern_count = sum(text.count(marker) for marker in hindi_markers)
        kruti_dev_count = sum(text.count(pattern) for pattern in kruti_dev_patterns)

        # Additional heuristics: proper Hindi Unicode has a lot of Devanagari characters
        devanagari_range = sum(1 for char in text if "\u0900" <= char <= "\u097f")

        # Kruti Dev encoded text will have very few actual Devanagari Unicode characters
        # but many Latin characters that form patterns like 'kjk', 'osQ', etc.

        # If we have a significant number of these patterns and few actual Devanagari characters,
        # it's likely incorrectly encoded Hindi
        return (
            pattern_count > 5
            or kruti_dev_count > 3
            or ("kjk" in text and "osQ" in text)
        ) and devanagari_range < len(text) / 10

    @staticmethod
    def get_hindi_font_mapping(font_type="krutidev"):
        """
        Get mapping dictionary for incorrectly encoded Hindi characters based on font type

        Args:
            font_type: The type of font encoding ('krutidev', 'chanakya', etc.)

        Returns:
            Dictionary mapping incorrect sequences to correct Unicode characters
        """
        mappings = {
            "krutidev": {
                # Vowels
                "v": "अ",
                "vk": "आ",
                "fv": "अि",
                "ik": "इ",
                "bZ": "ई",
                "m": "उ",
                "Å": "ऊ",
                "½": "ऋ",
                ",": "ए",
                ",s": "ऐ",
                "vks": "ओ",
                "vkS": "औ",
                "va": "अं",
                "v%": "अः",
                "vkW": "ऑ",
                # Consonants
                "d": "क",
                "[k": "ख",
                "x": "ग",
                "?k": "घ",
                "³": "ङ",
                "p": "च",
                "N": "छ",
                "t": "ज",
                ">": "झ",
                "¥": "ञ",
                "V": "ट",
                "B": "ठ",
                "M": "ड",
                "<": "ढ",
                ".k": "ण",
                "r": "त",
                "Fk": "थ",
                "n": "द",
                "/k": "ध",
                "u": "न",
                "i": "प",
                "Q": "फ",
                "c": "ब",
                "Hk": "भ",
                "e": "म",
                ";": "य",
                "j": "र",
                "y": "ल",
                "o": "व",
                "'k": "श",
                '"k': "ष",
                "l": "स",
                "g": "ह",
                "â": "त्र",
                "K": "ज्ञ",
                "J": "श्र",
                "D;": "क्य",
                "{k": "क्ष",
                # Matras
                "k": "ा",
                "f": "ि",
                "h": "ी",
                "q": "ु",
                "w": "ू",
                "`": "्",
                "s": "े",
                "S": "ै",
                "ks": "ो",
                "kS": "ौ",
                "W": "ॉ",
                "a": "ं",
                "%": "ः",
                "¡": "ँ",
                # Halant
                "~": "्",
                # Half characters/conjuncts
                "D": "क्",
                "[": "ख्",
                "X": "ग्",
                "?": "घ्",
                "P": "च्",
                "T": "ज्",
                "¶": "ट्",
                "B": "ठ्",
                "ï": "ड्",
                "<": "ढ्",
                "=": "त्",
                "F": "थ्",
                "/": "द्",
                "/": "ध्",
                "U": "न्",
                "I": "प्",
                "¶": "फ्",
                "C": "ब्",
                "H": "भ्",
                "E": "म्",
                "¸": "य्",
                "j": "र्",
                "Y": "ल्",
                "O": "व्",
                "'": "श्",
                '"': "ष्",
                "L": "स्",
                "»": "ह्",
                # Common patterns from sample text
                "osQ": "के",
                "kjk": "ारा",
                "bar": "इंत",
                "kj": "ार",
                "è": "ध",
                "---": "...",
                "`": "्",
                "kka": "ां",
                "dh": "की",
                "dk": "का",
                "esa": "में",
                "sa": "ें",
                # Numerals
                "0": "०",
                "1": "१",
                "2": "२",
                "3": "३",
                "4": "४",
                "5": "५",
                "6": "६",
                "7": "७",
                "8": "८",
                "9": "९",
                # Special replacements for common patterns
                "vkbZ": "आई",
                "kbZ": "ाई",
                "kb": "ाइ",
                "kb±": "ाईं",
                "kba": "ांइ",
                "Å¡": "ऊँ",
                "vkfn": "आदि",
                "Øe": "क्रम",
                "Z": "़",
            },
            "chanakya": {
                # Similar mapping for Chanakya font
                # Basic vowels
                "A": "अ",
                "Aa": "आ",
                "i": "इ",
                "I": "ई",
                "u": "उ",
                "U": "ऊ",
                "e": "ए",
                "E": "ऐ",
                "ao": "ओ",
                "AO": "औ",
                # Consonants
                "k": "क",
                "K": "ख",
                "g": "ग",
                "G": "घ",
                "|": "ङ",
                "c": "च",
                "C": "छ",
                "j": "ज",
                "J": "झ",
                "¬": "ञ",
                "t": "ट",
                "T": "ठ",
                "D": "ड",
                "Z": "ढ",
                "N": "ण",
                "w": "त",
                "W": "थ",
                "d": "द",
                "D": "ध",
                "n": "न",
                "p": "प",
                "P": "फ",
                "b": "ब",
                "B": "भ",
                "m": "म",
                "y": "य",
                "r": "र",
                "l": "ल",
                "v": "व",
                "S": "श",
                "R": "ष",
                "s": "स",
                "h": "ह",
                # Matras
                "a": "ा",
                "f": "ि",
                "I": "ी",
                "u": "ु",
                "U": "ू",
                "¤": "्",
                "o": "े",
                "O": "ै",
                "ao": "ो",
                "AO": "ौ",
                # Special characters
                "±": "ड़",
                "²": "ढ़",
            },
        }

        return mappings.get(font_type.lower(), mappings["krutidev"])

    @staticmethod
    def correct_hindi_text(text: str, font_type="auto") -> str:
        """
        Attempt to correct incorrectly encoded Hindi text

        Args:
            text: The incorrectly encoded text
            font_type: The type of font encoding ('auto', 'krutidev', 'chanakya', etc.)

        Returns:
            Corrected text as best as possible
        """
        if not text or not PDFCutterService.detect_potential_hindi_encoding_issue(text):
            return text

        # If we have indic_transliteration library available, use it for better results
        if INDIC_TRANSLITERATION_AVAILABLE:
            # Use indic_transliteration for better conversion if available
            try:
                # First try converting from HK to Devanagari
                if any(c in text for c in ["kk", "kh", "gh", "cha", "jh"]):
                    corrected = transliterate(text, sanscript.HK, sanscript.DEVANAGARI)
                    if (
                        sum(1 for c in corrected if "\u0900" <= c <= "\u097f")
                        > len(corrected) / 10
                    ):
                        return corrected
            except Exception as e:
                logger.warning(f"Error in transliteration: {str(e)}")

        # If auto-detection, try to determine the font type
        if font_type == "auto":
            # Some heuristics to determine font type
            if "kjk" in text and "osQ" in text:
                font_type = "krutidev"
            elif "Aa" in text and "ao" in text:
                font_type = "chanakya"
            else:
                font_type = "krutidev"  # Default to Krutidev

        # Get the appropriate mapping based on the font type
        mapping = PDFCutterService.get_hindi_font_mapping(font_type)

        # Sort keys by length in descending order to handle longer sequences first
        keys = sorted(mapping.keys(), key=len, reverse=True)

        # Replace each incorrectly encoded sequence with its correct Unicode equivalent
        corrected_text = text
        for key in keys:
            corrected_text = corrected_text.replace(key, mapping[key])

        return corrected_text

    @staticmethod
    def post_process_hindi_text(text: str) -> str:
        """
        Post-process Hindi text for further corrections after initial conversion

        Args:
            text: The text to post-process

        Returns:
            Post-processed text
        """
        if not text:
            return text

        # Fix common issues after conversion
        corrections = [
            # Fix double vowels
            (r"[ा][ा]", "ा"),
            (r"[ि][ि]", "ि"),
            (r"[ी][ी]", "ी"),
            (r"[ु][ु]", "ु"),
            (r"[ू][ू]", "ू"),
            (r"[े][े]", "े"),
            (r"[ै][ै]", "ै"),
            (r"[ो][ो]", "ो"),
            (r"[ौ][ौ]", "ौ"),
            # Fix vowels with halant
            (r"[्][ा]", "्"),
            (r"[्][ि]", "्"),
            (r"[्][ी]", "्"),
            (r"[्][ु]", "्"),
            (r"[्][ू]", "्"),
            (r"[्][े]", "्"),
            (r"[्][ै]", "्"),
            (r"[्][ो]", "्"),
            (r"[्][ौ]", "्"),
            # Remove extra spaces between Hindi words
            (r"([^\s\d\W])[ ]+([^\s\d\W])", r"\1\2"),
            # Fix common word patterns
            ("अौर", "और"),
            ("अार", "आर"),
            ("एक़", "एक"),
            # Add more corrections as needed
        ]

        # Apply corrections
        for pattern, replacement in corrections:
            text = re.sub(pattern, replacement, text)

        return text

    @staticmethod
    def fix_encoding(pdf_reader: PdfReader, pdf_writer: PdfWriter) -> PdfWriter:
        """
        Fix encoding issues in the PDF, particularly for Hindi text

        Args:
            pdf_reader: The original PDF reader object
            pdf_writer: The PDF writer object with pages already added

        Returns:
            The same PDF writer object with fixed encoding
        """
        # Check if we need to fix encoding by examining text content
        needs_encoding_fix = False
        sample_text = ""
        detected_font_type = "krutidev"  # Default font type

        try:
            # Extract sample text from a few pages to check for Hindi encoding issues
            for page_num in range(min(3, len(pdf_reader.pages))):
                try:
                    page_text = pdf_reader.pages[page_num].extract_text()
                    if page_text:
                        sample_text += page_text
                        if len(sample_text) > 1000:  # Limit sample size
                            break
                except Exception as e:
                    logger.warning(
                        f"Error extracting text from page {page_num+1}: {str(e)}"
                    )
                    continue

            # Check if text contains incorrectly encoded Hindi
            if sample_text and PDFCutterService.detect_potential_hindi_encoding_issue(
                sample_text
            ):
                needs_encoding_fix = True

                # Try to detect font type based on text patterns
                if "kjk" in sample_text and "osQ" in sample_text:
                    detected_font_type = "krutidev"
                elif "Aa" in sample_text and "ao" in sample_text:
                    detected_font_type = "chanakya"

                logger.info(
                    f"Detected incorrectly encoded Hindi text (likely {detected_font_type}), will attempt correction"
                )
        except Exception as e:
            logger.warning(f"Error analyzing PDF content: {str(e)}")

        if not needs_encoding_fix:
            return pdf_writer

        # Try to fix font encoding in the PDF structure
        try:
            # Preserve metadata from the original PDF
            if pdf_reader.metadata:
                pdf_writer.add_metadata(pdf_reader.metadata)

            # Set the PDF encoding to Unicode for better Indic script support
            for i in range(len(pdf_writer.pages)):
                page = pdf_writer.pages[i]
                if "/Resources" in page and "/Font" in page["/Resources"]:
                    for font_name, font in page["/Resources"]["/Font"].items():
                        if isinstance(font, dict):
                            # Ensure Unicode encoding
                            if "/Encoding" in font:
                                font["/Encoding"] = "/Identity-H"

                            # Look for and fix known problematic fonts
                            if "/BaseFont" in font:
                                base_font = str(font["/BaseFont"])
                                # Check for common fonts used for Hindi that might have encoding issues
                                if any(
                                    f in base_font
                                    for f in [
                                        "/Kruti",
                                        "/Mangal",
                                        "/Walkman",
                                        "/DevLys",
                                        "/Shusha",
                                    ]
                                ):
                                    logger.info(
                                        f"Found problematic Hindi font: {base_font}"
                                    )

            # Add metadata to help with Hindi text rendering
            pdf_writer.add_metadata(
                {
                    "/Lang": "hi-IN",
                }
            )

            logger.info("Applied font encoding fixes to PDF structure")

        except Exception as e:
            logger.warning(f"Error fixing font encoding in PDF structure: {str(e)}")

        # For PDFs with incorrectly encoded text content, we need to use an additional approach
        # Create text extraction data with corrected Hindi to be used by text extraction tools
        try:
            # Extract and correct text from each page
            for i in range(len(pdf_writer.pages)):
                try:
                    # Get the text content
                    page = pdf_reader.pages[i]
                    text = page.extract_text()

                    # If text has encoding issues, correct it
                    if text and PDFCutterService.detect_potential_hindi_encoding_issue(
                        text
                    ):
                        corrected_text = PDFCutterService.correct_hindi_text(
                            text, detected_font_type
                        )
                        # Apply post-processing to fix common conversion issues
                        corrected_text = PDFCutterService.post_process_hindi_text(
                            corrected_text
                        )

                        logger.info(f"Corrected Hindi text on page {i+1}")

                        # Store the corrected text in the page's annotations or metadata
                        # This helps text extraction tools get the corrected version
                        if "/Annots" not in pdf_writer.pages[i]:
                            pdf_writer.pages[i]["/Annots"] = []

                        # Add invisible text annotation with corrected content
                        # This is a technique to help text extraction tools
                        if hasattr(pdf_writer.pages[i], "add_annotation"):
                            try:
                                # This is specific to certain PDF libraries that support annotations
                                annotation = {
                                    "/Subtype": "/Text",
                                    "/Contents": corrected_text,
                                    "/Rect": [0, 0, 0, 0],  # Invisible
                                    "/F": 0,  # Not visible
                                    "/NM": f"CorrectedText{i}",
                                }
                                pdf_writer.pages[i].add_annotation(annotation)
                            except Exception as ann_err:
                                logger.warning(
                                    f"Error adding annotation: {str(ann_err)}"
                                )
                except Exception as e:
                    logger.warning(
                        f"Error processing text correction for page {i+1}: {str(e)}"
                    )
                    continue

            logger.info("Applied text corrections to PDF content")

        except Exception as e:
            logger.warning(f"Error in text correction process: {str(e)}")

        return pdf_writer

    @staticmethod
    def validate_config(config: Dict) -> bool:
        """
        Validate the configuration file structure

        Args:
            config: Configuration dictionary loaded from JSON

        Returns:
            True if valid, raises exception otherwise
        """
        # Check that it's a dictionary
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary")

        # Check each file entry
        for key, value in config.items():
            if not isinstance(value, dict):
                raise ValueError(f"Configuration for '{key}' must be a dictionary")

            # Check for page_ranges
            if "page_ranges" not in value:
                raise ValueError(f"Missing 'page_ranges' in configuration for '{key}'")

            # Check page_ranges format
            page_ranges = value["page_ranges"]
            if not isinstance(page_ranges, list):
                raise ValueError(f"'page_ranges' for '{key}' must be a list")

            # Check each page range
            for i, page_range in enumerate(page_ranges):
                if not isinstance(page_range, dict):
                    raise ValueError(
                        f"Page range #{i+1} for '{key}' must be a dictionary"
                    )

                if "start" not in page_range or "end" not in page_range:
                    raise ValueError(
                        f"Page range #{i+1} for '{key}' must have 'start' and 'end' keys"
                    )

                start = page_range["start"]
                end = page_range["end"]

                if not isinstance(start, int) or not isinstance(end, int):
                    raise ValueError(
                        f"'start' and 'end' for page range #{i+1} in '{key}' must be integers"
                    )

                if start <= 0:
                    raise ValueError(
                        f"'start' for page range #{i+1} in '{key}' must be positive"
                    )

                if end < start:
                    raise ValueError(
                        f"'end' for page range #{i+1} in '{key}' must be greater than or equal to 'start'"
                    )

        return True

    def get_pdf_info(self, pdf_path: str) -> Dict[str, Any]:
        """
        Get information about a PDF file

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary with PDF information
        """
        try:
            with open(pdf_path, "rb") as file:
                pdf_reader = PdfReader(file)
                info = {
                    "filename": os.path.basename(pdf_path),
                    "path": pdf_path,
                    "total_pages": len(pdf_reader.pages),
                    "size_kb": round(os.path.getsize(pdf_path) / 1024, 2),
                    "metadata": {},
                }

                # Extract metadata if available
                if pdf_reader.metadata:
                    for key, value in pdf_reader.metadata.items():
                        if key.startswith("/"):
                            key = key[1:]  # Remove leading slash
                        info["metadata"][key] = str(value)

                # Check for Hindi text encoding issues
                sample_text = ""
                for page_num in range(min(2, len(pdf_reader.pages))):
                    try:
                        text = pdf_reader.pages[page_num].extract_text()
                        if text:
                            sample_text += text
                            if len(sample_text) > 500:  # Limit sample size
                                break
                    except:
                        continue

                # Add encoding info to metadata
                if sample_text and self.detect_potential_hindi_encoding_issue(
                    sample_text
                ):
                    info["has_encoding_issues"] = True

                    # Try to detect font type based on text patterns
                    if "kjk" in sample_text and "osQ" in sample_text:
                        info["detected_font_type"] = "krutidev"
                    elif "Aa" in sample_text and "ao" in sample_text:
                        info["detected_font_type"] = "chanakya"
                    else:
                        info["detected_font_type"] = "unknown"
                else:
                    info["has_encoding_issues"] = False

                return info
        except Exception as e:
            logger.error(f"Error getting PDF info for {pdf_path}: {str(e)}")
            return {
                "filename": os.path.basename(pdf_path),
                "path": pdf_path,
                "error": str(e),
            }

    def split_pdf(
        self,
        input_file: str,
        output_dir: str,
        page_ranges: List[Tuple[int, int, Optional[str]]],
        prefix: Optional[str] = None,
        unit_name: Optional[str] = None,
        fix_encoding: bool = True,
    ) -> List[str]:
        """
        Split a PDF file into multiple PDF files based on page ranges

        Args:
            input_file: Path to the input PDF file
            output_dir: Directory to save the output PDF files
            page_ranges: List of tuples containing (start_page, end_page, lecture_name)
            prefix: Optional prefix for output file names
            unit_name: Optional unit name to include in output file names
            fix_encoding: Whether to fix encoding issues for non-Latin scripts (like Hindi)

        Returns:
            List of paths to created PDF files
        """
        # Update current task for status reporting
        global service_status
        service_status["current_task"] = f"Splitting {os.path.basename(input_file)}"
        self.current_task = service_status["current_task"]

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        created_files = []

        try:
            with open(input_file, "rb") as file:
                pdf_reader = PdfReader(file)
                total_pages = len(pdf_reader.pages)

                logger.info(f"Processing {input_file} with {total_pages} pages")

                # Get the base filename without extension
                base_filename = os.path.basename(input_file)
                base_name = os.path.splitext(base_filename)[0]

                # If unit_name is not provided, use the base filename
                if not unit_name:
                    unit_name = base_name

                # Check for encoding issues if fix_encoding is enabled
                encoding_issues = False
                font_type = "krutidev"  # Default font type

                if fix_encoding:
                    sample_text = ""
                    for page_num in range(min(3, total_pages)):
                        try:
                            text = pdf_reader.pages[page_num].extract_text()
                            if text:
                                sample_text += text
                                if len(sample_text) > 1000:  # Limit sample size
                                    break
                        except:
                            continue

                    encoding_issues = (
                        sample_text
                        and self.detect_potential_hindi_encoding_issue(sample_text)
                    )

                    # Try to detect font type based on text patterns
                    if encoding_issues:
                        if "kjk" in sample_text and "osQ" in sample_text:
                            font_type = "krutidev"
                        elif "Aa" in sample_text and "ao" in sample_text:
                            font_type = "chanakya"

                        logger.info(
                            f"Detected Hindi encoding issues with font type: {font_type}"
                        )

                for i, (start, end, lecture_name) in enumerate(page_ranges, 1):
                    # Validate page ranges
                    if start < 1 or end > total_pages or start > end:
                        logger.warning(
                            f"Invalid page range {start}-{end} for {input_file} (total pages: {total_pages}), skipping..."
                        )
                        continue

                    # Adjust for 0-based indexing
                    start_idx = start - 1
                    end_idx = end

                    # Create a new PDF writer
                    pdf_writer = PdfWriter()

                    # Add pages from the specified range
                    page_iterator = range(start_idx, end_idx)
                    if TQDM_AVAILABLE:
                        page_iterator = tqdm(
                            page_iterator,
                            desc=f"Processing pages {start}-{end}",
                            unit="page",
                        )

                    for page_num in page_iterator:
                        pdf_writer.add_page(pdf_reader.pages[page_num])

                    # Fix encoding issues, particularly for Hindi text, if enabled and needed
                    if fix_encoding and encoding_issues:
                        pdf_writer = self.fix_encoding(pdf_reader, pdf_writer)

                    # Generate output filename
                    if lecture_name:
                        lecture_id = lecture_name
                    else:
                        lecture_id = f"Lecture{i}"

                    filename_parts = []
                    if prefix:
                        filename_parts.append(prefix)
                    if unit_name:
                        filename_parts.append(unit_name)
                    filename_parts.append(lecture_id)

                    output_filename = "_".join(filename_parts) + ".pdf"
                    output_path = os.path.join(output_dir, output_filename)

                    # Write the new PDF file
                    with open(output_path, "wb") as output_file:
                        pdf_writer.write(output_file)

                    created_files.append(output_path)
                    logger.info(f"Created {output_path} with pages {start}-{end}")

                service_status["processed_files"] += 1
                service_status["last_processed"] = {
                    "file": base_filename,
                    "time": datetime.now().isoformat(),
                    "output_files": len(created_files),
                }

                return created_files

        except FileNotFoundError:
            logger.error(f"File not found: {input_file}")
            service_status["failed_files"] += 1
            raise
        except PermissionError:
            logger.error(f"Permission denied when accessing {input_file}")
            service_status["failed_files"] += 1
            raise
        except Exception as e:
            logger.error(f"Error processing {input_file}: {str(e)}")
            service_status["failed_files"] += 1
            raise

    @staticmethod
    def load_config(config_file: str) -> Dict:
        """
        Load configuration from a JSON file

        Args:
            config_file: Path to the configuration JSON file

        Returns:
            Dictionary containing configuration
        """
        try:
            with open(config_file, "r") as f:
                config = json.load(f)

            # Validate the configuration
            PDFCutterService.validate_config(config)

            return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file {config_file}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {str(e)}")
            raise

    def process_directory(
        self, input_dir: str, output_dir: str, config: Dict
    ) -> Dict[str, Any]:
        """
        Process all PDF files in a directory using configuration

        Args:
            input_dir: Directory containing input PDF files
            output_dir: Directory to save output PDF files
            config: Configuration dictionary

        Returns:
            Dictionary with processing results
        """
        # Count processed and skipped files
        results = {
            "processed": [],
            "skipped": [],
            "processed_count": 0,
            "skipped_count": 0,
            "output_files": [],
        }

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        for filename in os.listdir(input_dir):
            if not filename.lower().endswith(".pdf"):
                continue

            input_path = os.path.join(input_dir, filename)
            filename_without_ext = os.path.splitext(filename)[0]

            # Update current task
            global service_status
            service_status["current_task"] = f"Processing {filename}"
            self.current_task = service_status["current_task"]

            # Check if there's a specific configuration for this file
            if filename_without_ext in config:
                file_config = config[filename_without_ext]
                page_ranges = [
                    (r["start"], r["end"], r.get("name"))
                    for r in file_config["page_ranges"]
                ]
                unit_name = file_config.get("unit_name")
                prefix = file_config.get("prefix")
                fix_encoding = file_config.get("fix_encoding", True)

                logger.info(f"Using specific configuration for {filename}")

            # Check if there's a configuration for the file pattern
            elif any(
                re.match(pattern, filename_without_ext)
                for pattern in config
                if pattern.startswith("^") and pattern.endswith("$")
            ):
                # Find the matching pattern
                matching_pattern = next(
                    pattern
                    for pattern in config
                    if pattern.startswith("^")
                    and pattern.endswith("$")
                    and re.match(pattern, filename_without_ext)
                )

                file_config = config[matching_pattern]
                page_ranges = [
                    (r["start"], r["end"], r.get("name"))
                    for r in file_config["page_ranges"]
                ]
                unit_name = file_config.get("unit_name")
                prefix = file_config.get("prefix")
                fix_encoding = file_config.get("fix_encoding", True)

                logger.info(
                    f"Using pattern configuration ({matching_pattern}) for {filename}"
                )

            # Use default configuration if available
            elif "default" in config:
                file_config = config["default"]
                page_ranges = [
                    (r["start"], r["end"], r.get("name"))
                    for r in file_config["page_ranges"]
                ]
                unit_name = file_config.get("unit_name")
                prefix = file_config.get("prefix")
                fix_encoding = file_config.get("fix_encoding", True)

                logger.info(f"Using default configuration for {filename}")

            else:
                logger.warning(f"No configuration found for {filename}, skipping...")
                results["skipped"].append(filename)
                results["skipped_count"] += 1
                continue

            # Process the file
            try:
                output_files = self.split_pdf(
                    input_path, output_dir, page_ranges, prefix, unit_name, fix_encoding
                )
                results["processed"].append(filename)
                results["processed_count"] += 1
                results["output_files"].extend(output_files)
            except Exception as e:
                logger.error(f"Failed to process {filename}: {str(e)}")
                results["skipped"].append(filename)
                results["skipped_count"] += 1

        logger.info(
            f"Processed {results['processed_count']} files, skipped {results['skipped_count']} files"
        )

        return results


# File System Watcher for service mode
class PDFHandler(FileSystemEventHandler):
    """Handler for watching PDF files being added to a directory"""

    def __init__(self, output_dir, config_file=None, config=None):
        """Initialize the handler"""
        self.output_dir = output_dir
        self.config_file = config_file
        self.config = config
        self.service = PDFCutterService()
        self.processing_files = set()

    def on_created(self, event):
        """Handle when a file is created in the watched directory"""
        if event.is_directory:
            return

        if not event.src_path.lower().endswith(".pdf"):
            return

        # Avoid duplicate processing
        if event.src_path in self.processing_files:
            return

        # Add to task queue
        logger.info(f"Detected new PDF: {event.src_path}")
        task_queue.put((event.src_path, self.output_dir, self.config_file, self.config))
        self.processing_files.add(event.src_path)


# Worker thread for processing PDF files from the queue
def worker_thread():
    """Worker thread for processing PDF files from the queue"""
    service = PDFCutterService()

    while service_status["running"]:
        try:
            # Get a task from the queue (timeout allows for checking if service is still running)
            task = task_queue.get(timeout=1)
            if task:
                input_path, output_dir, config_file, config = task

                try:
                    # If config_file is provided but config is not, load the config
                    if config_file and not config:
                        config = service.load_config(config_file)

                    # Process based on config or prompt for page ranges
                    if config:
                        filename_without_ext = os.path.splitext(
                            os.path.basename(input_path)
                        )[0]

                        if filename_without_ext in config:
                            file_config = config[filename_without_ext]
                            page_ranges = [
                                (r["start"], r["end"], r.get("name"))
                                for r in file_config["page_ranges"]
                            ]
                            unit_name = file_config.get("unit_name")
                            prefix = file_config.get("prefix")
                            fix_encoding = file_config.get("fix_encoding", True)

                            service.split_pdf(
                                input_path,
                                output_dir,
                                page_ranges,
                                prefix,
                                unit_name,
                                fix_encoding,
                            )

                        elif "default" in config:
                            file_config = config["default"]
                            page_ranges = [
                                (r["start"], r["end"], r.get("name"))
                                for r in file_config["page_ranges"]
                            ]
                            unit_name = file_config.get("unit_name")
                            prefix = file_config.get("prefix")
                            fix_encoding = file_config.get("fix_encoding", True)

                            service.split_pdf(
                                input_path,
                                output_dir,
                                page_ranges,
                                prefix,
                                unit_name,
                                fix_encoding,
                            )

                        else:
                            logger.warning(
                                f"No configuration found for {input_path}, skipping..."
                            )

                except Exception as e:
                    logger.error(f"Error processing task {input_path}: {str(e)}")
                    traceback.print_exc()

                finally:
                    # Mark task as done
                    task_queue.task_done()

        except queue.Empty:
            # Queue is empty, continue the loop
            pass

        except Exception as e:
            logger.error(f"Error in worker thread: {str(e)}")
            traceback.print_exc()


# Simple HTTP API for the service
class PDFCutterRequestHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP API for the PDF Cutter Service"""

    def __init__(self, *args, **kwargs):
        self.service = PDFCutterService()
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Redirect logging to our logger instead of stderr
        logger.info(f"{self.address_string()} - {format % args}")

    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        try:
            # Status endpoint
            if path == "/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()

                # Add current task from service
                global service_status
                if self.service.current_task:
                    service_status["current_task"] = self.service.current_task

                # Add queue information
                service_status["queue_size"] = task_queue.qsize()

                status_json = json.dumps(service_status, indent=2)
                self.wfile.write(status_json.encode())
                return

            # Help/documentation endpoint
            elif path == "/" or path == "/help":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()

                help_text = """
PDF Cutter Service API

Available endpoints:
  GET /status - Get service status
  GET /help - This help information
  POST /split - Split a PDF (provide input_file and ranges parameters)
                
Example:
  curl -X POST "http://localhost:8111/split?input_file=example.pdf&ranges=1-5:Part1,6-10:Part2&output_dir=output"
                """
                self.wfile.write(help_text.encode())
                return

            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

        except Exception as e:
            logger.error(f"Error handling GET request: {str(e)}")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Server Error: {str(e)}".encode())

    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = dict(urllib.parse.parse_qsl(parsed_path.query))

        try:
            # Split PDF endpoint
            if path == "/split":
                if "input_file" not in query or "ranges" not in query:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(
                        b"Missing required parameters: input_file and ranges"
                    )
                    return

                input_file = query["input_file"]
                ranges_str = query["ranges"]
                output_dir = query.get("output_dir", "output")
                prefix = query.get("prefix")
                unit_name = query.get("unit_name")
                fix_encoding = query.get("fix_encoding", "true").lower() == "true"

                try:
                    # Parse page ranges
                    page_ranges = self.service.parse_page_ranges(ranges_str)

                    # Split the PDF
                    output_files = self.service.split_pdf(
                        input_file,
                        output_dir,
                        page_ranges,
                        prefix,
                        unit_name,
                        fix_encoding,
                    )

                    # Return success response
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()

                    response = {
                        "status": "success",
                        "input_file": input_file,
                        "output_dir": output_dir,
                        "output_files": output_files,
                        "page_ranges": [
                            (start, end, name) for start, end, name in page_ranges
                        ],
                    }

                    self.wfile.write(json.dumps(response, indent=2).encode())

                except Exception as e:
                    logger.error(f"Error processing split request: {str(e)}")
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"Error: {str(e)}".encode())

                return

            # Text correction endpoint for handling Hindi encoding issues directly
            elif path == "/correct_text":
                # Get the request body
                content_length = int(self.headers["Content-Length"])
                post_data = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(post_data)

                if "text" not in data:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"Missing required parameter: text")
                    return

                text = data["text"]
                font_type = data.get("font_type", "auto")

                # Process the text
                has_encoding_issues = (
                    self.service.detect_potential_hindi_encoding_issue(text)
                )

                if has_encoding_issues:
                    corrected_text = self.service.correct_hindi_text(text, font_type)
                    corrected_text = self.service.post_process_hindi_text(
                        corrected_text
                    )
                else:
                    corrected_text = text

                # Return the corrected text
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()

                response = {
                    "original_text": text,
                    "has_encoding_issues": has_encoding_issues,
                    "corrected_text": corrected_text,
                    "detected_font_type": (
                        font_type if font_type != "auto" else "krutidev"
                    ),
                }

                self.wfile.write(json.dumps(response, indent=2).encode())
                return

            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

        except Exception as e:
            logger.error(f"Error handling POST request: {str(e)}")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Server Error: {str(e)}".encode())


def find_available_port(start_port=8001, max_attempts=100):
    """Find an available port starting from start_port"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port

    # If no port found, use a random high port
    return 0  # Let the OS choose a port


def run_service(watch_dir=None, output_dir="output", config_file=None, port=None):
    """Run the PDF Cutter Service"""
    # Initialize service
    config = None
    if config_file:
        try:
            config = PDFCutterService.load_config(config_file)
            logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            return

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Start worker thread
    worker = threading.Thread(target=worker_thread, daemon=True)
    worker.start()
    logger.info("Started worker thread")

    # Set up directory watcher if watch_dir is specified
    observer = None
    if watch_dir:
        observer = Observer()
        event_handler = PDFHandler(output_dir, config_file, config)
        observer.schedule(event_handler, watch_dir, recursive=False)
        observer.start()
        logger.info(f"Watching directory: {watch_dir}")

    # Set up HTTP server
    if port is None:
        port = find_available_port()

    try:
        httpd = socketserver.TCPServer(("", port), PDFCutterRequestHandler)
        logger.info(f"Starting HTTP server on port {port}")

        # Print service info
        print(f"\n{'=' * 60}")
        print(f"PDF Cutter Service is running")
        print(f"{'=' * 60}")
        print(f"API available at http://localhost:{port}")
        print(f"API endpoints:")
        print(f"  - GET  /status - Service status")
        print(f"  - GET  /help   - Help information")
        print(f"  - POST /split  - Split a PDF")
        print(f"  - POST /correct_text - Correct Hindi text encoding")
        if watch_dir:
            print(f"Watching directory: {watch_dir}")
        print(f"Output directory: {output_dir}")
        if config_file:
            print(f"Using configuration: {config_file}")
        print(f"{'=' * 60}\n")

        # Run the server
        httpd.serve_forever()

    except KeyboardInterrupt:
        logger.info("Service shutting down on CTRL+C")
        print("\nShutting down PDF Cutter Service...")

    except Exception as e:
        logger.error(f"Error running service: {str(e)}")

    finally:
        # Cleanup
        if observer:
            observer.stop()
            observer.join()

        service_status["running"] = False
        worker.join(timeout=2)
        logger.info("PDF Cutter Service stopped")


def main():
    """Main function to parse arguments and execute the service"""
    parser = argparse.ArgumentParser(
        description="PDF Cutter Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run as a service watching a directory
  python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json
  
  # Run as a service with a specific port for API access
  python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --port 5000
  
  # Run as a service without watching a directory (API only)
  python pdf_cutter_service.py --output-dir ./output --port 8111
        """,
    )

    parser.add_argument("--watch-dir", help="Directory to watch for new PDF files")
    parser.add_argument(
        "--output-dir", default="output", help="Output directory for split PDF files"
    )
    parser.add_argument("--config", help="JSON configuration file")
    parser.add_argument(
        "--port", type=int, help="Port for HTTP API (default: auto-detect)"
    )

    args = parser.parse_args()

    # Run the service
    run_service(args.watch_dir, args.output_dir, args.config, args.port)


if __name__ == "__main__":
    main()
