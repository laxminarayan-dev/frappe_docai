"""Generic semantic extraction layer."""

from __future__ import annotations

from typing import Any

from .semantic_provider import SemanticProvider, get_schema_array_fields


class SemanticExtractor:
    """Generic extractor contract for config-driven document processing.

    This implementation intentionally stays provider-agnostic and works from the normalized OCR
    document and reconstructed rows. It does not hard-code any specific business document format.
    """

    def __init__(self, configuration: dict[str, Any] | None = None, provider: SemanticProvider | None = None):
        self.configuration = configuration or {}
        self.provider = provider

    def build_context(self, document: dict[str, Any], rows: list[dict[str, Any]] | None = None):
        document = document or {}
        return {
            "document": document,
            "raw_text": document.get("raw_text") or "",
            "pages": document.get("pages") or [],
            "rows": rows or document.get("rows") or document.get("reconstructed_rows") or [],
            "spatial": document.get("spatial") or {},
            "instructions": self.configuration.get("extraction_instructions") or "",
        }

    def _coerce_value(self, value: Any, field_type: str | None = None):
        if value is None:
            return None
        if field_type and field_type.lower() == "number":
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip().replace(",", "")
            try:
                return float(text)
            except ValueError:
                return text
        if field_type and field_type.lower() == "date":
            return str(value).strip()
        return str(value).strip()

    def _extract_item_property(self, row: dict[str, Any], field_name: str, field_type: str | None = None):
        cells = row.get("cells") or []
        normalized_name = str(field_name).lower().replace("_", " ")
        for cell in cells:
            column_name = str(cell.get("column_name") or "").lower().replace("_", " ")
            cell_text = str(cell.get("text") or "").strip()
            if not cell_text:
                continue
            if normalized_name == column_name:
                return self._coerce_value(cell_text, field_type)

        return None

    def _extract_array(self, field_name: str, field_schema: dict[str, Any], rows: list[dict[str, Any]], raw_text: str):
        item_schema = field_schema.get("items") or {}
        item_properties = (item_schema.get("properties") or {}) if isinstance(item_schema, dict) else {}
        extracted_rows: list[dict[str, Any]] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            item: dict[str, Any] = {}
            for prop_name, prop_schema in item_properties.items():
                value = self._extract_item_property(row, prop_name, str((prop_schema or {}).get("type") or "string").lower())
                if value is not None:
                    item[prop_name] = value
            extracted_rows.append(item)

        return extracted_rows

    def _extract_scalar(self, field_name: str, field_schema: dict[str, Any], raw_text: str, rows: list[dict[str, Any]]):
        field_type = str((field_schema or {}).get("type") or "string").lower()
        normalized_name = field_name.lower().replace("_", " ")
        for row in rows:
            for cell in row.get("cells") or []:
                column_name = str(cell.get("column_name") or "").lower().replace("_", " ")
                cell_text = str(cell.get("text") or "").strip()
                if cell_text and normalized_name == column_name:
                    return self._coerce_value(cell_text, field_type)

        return None

    def extract(self, context: dict[str, Any], schema: dict[str, Any] | None = None, instructions: str | None = None):
        context = context or {}
        schema = schema or {}
        rows = context.get("rows") or context.get("reconstructed_rows") or []
        raw_text = context.get("raw_text") or context.get("document_text") or ""
        prompt = instructions or self.configuration.get("extraction_instructions") or context.get("instructions") or ""
        extraction_context = dict(context)
        extraction_context.update(
            {
                "raw_text": raw_text,
                "rows": rows,
                "schema": schema,
                "instructions": prompt,
            }
        )

        if self.provider is not None:
            provider_kwargs = {
                "raw_text": raw_text,
                "rows": rows,
                "instructions": prompt,
                "schema": schema,
            }

            if context.get("document_bytes") is not None:
                provider_kwargs["document_bytes"] = context.get("document_bytes")

            if context.get("mime_type") is not None:
                provider_kwargs["mime_type"] = context.get("mime_type")

            return self.provider.extract(**provider_kwargs)

        if not schema:
            return {
                "schema": {},
                "instructions": prompt,
                "document": extraction_context,
            }

        result: dict[str, Any] = {"schema": schema, "instructions": prompt, "document": extraction_context}

        for field_name, field_schema in schema.items():
            if not isinstance(field_schema, dict):
                continue

            field_type = str(field_schema.get("type") or "").lower()
            if field_type in {"array", "list"}:
                result[field_name] = self._extract_array(field_name, field_schema, rows, raw_text)
                continue

            if field_type == "object":
                obj_props = field_schema.get("properties") or {}
                if obj_props:
                    result[field_name] = self.extract({"raw_text": raw_text, "rows": rows}, schema=obj_props, instructions=prompt)
                    continue

            value = self._extract_scalar(field_name, field_schema, raw_text, rows)
            if value is not None:
                result[field_name] = value

        return result
