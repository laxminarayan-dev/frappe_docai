"""Replaceable semantic extraction providers for V3."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class SemanticProviderError(ValueError):
    """Raised when a semantic provider cannot return schema-valid JSON."""


class SemanticProvider(ABC):
    """Provider contract for schema-driven semantic extraction."""

    @abstractmethod
    def extract(
        self,
        raw_text: str,
        rows: list[dict[str, Any]],
        instructions: str,
        schema: dict[str, Any],
        document_bytes: bytes | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """Return structured JSON matching schema."""


def get_schema_array_fields(schema: dict[str, Any] | None) -> list[str]:
    return [
        field_name
        for field_name, field_schema in (schema or {}).items()
        if isinstance(field_schema, dict)
        and str(field_schema.get("type") or "").lower() in {"array", "list"}
    ]


def build_semantic_prompt(
    raw_text: str,
    rows: list[dict[str, Any]],
    instructions: str,
    schema: dict[str, Any],
) -> str:
    if raw_text or rows:
        source_context = [
            "DOCUMENT OCR:\n" + (raw_text or ""),
            "RECONSTRUCTED TABLE ROWS:\n"
            + json.dumps(rows, ensure_ascii=False),
        ]
    else:
        source_context = [
            "DOCUMENT INPUT:\n"
            "The original document is attached to this request. "
            "Read the attached document directly and use its visual layout, "
            "text, tables, labels, values, and spatial relationships as the "
            "primary source of truth."
        ]

    return "\n\n".join(
        source_context
        + [
            "EXTRACTION INSTRUCTIONS:\n" + (instructions or ""),
            (
                "The output schema is supplied separately as a structured "
                "response schema. Use the OCR text as document evidence and "
                "the reconstructed rows as physical source rows."
            ),
            (
                "Every physical table row must produce exactly one item in "
                "the configured output array. Never merge, duplicate, drop, "
                "or invent physical rows."
            ),
            (
                "Interpret values using the printed table headers and "
                "surrounding document context, not column position alone."
            ),
            (
                "Distinguish carefully between line-level values and "
                "invoice-level values."
            ),
            (
                "If taxes such as CGST, SGST, IGST, VAT, CESS, or other "
                "taxes are printed separately below or outside the item "
                "table, treat them as invoice-level tax evidence unless "
                "the document clearly associates them with a specific "
                "line item."
            ),
            (
                "Record every printed tax component in tax_components when "
                "present. Preserve its printed label, rate, amount, and "
                "whether it is line-level or invoice-level."
            ),
            (
                "Do not distribute an invoice-level tax across individual "
                "line items unless the document explicitly shows that tax "
                "at line level."
            ),
            (
                "Do not assume CGST, SGST, or IGST is present merely because "
                "the document is an Indian invoice. Extract only printed "
                "tax evidence."
            ),
            (
                "Do not treat every tax as GST. Taxes such as CESS, VAT, "
                "service tax, surcharge, or other non-GST taxes must remain "
                "separate tax evidence unless the instructions explicitly "
                "require otherwise."
            ),
            (
                "Do not calculate missing financial values unless the "
                "instructions explicitly require it."
            ),
            (
                "Distinguish printed line amount, taxable/base amount, GST, "
                "and final amount. Do not assume one is another."
            ),
            (
                "A base_amount is taxable/pre-GST only when the document "
                "explicitly supports that meaning."
            ),
            (
                "A total_amount is final including tax only when explicitly "
                "supported by the document."
            ),
            (
                "If GST is absent from a line item, return null for its "
                "line-level GST fields rather than inventing a rate or "
                "amount."
            ),
            (
                "If a tax component is printed at invoice level, preserve "
                "it as invoice-level evidence and do not copy that tax into "
                "each line item."
            ),
            (
                "Return null for values that cannot be reliably established, "
                "preserve printed values, and return only JSON."
            ),
        ]
    )


def to_agent_platform_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert the configured schema to the Agent Platform responseSchema format."""
    if not isinstance(schema, dict):
        raise SemanticProviderError(
            "Configured semantic schema must be a JSON object."
        )

    def convert(value: Any) -> Any:
        if isinstance(value, list):
            return [convert(item) for item in value]

        if not isinstance(value, dict):
            return value

        converted = {}

        for key, item in value.items():
            if key == "type" and isinstance(item, str):
                converted[key] = item.upper()
            else:
                converted[key] = convert(item)

        if (
            converted.get("type") == "OBJECT"
            and isinstance(converted.get("properties"), dict)
        ):
            converted["required"] = list(converted["properties"].keys())

        return converted

    return convert({
        "type": "object",
        "properties": schema,
    })

def build_provider_response_schema(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the provider response schema.

    The configured schema is preserved, while an internal
    tax_components array is added so the semantic model can capture
    printed invoice-level tax evidence such as CGST/SGST/IGST.
    """
    provider_schema = json.loads(json.dumps(schema))

    provider_schema.setdefault(
        "tax_components",
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": (
                            "Printed tax label such as CGST, SGST, IGST, "
                            "VAT, CESS, surcharge, or another tax label."
                        ),
                    },
                    "rate": {
                        "type": "number",
                        "description": (
                            "Printed tax rate percentage. "
                            "Return null if no rate is printed."
                        ),
                    },
                    "amount": {
                        "type": "number",
                        "description": (
                            "Printed tax amount. "
                            "Return null if no amount is printed."
                        ),
                    },
                    "level": {
                        "type": "string",
                        "description": (
                            "Whether the tax is printed at line level "
                            "or invoice level."
                        ),
                    },
                },
            },
        },
    )

    return provider_schema


def _normalize_value(
    value: Any,
    schema: dict[str, Any],
    path: str,
) -> Any:
    field_type = str(schema.get("type") or "").lower()

    if field_type in {"array", "list"} and value is None:
        return []

    if value is None:
        return None

    if field_type in {"string", "str"}:
        if not isinstance(value, str):
            raise SemanticProviderError(
                f"{path} must be a string or null."
            )

        if value.strip().lower() == "null":
            return None

        return value

    if field_type in {"number", "integer", "float"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SemanticProviderError(
                f"{path} must be numeric or null."
            )

        return value

    if field_type in {"array", "list"}:
        if not isinstance(value, list):
            raise SemanticProviderError(
                f"{path} must be an array."
            )

        item_schema = schema.get("items") or {}

        return [
            _normalize_value(
                item,
                item_schema,
                f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]

    if field_type == "object":
        if not isinstance(value, dict):
            raise SemanticProviderError(
                f"{path} must be an object or null."
            )

        return _normalize_object(
            value,
            schema,
            path,
        )

    return value


def _normalize_object(
    value: dict[str, Any],
    schema: dict[str, Any],
    path: str,
) -> dict[str, Any]:
    properties = schema.get("properties") or {}
    normalized = {}

    for field_name, field_schema in properties.items():
        normalized[field_name] = _normalize_value(
            value.get(field_name),
            field_schema if isinstance(field_schema, dict) else {},
            f"{path}.{field_name}",
        )

    return normalized


def parse_semantic_response(
    response: str | dict[str, Any],
    schema: dict[str, Any],
    expected_rows: int | None = None,
) -> dict[str, Any]:
    if isinstance(response, str):
        text = response.strip()

        if text.startswith("```"):
            text = (
                text.split("\n", 1)[-1]
                .rsplit("```", 1)[0]
                .strip()
            )

        try:
            response = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SemanticProviderError(
                "Semantic provider returned invalid JSON."
            ) from exc

    if not isinstance(response, dict):
        raise SemanticProviderError(
            "Semantic provider response must be a JSON object."
        )

    normalized = _normalize_object(
        response,
        {
            "type": "object",
            "properties": schema,
        },
        "$",
    )

    array_fields = get_schema_array_fields(schema)

    if expected_rows is not None and len(array_fields) == 1:
        array_field = array_fields[0]

        if len(normalized[array_field]) != expected_rows:
            raise SemanticProviderError(
                f"Semantic provider returned "
                f"{len(normalized[array_field])} rows; "
                f"expected {expected_rows}."
            )

    return normalized


class VertexAISemanticProvider(SemanticProvider):
    """Google Vertex AI provider using the generative model REST contract."""

    def __init__(
        self,
        connection: dict[str, Any],
        model: str,
        location: str = "us-central1",
        endpoint: str | None = None,
    ):
        self.connection = connection or {}
        self.model = model
        self.location = location or "us-central1"
        self.endpoint = endpoint
        self.last_usage_metadata = None
        self.last_request_time = None
        self.last_raw_response = None

    def _get_access_token(self) -> str:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        service_account_json = self.connection.get("service_account_json")

        if not service_account_json:
            raise SemanticProviderError(
                "Google service-account credentials are required."
            )

        if isinstance(service_account_json, dict):
            credentials = service_account.Credentials.from_service_account_info(
                service_account_json,
                scopes=[CLOUD_PLATFORM_SCOPE],
            )
        else:
            credential_path = str(service_account_json).strip()

            if credential_path.startswith("/private/files/"):
                import frappe

                filename = credential_path[len("/private/files/"):]
                credential_path = frappe.get_site_path(
                    "private",
                    "files",
                    filename,
                )
            elif credential_path.startswith("/files/"):
                import frappe

                filename = credential_path[len("/files/"):]
                credential_path = frappe.get_site_path(
                    "private",
                    "files",
                    filename,
                )

            if not os.path.exists(credential_path):
                raise SemanticProviderError(
                    f"Google service-account file not found: {credential_path}"
                )

            credentials = service_account.Credentials.from_service_account_file(
                credential_path,
                scopes=[CLOUD_PLATFORM_SCOPE],
            )

        credentials.refresh(Request())

        if not credentials.token:
            raise SemanticProviderError(
                "Google credentials did not provide an access token."
            )

        return credentials.token

    def _build_endpoint(self) -> str:
        project_id = (
            self.connection.get("google_cloud_project_id")
            or self.connection.get("project_id")
        )

        if not project_id:
            raise SemanticProviderError(
                "Google Cloud project ID is required for Vertex AI."
            )

        if self.endpoint:
            return self.endpoint.format(
                project_id=project_id,
                location=self.location,
                model=self.model,
            )

        service_endpoint = (
            "https://aiplatform.googleapis.com"
            if self.location == "global"
            else f"https://{self.location}-aiplatform.googleapis.com"
        )

        return (
            f"{service_endpoint}/v1/projects/{project_id}"
            f"/locations/{self.location}"
            f"/publishers/google/models/{self.model}:generateContent"
        )

    def extract(
        self,
        raw_text: str,
        rows: list[dict[str, Any]],
        instructions: str,
        schema: dict[str, Any],
        document_bytes: bytes | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        prompt = build_semantic_prompt(
            raw_text,
            rows,
            instructions,
            schema,
        )

        # The configured schema is expanded only for the provider so that
        # internal tax evidence can be captured without exposing it as part
        # of the configured/output schema.
        provider_schema = build_provider_response_schema(schema)

        parts = []

        if document_bytes:
            if not mime_type:
                raise SemanticProviderError(
                    "Document MIME type is required when document bytes are supplied."
                )

            parts.append(
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64.b64encode(document_bytes).decode("ascii"),
                    }
                }
            )

        parts.append(
            {
                "text": prompt,
            }
        )

        request_body = {
            "contents": [
                {
                    "role": "user",
                    "parts": parts,
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": to_agent_platform_schema(
                    provider_schema
                ),
            },
        }

        request = urllib.request.Request(
            self._build_endpoint(),
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._get_access_token()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        request_start = time.perf_counter()

        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            self.last_request_time = (
                time.perf_counter() - request_start
            )

            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = ""

            raise SemanticProviderError(
                f"Vertex AI semantic extraction HTTP {exc.code}: "
                f"{error_body[:2000]}"
            ) from exc

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            self.last_request_time = (
                time.perf_counter() - request_start
            )

            raise SemanticProviderError(
                f"Vertex AI semantic extraction request failed: {exc}"
            ) from exc

        self.last_request_time = (
            time.perf_counter() - request_start
        )

        self.last_raw_response = payload

        self.last_usage_metadata = payload.get(
            "usageMetadata"
        )

        try:
            response_text = (
                payload["candidates"][0]["content"]["parts"][0]["text"]
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise SemanticProviderError(
                "Vertex AI returned no semantic JSON content."
            ) from exc

        return parse_semantic_response(
            response_text,
            provider_schema,
            expected_rows=len(rows) if rows else None,
        )


def create_semantic_provider(
    configuration: dict[str, Any],
    connection: dict[str, Any],
) -> SemanticProvider:
    provider_name = (
        str(
            configuration.get("semantic_provider")
            or "vertex_ai"
        )
        .lower()
        .replace(" ", "_")
    )

    if provider_name in {
        "vertex_ai",
        "vertex",
        "google_vertex_ai",
        "google_agent_platform",
    }:
        return VertexAISemanticProvider(
            connection=connection,
            model=configuration.get("semantic_model")
            or "gemini-2.5-flash",
            location=configuration.get("semantic_location")
            or "us-central1",
            endpoint=configuration.get("semantic_endpoint"),
        )

    raise SemanticProviderError(
        f"Unsupported semantic provider: {provider_name}"
    )