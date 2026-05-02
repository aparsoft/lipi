# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] - 2025-05-01

### Added
- Restructured from flat `pdf_service` into `src/lipi/` package layout.
- `lipi.preprocessor.HindiPreprocessor` — convert KrutiDev/Chanakya to Unicode.
- `lipi.extractor.extract_unicode_text()` — PDF text extraction with auto-conversion.
- `lipi.splitter.PDFSplitter` — PDF splitting and batch directory processing.
- `lipi.cli` — `lipi extract`, `lipi split`, `lipi info` commands.
- `lipi._quality.is_garbage_text()` — text quality gate for extraction results.
- `lipi.mappings` — split mapping tables: krutidev, chanakya, walkman_chanakya.
- `web/flask_app.py` — Flask web UI using lipi package.
- Backward-compat shims for `hindi_preprocessor.py` and `pdf_cutter_service.py`.
- 71 unit tests covering mappings, preprocessor, extractor, and splitter.
- Walkman-Chanakya905 font support (multi-char tokens + single-char overrides).

### Changed
- Package name: `aparsoft-pdf-tools` → `lipi`.
- Entry point: `aparsoft-pdf` → `lipi`.
- Core dependency: only `pypdf>=4.0` (watchdog/tqdm moved to `[flask]` extra).
- `.gitignore`: removed `tests/` from ignore list.

### Removed
- `indic_pdf_extractor.py` async/LangChain code (only `_is_garbage_text()` retained).
- `fix_encoding()` invisible annotation approach (removed in prior version).
- Dead code: `_IMATRA_REORDER_REPL`, `_IMATRA_ANUSVARA_REORDER_REPL`.
