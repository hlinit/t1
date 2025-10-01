from __future__ import annotations

import io
from typing import List

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("pypdf is required to read T1 field names") from exc


def get_t1_field_names(pdf_bytes: bytes) -> List[str]:
    """Extract sorted AcroForm field names from PDF bytes."""
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise TypeError("pdf_bytes must be bytes-like")
    if not pdf_bytes:
        return []

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        fields = reader.get_fields() or {}
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError("Failed to read PDF form fields") from exc

    names = sorted({str(name) for name in fields.keys()})
    return names
