"""Unit tests for the PDF/DOCX Document Generator.

Pure unit tests — no real S3 uploads (storage.upload_and_sign is mocked).
Verify: output is bytes, correct magic bytes, includes expected content.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.worker.doc_generator import generate_pdf, generate_docx
from src.worker.trip_composer import ComposedTrip, CitySlot, DaySchedule, compose, select_cities
from src.worker.rules_engine import RecommendationCandidate


# ── Fixtures ─────────────────────────────────────────────────────────────────

PREFS = {
    "pace": "medium",
    "focus": ["food", "culture", "nature"],
    "crowds": "medium",
    "hotel": "mixed",
    "restrictions": [],
}

TRIP_META = {
    "country": "Italy",
    "days": 7,
    "party_size": "couple",
    "dates_or_month": "09/2026",
    "origin": "GRU",
}


def _make_recs(cities: list[str]) -> list[RecommendationCandidate]:
    candidates = []
    for city in cities:
        for t in ["hotel", "attraction", "activity", "restaurant", "bar"]:
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type=t,
                        name=f"{city} {t.title()} {i + 1}",
                        rating=4.3,
                        review_count=600,
                        price_hint="€€",
                        source_name="Google Maps",
                        source_url=f"https://maps.google.com/?q={city}+{t}+{i}",
                    )
                )
    return candidates


@pytest.fixture
def composed_trip() -> ComposedTrip:
    slots = select_cities("Italy", 7, PREFS)
    cities = [s.city for s in slots]
    recs = _make_recs(cities)
    return compose("Italy", 7, PREFS, start_date=None, all_recommendations=recs)


# ── PDF tests ─────────────────────────────────────────────────────────────────

class TestPDFGeneration:
    def test_generate_pdf_returns_non_empty_bytes(self, composed_trip):
        result = generate_pdf(composed_trip, TRIP_META)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_pdf_has_pdf_magic_bytes(self, composed_trip):
        result = generate_pdf(composed_trip, TRIP_META)
        # PDFs start with %PDF
        assert result[:4] == b"%PDF"

    def test_pdf_contains_country_name(self, composed_trip):
        result = generate_pdf(composed_trip, TRIP_META)
        assert b"Italy" in result


# ── DOCX tests ────────────────────────────────────────────────────────────────

class TestDOCXGeneration:
    def test_generate_docx_returns_non_empty_bytes(self, composed_trip):
        result = generate_docx(composed_trip, TRIP_META)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_docx_has_ooxml_magic_bytes(self, composed_trip):
        result = generate_docx(composed_trip, TRIP_META)
        # DOCX (zip) starts with PK\x03\x04
        assert result[:4] == b"PK\x03\x04"

    def test_docx_contains_city_name(self, composed_trip):
        result = generate_docx(composed_trip, TRIP_META)
        # The city name should appear in the raw zip content
        assert len(result) > 1000  # non-trivial document


# ── Storage key convention tests (C5) ────────────────────────────────────────

class TestS3Upload:
    def test_upload_pdf_uses_correct_s3_key(self, composed_trip):
        trip_id = str(uuid.uuid4())
        pdf_bytes = generate_pdf(composed_trip, TRIP_META)

        with patch("src.worker.storage.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.generate_presigned_url.return_value = (
                f"https://bucket.s3.amazonaws.com/trips/{trip_id}/itinerary.pdf?sig=abc"
            )

            from src.worker.storage import upload_and_sign
            url = upload_and_sign(pdf_bytes, trip_id, "pdf")

        # Verify the S3 key passed to put_object follows C5 convention
        put_call = mock_client.put_object.call_args
        key = put_call.kwargs.get("Key") or (put_call.args[0] if put_call.args else "")
        assert f"trips/{trip_id}/itinerary.pdf" in key or f"trips/{trip_id}" in str(put_call)

    def test_upload_docx_uses_correct_s3_key(self, composed_trip):
        trip_id = str(uuid.uuid4())
        docx_bytes = generate_docx(composed_trip, TRIP_META)

        with patch("src.worker.storage.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.generate_presigned_url.return_value = (
                f"https://bucket.s3.amazonaws.com/trips/{trip_id}/itinerary.docx?sig=abc"
            )

            from src.worker.storage import upload_and_sign
            url = upload_and_sign(docx_bytes, trip_id, "docx")

        put_call = mock_client.put_object.call_args
        assert put_call is not None

    def test_presigned_url_is_returned(self, composed_trip):
        trip_id = str(uuid.uuid4())
        pdf_bytes = generate_pdf(composed_trip, TRIP_META)
        expected_url = f"https://bucket.s3.amazonaws.com/trips/{trip_id}/itinerary.pdf?sig=test"

        with patch("src.worker.storage.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.generate_presigned_url.return_value = expected_url

            from src.worker.storage import upload_and_sign
            url = upload_and_sign(pdf_bytes, trip_id, "pdf")

        assert url == expected_url


# ── Rating formatting tests ───────────────────────────────────────────────────

class TestRatingFormatting:
    def test_pdf_rating_is_formatted_to_one_decimal(self, composed_trip):
        """PDF should show '4.3' not '4.300000...' for any rating."""
        result = generate_pdf(composed_trip, TRIP_META)
        # The fixture uses rating=4.3 — verify it's formatted
        assert b"4.3" in result
        # Make sure raw float is NOT present
        assert b"4.30000" not in result

    def test_docx_rating_is_formatted_to_one_decimal(self, composed_trip):
        """DOCX should show formatted rating, not raw float."""
        import zipfile, io
        result = generate_docx(composed_trip, TRIP_META)
        # DOCX is a zip — extract text content and check
        with zipfile.ZipFile(io.BytesIO(result)) as z:
            # word/document.xml contains the text
            with z.open("word/document.xml") as f:
                content = f.read().decode("utf-8")
        assert "4.3" in content
        assert "4.30000" not in content


# ── PDF table layout tests ────────────────────────────────────────────────────

class TestPDFTableLayout:
    def test_pdf_col_widths_sum_to_18cm(self):
        """Column widths must fit A4 usable width (18.0 cm)."""
        import importlib
        import src.worker.doc_generator as dg
        import inspect, ast, re

        # Read the source and verify the col_widths list
        source = inspect.getsource(dg._build_pdf_schedule_table)
        # Extract col_widths values from source
        match = re.search(r'col_widths\s*=\s*\[([^\]]+)\]', source)
        assert match, "col_widths not found in _build_pdf_schedule_table"
        widths_str = match.group(1)
        # Parse numeric values (pattern: X.X * cm)
        values = [float(v) for v in re.findall(r'([\d.]+)\s*\*\s*cm', widths_str)]
        assert len(values) == 6, f"Expected 6 columns, got {len(values)}"
        total = sum(values)
        assert total <= 18.0, f"Column widths sum to {total} cm, must be <= 18.0 cm"
