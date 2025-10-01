from __future__ import annotations

import re
from typing import Any, Dict, Union

IDENTITY_KEYS = {
    "Slip1FirstName": "firstName",
    "Slip1LastName": "lastName",
    "Slip1Initial": "initial",
    "Slip1Address": "address",
    "Slip1Box12": "sin",
    "Slip1EmployersName": "employer",
    "Slip1Box54": "payrollAccount",
}

_BOX_KEY_PATTERN = re.compile(r"^Slip1Box(\d+)$", re.IGNORECASE)
_OTHER_KEY_PATTERN = re.compile(r"^Slip1Box([A-Za-z])$", re.IGNORECASE)
_AMOUNT_KEY_PATTERN = re.compile(r"^Slip1Amount([A-Za-z])$", re.IGNORECASE)


class NormalizationError(ValueError):
    """Raised when raw slip data cannot be normalized."""


Number = Union[int, float]


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _coerce_number(value: Any) -> Number:
    if isinstance(value, bool):
        raise NormalizationError("Boolean values are not valid numeric amounts")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            raise NormalizationError("Empty string cannot be converted to a number")
        try:
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except ValueError as exc:
            raise NormalizationError(f"Unable to convert '{value}' to a number") from exc
    raise NormalizationError(f"Unsupported numeric type: {type(value)!r}")


def _collect_other_info(raw: Dict[str, Any]) -> Dict[str, float]:
    pairs: Dict[str, list[Any]] = {}
    for key, value in raw.items():
        if _is_empty(value) or isinstance(value, bool):
            continue
        box_match = _OTHER_KEY_PATTERN.match(key)
        if box_match:
            suffix = box_match.group(1).upper()
            pairs.setdefault(suffix, [None, None])[0] = str(value)
            continue
        amount_match = _AMOUNT_KEY_PATTERN.match(key)
        if amount_match:
            suffix = amount_match.group(1).upper()
            pairs.setdefault(suffix, [None, None])[1] = value

    other_info: Dict[str, float] = {}
    for suffix, pair in pairs.items():
        box_code, amount = pair
        if box_code is None:
            continue
        if amount is None:
            raise NormalizationError(
                f"Missing amount for other info code '{box_code}' (suffix {suffix})"
            )
        code = str(box_code).strip()
        if not code:
            continue
        other_info[code] = float(_coerce_number(amount))
    return other_info


def normalize_t4_raw_json(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Azure form recognizer output into the strict extract schema."""
    if not isinstance(raw, dict):
        raise NormalizationError("Input must be a dictionary of raw slip values")

    identity: Dict[str, str] = {}
    boxes: Dict[str, Union[Number, str]] = {}

    for key, value in raw.items():
        if isinstance(value, bool) or _is_empty(value):
            continue

        if key in IDENTITY_KEYS:
            field = IDENTITY_KEYS[key]
            text_value = str(value).strip()
            if text_value:
                identity[field] = text_value
            continue

        box_match = _BOX_KEY_PATTERN.match(key)
        if box_match:
            box_number = box_match.group(1)
            if box_number == "10" and isinstance(value, str):
                normalized = value.strip()
                if len(normalized) == 2:
                    boxes[box_number] = normalized
                    continue
            try:
                boxes[box_number] = _coerce_number(value)
            except NormalizationError:
                if box_number == "10":
                    boxes[box_number] = str(value).strip()
                else:
                    raise
            continue

    other_info = _collect_other_info(raw)

    if not identity and not boxes and not other_info:
        raise NormalizationError("No recognizable T4 fields found in payload")

    return {
        "identity": identity,
        "boxes": boxes,
        "otherInfo": other_info,
    }
