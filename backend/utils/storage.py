from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from azure.storage.blob import BlobClient, ContentSettings
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("azure-storage-blob is required for storage utilities") from exc


class StorageError(RuntimeError):
    """Raised when Azure Blob Storage operations fail."""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise StorageError(f"Environment variable {name} is required")
    return value


def _build_blob_client(connection_string: str, container: str, blob: str) -> BlobClient:
    try:
        return BlobClient.from_connection_string(connection_string, container, blob)
    except Exception as exc:  # pragma: no cover - defensive
        raise StorageError("Failed to build BlobClient") from exc


def get_t1_template_bytes() -> bytes:
    connection_string = _require_env("AZURE_STORAGE_CONNECTION_STRING")
    container = _require_env("AZURE_STORAGE_CONTAINER")
    blob_name = _require_env("AZURE_STORAGE_BLOB")

    client = _build_blob_client(connection_string, container, blob_name)
    try:
        downloader = client.download_blob()
        data = downloader.readall()
        logger.info("Downloaded template blob %s/%s (%d bytes)", container, blob_name, len(data) if data else 0)
    except Exception as exc:
        raise StorageError(f"Failed to download blob '{blob_name}' from container '{container}'") from exc

    if not data:
        raise StorageError("Template blob was empty")
    return data


def upload_completed_t1(pdf_bytes: bytes, out_blob_name: str) -> str:
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise StorageError("pdf_bytes must be bytes-like")
    if not out_blob_name:
        raise StorageError("out_blob_name must be provided")

    save_enabled = os.getenv("SAVE_OUTPUT_TO_BLOB", "false").lower() == "true"
    if not save_enabled:
        return ""

    connection_string = _require_env("AZURE_STORAGE_CONNECTION_STRING")
    target_container = os.getenv("AZURE_OUTPUT_CONTAINER") or os.getenv("AZURE_STORAGE_CONTAINER")
    if not target_container:
        raise StorageError("AZURE_OUTPUT_CONTAINER or AZURE_STORAGE_CONTAINER must be set for uploads")

    client = _build_blob_client(connection_string, target_container, out_blob_name)
    try:
        client.upload_blob(
            pdf_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/pdf"),
        )
        logger.info("Uploaded filled PDF to %s/%s (%d bytes)", target_container, out_blob_name, len(pdf_bytes))
    except Exception as exc:
        raise StorageError(
            f"Failed to upload blob '{out_blob_name}' to container '{target_container}'"
        ) from exc

    return client.url or ""
