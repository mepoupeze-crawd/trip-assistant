"""Unit tests for the PDF/DOCX Document Generator.

The generator is expected at ``src.lib.doc_generator``.
All tests mock storage (S3) — no real uploads.
All tests are skipped until the backend agent implements the module.

Test strategy: verify output structure, not pixel-level rendering.
Verify that:
  1. generate_pdf() returns bytes (or a file-like object) of non-zero length.
  2. generate_docx() returns bytes of non-zero length.
  3. Generated content includes expected section headings.
  4. Storage upload produces the correct S3 key pattern (C5 contract).
"""

from __future__ import annotations

import io
import uuid

import pytest

try:
    from src.lib.doc_generator import DocumentGenerator  # type: ignore[import]

    _DOC_GEN_AVAILABLE = True
except ImportError:
    _DOC_GEN_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DOC_GEN_AVAILABLE,
    reason="src.lib.doc_generator not yet implemented — backend agent pending",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_itinerary() -> dict:
    """Minimal itinerary structure for doc generation tests."""
    return {
        "trip_id": str(uuid.uuid4()),
        "country": "Italy",
        "days": 5,
        "cities": [
            {
                "name": "Rome",
                "days_allocated": 3,
                "days": [
                    {
                        "day_number": 1,
                        "activities": [
                            {"type": "hotel", "name": "Hotel Hassler", "rating": 4.8, "price_hint": "luxury"},
                            {"type": "attraction", "name": "Colosseum", "rating": 4.7, "price_hint": "€16"},
                            {"type": "restaurant", "name": "La Pergola", "rating": 4.9, "price_hint": "€€€€"},
                        ],
                    }
                ],
            }
        ],
        "justifications": [],
    }


# ---------------------------------------------------------------------------
# TestPDFGeneration
# ---------------------------------------------------------------------------


class TestPDFGeneration:
    def test_generate_pdf_returns_non_empty_bytes(self, sample_itinerary):
        gen = DocumentGenerator()
        pdf_bytes = gen.generate_pdf(sample_itinerary)
        assert isinstance(pdf_bytes, bytes), "generate_pdf() should return bytes"
        assert len(pdf_bytes) > 0, "PDF output must not be empty"

    def test_pdf_has_pdf_magic_bytes(self, sample_itinerary):
        # PDF files start with %PDF-
        gen = DocumentGenerator()
        pdf_bytes = gen.generate_pdf(sample_itinerary)
        assert pdf_bytes[:4] == b"%PDF", "Output does not look like a valid PDF"

    def test_pdf_contains_country_name(self, sample_itinerary, mocker):
        """Verify the country name appears somewhere in the generated PDF.

        Uses text extraction via a lightweight check — not pixel comparison.
        """
        gen = DocumentGenerator()
        pdf_bytes = gen.generate_pdf(sample_itinerary)
        # ReportLab embeds text in the PDF stream; simple substring check is sufficient.
        assert b"Italy" in pdf_bytes or b"Italy".lower() in pdf_bytes.lower()


# ---------------------------------------------------------------------------
# TestDOCXGeneration
# ---------------------------------------------------------------------------


class TestDOCXGeneration:
    def test_generate_docx_returns_non_empty_bytes(self, sample_itinerary):
        gen = DocumentGenerator()
        docx_bytes = gen.generate_docx(sample_itinerary)
        assert isinstance(docx_bytes, bytes), "generate_docx() should return bytes"
        assert len(docx_bytes) > 0, "DOCX output must not be empty"

    def test_docx_has_ooxml_magic_bytes(self, sample_itinerary):
        # DOCX (ZIP) starts with PK\x03\x04
        gen = DocumentGenerator()
        docx_bytes = gen.generate_docx(sample_itinerary)
        assert docx_bytes[:2] == b"PK", "Output does not look like a valid DOCX/ZIP"

    def test_docx_contains_city_name(self, sample_itinerary):
        gen = DocumentGenerator()
        docx_bytes = gen.generate_docx(sample_itinerary)
        # python-docx embeds text in the underlying XML inside the zip
        assert b"Rome" in docx_bytes, "City name 'Rome' should appear in DOCX content"


# ---------------------------------------------------------------------------
# TestS3Upload (C5 key convention)
# ---------------------------------------------------------------------------


class TestS3Upload:
    """Verify C5 storage key convention: trips/{trip_id}/itinerary.pdf|docx"""

    def test_upload_pdf_uses_correct_s3_key(self, sample_itinerary, mock_s3, mocker):
        trip_id = sample_itinerary["trip_id"]
        gen = DocumentGenerator()
        pdf_bytes = gen.generate_pdf(sample_itinerary)

        # Act: upload via generator
        pdf_url = gen.upload_pdf(trip_id=trip_id, pdf_bytes=pdf_bytes)

        # Assert: the S3 key follows the C5 contract
        expected_key = f"trips/{trip_id}/itinerary.pdf"
        objects = mock_s3.list_objects_v2(
            Bucket="trip-planner-docs", Prefix=f"trips/{trip_id}/"
        )
        keys = [obj["Key"] for obj in objects.get("Contents", [])]
        assert expected_key in keys, (
            f"Expected S3 key '{expected_key}' not found. Found: {keys}"
        )

    def test_upload_docx_uses_correct_s3_key(self, sample_itinerary, mock_s3):
        trip_id = sample_itinerary["trip_id"]
        gen = DocumentGenerator()
        docx_bytes = gen.generate_docx(sample_itinerary)

        docx_url = gen.upload_docx(trip_id=trip_id, docx_bytes=docx_bytes)

        expected_key = f"trips/{trip_id}/itinerary.docx"
        objects = mock_s3.list_objects_v2(
            Bucket="trip-planner-docs", Prefix=f"trips/{trip_id}/"
        )
        keys = [obj["Key"] for obj in objects.get("Contents", [])]
        assert expected_key in keys, (
            f"Expected S3 key '{expected_key}' not found. Found: {keys}"
        )

    def test_presigned_url_is_returned(self, sample_itinerary, mock_s3):
        trip_id = sample_itinerary["trip_id"]
        gen = DocumentGenerator()
        pdf_bytes = gen.generate_pdf(sample_itinerary)
        pdf_url = gen.upload_pdf(trip_id=trip_id, pdf_bytes=pdf_bytes)

        # Presigned URL should be a non-empty string starting with http
        assert isinstance(pdf_url, str) and pdf_url.startswith("http"), (
            f"Expected presigned URL string, got: {pdf_url!r}"
        )
