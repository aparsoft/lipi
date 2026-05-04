"""Focused tests for the Flask extraction comparison response."""

import io
from pathlib import Path

import pytest

pytest.importorskip("flask")

from web.flask_app import app


ROOT = Path(__file__).resolve().parent.parent


def _post_extract(pdf_name: str):
    pdf_path = ROOT / "temp" / pdf_name
    with app.test_client() as client, pdf_path.open("rb") as handle:
        response = client.post(
            "/extract_pdf_text",
            data={
                "pdf_file": (io.BytesIO(handle.read()), pdf_name),
                "font_type": "auto",
                "correct_encoding": "true",
                "page_range": "1-1",
            },
            content_type="multipart/form-data",
        )
    return response


def test_extract_pdf_text_exposes_raw_vs_corrected_for_legacy_pdf():
    response = _post_extract("jhkr102.pdf")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["has_encoding_issues"] is True
    assert payload["raw_equals_corrected"] is False
    assert payload["conversion_applied"] is True
    assert "pypdf" in payload["extraction_summary"]
    assert "lipi-aparsoft" in payload["extraction_summary"]


def test_extract_pdf_text_explains_unchanged_output_for_nonlegacy_pdf():
    response = _post_extract("ihkr101.pdf")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["has_encoding_issues"] is True
    assert payload["raw_equals_corrected"] is False
    assert payload["conversion_applied"] is True
    assert payload["legacy_conversion_applied"] is False
    assert payload["scrambled_cleanup_applied"] is True
    assert "scrambled" in payload["extraction_summary"]
