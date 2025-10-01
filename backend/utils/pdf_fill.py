from __future__ import annotations

import io
from typing import Mapping, Union

try:
    from pypdf import PdfReader, PdfWriter
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("pypdf is required to fill PDF forms") from exc


PdfValue = Union[str, int, float]


class PdfFillError(RuntimeError):
    """Raised when a PDF form cannot be filled."""


def fill_pdf_fields(template_bytes: bytes, field_values: Mapping[str, PdfValue]) -> bytes:
    """Fill AcroForm fields in the given PDF and return the modified PDF bytes."""
    if not isinstance(template_bytes, (bytes, bytearray)):
        raise TypeError("template_bytes must be bytes-like")
    if not isinstance(field_values, Mapping):
        raise TypeError("field_values must be a mapping of field names to values")

    if not template_bytes:
        raise PdfFillError("Template PDF content is empty")

    try:
        reader = PdfReader(io.BytesIO(template_bytes))
    except Exception as exc:
        raise PdfFillError("Failed to read template PDF") from exc

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    stringified = {k: str(v) for k, v in field_values.items() if v is not None}
    try:
        for index, page in enumerate(writer.pages):
            writer.update_page_form_field_values(page, stringified)
    except Exception as exc:
        raise PdfFillError("Failed to write PDF form fields") from exc

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
