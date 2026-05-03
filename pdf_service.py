"""
Backward-compatibility shim for pdf_service.py.

All functionality has been moved to the ``lipi`` package:
- PDFSplitter, parse_page_ranges, etc. -> lipi.splitter
- extract_unicode_text -> lipi.extractor
- CLI -> lipi.cli
- HindiPreprocessor -> lipi.preprocessor

Existing imports like ``from pdf_service import PDFCutterService``
will continue to work via the PDFCutterService compatibility class below.
"""

from typing import Dict, Any, List, Tuple, Optional

from lipi.preprocessor import HindiPreprocessor
from lipi.splitter import PDFSplitter
from lipi.extractor import extract_unicode_text

__version__ = "1.0.0"


class PDFCutterService:
    """
    Backward-compatible facade that delegates to lipi.splitter.PDFSplitter
    and lipi.preprocessor.HindiPreprocessor.
    """

    def __init__(self) -> None:
        self.current_task: Optional[str] = None

    # -- Parsing --
    @staticmethod
    def parse_page_ranges(ranges_str: str) -> List[Tuple[int, int, Optional[str]]]:
        return PDFSplitter.parse_page_ranges(ranges_str)

    # -- Hindi encoding (delegated) --
    @staticmethod
    def detect_encoding_issues(text: str) -> Tuple[bool, str]:
        return HindiPreprocessor.detect_encoding(text)

    @staticmethod
    def detect_potential_hindi_encoding_issue(text: str) -> bool:
        has_issues, _ = HindiPreprocessor.detect_encoding(text)
        return has_issues

    @staticmethod
    def get_hindi_font_mapping(font_type: str = "krutidev") -> Dict[str, str]:
        return HindiPreprocessor.get_mapping(font_type)

    @staticmethod
    def convert_to_unicode(text: str, font_type: str = "auto") -> str:
        return HindiPreprocessor.convert(text, font_type)

    @staticmethod
    def correct_hindi_text(text: str, font_type: str = "auto") -> str:
        return HindiPreprocessor.correct_hindi_text(text, font_type)

    @staticmethod
    def post_process_hindi_text(text: str) -> str:
        return HindiPreprocessor.post_process(text)

    # -- Extraction --
    def extract_unicode_text(self, pdf_path, page_range=None, font_type="auto", post_process=True):
        return extract_unicode_text(pdf_path, page_range, font_type, post_process)

    def batch_extract_unicode_text(self, input_dir, font_type="auto", post_process=True):
        import os

        results = []
        for filename in sorted(os.listdir(input_dir)):
            if not filename.lower().endswith(".pdf"):
                continue
            pdf_path = os.path.join(input_dir, filename)
            res = extract_unicode_text(pdf_path, font_type=font_type, post_process=post_process)
            results.append(res)
        return results

    # -- PDF info --
    def get_pdf_info(self, pdf_path: str) -> Dict[str, Any]:
        return PDFSplitter.get_pdf_info(pdf_path)

    # -- Config --
    @staticmethod
    def validate_config(config: Dict) -> bool:
        return PDFSplitter.validate_config(config)

    @staticmethod
    def load_config(config_file: str) -> Dict:
        return PDFSplitter.load_config(config_file)

    # -- Splitting --
    def split_pdf(self, input_file, output_dir, page_ranges, prefix=None, unit_name=None):
        return PDFSplitter.split_pdf(input_file, output_dir, page_ranges, prefix, unit_name)

    def process_directory(self, input_dir, output_dir, config):
        return PDFSplitter.process_directory(input_dir, output_dir, config)


def main() -> None:
    from lipi.cli import main as lipi_main

    lipi_main()


if __name__ == "__main__":
    main()
