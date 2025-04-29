#!/usr/bin/env python3
"""
PDF Cutter Service

This service splits PDF files into separate PDF files based on specified page ranges.
It can be run as a standalone service or imported for use in other applications.

Dependencies:
    - pypdf: pip install pypdf
    - watchdog: pip install watchdog
    - tqdm: pip install tqdm

Usage as a service:
    # Run as a service watching a directory
    python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json
    
    # Run as a service with a specific port for API access
    python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --port 5000
    
Usage as a library:
    from pdf_cutter_service import PDFCutterService
    
    service = PDFCutterService()
    service.split_pdf(input_file, output_dir, page_ranges)
"""

import os
import argparse
import json
import logging
import re
import time
import threading
import queue
import http.server
import socketserver
import urllib.parse
from typing import Dict, List, Tuple, Union, Optional, Any
from pypdf import PdfReader, PdfWriter
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import socket
from pathlib import Path
from datetime import datetime
import traceback

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pdf_cutter_service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PDF Cutter Service")

# Global task queue for processing PDFs
task_queue = queue.Queue()

# Global service status
service_status = {
    "running": True,
    "processed_files": 0,
    "failed_files": 0,
    "current_task": None,
    "last_processed": None,
    "start_time": datetime.now().isoformat(),
}


class PDFCutterService:
    """PDF Cutter Service class for splitting PDFs by page ranges"""

    def __init__(self):
        """Initialize the service"""
        self.current_task = None

    @staticmethod
    def parse_page_ranges(ranges_str: str) -> List[Tuple[int, int, Optional[str]]]:
        """
        Parse page ranges string into a list of tuples (start_page, end_page, name)

        Args:
            ranges_str: String containing page ranges in format "1-10:Lecture1,11-20:Lecture2"
                    The lecture name after colon is optional

        Returns:
            List of tuples containing (start_page, end_page, lecture_name)

        Example:
            >>> parse_page_ranges("1-10:Intro,11-20:Basics,21-30")
            [(1, 10, 'Intro'), (11, 20, 'Basics'), (21, 30, None)]
        """
        ranges = []
        
        # First, we'll URL decode the ranges string to handle spaces and special characters
        ranges_str = urllib.parse.unquote_plus(ranges_str)
        
        # Split by commas, but be careful with lecture names that may contain commas
        # We'll use a more robust approach - find all page ranges patterns
        pattern = re.compile(r'(\d+)-(\d+)(?::([^,]*)?)?')
        matches = pattern.findall(ranges_str)
        
        if not matches:
            raise ValueError("Invalid ranges format. Expected format: '1-10:Lecture1,11-20:Lecture2'")
            
        for match in matches:
            start_str, end_str, lecture_name = match
            
            try:
                start = int(start_str)
                end = int(end_str)
                
                if start <= 0:
                    raise ValueError(f"Start page must be positive: {start}")
                if end < start:
                    raise ValueError(f"End page must be greater than or equal to start page: {start}-{end}")
                
                # Lecture name might be empty
                if not lecture_name.strip():
                    lecture_name = None
                    
                ranges.append((start, end, lecture_name))
            except Exception as e:
                raise ValueError(f"Error parsing page range '{start_str}-{end_str}': {str(e)}")

        return ranges

    @staticmethod
    def validate_config(config: Dict) -> bool:
        """
        Validate the configuration file structure

        Args:
            config: Configuration dictionary loaded from JSON

        Returns:
            True if valid, raises exception otherwise
        """
        # Check that it's a dictionary
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary")

        # Check each file entry
        for key, value in config.items():
            if not isinstance(value, dict):
                raise ValueError(
                    f"Configuration for '{key}' must be a dictionary")

            # Check for page_ranges
            if 'page_ranges' not in value:
                raise ValueError(
                    f"Missing 'page_ranges' in configuration for '{key}'")

            # Check page_ranges format
            page_ranges = value['page_ranges']
            if not isinstance(page_ranges, list):
                raise ValueError(f"'page_ranges' for '{key}' must be a list")

            # Check each page range
            for i, page_range in enumerate(page_ranges):
                if not isinstance(page_range, dict):
                    raise ValueError(
                        f"Page range #{i+1} for '{key}' must be a dictionary")

                if 'start' not in page_range or 'end' not in page_range:
                    raise ValueError(
                        f"Page range #{i+1} for '{key}' must have 'start' and 'end' keys")

                start = page_range['start']
                end = page_range['end']

                if not isinstance(start, int) or not isinstance(end, int):
                    raise ValueError(
                        f"'start' and 'end' for page range #{i+1} in '{key}' must be integers")

                if start <= 0:
                    raise ValueError(
                        f"'start' for page range #{i+1} in '{key}' must be positive")

                if end < start:
                    raise ValueError(
                        f"'end' for page range #{i+1} in '{key}' must be greater than or equal to 'start'")

        return True

    def get_pdf_info(self, pdf_path: str) -> Dict[str, Any]:
        """
        Get information about a PDF file

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary with PDF information
        """
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                info = {
                    "filename": os.path.basename(pdf_path),
                    "path": pdf_path,
                    "total_pages": len(pdf_reader.pages),
                    "size_kb": round(os.path.getsize(pdf_path) / 1024, 2),
                    "metadata": {}
                }

                # Extract metadata if available
                if pdf_reader.metadata:
                    for key, value in pdf_reader.metadata.items():
                        if key.startswith('/'):
                            key = key[1:]  # Remove leading slash
                        info["metadata"][key] = str(value)

                return info
        except Exception as e:
            logger.error(f"Error getting PDF info for {pdf_path}: {str(e)}")
            return {
                "filename": os.path.basename(pdf_path),
                "path": pdf_path,
                "error": str(e)
            }

    def split_pdf(self, input_file: str, output_dir: str, page_ranges: List[Tuple[int, int, Optional[str]]],
                  prefix: Optional[str] = None, unit_name: Optional[str] = None) -> List[str]:
        """
        Split a PDF file into multiple PDF files based on page ranges

        Args:
            input_file: Path to the input PDF file
            output_dir: Directory to save the output PDF files
            page_ranges: List of tuples containing (start_page, end_page, lecture_name)
            prefix: Optional prefix for output file names
            unit_name: Optional unit name to include in output file names

        Returns:
            List of paths to created PDF files
        """
        # Update current task for status reporting
        global service_status
        service_status["current_task"] = f"Splitting {os.path.basename(input_file)}"
        self.current_task = service_status["current_task"]

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        created_files = []

        try:
            with open(input_file, 'rb') as file:
                pdf_reader = PdfReader(file)
                total_pages = len(pdf_reader.pages)

                logger.info(
                    f"Processing {input_file} with {total_pages} pages")

                # Get the base filename without extension
                base_filename = os.path.basename(input_file)
                base_name = os.path.splitext(base_filename)[0]

                # If unit_name is not provided, use the base filename
                if not unit_name:
                    unit_name = base_name

                for i, (start, end, lecture_name) in enumerate(page_ranges, 1):
                    # Validate page ranges
                    if start < 1 or end > total_pages or start > end:
                        logger.warning(
                            f"Invalid page range {start}-{end} for {input_file} (total pages: {total_pages}), skipping...")
                        continue

                    # Adjust for 0-based indexing
                    start_idx = start - 1
                    end_idx = end

                    # Create a new PDF writer
                    pdf_writer = PdfWriter()

                    # Add pages from the specified range
                    page_iterator = range(start_idx, end_idx)
                    if TQDM_AVAILABLE:
                        page_iterator = tqdm(
                            page_iterator, desc=f"Processing pages {start}-{end}", unit="page")

                    for page_num in page_iterator:
                        pdf_writer.add_page(pdf_reader.pages[page_num])

                    # Generate output filename
                    if lecture_name:
                        lecture_id = lecture_name
                    else:
                        lecture_id = f"Lecture{i}"

                    filename_parts = []
                    if prefix:
                        filename_parts.append(prefix)
                    if unit_name:
                        filename_parts.append(unit_name)
                    filename_parts.append(lecture_id)

                    output_filename = '_'.join(filename_parts) + '.pdf'
                    output_path = os.path.join(output_dir, output_filename)

                    # Write the new PDF file
                    with open(output_path, 'wb') as output_file:
                        pdf_writer.write(output_file)

                    created_files.append(output_path)
                    logger.info(
                        f"Created {output_path} with pages {start}-{end}")

                service_status["processed_files"] += 1
                service_status["last_processed"] = {
                    "file": base_filename,
                    "time": datetime.now().isoformat(),
                    "output_files": len(created_files)
                }

                return created_files

        except FileNotFoundError:
            logger.error(f"File not found: {input_file}")
            service_status["failed_files"] += 1
            raise
        except PermissionError:
            logger.error(f"Permission denied when accessing {input_file}")
            service_status["failed_files"] += 1
            raise
        except Exception as e:
            logger.error(f"Error processing {input_file}: {str(e)}")
            service_status["failed_files"] += 1
            raise

    @staticmethod
    def load_config(config_file: str) -> Dict:
        """
        Load configuration from a JSON file

        Args:
            config_file: Path to the configuration JSON file

        Returns:
            Dictionary containing configuration
        """
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            # Validate the configuration
            PDFCutterService.validate_config(config)

            return config
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON in config file {config_file}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {str(e)}")
            raise

    def process_directory(self, input_dir: str, output_dir: str, config: Dict) -> Dict[str, Any]:
        """
        Process all PDF files in a directory using configuration

        Args:
            input_dir: Directory containing input PDF files
            output_dir: Directory to save output PDF files
            config: Configuration dictionary

        Returns:
            Dictionary with processing results
        """
        # Count processed and skipped files
        results = {
            "processed": [],
            "skipped": [],
            "processed_count": 0,
            "skipped_count": 0,
            "output_files": []
        }

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        for filename in os.listdir(input_dir):
            if not filename.lower().endswith('.pdf'):
                continue

            input_path = os.path.join(input_dir, filename)
            filename_without_ext = os.path.splitext(filename)[0]

            # Update current task
            global service_status
            service_status["current_task"] = f"Processing {filename}"
            self.current_task = service_status["current_task"]

            # Check if there's a specific configuration for this file
            if filename_without_ext in config:
                file_config = config[filename_without_ext]
                page_ranges = [(r['start'], r['end'], r.get('name'))
                               for r in file_config['page_ranges']]
                unit_name = file_config.get('unit_name')
                prefix = file_config.get('prefix')

                logger.info(f"Using specific configuration for {filename}")

            # Check if there's a configuration for the file pattern
            elif any(re.match(pattern, filename_without_ext) for pattern in config if pattern.startswith('^') and pattern.endswith('$')):
                # Find the matching pattern
                matching_pattern = next(pattern for pattern in config if pattern.startswith('^') and pattern.endswith('$')
                                        and re.match(pattern, filename_without_ext))

                file_config = config[matching_pattern]
                page_ranges = [(r['start'], r['end'], r.get('name'))
                               for r in file_config['page_ranges']]
                unit_name = file_config.get('unit_name')
                prefix = file_config.get('prefix')

                logger.info(
                    f"Using pattern configuration ({matching_pattern}) for {filename}")

            # Use default configuration if available
            elif 'default' in config:
                file_config = config['default']
                page_ranges = [(r['start'], r['end'], r.get('name'))
                               for r in file_config['page_ranges']]
                unit_name = file_config.get('unit_name')
                prefix = file_config.get('prefix')

                logger.info(f"Using default configuration for {filename}")

            else:
                logger.warning(
                    f"No configuration found for {filename}, skipping...")
                results["skipped"].append(filename)
                results["skipped_count"] += 1
                continue

            # Process the file
            try:
                output_files = self.split_pdf(
                    input_path, output_dir, page_ranges, prefix, unit_name)
                results["processed"].append(filename)
                results["processed_count"] += 1
                results["output_files"].extend(output_files)
            except Exception as e:
                logger.error(f"Failed to process {filename}: {str(e)}")
                results["skipped"].append(filename)
                results["skipped_count"] += 1

        logger.info(
            f"Processed {results['processed_count']} files, skipped {results['skipped_count']} files")

        return results


# File System Watcher for service mode
class PDFHandler(FileSystemEventHandler):
    """Handler for watching PDF files being added to a directory"""

    def __init__(self, output_dir, config_file=None, config=None):
        """Initialize the handler"""
        self.output_dir = output_dir
        self.config_file = config_file
        self.config = config
        self.service = PDFCutterService()
        self.processing_files = set()

    def on_created(self, event):
        """Handle when a file is created in the watched directory"""
        if event.is_directory:
            return

        if not event.src_path.lower().endswith('.pdf'):
            return

        # Avoid duplicate processing
        if event.src_path in self.processing_files:
            return

        # Add to task queue
        logger.info(f"Detected new PDF: {event.src_path}")
        task_queue.put((event.src_path, self.output_dir,
                       self.config_file, self.config))
        self.processing_files.add(event.src_path)


# Worker thread for processing PDF files from the queue
def worker_thread():
    """Worker thread for processing PDF files from the queue"""
    service = PDFCutterService()

    while service_status["running"]:
        try:
            # Get a task from the queue (timeout allows for checking if service is still running)
            task = task_queue.get(timeout=1)
            if task:
                input_path, output_dir, config_file, config = task

                try:
                    # If config_file is provided but config is not, load the config
                    if config_file and not config:
                        config = service.load_config(config_file)

                    # Process based on config or prompt for page ranges
                    if config:
                        filename_without_ext = os.path.splitext(
                            os.path.basename(input_path))[0]

                        if filename_without_ext in config:
                            file_config = config[filename_without_ext]
                            page_ranges = [(r['start'], r['end'], r.get('name'))
                                           for r in file_config['page_ranges']]
                            unit_name = file_config.get('unit_name')
                            prefix = file_config.get('prefix')

                            service.split_pdf(
                                input_path, output_dir, page_ranges, prefix, unit_name)

                        elif 'default' in config:
                            file_config = config['default']
                            page_ranges = [(r['start'], r['end'], r.get('name'))
                                           for r in file_config['page_ranges']]
                            unit_name = file_config.get('unit_name')
                            prefix = file_config.get('prefix')

                            service.split_pdf(
                                input_path, output_dir, page_ranges, prefix, unit_name)

                        else:
                            logger.warning(
                                f"No configuration found for {input_path}, skipping...")

                except Exception as e:
                    logger.error(
                        f"Error processing task {input_path}: {str(e)}")
                    traceback.print_exc()

                finally:
                    # Mark task as done
                    task_queue.task_done()

        except queue.Empty:
            # Queue is empty, continue the loop
            pass

        except Exception as e:
            logger.error(f"Error in worker thread: {str(e)}")
            traceback.print_exc()


# Simple HTTP API for the service
class PDFCutterRequestHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP API for the PDF Cutter Service"""

    def __init__(self, *args, **kwargs):
        self.service = PDFCutterService()
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Redirect logging to our logger instead of stderr
        logger.info(f"{self.address_string()} - {format % args}")

    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        try:
            # Status endpoint
            if path == '/status':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()

                # Add current task from service
                global service_status
                if self.service.current_task:
                    service_status["current_task"] = self.service.current_task

                # Add queue information
                service_status["queue_size"] = task_queue.qsize()

                status_json = json.dumps(service_status, indent=2)
                self.wfile.write(status_json.encode())
                return

            # Help/documentation endpoint
            elif path == '/' or path == '/help':
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()

                help_text = """
PDF Cutter Service API

Available endpoints:
  GET /status - Get service status
  GET /help - This help information
  POST /split - Split a PDF (provide input_file and ranges parameters)
                
Example:
  curl -X POST "http://localhost:8000/split?input_file=example.pdf&ranges=1-5:Part1,6-10:Part2&output_dir=output"
                """
                self.wfile.write(help_text.encode())
                return

            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

        except Exception as e:
            logger.error(f"Error handling GET request: {str(e)}")
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Server Error: {str(e)}".encode())

    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = dict(urllib.parse.parse_qsl(parsed_path.query))

        try:
            # Split PDF endpoint
            if path == '/split':
                if 'input_file' not in query or 'ranges' not in query:
                    self.send_response(400)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(
                        b'Missing required parameters: input_file and ranges')
                    return

                input_file = query['input_file']
                ranges_str = query['ranges']
                output_dir = query.get('output_dir', 'output')
                prefix = query.get('prefix')
                unit_name = query.get('unit_name')

                try:
                    # Parse page ranges
                    page_ranges = self.service.parse_page_ranges(ranges_str)

                    # Split the PDF
                    output_files = self.service.split_pdf(
                        input_file, output_dir, page_ranges, prefix, unit_name)

                    # Return success response
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()

                    response = {
                        "status": "success",
                        "input_file": input_file,
                        "output_dir": output_dir,
                        "output_files": output_files,
                        "page_ranges": [(start, end, name) for start, end, name in page_ranges]
                    }

                    self.wfile.write(json.dumps(response, indent=2).encode())

                except Exception as e:
                    logger.error(f"Error processing split request: {str(e)}")
                    self.send_response(400)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f"Error: {str(e)}".encode())

                return

            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

        except Exception as e:
            logger.error(f"Error handling POST request: {str(e)}")
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Server Error: {str(e)}".encode())


def find_available_port(start_port=8000, max_attempts=100):
    """Find an available port starting from start_port"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port

    # If no port found, use a random high port
    return 0  # Let the OS choose a port


def run_service(watch_dir=None, output_dir="output", config_file=None, port=None):
    """Run the PDF Cutter Service"""
    # Initialize service
    config = None
    if config_file:
        try:
            config = PDFCutterService.load_config(config_file)
            logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            return

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Start worker thread
    worker = threading.Thread(target=worker_thread, daemon=True)
    worker.start()
    logger.info("Started worker thread")

    # Set up directory watcher if watch_dir is specified
    observer = None
    if watch_dir:
        observer = Observer()
        event_handler = PDFHandler(output_dir, config_file, config)
        observer.schedule(event_handler, watch_dir, recursive=False)
        observer.start()
        logger.info(f"Watching directory: {watch_dir}")

    # Set up HTTP server
    if port is None:
        port = find_available_port()

    try:
        httpd = socketserver.TCPServer(("", port), PDFCutterRequestHandler)
        logger.info(f"Starting HTTP server on port {port}")

        # Print service info
        print(f"\n{'=' * 60}")
        print(f"PDF Cutter Service is running")
        print(f"{'=' * 60}")
        print(f"API available at http://localhost:{port}")
        print(f"API endpoints:")
        print(f"  - GET  /status - Service status")
        print(f"  - GET  /help   - Help information")
        print(f"  - POST /split  - Split a PDF")
        if watch_dir:
            print(f"Watching directory: {watch_dir}")
        print(f"Output directory: {output_dir}")
        if config_file:
            print(f"Using configuration: {config_file}")
        print(f"{'=' * 60}\n")

        # Run the server
        httpd.serve_forever()

    except KeyboardInterrupt:
        logger.info("Service shutting down on CTRL+C")
        print("\nShutting down PDF Cutter Service...")

    except Exception as e:
        logger.error(f"Error running service: {str(e)}")

    finally:
        # Cleanup
        if observer:
            observer.stop()
            observer.join()

        service_status["running"] = False
        worker.join(timeout=2)
        logger.info("PDF Cutter Service stopped")


def main():
    """Main function to parse arguments and execute the service"""
    parser = argparse.ArgumentParser(
        description="PDF Cutter Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run as a service watching a directory
  python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --config config.json
  
  # Run as a service with a specific port for API access
  python pdf_cutter_service.py --watch-dir ./input --output-dir ./output --port 5000
  
  # Run as a service without watching a directory (API only)
  python pdf_cutter_service.py --output-dir ./output --port 8000
        """
    )

    parser.add_argument(
        '--watch-dir', help='Directory to watch for new PDF files')
    parser.add_argument('--output-dir', default='output',
                        help='Output directory for split PDF files')
    parser.add_argument('--config', help='JSON configuration file')
    parser.add_argument('--port', type=int,
                        help='Port for HTTP API (default: auto-detect)')

    args = parser.parse_args()

    # Run the service
    run_service(args.watch_dir, args.output_dir, args.config, args.port)


if __name__ == "__main__":
    main()
