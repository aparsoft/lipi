import atexit
import os
import json
import glob
import sys
import time
import subprocess
import requests
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_file, abort
from pypdf import PdfReader
from werkzeug.utils import secure_filename

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from pdf_cutter_service import PDFCutterService, __version__ as SERVICE_VERSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

SERVICE_PROCESS = None
DEFAULT_SERVICE_URL = "http://localhost:8111"


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
# Service management
# ---------------------------------------------------------------------------


def start_service_process(output_dir: str, config_file=None, port: int = 8111) -> bool:
    global SERVICE_PROCESS
    cmd = [
        sys.executable,
        os.path.join(BASE_DIR, "pdf_cutter_service.py"),
        "--output-dir",
        output_dir,
        "--port",
        str(port),
    ]
    if config_file:
        cmd += ["--config", config_file]

    try:
        SERVICE_PROCESS = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        time.sleep(2)
        return True
    except Exception as exc:
        print(f"Failed to start service: {exc}")
        return False


def check_service_status(url: str = DEFAULT_SERVICE_URL) -> dict:
    try:
        resp = requests.get(f"{url}/status", timeout=2)
        if resp.status_code == 200:
            return resp.json()
        return {"running": False, "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"running": False, "error": "Cannot connect to service"}
    except Exception as exc:
        return {"running": False, "error": str(exc)}


def get_pdf_info(file_path: str) -> dict:
    return PDFCutterService().get_pdf_info(file_path)


def correct_hindi_text(
    text: str, font_type: str = "auto", service_url: str = DEFAULT_SERVICE_URL
) -> dict:
    """
    Correct legacy Hindi font encoding.  Tries the running service API first;
    falls back to direct in-process conversion if the service is not available.
    """
    try:
        resp = requests.post(
            f"{service_url}/correct_text",
            json={"text": text, "font_type": font_type},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # In-process fallback
    svc = PDFCutterService()
    has_issues, detected = svc.detect_encoding_issues(text)
    if has_issues:
        corrected = svc.convert_to_unicode(text, font_type)
        corrected = svc.post_process_hindi_text(corrected)
    else:
        corrected = text
    return {
        "original_text": text,
        "has_encoding_issues": has_issues,
        "corrected_text": corrected,
        "detected_font_type": detected if has_issues else None,
    }


def split_pdf_through_api(
    input_file: str,
    ranges: str,
    output_dir: str,
    prefix=None,
    unit_name=None,
    service_url: str = DEFAULT_SERVICE_URL,
) -> dict:
    params = {
        "input_file": input_file,
        "ranges": ranges,
        "output_dir": output_dir,
    }
    if prefix:
        params["prefix"] = prefix
    if unit_name:
        params["unit_name"] = unit_name

    try:
        resp = requests.post(f"{service_url}/split", params=params, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        return {"status": "error", "message": resp.text}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


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


@app.route("/start_service", methods=["POST"])
def start_service():
    out_dir = request.form.get("output_dir", "output")
    port = int(request.form.get("port", 8888))
    config_file = (
        request.form.get("config_file", "") or None
        if request.form.get("use_config") == "on"
        else None
    )
    if config_file and not os.path.isfile(config_file):
        return jsonify(
            {"success": False, "message": f"Config file not found: {config_file}"}
        )
    success = start_service_process(out_dir, config_file, port)
    msg = "Service started successfully" if success else "Failed to start service"
    return jsonify({"success": success, "message": msg})


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
        return jsonify(
            {"success": False, "message": "input_file and ranges are required"}
        )

    # Validate input_file stays within BASE_DIR (path traversal protection)
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

    result = split_pdf_through_api(input_file, ranges, output_dir, prefix, unit_name)
    if result.get("status") == "success":
        return jsonify(
            {"success": True, "message": "PDF split successfully", "result": result}
        )
    return jsonify(
        {"success": False, "message": result.get("message", "Unknown error")}
    )


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

    svc = PDFCutterService()
    result = svc.extract_unicode_text(
        file_path,
        page_range=page_range,
        font_type=font_type if correct_encoding else "none",
        post_process=correct_encoding,
    )

    return jsonify(
        {
            "success": True,
            "filename": filename,
            **result,
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

    svc = PDFCutterService()
    config = svc.load_config(config_file)
    try:
        result = svc.process_directory(input_dir, output_dir, config)
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
    config_path = _safe_path(data.get("config_path", "config.json"))

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
    # BUG FIX: output_dir was previously not passed through _safe_path,
    # allowing path traversal (e.g. output_dir=../../etc).
    raw_dir = request.args.get("output_dir", "output")
    try:
        output_dir = _safe_path(raw_dir)
    except Exception:
        return jsonify({"success": False, "message": "Invalid output_dir"})

    if not os.path.isdir(output_dir):
        return jsonify(
            {"success": False, "message": f"Directory not found: {output_dir}"}
        )

    files = []
    for file_path in sorted(glob.glob(os.path.join(output_dir, "*.pdf"))):
        files.append(
            {
                "name": os.path.basename(file_path),
                "path": file_path,
                "size_kb": round(os.path.getsize(file_path) / 1024, 2),
                "modified": datetime.fromtimestamp(
                    os.path.getmtime(file_path)
                ).isoformat(),
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
        return jsonify(
            {"success": True, "message": f"Deleted: {os.path.basename(file_path)}"}
        )
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)})


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@atexit.register
def cleanup():
    global SERVICE_PROCESS
    if SERVICE_PROCESS:
        SERVICE_PROCESS.terminate()
        SERVICE_PROCESS = None


if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    app.run(debug=True, port=5000)
