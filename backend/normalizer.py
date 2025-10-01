from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Union

from .models import NormalizedIdentity, NormalizedPayload


class NormalizationError(Exception):
    """Raised when a payload cannot be normalized."""


_CURRENCY_RE = re.compile(r"[^0-9A-Za-z.\-]")


@dataclass
class IdentityGuess:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_initial: Optional[str] = None
    sin: Optional[str] = None
    address: Optional[str] = None
    employer: Optional[str] = None
    payroll_account: Optional[str] = None


def _coerce_numeric(value: Any) -> Union[float, str]:
    if value is None:
        raise ValueError("Empty value")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("Empty string")
        normalized = stripped.replace(",", "")
        try:
            return float(normalized)
        except ValueError:
            if len(normalized) <= 4:
                return normalized
            cleaned = _CURRENCY_RE.sub("", normalized)
            try:
                return float(cleaned)
            except ValueError:
                return normalized
    raise ValueError("Unsupported value type")


def _normalize_boxes(entries: Any) -> Dict[str, Union[float, str]]:
    result: Dict[str, Union[float, str]] = {}
    if isinstance(entries, dict):
        iterable = entries.items()
    elif isinstance(entries, Iterable):
        iterable = []
        for item in entries:
            if isinstance(item, dict):
                key = item.get("box") or item.get("code") or item.get("number")
                value = item.get("value") or item.get("amount")
                if key is not None:
                    iterable.append((key, value))
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                iterable.append((item[0], item[1]))
        iterable = tuple(iterable)
    else:
        iterable = []

    for key, raw_value in iterable:
        if key is None:
            continue
        key_str = str(key).strip()
        if not key_str:
            continue
        try:
            coerced = _coerce_numeric(raw_value)
        except ValueError:
            continue
        result[key_str] = coerced
    return result


def _normalize_other_info(entries: Any) -> Dict[str, float]:
    result: Dict[str, float] = {}
    if isinstance(entries, dict):
        iterable = entries.items()
    elif isinstance(entries, Iterable):
        iterable = []
        for item in entries:
            if isinstance(item, dict):
                code = item.get("code") or item.get("box") or item.get("number") or item.get("key")
                value = item.get("value") or item.get("amount")
                if code is not None:
                    iterable.append((code, value))
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                iterable.append((item[0], item[1]))
        iterable = tuple(iterable)
    else:
        iterable = []

    for key, raw_value in iterable:
        if key is None:
            continue
        key_str = str(key).strip()
        if not key_str:
            continue
        try:
            coerced = _coerce_numeric(raw_value)
        except ValueError:
            continue
        if isinstance(coerced, str):
            continue
        result[key_str] = float(coerced)
    return result


def _split_name(value: str) -> IdentityGuess:
    cleaned = value.strip()
    if not cleaned:
        return IdentityGuess()
    if "," in cleaned:
        last, _, given = cleaned.partition(",")
        segments = given.strip().split()
        first = segments[0] if segments else None
        middle = segments[1][:1] if len(segments) > 1 else None
        return IdentityGuess(first_name=first, last_name=last.strip() or None, middle_initial=middle)
    parts = cleaned.split()
    if len(parts) == 1:
        return IdentityGuess(last_name=parts[0])
    if len(parts) == 2:
        return IdentityGuess(first_name=parts[0], last_name=parts[1])
    return IdentityGuess(first_name=parts[0], middle_initial=parts[1][:1], last_name=parts[-1])


def _extract_identity(source: Dict[str, Any]) -> NormalizedIdentity:
    identity = IdentityGuess()
    mapping = {
        "firstName": "first_name",
        "firstname": "first_name",
        "first_name": "first_name",
        "lastName": "last_name",
        "lastname": "last_name",
        "last_name": "last_name",
        "initial": "middle_initial",
        "middleInitial": "middle_initial",
        "middle": "middle_initial",
        "sin": "sin",
        "socialInsuranceNumber": "sin",
        "address": "address",
        "mailingAddress": "address",
        "employer": "employer",
        "employerName": "employer",
        "payrollAccount": "payroll_account",
        "payrollNumber": "payroll_account",
    }

    for key, value in source.items():
        norm_key = mapping.get(key)
        if not norm_key:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            setattr(identity, norm_key, stripped)
        else:
            setattr(identity, norm_key, value)  # type: ignore[arg-type]

    name = source.get("name") or source.get("employeeName")
    if isinstance(name, str):
        guessed = _split_name(name)
        identity.first_name = identity.first_name or guessed.first_name
        identity.last_name = identity.last_name or guessed.last_name
        identity.middle_initial = identity.middle_initial or guessed.middle_initial

    return NormalizedIdentity(
        firstName=identity.first_name,
        lastName=identity.last_name,
        initial=identity.middle_initial,
        sin=identity.sin,
        address=identity.address,
        employer=identity.employer,
        payrollAccount=identity.payroll_account,
    )


def normalize_t4_payload(raw: Union[str, Dict[str, Any], NormalizedPayload]) -> NormalizedPayload:
    """Normalize potentially messy extraction output into the strict schema."""
    if isinstance(raw, NormalizedPayload):
        return raw
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NormalizationError("Provided payload is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise NormalizationError("Normalization requires a dict payload")

    identity_source: Dict[str, Any] = {}
    if isinstance(raw.get("identity"), dict):
        identity_source.update(raw["identity"])  # type: ignore[arg-type]

    identity_candidates = (
        "firstName",
        "firstname",
        "first_name",
        "lastName",
        "lastname",
        "last_name",
        "initial",
        "middleInitial",
        "middle",
        "sin",
        "socialInsuranceNumber",
        "address",
        "mailingAddress",
        "employer",
        "employerName",
        "payrollAccount",
        "payrollNumber",
        "name",
        "employeeName",
    )
    for candidate in identity_candidates:
        if candidate in raw and candidate not in identity_source:
            identity_source[candidate] = raw[candidate]

    boxes_source = raw.get("boxes") or {}
    if not boxes_source:
        for candidate in ("boxValues", "boxesList", "box_list", "t4Boxes"):
            candidate_value = raw.get(candidate)
            if candidate_value:
                boxes_source = candidate_value
                break

    other_source = raw.get("otherInfo") or raw.get("other_info") or {}
    if not other_source:
        for candidate in ("other", "otherInformation", "other_information"):
            candidate_value = raw.get(candidate)
            if candidate_value:
                other_source = candidate_value
                break

    identity = _extract_identity(identity_source)
    boxes = _normalize_boxes(boxes_source)
    other_info = _normalize_other_info(other_source)

    if not identity.model_dump(exclude_none=True) and not boxes and not other_info:
        raise NormalizationError("No recognizable data to normalize")

    return NormalizedPayload(identity=identity, boxes=boxes, otherInfo=other_info)
