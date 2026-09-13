import base64
import json
import re
from collections import defaultdict

import frappe
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account


CONFIG_DOCTYPE = "Document AI Configuration"


# ============================================================
# CONFIGURATION
# ============================================================

def get_config():
    config = frappe.get_single(CONFIG_DOCTYPE)

    if not config.enabled:
        frappe.throw("Document AI is disabled.")

    required_fields = [
        ("Google Cloud Project ID", config.project_id),
        ("Google Cloud Location", config.location),
        ("Processor ID", config.processor_id),
        ("Processor Version", config.processor_version),
        ("Google Credentials JSON", config.credentials_json),
    ]

    missing = [
        label
        for label, value in required_fields
        if not value
    ]

    if missing:
        frappe.throw(
            "Document AI Configuration is incomplete. Missing: "
            + ", ".join(missing)
        )

    return config


def get_credentials(config):
    file_url = config.credentials_json

    if not file_url:
        frappe.throw(
            "Google Credentials JSON is not configured."
        )

    # Frappe Attach field normally stores:
    # /private/files/file.json
    if file_url.startswith("/private/files/"):
        filename = file_url.replace(
            "/private/files/",
            "",
            1,
        )

    elif file_url.startswith("/files/"):
        filename = file_url.replace(
            "/files/",
            "",
            1,
        )

    else:
        filename = file_url.split("/")[-1]

    file_path = frappe.get_site_path(
        "private",
        "files",
        filename,
    )

    if not frappe.os.path.exists(file_path):
        frappe.throw(
            f"Google credentials file not found: {file_path}"
        )

    return service_account.Credentials.from_service_account_file(
        file_path,
        scopes=[
            "https://www.googleapis.com/auth/cloud-platform"
        ],
    )


def get_session(config):
    credentials = get_credentials(config)

    return AuthorizedSession(credentials)


# ============================================================
# SCHEMA PARSING
# ============================================================

VALID_TYPES = {
    "STRING",
    "NUMBER",
    "BOOLEAN",
    "INTEGER",
}

VALID_OCCURRENCES = {
    "OPTIONAL_ONCE",
    "OPTIONAL_MULTIPLE",
    "REQUIRED_ONCE",
    "REQUIRED_MULTIPLE",
}


def normalize_type(value):
    value = str(
        value or "STRING"
    ).upper().strip()

    if value not in VALID_TYPES:
        return "STRING"

    return value


def normalize_occurrence(value):
    value = str(
        value or "OPTIONAL_ONCE"
    ).upper().strip()

    if value not in VALID_OCCURRENCES:
        return "OPTIONAL_ONCE"

    return value


def make_property(
    display_name,
    value_type="STRING",
    occurrence="OPTIONAL_ONCE",
):
    """
    IMPORTANT:

    Do NOT send `description`.
    Do NOT send `method`.

    Both caused invalid schema errors with this processor.
    """

    return {
        "displayName": display_name,
        "valueType": normalize_type(value_type),
        "occurrenceType": normalize_occurrence(
            occurrence
        ),
    }


def parse_configured_schema(config):
    if not config.schema_json:
        frappe.throw(
            "Schema JSON is not configured."
        )

    try:
        schema = json.loads(
            config.schema_json
        )
    except Exception as e:
        frappe.throw(
            f"Invalid Schema JSON: {e}"
        )

    if not isinstance(schema, dict):
        frappe.throw(
            "Schema JSON must contain a JSON object."
        )

    return schema


def get_line_item_config(schema):
    """
    Finds an ARRAY -> OBJECT field dynamically.

    Example:

    line_items:
      type: ARRAY
      items:
        type: OBJECT
        properties:
          particular:
            type: STRING
          base_amount:
            type: NUMBER
    """

    for field_name, field_config in schema.items():

        if not isinstance(field_config, dict):
            continue

        if (
            str(
                field_config.get("type", "")
            ).upper()
            != "ARRAY"
        ):
            continue

        items = field_config.get(
            "items"
        ) or {}

        if (
            str(
                items.get("type", "")
            ).upper()
            != "OBJECT"
        ):
            continue

        properties = (
            items.get("properties")
            or {}
        )

        if properties:
            return (
                field_name,
                properties,
            )

    return None, {}


# ============================================================
# BUILD DOCUMENT AI SCHEMA
# ============================================================

def build_rest_schema(config, schema):
    """
    Google Custom Extractor in the current setup does not
    reliably accept nested ARRAY -> OBJECT overrides.

    Therefore:

        line_items.particular

    becomes:

        line_items__particular

    and repeated values are reconstructed into rows after
    Document AI processing.
    """

    line_item_name, line_item_properties = (
        get_line_item_config(schema)
    )

    properties = {}

    # --------------------------------------------------------
    # ROOT FIELDS
    # --------------------------------------------------------

    for field_name, field_config in schema.items():

        if field_name == line_item_name:
            continue

        if not isinstance(
            field_config,
            dict,
        ):
            continue

        field_type = normalize_type(
            field_config.get("type")
        )

        occurrence = normalize_occurrence(
            field_config.get(
                "occurrence",
                "OPTIONAL_ONCE",
            )
        )

        properties[field_name] = make_property(
            field_name,
            field_type,
            occurrence,
        )

    # --------------------------------------------------------
    # LINE ITEM FIELDS
    # --------------------------------------------------------

    for child_name, child_config in (
        line_item_properties.items()
    ):

        if not isinstance(
            child_config,
            dict,
        ):
            child_config = {}

        child_type = normalize_type(
            child_config.get("type")
        )

        flat_name = (
            f"{line_item_name}__{child_name}"
        )

        properties[flat_name] = make_property(
            flat_name,
            child_type,
            "OPTIONAL_MULTIPLE",
        )

    schema_override = {
        "entityTypes": [
            {
                "displayName":
                    "custom_extraction_document_type",
                "properties":
                    list(properties.values()),
            }
        ]
    }

    # Keep the configured extraction instructions available
    # for future use, but DO NOT put documentPrompt into
    # schemaOverride because this REST endpoint rejected it.
    document_prompt = (
        config.extraction_instructions
        or ""
    ).strip()

    return (
        schema_override,
        document_prompt,
    )


# ============================================================
# BASIC VALUE CLEANING
# ============================================================

def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def clean_number(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Currency symbols
    value = value.replace("₹", "")
    value = value.replace("$", "")
    value = value.replace("€", "")
    value = value.replace("£", "")

    # Common Indian currency prefixes
    value = value.replace("INR", "")
    value = value.replace("Rs.", "")
    value = value.replace("Rs", "")

    # Thousands separators
    value = value.replace(",", "")

    # Spaces
    value = value.replace(" ", "")

    # Percentage
    value = value.replace("%", "")

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value,
    )

    if not match:
        return None

    number = match.group(0)

    try:
        result = float(number)

        if result.is_integer():
            return int(result)

        return result

    except Exception:
        return None


def normalize_value(
    value,
    value_type,
):
    value_type = normalize_type(
        value_type
    )

    if value_type in {
        "NUMBER",
        "INTEGER",
    }:
        return clean_number(value)

    if value_type == "BOOLEAN":

        if isinstance(
            value,
            bool,
        ):
            return value

        text = str(
            value or ""
        ).strip().lower()

        if text in {
            "true",
            "yes",
            "1",
        }:
            return True

        if text in {
            "false",
            "no",
            "0",
        }:
            return False

        return None

    return clean_text(value)


# ============================================================
# DOCUMENT AI ENTITY HELPERS
# ============================================================

def get_entity_text(
    entity,
    document_text,
):
    """
    First try mentionText.

    If mentionText isn't present, reconstruct the text
    using textAnchor -> document.text.
    """

    mention_text = entity.get(
        "mentionText"
    )

    if mention_text:
        return clean_text(
            mention_text
        )

    anchor = (
        entity.get(
            "textAnchor"
        )
        or {}
    )

    parts = []

    for segment in (
        anchor.get(
            "textSegments"
        )
        or []
    ):

        start = int(
            segment.get(
                "startIndex",
                0,
            )
            or 0
        )

        end = int(
            segment.get(
                "endIndex",
                0,
            )
            or 0
        )

        if end > start:
            parts.append(
                document_text[
                    start:end
                ]
            )

    return clean_text(
        "".join(parts)
    )


def get_entity_position(
    entity
):
    """
    Returns approximate normalized page position.
    """

    page_anchor = (
        entity.get(
            "pageAnchor"
        )
        or {}
    )

    page_refs = (
        page_anchor.get(
            "pageRefs"
        )
        or []
    )

    if not page_refs:
        return {
            "page": 0,
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        }

    ref = page_refs[0]

    page = int(
        ref.get(
            "page",
            0,
        )
        or 0
    )

    poly = (
        ref.get(
            "boundingPoly"
        )
        or {}
    )

    vertices = (
        poly.get(
            "normalizedVertices"
        )
        or []
    )

    if not vertices:
        return {
            "page": page,
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        }

    xs = [
        float(
            v.get("x", 0)
        )
        for v in vertices
    ]

    ys = [
        float(
            v.get("y", 0)
        )
        for v in vertices
    ]

    return {
        "page": page,
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


# ============================================================
# TABLE HELPERS
# ============================================================

def get_cell_text(
    cell,
    document_text,
):
    """
    Document AI table cell text is reconstructed from
    document.text using textSegments.

    This avoids the previous NameError and does not rely
    on any console/global variable.
    """

    layout = (
        cell.get(
            "layout"
        )
        or {}
    )

    anchor = (
        layout.get(
            "textAnchor"
        )
        or {}
    )

    parts = []

    for segment in (
        anchor.get(
            "textSegments"
        )
        or []
    ):

        start = int(
            segment.get(
                "startIndex",
                0,
            )
            or 0
        )

        end = int(
            segment.get(
                "endIndex",
                0,
            )
            or 0
        )

        if end > start:
            parts.append(
                document_text[
                    start:end
                ]
            )

    return clean_text(
        "".join(parts)
    )


def get_cell_position(
    cell
):
    layout = (
        cell.get(
            "layout"
        )
        or {}
    )

    poly = (
        layout.get(
            "boundingPoly"
        )
        or {}
    )

    vertices = (
        poly.get(
            "normalizedVertices"
        )
        or []
    )

    if not vertices:
        return {
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        }

    xs = [
        float(
            v.get("x", 0)
        )
        for v in vertices
    ]

    ys = [
        float(
            v.get("y", 0)
        )
        for v in vertices
    ]

    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def extract_tables(
    document
):
    """
    Convert Document AI table response into an easier structure.

    Returns:

    [
        {
            page: 0,
            header: [
                [
                    {
                        text: "...",
                        position: {...}
                    }
                ]
            ],
            body: [
                [...]
            ]
        }
    ]
    """

    document_text = (
        document.get(
            "text",
            "",
        )
        or ""
    )

    result = []

    for page_index, page in enumerate(
        document.get(
            "pages",
            [],
        )
    ):

        for table in (
            page.get(
                "tables",
                []
            )
        ):

            headers = []

            for row in (
                table.get(
                    "headerRows",
                    []
                )
            ):

                cells = []

                for cell in (
                    row.get(
                        "cells",
                        []
                    )
                ):

                    cells.append(
                        {
                            "text":
                                get_cell_text(
                                    cell,
                                    document_text,
                                ),
                            "position":
                                get_cell_position(
                                    cell
                                ),
                        }
                    )

                headers.append(
                    cells
                )

            body = []

            for row in (
                table.get(
                    "bodyRows",
                    []
                )
            ):

                cells = []

                for cell in (
                    row.get(
                        "cells",
                        []
                    )
                ):

                    cells.append(
                        {
                            "text":
                                get_cell_text(
                                    cell,
                                    document_text,
                                ),
                            "position":
                                get_cell_position(
                                    cell
                                ),
                        }
                    )

                body.append(
                    cells
                )

            result.append(
                {
                    "page":
                        page_index,
                    "header":
                        headers,
                    "body":
                        body,
                }
            )

    return result


# ============================================================
# LINE ITEM ENTITY POSITION DATA
# ============================================================

def get_line_item_entities(
    document,
    line_item_name,
):
    prefix = (
        f"{line_item_name}__"
    )

    document_text = (
        document.get(
            "text",
            "",
        )
        or ""
    )

    result = []

    for entity in (
        document.get(
            "entities",
            []
        )
        or []
    ):

        entity_type = (
            entity.get(
                "type"
            )
            or ""
        )

        if not entity_type.startswith(
            prefix
        ):
            continue

        child_name = (
            entity_type[
                len(prefix):
            ]
        )

        result.append(
            {
                "field":
                    child_name,
                "value":
                    get_entity_text(
                        entity,
                        document_text,
                    ),
                "position":
                    get_entity_position(
                        entity
                    ),
            }
        )

    return result


# ============================================================
# COLUMN POSITION HELPERS
# ============================================================

def get_center_x(position):
    return (
        float(
            position.get(
                "x",
                0,
            )
        )
        +
        (
            float(
                position.get(
                    "width",
                    0,
                )
            )
            / 2
        )
    )


def average(values):
    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return 0

    return (
        sum(values)
        / len(values)
    )


# ============================================================
# HEADER COLUMN MAPPING
# ============================================================

def normalize_words(text):
    text = str(
        text or ""
    ).lower()

    return [
        word
        for word in re.split(
            r"[^a-z0-9]+",
            text,
        )
        if len(word) > 2
    ]


def map_by_headers(
    table,
    line_item_properties,
):
    mapping = {}

    header_rows = (
        table.get(
            "header"
        )
        or []
    )

    if not header_rows:
        return mapping

    # Use first header row primarily
    headers = header_rows[0]

    for child_name, child_config in (
        line_item_properties.items()
    ):

        description = ""

        if isinstance(
            child_config,
            dict,
        ):
            description = (
                child_config.get(
                    "description",
                    ""
                )
                or ""
            )

        search_terms = []

        search_terms.append(
            child_name
        )

        if description:
            search_terms.append(
                description
            )

        search_words = set()

        for term in search_terms:
            search_words.update(
                normalize_words(term)
            )

        if not search_words:
            continue

        best_index = None
        best_score = 0

        for index, header in enumerate(
            headers
        ):

            text = (
                header.get(
                    "text",
                    ""
                )
                or ""
            ).lower()

            if not text:
                continue

            header_words = set(
                normalize_words(text)
            )

            if not header_words:
                continue

            score = len(
                search_words
                &
                header_words
            )

            if score > best_score:
                best_score = score
                best_index = index

        if best_index is not None:
            mapping[
                child_name
            ] = best_index

    return mapping


# ============================================================
# POSITION BASED COLUMN MAPPING
# ============================================================

def map_by_entity_positions(
    table,
    line_item_properties,
    line_item_entities,
):
    mapping = {}

    body = (
        table.get(
            "body"
        )
        or []
    )

    if not body:
        return mapping

    # Calculate center X for each table column.
    column_x = {}

    max_columns = max(
        [
            len(row)
            for row in body
        ]
        or [0]
    )

    for column_index in range(
        max_columns
    ):

        positions = []

        for row in body:

            if column_index >= len(
                row
            ):
                continue

            position = (
                row[
                    column_index
                ].get(
                    "position"
                )
                or {}
            )

            if position.get(
                "width",
                0,
            ) <= 0:
                continue

            positions.append(
                get_center_x(
                    position
                )
            )

        if positions:
            column_x[
                column_index
            ] = average(
                positions
            )

    if not column_x:
        return mapping

    # Match configured fields against entity X position.
    for child_name in (
        line_item_properties
    ):

        candidates = [
            entity
            for entity in (
                line_item_entities
            )
            if entity["field"]
            == child_name
        ]

        if not candidates:
            continue

        entity_x_values = [
            get_center_x(
                entity[
                    "position"
                ]
            )
            for entity in candidates
            if entity[
                "position"
            ].get(
                "width",
                0,
            ) > 0
        ]

        if not entity_x_values:
            continue

        entity_x = average(
            entity_x_values
        )

        nearest_column = min(
            column_x,
            key=lambda index:
                abs(
                    column_x[index]
                    - entity_x
                ),
        )

        mapping[
            child_name
        ] = nearest_column

    return mapping


# ============================================================
# TABLE LINE ITEM EXTRACTION
# ============================================================

def extract_line_items_from_tables(
    document,
    line_item_name,
    line_item_properties,
):
    """
    Extract invoice line items directly from Document AI tables.

    Document AI may return merged/expanded cells, so fixed column indexes
    are unreliable. We therefore use the actual cell text and invoice
    amount patterns.
    """

    tables = extract_tables(document)

    if not tables:
        return []

    result = []

    for table in tables:
        body = table.get("body") or []

        if not body:
            continue

        for row in body:
            if not row:
                continue

            values = []

            for cell in row:
                value = str(cell.get("text") or "").strip()

                if value:
                    values.append(value)

            if not values:
                continue

            # Skip total/footer rows.
            first_text = values[0].strip().lower()

            if (
                first_text.startswith("total")
                or first_text.startswith("subtotal")
                or first_text.startswith("grand total")
            ):
                continue

            # --------------------------------------------------
            # PARTICULAR
            # --------------------------------------------------
            particular = values[0]

            # Ignore rows which clearly are not item rows.
            if particular.lower() in {
                "si.",
                "description",
                "shipping",
                "total",
            }:
                continue

            item = {
                "particular": particular,
            }

            # --------------------------------------------------
            # Find GST %
            # --------------------------------------------------
            gst_index = None
            gst_percent = None

            for index, value in enumerate(values):
                match = re.search(
                    r"(\d+(?:\.\d+)?)\s*%",
                    value,
                )

                if match:
                    gst_index = index
                    try:
                        gst_percent = float(match.group(1))
                    except Exception:
                        gst_percent = None
                    break

            if gst_percent is not None:
                item["gst_percent"] = (
                    int(gst_percent)
                    if gst_percent.is_integer()
                    else gst_percent
                )

            # --------------------------------------------------
            # Numeric values
            # --------------------------------------------------
            numeric_values = []

            for index, value in enumerate(values):
                if "%" in value:
                    continue

                cleaned = (
                    value
                    .replace("₹", "")
                    .replace(",", "")
                    .strip()
                )

                # Ignore HSN / text containing letters.
                if re.search(r"[A-Za-z]", cleaned):
                    continue

                match = re.fullmatch(
                    r"-?\d+(?:\.\d+)?",
                    cleaned,
                )

                if not match:
                    continue

                try:
                    number = float(cleaned)
                except Exception:
                    continue

                numeric_values.append(
                    {
                        "index": index,
                        "value": number,
                        "raw": value,
                    }
                )

            # --------------------------------------------------
            # GST AMOUNT + TOTAL AMOUNT
            #
            # In the actual invoice:
            #
            # iPhone:
            # ... 75,000.0 | 18% | IGST | 16,750.00 | ₹81,749.00
            #
            # Shipping:
            # ... 84.75 | 18% | IGST | 15.25 | 100.00
            # --------------------------------------------------
            if gst_index is not None:
                after_gst = [
                    x
                    for x in numeric_values
                    if x["index"] > gst_index
                ]

                if len(after_gst) >= 2:
                    gst_amount = after_gst[-2]["value"]
                    total_amount = after_gst[-1]["value"]

                    item["gst_amount"] = gst_amount
                    item["total_amount"] = total_amount

                    # --------------------------------------------------
                    # BASE AMOUNT
                    #
                    # Pick the numeric value immediately before the GST
                    # amount, while excluding quantity/discount values.
                    # --------------------------------------------------
                    before_gst = [
                        x
                        for x in numeric_values
                        if x["index"] < gst_index
                    ]

                    if before_gst:
                        # Prefer the last positive amount before GST.
                        positive_before_gst = [
                            x
                            for x in before_gst
                            if x["value"] > 0
                        ]

                        if positive_before_gst:
                            item["base_amount"] = (
                                positive_before_gst[-1]["value"]
                            )
                        else:
                            item["base_amount"] = (
                                before_gst[-1]["value"]
                            )

            # --------------------------------------------------
            # Remove empty/zero-only accidental rows.
            # --------------------------------------------------
            if (
                "gst_amount" not in item
                and "total_amount" not in item
                and "base_amount" not in item
            ):
                continue

            # Convert integral floats to integers.
            for field in (
                "base_amount",
                "gst_amount",
                "total_amount",
            ):
                if field in item:
                    value = item[field]

                    if (
                        isinstance(value, float)
                        and value.is_integer()
                    ):
                        item[field] = int(value)

            result.append(item)

    return result


# ============================================================
# ENTITY LINE ITEM FALLBACK
# ============================================================

def build_line_items_from_entities(
    document,
    line_item_name,
    line_item_properties,
):
    entities = (
        get_line_item_entities(
            document,
            line_item_name,
        )
    )

    if not entities:
        return []

    # Sort top-to-bottom, then left-to-right.
    entities.sort(
        key=lambda entity: (
            entity[
                "position"
            ].get(
                "page",
                0,
            ),
            entity[
                "position"
            ].get(
                "y",
                0,
            ),
            entity[
                "position"
            ].get(
                "x",
                0,
            ),
        )
    )

    rows = []

    for entity in entities:

        position = entity[
            "position"
        ]

        page = position.get(
            "page",
            0,
        )

        y = position.get(
            "y",
            0,
        )

        matched_row = None

        for row in rows:

            if row[
                "page"
            ] != page:
                continue

            if abs(
                row["y"] - y
            ) <= 0.025:

                matched_row = row
                break

        if matched_row is None:

            matched_row = {
                "page":
                    page,
                "y":
                    y,
                "values":
                    {},
            }

            rows.append(
                matched_row
            )

        field = entity[
            "field"
        ]

        field_config = (
            line_item_properties.get(
                field
            )
            or {}
        )

        value = normalize_value(
            entity[
                "value"
            ],
            field_config.get(
                "type",
                "STRING",
            ),
        )

        if value is not None:
            matched_row[
                "values"
            ][field] = value

    return [
        row["values"]
        for row in rows
        if row["values"]
    ]


# ============================================================
# ROOT ENTITY PARSER
# ============================================================

def parse_root_entities(
    document,
    schema,
):
    result = {}

    line_item_name, _ = (
        get_line_item_config(
            schema
        )
    )

    configured_fields = {
        field_name:
            field_config
        for field_name, field_config
        in schema.items()
        if field_name
        != line_item_name
    }

    document_text = (
        document.get(
            "text",
            "",
        )
        or ""
    )

    for entity in (
        document.get(
            "entities",
            []
        )
        or []
    ):

        entity_type = (
            entity.get(
                "type"
            )
        )

        if not entity_type:
            continue

        # Ignore line item flat entities here.
        if line_item_name and entity_type.startswith(
            f"{line_item_name}__"
        ):
            continue

        if entity_type not in (
            configured_fields
        ):
            continue

        field_config = (
            configured_fields[
                entity_type
            ]
            or {}
        )

        raw_value = get_entity_text(
            entity,
            document_text,
        )

        value = normalize_value(
            raw_value,
            field_config.get(
                "type",
                "STRING",
            ),
        )

        if value is not None:
            result[
                entity_type
            ] = value

    return result


# ============================================================
# MAIN PROCESS
# ============================================================

def process_invoice_with_docai(
    file_url
):
    """
    Main public function.

    Everything comes from Document AI Configuration.
    """

    config = get_config()

    schema = parse_configured_schema(
        config
    )

    # --------------------------------------------------------
    # Get Frappe File
    # --------------------------------------------------------

    file_doc = frappe.get_doc(
        "File",
        {
            "file_url":
                file_url
        },
    )

    if file_doc.is_private:

        file_path = (
            frappe.get_site_path(
                "private",
                "files",
                file_doc.file_name,
            )
        )

    else:

        file_path = (
            frappe.get_site_path(
                "public",
                "files",
                file_doc.file_name,
            )
        )

    if not frappe.os.path.exists(
        file_path
    ):
        frappe.throw(
            f"Invoice file not found: {file_path}"
        )

    with open(
        file_path,
        "rb",
    ) as f:
        content = f.read()

    # --------------------------------------------------------
    # MIME TYPE
    # --------------------------------------------------------

    filename = (
        file_doc.file_name
        or ""
    ).lower()

    if filename.endswith(
        ".pdf"
    ):
        mime_type = (
            "application/pdf"
        )

    elif filename.endswith(
        ".png"
    ):
        mime_type = (
            "image/png"
        )

    elif filename.endswith(
        ".jpg"
    ) or filename.endswith(
        ".jpeg"
    ):
        mime_type = (
            "image/jpeg"
        )

    elif filename.endswith(
        ".tif"
    ) or filename.endswith(
        ".tiff"
    ):
        mime_type = (
            "image/tiff"
        )

    else:
        mime_type = (
            "application/octet-stream"
        )

    # --------------------------------------------------------
    # BUILD SCHEMA
    # --------------------------------------------------------

    schema_override, document_prompt = (
        build_rest_schema(
            config,
            schema,
        )
    )

    # --------------------------------------------------------
    # CONFIG-DRIVEN PROCESSOR URL
    # --------------------------------------------------------

    project_id = (
        config.project_id
    )

    location = (
        config.location
    )

    processor_id = (
        config.processor_id
    )

    processor_version = (
        config.processor_version
    )

    endpoint = (
        f"https://{location}-documentai.googleapis.com"
        f"/v1/projects/{project_id}"
        f"/locations/{location}"
        f"/processors/{processor_id}"
        f"/processorVersions/{processor_version}"
        f":process"
    )

    # --------------------------------------------------------
    # REQUEST
    # --------------------------------------------------------

    request_body = {
        "rawDocument": {
            "content":
                base64.b64encode(
                    content
                ).decode(
                    "utf-8"
                ),
            "mimeType":
                mime_type,
        }
    }

    # --------------------------------------------------------
    # CALL GOOGLE
    # --------------------------------------------------------

    session = get_session(
        config
    )

    response = session.post(
        endpoint,
        json=request_body,
        timeout=120,
    )

    if response.status_code != 200:

        frappe.throw(
            "Google Document AI error "
            f"{response.status_code}: "
            f"{response.text}"
        )

    data = response.json()

    document = (
        data.get(
            "document"
        )
        or {}
    )

    # --------------------------------------------------------
    # ROOT FIELDS
    # --------------------------------------------------------

    result = parse_root_entities(
        document,
        schema,
    )

    # --------------------------------------------------------
    # LINE ITEMS
    # --------------------------------------------------------

    line_item_name, line_item_properties = (
        get_line_item_config(
            schema
        )
    )

    if (
        line_item_name
        and line_item_properties
    ):

        # PRIMARY:
        # Document AI table rows
        line_items = (
            extract_line_items_from_tables(
                document,
                line_item_name,
                line_item_properties,
            )
        )

        # FALLBACK:
        # Repeated entities grouped by Y position
        if not line_items:

            line_items = (
                build_line_items_from_entities(
                    document,
                    line_item_name,
                    line_item_properties,
                )
            )

        result[
            line_item_name
        ] = line_items

    # --------------------------------------------------------
    # ENSURE ROOT FIELDS EXIST
    # --------------------------------------------------------

    for field_name in schema:

        if field_name == line_item_name:
            continue

        if field_name not in result:
            result[
                field_name
            ] = None

    return result


# ============================================================
# CONNECTION TEST
# ============================================================

def test_connection():
    """
    Uses ONLY configured:
        project_id
        location
        processor_id
        processor_version
        credentials
    """

    config = get_config()

    session = get_session(
        config
    )

    endpoint = (
        f"https://{config.location}-documentai.googleapis.com"
        f"/v1/projects/{config.project_id}"
        f"/locations/{config.location}"
        f"/processors/{config.processor_id}"
        f"/processorVersions/{config.processor_version}"
    )

    response = session.get(
        endpoint,
        timeout=30,
    )

    if response.status_code != 200:

        status = (
            f"FAILED ({response.status_code}): "
            f"{response.text}"
        )

        frappe.db.set_value(
            CONFIG_DOCTYPE,
            None,
            "connection_status",
            status,
        )

        frappe.db.set_value(
            CONFIG_DOCTYPE,
            None,
            "last_connection_test",
            frappe.utils.now_datetime(),
        )

        frappe.db.commit()

        return {
            "success":
                False,
            "message":
                status,
        }

    status = (
        "Connected successfully."
    )

    frappe.db.set_value(
        CONFIG_DOCTYPE,
        None,
        "connection_status",
        status,
    )

    frappe.db.set_value(
        CONFIG_DOCTYPE,
        None,
        "last_connection_test",
        frappe.utils.now_datetime(),
    )

    frappe.db.commit()

    return {
        "success":
            True,
        "message":
            status,
    }


@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)