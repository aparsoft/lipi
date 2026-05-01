import atexit
import os
import json
import glob
import sys
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, abort
from pypdf import PdfReader
from werkzeug.utils import secure_filename

# Import the service module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from pdf_cutter_service import PDFCutterService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "temp")
# Increase maximum file size to 100 MB
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# Ensure temp and output directories exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

# Global variables
SERVICE_PROCESS = None
DEFAULT_SERVICE_URL = "http://localhost:8111"


def _safe_path(user_path: str, allowed_base: str = BASE_DIR) -> str:
    """Resolve user-supplied path and ensure it stays within the allowed base directory."""
    resolved = os.path.realpath(os.path.join(allowed_base, user_path))
    if not resolved.startswith(
        os.path.realpath(allowed_base) + os.sep
    ) and resolved != os.path.realpath(allowed_base):
        abort(403, description="Access denied: path outside allowed directory")
    return resolved


def start_service_process(output_dir: str, config_file=None, port: int = 8111):
    """Start the PDF Cutter Service as a subprocess"""
    global SERVICE_PROCESS

    # Build the command
    cmd = [
        sys.executable,
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "pdf_cutter_service.py"
        ),
        "--output-dir",
        output_dir,
        "--port",
        str(port),
    ]

    if config_file:
        cmd.extend(["--config", config_file])

    try:
        # Start the process
        SERVICE_PROCESS = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Wait for the service to start
        time.sleep(2)
        return True
    except Exception as e:
        print(f"Failed to start service: {e}")
        return False


def check_service_status(url=DEFAULT_SERVICE_URL):
    """Check if the service is running and get its status"""
    try:
        response = requests.get(f"{url}/status", timeout=2)
        if response.status_code == 200:
            return response.json()
        return {
            "running": False,
            "error": f"Service returned status code {response.status_code}",
        }
    except requests.exceptions.ConnectionError:
        return {"running": False, "error": "Cannot connect to service"}
    except Exception as e:
        return {"running": False, "error": str(e)}


def get_pdf_info(file_path):
    """Get information about a PDF file"""
    service = PDFCutterService()
    return service.get_pdf_info(file_path)


def correct_hindi_text(text, font_type="auto", service_url=DEFAULT_SERVICE_URL):
    """
    Correct Hindi text encoding issues using the service API

    Args:
        text: Text with encoding issues
        font_type: Font type ('auto', 'krutidev', 'chanakya')
        service_url: Service URL

    Returns:
        Dictionary with original and corrected text
    """
    try:
        # Use service API for text correction
        url = f"{service_url}/correct_text"
        data = {"text": text, "font_type": font_type}

        response = requests.post(url, json=data, timeout=30)

        if response.status_code == 200:
            return response.json()
        else:
            # Fallback to direct method if API call fails
            service = PDFCutterService()
            has_encoding_issues = service.detect_potential_hindi_encoding_issue(text)

            if has_encoding_issues:
                corrected_text = service.correct_hindi_text(text, font_type)
                corrected_text = service.post_process_hindi_text(corrected_text)

                return {
                    "original_text": text,
                    "has_encoding_issues": True,
                    "corrected_text": corrected_text,
                    "detected_font_type": (
                        font_type if font_type != "auto" else "krutidev"
                    ),
                }
            else:
                return {
                    "original_text": text,
                    "has_encoding_issues": False,
                    "corrected_text": text,
                    "detected_font_type": None,
                }
    except Exception as e:
        # Direct method as fallback
        service = PDFCutterService()
        has_encoding_issues = service.detect_potential_hindi_encoding_issue(text)

        if has_encoding_issues:
            corrected_text = service.correct_hindi_text(text, font_type)
            corrected_text = service.post_process_hindi_text(corrected_text)

            return {
                "original_text": text,
                "has_encoding_issues": True,
                "corrected_text": corrected_text,
                "detected_font_type": font_type if font_type != "auto" else "krutidev",
                "error": str(e),
            }
        else:
            return {
                "original_text": text,
                "has_encoding_issues": False,
                "corrected_text": text,
                "detected_font_type": None,
                "error": str(e),
            }


def split_pdf_through_api(
    input_file,
    ranges,
    output_dir,
    prefix=None,
    unit_name=None,
    fix_encoding=True,
    service_url=DEFAULT_SERVICE_URL,
):
    """Split a PDF file through the service API"""
    params = {
        "input_file": input_file,
        "ranges": ranges,
        "output_dir": output_dir,
        "fix_encoding": str(fix_encoding).lower(),
    }

    if prefix:
        params["prefix"] = prefix

    if unit_name:
        params["unit_name"] = unit_name

    try:
        # We'll construct the URL with proper encoding to handle spaces and special characters
        url = f"{service_url}/split"
        response = requests.post(url, params=params, timeout=30)

        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "message": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.route("/")
def index():
    """Main route for the application"""
    # Check service status
    status = check_service_status()

    return render_template("index.html", status=status)


@app.route("/start_service", methods=["POST"])
def start_service():
    """Start the PDF Cutter Service"""
    output_dir = request.form.get("output_dir", "output")
    port = int(request.form.get("port", 8888))
    config_file = (
        request.form.get("config_file", "")
        if request.form.get("use_config", "") == "on"
        else None
    )

    if config_file and not os.path.isfile(config_file):
        return jsonify(
            {"success": False, "message": f"Config file not found: {config_file}"}
        )

    success = start_service_process(output_dir, config_file, port)

    if success:
        return jsonify({"success": True, "message": "Service started successfully"})
    else:
        return jsonify({"success": False, "message": "Failed to start service"})


@app.route("/service_status")
def service_status():
    """Get service status"""
    status = check_service_status()
    return jsonify(status)


@app.route("/single_pdf")
def single_pdf():
    """Page for single PDF processing"""
    status = check_service_status()
    return render_template("single_pdf.html", status=status)


@app.route("/batch_process")
def batch_process():
    """Page for batch PDF processing"""
    status = check_service_status()
    return render_template("batch_process.html", status=status)


@app.route("/config_editor")
def config_editor():
    """Page for configuration editing"""
    status = check_service_status()

    # Load config if exists
    config_data = {}
    config_path = request.args.get("config_path", "config.json")

    config_path = _safe_path(config_path)
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return render_template(
        "config_editor.html", status=status, config=config_data, config_path=config_path
    )


@app.route("/upload_pdf", methods=["POST"])
def upload_pdf():
    """Handle PDF upload"""
    if "pdf_file" not in request.files:
        return jsonify({"success": False, "message": "No file part"})

    file = request.files["pdf_file"]

    if file.filename == "":
        return jsonify({"success": False, "message": "No selected file"})

    if file and file.filename.lower().endswith(".pdf"):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        # Get PDF info
        pdf_info = get_pdf_info(file_path)

        return jsonify(
            {
                "success": True,
                "message": "File uploaded successfully",
                "file_path": file_path,
                "pdf_info": pdf_info,
            }
        )

    return jsonify({"success": False, "message": "Invalid file format"})


@app.route("/split_pdf", methods=["POST"])
def split_pdf():
    """Handle PDF splitting"""
    input_file = request.form.get("input_file")
    ranges = request.form.get("ranges")
    output_dir = request.form.get("output_dir", "output")
    prefix = request.form.get("prefix", "")
    unit_name = request.form.get("unit_name", "")
    fix_encoding = request.form.get("fix_encoding", "true").lower() == "true"

    if not input_file or not ranges:
        return jsonify(
            {"success": False, "message": "Input file and ranges are required"}
        )

    if not os.path.isfile(input_file):
        return jsonify(
            {"success": False, "message": f"Input file not found: {input_file}"}
        )

    # Process the PDF
    result = split_pdf_through_api(
        input_file,
        ranges,
        output_dir,
        prefix if prefix else None,
        unit_name if unit_name else None,
        fix_encoding,
    )

    if result.get("status") == "success":
        return jsonify(
            {"success": True, "message": "PDF split successfully", "result": result}
        )
    else:
        return jsonify(
            {"success": False, "message": result.get("message", "Unknown error")}
        )


@app.route("/correct_hindi_text", methods=["POST"])
def correct_hindi_text_route():
    """Handle Hindi text encoding correction"""
    text = request.form.get("text", "")
    font_type = request.form.get("font_type", "auto")

    if not text:
        return jsonify({"success": False, "message": "No text provided"})

    # Process the text
    result = correct_hindi_text(text, font_type)

    return jsonify({"success": True, "result": result})


@app.route("/extract_pdf_text", methods=["POST"])
def extract_pdf_text():
    """Extract text from PDF and optionally correct Hindi encoding"""
    if "pdf_file" not in request.files:
        return jsonify({"success": False, "message": "No file part"})

    file = request.files["pdf_file"]
    correct_encoding = request.form.get("correct_encoding", "true").lower() == "true"
    font_type = request.form.get("font_type", "auto")
    page_range = request.form.get("page_range", "")

    if file.filename == "":
        return jsonify({"success": False, "message": "No selected file"})

    if file and file.filename.lower().endswith(".pdf"):
        try:
            # Save the file temporarily
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            # Extract text from the PDF
            with open(file_path, "rb") as f:
                pdf_reader = PdfReader(f)
                total_pages = len(pdf_reader.pages)

                # Parse page range if provided
                start_page, end_page = 0, total_pages
                if page_range:
                    try:
                        if "-" in page_range:
                            parts = page_range.split("-")
                            # 1-indexed to 0-indexed
                            start_page = max(0, int(parts[0]) - 1)
                            end_page = min(total_pages, int(parts[1]))
                        else:
                            start_page = max(0, int(page_range) - 1)
                            end_page = min(total_pages, start_page + 1)
                    except (ValueError, IndexError):
                        start_page, end_page = 0, total_pages

                # Extract text from the specified pages
                extracted_text = ""
                has_encoding_issues = False

                for page_num in range(start_page, end_page):
                    page_text = pdf_reader.pages[page_num].extract_text()
                    if page_text:
                        extracted_text += page_text + "\n\n"

                # Check if there are Hindi encoding issues
                service = PDFCutterService()
                has_encoding_issues = service.detect_potential_hindi_encoding_issue(
                    extracted_text
                )

                # Correct encoding if needed
                if correct_encoding and has_encoding_issues:
                    result = correct_hindi_text(extracted_text, font_type)
                    corrected_text = result["corrected_text"]
                    detected_font_type = result.get("detected_font_type", font_type)
                else:
                    corrected_text = extracted_text
                    detected_font_type = None

                return jsonify(
                    {
                        "success": True,
                        "filename": filename,
                        "total_pages": total_pages,
                        "extracted_text": extracted_text,
                        "has_encoding_issues": has_encoding_issues,
                        "corrected_text": corrected_text if correct_encoding else None,
                        "detected_font_type": detected_font_type,
                    }
                )

        except Exception as e:
            return jsonify(
                {"success": False, "message": f"Error extracting text: {str(e)}"}
            )

    return jsonify({"success": False, "message": "Invalid file format"})


@app.route("/process_directory", methods=["POST"])
def process_directory():
    """Handle batch processing of a directory"""
    input_dir = request.form.get("input_dir")
    output_dir = request.form.get("output_dir", "output")
    config_file = request.form.get("config_file")

    if not input_dir:
        return jsonify({"success": False, "message": "Input directory is required"})

    input_dir = _safe_path(input_dir)
    output_dir = _safe_path(output_dir)

    if not os.path.isdir(input_dir):
        return jsonify({"success": False, "message": "Input directory not found"})

    if not config_file:
        return jsonify({"success": False, "message": "Config file is required"})

    config_file = _safe_path(config_file)
    if not os.path.isfile(config_file):
        return jsonify({"success": False, "message": "Config file not found"})

    # Process the directory
    service = PDFCutterService()
    config = service.load_config(config_file)

    try:
        result = service.process_directory(input_dir, output_dir, config)
        return jsonify(
            {
                "success": True,
                "message": f"Processed {result['processed_count']} files, skipped {result['skipped_count']} files",
                "result": result,
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error processing directory: {str(e)}"}
        )


@app.route("/save_config", methods=["POST"])
def save_config():
    """Save configuration file"""
    config_data = request.json.get("config")
    config_path = request.json.get("config_path", "config.json")

    if not config_data:
        return jsonify({"success": False, "message": "No configuration data provided"})

    config_path = _safe_path(config_path)
    try:
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        return jsonify(
            {"success": True, "message": f"Configuration saved to {config_path}"}
        )
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error saving configuration: {str(e)}"}
        )


@app.route("/list_output_files")
def list_output_files():
    """List output files"""
    output_dir = request.args.get("output_dir", "output")

    if not os.path.isdir(output_dir):
        return jsonify(
            {"success": False, "message": f"Output directory not found: {output_dir}"}
        )

    files = []
    for file_path in glob.glob(os.path.join(output_dir, "*.pdf")):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        files.append(
            {"name": file_name, "path": file_path, "size": round(file_size, 2)}
        )

    return jsonify({"success": True, "files": files})


@app.route("/download_file")
def download_file():
    """Download a file"""
    file_path = request.args.get("file_path")
    if not file_path:
        return jsonify({"success": False, "message": "No file path provided"})

    file_path = _safe_path(file_path)
    if not os.path.isfile(file_path):
        return jsonify({"success": False, "message": "File not found"})

    return send_file(file_path, as_attachment=True)


@app.route("/delete_file", methods=["POST"])
def delete_file():
    """Delete a file"""
    file_path = request.form.get("file_path")
    if not file_path:
        return jsonify({"success": False, "message": "No file path provided"})

    file_path = _safe_path(file_path)
    if not os.path.isfile(file_path):
        return jsonify({"success": False, "message": "File not found"})

    try:
        os.remove(file_path)
        return jsonify(
            {"success": True, "message": f"File deleted: {os.path.basename(file_path)}"}
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Error deleting file: {str(e)}"})


# Register cleanup function to stop the service when the app exits
def cleanup():
    global SERVICE_PROCESS
    if SERVICE_PROCESS:
        SERVICE_PROCESS.terminate()
        SERVICE_PROCESS = None


atexit.register(cleanup)


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    os.makedirs("templates", exist_ok=True)

    # Start the Flask app
    app.run(debug=True, port=5000)
