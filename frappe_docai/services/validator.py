"""Validation layer for OCR-to-structure-to-extraction workflows."""

from __future__ import annotations

from typing import Any


def validate_extraction(
    extracted: dict[str, Any],
    detected_rows: int | None = None,
    item_field: str = "items",
    required_fields: list[str] | None = None,
    numeric_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Validate semantic extraction against structural OCR findings.

    This intentionally keeps validation rules modular so additional checks can be added later.
    """
    required_fields = required_fields or []
    numeric_fields = numeric_fields or []
    result = {"valid": True, "reason": None}

    if detected_rows is not None and item_field in extracted:
        extracted_items = extracted.get(item_field) or []
        if isinstance(extracted_items, list):
            extracted_count = len(extracted_items)
            if extracted_count != detected_rows:
                return {
                    "valid": False,
                    "reason": "ITEM_COUNT_MISMATCH",
                    "detected_rows": detected_rows,
                    "extracted_items": extracted_count,
                }

    for required_field in required_fields:
        if required_field not in extracted:
            return {"valid": False, "reason": "MISSING_REQUIRED_FIELD", "field": required_field}

    for numeric_field in numeric_fields:
        if numeric_field in extracted and extracted.get(numeric_field) is not None:
            try:
                float(extracted[numeric_field])
            except (TypeError, ValueError):
                return {"valid": False, "reason": "INVALID_NUMERIC_VALUE", "field": numeric_field}

    return result
