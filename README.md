# Lipi

> **Part of the [Aparsoft](https://aparsoft.in) open-source EdTech toolchain**
> Built for the [Apar Academy](https://aparacademy.in) Hindi PDF content ingestion pipeline — open-sourced for the Indian EdTech community.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange)](https://github.com/aparsoft/lipi)

---

## What this does

Two things — and only those two things, done well:

1. **Split PDFs by page range** — extract chapters, lectures, or units out of a large PDF into separate files, with optional batch processing via a JSON config.

2. **Extract Unicode text from legacy Hindi-font PDFs** — detect KrutiDev / Chanakya encoded PDFs and convert the extracted text to proper Unicode Devanagari, making it searchable, copy-pasteable, and usable in NLP pipelines.

### Why this exists

Old legacy Hindi textbooks, state board materials, government circulars, and Hindi newspapers were typeset in **glyph-substitution fonts** like KrutiDev and Chanakya *before* Unicode became the standard.  These PDFs *look* correct in a viewer but the underlying bytes are ASCII — not Devanagari.  When you extract text with any standard library (`pypdf`, `pdfplumber`, `pdfminer`) you get gibberish like `osQ kjk Fk Hk`.

This toolkit detects that situation and applies a character-level reverse-mapping to give you usable Hindi text.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **Conversion is ~85-92% accurate** | KrutiDev glyph mapping is context-free. Some characters (e.g. `k`) can be the `ा` matra *or* part of a consonant cluster. Perfect accuracy requires a context-aware parser or an LLM correction pass. |
| **PDF fonts are NOT re-encoded** | `split_pdf()` copies pages byte-for-byte. The output PDFs will still render correctly in viewers, but the underlying bytes remain in the legacy encoding. Use `extract_unicode_text()` when you need the text, not the file. |
| **Chanakya support is partial** | The Chanakya mapping covers the most common characters. Documents using uncommon ligatures or regional variants may need manual review. |

---

## Installation

```bash
# Core (PDF splitting + text extraction)
pip install lipi

# With PyMuPDF for better font-name-based extraction
pip install "lipi[fitz]"

# With Flask web UI
pip install "lipi[flask]"

# Development
pip install "lipi[dev]"
```

Or clone and install in editable mode:

```bash
git clone https://github.com/aparsoft/lipi.git
cd lipi
pip install -e ".[dev]"
```

---

## Quick Start

### Extract Unicode text from a Hindi PDF

```python
from lipi import HindiPreprocessor

# Convert raw KrutiDev text
unicode_text = HindiPreprocessor.convert("osQ kjk Fk", font_type="krutidev")
print(unicode_text)  # के ारा थ

# Auto-detect and convert
result = HindiPreprocessor.correct_hindi_text("eSaus gSjku gksdj ns[kk")
```

### Extract from a PDF

```python
from lipi.extractor import extract_unicode_text

result = extract_unicode_text("old_hindi_textbook.pdf")
print(result["has_encoding_issues"])   # True
print(result["detected_font_type"])    # "krutidev"
print(result["full_text"][:500])       # Clean Devanagari Unicode
```

### Split a PDF

```python
from lipi.splitter import PDFSplitter

PDFSplitter.split_pdf(
    input_file  = "hindi_science_class10.pdf",
    output_dir  = "chapters/",
    page_ranges = [
        (1,  18, "Chapter1_ChemicalReactions"),
        (19, 40, "Chapter2_Acids"),
        (41, 65, "Chapter3_Metals"),
    ],
    prefix    = "HindiPDF_Sci10",
    unit_name = "Science",
)
```

### Detect encoding

```python
from lipi import HindiPreprocessor

has_issues, font_type = HindiPreprocessor.detect_encoding(raw_text)
# → (True, "krutidev")
```

---

## CLI

```bash
# Extract text from a PDF
lipi extract hindi.pdf

# Extract with JSON output
lipi extract hindi.pdf --json

# Extract specific pages
lipi extract hindi.pdf --page-range 1-10

# Split a PDF
lipi split book.pdf --ranges "1-20:Ch1,21-45:Ch2" --output-dir chapters/

# Show PDF info
lipi info hindi.pdf
```

---

## Flask Web UI

```bash
pip install "lipi[flask]"
python web/flask_app.py
# → http://localhost:5000
```

Features:
- Upload & preview PDF info (page count, size, encoding detection)
- Single PDF splitting with named ranges
- Batch directory processing with JSON config
- Hindi text extraction with before/after preview
- JSON config editor
- Output file browser with download/delete

---

## Project structure

```
lipi/
├── src/lipi/
│   ├── __init__.py              # Public API (HindiPreprocessor)
│   ├── preprocessor.py          # Convert + detect + post-process
│   ├── extractor.py             # PDF text extraction (pypdf + optional fitz)
│   ├── splitter.py              # PDF splitting + batch processing
│   ├── cli.py                   # Command-line interface
│   ├── _quality.py              # Garbage text detection
│   └── mappings/
│       ├── __init__.py          # FONT_MAPPINGS merged dict
│       ├── krutidev.py          # KrutiDev → Unicode base table
│       ├── chanakya.py          # Chanakya → Unicode table
│       └── walkman_chanakya.py  # Walkman-Chanakya905 overrides
├── web/
│   ├── flask_app.py             # Flask web UI
│   └── templates/               # HTML templates
├── tests/
│   ├── test_mappings.py
│   ├── test_preprocessor.py
│   ├── test_extractor.py
│   └── test_splitter.py
├── pyproject.toml
└── README.md
```

---

## How the Hindi encoding fix works

```
PDF file (KrutiDev font)
        |
        v
pypdf.extract_text()   <- returns garbled ASCII: "osQ kjk Fk dj jgk gS"
        |
        v
detect_encoding()  <- heuristic: low Devanagari ratio + KrutiDev fingerprints
        |
        v
convert()   <- longest-match-first substitution using char mapping table
        |
        v
post_process()  <- removes doubled matras, fixes common word errors
        |
        v
Unicode text: "के ारा थ कर रहा है"  <- ~85-92% accuracy
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding font mappings and contributing code.

### Development setup

```bash
git clone https://github.com/aparsoft/lipi.git
cd lipi
pip install -e ".[dev]"
pytest
```

---

## Acknowledgements

- Built on [`pypdf`](https://github.com/py-pdf/pypdf) for PDF manipulation
- KrutiDev mapping tables cross-referenced against community resources at [rajbhasha.net](https://rajbhasha.net)
- Inspired by countless developers who hit the "Hindi PDF gibberish" problem on GitHub Issues and Stack Overflow

---

## License

MIT © [Aparsoft Private Limited](https://aparsoft.in)

---

*Aparsoft builds AI-powered EdTech tools for Indian schools and students. Our flagship product [Apar AI LMS](https://aparsoft.in) delivers Hindi curriculum-aligned content to schools across India. This toolkit is part of our internal content processing pipeline, open-sourced for the community.*
