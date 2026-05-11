from __future__ import annotations

import io
import logging
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import BlobSasPermissions
from azure.storage.blob import ContentSettings
from azure.storage.blob import generate_blob_sas


class StorageConfigurationError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def _blob_client() -> BlobServiceClient:
    account_name = settings.AZURE_STORAGE_ACCOUNT_NAME
    account_key = settings.AZURE_STORAGE_ACCOUNT_KEY

    if not account_name or not account_key:
        raise StorageConfigurationError("Azure Blob storage credentials are not configured.")

    account_url = f"https://{account_name}.blob.core.windows.net"
    return BlobServiceClient(account_url=account_url, credential=account_key)


def _exif_value_to_json(value):
    """Recursively convert EXIF values to JSON-serialisable types."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, tuple):
        return [_exif_value_to_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _exif_value_to_json(v) for k, v in value.items()}
    # IFDRational and other numeric types
    try:
        f = float(value)
        return f if f == f else None  # guard against NaN
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return str(value)


def extract_exif_data(uploaded_file) -> dict | None:
    """
    Extract EXIF metadata from an image file and return as a JSON-safe dict.
    Returns None for non-images or files with no EXIF.
    The caller is responsible for seeking back to 0 after this call.
    """
    from PIL.ExifTags import GPSTAGS, TAGS

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        raw_exif = image._getexif()  # returns None for non-JPEG / no EXIF
        if not raw_exif:
            return None

        result: dict = {}
        for tag_id, value in raw_exif.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            if tag_name == "GPSInfo" and isinstance(value, dict):
                result["GPSInfo"] = {
                    GPSTAGS.get(k, str(k)): _exif_value_to_json(v) for k, v in value.items()
                }
            else:
                result[tag_name] = _exif_value_to_json(value)
        return result or None
    except Exception:
        logger.debug("EXIF extraction failed; skipping.", exc_info=True)
        return None


def upload_submission_media(
    *,
    season_slug: str,
    assignment_id: int,
    uploaded_file,
    media_type: str,
    strip_exif: bool = True,
) -> str:
    extension = Path(uploaded_file.name).suffix.lower()
    blob_name = (
        f"season/{season_slug}/assignment/{assignment_id}/{media_type}/"
        f"{uuid.uuid4().hex}{extension}"
    )

    client = _blob_client()
    blob = client.get_blob_client(container=settings.AZURE_STORAGE_MEDIA_CONTAINER, blob=blob_name)

    payload = _normalized_media_payload(uploaded_file=uploaded_file, media_type=media_type, strip_exif=strip_exif)
    blob.upload_blob(
        payload,
        overwrite=False,
        content_settings=ContentSettings(content_type=uploaded_file.content_type),
    )
    return blob.url


def detect_video_duration_seconds(uploaded_file) -> int | None:
    with tempfile.NamedTemporaryFile(suffix=Path(uploaded_file.name).suffix, delete=True) as temp_file:
        uploaded_file.seek(0)
        temp_file.write(uploaded_file.read())
        temp_file.flush()

        parser = createParser(temp_file.name)
        if not parser:
            return None

        with parser:
            metadata = extractMetadata(parser)
            if not metadata or not metadata.has("duration"):
                return None
            duration = metadata.get("duration")
            # Hachoir returns a timedelta-like object for duration.
            return int(duration.total_seconds())


def signed_read_url(blob_url: str, *, ttl_minutes: int = 10) -> str:
    account_name = settings.AZURE_STORAGE_ACCOUNT_NAME
    account_key = settings.AZURE_STORAGE_ACCOUNT_KEY
    if not account_name or not account_key:
        return blob_url

    parsed = urlparse(blob_url)
    path_parts = parsed.path.lstrip("/").split("/", 1)
    if len(path_parts) != 2:
        return blob_url

    container_name, blob_name = path_parts
    try:
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        )
        return f"{blob_url}?{sas_token}"
    except Exception:
        logger.warning("Signed URL generation failed; returning raw blob URL.", exc_info=True)
        return blob_url


def _normalized_media_payload(*, uploaded_file, media_type: str, strip_exif: bool) -> bytes:
    uploaded_file.seek(0)
    payload = uploaded_file.read()
    if media_type != "image" or not strip_exif:
        return payload

    try:
        image = Image.open(io.BytesIO(payload))
        image_format = image.format or "JPEG"
        output = io.BytesIO()
        # Re-saving image data strips EXIF metadata by default.
        image.save(output, format=image_format)
        return output.getvalue()
    except Exception:
        # Fall back to original bytes if sanitization fails.
        return payload
