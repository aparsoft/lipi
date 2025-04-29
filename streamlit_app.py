import streamlit as st
import os
import json
import time
import pandas as pd
import requests
import glob
import re
import sys
import subprocess
import threading
import PyPDF2
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path
import base64
from io import BytesIO

# Import the service module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from pdf_cutter_service import PDFCutterService

# Set page config
st.set_page_config(
    page_title="PDF Cutter App",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Define service API URL
DEFAULT_SERVICE_URL = "http://localhost:8000"
SERVICE_PROCESS = None


def start_service_process(output_dir: str, config_file: Optional[str] = None, port: int = 8000):
    """Start the PDF Cutter Service as a subprocess"""
    global SERVICE_PROCESS
    
    # Build the command
    cmd = [
        sys.executable, 
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_cutter_service.py"),
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
        st.error(f"Failed to start service: {e}")
        return False


def check_service_status(url: str = DEFAULT_SERVICE_URL) -> Dict[str, Any]:
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


def get_pdf_info(file_path: str) -> Dict[str, Any]:
    """Get information about a PDF file"""
    service = PDFCutterService()
    return service.get_pdf_info(file_path)


def split_pdf_through_api(input_file: str, ranges: str, output_dir: str, 
                         prefix: Optional[str] = None, unit_name: Optional[str] = None,
                         service_url: str = DEFAULT_SERVICE_URL) -> Dict[str, Any]:
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
        response = requests.post(f"{service_url}/split", params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "message": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_pdf_preview(pdf_path: str, page: int = 0) -> Optional[str]:
    """Generate a base64 thumbnail of the first page of a PDF"""
    try:
        # This would typically use a library like pdf2image to convert PDF pages to images
        # Since that requires additional dependencies, we'll just return a placeholder for now
        return None
    except Exception as e:
        st.error(f"Error generating PDF preview: {e}")
        return None


def generate_config_file(config_data: Dict[str, Any], output_path: str) -> str:
    """Generate a configuration file from the form data"""
    try:
        with open(output_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        return output_path
    except Exception as e:
        st.error(f"Error saving configuration file: {e}")
        return ""


def create_download_link(file_path: str, link_text: str = "Download file") -> str:
    """Create a download link for a file"""
    try:
        with open(file_path, "rb") as f:
            bytes_data = f.read()
        b64 = base64.b64encode(bytes_data).decode()
        filename = os.path.basename(file_path)
        mime_type = "application/pdf" if file_path.lower().endswith('.pdf') else "application/octet-stream"
        href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{link_text}</a>'
        return href
    except Exception as e:
        st.error(f"Error creating download link: {e}")
        return ""


# Sidebar for configuration and service status
with st.sidebar:
    st.title("PDF Cutter")
    st.markdown("---")
    
    # Service status and control
    st.subheader("Service Status")
    
    # Check if service is running
    status = check_service_status()
    if status.get("running", False):
        st.success("Service is running 🟢")
        st.write(f"Queue size: {status.get('queue_size', 0)}")
        st.write(f"Processed files: {status.get('processed_files', 0)}")
        if status.get("current_task"):
            st.write(f"Current task: {status.get('current_task')}")
    else:
        st.error("Service is not running 🔴")
        
        # Service configuration
        st.subheader("Start Service")
        output_dir = st.text_input("Output Directory", "output", key="service_output_dir")
        
        col1, col2 = st.columns(2)
        with col1:
            use_config = st.checkbox("Use Config File")
        with col2:
            service_port = st.number_input("Port", value=8000, min_value=1024, max_value=65535)
        
        config_file = None
        if use_config:
            config_file = st.text_input("Config File Path", "config.json")
        
        if st.button("Start Service"):
            with st.spinner("Starting service..."):
                if start_service_process(output_dir, config_file, service_port):
                    st.success("Service started successfully!")
                    time.sleep(1)
                    st.rerun()
    
    st.markdown("---")
    
    # App modes
    st.subheader("Navigation")
    app_mode = st.radio("Select Mode", 
                        ["Single PDF Splitter", "Batch Processing", "Configuration Editor"])


# Main content area
st.title("PDF Cutter Tool")

# Handle different app modes
if app_mode == "Single PDF Splitter":
    st.header("Split a Single PDF")
    
    # File upload or path input
    use_upload = st.checkbox("Upload PDF file", value=True)
    
    if use_upload:
        uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
        if uploaded_file:
            # Save the uploaded file to disk
            with st.spinner("Processing uploaded file..."):
                temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
                os.makedirs(temp_dir, exist_ok=True)
                temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                
                with open(temp_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Get file info
                pdf_info = get_pdf_info(temp_file_path)
                
                # Display PDF info
                st.write(f"File: **{pdf_info['filename']}**")
                st.write(f"Total pages: **{pdf_info['total_pages']}**")
                st.write(f"Size: **{pdf_info['size_kb']} KB**")
                
                # Page range input
                st.subheader("Define Page Ranges")
                
                # Interactive page range builder
                ranges = []
                col1, col2, col3 = st.columns([2, 2, 4])
                
                with col1:
                    range_preset = st.selectbox("Preset ranges", 
                                               ["Custom", "One range per page", "Single range (all pages)"])
                
                if range_preset == "One range per page":
                    ranges = [(i, i, f"Page{i}") for i in range(1, pdf_info['total_pages'] + 1)]
                elif range_preset == "Single range (all pages)":
                    ranges = [(1, pdf_info['total_pages'], "CompleteDocument")]
                
                # Custom ranges builder
                if range_preset == "Custom":
                    st.write("Add your custom page ranges:")
                    
                    # Initialize session state for ranges if not exists
                    if 'ranges' not in st.session_state:
                        st.session_state.ranges = [{"start": 1, "end": pdf_info['total_pages'], "name": "CompleteDocument"}]
                    
                    # Display existing ranges and allow editing
                    updated_ranges = []
                    for i, range_item in enumerate(st.session_state.ranges):
                        st.markdown(f"**Range {i+1}**")
                        cols = st.columns([2, 2, 4, 1])
                        with cols[0]:
                            start = st.number_input("Start page", 
                                                  value=range_item["start"], 
                                                  min_value=1, 
                                                  max_value=pdf_info['total_pages'],
                                                  key=f"start_{i}")
                        with cols[1]:
                            end = st.number_input("End page", 
                                                value=range_item["end"], 
                                                min_value=start, 
                                                max_value=pdf_info['total_pages'],
                                                key=f"end_{i}")
                        with cols[2]:
                            name = st.text_input("Name", 
                                               value=range_item["name"],
                                               key=f"name_{i}")
                        with cols[3]:
                            if st.button("Remove", key=f"remove_{i}"):
                                continue
                        
                        updated_ranges.append({"start": start, "end": end, "name": name})
                    
                    st.session_state.ranges = updated_ranges
                    
                    if st.button("Add Range"):
                        if not st.session_state.ranges:
                            st.session_state.ranges.append({"start": 1, "end": pdf_info['total_pages'], "name": "NewRange"})
                        else:
                            # Start from the end of the last range
                            last_end = st.session_state.ranges[-1]["end"]
                            new_start = min(last_end + 1, pdf_info['total_pages'])
                            new_end = pdf_info['total_pages']
                            st.session_state.ranges.append({"start": new_start, "end": new_end, "name": f"Range{len(st.session_state.ranges)+1}"})
                        st.rerun()
                    
                    ranges = [(r["start"], r["end"], r["name"]) for r in st.session_state.ranges]
                
                # Convert to string format for API
                range_str = ",".join([f"{start}-{end}:{name}" for start, end, name in ranges])
                
                # Output options
                st.subheader("Output Options")
                col1, col2 = st.columns(2)
                with col1:
                    output_dir = st.text_input("Output Directory", "output")
                with col2:
                    use_prefix = st.checkbox("Use prefix")
                
                prefix = None
                unit_name = None
                if use_prefix:
                    col1, col2 = st.columns(2)
                    with col1:
                        prefix = st.text_input("Prefix", "NCERT")
                    with col2:
                        unit_name = st.text_input("Unit Name", "English")
                
                # Split button
                if st.button("Split PDF", type="primary"):
                    if status.get("running", False):
                        with st.spinner("Splitting PDF..."):
                            result = split_pdf_through_api(
                                temp_file_path, range_str, output_dir, prefix, unit_name
                            )
                            
                            if result.get("status") == "success":
                                st.success("PDF split successfully!")
                                
                                # Display and download links for output files
                                st.subheader("Output Files")
                                for output_file in result.get("output_files", []):
                                    file_name = os.path.basename(output_file)
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.write(file_name)
                                    with col2:
                                        st.markdown(create_download_link(output_file, "Download"), unsafe_allow_html=True)
                            else:
                                st.error(f"Error: {result.get('message', 'Unknown error')}")
                    else:
                        st.error("Service is not running. Please start the service first.")
    else:
        # Path input mode
        input_file = st.text_input("PDF File Path")
        if input_file and os.path.isfile(input_file):
            # Get file info
            pdf_info = get_pdf_info(input_file)
            
            # Display PDF info
            st.write(f"File: **{pdf_info['filename']}**")
            st.write(f"Total pages: **{pdf_info['total_pages']}**")
            st.write(f"Size: **{pdf_info['size_kb']} KB**")
            
            # Page range input
            range_str = st.text_input("Page Ranges (e.g., '1-5:Chapter1,6-10:Chapter2')")
            
            # Output options
            st.subheader("Output Options")
            col1, col2 = st.columns(2)
            with col1:
                output_dir = st.text_input("Output Directory", "output")
            with col2:
                use_prefix = st.checkbox("Use prefix")
            
            prefix = None
            unit_name = None
            if use_prefix:
                col1, col2 = st.columns(2)
                with col1:
                    prefix = st.text_input("Prefix", "NCERT")
                with col2:
                    unit_name = st.text_input("Unit Name", "English")
            
            # Split button
            if st.button("Split PDF", type="primary"):
                if status.get("running", False):
                    with st.spinner("Splitting PDF..."):
                        result = split_pdf_through_api(
                            input_file, range_str, output_dir, prefix, unit_name
                        )
                        
                        if result.get("status") == "success":
                            st.success("PDF split successfully!")
                            
                            # Display and download links for output files
                            st.subheader("Output Files")
                            for output_file in result.get("output_files", []):
                                file_name = os.path.basename(output_file)
                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    st.write(file_name)
                                with col2:
                                    st.markdown(create_download_link(output_file, "Download"), unsafe_allow_html=True)
                        else:
                            st.error(f"Error: {result.get('message', 'Unknown error')}")
                else:
                    st.error("Service is not running. Please start the service first.")

elif app_mode == "Batch Processing":
    st.header("Batch Process Multiple PDFs")
    
    # Input directory
    input_dir = st.text_input("Input Directory (containing PDFs)")
    
    # Output directory
    output_dir = st.text_input("Output Directory", "output")
    
    # Configuration file
    use_config = st.checkbox("Use Configuration File", value=True)
    
    if use_config:
        config_file = st.text_input("Configuration File Path", "config.json")
        
        # Show config if exists
        if os.path.isfile(config_file):
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            with st.expander("View Configuration"):
                st.json(config_data)
        else:
            st.warning("Configuration file not found. Please create one first.")
    
    # Process button
    if st.button("Process PDFs", type="primary"):
        if not os.path.isdir(input_dir):
            st.error(f"Input directory does not exist: {input_dir}")
        elif use_config and not os.path.isfile(config_file):
            st.error(f"Configuration file does not exist: {config_file}")
        elif not status.get("running", False):
            st.error("Service is not running. Please start the service first.")
        else:
            # Get list of PDF files
            pdf_files = glob.glob(os.path.join(input_dir, "*.pdf"))
            
            if not pdf_files:
                st.warning(f"No PDF files found in {input_dir}")
            else:
                st.info(f"Found {len(pdf_files)} PDF files. Processing...")
                
                # Process each file
                results = []
                progress_bar = st.progress(0)
                
                for i, pdf_file in enumerate(pdf_files):
                    file_name = os.path.basename(pdf_file)
                    st.write(f"Processing {file_name}...")
                    
                    # Start a new task in the service
                    service = PDFCutterService()
                    config = service.load_config(config_file) if use_config else None
                    
                    try:
                        if use_config:
                            # Process based on configuration
                            result = service.process_directory(input_dir, output_dir, config)
                            results.append({
                                "file": file_name,
                                "status": "success",
                                "output_files": len(result.get("output_files", []))
                            })
                        else:
                            # Use default ranges
                            range_str = "1-9999:Complete"  # Process all pages
                            result = split_pdf_through_api(pdf_file, range_str, output_dir)
                            results.append({
                                "file": file_name,
                                "status": "success" if result.get("status") == "success" else "error",
                                "output_files": len(result.get("output_files", []))
                            })
                    except Exception as e:
                        results.append({
                            "file": file_name,
                            "status": "error",
                            "error": str(e)
                        })
                    
                    # Update progress
                    progress_bar.progress((i + 1) / len(pdf_files))
                
                # Display results
                st.success("Batch processing complete!")
                
                # Display results table
                df = pd.DataFrame(results)
                st.dataframe(df)
                
                # Show output directory
                st.subheader("Output Files")
                if os.path.isdir(output_dir):
                    output_files = glob.glob(os.path.join(output_dir, "*.pdf"))
                    for output_file in output_files:
                        file_name = os.path.basename(output_file)
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(file_name)
                        with col2:
                            st.markdown(create_download_link(output_file, "Download"), unsafe_allow_html=True)

elif app_mode == "Configuration Editor":
    st.header("Configuration Editor")
    
    # Initialize or load configuration
    if 'config' not in st.session_state:
        # Default template
        st.session_state.config = {
            "default": {
                "page_ranges": [
                    {
                        "start": 1,
                        "end": 5,
                        "name": "Introduction"
                    }
                ],
                "unit_name": "Default",
                "prefix": "NCERT"
            }
        }
    
    # Load existing config
    col1, col2 = st.columns([3, 1])
    with col1:
        load_path = st.text_input("Load Configuration File")
    with col2:
        if st.button("Load") and load_path:
            try:
                with open(load_path, 'r') as f:
                    st.session_state.config = json.load(f)
                st.success(f"Configuration loaded from {load_path}")
            except Exception as e:
                st.error(f"Error loading configuration: {e}")
    
    # Edit configuration
    st.subheader("Edit Configuration")
    
    # Add a new pattern/file
    with st.expander("Add New Pattern or File Configuration"):
        col1, col2 = st.columns(2)
        with col1:
            new_pattern_type = st.selectbox("Type", ["Exact Filename", "Regex Pattern"])
        with col2:
            if new_pattern_type == "Exact Filename":
                new_pattern = st.text_input("Filename (without extension)")
            else:
                new_pattern = st.text_input("Regex Pattern (e.g., ^chapter(\\d+)$)")
        
        col1, col2 = st.columns(2)
        with col1:
            new_unit_name = st.text_input("Unit Name")
        with col2:
            new_prefix = st.text_input("Prefix")
        
        if st.button("Add Pattern"):
            if new_pattern:
                # Add the pattern with empty page ranges
                if new_pattern_type == "Regex Pattern" and not new_pattern.startswith("^"):
                    new_pattern = "^" + new_pattern + "$"
                
                st.session_state.config[new_pattern] = {
                    "page_ranges": [],
                    "unit_name": new_unit_name,
                    "prefix": new_prefix
                }
                st.success(f"Added new pattern: {new_pattern}")
                st.rerun()
    
    # Edit existing patterns
    for pattern in list(st.session_state.config.keys()):
        with st.expander(f"Edit {pattern}"):
            pattern_config = st.session_state.config[pattern]
            
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                unit_name = st.text_input("Unit Name", pattern_config.get("unit_name", ""), key=f"unit_{pattern}")
                pattern_config["unit_name"] = unit_name
            with col2:
                prefix = st.text_input("Prefix", pattern_config.get("prefix", ""), key=f"prefix_{pattern}")
                pattern_config["prefix"] = prefix
            with col3:
                if pattern != "default" and st.button("Delete Pattern", key=f"delete_{pattern}"):
                    del st.session_state.config[pattern]
                    st.warning(f"Deleted pattern: {pattern}")
                    st.rerun()
            
            st.subheader("Page Ranges")
            
            # Initialize page ranges if not exists
            if "page_ranges" not in pattern_config:
                pattern_config["page_ranges"] = []
            
            # Edit existing page ranges
            updated_ranges = []
            for i, range_item in enumerate(pattern_config["page_ranges"]):
                col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
                with col1:
                    start = st.number_input("Start", value=range_item.get("start", 1), min_value=1, key=f"{pattern}_start_{i}")
                with col2:
                    end = st.number_input("End", value=range_item.get("end", 10), min_value=start, key=f"{pattern}_end_{i}")
                with col3:
                    name = st.text_input("Name", value=range_item.get("name", ""), key=f"{pattern}_name_{i}")
                with col4:
                    if st.button("Remove", key=f"{pattern}_remove_{i}"):
                        continue
                
                updated_ranges.append({"start": start, "end": end, "name": name})
            
            pattern_config["page_ranges"] = updated_ranges
            
            if st.button("Add Range", key=f"{pattern}_add_range"):
                last_end = 1
                if pattern_config["page_ranges"]:
                    last_end = pattern_config["page_ranges"][-1]["end"]
                
                pattern_config["page_ranges"].append({
                    "start": last_end + 1,
                    "end": last_end + 10,
                    "name": f"Range{len(pattern_config['page_ranges'])+1}"
                })
                st.rerun()
    
    # Add default pattern if not exists
    if "default" not in st.session_state.config:
        if st.button("Add Default Configuration"):
            st.session_state.config["default"] = {
                "page_ranges": [
                    {
                        "start": 1,
                        "end": 10,
                        "name": "Default"
                    }
                ],
                "unit_name": "Default",
                "prefix": "NCERT"
            }
            st.rerun()
    
    # Save configuration
    st.subheader("Save Configuration")
    col1, col2 = st.columns([3, 1])
    with col1:
        save_path = st.text_input("Save Configuration File Path", "config.json")
    with col2:
        if st.button("Save"):
            try:
                config_path = generate_config_file(st.session_state.config, save_path)
                if config_path:
                    st.success(f"Configuration saved to {config_path}")
            except Exception as e:
                st.error(f"Error saving configuration: {e}")
    
    # View JSON
    with st.expander("View JSON Configuration"):
        st.json(st.session_state.config)

# Footer
st.markdown("---")
st.caption("PDF Cutter Tool - Created for NCERT PDF processing")

# Cleanup on app exit
def cleanup():
    global SERVICE_PROCESS
    if SERVICE_PROCESS:
        SERVICE_PROCESS.terminate()
        SERVICE_PROCESS = None

# Register the cleanup function
import atexit
atexit.register(cleanup)
