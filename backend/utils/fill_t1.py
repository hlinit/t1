from __future__ import annotations

import io
from typing import Mapping, Union

try:
    from pypdf import PdfReader, PdfWriter
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("pypdf is required to fill T1 PDFs") from exc

PdfValue = Union[str, int, float]


def fill_t1_pdf(template_bytes: bytes, by_field: Mapping[str, PdfValue]) -> bytes:
    """Fill T1 AcroForm fields with provided values and return new PDF bytes."""
    if not isinstance(template_bytes, (bytes, bytearray)):
        raise TypeError("template_bytes must be bytes-like")
    if not isinstance(by_field, Mapping):
        raise TypeError("by_field must be a mapping of field names to values")

    reader = PdfReader(io.BytesIO(template_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # Ensure form values remain visible across viewers by setting NeedAppearances.
    writer._root_object.setdefault("/AcroForm", reader.trailer["/Root"].get("/AcroForm", {}))
    acro_form = writer._root_object.get("/AcroForm")
    if acro_form is not None:
        acro_form["/NeedAppearances"] = True

    stringified = {name: str(value) for name, value in by_field.items() if value is not None}

    for page in writer.pages:
        writer.update_page_form_field_values(page, stringified)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
