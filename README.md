# Aparsoft PDF Tools

> **Part of the [Aparsoft](https://aparsoft.in) open-source EdTech toolchain**  
> Built for the [Apar Academy](https://aparacademy.in) NCERT content pipeline — open-sourced for the Indian EdTech community.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-orange)](https://github.com/aparsoft/aparsoft-pdf-tools)

---

## What this does

Two things — and only those two things, done well:

1. **Split PDFs by page range** — extract chapters, lectures, or units out of a large PDF into separate files, with optional batch processing via a JSON config.

2. **Extract Unicode text from legacy Hindi-font PDFs** — detect KrutiDev / Chanakya / DevLys encoded PDFs and convert the extracted text to proper Unicode Devanagari, making it searchable, copy-pasteable, and usable in NLP pipelines.

### Why this exists

Old NCERT textbooks, state board materials, government circulars, and Hindi newspapers were typeset in **glyph-substitution fonts** like KrutiDev and Chanakya *before* Unicode became the standard.  These PDFs *look* correct in a viewer but the underlying bytes are ASCII — not Devanagari.  When you extract text with any standard library (`pypdf`, `pdfplumber`, `pdfminer`) you get gibberish like `osQ kjk Fk Hk`.

This toolkit detects that situation and applies a character-level reverse-mapping to give you usable Hindi text.

---

## ⚠️ Known Limitations (read before raising issues)

| Limitation | Detail |
|---|---|
| **Conversion is ~85–92 % accurate** | KrutiDev glyph mapping is context-free. Some characters (e.g. `k`) can be the `ा` matra *or* part of a consonant cluster. Perfect accuracy requires a context-aware parser or an LLM correction pass. |
| **PDF fonts are NOT re-encoded** | `split_pdf()` copies pages byte-for-byte. The output PDFs will still render correctly in viewers, but the underlying bytes remain in the legacy encoding. Use `extract_unicode_text()` when you need the text, not the file. |
| **Chanakya support is partial** | The Chanakya mapping covers the most common characters. Documents using uncommon ligatures or regional variants may need manual review. |
| **DevLys / Shusha / Walkman** | Not yet supported. PRs welcome. |

---

## Installation

```bash
# Core (PDF splitting + text extraction)
pip install aparsoft-pdf-tools

# With Flask web UI
pip install "aparsoft-pdf-tools[flask]"

# With better Hindi transliteration (recommended)
pip install "aparsoft-pdf-tools[indic]"

# Everything
pip install "aparsoft-pdf-tools[all]"
```

Or clone and install in editable mode:

```bash
git clone https://github.com/aparsoft/aparsoft-pdf-tools.git
cd aparsoft-pdf-tools
pip install -e ".[all]"
```

---

## Quick Start

### Split a PDF

```python
from pdf_cutter_service import PDFCutterService

svc = PDFCutterService()

# Split a textbook into chapters
svc.split_pdf(
    input_file  = "ncert_science_class10.pdf",
    output_dir  = "chapters/",
    page_ranges = [
        (1,  18, "Chapter1_ChemicalReactions"),
        (19, 40, "Chapter2_Acids"),
        (41, 65, "Chapter3_Metals"),
    ],
    prefix    = "NCERT_Sci10",
    unit_name = "Science",
)
# → chapters/NCERT_Sci10_Science_Chapter1_ChemicalReactions.pdf
# → chapters/NCERT_Sci10_Science_Chapter2_Acids.pdf
# → ...
```

### Extract Unicode text from a Hindi PDF

```python
from pdf_cutter_service import PDFCutterService

svc = PDFCutterService()
result = svc.extract_unicode_text("old_hindi_textbook.pdf")

print(result["has_encoding_issues"])   # True
print(result["detected_font_type"])    # "krutidev"
print(result["full_text"][:500])       # Clean Devanagari Unicode ✓

# Access page-by-page
for page_num, text in result["pages"].items():
    print(f"Page {page_num}:\n{text}\n")
```

### Detect encoding issues without converting

```python
from pdf_cutter_service import PDFCutterService

has_issues, font_type = PDFCutterService.detect_encoding_issues(raw_text)
# → (True, "krutidev")
```

### Batch extract from a directory

```python
results = svc.batch_extract_unicode_text("./hindi_pdfs/")
for r in results:
    print(r["filename"], "→", r["detected_font_type"])
    # Save unicode text somewhere useful
    with open(f"unicode/{r['filename']}.txt", "w") as f:
        f.write(r["full_text"])
```

---

## CLI (command line)

```bash
# Start the HTTP API service (watches a directory + exposes REST endpoints)
aparsoft-pdf --watch-dir ./input --output-dir ./output --config config.json

# API-only mode on a specific port
aparsoft-pdf --output-dir ./output --port 8111
```

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Service health and stats |
| `GET` | `/help` | Endpoint reference |
| `POST` | `/split` | Split a PDF (`input_file`, `ranges`, `output_dir`) |
| `POST` | `/extract_text` | Extract Unicode text (`pdf_path`, `font_type`) |
| `POST` | `/correct_text` | Convert raw KrutiDev text to Unicode |

```bash
# Example: split via curl
curl -X POST "http://localhost:8111/split?input_file=book.pdf&ranges=1-20:Ch1,21-45:Ch2&output_dir=out"

# Example: extract text
curl -X POST "http://localhost:8111/extract_text?pdf_path=hindi.pdf&font_type=auto"
```

---

## Flask Web UI

```bash
python flask_app.py
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

## Batch config format

```json
{
  "ncert_hindi_class9": {
    "page_ranges": [
      { "start": 1,  "end": 20, "name": "Chapter1" },
      { "start": 21, "end": 45, "name": "Chapter2" },
      { "start": 46, "end": 70, "name": "Chapter3" }
    ],
    "prefix": "NCERT",
    "unit_name": "Hindi9"
  },
  "default": {
    "page_ranges": [
      { "start": 1, "end": 50, "name": "Part1" }
    ]
  }
}
```

- Key = PDF filename **without** extension, or a regex pattern (`^pattern$`), or `"default"`.
- `prefix` and `unit_name` are optional; they appear in the output filename.
- Output filename pattern: `{prefix}_{unit_name}_{name}.pdf`

---

## Project structure

```
aparsoft-pdf-tools/
├── pdf_cutter_service.py   # Core library + HTTP service + CLI
├── flask_app.py            # Flask web UI
├── pyproject.toml          # Package metadata
├── README.md
├── LICENSE
├── tests/
│   ├── test_splitting.py
│   ├── test_encoding.py
│   └── fixtures/
│       ├── sample_krutidev.pdf
│       └── sample_unicode.pdf
├── templates/              # Flask Jinja2 templates (not included in core)
│   ├── index.html
│   ├── single_pdf.html
│   ├── batch_process.html
│   └── config_editor.html
└── config.example.json
```

---

## How the Hindi encoding fix works

```
PDF file (KrutiDev font)
        │
        ▼
pypdf.extract_text()   ← returns garbled ASCII: "osQ kjk Fk dj jgk gS"
        │
        ▼
detect_encoding_issues()  ← heuristic: low Devanagari ratio + KrutiDev fingerprints
        │
        ▼
convert_to_unicode()   ← longest-match-first substitution using char mapping table
        │
        ▼
post_process_hindi_text()  ← removes doubled matras, fixes common word errors
        │
        ▼
Unicode text: "के ारा थ कर रहा है"  ← ~85–92% accuracy
```

For higher accuracy, pipe the output through an LLM correction step or `indic-transliteration`.

---

## Contributing

PRs are welcome, especially for:

- [ ] Improved KrutiDev mapping (context-aware parser)
- [ ] DevLys / Shusha / Walkman Chanakya support
- [ ] Test fixtures (sample PDFs with known encoding)
- [ ] Flask template HTML files
- [ ] CI/CD workflow (GitHub Actions)

### Development setup

```bash
git clone https://github.com/aparsoft/aparsoft-pdf-tools.git
cd aparsoft-pdf-tools
pip install -e ".[all,dev]"
pytest
```

---

## Acknowledgements

- Built on [`pypdf`](https://github.com/py-pdf/pypdf) for PDF manipulation
- [`indic-transliteration`](https://github.com/indic-transliteration/indic_transliteration_py) for optional HK-scheme conversion
- KrutiDev mapping tables cross-referenced against community resources at [rajbhasha.net](https://rajbhasha.net)
- Inspired by countless developers who hit the "Hindi PDF gibberish" problem on GitHub Issues and Stack Overflow

---

## License

MIT © [Aparsoft Private Limited](https://aparsoft.in)

---

*Aparsoft builds AI-powered EdTech tools for Indian schools and students. Our flagship product [Apar AI LMS](https://aparsoft.in) delivers NCERT-aligned content to schools across India. This toolkit is part of our internal content processing pipeline, open-sourced for the community.*