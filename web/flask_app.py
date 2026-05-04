import atexit
import os
import json
import glob
import sys
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from lipi.preprocessor import HindiPreprocessor
from lipi.splitter import PDFSplitter
from lipi.extractor import extract_unicode_text
from lipi import __version__ as SERVICE_VERSION

UPLOAD_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"),
)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Security helper
# ---------------------------------------------------------------------------


def _safe_path(user_path: str, allowed_base: str = BASE_DIR) -> str:
    """
    Resolve *user_path* relative to *allowed_base* and abort with 403 if
    the result escapes the allowed directory (path traversal protection).
    """
    resolved = os.path.realpath(os.path.join(allowed_base, user_path))
    base_real = os.path.realpath(allowed_base)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        abort(403, description="Access denied: path outside allowed directory")
    return resolved


# ---------------------------------------------------------------------------
# Service status — all operations run in-process via the lipi package,
# so the service is always "running".
# ---------------------------------------------------------------------------


def check_service_status() -> dict:
    return {"running": True, "version": SERVICE_VERSION}


def get_pdf_info(file_path: str) -> dict:
    return PDFSplitter.get_pdf_info(file_path)


def correct_hindi_text(text: str, font_type: str = "auto") -> dict:
    """Correct legacy Hindi font encoding (in-process, no service dependency)."""
    has_issues, detected = HindiPreprocessor.detect_encoding(text)
    corrected = text
    if has_issues:
        corrected = HindiPreprocessor.convert(text, font_type)
    corrected = HindiPreprocessor.post_process(corrected)
    return {
        "original_text": text,
        "has_encoding_issues": has_issues,
        "corrected_text": corrected,
        "detected_font_type": detected if has_issues else None,
    }


def split_pdf_direct(
    input_file: str,
    ranges: str,
    output_dir: str,
    prefix=None,
    unit_name=None,
) -> dict:
    """Split PDF directly using PDFSplitter (no service dependency)."""
    try:
        page_ranges = PDFSplitter.parse_page_ranges(ranges)
        output_files = PDFSplitter.split_pdf(input_file, output_dir, page_ranges, prefix, unit_name)
        return {
            "status": "success",
            "input_file": input_file,
            "output_files": output_files,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _summarize_extraction_result(
    raw_text: str,
    corrected_text: str,
    has_encoding_issues: bool,
    detected_font_type: str,
    correct_encoding: bool,
) -> dict:
    """Build explicit comparison metadata for the Flask extraction UI."""
    raw_equals_corrected = raw_text == corrected_text
    conversion_applied = correct_encoding and not raw_equals_corrected
    scrambled_cleanup_applied = detected_font_type == "scrambled_devanagari" and conversion_applied
    legacy_conversion_applied = (
        has_encoding_issues
        and conversion_applied
        and detected_font_type not in ("unknown", "scrambled_devanagari")
    )

    if not correct_encoding:
        summary = (
            "Showing direct pypdf extraction only because lipi-aparsoft conversion "
            "was disabled for this request."
        )
        tone = "secondary"
    elif legacy_conversion_applied:
        font_label = detected_font_type or "legacy"
        summary = (
            f"pypdf extracted the raw page text first. lipi-aparsoft then detected "
            f"{font_label} encoding and converted that raw extraction into cleaner "
            "Unicode Devanagari."
        )
        tone = "success"
    elif scrambled_cleanup_applied:
        summary = (
            "pypdf already extracted Devanagari text, but the PDF's Unicode mapping was "
            "scrambled. lipi-aparsoft repaired broken matra placement, mark spacing, and "
            "other extraction artefacts without running legacy-font glyph conversion."
        )
        tone = "info"
    elif conversion_applied:
        summary = (
            "pypdf already extracted Devanagari text, but lipi-aparsoft still improved "
            "that raw extraction with generic Unicode cleanup such as mark-spacing, matra, "
            "and broken-glyph repairs."
        )
        tone = "info"
    elif has_encoding_issues:
        summary = (
            "pypdf extracted raw legacy-looking text and lipi-aparsoft ran its cleanup "
            "pipeline, but the visible output stayed the same for this selection."
        )
        tone = "info"
    else:
        summary = (
            "pypdf already extracted Devanagari text for this selection. lipi-aparsoft "
            "did not detect a legacy font, so the Unicode output matches the raw pypdf extraction."
        )
        tone = "secondary"

    return {
        "raw_equals_corrected": raw_equals_corrected,
        "conversion_applied": conversion_applied,
        "legacy_conversion_applied": legacy_conversion_applied,
        "scrambled_cleanup_applied": scrambled_cleanup_applied,
        "comparison_tone": tone,
        "extraction_summary": summary,
        "raw_char_count": len(raw_text),
        "unicode_char_count": len(corrected_text),
    }


# ---------------------------------------------------------------------------
# Routes — pages
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    status = check_service_status()
    return render_template("index.html", status=status, version=SERVICE_VERSION)


@app.route("/single_pdf")
def single_pdf():
    status = check_service_status()
    return render_template("single_pdf.html", status=status)


@app.route("/batch_process")
def batch_process():
    status = check_service_status()
    return render_template("batch_process.html", status=status)


@app.route("/config_editor")
def config_editor():
    status = check_service_status()
    config_path = _safe_path(request.args.get("config_path", "config.json"))
    config_data = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                config_data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return render_template(
        "config_editor.html",
        status=status,
        config=config_data,
        config_path=config_path,
    )


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------


@app.route("/service_status")
def service_status():
    return jsonify(check_service_status())


@app.route("/upload_pdf", methods=["POST"])
def upload_pdf():
    if "pdf_file" not in request.files:
        return jsonify({"success": False, "message": "No file in request"})
    file = request.files["pdf_file"]
    if not file.filename:
        return jsonify({"success": False, "message": "No file selected"})
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "message": "Only PDF files are accepted"})

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)
    return jsonify(
        {
            "success": True,
            "message": "File uploaded",
            "file_path": file_path,
            "pdf_info": get_pdf_info(file_path),
        }
    )


@app.route("/split_pdf", methods=["POST"])
def split_pdf():
    input_file = request.form.get("input_file")
    ranges = request.form.get("ranges")
    output_dir = request.form.get("output_dir", OUTPUT_DIR)
    prefix = request.form.get("prefix") or None
    unit_name = request.form.get("unit_name") or None

    if not input_file or not ranges:
        return jsonify({"success": False, "message": "input_file and ranges are required"})

    try:
        input_file = _safe_path(input_file)
    except Exception:
        return jsonify({"success": False, "message": "Invalid input file path"})

    if not os.path.isfile(input_file):
        return jsonify({"success": False, "message": f"File not found: {input_file}"})

    try:
        output_dir = _safe_path(output_dir)
    except Exception:
        return jsonify({"success": False, "message": "Invalid output directory"})

    result = split_pdf_direct(input_file, ranges, output_dir, prefix, unit_name)
    if result.get("status") == "success":
        return jsonify({"success": True, "message": "PDF split successfully", "result": result})
    return jsonify({"success": False, "message": result.get("message", "Unknown error")})


@app.route("/correct_hindi_text", methods=["POST"])
def correct_hindi_text_route():
    text = request.form.get("text", "")
    font_type = request.form.get("font_type", "auto")
    if not text:
        return jsonify({"success": False, "message": "No text provided"})
    return jsonify({"success": True, "result": correct_hindi_text(text, font_type)})


@app.route("/extract_pdf_text", methods=["POST"])
def extract_pdf_text():
    if "pdf_file" not in request.files:
        return jsonify({"success": False, "message": "No file in request"})

    file = request.files["pdf_file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"success": False, "message": "Only PDF files are accepted"})

    correct_encoding = request.form.get("correct_encoding", "true").lower() == "true"
    font_type = request.form.get("font_type", "auto")
    page_range_str = request.form.get("page_range", "")

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # Parse optional page range
    page_range = None
    if page_range_str:
        try:
            if "-" in page_range_str:
                parts = page_range_str.split("-")
                page_range = (int(parts[0]), int(parts[1]))
            else:
                n = int(page_range_str)
                page_range = (n, n)
        except (ValueError, IndexError):
            pass

    # Always extract raw text (no conversion) so the UI can show the before/after
    raw_result = extract_unicode_text(
        file_path,
        page_range=page_range,
        font_type="none",
        post_process=False,
    )

    # Extract with conversion for the Unicode output
    converted_result = extract_unicode_text(
        file_path,
        page_range=page_range,
        font_type=font_type if correct_encoding else "none",
        post_process=correct_encoding,
    )

    raw_text = raw_result.get("full_text", "")
    corrected_text = converted_result.get("full_text", "")
    comparison = _summarize_extraction_result(
        raw_text=raw_text,
        corrected_text=corrected_text,
        has_encoding_issues=converted_result.get("has_encoding_issues", False),
        detected_font_type=converted_result.get("detected_font_type", "unknown"),
        correct_encoding=correct_encoding,
    )

    return jsonify(
        {
            "success": True,
            "filename": filename,
            "raw_text": raw_text,
            "corrected_text": corrected_text,
            **comparison,
            **converted_result,
        }
    )


@app.route("/process_directory", methods=["POST"])
def process_directory():
    input_dir = request.form.get("input_dir")
    output_dir = request.form.get("output_dir", OUTPUT_DIR)
    config_file = request.form.get("config_file")

    if not input_dir:
        return jsonify({"success": False, "message": "input_dir is required"})

    input_dir = _safe_path(input_dir)
    output_dir = _safe_path(output_dir)

    if not os.path.isdir(input_dir):
        return jsonify({"success": False, "message": "input_dir not found"})
    if not config_file:
        return jsonify({"success": False, "message": "config_file is required"})

    config_file = _safe_path(config_file)
    if not os.path.isfile(config_file):
        return jsonify({"success": False, "message": "config_file not found"})

    config = PDFSplitter.load_config(config_file)
    try:
        result = PDFSplitter.process_directory(input_dir, output_dir, config)
        return jsonify(
            {
                "success": True,
                "message": (
                    f"Processed {result['processed_count']} files, "
                    f"skipped {result['skipped_count']}"
                ),
                "result": result,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"Error: {exc}"})


@app.route("/save_config", methods=["POST"])
def save_config():
    data = request.json or {}
    config_data = data.get("config")
    try:
        config_path = _safe_path(data.get("config_path", "config.json"))
    except Exception:
        return jsonify({"success": False, "message": "Invalid config file path"})

    if not config_data:
        return jsonify({"success": False, "message": "No config data provided"})

    try:
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(config_data, fh, indent=2, ensure_ascii=False)
        return jsonify({"success": True, "message": f"Saved to {config_path}"})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)})


@app.route("/list_output_files")
def list_output_files():
    raw_dir = request.args.get("output_dir", "output")
    try:
        output_dir = _safe_path(raw_dir)
    except Exception:
        return jsonify({"success": False, "message": "Invalid output_dir"})

    if not os.path.isdir(output_dir):
        return jsonify({"success": False, "message": f"Directory not found: {output_dir}"})

    files = []
    for file_path in sorted(glob.glob(os.path.join(output_dir, "*.pdf"))):
        files.append(
            {
                "name": os.path.basename(file_path),
                "path": file_path,
                "size_kb": round(os.path.getsize(file_path) / 1024, 2),
                "modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
            }
        )
    return jsonify({"success": True, "files": files, "count": len(files)})


@app.route("/download_file")
def download_file():
    file_path = request.args.get("file_path", "")
    if not file_path:
        return jsonify({"success": False, "message": "file_path is required"})
    file_path = _safe_path(file_path)
    if not os.path.isfile(file_path):
        return jsonify({"success": False, "message": "File not found"})
    return send_file(file_path, as_attachment=True)


@app.route("/delete_file", methods=["POST"])
def delete_file():
    file_path = request.form.get("file_path", "")
    if not file_path:
        return jsonify({"success": False, "message": "file_path is required"})
    file_path = _safe_path(file_path)
    if not os.path.isfile(file_path):
        return jsonify({"success": False, "message": "File not found"})
    try:
        os.remove(file_path)
        return jsonify({"success": True, "message": f"Deleted: {os.path.basename(file_path)}"})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)})


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@atexit.register
def cleanup():
    pass


if __name__ == "__main__":
    app.run(debug=True, port=5000)
