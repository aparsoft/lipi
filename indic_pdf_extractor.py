# /home/ram/school_edition_lms/backend/apps/curriculum/services/utils/indic_pdf_extractor.py

"""
Indic Language PDF Text Extractor
===================================

🔥 HIGH-PERFORMANCE TEXT EXTRACTION FOR HINDI/SANSKRIT/INDIC LANGUAGES

This utility module provides specialized PDF text extraction optimized for:
- 🕉️ Sanskrit (Devanagari script)
- 🇮🇳 Hindi and other Indic languages
- 📚 Complex Unicode documents
- 🎯 Custom font encodings

KEY FEATURES:
- PyMuPDF (fitz) as primary extractor - EXCELLENT for Unicode/Indic languages
- Intelligent garbage text detection for font encoding issues
- Multi-method fallback strategy (PyMuPDF → pdfplumber → pypdf → OCR)
- Batched OCR processing for image-based PDFs
- Memory-safe operations
- Production-ready error handling

USAGE:
    from curriculum.services.utils.indic_pdf_extractor import IndicPdfExtractor

    # Initialize with configuration
    extractor = IndicPdfExtractor(
        enable_ocr=True,
        ocr_language="hin+san+eng",  # Hindi + Sanskrit + English
        ocr_config="--psm 6"
    )

    # Extract text with automatic method selection
    result = await extractor.extract_text_from_pdf(
        file_path="/path/to/sanskrit.pdf",
        prefer_method="pymupdf"  # or "pdfplumber", "pypdf", "ocr"
    )

    if result.success:
        print(f"Extracted {result.char_count} characters")
        print(f"Method: {result.extraction_method}")
        print(f"Text quality: {result.quality_score}")

    # Get LangChain documents (for document_services.py)
    documents = await extractor.extract_as_langchain_documents(file_path)

INTEGRATION:
    This module is designed to be imported by:
    - document_services.py (for vector search/RAG)
    - document_text_service.py (for direct AI analysis)
    - Any other service needing Indic PDF extraction

Author: AI Assistant
Date: November 2025
Version: 1.0.0
"""

import os
import logging
import asyncio
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# Check library availability
try:
    import fitz  # PyMuPDF - BEST for Hindi/Sanskrit/Unicode

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) not available. Install: pip install pymupdf")

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not available. Install: pip install pdfplumber")

try:
    import pypdf

    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False
    logger.warning("pypdf not available. Install: pip install pypdf")

try:
    import pytesseract
    from PIL import Image

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("OCR libraries not available. Install: pip install pytesseract pillow")

try:
    from langchain_core.documents import Document

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


@dataclass
class ExtractionResult:
    """Result of PDF text extraction"""

    text: str
    extraction_method: str
    success: bool
    page_count: int
    char_count: int
    word_count: int
    quality_score: float  # 0.0 to 1.0
    is_garbage: bool
    metadata: Dict[str, Any]
    error: Optional[str] = None
    processing_time_seconds: Optional[float] = None


class IndicPdfExtractor:
    """
    High-performance PDF text extractor optimized for Indic languages.

    Extraction Strategy:
    1. Try PyMuPDF (fitz) - BEST for Unicode/Hindi/Sanskrit
    2. Validate text quality (garbage detection)
    3. Fallback to pdfplumber if needed
    4. Fallback to pypdf if needed
    5. Fallback to OCR for image-based PDFs
    """

    def __init__(
        self,
        enable_ocr: bool = True,
        ocr_language: str = "eng+hin+san",  # English + Hindi + Sanskrit
        ocr_config: str = "--psm 6",
        max_pages_per_batch: int = 2,
        ocr_dpi: int = 200,
        prefer_pymupdf: bool = True,
    ):
        """
        Initialize the Indic PDF extractor.

        Args:
            enable_ocr: Enable OCR fallback for image-based PDFs
            ocr_language: Tesseract language codes (e.g., "eng+hin+san")
            ocr_config: Tesseract PSM config
            max_pages_per_batch: Pages per batch for OCR (memory safety)
            ocr_dpi: DPI for OCR conversion
            prefer_pymupdf: Prefer PyMuPDF over other methods
        """
        self.enable_ocr = enable_ocr
        self.ocr_language = ocr_language
        self.ocr_config = ocr_config
        self.max_pages_per_batch = max_pages_per_batch
        self.ocr_dpi = ocr_dpi
        self.prefer_pymupdf = prefer_pymupdf

        # Check library availability
        self._check_dependencies()

    def _check_dependencies(self):
        """Check which extraction libraries are available"""
        status = []

        if PYMUPDF_AVAILABLE:
            status.append("✅ PyMuPDF (fitz) - BEST for Indic languages")
        else:
            status.append("❌ PyMuPDF not available")

        if PDFPLUMBER_AVAILABLE:
            status.append("✅ pdfplumber - Good for tables")
        else:
            status.append("❌ pdfplumber not available")

        if PYPDF_AVAILABLE:
            status.append("✅ pypdf - Basic extraction")
        else:
            status.append("❌ pypdf not available")

        if OCR_AVAILABLE and self.enable_ocr:
            status.append(f"✅ OCR enabled - Language: {self.ocr_language}")
        elif self.enable_ocr:
            status.append("⚠️ OCR enabled but libraries not available")

        logger.info("Indic PDF Extractor initialized:")
        for s in status:
            logger.info(f"  {s}")

    def _is_garbage_text(self, text: str) -> Tuple[bool, float, str]:
        """
        Detect if extracted text is garbage (font encoding issues).

        Common with Hindi/Indic PDFs that have custom font mappings.

        Args:
            text: Extracted text to analyze

        Returns:
            (is_garbage, quality_score, reason)
        """
        if not text or len(text.strip()) < 50:
            return (True, 0.0, "Text too short (< 50 chars)")

        # Count character types
        total_chars = 0
        punctuation_chars = 0
        garbage_chars = 0
        letter_chars = 0
        digit_chars = 0

        for char in text:
            if char.strip():  # Non-whitespace
                total_chars += 1
                code = ord(char)

                # Check if it's punctuation/separator
                if char in ".,!?;:()[]{}\"'-=/" or (0x2000 <= code <= 0x206F):
                    punctuation_chars += 1
                    continue

                # Check if it's a digit
                if 0x0030 <= code <= 0x0039:
                    digit_chars += 1
                    continue

                # Check if it's a valid letter (Latin or Indic scripts)
                is_valid_letter = (
                    (0x0041 <= code <= 0x005A)  # Uppercase Latin
                    or (0x0061 <= code <= 0x007A)  # Lowercase Latin
                    or (0x0900 <= code <= 0x097F)  # Devanagari (Hindi/Sanskrit)
                    or (0x0980 <= code <= 0x09FF)  # Bengali
                    or (0x0A00 <= code <= 0x0A7F)  # Gurmukhi (Punjabi)
                    or (0x0A80 <= code <= 0x0AFF)  # Gujarati
                    or (0x0B00 <= code <= 0x0B7F)  # Oriya
                    or (0x0B80 <= code <= 0x0BFF)  # Tamil
                    or (0x0C00 <= code <= 0x0C7F)  # Telugu
                    or (0x0C80 <= code <= 0x0CFF)  # Kannada
                    or (0x0D00 <= code <= 0x0D7F)  # Malayalam
                )

                if is_valid_letter:
                    letter_chars += 1
                else:
                    garbage_chars += 1

        if total_chars == 0:
            return (True, 0.0, "No characters found")

        # Calculate ratios
        punctuation_ratio = punctuation_chars / total_chars
        letter_ratio = letter_chars / total_chars
        garbage_ratio = garbage_chars / total_chars

        # Detection 1: Too much punctuation (> 50%)
        if punctuation_ratio > 0.5:
            return (
                True,
                1.0 - punctuation_ratio,
                f"Too much punctuation: {punctuation_ratio:.1%}",
            )

        # Detection 2: Too few letters (< 40%)
        if letter_ratio < 0.4:
            return (True, letter_ratio, f"Too few letters: {letter_ratio:.1%}")

        # Detection 3: Too many garbage characters (> 30%)
        if garbage_ratio > 0.3:
            return (
                True,
                1.0 - garbage_ratio,
                f"Too many unreadable characters: {garbage_ratio:.1%}",
            )

        # Calculate quality score (0.0 to 1.0)
        # Higher score = better quality
        quality_score = (
            letter_ratio * 0.7  # Letters are most important
            + (1.0 - garbage_ratio) * 0.2  # Low garbage is good
            + (1.0 - punctuation_ratio) * 0.1  # Low punctuation is good
        )

        return (False, quality_score, "Text quality acceptable")

    async def extract_text_from_pdf(
        self, file_path: str, prefer_method: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract text from PDF with automatic method selection and quality validation.

        Args:
            file_path: Path to PDF file
            prefer_method: Preferred extraction method ("pymupdf", "pdfplumber", "pypdf", "ocr")

        Returns:
            ExtractionResult with extracted text and metadata
        """
        start_time = datetime.now()

        if not os.path.exists(file_path):
            return ExtractionResult(
                text="",
                extraction_method="none",
                success=False,
                page_count=0,
                char_count=0,
                word_count=0,
                quality_score=0.0,
                is_garbage=True,
                metadata={},
                error=f"File not found: {file_path}",
            )

        # Get page count
        page_count = await self._get_page_count(file_path)

        # Determine extraction order based on preference
        if prefer_method == "ocr" and OCR_AVAILABLE and self.enable_ocr:
            methods = ["ocr"]
        elif prefer_method == "pdfplumber" and PDFPLUMBER_AVAILABLE:
            methods = ["pdfplumber", "pymupdf", "pypdf", "ocr"]
        elif prefer_method == "pypdf" and PYPDF_AVAILABLE:
            methods = ["pypdf", "pymupdf", "pdfplumber", "ocr"]
        else:
            # Default order: PyMuPDF first (BEST for Indic)
            methods = ["pymupdf", "pdfplumber", "pypdf", "ocr"]

        # Try each method in order
        for method in methods:
            try:
                logger.info(f"🔍 Attempting extraction with: {method}")

                if method == "pymupdf" and PYMUPDF_AVAILABLE:
                    text = await self._extract_with_pymupdf(file_path)
                    extraction_method = "pymupdf"

                elif method == "pdfplumber" and PDFPLUMBER_AVAILABLE:
                    text = await self._extract_with_pdfplumber(file_path)
                    extraction_method = "pdfplumber"

                elif method == "pypdf" and PYPDF_AVAILABLE:
                    text = await self._extract_with_pypdf(file_path)
                    extraction_method = "pypdf"

                elif method == "ocr" and OCR_AVAILABLE and self.enable_ocr:
                    text = await self._extract_with_ocr(file_path, page_count)
                    extraction_method = "ocr_batched"

                else:
                    continue

                # Validate text quality
                is_garbage, quality_score, reason = self._is_garbage_text(text)

                if is_garbage:
                    logger.warning(
                        f"⚠️ {extraction_method} produced garbage text: {reason} "
                        f"(quality: {quality_score:.2f}). Trying next method..."
                    )
                    continue

                # Success! Calculate metrics
                char_count = len(text)
                word_count = len(text.split())
                processing_time = (datetime.now() - start_time).total_seconds()

                logger.info(
                    f"✅ Successfully extracted {char_count:,} chars "
                    f"using {extraction_method} (quality: {quality_score:.2f})"
                )

                return ExtractionResult(
                    text=text,
                    extraction_method=extraction_method,
                    success=True,
                    page_count=page_count,
                    char_count=char_count,
                    word_count=word_count,
                    quality_score=quality_score,
                    is_garbage=False,
                    metadata={
                        "file_path": file_path,
                        "file_name": os.path.basename(file_path),
                        "quality_reason": reason,
                    },
                    processing_time_seconds=processing_time,
                )

            except Exception as e:
                logger.warning(f"❌ {method} extraction failed: {str(e)}")
                continue

        # All methods failed
        processing_time = (datetime.now() - start_time).total_seconds()
        return ExtractionResult(
            text="",
            extraction_method="all_failed",
            success=False,
            page_count=page_count,
            char_count=0,
            word_count=0,
            quality_score=0.0,
            is_garbage=True,
            metadata={"file_path": file_path},
            error="All extraction methods failed or produced garbage text",
            processing_time_seconds=processing_time,
        )

    async def _get_page_count(self, file_path: str) -> int:
        """Get PDF page count using available libraries"""
        try:
            if PYPDF_AVAILABLE:

                def count_pages():
                    with open(file_path, "rb") as f:
                        reader = pypdf.PdfReader(f)
                        return len(reader.pages)

                return await asyncio.to_thread(count_pages)

            elif PYMUPDF_AVAILABLE:

                def count_pages():
                    doc = fitz.open(file_path)
                    count = len(doc)
                    doc.close()
                    return count

                return await asyncio.to_thread(count_pages)

            else:
                logger.warning("No PDF library available for page counting")
                return 1

        except Exception as e:
            logger.warning(f"Could not count pages: {e}")
            return 1

    async def _extract_with_pymupdf(self, file_path: str) -> str:
        """
        Extract text using PyMuPDF (fitz) - EXCELLENT for Unicode/Hindi/Indic languages.

        PyMuPDF handles complex font encodings and Unicode better than other libraries.
        """

        def extract():
            text_parts = []
            doc = fitz.open(file_path)

            try:
                for page_num in range(len(doc)):
                    try:
                        page = doc[page_num]
                        # Extract with proper Unicode handling
                        page_text = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)

                        if page_text and page_text.strip():
                            text_parts.append(f"=== Page {page_num + 1} ===\n{page_text}\n")
                    except Exception as e:
                        logger.warning(f"Error extracting page {page_num + 1} with PyMuPDF: {e}")
                        continue
            finally:
                doc.close()

            return "\n".join(text_parts)

        return await asyncio.to_thread(extract)

    async def _extract_with_pdfplumber(self, file_path: str) -> str:
        """Extract text using pdfplumber (good for tables)"""

        def extract():
            text_parts = []

            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            text_parts.append(f"=== Page {page_num + 1} ===\n{page_text}\n")
                    except Exception as e:
                        logger.warning(f"Error extracting page {page_num + 1} with pdfplumber: {e}")
                        continue

            return "\n".join(text_parts)

        return await asyncio.to_thread(extract)

    async def _extract_with_pypdf(self, file_path: str) -> str:
        """Extract text using pypdf (basic extraction)"""

        def extract():
            text_parts = []

            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)

                for page_num, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            text_parts.append(f"=== Page {page_num + 1} ===\n{page_text}\n")
                    except Exception as e:
                        logger.warning(f"Error extracting page {page_num + 1} with pypdf: {e}")
                        continue

            return "\n".join(text_parts)

        return await asyncio.to_thread(extract)

    async def _extract_with_ocr(self, file_path: str, page_count: int) -> str:
        """
        Extract text using OCR with batched processing (memory-safe).

        Uses the same batching strategy as ocr_config.py to prevent OOM kills.
        """
        import gc

        logger.info(f"🤖 Starting OCR extraction for {page_count} pages")

        # Check page limit
        max_pages = 50  # Safety limit
        if page_count > max_pages:
            raise ValueError(f"PDF has {page_count} pages, exceeds OCR limit of {max_pages}")

        all_text_parts = []

        # Calculate batch ranges
        batch_ranges = []
        for start in range(1, page_count + 1, self.max_pages_per_batch):
            end = min(start + self.max_pages_per_batch - 1, page_count)
            batch_ranges.append((start, end))

        logger.info(f"📦 Processing {page_count} pages in {len(batch_ranges)} batches")

        # Process each batch
        for batch_num, (first_page, last_page) in enumerate(batch_ranges, 1):
            try:
                logger.info(
                    f"⚙️  Batch {batch_num}/{len(batch_ranges)}: " f"pages {first_page}-{last_page}"
                )

                # Convert PDF pages to images using fitz (no pdf2image needed)
                def render_pages(fp, fp_start, fp_end, dpi):
                    doc = fitz.open(fp)
                    mat = fitz.Matrix(dpi / 72, dpi / 72)
                    imgs = []
                    for pn in range(fp_start - 1, fp_end):  # fitz is 0-indexed
                        pix = doc[pn].get_pixmap(matrix=mat)
                        imgs.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
                    doc.close()
                    return imgs

                batch_images = await asyncio.wait_for(
                    asyncio.to_thread(
                        render_pages,
                        file_path,
                        first_page,
                        last_page,
                        self.ocr_dpi,
                    ),
                    timeout=30 * (last_page - first_page + 1),
                )

                # OCR each image
                for idx, image in enumerate(batch_images):
                    page_num = first_page + idx

                    try:
                        # Resize if too large (memory optimization)
                        max_dim = 2000
                        if image.width > max_dim or image.height > max_dim:
                            ratio = min(max_dim / image.width, max_dim / image.height)
                            new_size = (
                                int(image.width * ratio),
                                int(image.height * ratio),
                            )
                            image = image.resize(new_size, Image.LANCZOS)

                        # Extract text with OCR
                        page_text = await asyncio.wait_for(
                            asyncio.to_thread(
                                pytesseract.image_to_string,
                                image,
                                lang=self.ocr_language,
                                config=self.ocr_config,
                            ),
                            timeout=30,
                        )

                        if page_text and page_text.strip():
                            all_text_parts.append(f"=== Page {page_num} ===\n{page_text.strip()}\n")

                    except asyncio.TimeoutError:
                        logger.warning(f"⏰ OCR timeout on page {page_num}")
                        continue
                    except Exception as e:
                        logger.warning(f"❌ OCR failed on page {page_num}: {e}")
                        continue

                # Cleanup batch
                del batch_images
                gc.collect()

            except Exception as e:
                logger.error(f"❌ Batch {batch_num} processing failed: {e}")
                continue

        full_text = "\n".join(all_text_parts)

        if not full_text.strip():
            raise ValueError("No text extracted from PDF via OCR")

        logger.info(
            f"✅ OCR complete: {len(all_text_parts)} pages, " f"{len(full_text)} characters"
        )

        return full_text

    async def extract_as_langchain_documents(
        self, file_path: str, custom_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Extract PDF as LangChain Document objects (for document_services.py).

        Args:
            file_path: Path to PDF file
            custom_metadata: Additional metadata to add to documents

        Returns:
            List of LangChain Document objects (one per page)
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain not available. Install: pip install langchain-core")

        # Extract text
        result = await self.extract_text_from_pdf(file_path)

        if not result.success:
            logger.error(f"Failed to extract text: {result.error}")
            return []

        # Split by page markers
        page_pattern = r"=== Page (\d+) ===\n(.*?)(?=\n=== Page \d+ ===|\Z)"
        matches = re.finditer(page_pattern, result.text, re.DOTALL)

        documents = []
        base_metadata = custom_metadata or {}

        for match in matches:
            page_num = int(match.group(1))
            page_content = match.group(2).strip()

            if page_content:
                metadata = {
                    **base_metadata,
                    "source": file_path,
                    "page": page_num,
                    "file_type": "pdf",
                    "extraction_method": result.extraction_method,
                    "quality_score": result.quality_score,
                }

                doc = Document(page_content=page_content, metadata=metadata)
                documents.append(doc)

        logger.info(f"✅ Created {len(documents)} LangChain documents from {file_path}")

        return documents


# Convenience functions for quick usage


async def extract_pdf_text(
    file_path: str, ocr_language: str = "eng+hin+san", enable_ocr: bool = True
) -> ExtractionResult:
    """
    Quick extraction function.

    Args:
        file_path: Path to PDF
        ocr_language: Tesseract language codes
        enable_ocr: Enable OCR fallback

    Returns:
        ExtractionResult
    """
    extractor = IndicPdfExtractor(enable_ocr=enable_ocr, ocr_language=ocr_language)
    return await extractor.extract_text_from_pdf(file_path)


async def extract_pdf_as_langchain_docs(
    file_path: str,
    custom_metadata: Optional[Dict[str, Any]] = None,
    ocr_language: str = "eng+hin+san",
) -> List[Document]:
    """
    Quick extraction as LangChain documents.

    Args:
        file_path: Path to PDF
        custom_metadata: Additional metadata
        ocr_language: Tesseract language codes

    Returns:
        List of LangChain Document objects
    """
    extractor = IndicPdfExtractor(ocr_language=ocr_language)
    return await extractor.extract_as_langchain_documents(file_path, custom_metadata)


if __name__ == "__main__":
    import sys
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python indic_pdf_extractor.py <pdf_path> [output_txt_path]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(pdf_path).with_suffix(".txt"))

    async def main():
        print(f"📄 Extracting: {pdf_path}")
        extractor = IndicPdfExtractor(enable_ocr=True, ocr_language="eng+hin+san")
        result = await extractor.extract_text_from_pdf(pdf_path)

        if not result.success:
            print(f"❌ Extraction failed: {result.error}")
            sys.exit(1)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.text)

        print(f"✅ Done!")
        print(f"   Method  : {result.extraction_method}")
        print(f"   Pages   : {result.page_count}")
        print(f"   Chars   : {result.char_count:,}")
        print(f"   Words   : {result.word_count:,}")
        print(f"   Quality : {result.quality_score:.2f}")
        print(f"   Output  : {output_path}")

    asyncio.run(main())
