# PDF Cutter Service

A Python tool to split PDF files into separate documents based on page ranges. Includes a background service with an HTTP API and a Flask web UI.

## Features

- **PDF Splitting** -- Split PDFs by page ranges with custom output naming
- **Batch Processing** -- Process multiple PDFs at once using a JSON configuration file
- **Directory Watcher** -- Automatically process new PDFs dropped into a watched folder
- **HTTP API** -- Programmatic access via a lightweight REST API
- **Flask Web UI** -- Browser-based interface for uploading, splitting, batch processing, and editing configs
- **Hindi Text Encoding** -- Detects and attempts to fix Kruti Dev / Chanakya encoded Hindi text in PDFs

## Requirements

- Python 3.9+

### Install dependencies

```bash
pip install -r requirements.txt
```

Core packages: `Flask`, `pypdf`, `requests`, `watchdog`, `tqdm`, `indic-transliteration`.

## Quick Start

### 1. Start the Flask web app (recommended)

```bash
python flask_app.py
```

Open http://127.0.0.1:5000 in your browser. From the sidebar you can start the background PDF Cutter Service which provides the actual splitting backend on port 8111.

### 2. Start the service standalone (CLI / API only)

```bash
# API-only mode
python pdf_cutter_service.py --output-dir ./output --port 8111

# Watch a directory for new PDFs + use a config file
python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json

# Combine both
python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json --port 8111
```

### 3. Streamlit app (alternative UI)

```bash
streamlit run streamlit_app.py
```

> **Note:** The Streamlit app still uses `PyPDF2`. It works but the Flask app is the recommended interface.

## Using the Flask Web UI

1. **Start the service** from the sidebar (set output directory and port, then click *Start Service*).
2. Navigate to one of:
   - **Single PDF Splitter** -- Upload a PDF, define page ranges, split.
   - **Batch Processing** -- Point at a directory of PDFs + a config JSON, process all at once.
   - **Configuration Editor** -- Create / edit config files visually.

## HTTP API

Once the service is running (default port **8111**):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/status` | Service status (JSON) |
| `GET`  | `/help`   | Help text |
| `POST` | `/split`  | Split a PDF |
| `POST` | `/correct_text` | Correct Hindi text encoding |

### Split example

```bash
curl -X POST "http://localhost:8111/split?input_file=example.pdf&ranges=1-5:Part1,6-10:Part2&output_dir=output"
```

**Parameters:**
- `input_file` (required) -- Path to the input PDF
- `ranges` (required) -- Page ranges, e.g. `1-10:Intro,11-20:Chapter1`
- `output_dir` -- Output directory (default: `output`)
- `prefix` -- Filename prefix
- `unit_name` -- Unit name for filenames
- `fix_encoding` -- `true`/`false`, attempt Hindi encoding fix (default: `true`)

## Configuration File

The config file (`config.json`) maps PDF filenames (or patterns) to splitting rules:

```json
{
  "default": {
    "page_ranges": [
      { "start": 1, "end": 5, "name": "Introduction" },
      { "start": 6, "end": 15, "name": "MainContent" }
    ],
    "unit_name": "DefaultUnit",
    "prefix": "NCERT"
  },
  "english_textbook": {
    "page_ranges": [
      { "start": 1, "end": 10, "name": "Chapter1" },
      { "start": 11, "end": 25, "name": "Chapter2" }
    ],
    "unit_name": "English",
    "prefix": "Class6"
  },
  "^chapter(\\d+)$": {
    "page_ranges": [
      { "start": 1, "end": 5, "name": "Introduction" }
    ],
    "unit_name": "PatternMatched",
    "prefix": "NCERT"
  }
}
```

- **`default`** -- Applied when no specific match is found
- **Exact name** (e.g. `english_textbook`) -- Matches the PDF filename (without `.pdf`)
- **Regex pattern** (e.g. `^chapter(\d+)$`) -- Matches filenames via regex

## Output Naming

Files are named: `[prefix]_[unit_name]_[name].pdf`

Example: prefix=`Class6`, unit_name=`English`, name=`Chapter1` → `Class6_English_Chapter1.pdf`

## Project Structure

```
flask_app.py             # Flask web application
pdf_cutter_service.py    # Core service (splitting, API, watcher)
streamlit_app.py         # Alternative Streamlit UI
config.json              # Sample configuration file
requirements.txt         # Python dependencies
templates/               # Jinja2 HTML templates for Flask
  layout.html            # Base layout with sidebar
  index.html             # Home page
  single_pdf.html        # Single PDF splitter page
  batch_process.html     # Batch processing page
  config_editor.html     # Config editor page
output/                  # Default output directory
temp/                    # Temporary upload directory
```

## Troubleshooting

- **Service not starting?** Make sure the port isn't already in use. Change it in the sidebar or via `--port`.
- **PDF errors?** Verify the PDF isn't password-protected or corrupted.
- **Missing directories?** The app auto-creates `output/` and `temp/` on startup.
- **Streamlit issues?** Use the Flask app instead -- it has fewer dependencies and works with current Python/NumPy versions.
