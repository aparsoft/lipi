# Contributing to Lipi

Thank you for your interest in improving Lipi!

## How to add a new font mapping

1. Create a new file in `src/lipi/mappings/` (e.g. `devlys.py`).
2. Define a dict mapping legacy font characters to Unicode Devanagari:

```python
# src/lipi/mappings/devlys.py
"""DevLys -> Unicode Devanagari mapping table."""

DEVLYS_TO_UNICODE: dict[str, str] = {
    "v": "\u0905",  # अ
    # ... more entries
}
```

3. Import and register it in `src/lipi/mappings/__init__.py`:

```python
from lipi.mappings.devlys import DEVLYS_TO_UNICODE

FONT_MAPPINGS["devlys"] = DEVLYS_TO_UNICODE
```

4. Add detection fingerprints in `src/lipi/preprocessor.py` if needed.
5. Write tests in `tests/test_mappings.py`.

## Development setup

```bash
git clone https://github.com/aparsoft/lipi.git
cd lipi
pip install -e ".[dev]"
pytest
```

> **Install from PyPI:** `pip install lipi-aparsoft`  
> **Python import:** `from lipi import HindiPreprocessor` (import name is `lipi`, not `lipi-aparsoft`)

## Pull request guidelines

- Keep PRs focused on a single change.
- Add tests for any new functionality.
- Run `pytest` and ensure all tests pass before submitting.
- Follow the existing code style (line length 100, Black formatting).

## Reporting issues

Please include:
- Python version
- A sample PDF or text that demonstrates the issue
- Expected vs actual output

## Areas that need help

- Context-aware KrutiDev parser (higher conversion accuracy)
- DevLys / Shusha font support
- Test fixtures (sample PDFs with known encoding)
- CI/CD workflow
