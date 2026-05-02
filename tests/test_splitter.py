"""Unit tests for lipi.splitter — PDFSplitter class."""

import os
import json
import tempfile
import pytest
from pypdf import PdfWriter

from lipi.splitter import PDFSplitter


def _create_test_pdf(path: str, num_pages: int = 5) -> str:
    """Create a minimal PDF with *num_pages* pages at *path*."""
    writer = PdfWriter()
    for i in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


class TestParsePageRanges:
    """Tests for PDFSplitter.parse_page_ranges()."""

    def test_basic_ranges(self):
        result = PDFSplitter.parse_page_ranges("1-10:Lecture1,11-20:Lecture2")
        assert len(result) == 2
        assert result[0] == (1, 10, "Lecture1")
        assert result[1] == (11, 20, "Lecture2")

    def test_ranges_without_names(self):
        result = PDFSplitter.parse_page_ranges("1-5,6-10")
        assert len(result) == 2
        assert result[0] == (1, 5, None)
        assert result[1] == (6, 10, None)

    def test_mixed_ranges(self):
        result = PDFSplitter.parse_page_ranges("1-3:Intro,4-10,11-15:Final")
        assert len(result) == 3
        assert result[0] == (1, 3, "Intro")
        assert result[1] == (4, 10, None)
        assert result[2] == (11, 15, "Final")

    def test_url_encoded_ranges(self):
        result = PDFSplitter.parse_page_ranges("1-10%3AMath%2C11-20%3AScience")
        assert len(result) == 2

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid ranges"):
            PDFSplitter.parse_page_ranges("invalid")

    def test_negative_start_raises(self):
        with pytest.raises(ValueError, match="positive"):
            PDFSplitter.parse_page_ranges("0-5")

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match=">= start"):
            PDFSplitter.parse_page_ranges("10-5")


class TestValidateConfig:
    """Tests for PDFSplitter.validate_config()."""

    def test_valid_config(self):
        config = {
            "test": {
                "page_ranges": [
                    {"start": 1, "end": 5, "name": "Part1"},
                    {"start": 6, "end": 10},
                ]
            }
        }
        assert PDFSplitter.validate_config(config) is True

    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="dictionary"):
            PDFSplitter.validate_config("not a dict")

    def test_missing_page_ranges_raises(self):
        with pytest.raises(ValueError, match="page_ranges"):
            PDFSplitter.validate_config({"test": {"prefix": "x"}})

    def test_invalid_start_raises(self):
        with pytest.raises(ValueError, match="> 0"):
            PDFSplitter.validate_config({"test": {"page_ranges": [{"start": 0, "end": 5}]}})

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match=">= 'start'"):
            PDFSplitter.validate_config({"test": {"page_ranges": [{"start": 10, "end": 5}]}})


class TestLoadConfig:
    """Tests for PDFSplitter.load_config()."""

    def test_load_valid_config(self, tmp_path):
        config = {"test": {"page_ranges": [{"start": 1, "end": 5}]}}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))
        result = PDFSplitter.load_config(str(config_path))
        assert "test" in result

    def test_invalid_json_raises(self, tmp_path):
        config_path = tmp_path / "bad.json"
        config_path.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            PDFSplitter.load_config(str(config_path))


class TestSplitPdf:
    """Tests for PDFSplitter.split_pdf()."""

    def test_split_creates_files(self, tmp_path):
        pdf_path = str(tmp_path / "test.pdf")
        _create_test_pdf(pdf_path, num_pages=10)
        output_dir = str(tmp_path / "output")

        files = PDFSplitter.split_pdf(
            pdf_path,
            output_dir,
            [(1, 5, "Part1"), (6, 10, "Part2")],
        )
        assert len(files) == 2
        for f in files:
            assert os.path.isfile(f)

    def test_split_with_prefix(self, tmp_path):
        pdf_path = str(tmp_path / "test.pdf")
        _create_test_pdf(pdf_path, num_pages=5)
        output_dir = str(tmp_path / "output")

        files = PDFSplitter.split_pdf(
            pdf_path,
            output_dir,
            [(1, 5, "All")],
            prefix="NCERT",
        )
        assert len(files) == 1
        assert "NCERT" in os.path.basename(files[0])

    def test_split_skips_invalid_range(self, tmp_path):
        pdf_path = str(tmp_path / "test.pdf")
        _create_test_pdf(pdf_path, num_pages=5)
        output_dir = str(tmp_path / "output")

        files = PDFSplitter.split_pdf(
            pdf_path,
            output_dir,
            [(1, 3, "Valid"), (10, 20, "Invalid")],
        )
        assert len(files) == 1

    def test_split_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            PDFSplitter.split_pdf(
                "/nonexistent.pdf",
                "/tmp/output",
                [(1, 5, "Test")],
            )


class TestGetPdfInfo:
    """Tests for PDFSplitter.get_pdf_info()."""

    def test_returns_info(self, tmp_path):
        pdf_path = str(tmp_path / "test.pdf")
        _create_test_pdf(pdf_path, num_pages=3)

        info = PDFSplitter.get_pdf_info(pdf_path)
        assert info["filename"] == "test.pdf"
        assert info["total_pages"] == 3
        assert info["size_kb"] > 0

    def test_file_not_found(self):
        info = PDFSplitter.get_pdf_info("/nonexistent.pdf")
        assert "error" in info
