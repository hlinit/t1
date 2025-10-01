from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, HTTPException

from ..utils.storage import StorageError, get_t1_template_bytes

router = APIRouter()


@router.get("/template-info")
async def get_template_info() -> dict[str, object]:
    container = os.getenv("AZURE_STORAGE_CONTAINER")
    blob = os.getenv("AZURE_STORAGE_BLOB")

    try:
        template_bytes = get_t1_template_bytes()
    except StorageError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(exc),
                "container": container,
                "blob": blob,
            },
        ) from exc

    digest = hashlib.sha256(template_bytes).hexdigest()[:16]
    return {
        "container": container,
        "blob": blob,
        "size": len(template_bytes),
        "sha256": digest,
    }
