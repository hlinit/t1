from __future__ import annotations

import io
from typing import Mapping, Union

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, IndirectObject, NameObject
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
    writer.clone_reader_document_root(reader)
    for page in reader.pages:
        writer.add_page(page)

    root = writer._root_object
    acro_form_obj = root.get(NameObject("/AcroForm"))
    if isinstance(acro_form_obj, IndirectObject):
        acro_form = acro_form_obj.get_object()  # unwrap
    elif acro_form_obj is None:
        existing_acro = reader.trailer.get("/Root", {}).get("/AcroForm")
        acro_form = existing_acro.get_object() if isinstance(existing_acro, IndirectObject) else existing_acro
        if acro_form is None:
            acro_form = DictionaryObject()
        root[NameObject("/AcroForm")] = acro_form
    else:
        acro_form = acro_form_obj

    fields_array = acro_form.get(NameObject("/Fields"))
    if fields_array is None:
        existing_fields = reader.trailer.get("/Root", {}).get("/AcroForm", {}).get("/Fields")
        if existing_fields is None:
            raise ValueError("Template PDF does not contain form fields.")
        if isinstance(existing_fields, IndirectObject):
            fields_array = existing_fields.get_object()
        else:
            fields_array = existing_fields
        if not isinstance(fields_array, ArrayObject):
            raise ValueError("AcroForm fields dictionary is malformed.")
        acro_form[NameObject("/Fields")] = fields_array

    acro_form[NameObject("/NeedAppearances")] = BooleanObject(True)

    stringified = {name: str(value) for name, value in by_field.items() if value is not None}

    for page in writer.pages:
        writer.update_page_form_field_values(page, stringified)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
