"""Deterministic financial validation for untrusted semantic extraction output."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MONEY_QUANTUM = Decimal("0.01")
DEFAULT_TOLERANCE = Decimal("0.01")


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        return Decimal(
            str(value).replace(",", "")
        ).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None


def _number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)

    return float(value)


def _array_field(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
) -> str | None:
    for field_name, field_schema in (schema or {}).items():
        if (
            isinstance(field_schema, dict)
            and str(
                field_schema.get("type") or ""
            ).lower()
            in {"array", "list"}
        ):
            if isinstance(
                data.get(field_name),
                list,
            ):
                return field_name

    for field_name, value in data.items():
        if (
            isinstance(value, list)
            and field_name != "tax_components"
        ):
            return field_name

    return None


def _record(
    corrections: list[dict[str, Any]],
    field: str,
    original: Any,
    corrected: Any,
    reason: str,
):
    if original != corrected:
        corrections.append(
            {
                "field": field,
                "original": original,
                "corrected": corrected,
                "reason": reason,
            }
        )


def _tax_component_level(
    component: dict[str, Any],
) -> str:
    """
    Normalize tax component scope.

    Supported meanings:

        invoice / invoice-level / consolidated / total
            -> invoice

        line / line-level / line-item / item / row
            -> line

    Unknown values remain unknown and are handled by inference.
    """
    value = str(
        component.get("level") or ""
    ).strip().lower()

    value = value.replace("_", "-")
    value = value.replace(" ", "-")

    if any(
        token in value
        for token in (
            "invoice",
            "consolidated",
            "overall",
            "header",
            "document-total",
            "invoice-total",
            "total",
        )
    ):
        return "invoice"

    if any(
        token in value
        for token in (
            "line",
            "line-item",
            "item",
            "row",
        )
    ):
        return "line"

    return "unknown"


def _has_line_gst(
    line_items: list[Any],
) -> bool:
    """
    Detect whether the semantic extraction already supplied
    GST directly on line items.
    """
    for item in line_items:
        if not isinstance(item, dict):
            continue

        percent = _decimal(
            item.get("gst_percent")
        )

        amount = _decimal(
            item.get("gst_amount")
        )

        if (
            (percent is not None and percent > 0)
            or (amount is not None and amount > 0)
        ):
            return True

    return False


def validate_and_correct(
    extracted: dict[str, Any],
    schema: dict[str, Any] | None = None,
    tolerance: Any = DEFAULT_TOLERANCE,
):
    """
    Validate and deterministically normalize financial data.

    Tax normalization rules:

    1. Invoice/consolidated GST
       - GST components apply to the combined taxable base.
       - Sum their percentages.
       - Sum their amounts.
       - Store the result in top-level:
            gst_percentage
            gst_amount
       - Set every line's GST fields to zero.

    2. Line-level GST
       - Do NOT add GST percentages across different lines.
       - Keep GST percentage/amount inside each line.
       - Top-level gst_percentage and gst_amount are zero.

    3. A tax percentage is only added when multiple tax components
       belong to the same tax scope/base.

    4. Tax labels such as CGST/SGST/IGST are treated as evidence
       only; the system output is normalized into generic GST fields.
    """
    data = deepcopy(extracted or {})
    corrections: list[dict[str, Any]] = []

    tolerance_decimal = (
        _decimal(tolerance)
        or DEFAULT_TOLERANCE
    )

    line_field = _array_field(
        data,
        schema,
    )

    line_items = (
        data.get(line_field)
        if line_field
        else []
    )

    if not isinstance(
        line_items,
        list,
    ):
        line_items = []
        line_field = None

    raw_bases = [
        _decimal(
            item.get("base_amount")
        )
        for item in line_items
        if isinstance(item, dict)
    ]

    raw_totals = [
        _decimal(
            item.get("total_amount")
        )
        for item in line_items
        if isinstance(item, dict)
    ]

    raw_base_sum = sum(
        (
            value
            for value in raw_bases
            if value is not None
        ),
        Decimal("0.00"),
    )

    raw_total_sum = sum(
        (
            value
            for value in raw_totals
            if value is not None
        ),
        Decimal("0.00"),
    )

    printed_tax = _decimal(
        data.get("tax_amount")
    )

    printed_grand_total = _decimal(
        data.get("total_amount")
    )

    # ------------------------------------------------------------
    # CLASSIFY TAX COMPONENTS BY SCOPE
    # ------------------------------------------------------------

    tax_components = data.get(
        "tax_components"
    )

    if not isinstance(
        tax_components,
        list,
    ):
        tax_components = []

    invoice_components: list[dict[str, Any]] = []
    line_components: list[dict[str, Any]] = []
    unknown_components: list[dict[str, Any]] = []

    for component in tax_components:
        if not isinstance(component, dict):
            continue

        level = _tax_component_level(
            component
        )

        if level == "invoice":
            invoice_components.append(
                component
            )

        elif level == "line":
            line_components.append(
                component
            )

        else:
            unknown_components.append(
                component
            )

    # ------------------------------------------------------------
    # DETERMINE TAX SCOPE
    # ------------------------------------------------------------

    invoice_level_tax_present = False

    if invoice_components:
        invoice_level_tax_present = True

    elif line_components:
        invoice_level_tax_present = False

    elif unknown_components:
        # If the model did not provide scope, use the strongest
        # available evidence.
        if _has_line_gst(line_items):
            invoice_level_tax_present = False

        elif (
            printed_tax is not None
            and printed_grand_total is not None
            and raw_base_sum > 0
        ):
            invoice_level_tax_present = (
                abs(
                    (
                        raw_base_sum
                        + printed_tax
                    )
                    - printed_grand_total
                )
                <= tolerance_decimal
                and abs(
                    raw_total_sum
                    - raw_base_sum
                )
                <= tolerance_decimal
                and printed_tax > 0
            )

        else:
            invoice_level_tax_present = False

    else:
        # No explicit tax_components.
        # Infer consolidated GST from invoice totals only when
        # the printed totals clearly support that structure.
        if (
            printed_tax is not None
            and printed_grand_total is not None
            and raw_base_sum > 0
        ):
            invoice_level_tax_present = (
                abs(
                    (
                        raw_base_sum
                        + printed_tax
                    )
                    - printed_grand_total
                )
                <= tolerance_decimal
                and abs(
                    raw_total_sum
                    - raw_base_sum
                )
                <= tolerance_decimal
                and printed_tax > 0
            )

    # ------------------------------------------------------------
    # INVOICE-LEVEL TAX
    # ------------------------------------------------------------

    invoice_tax = Decimal("0.00")
    invoice_gst_percent = Decimal("0.00")

    if invoice_level_tax_present:

        for component in invoice_components:
            amount = _decimal(
                component.get("amount")
            )

            rate = _decimal(
                component.get("rate")
            )

            if amount is not None:
                invoice_tax += amount

            if rate is not None:
                invoice_gst_percent += rate

        invoice_tax = invoice_tax.quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        invoice_gst_percent = invoice_gst_percent.quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        # Fallback when tax_components are missing but totals clearly
        # indicate consolidated GST.
        if (
            not invoice_components
            and printed_tax is not None
        ):
            invoice_tax = printed_tax

        if (
            invoice_gst_percent == 0
            and invoice_tax > 0
            and raw_base_sum > 0
        ):
            invoice_gst_percent = (
                invoice_tax
                / raw_base_sum
                * Decimal("100")
            ).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )

    # ------------------------------------------------------------
    # LINE-LEVEL TAX
    # ------------------------------------------------------------

    line_level_tax_present = (
        not invoice_level_tax_present
        and (
            bool(line_components)
            or _has_line_gst(line_items)
        )
    )

    calculated_subtotal = Decimal("0.00")
    line_tax_total = Decimal("0.00")

    for index, item in enumerate(line_items):

        if not isinstance(item, dict):
            continue

        base = _decimal(
            item.get("base_amount")
        )

        if base is None:
            continue

        original_percent = item.get(
            "gst_percent"
        )

        original_gst = item.get(
            "gst_amount"
        )

        original_total = item.get(
            "total_amount"
        )

        percent = _decimal(
            original_percent
        )

        gst = _decimal(
            original_gst
        )

        # --------------------------------------------------------
        # CONSOLIDATED / INVOICE-LEVEL GST
        # --------------------------------------------------------

        if invoice_level_tax_present:

            percent = Decimal("0.00")
            gst = Decimal("0.00")

            total = base

            _record(
                corrections,
                f"{line_field}[{index}].gst_percent",
                original_percent,
                _number(percent),
                "GST is applied on the consolidated taxable base and must not be allocated to line items",
            )

            _record(
                corrections,
                f"{line_field}[{index}].gst_amount",
                original_gst,
                _number(gst),
                "GST is applied on the consolidated taxable base and must not be allocated to line items",
            )

        # --------------------------------------------------------
        # LINE-LEVEL GST
        # --------------------------------------------------------

        elif line_level_tax_present:

            if (
                percent is None
                and gst is None
            ):
                percent = Decimal("0.00")
                gst = Decimal("0.00")

                _record(
                    corrections,
                    f"{line_field}[{index}].gst_percent",
                    original_percent,
                    _number(percent),
                    "No explicit line-level GST percentage was provided",
                )

                _record(
                    corrections,
                    f"{line_field}[{index}].gst_amount",
                    original_gst,
                    _number(gst),
                    "No explicit line-level GST amount was provided",
                )

            elif (
                percent is not None
                and percent > 0
            ):
                expected_gst = (
                    base
                    * percent
                    / Decimal("100")
                ).quantize(
                    MONEY_QUANTUM,
                    rounding=ROUND_HALF_UP,
                )

                if (
                    gst is None
                    or abs(
                        gst - expected_gst
                    )
                    > tolerance_decimal
                ):
                    _record(
                        corrections,
                        f"{line_field}[{index}].gst_amount",
                        original_gst,
                        _number(expected_gst),
                        "Line GST amount did not match the explicit line GST percentage",
                    )

                    gst = expected_gst

            elif (
                gst is not None
                and gst > 0
            ):
                # When only GST amount is available, derive its effective
                # percentage from the same line's taxable base.
                percent = (
                    gst
                    / base
                    * Decimal("100")
                ).quantize(
                    MONEY_QUANTUM,
                    rounding=ROUND_HALF_UP,
                )

            else:
                percent = Decimal("0.00")
                gst = Decimal("0.00")

            total = (
                base
                + (
                    gst
                    or Decimal("0.00")
                )
            ).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )

        # --------------------------------------------------------
        # NO TAX
        # --------------------------------------------------------

        else:

            percent = Decimal("0.00")
            gst = Decimal("0.00")
            total = base

            _record(
                corrections,
                f"{line_field}[{index}].gst_percent",
                original_percent,
                _number(percent),
                "No explicit GST scope or line-level GST was provided",
            )

            _record(
                corrections,
                f"{line_field}[{index}].gst_amount",
                original_gst,
                _number(gst),
                "No explicit GST scope or line-level GST was provided",
            )

        _record(
            corrections,
            f"{line_field}[{index}].total_amount",
            original_total,
            _number(total),
            "Line total did not equal base amount plus applicable line GST",
        )

        item["base_amount"] = _number(
            base
        )

        item["gst_percent"] = _number(
            percent
            or Decimal("0.00")
        )

        item["gst_amount"] = _number(
            gst
            or Decimal("0.00")
        )

        item["total_amount"] = _number(
            total
        )

        calculated_subtotal += base

        line_tax_total += (
            gst
            or Decimal("0.00")
        )

    calculated_subtotal = calculated_subtotal.quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )

    line_tax_total = line_tax_total.quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )

    # ------------------------------------------------------------
    # FINAL TAX / GRAND TOTAL
    # ------------------------------------------------------------

    if invoice_level_tax_present:
        calculated_tax = invoice_tax

        calculated_grand_total = (
            calculated_subtotal
            + invoice_tax
        ).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    else:
        calculated_tax = line_tax_total

        calculated_grand_total = (
            calculated_subtotal
            + line_tax_total
        ).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    # ------------------------------------------------------------
    # NORMALIZED TOP-LEVEL GST FIELDS
    # ------------------------------------------------------------

    original_gst_percentage = data.get(
        "gst_percentage"
    )

    original_gst_amount = data.get(
        "gst_amount"
    )

    if invoice_level_tax_present:

        normalized_gst_percentage = (
            invoice_gst_percent
        )

        normalized_gst_amount = (
            invoice_tax
        )

        _record(
            corrections,
            "gst_percentage",
            original_gst_percentage,
            _number(
                normalized_gst_percentage
            ),
            "Consolidated GST percentage is the sum of tax component percentages applied to the same taxable base",
        )

        _record(
            corrections,
            "gst_amount",
            original_gst_amount,
            _number(
                normalized_gst_amount
            ),
            "Consolidated GST amount is the sum of invoice-level tax component amounts",
        )

    else:

        normalized_gst_percentage = Decimal(
            "0.00"
        )

        normalized_gst_amount = Decimal(
            "0.00"
        )

        _record(
            corrections,
            "gst_percentage",
            original_gst_percentage,
            0,
            "GST is applied at line level, so top-level GST percentage must be zero",
        )

        _record(
            corrections,
            "gst_amount",
            original_gst_amount,
            0,
            "GST is applied at line level, so top-level GST amount must be zero",
        )

    data["gst_percentage"] = _number(
        normalized_gst_percentage
    )

    data["gst_amount"] = _number(
        normalized_gst_amount
    )

    # ------------------------------------------------------------
    # SUBTOTAL
    # ------------------------------------------------------------

    original_subtotal = data.get(
        "subtotal"
    )

    if (
        original_subtotal is not None
        and (
            _decimal(original_subtotal) is None
            or abs(
                _decimal(original_subtotal)
                - calculated_subtotal
            )
            > tolerance_decimal
        )
    ):
        _record(
            corrections,
            "subtotal",
            original_subtotal,
            _number(
                calculated_subtotal
            ),
            "Subtotal did not equal the deterministic sum of line base amounts",
        )

        data["subtotal"] = _number(
            calculated_subtotal
        )

    elif original_subtotal is None:
        data["subtotal"] = _number(
            calculated_subtotal
        )

    # ------------------------------------------------------------
    # TAX TOTAL / GRAND TOTAL
    # ------------------------------------------------------------

    for field_name, calculated, reason in (
        (
            "tax_amount",
            calculated_tax,
            "Tax total did not equal the deterministic GST calculation",
        ),
        (
            "total_amount",
            calculated_grand_total,
            "Grand total did not equal subtotal plus applicable GST",
        ),
    ):
        original = data.get(
            field_name
        )

        if (
            original is not None
            and _decimal(original) is not None
            and abs(
                _decimal(original)
                - calculated
            )
            <= tolerance_decimal
        ):
            continue

        _record(
            corrections,
            field_name,
            original,
            _number(calculated),
            reason,
        )

        data[field_name] = _number(
            calculated
        )

    return {
        "data": data,
        "financial_validation": {
            "valid": True,
            "corrected": bool(
                corrections
            ),
            "corrections": corrections,
            "calculated_subtotal": _number(
                calculated_subtotal
            ),
            "calculated_tax": _number(
                calculated_tax
            ),
            "calculated_grand_total": _number(
                calculated_grand_total
            ),
        },
    }