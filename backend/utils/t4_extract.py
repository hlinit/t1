from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("pypdf is required to read T4 PDFs") from exc


class T4ExtractionError(RuntimeError):
    """Raised when identity details cannot be extracted from a T4 PDF."""


@dataclass
class T4Identity:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    initial: Optional[str] = None
    sin: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None


def _first_non_empty(fields: Dict[str, Optional[str]], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = fields.get(key)
        if value:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _normalize_postal_code(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if len(cleaned) != 6:
        return raw.strip()
    return f"{cleaned[:3]} {cleaned[3:]}"


def _parse_address(raw: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    text = raw.replace("\n", " ")
    parts = [part.strip() for part in text.split(",") if part.strip()]
    street = parts[0] if parts else raw.strip() or None
    city = None
    province = None
    postal = None

    if len(parts) >= 2:
        city = parts[1]
    remainder = " ".join(parts[2:]) if len(parts) >= 3 else ""
    remainder = re.sub(r"\s+", " ", remainder).strip()

    if remainder:
        match = re.match(r"([A-Za-z]{2})\s+([A-Za-z]\d[A-Za-z]\s*\d[A-Za-z]\d)$", remainder)
        if match:
            province = match.group(1).upper()
            postal = _normalize_postal_code(match.group(2))
        else:
            postal_match = re.search(r"([A-Za-z]\d[A-Za-z]\s*\d[A-Za-z]\d)$", remainder)
            if postal_match:
                postal = _normalize_postal_code(postal_match.group(1))
                province_candidate = remainder[: postal_match.start()].strip()
                if len(province_candidate) == 2:
                    province = province_candidate.upper()
    elif city:
        city_match = re.search(r"([A-Za-z]{2})\s+([A-Za-z]\d[A-Za-z]\s*\d[A-Za-z]\d)$", city)
        if city_match:
            province = city_match.group(1).upper()
            postal = _normalize_postal_code(city_match.group(2))
            city = city[: city_match.start()].strip()

    if city == "":
        city = None

    return street, city, province, postal


def _format_sin(value: str) -> Optional[str]:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 9:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    return digits or None


def extract_t4_identity(pdf_bytes: bytes) -> T4Identity:
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise TypeError("pdf_bytes must be bytes-like")
    if not pdf_bytes:
        raise T4ExtractionError("T4 PDF was empty")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        fields = reader.get_form_text_fields()
    except Exception as exc:  # pragma: no cover - defensive
        raise T4ExtractionError("Failed to read T4 form fields") from exc

    if not fields:
        raise T4ExtractionError("No form fields were found in the T4 PDF")

    first_name = _first_non_empty(fields, ("Slip1FirstName[0]", "Slip1FirstName[0].2"))
    last_name = _first_non_empty(fields, ("Slip1LastName[0]", "Slip1LastName[0].2"))
    initial = _first_non_empty(fields, ("Slip1Initial[0]", "Slip1Initial[0].2"))
    sin = None
    sin_candidate = _first_non_empty(fields, ("Slip1Box12[0]", "Slip1Box12[0].2", "Slip1SocialInsurance[0]"))
    if sin_candidate:
        sin = _format_sin(sin_candidate)

    address_value = _first_non_empty(fields, ("Slip1Address[0]", "Slip1Address[0].2"))
    street = city = province = postal = None
    if address_value:
        street, city, province, postal = _parse_address(address_value)

    return T4Identity(
        first_name=first_name,
        last_name=last_name,
        initial=initial,
        sin=sin,
        street=street,
        city=city,
        province=province,
        postal_code=postal,
    )


def t4_identity_to_t1_fields(identity: T4Identity) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if identity.first_name or identity.initial:
        first_line = identity.first_name or ""
        if identity.initial:
            first_line = f"{first_line} {identity.initial}".strip()
        mapping["ID_FirstNameInitial[0]"] = first_line
    if identity.last_name:
        mapping["ID_LastName[0]"] = identity.last_name
    if identity.street:
        mapping["ID_MailingAddress[0]"] = identity.street
    if identity.city or identity.province:
        if identity.city and identity.province:
            mapping["ID_City[0]"] = f"{identity.city}, {identity.province}"
        else:
            mapping["ID_City[0]"] = identity.city or identity.province or ""
    if identity.postal_code:
        mapping["PostalCode[0]"] = identity.postal_code
    if identity.sin:
        mapping["SIN_Comb[0]"] = identity.sin
    return {key: value for key, value in mapping.items() if value}


def extract_t4_identity_fields(pdf_bytes: bytes) -> Dict[str, str]:
    identity = extract_t4_identity(pdf_bytes)
    mapping = t4_identity_to_t1_fields(identity)
    if not mapping:
        raise T4ExtractionError("No identity fields could be mapped from the T4")
    return mapping
