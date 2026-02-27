"""S3 / Cloudflare R2 storage — upload and presigned URL generation.

Key patterns (C5 contract):
  PDF:  trips/{trip_id}/itinerary.pdf
  DOCX: trips/{trip_id}/itinerary.docx

Presigned URLs valid for 7 days (C5 contract).

Uses boto3 with configurable endpoint_url for R2 compatibility.
"""

from __future__ import annotations

import structlog
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from src.lib.config import settings

log = structlog.get_logger(__name__)


def _get_s3_client():
    """Build a boto3 S3 client, using custom endpoint if configured (R2/MinIO)."""
    kwargs: dict = {
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "config": Config(signature_version="s3v4"),
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url

    return boto3.client("s3", **kwargs)


def upload_bytes(
    data: bytes,
    trip_id: str,
    file_type: str,  # "pdf" or "docx"
) -> str:
    """Upload bytes to S3/R2 and return the object key.

    Args:
        data: Raw file bytes
        trip_id: Trip UUID (used in key path)
        file_type: "pdf" or "docx"

    Returns:
        Object key (not the presigned URL — call get_presigned_url separately)

    Raises:
        RuntimeError: if upload fails after all retries
    """
    extension = file_type.lower()
    key = f"trips/{trip_id}/itinerary.{extension}"

    content_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    content_type = content_type_map.get(extension, "application/octet-stream")

    client = _get_s3_client()

    try:
        client.put_object(
            Bucket=settings.aws_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        log.info(
            "s3_upload_success",
            trip_id=trip_id,
            key=key,
            size_bytes=len(data),
        )
        return key
    except (BotoCoreError, ClientError) as exc:
        log.error("s3_upload_failed", trip_id=trip_id, key=key, error=str(exc))
        raise RuntimeError(f"Failed to upload {key}: {exc}") from exc


def get_presigned_url(key: str) -> str:
    """Generate a presigned GET URL valid for configured TTL (7 days default).

    Args:
        key: S3 object key

    Returns:
        Presigned HTTPS URL

    Raises:
        RuntimeError: if presign generation fails
    """
    client = _get_s3_client()

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.aws_bucket_name,
                "Key": key,
            },
            ExpiresIn=settings.presigned_url_ttl_seconds,
        )
        log.info("presigned_url_generated", key=key, ttl_seconds=settings.presigned_url_ttl_seconds)
        return url
    except (BotoCoreError, ClientError) as exc:
        log.error("presigned_url_failed", key=key, error=str(exc))
        raise RuntimeError(f"Failed to generate presigned URL for {key}: {exc}") from exc


def upload_and_sign(
    data: bytes,
    trip_id: str,
    file_type: str,
) -> str:
    """Convenience: upload bytes and return presigned URL in one call."""
    key = upload_bytes(data, trip_id, file_type)
    return get_presigned_url(key)
