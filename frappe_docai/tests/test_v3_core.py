from pathlib import Path
import json
import importlib
import sys
import types

import pytest

from frappe_docai.services.extractor import SemanticExtractor, get_schema_array_fields
from frappe_docai.services.financial_validator import validate_and_correct
from frappe_docai.services.google_vision import GoogleVisionOCRService
from frappe_docai.services.ocr_normalizer import normalize_vision_response
from frappe_docai.services.semantic_provider import (
    CLOUD_PLATFORM_SCOPE,
    SemanticProvider,
    SemanticProviderError,
    build_semantic_prompt,
    create_semantic_provider,
    parse_semantic_response,
    to_agent_platform_schema,
)
import frappe_docai.services.semantic_provider as semantic_provider_module
from frappe_docai.services.table_reconstructor import TableReconstructor
from frappe_docai.services.validator import validate_extraction


def make_word(text, x, y, width, height, confidence=0.96):
    return {
        "text": text,
        "confidence": confidence,
        "boundingBox": {
            "vertices": [
                {"x": x, "y": y},
                {"x": x + width, "y": y},
                {"x": x + width, "y": y + height},
                {"x": x, "y": y + height},
            ]
        },
    }


def sample_vision_response():
    rows = [
        [
            make_word("Emergency", 30, 180, 150, 22),
            make_word("Area", 190, 180, 90, 22),
            make_word("Board", 290, 180, 90, 22),
            make_word("(Sun", 390, 180, 55, 22),
            make_word("Board)", 455, 180, 70, 22),
            make_word("36\"", 560, 180, 55, 22),
            make_word("x", 620, 180, 18, 22),
            make_word("30\"", 650, 180, 45, 22),
            make_word("3", 760, 180, 15, 22),
            make_word("3.1", 820, 180, 40, 22),
            make_word("10044.00", 900, 180, 90, 22),
        ],
        [
            make_word("Anti", 30, 230, 80, 22),
            make_word("Ragging", 120, 230, 100, 22),
            make_word("Board", 233, 230, 90, 22),
            make_word("(Sun", 330, 230, 55, 22),
            make_word("Board)", 395, 230, 70, 22),
            make_word("18\"", 478, 230, 50, 22),
            make_word("x", 540, 230, 18, 22),
            make_word("24\"", 570, 230, 45, 22),
            make_word("4", 760, 230, 15, 22),
            make_word("3.1", 820, 230, 40, 22),
            make_word("5357.00", 900, 230, 90, 22),
        ],
        [
            make_word("TOTAL", 660, 300, 80, 22),
            make_word("10000.00", 900, 300, 90, 22),
        ],
    ]

    words = []
    for row in rows:
        for word in row:
            words.append(word)

    return {
        "responses": [
            {
                "fullTextAnnotation": {
                    "text": "Emergency Area Board (Sun Board) 36\" x 30\" 3 3.1 10044.00\nAnti Ragging Board (Sun Board) 18\" x 24\" 4 3.1 5357.00\nTOTAL 10000.00",
                    "pages": [
                        {
                            "blocks": [{"paragraphs": [{"words": words}]}],
                            "width": 1200,
                            "height": 500,
                        }
                    ],
                }
            }
        ]
    }


def test_normalize_vision_response_keeps_spatial_data():
    normalized = normalize_vision_response(sample_vision_response())
    assert normalized["raw_text"]
    assert normalized["pages"][0]["words"][0]["text"] == "Emergency"
    assert "bbox" in normalized["pages"][0]["words"][0]


def test_row_reconstruction_preserves_multiple_line_items():
    words = sample_vision_response()["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"]
    rows = TableReconstructor(words).reconstruct_rows()
    assert len(rows) == 2
    assert rows[0]["cells"][0]["text"].startswith("Emergency")
    assert rows[0]["cells"][-1]["text"] == "10044.00"
    assert rows[1]["cells"][-1]["text"] == "5357.00"


def test_row_reconstruction_uses_normalized_bbox_for_two_physical_rows():
    normalized = normalize_vision_response(sample_vision_response())

    rows = TableReconstructor(normalized["pages"][0]["words"]).reconstruct_rows()

    assert len(rows) == 2


def test_row_reconstruction_keeps_one_physical_row_together():
    words = sample_vision_response()["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"][:11]

    rows = TableReconstructor(words).reconstruct_rows()

    assert len(rows) == 1
    assert rows[0]["cells"][0]["text"] == 'Emergency Area Board (Sun Board) 36" x 30"'


def test_row_reconstruction_detects_three_physical_rows():
    words = sample_vision_response()["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"]
    third_row = [make_word("Third", 30, 280, 70, 22), make_word("Item", 110, 280, 60, 22), make_word("7", 760, 280, 15, 22), make_word("4.2", 820, 280, 35, 22), make_word("800.00", 900, 280, 80, 22)]

    rows = TableReconstructor(words[:22] + third_row).reconstruct_rows()

    assert len(rows) == 3


def test_row_reconstruction_preserves_spaced_dimensions_and_numeric_association():
    words = sample_vision_response()["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"]

    rows = TableReconstructor(words).reconstruct_rows()

    assert rows[0]["cells"][0]["text"].endswith('36" x 30"')
    assert rows[0]["cells"][-3]["text"] == "3"
    assert rows[0]["cells"][-2]["text"] == "3.1"
    assert rows[0]["cells"][-1]["text"] == "10044.00"
    assert rows[1]["cells"][0]["text"].endswith('18" x 24"')
    assert rows[1]["cells"][-3]["text"] == "4"
    assert rows[1]["cells"][-2]["text"] == "3.1"
    assert rows[1]["cells"][-1]["text"] == "5357.00"


def test_column_assignment_uses_spatial_positions():
    words = sample_vision_response()["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"]
    rows = TableReconstructor(words).reconstruct_rows()
    first_row = rows[0]
    qty = [cell for cell in first_row["cells"] if cell["column_name"] == "qty"][0]
    rate = [cell for cell in first_row["cells"] if cell["column_name"] == "rate"][0]
    amount = [cell for cell in first_row["cells"] if cell["column_name"] == "amount"][0]
    assert qty["text"] == "3"
    assert rate["text"] == "3.1"
    assert amount["text"] == "10044.00"


def test_totals_are_not_treated_as_line_items():
    words = sample_vision_response()["responses"][0]["fullTextAnnotation"]["pages"][0]["blocks"][0]["paragraphs"][0]["words"]
    rows = TableReconstructor(words).reconstruct_rows()
    line_items = [row for row in rows if row.get("is_line_item")]
    assert len(line_items) == 2
    assert all("TOTAL" not in cell["text"] for row in line_items for cell in row["cells"])


def test_schema_validation_detects_item_count_mismatch():
    result = validate_extraction(
        {"items": [{"description": "A"}, {"description": "B"}]},
        detected_rows=3,
        item_field="items",
    )
    assert result["valid"] is False
    assert result["reason"] == "ITEM_COUNT_MISMATCH"


def test_schema_validation_accepts_matching_items():
    result = validate_extraction(
        {"items": [{"description": "A"}, {"description": "B"}]},
        detected_rows=2,
        item_field="items",
    )
    assert result["valid"] is True


def test_semantic_extractor_builds_dynamic_item_array_from_schema_and_rows():
    schema = {
        "supplier": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "qty": {"type": "number"},
                    "rate": {"type": "number"},
                    "amount": {"type": "number"},
                },
            },
        },
    }
    rows = [
        {"cells": [{"column_name": "description", "text": "Emergency Area Board (Sun Board) 36\" x 30\""}, {"column_name": "qty", "text": "3"}, {"column_name": "rate", "text": "3.1"}, {"column_name": "amount", "text": "10044.00"}]},
        {"cells": [{"column_name": "description", "text": "Anti Ragging Board (Sun Board) 18\" x 24\""}, {"column_name": "qty", "text": "4"}, {"column_name": "rate", "text": "3.1"}, {"column_name": "amount", "text": "5357.00"}]},
    ]
    result = SemanticExtractor().extract({"raw_text": "Sample", "rows": rows}, schema=schema, instructions="Extract all line items.")
    assert len(result["items"]) == 2
    assert result["items"][0]["description"].startswith("Emergency")
    assert result["items"][1]["qty"] == 4


def test_semantic_extractor_validates_any_configured_array_field():
    rows = [
        {"cells": [{"column_name": "description", "text": "A"}]},
        {"cells": [{"column_name": "description", "text": "B"}]},
    ]

    for field_name in ("items", "line_items", "products"):
        schema = {
            field_name: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}},
                },
            }
        }
        result = SemanticExtractor().extract({"raw_text": "", "rows": rows}, schema=schema)
        validation = validate_extraction(
            result,
            detected_rows=len(rows),
            item_field=get_schema_array_fields(schema)[0],
        )

        assert len(result[field_name]) == 2
        assert validation["valid"] is True


def test_semantic_extractor_does_not_invent_items_without_array_schema():
    schema = {"supplier": {"type": "string"}}
    result = SemanticExtractor().extract(
        {"raw_text": "Sample", "rows": [{"cells": [{"column_name": "description", "text": "A"}]}]},
        schema=schema,
    )

    assert "items" not in result
    assert get_schema_array_fields(schema) == []


def test_semantic_extractor_does_not_infer_unmapped_semantic_fields():
    schema = {
        "vendor_name": {"type": "string"},
        "total_amount": {"type": "number"},
        "tax_amount": {"type": "number"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "particular": {"type": "string"},
                    "base_amount": {"type": "number"},
                    "gst_amount": {"type": "number"},
                    "total_amount": {"type": "number"},
                },
            },
        },
    }
    rows = [
        {
            "row_index": 0,
            "cells": [
                {"column_name": "description", "text": "A"},
                {"column_name": "qty", "text": "3"},
                {"column_name": "rate", "text": "3.1"},
                {"column_name": "amount", "text": "10044.00"},
            ],
        },
        {
            "row_index": 1,
            "cells": [
                {"column_name": "description", "text": "B"},
                {"column_name": "qty", "text": "4"},
                {"column_name": "rate", "text": "3.1"},
                {"column_name": "amount", "text": "5357.00"},
            ],
        },
    ]

    result = SemanticExtractor().extract(
        {"raw_text": "complete OCR text", "rows": rows},
        schema=schema,
        instructions="Extract structured values.",
    )

    assert len(result["line_items"]) == 2
    assert result["line_items"] == [{}, {}]
    assert "vendor_name" not in result
    assert "total_amount" not in result
    assert "tax_amount" not in result


def test_semantic_extractor_preserves_raw_text_rows_and_schema_context():
    schema = {"products": {"type": "array", "items": {"type": "object", "properties": {}}}}
    rows = [{"row_index": 0, "cells": [{"column_name": "amount", "text": "10"}]}]

    result = SemanticExtractor().extract(
        {"raw_text": "complete document OCR", "rows": rows, "pages": [{"page_index": 0}]},
        schema=schema,
        instructions="Preserve context.",
    )

    assert result["document"]["raw_text"] == "complete document OCR"
    assert result["document"]["rows"] == rows
    assert result["document"]["pages"] == [{"page_index": 0}]
    assert result["document"]["schema"] == schema
    assert result["document"]["instructions"] == "Preserve context."


def test_multiple_schema_arrays_do_not_select_a_validation_field():
    schema = {
        "products": {"type": "array", "items": {"type": "object", "properties": {}}},
        "taxes": {"type": "array", "items": {"type": "object", "properties": {}}},
    }
    rows = [{"row_index": 0, "cells": []}, {"row_index": 1, "cells": []}]
    result = SemanticExtractor().extract({"raw_text": "", "rows": rows}, schema=schema)

    array_fields = get_schema_array_fields(schema)
    validation = validate_extraction(
        result,
        detected_rows=None,
        item_field=None,
    )

    assert array_fields == ["products", "taxes"]
    assert validation["valid"] is True


def financial_schema():
    return {
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "particular": {"type": "string"},
                    "base_amount": {"type": "number"},
                    "gst_percent": {"type": "number"},
                    "gst_amount": {"type": "number"},
                    "total_amount": {"type": "number"},
                },
            },
        }
    }


def test_financial_validator_handles_invoice_level_cgst_sgst():
    extracted = {
        "line_items": [{"base_amount": 10044}, {"base_amount": 5357}],
        "subtotal": 15401,
        "tax_components": [
            {"name": "CGST", "rate": 9, "amount": 1386.09},
            {"name": "SGST", "rate": 9, "amount": 1386.09},
        ],
        "tax_amount": 2772.18,
        "total_amount": 18173.18,
    }

    result = validate_and_correct(extracted, financial_schema())

    assert result["data"]["line_items"] == [
        {"base_amount": 10044, "gst_percent": 0, "gst_amount": 0, "total_amount": 10044},
        {"base_amount": 5357, "gst_percent": 0, "gst_amount": 0, "total_amount": 5357},
    ]
    assert result["financial_validation"]["calculated_tax"] == 2772.18
    assert result["financial_validation"]["calculated_grand_total"] == 18173.18
    assert result["data"]["subtotal"] == 15401


def test_financial_validator_preserves_correct_line_level_gst():
    extracted = {"line_items": [{"base_amount": 1000, "gst_percent": 18, "gst_amount": 180, "total_amount": 1180}], "tax_amount": 180, "total_amount": 1180}

    result = validate_and_correct(extracted, financial_schema())

    assert result["data"]["line_items"][0] == {"base_amount": 1000, "gst_percent": 18, "gst_amount": 180, "total_amount": 1180}
    assert result["financial_validation"]["corrected"] is False


def test_financial_validator_corrects_wrong_line_total():
    result = validate_and_correct(
        {"line_items": [{"base_amount": 1000, "gst_percent": 18, "gst_amount": 180, "total_amount": 1000}]},
        financial_schema(),
    )

    assert result["data"]["line_items"][0]["total_amount"] == 1180


def test_financial_validator_corrects_wrong_gst_amount_and_total():
    result = validate_and_correct(
        {"line_items": [{"base_amount": 1000, "gst_percent": 18, "gst_amount": 100, "total_amount": 1100}]},
        financial_schema(),
    )

    assert result["data"]["line_items"][0]["gst_amount"] == 180
    assert result["data"]["line_items"][0]["total_amount"] == 1180


def test_financial_validator_defaults_missing_gst_to_zero():
    result = validate_and_correct({"line_items": [{"base_amount": 1000}]}, financial_schema())

    assert result["data"]["line_items"][0] == {"base_amount": 1000, "gst_percent": 0, "gst_amount": 0, "total_amount": 1000}
    assert result["data"]["tax_amount"] == 0
    assert result["data"]["total_amount"] == 1000


def test_financial_validator_handles_invoice_level_igst():
    result = validate_and_correct(
        {
            "line_items": [{"base_amount": 10000}],
            "tax_components": [{"name": "IGST", "rate": 18, "amount": 1800}],
            "tax_amount": 0,
            "total_amount": 10000,
        },
        financial_schema(),
    )

    assert result["data"]["tax_amount"] == 1800
    assert result["data"]["total_amount"] == 11800
    assert result["data"]["line_items"][0]["gst_amount"] == 0


def test_financial_validator_sums_multiple_invoice_tax_components():
    result = validate_and_correct(
        {
            "line_items": [{"base_amount": 10000}],
            "tax_components": [
                {"name": "CGST", "amount": 900},
                {"name": "SGST", "amount": 900},
                {"name": "CESS", "amount": 100},
            ],
            "tax_amount": 1,
            "total_amount": 1,
        },
        financial_schema(),
    )

    assert result["data"]["tax_amount"] == 1900
    assert result["data"]["total_amount"] == 11900


def test_financial_validator_corrects_grand_total_and_tax_total():
    result = validate_and_correct(
        {
            "line_items": [{"base_amount": 1000, "gst_percent": 18, "gst_amount": 180, "total_amount": 1180}],
            "tax_amount": 99,
            "total_amount": 99,
        },
        financial_schema(),
    )

    assert result["data"]["tax_amount"] == 180
    assert result["data"]["total_amount"] == 1180


def test_financial_validator_removes_model_distributed_invoice_tax():
    extracted = {
        "line_items": [
            {"base_amount": 10044, "gst_percent": 9, "gst_amount": 903.96, "total_amount": 10044},
            {"base_amount": 5357, "gst_percent": 9, "gst_amount": 482.13, "total_amount": 5357},
        ],
        "tax_components": [{"name": "CGST", "rate": 9, "amount": 1386.09}, {"name": "SGST", "rate": 9, "amount": 1386.09}],
    }
    result = validate_and_correct(extracted, financial_schema())

    assert all(item["gst_percent"] == 0 and item["gst_amount"] == 0 for item in result["data"]["line_items"])
    assert all(item["total_amount"] == item["base_amount"] for item in result["data"]["line_items"])
    assert result["data"]["tax_amount"] == 2772.18
    assert result["data"]["total_amount"] == 18173.18
    assert extracted["line_items"][0]["gst_amount"] == 903.96


def test_financial_validator_reconciles_invoice_tax_without_components():
    extracted = {
        "line_items": [
            {"base_amount": 10044, "gst_percent": 9, "gst_amount": 903.96, "total_amount": 10044},
            {"base_amount": 5357, "gst_percent": 9, "gst_amount": 482.13, "total_amount": 5357},
        ],
        "tax_amount": 2772.18,
        "total_amount": 18173.18,
    }

    result = validate_and_correct(extracted, financial_schema())

    assert result["data"]["line_items"][0]["gst_percent"] == 0
    assert result["data"]["line_items"][0]["gst_amount"] == 0
    assert result["data"]["line_items"][0]["total_amount"] == 10044
    assert result["data"]["tax_amount"] == 2772.18
    assert result["data"]["total_amount"] == 18173.18


class RecordingSemanticProvider(SemanticProvider):
    def __init__(self, response):
        self.response = response
        self.received = None

    def extract(self, raw_text, rows, instructions, schema):
        self.received = {
            "raw_text": raw_text,
            "rows": rows,
            "instructions": instructions,
            "schema": schema,
        }
        return parse_semantic_response(self.response, schema, expected_rows=len(rows))


def test_semantic_provider_receives_complete_context_and_is_replaceable():
    schema = {
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"description": {"type": "string"}},
            },
        }
    }
    rows = [{"row_index": 0, "cells": [{"column_name": "description", "text": "A"}]}]
    provider = RecordingSemanticProvider('{"line_items": [{"description": "A"}]}')

    result = SemanticExtractor(provider=provider).extract(
        {"raw_text": "complete OCR", "rows": rows},
        schema=schema,
        instructions="Extract every physical row.",
    )

    assert result["line_items"] == [{"description": "A"}]
    assert provider.received == {
        "raw_text": "complete OCR",
        "rows": rows,
        "instructions": "Extract every physical row.",
        "schema": schema,
    }


def test_semantic_provider_prompt_contains_all_required_inputs():
    prompt = build_semantic_prompt(
        "complete OCR",
        [{"row_index": 0, "cells": []}],
        "Use exact identifiers.",
        {"products": {"type": "ARRAY"}},
    )

    assert "DOCUMENT OCR:" in prompt
    assert "complete OCR" in prompt
    assert "RECONSTRUCTED TABLE ROWS:" in prompt
    assert "EXTRACTION INSTRUCTIONS:" in prompt
    assert "Use exact identifiers." in prompt
    assert "response schema" in prompt
    assert "Do not calculate missing financial values" in prompt


def test_agent_platform_schema_conversion_preserves_configured_structure():
    schema = {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"quantity": {"type": "number"}},
            },
        }
    }

    assert to_agent_platform_schema(schema) == {
        "type": "OBJECT",
        "properties": {
            "products": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {"quantity": {"type": "NUMBER"}},
                },
            }
        },
    }


def test_agent_platform_request_includes_json_response_schema(monkeypatch):
    captured = {}
    schema = {
        "products": {
            "type": "array",
            "items": {"type": "object", "properties": {"name": {"type": "string"}}},
        }
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": '{"products": [{"name": "A"}]}' }]}}]}).encode()

    def urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(semantic_provider_module.urllib.request, "urlopen", urlopen)
    provider = create_semantic_provider(
        {"semantic_provider": "google_agent_platform", "semantic_model": "demo", "semantic_location": "global"},
        {"google_cloud_project_id": "demo-project"},
    )
    monkeypatch.setattr(provider, "_get_access_token", lambda: "token")

    result = provider.extract("OCR", [{"row_index": 0, "cells": []}], "Extract rows.", schema)
    body = json.loads(captured["request"].data.decode())

    assert result == {
        "products": [{"name": "A"}],
        "tax_components": [],
    }
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"] == to_agent_platform_schema(semantic_provider_module.build_provider_response_schema(schema))
    assert "OCR" in body["contents"][0]["parts"][0]["text"]


def test_reconstructed_rows_preserve_spatial_context_for_provider():
    normalized = normalize_vision_response(sample_vision_response())
    rows = TableReconstructor(normalized["pages"][0]["words"]).reconstruct_rows()

    assert rows[0]["page_index"] == 0
    assert rows[0]["bbox"]["top"] == 180.0
    assert rows[0]["words"][0]["bbox"]["left"] == 30.0
    assert rows[0]["words"][0]["y_center"] == 191.0


def test_semantic_provider_rejects_invalid_json():
    with pytest.raises(SemanticProviderError, match="invalid JSON"):
        parse_semantic_response("not json", {"items": {"type": "ARRAY"}})


def test_semantic_provider_accepts_google_agent_platform_alias_and_configuration():
    configuration = {
        "semantic_provider": "google_agent_platform",
        "semantic_model": "gemini-3.5-flash",
        "semantic_location": "global",
    }

    provider = create_semantic_provider(configuration, {"service_account_json": "/private/files/account.json"})

    assert isinstance(provider, type(create_semantic_provider({"semantic_provider": "vertex"}, {})))
    assert provider.model == "gemini-3.5-flash"
    assert provider.location == "global"


def test_semantic_provider_accepts_existing_aliases():
    for alias in ("vertex_ai", "vertex", "google_vertex_ai"):
        provider = create_semantic_provider(
            {"semantic_provider": alias, "semantic_model": "gemini-3.5-flash", "semantic_location": "global"},
            {},
        )

        assert provider.model == "gemini-3.5-flash"
        assert provider.location == "global"


def test_semantic_provider_builds_global_endpoint():
    provider = create_semantic_provider(
        {
            "semantic_provider": "google_agent_platform",
            "semantic_model": "gemini-3.5-flash",
            "semantic_location": "global",
        },
        {"google_cloud_project_id": "demo-project"},
    )

    assert provider._build_endpoint() == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/global/"
        "publishers/google/models/gemini-3.5-flash:generateContent"
    )


def test_semantic_provider_builds_regional_endpoint():
    provider = create_semantic_provider(
        {
            "semantic_provider": "google_agent_platform",
            "semantic_model": "gemini-3.5-flash",
            "semantic_location": "us-central1",
        },
        {"google_cloud_project_id": "demo-project"},
    )

    assert provider._build_endpoint() == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/demo-project/locations/us-central1/"
        "publishers/google/models/gemini-3.5-flash:generateContent"
    )


def test_semantic_provider_rejects_unsupported_alias():
    with pytest.raises(SemanticProviderError, match="Unsupported semantic provider"):
        create_semantic_provider({"semantic_provider": "unknown_provider"}, {})


def test_semantic_provider_rejects_schema_mismatch_and_preserves_row_count():
    schema = {"products": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {}}}}

    with pytest.raises(SemanticProviderError, match="expected 2"):
        parse_semantic_response('{"products": [{}]}', schema, expected_rows=2)


def test_semantic_provider_returns_null_for_unresolved_values_without_guessing():
    schema = {
        "line_items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING"},
                    "base_amount": {"type": "NUMBER"},
                    "gst_amount": {"type": "NUMBER"},
                    "total_amount": {"type": "NUMBER"},
                },
            },
        }
    }

    result = parse_semantic_response(
        '{"line_items": [{"description": "A"}, {"description": "B"}]}',
        schema,
        expected_rows=2,
    )

    assert result == {
        "line_items": [
            {"description": "A", "base_amount": None, "gst_amount": None, "total_amount": None},
            {"description": "B", "base_amount": None, "gst_amount": None, "total_amount": None},
        ]
    }


def test_semantic_provider_converts_literal_null_strings_to_null():
    result = parse_semantic_response(
        '{"vendor_name": "null", "line_items": []}',
        {"vendor_name": {"type": "STRING"}, "line_items": {"type": "ARRAY"}},
    )

    assert result["vendor_name"] is None


def test_google_vision_reads_service_account_from_private_attach_file(monkeypatch, tmp_path):
    fake_frappe = types.SimpleNamespace(get_site_path=lambda *parts: str(tmp_path / parts[-1]))
    monkeypatch.setitem(sys.modules, "frappe", fake_frappe)

    payload = {
        "type": "service_account",
        "project_id": "demo-project",
        "private_key_id": "abc123",
        "private_key": "-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----\n",
        "client_email": "demo@demo-project.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    json_path = tmp_path / "demo-service-account.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    fake_google = types.ModuleType("google")
    fake_oauth2 = types.ModuleType("google.oauth2")
    fake_service_account = types.ModuleType("google.oauth2.service_account")

    class DummyCredentials:
        def __init__(self, info, scopes=None):
            self.info = info
            self.scopes = scopes

        @classmethod
        def from_service_account_info(cls, info, **kwargs):
            return cls(info, scopes=kwargs.get("scopes"))

    fake_service_account.Credentials = DummyCredentials
    fake_oauth2.service_account = fake_service_account
    fake_google.oauth2 = fake_oauth2

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.oauth2", fake_oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", fake_service_account)

    service = GoogleVisionOCRService(connection={"service_account_json": "/private/files/demo-service-account.json"})
    credentials = service.get_credentials()

    assert credentials.info["project_id"] == "demo-project"
    assert credentials.info["client_email"].endswith("@demo-project.iam.gserviceaccount.com")
    assert credentials.scopes is None


def test_semantic_provider_requests_cloud_platform_scope(monkeypatch):
    requested = {}

    fake_google = types.ModuleType("google")
    fake_auth = types.ModuleType("google.auth")
    fake_transport = types.ModuleType("google.auth.transport")
    fake_requests = types.ModuleType("google.auth.transport.requests")
    fake_oauth2 = types.ModuleType("google.oauth2")
    fake_service_account = types.ModuleType("google.oauth2.service_account")

    class DummyRequest:
        pass

    class DummyCredentials:
        token = "access-token"

        def refresh(self, request):
            requested["request"] = request

    def from_service_account_file(filename, scopes=None):
        requested["filename"] = filename
        requested["scopes"] = scopes
        return DummyCredentials()

    fake_requests.Request = DummyRequest
    fake_transport.requests = fake_requests
    fake_auth.transport = fake_transport
    fake_google.auth = fake_auth
    fake_google.oauth2 = fake_oauth2
    fake_oauth2.service_account = fake_service_account
    fake_service_account.Credentials = types.SimpleNamespace(
        from_service_account_file=from_service_account_file
    )

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.auth", fake_auth)
    monkeypatch.setitem(sys.modules, "google.auth.transport", fake_transport)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", fake_requests)
    monkeypatch.setitem(sys.modules, "google.oauth2", fake_oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", fake_service_account)

    credential_path = "/tmp/test-service-account.json"
    Path(credential_path).write_text("{}")

    provider = create_semantic_provider(
        {
            "semantic_provider": "google_agent_platform",
            "semantic_model": "gemini-3.5-flash",
            "semantic_location": "global",
        },
        {
            "service_account_json": credential_path,
        },
    )

    token = provider._get_access_token()

    assert token == "access-token"
    assert requested["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]
    assert isinstance(requested["request"], DummyRequest)


def test_google_vision_credentials_accept_explicit_scope(monkeypatch):
    captured = {}
    fake_frappe = types.SimpleNamespace(get_site_path=lambda *parts: "/tmp/demo-service-account.json")
    monkeypatch.setitem(sys.modules, "frappe", fake_frappe)

    fake_google = types.ModuleType("google")
    fake_oauth2 = types.ModuleType("google.oauth2")
    fake_service_account = types.ModuleType("google.oauth2.service_account")

    class DummyCredentials:
        @classmethod
        def from_service_account_info(cls, info, **kwargs):
            captured["info"] = info
            captured["kwargs"] = kwargs
            return cls()

    fake_service_account.Credentials = DummyCredentials
    fake_oauth2.service_account = fake_service_account
    fake_google.oauth2 = fake_oauth2
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.oauth2", fake_oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", fake_service_account)

    service = GoogleVisionOCRService(connection={"service_account_json": {"type": "service_account"}})
    service.get_credentials(scopes=[CLOUD_PLATFORM_SCOPE])

    assert captured["kwargs"] == {"scopes": [CLOUD_PLATFORM_SCOPE]}
    assert "default_scopes" not in captured["kwargs"]
    assert "default_host" not in captured["kwargs"]
    assert "target_audience" not in captured["kwargs"]


def test_google_cloud_connection_validate_runs_custom_checks_without_super(monkeypatch, tmp_path):
    fake_frappe = types.ModuleType("frappe")
    fake_frappe.get_site_path = lambda *parts: str(tmp_path.joinpath(*parts))
    fake_frappe.throw = lambda message: (_ for _ in ()).throw(ValueError(message))

    fake_model_module = types.ModuleType("frappe.model")
    fake_document_module = types.ModuleType("frappe.model.document")

    class DummyDocument:
        pass

    fake_document_module.Document = DummyDocument
    fake_model_module.document = fake_document_module
    fake_frappe.model = fake_model_module

    monkeypatch.setitem(sys.modules, "frappe", fake_frappe)
    monkeypatch.setitem(sys.modules, "frappe.model", fake_model_module)
    monkeypatch.setitem(sys.modules, "frappe.model.document", fake_document_module)

    module_name = "frappe_docai.frappe_document_ai.doctype.google_cloud_connection.google_cloud_connection"
    sys.modules.pop(module_name, None)
    mod = importlib.import_module(module_name)

    private_file = tmp_path / "private" / "files" / "demo-service-account.json"
    private_file.parent.mkdir(parents=True, exist_ok=True)
    private_file.write_text(json.dumps({"type": "service_account", "project_id": "demo-project"}), encoding="utf-8")

    doc = mod.GoogleCloudConnection()
    doc.service_account_json = "/private/files/demo-service-account.json"

    doc.validate()

    assert doc.service_account_json == "/private/files/demo-service-account.json"
