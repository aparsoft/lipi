# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [1.0.9] - 2026-05-05

### Added
- Added an opt-in candidate-generator pipeline in `lipi.candidates` so token rules can emit multiple repair candidates and let a scorer choose the winner instead of destructively rewriting text in place.
- Added `SymSpellHindiCorrector` in `lipi.symspell_corrector` for frequency-weighted corpus-scale correction, plus optional `symspell` installation extras.
- Added optional KenLM character-language-model support in `lipi.lm` for tie-breaking near-equal candidates, plus `lm` installation extras.
- Added a multiprocessing corpus cleaner in `lipi.batch` and a new `lipi correct-corpus` CLI flow for batch-cleaning directories of pre-extracted text into JSONL output.
- Added an optional transformer fallback in `lipi.ml_fallback` for the last low-confidence correction tier, plus `ml` installation extras.
- Added corpus tooling for production workflows: `tools/build_frequency_lexicon.py` to build frequency dictionaries and `tools/train_kenlm.py` to train a Hindi character LM.
- Added focused tests for candidate generation, corpus CLI flow, and SymSpell-backed correction.

### Changed
- Expanded Lipi from a PDF/text cleanup toolkit into a more scalable Hindi corpus-correction stack with layered correction options for lakhs of extracted files.
- Kept the existing `clean_extracted_text()` path as the cheap default while documenting and exposing heavier opt-in layers for throughput, tie-breaking, and last-resort recovery.
- Refreshed the README to document the new large-corpus flow, optional extras, `correct-corpus` CLI command, and recommended layer-by-layer rollout strategy.

### Fixed
- Reduced the need for destructive regex-only correction by introducing candidate scoring and opt-in external signals, which gives production pipelines a safer path for large-scale fuzzy cleanup.

## [1.0.7] - 2026-05-05

### Added
- Added Single PDF web extraction behavior for English / Latin chunks so the Flask UI can show a neutral extracted-text view instead of pretending a KrutiDev or Chanakya conversion happened.
- Added focused Flask route coverage for the English / Latin extraction path in addition to the existing legacy and scrambled-Devanagari tests.

### Changed
- `HindiPreprocessor.post_process()` now collapses duplicated auxiliary forms such as `हैहै -> है` and `थाथा -> था` when they appear as standalone token duplication artefacts.
- Refreshed the README to document the broader Hindi ETL pipeline, safe versus aggressive cleanup, scrambled Devanagari handling, and the smarter web UI extraction behavior.

### Fixed
- Fixed the Flask extraction UI so English PDFs no longer show misleading legacy-font badges or bogus lipi-aparsoft conversion framing.
- Fixed duplicated auxiliary cleanup around Hindi danda punctuation so cases such as `हैहै।` normalize correctly.

## [1.0.6] - 2026-05-05

### Added
- Added `clean_extracted_text()` so already-extracted Hindi text can be cleaned without reopening the original PDFs, with `safe`, `aggressive`, and optional contextual lexicon bootstrapping modes.
- Added `scrambled_devanagari` detection and artifact diagnostics for Unicode-looking PDF text that is still corrupted by broken extraction.
- Added broader textbook and prose Hindi lexicon coverage plus new regression tests for raw-text cleanup, exact-match repairs, and false-positive prevention.

### Changed
- Expanded the package from a PDF-only converter into a more general Hindi ETL cleanup pipeline for both PDF extraction output and existing raw text corpora.
- Safe cleanup now prefers exact normalized repairs for scrambled Devanagari noise, including repeated consonants, repeated halants, common `ज`/`ि` swap corruption, and tightly scoped stray `ि` repair.
- Generic post-processing now cleans more Unicode extraction artefacts before lexicon correction, including duplicated auxiliary forms such as `हैहै -> है`.
- Local demo and test paths now resolve the checkout `src/` tree consistently, so validation runs against the current code instead of a stale installed wheel.

### Fixed
- Fixed false-positive safe corrections where one valid Hindi word could be rewritten to another valid Hindi word, including cases such as `व्यक्ति -> व्यक्त` and `बिना -> बना`.
- Prevented unsafe fuzzy jumps on structurally corrupted tokens unless an exact normalized lexicon candidate exists.
- Fixed raw-text demo reporting so correction samples and cleaned output reflect the actual pipeline behavior.

## [1.0.2] - 2026-05-02

### Changed
- Made the Flask single-PDF extractor explicitly show the exact raw `pypdf` extraction alongside the `lipi-aparsoft` Unicode output for easier demos and screencasts.
- Added extraction comparison metadata so the UI can state whether `lipi-aparsoft` actually changed the text or intentionally left the raw extraction unchanged.
- Applied generic Unicode cleanup even when a page is already Devanagari and legacy-font detection is `unknown`, so broken `pypdf` output is still improved.

### Added
- Focused Flask route tests covering legacy PDFs that do change and non-legacy PDFs that intentionally remain unchanged.
- Added `compare_extraction_dump.py` to dump raw `pypdf` output and `lipi-aparsoft` output into separate text files for manual inspection.

## [1.0.1] - 2025-05-02

### Fixed
- Updated PUBLISHING.md with complete release workflow and version bump requirements.
- Documented PyPI "file already exists" error and prevention strategy.

## [1.0.0] - 2025-05-01

### Changed
- PyPI distribution name changed from `lipi` to `lipi-aparsoft` (name was taken on PyPI).
  Install with `pip install lipi-aparsoft`; Python import name remains `lipi` (unchanged).

### Added
- Restructured from flat `pdf_service` into `src/lipi/` package layout.
- `lipi.preprocessor.HindiPreprocessor` — convert KrutiDev/Chanakya to Unicode.
- `lipi.extractor.extract_unicode_text()` — PDF text extraction with auto-conversion.
- `lipi.splitter.PDFSplitter` — PDF splitting and batch directory processing.
- `lipi.cli` — `lipi extract`, `lipi split`, `lipi info` commands.
- `lipi._quality.is_garbage_text()` — text quality gate for extraction results.
- `lipi.mappings` — split mapping tables: krutidev, chanakya, walkman_chanakya.
- `web/flask_app.py` — Flask web UI using lipi package.
- Backward-compat shims for `hindi_preprocessor.py` and `pdf_service.py`.
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
