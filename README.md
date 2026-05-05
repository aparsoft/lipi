# Lipi

> **Part of the [Aparsoft](https://aparsoft.com) open-source EdTech toolchain**
> Built for the [Apar Academy](https://aparacademy.com) Hindi PDF content ingestion pipeline - open-sourced for the Indian EdTech community.

[![PyPI](https://img.shields.io/pypi/v/lipi-aparsoft)](https://pypi.org/project/lipi-aparsoft/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-100%20passing-brightgreen)](https://github.com/aparsoft/lipi)

---

## Decode legacy Hindi PDFs and clean noisy extracted text. KrutiDev, Chanakya, scrambled Devanagari → Unicode.

## What this does

1. **Split PDFs by page range** - extract chapters, lectures, or units out of a large PDF into separate files, with optional batch processing via a JSON config.

2. **Extract and normalize Hindi PDF text** - detect KrutiDev / Chanakya encoded PDFs, handle `scrambled_devanagari` Unicode extraction artefacts, and produce cleaner Unicode Devanagari that is searchable, copy-pasteable, and usable in NLP pipelines.

3. **Safer second-stage correction modes** - use `safe` exact normalized corrections for bulk cleanup, or `aggressive` bounded fuzzy correction when you are reviewing output more closely.

4. **Clean already-extracted raw text** - if the PDF is gone and you only have noisy text in a database / JSON / CSV dump, reuse the same cleanup stack directly on that text.

5. **Use a smarter web extractor UI** - the Flask app shows raw-vs-cleaned comparison for Hindi extraction when it is meaningful, but keeps English / Latin chunks in a neutral single extracted-text view.

### Common use cases

- **Educational textbook ingestion**: split books chapter-wise, extract text, and normalize Hindi into searchable Unicode.
- **Already-extracted corpus cleanup**: repair noisy Hindi text already stored in a database, JSONL file, spreadsheet export, or search index without reopening the PDFs.
- **RAG / search preprocessing**: clean chapter text before chunking for embeddings, keyword search, question answering, or summarization.
- **Corpus QA and triage**: flag `scrambled_devanagari` pages, count extraction artefacts, and route only the worst pages for human review or a later LLM pass.
- **Migration of legacy content archives**: batch-convert old KrutiDev / Chanakya learning materials into Unicode Devanagari before re-publishing or analytics.

### Why this exists

Old legacy Hindi textbooks, state board materials, government circulars, and Hindi newspapers were typeset in **glyph-substitution fonts** like KrutiDev and Chanakya *before* Unicode became the standard.  These PDFs *look* correct in a viewer but the underlying bytes are ASCII - not Devanagari.  When you extract text with any standard library (`pypdf`, `pdfplumber`, `pdfminer`) you get gibberish like `osQ kjk Fk Hk`.

This toolkit detects that situation and applies a character-level reverse-mapping to give you usable Hindi text.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **Conversion is ~85-92% accurate** | KrutiDev glyph mapping is context-free. Some characters (e.g. `k`) can be the `ा` matra *or* part of a consonant cluster. Perfect accuracy requires a context-aware parser or an LLM correction pass. |
| **PDF fonts are NOT re-encoded** | `split_pdf()` copies pages byte-for-byte. The output PDFs will still render correctly in viewers, but the underlying bytes remain in the legacy encoding. Use `extract_unicode_text()` when you need the text, not the file. |
| **Chanakya support is partial** | The Chanakya mapping covers the most common characters. Documents using uncommon ligatures or regional variants may need manual review. |
| **Safe mode is intentionally conservative** | `clean_extracted_text(..., correction_mode="safe")` prefers exact normalized matches and is designed to avoid rewriting one valid Hindi word into another. Some noisy tokens are intentionally left untouched until a stronger exact signal exists. |
| **Aggressive correction is heuristic** | The bounded fuzzy pass can improve messy output, but it should be reviewed on important documents or high-value publishing flows. |

---

## Installation

```bash
# Core (PDF splitting + text extraction)
pip install lipi-aparsoft

# With Flask web UI
pip install "lipi-aparsoft[flask]"

# Development
pip install "lipi-aparsoft[dev]"
```

Or clone and install in editable mode:

```bash
git clone https://github.com/aparsoft/lipi.git
cd lipi
pip install -e ".[dev]"
```

> **Note:** The PyPI distribution name is `lipi-aparsoft`, but the Python import name remains `lipi`:
> ```python
> from lipi import HindiPreprocessor  # import name is always 'lipi'
> ```

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

# Optional second-stage lexicon correction for legacy or scrambled Hindi PDFs
improved = extract_unicode_text(
        "old_hindi_textbook.pdf",
        second_stage="lexicon",
)
print(improved["correction_stats"])
```

### Clean already-extracted raw text (no PDF required)

```python
from lipi import clean_extracted_text

raw_text = """भाषा संंगम\nशब््दोों की सूची"""

result = clean_extracted_text(
        raw_text,
        correction_mode="safe",  # recommended default for bulk corpora
)

print(result["detected_font_type"])      # "unknown" or "scrambled_devanagari"
print(result["artifact_count_before"])   # e.g. 6
print(result["artifact_count_after"])    # e.g. 2
print(result["cleaned_text"])
```

### Batch-clean a corpus you already extracted

```python
from lipi import clean_extracted_text

pages = [
        {"doc_id": "book-1", "page": 1, "raw_text": "..."},
        {"doc_id": "book-1", "page": 2, "raw_text": "..."},
        {"doc_id": "book-1", "page": 3, "raw_text": "..."},
]

context_texts = [page["raw_text"] for page in pages]

for page in pages:
        result = clean_extracted_text(
                page["raw_text"],
                correction_mode="safe",
                contextual_texts=context_texts,
                bootstrap_lexicon=True,
        )
        page["cleaned_text"] = result["cleaned_text"]
        page["artifacts_removed"] = result["artifacts_removed"]
```

This is the intended path when you already have text for lakhs of PDFs and want a safer first-pass cleanup without reopening each source file.

### Choose a correction mode

- `none`: only conversion + Unicode cleanup. Best when you want zero lexicon intervention.
- `safe`: exact normalized lexicon matches only. Recommended default for large-scale corpora.
- `aggressive`: bounded fuzzy correction. Useful for review queues and experiments, but inspect the output.

### Run the regression harness over real samples

```python
from lipi.regression import run_regression_harness

report = run_regression_harness([
        "temp/jhkr102.pdf",
        "temp/ihkr101.pdf",
])
print(report["improved_pages"])
print(report["average_quality_delta"])
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

# Extract with optional second-stage lexicon correction
lipi extract hindi.pdf --second-stage lexicon

# Extract with JSON output
lipi extract hindi.pdf --json

# Extract specific pages
lipi extract hindi.pdf --page-range 1-10

# Split a PDF
lipi split book.pdf --ranges "1-20:Ch1,21-45:Ch2" --output-dir chapters/

# Show PDF info
lipi info hindi.pdf

# Benchmark one or more PDFs page-by-page
lipi regress temp/jhkr102.pdf temp/ihkr101.pdf

# Opt in to a more aggressive contextual lexicon built from repeated clean tokens
lipi regress temp/jhkr102.pdf --bootstrap-lexicon
```

For already-extracted text, use `clean_extracted_text()` from Python and run it over your existing JSON / CSV / DB records.

---

## Flask Web UI

```bash
pip install "lipi-aparsoft[flask]"
python web/flask_app.py
# → http://localhost:5000
```

Features:
- Upload & preview PDF info (page count, size, encoding detection)
- Single PDF splitting with named ranges
- Batch directory processing with JSON config
- Hindi text extraction with smart presentation: raw-vs-cleaned comparison for Hindi legacy/scrambled pages, and a neutral single extracted-text view for English / Latin chunks
- Conversion summary badges (legacy detected, text changed, etc.)
- JSON config editor
- Output file browser with download/delete

Single-PDF extraction behavior:
- Legacy or scrambled Hindi pages: show exact raw `pypdf` output first, then the cleaned `lipi-aparsoft` output.
- English / Latin chunks: keep the direct `pypdf` extraction and suppress fake KrutiDev / Chanakya conversion framing.

---

## Project structure

```
lipi/
├── src/lipi/
│   ├── __init__.py              # Public API: HindiPreprocessor, HindiLexiconCorrector, run_regression_harness
│   ├── preprocessor.py          # Convert + detect + post-process
│   ├── extractor.py             # PDF text extraction (pypdf) + optional lexicon stage
│   ├── correction.py            # HindiLexiconCorrector (bounded Levenshtein, suspicious-token heuristics)
│   ├── text_pipeline.py         # Clean already-extracted raw text (safe/aggressive modes)
│   ├── regression.py            # Page-by-page quality harness with quality metrics
│   ├── splitter.py              # PDF splitting + batch processing
│   ├── cli.py                   # Command-line interface (extract, split, info, regress)
│   ├── _quality.py              # Garbage text detection (character ratio analysis)
│   ├── _lexicon.py              # Bundled Hindi word list (~300+ words)
│   └── mappings/
│       ├── __init__.py          # FONT_MAPPINGS merged dict
│       ├── krutidev.py          # KrutiDev → Unicode base table
│       ├── chanakya.py          # Chanakya → Unicode table
│       └── walkman_chanakya.py  # Walkman-Chanakya905 overrides
├── web/
│   ├── flask_app.py             # Flask web UI (smart extraction comparison + English chunk fallback)
│   └── templates/               # HTML templates
├── tests/
│   ├── test_mappings.py         # Mapping tables: loading, merging, value validation
│   ├── test_preprocessor.py     # Detection, conversion, i-matra reorder, post-process repairs
│   ├── test_extractor.py        # Quality gate, file-not-found, generic cleanup on non-legacy PDFs
│   ├── test_correction.py       # Lexicon corrector: token correction, suspicious token detection
│   ├── test_regression.py       # Quality metrics: quality_index, lexicon_hit_rate, artifact counts
│   ├── test_splitter.py         # Parse ranges, config validation, split files, PDF info
│   └── test_flask_app.py        # Flask route tests
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
detect_encoding()      <- heuristic: low Devanagari ratio + KrutiDev fingerprints
        |
        v
convert()              <- longest-match-first substitution using char mapping table
        |
        v
post_process()         <- generic Unicode cleanup:
                           - remove doubled matras (ाा→ा)
                           - fix mark-spacing (consonant SPACE matra → consonant+matra)
                           - fix halant-spacing (् SPACE consonant → ्consonant)
                           - fix duplicate consonant+i-matra (कक→कि, ववक→विक)
                           - fix श्श्ि → श्चि
                           - fix decomposed nukta+i (डड़→ड़ि)
                           - collapse duplicated auxiliaries (हैहै→है)
                           - fix common words (अौर→और, अार→आर)
        |
        v
lexicon second stage   <- optional for legacy or scrambled Hindi PDF paths:
  (HindiLexiconCorrector)
                           - split text into tokens
                           - detect suspicious tokens (nonstandard nukta, duplicate marks)
                           - find closest lexicon match via bounded Levenshtein
                           - only replace if distance ≤ 2 and match is strong
        |
        v
Unicode text: "के ारा थ कर रहा है"  <- ~85-92% accuracy (improves with lexicon stage)
```

## Raw text pipeline

When you no longer have the PDF and only have extracted text, the pipeline is simpler:

```text
raw extracted text
        |
        v
detect_encoding() / detect_scrambled_devanagari()
        |
        v
post_process()       <- remove duplicate marks, repair spacing, strip control chars
        |
        v
lexicon stage        <- optional: safe or aggressive
        |
        v
cleaned Hindi text + diagnostics (artifacts removed, correction stats)
```

This is exactly what `clean_extracted_text()` wraps.

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

> **Install from PyPI:** `pip install lipi-aparsoft`
> **Python import:** `from lipi import HindiPreprocessor` (import name is `lipi`, not `lipi-aparsoft`)

---

## Acknowledgements

- Built on [`pypdf`](https://github.com/py-pdf/pypdf) for PDF manipulation
- KrutiDev mapping tables cross-referenced against community resources at [rajbhasha.net](https://rajbhasha.net)
- Inspired by countless developers who hit the "Hindi PDF gibberish" problem on GitHub Issues and Stack Overflow

---

## License

MIT © [Aparsoft Private Limited](https://aparsoft.com)

---

*Aparsoft builds AI-powered EdTech tools for Indian schools and students. Our flagship product [Apar AI LMS](https://aparailms.com) delivers Hindi curriculum-aligned content to schools across India. This toolkit is part of our internal content processing pipeline, open-sourced for the community.*
