# PDF Cutter Service and App

This is an enhanced version of the PDF cutter tool, with a service component that can run independently and web applications for a user-friendly interface.

## Features

- **PDF Cutter Service**: A background service that can:
  - Split PDFs based on page ranges
  - Watch directories for new PDFs to process automatically
  - Provide an HTTP API for programmatic access
  - Run independently via command line

- **Web Applications**: Choose between two user-friendly interfaces:
  - **Flask App**: Compatible with NumPy 2.0 and newer Python versions
  - **Streamlit App** (requires NumPy<2.0): Rich interactive interface

Both interfaces allow you to:
  - Split individual PDFs with custom page ranges
  - Batch process multiple PDFs with a configuration file
  - Create and edit configuration files through a visual editor
  - Manage and monitor the PDF Cutter Service

## Installation

### Prerequisites

Make sure you have Python 3.7+ installed. Then install the required dependencies:

```bash
# For Flask app (compatible with NumPy 2.0)
pip install flask PyPDF2 requests werkzeug watchdog

# For Streamlit app (requires NumPy<2.0)
pip install streamlit PyPDF2 watchdog tqdm
```

### Quick Start

1. Choose your preferred interface:

   - **For Flask app** (recommended, works with NumPy 2.0):
     ```
     start_flask_app.bat
     ```

   - **For Streamlit app** (requires NumPy<2.0):
     ```
     start_pdf_cutter.bat
     ```

2. Or start the components separately:
   - Start the service:
     ```
     python pdf_cutter_service.py --output-dir ./output --port 8888
     ```
   - Start the Flask app:
     ```
     python flask_app.py
     ```
   - Start the Streamlit app (if NumPy<2.0):
     ```
     streamlit run streamlit_app.py
     ```

## Using the Flask App

1. **Start the service** from the sidebar if it's not already running
2. Choose one of the three sections:
   - **Single PDF Splitter**: Upload or specify the path to a PDF and define page ranges
   - **Batch Processing**: Process multiple PDFs using a configuration file
   - **Configuration Editor**: Create or edit configuration files visually

## Using the Service Directly (Command Line)

```
# Run as a service watching a directory
python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json

# Run as a service with a specific port for API access
python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --port 5000

# Run as a service without watching a directory (API only)
python pdf_cutter_service.py --output-dir ./output --port 8000
```

## Using the HTTP API

The service provides a simple HTTP API on port 8000 (or as configured):

- `GET /status` - Get the current service status
- `GET /help` - Get API help information
- `POST /split` - Split a PDF file with parameters:
  - `input_file`: Path to the input PDF
  - `ranges`: Page ranges in format "1-10:Lecture1,11-20:Lecture2"
  - `output_dir`: Output directory
  - `prefix` (optional): Prefix for output filenames
  - `unit_name` (optional): Unit name for output filenames

Example:
```
curl -X POST "http://localhost:8000/split?input_file=example.pdf&ranges=1-5:Part1,6-10:Part2&output_dir=output"
```

## Configuration File Format

The configuration file is in JSON format and defines how PDFs should be split:

```json
{
  "default": {
    "page_ranges": [
      {
        "start": 1,
        "end": 5,
        "name": "Introduction"
      },
      {
        "start": 6,
        "end": 15,
        "name": "MainContent"
      }
    ],
    "unit_name": "DefaultUnit",
    "prefix": "NCERT"
  },
  "english_textbook": {
    "page_ranges": [
      {
        "start": 1,
        "end": 10,
        "name": "Chapter1"
      },
      {
        "start": 11,
        "end": 25,
        "name": "Chapter2"
      }
    ],
    "unit_name": "English",
    "prefix": "Class6"
  },
  "^chapter(\\d+)$": {
    "page_ranges": [
      {
        "start": 1,
        "end": 5,
        "name": "Introduction"
      },
      {
        "start": 6,
        "end": 15,
        "name": "Content"
      }
    ],
    "unit_name": "PatternMatched",
    "prefix": "NCERT"
  }
}
```

- **default**: Applied when no specific pattern matches
- **exact filenames**: (like "english_textbook") matches exact filename without extension
- **regex patterns**: (starting with ^ and ending with $) matches filenames using regular expressions

## Output Naming

The output files are named according to the pattern:
`[prefix]_[unit_name]_[name].pdf`

For example, with:
- prefix = "Class6"
- unit_name = "English"
- name = "Chapter1"

The output file would be: `Class6_English_Chapter1.pdf`

## Troubleshooting

### NumPy Version Issues

If you encounter errors about NumPy version compatibility (such as errors with NumPy 2.0 and Streamlit), use the Flask app instead, which is compatible with newer NumPy versions.

### General Issues

1. Make sure all required directories exist (templates, output, temp)
2. Check that the service is running before using the web interfaces
3. For PDF processing errors, verify that the PDF file is valid and not password-protected
