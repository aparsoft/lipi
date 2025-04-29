import atexit
from pdf_cutter_service import PDFCutterService
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
import os
import json
from pypdf import PdfReader  # Updated import to pypdf
import glob
import re
import sys
import threading
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

# Import the service module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "temp")
# Increase maximum file size to 100 MB
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# Ensure temp and output directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs("output", exist_ok=True)

# Global variables
SERVICE_PROCESS = None
DEFAULT_SERVICE_URL = "http://localhost:8888"


def start_service_process(output_dir: str, config_file=None, port: int = 8888):
    """Start the PDF Cutter Service as a subprocess"""
    global SERVICE_PROCESS

    # Build the command
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "pdf_cutter_service.py"),
        "--output-dir", output_dir,
        "--port", str(port)
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
            universal_newlines=True
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
        return {"running": False, "error": f"Service returned status code {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"running": False, "error": "Cannot connect to service"}
    except Exception as e:
        return {"running": False, "error": str(e)}


def get_pdf_info(file_path):
    """Get information about a PDF file"""
    service = PDFCutterService()
    return service.get_pdf_info(file_path)


def split_pdf_through_api(input_file, ranges, output_dir, prefix=None, unit_name=None, service_url=DEFAULT_SERVICE_URL):
    """Split a PDF file through the service API"""
    params = {
        "input_file": input_file,
        "ranges": ranges,
        "output_dir": output_dir
    }

    if prefix:
        params["prefix"] = prefix

    if unit_name:
        params["unit_name"] = unit_name

    try:
        response = requests.post(
            f"{service_url}/split", params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "message": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.route('/')
def index():
    """Main route for the application"""
    # Check service status
    status = check_service_status()

    return render_template('index.html', status=status)


@app.route('/start_service', methods=['POST'])
def start_service():
    """Start the PDF Cutter Service"""
    output_dir = request.form.get('output_dir', 'output')
    port = int(request.form.get('port', 8888))
    config_file = request.form.get('config_file', '') if request.form.get(
        'use_config', '') == 'on' else None

    if config_file and not os.path.isfile(config_file):
        return jsonify({"success": False, "message": f"Config file not found: {config_file}"})

    success = start_service_process(output_dir, config_file, port)

    if success:
        return jsonify({"success": True, "message": "Service started successfully"})
    else:
        return jsonify({"success": False, "message": "Failed to start service"})


@app.route('/service_status')
def service_status():
    """Get service status"""
    status = check_service_status()
    return jsonify(status)


@app.route('/single_pdf')
def single_pdf():
    """Page for single PDF processing"""
    status = check_service_status()
    return render_template('single_pdf.html', status=status)


@app.route('/batch_process')
def batch_process():
    """Page for batch PDF processing"""
    status = check_service_status()
    return render_template('batch_process.html', status=status)


@app.route('/config_editor')
def config_editor():
    """Page for configuration editing"""
    status = check_service_status()

    # Load config if exists
    config_data = {}
    config_path = request.args.get('config_path', 'config.json')

    if os.path.isfile(config_path):
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except:
            pass

    return render_template('config_editor.html', status=status, config=config_data, config_path=config_path)


@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """Handle PDF upload"""
    if 'pdf_file' not in request.files:
        return jsonify({"success": False, "message": "No file part"})

    file = request.files['pdf_file']

    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"})

    if file and file.filename.lower().endswith('.pdf'):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Get PDF info
        pdf_info = get_pdf_info(file_path)

        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "file_path": file_path,
            "pdf_info": pdf_info
        })

    return jsonify({"success": False, "message": "Invalid file format"})


@app.route('/split_pdf', methods=['POST'])
def split_pdf():
    """Handle PDF splitting"""
    input_file = request.form.get('input_file')
    ranges = request.form.get('ranges')
    output_dir = request.form.get('output_dir', 'output')
    prefix = request.form.get('prefix', '')
    unit_name = request.form.get('unit_name', '')

    if not input_file or not ranges:
        return jsonify({"success": False, "message": "Input file and ranges are required"})

    if not os.path.isfile(input_file):
        return jsonify({"success": False, "message": f"Input file not found: {input_file}"})

    # Process the PDF
    result = split_pdf_through_api(
        input_file, ranges, output_dir,
        prefix if prefix else None,
        unit_name if unit_name else None
    )

    if result.get("status") == "success":
        return jsonify({
            "success": True,
            "message": "PDF split successfully",
            "result": result
        })
    else:
        return jsonify({
            "success": False,
            "message": result.get("message", "Unknown error")
        })


@app.route('/process_directory', methods=['POST'])
def process_directory():
    """Handle batch processing of a directory"""
    input_dir = request.form.get('input_dir')
    output_dir = request.form.get('output_dir', 'output')
    config_file = request.form.get('config_file')

    if not input_dir or not os.path.isdir(input_dir):
        return jsonify({"success": False, "message": f"Input directory not found: {input_dir}"})

    if not config_file or not os.path.isfile(config_file):
        return jsonify({"success": False, "message": f"Config file not found: {config_file}"})

    # Process the directory
    service = PDFCutterService()
    config = service.load_config(config_file)

    try:
        result = service.process_directory(input_dir, output_dir, config)
        return jsonify({
            "success": True,
            "message": f"Processed {result['processed_count']} files, skipped {result['skipped_count']} files",
            "result": result
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error processing directory: {str(e)}"
        })


@app.route('/save_config', methods=['POST'])
def save_config():
    """Save configuration file"""
    config_data = request.json.get('config')
    config_path = request.json.get('config_path', 'config.json')

    if not config_data:
        return jsonify({"success": False, "message": "No configuration data provided"})

    try:
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        return jsonify({
            "success": True,
            "message": f"Configuration saved to {config_path}"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error saving configuration: {str(e)}"
        })


@app.route('/list_output_files')
def list_output_files():
    """List output files"""
    output_dir = request.args.get('output_dir', 'output')

    if not os.path.isdir(output_dir):
        return jsonify({"success": False, "message": f"Output directory not found: {output_dir}"})

    files = []
    for file_path in glob.glob(os.path.join(output_dir, "*.pdf")):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        files.append({
            "name": file_name,
            "path": file_path,
            "size": round(file_size, 2)
        })

    return jsonify({
        "success": True,
        "files": files
    })


@app.route('/download_file')
def download_file():
    """Download a file"""
    file_path = request.args.get('file_path')

    if not file_path or not os.path.isfile(file_path):
        return jsonify({"success": False, "message": f"File not found: {file_path}"})

    return send_file(file_path, as_attachment=True)


@app.route('/delete_file', methods=['POST'])
def delete_file():
    """Delete a file"""
    file_path = request.form.get('file_path')

    if not file_path or not os.path.isfile(file_path):
        return jsonify({"success": False, "message": f"File not found: {file_path}"})

    try:
        os.remove(file_path)
        return jsonify({
            "success": True,
            "message": f"File deleted: {os.path.basename(file_path)}"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error deleting file: {str(e)}"
        })


# Register cleanup function to stop the service when the app exits
def cleanup():
    global SERVICE_PROCESS
    if SERVICE_PROCESS:
        SERVICE_PROCESS.terminate()
        SERVICE_PROCESS = None


atexit.register(cleanup)


if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)

    # Start the Flask app
    app.run(debug=True, port=5000)
