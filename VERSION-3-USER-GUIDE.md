# frappe_docai V3 — User Guide

## 1. Purpose

`frappe_docai` V3 provides a reusable API for extracting structured information from uploaded business documents.

The current V3 runtime is designed around:

```text
Frappe Client Script
        ↓
frappe.call()
        ↓
frappe_docai.api.process
        ↓
Gemini / Vertex AI
        ↓
Financial validation
        ↓
Corrected JSON
        ↓
Client Script
```

The same API can be used from Payment Entry or another Frappe DocType.

---

# 2. Main API

Use:

```text
frappe_docai.api.process
```

Do not use the older:

```text
frappe_docai.api.process_invoice
```

for the V3 integration.

---

# 3. API Parameters

The V3 API accepts:

```text
file_url
configuration
options
```

### Required

```javascript
file_url
configuration
```

### Optional

```javascript
options
```

Example:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: "/private/files/invoice.pdf",
        configuration: "7ujjqp2oki"
    }
});
```

---

# 4. Recommended Client Script Pattern

The recommended basic pattern is:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "7ujjqp2oki"
    },
    freeze: true,
    freeze_message: __("Extracting document..."),
    callback: function(r) {

        const apiResult = r.message || {};

        if (!apiResult.valid) {
            frappe.msgprint(
                apiResult.validation?.reason ||
                __("Document extraction failed validation.")
            );
            return;
        }

        const result = apiResult.corrected || {};

        console.log("Corrected result:", result);
    },
    error: function(err) {
        console.error("Document AI error:", err);

        frappe.msgprint(
            __("Document extraction failed.")
        );
    }
});
```

The important part is:

```javascript
const apiResult = r.message || {};
const result = apiResult.corrected || {};
```

Use the `corrected` object for populating ERPNext fields.

---

# 5. Why Use `corrected`

The API returns both:

```text
extracted
corrected
```

The `extracted` object is the direct semantic-model output.

The `corrected` object is the result after deterministic financial validation.

Conceptually:

```text
Gemini output
    ↓
extracted
    ↓
financial validator
    ↓
corrected
```

For accounting-related fields, use:

```javascript
apiResult.corrected
```

instead of directly using:

```javascript
apiResult.extracted
```

---

# 6. Example Response

A successful V3 response has the following general structure:

```json
{
  "valid": true,
  "configuration": "7ujjqp2oki",
  "file_name": "TEN BILL (1).pdf",
  "mime_type": "application/pdf",

  "extracted": {
    "vendor_name": "TEN INDIA",
    "invoice_number": "TI-104",
    "date": "2026-09-09",
    "total_amount": 18173.18,
    "tax_amount": 2772.18,
    "gst_percentage": 18,
    "gst_amount": 2772.18,
    "line_items": []
  },

  "corrected": {
    "vendor_name": "TEN INDIA",
    "invoice_number": "TI-104",
    "date": "2026-09-09",
    "total_amount": 18173.18,
    "tax_amount": 2772.18,
    "gst_percentage": 18,
    "gst_amount": 2772.18,
    "line_items": []
  },

  "financial_validation": {
    "valid": true,
    "corrected": true
  },

  "validation": {
    "valid": true,
    "reason": null
  }
}
```

The exact fields depend on the configured OCR schema.

---

# 7. Payment Entry Example

For a Payment Entry Client Script, the API call can be:

```javascript
const response = await frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_doc.file_url,
        configuration: "7ujjqp2oki"
    }
});

const apiResult = response.message || {};

if (!apiResult.valid) {
    throw new Error(
        apiResult.validation?.reason ||
        "Document AI extraction failed validation."
    );
}

const result = apiResult.corrected || {};
```

Then populate fields:

```javascript
if (result.invoice_number) {
    await frm.set_value(
        "custom_invoice_number",
        result.invoice_number
    );
}

if (result.date) {
    await frm.set_value(
        "custom_invoice_date",
        result.date
    );
}

if (result.total_amount) {
    await frm.set_value(
        "custom_total_amount",
        result.total_amount
    );
}
```

---

# 8. Populating Line Items

The current line-item structure is:

```text
line_items[]
    particular
    base_amount
    gst_percent
    gst_amount
    total_amount
```

Example:

```javascript
frm.clear_table("custom_items");

const lineItems = Array.isArray(result.line_items)
    ? result.line_items
    : [];

for (const item of lineItems) {

    const row = frm.add_child("custom_items");

    await frappe.model.set_value(
        row.doctype,
        row.name,
        {
            perticular: item.particular,
            base_amount: item.base_amount,
            gst: item.gst_percent,
            gst_amount: item.gst_amount,
            amount_after_tax: item.total_amount
        }
    );
}

frm.refresh_field("custom_items");
```

The field names on the ERPNext DocType must match the actual custom fields in that DocType.

---

# 9. Handling Supplier / Vendor

Example:

```javascript
if (result.vendor_name) {

    const supplierResponse = await frappe.db.get_value(
        "Supplier",
        {
            supplier_name: result.vendor_name
        },
        "name"
    );

    if (
        supplierResponse.message &&
        supplierResponse.message.name
    ) {

        await frm.set_value(
            "party_type",
            "Supplier"
        );

        await frm.set_value(
            "party",
            supplierResponse.message.name
        );
    }
}
```

This is application-specific logic. The V3 API itself only returns the extracted data.

---

# 10. Checking for API Errors

A safe pattern is:

```javascript
try {

    const response = await frappe.call({
        method: "frappe_docai.api.process",
        args: {
            file_url: file_url,
            configuration: "7ujjqp2oki"
        }
    });

    const apiResult = response.message || {};

    if (!apiResult.valid) {
        throw new Error(
            apiResult.validation?.reason ||
            "Extraction validation failed."
        );
    }

    const result = apiResult.corrected || {};

    console.log(result);

} catch (err) {

    console.error(
        "Document AI extraction error:",
        err
    );

    frappe.msgprint(
        __("Document extraction failed: {0}", [
            err.message || err
        ])
    );
}
```

---

# 11. Configuration ID

The configuration is selected using the OCR Configuration document name.

Current example:

```text
7ujjqp2oki
```

The configuration determines the extraction behavior, including:

```text
semantic provider
semantic model
semantic location
semantic endpoint
extraction instructions
output schema
Google Cloud connection
```

For another OCR configuration, replace:

```javascript
configuration: "7ujjqp2oki"
```

with the correct OCR Configuration document name.

---

# 12. Using Different Configurations

The same API can be reused for different documents.

Example:

```javascript
// Invoice
configuration: "invoice_config_name"
```

```javascript
// Purchase Order
configuration: "purchase_order_config_name"
```

```javascript
// Packing List
configuration: "packing_list_config_name"
```

The Client Script only needs to pass the desired configuration.

---

# 13. Passing Options

The API also supports:

```text
options
```

It can be passed as a JavaScript object:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "7ujjqp2oki",
        options: {
            example_option: true
        }
    }
});
```

Use only options supported by the current V3 backend implementation.

Do not assume arbitrary option names are supported.

---

# 14. Reading Validation Information

The response contains:

```text
financial_validation
validation
```

Example:

```javascript
console.log(
    "Financial validation:",
    apiResult.financial_validation
);

console.log(
    "Final validation:",
    apiResult.validation
);
```

A financial correction can be visible in:

```javascript
apiResult.financial_validation.corrections
```

Example:

```javascript
for (
    const correction
    of apiResult.financial_validation?.corrections || []
) {
    console.log(
        correction.field,
        correction.original,
        correction.corrected,
        correction.reason
    );
}
```

---

# 15. GST Data

The current schema is designed to represent two broad GST layouts.

## Consolidated GST

When GST is applied on the combined taxable/base amount:

```text
top-level gst_percentage
top-level gst_amount
```

are used.

Line GST should then be zero.

Example:

```json
{
  "gst_percentage": 18,
  "gst_amount": 2772.18,
  "line_items": [
    {
      "base_amount": 10044,
      "gst_percent": 0,
      "gst_amount": 0
    },
    {
      "base_amount": 5357,
      "gst_percent": 0,
      "gst_amount": 0
    }
  ]
}
```

## Line-level GST

When GST is applied separately to lines:

```text
top-level gst_percentage = 0
top-level gst_amount = 0
```

and the GST values remain inside each line.

Example:

```json
{
  "gst_percentage": 0,
  "gst_amount": 0,
  "line_items": [
    {
      "base_amount": 75000,
      "gst_percent": 18,
      "gst_amount": 6750
    },
    {
      "base_amount": 84.75,
      "gst_percent": 18,
      "gst_amount": 15.25
    }
  ]
}
```

Important:

```text
18% on line 1
+
18% on line 2
=
NOT 36%
```

Rates from different taxable bases must not be blindly added.

---

# 16. File Upload Example

A common flow is:

```javascript
new frappe.ui.FileUploader({

    doctype: frm.doc.doctype,
    docname: frm.doc.name,
    folder: "Home/Attachments",

    on_success: async (file_doc) => {

        const response = await frappe.call({
            method: "frappe_docai.api.process",
            args: {
                file_url: file_doc.file_url,
                configuration: "7ujjqp2oki"
            }
        });

        const apiResult =
            response.message || {};

        const result =
            apiResult.corrected || {};

        console.log(
            "OCR result:",
            result
        );
    }
});
```

The FileUploader's `file_doc.file_url` becomes the `file_url` parameter for the V3 API.

---

# 17. Recommended UI Flow

For a good user experience:

```text
Upload
  ↓
Freeze screen
  ↓
"Extracting document..."
  ↓
Call V3 API
  ↓
Validate API response
  ↓
Use corrected data
  ↓
Populate fields
  ↓
Refresh child table
  ↓
Unfreeze
```

Example:

```javascript
frappe.dom.freeze(
    __("Processing document...")
);

try {

    const response = await frappe.call({
        method: "frappe_docai.api.process",
        args: {
            file_url: file_url,
            configuration: "7ujjqp2oki"
        }
    });

    const apiResult =
        response.message || {};

    if (!apiResult.valid) {
        throw new Error(
            apiResult.validation?.reason ||
            "Validation failed."
        );
    }

    const result =
        apiResult.corrected || {};

    // Populate form here.

} catch (err) {

    frappe.msgprint(
        err.message ||
        __("Document extraction failed.")
    );

} finally {

    frappe.dom.unfreeze();

}
```

---

# 18. Security

The Client Script should only send:

```text
file_url
configuration
options
```

Do not put the Google service-account JSON or Google access token in JavaScript.

Google credentials remain server-side in the Frappe Google Cloud Connection configuration.

---

# 19. Debugging

The application creates `OCR API Log` records for API calls.

Useful fields include:

```text
status
raw_response
extracted_json
corrected_json
financial_validation
final_validation
token_usage
usage_metadata
credits_used_inr
gemini_request_time
total_processing_time
error
request_options
```

When debugging a failed or unexpected extraction, inspect:

```text
OCR API Log
```

and compare:

```text
raw_response
        ↓
extracted_json
        ↓
corrected_json
```

This makes it possible to distinguish:

```text
Gemini extraction problem
```

from:

```text
financial validator correction
```

or:

```text
final validation problem
```

---

# 20. What the Client Script Should Use

For normal ERPNext field population:

```javascript
const result = response.message.corrected || {};
```

Then use:

```javascript
result.vendor_name
result.invoice_number
result.date
result.total_amount
result.tax_amount
result.gst_percentage
result.gst_amount
result.line_items
```

For debugging:

```javascript
response.message.extracted
response.message.corrected
response.message.financial_validation
response.message.validation
response.message.usageMetadata
response.message.token_usage
response.message.timings
```

---

# 21. Minimal Reusable Helper

For multiple Client Scripts, the API call can be wrapped in a small JavaScript helper:

```javascript
async function extractDocument(file_url, configuration) {

    const response = await frappe.call({
        method: "frappe_docai.api.process",
        args: {
            file_url,
            configuration
        }
    });

    const apiResult =
        response.message || {};

    if (!apiResult.valid) {
        throw new Error(
            apiResult.validation?.reason ||
            "Document extraction failed validation."
        );
    }

    return apiResult.corrected || {};
}
```

Usage:

```javascript
const result = await extractDocument(
    file_doc.file_url,
    "7ujjqp2oki"
);

console.log(result);
```

This makes the same V3 API easy to reuse across multiple DocTypes.

---

# 22. Current Recommended Integration

The recommended integration for the current V3 implementation is:

```javascript
const response = await frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_doc.file_url,
        configuration: "7ujjqp2oki"
    }
});

const apiResult = response.message || {};

if (!apiResult.valid) {
    throw new Error(
        apiResult.validation?.reason ||
        "Document extraction failed validation."
    );
}

const result = apiResult.corrected || {};
```

Then map:

```text
result → ERPNext fields
result.line_items → ERPNext child table
```

---

# 23. Quick Reference

## API

```text
frappe_docai.api.process
```

## Required arguments

```text
file_url
configuration
```

## Result to use

```text
response.message.corrected
```

## Status

```text
response.message.valid
```

## Validation reason

```text
response.message.validation.reason
```

## Financial corrections

```text
response.message.financial_validation.corrections
```

## Token usage

```text
response.message.token_usage
```

## Timing

```text
response.message.timings
```

---

# 24. Complete Payment Entry Example

```javascript
frappe.ui.form.on("Payment Entry", {

    refresh: function(frm) {

        if (!frm.is_new()) {
            return;
        }

        frm.add_custom_button(
            __("Upload & Extract Invoice"),
            async function() {

                new frappe.ui.FileUploader({

                    doctype: frm.doc.doctype,
                    docname: frm.doc.name,
                    folder: "Home/Attachments",

                    on_success: async function(file_doc) {

                        try {

                            await frm.set_value(
                                "custom_invoice_file",
                                file_doc.file_url
                            );

                            frappe.dom.freeze(
                                __("Extracting invoice...")
                            );

                            const response =
                                await frappe.call({
                                    method:
                                        "frappe_docai.api.process",
                                    args: {
                                        file_url:
                                            file_doc.file_url,
                                        configuration:
                                            "7ujjqp2oki"
                                    }
                                });

                            const apiResult =
                                response.message || {};

                            if (!apiResult.valid) {
                                throw new Error(
                                    apiResult.validation?.reason ||
                                    "Document extraction failed validation."
                                );
                            }

                            const result =
                                apiResult.corrected || {};

                            if (result.invoice_number) {
                                await frm.set_value(
                                    "custom_invoice_number",
                                    result.invoice_number
                                );
                            }

                            if (result.date) {
                                await frm.set_value(
                                    "custom_invoice_date",
                                    result.date
                                );
                            }

                            frm.clear_table(
                                "custom_items"
                            );

                            const items =
                                Array.isArray(
                                    result.line_items
                                )
                                    ? result.line_items
                                    : [];

                            for (const item of items) {

                                const row =
                                    frm.add_child(
                                        "custom_items"
                                    );

                                await frappe.model.set_value(
                                    row.doctype,
                                    row.name,
                                    {
                                        perticular:
                                            item.particular,
                                        base_amount:
                                            item.base_amount,
                                        gst:
                                            item.gst_percent,
                                        gst_amount:
                                            item.gst_amount,
                                        amount_after_tax:
                                            item.total_amount
                                    }
                                );
                            }

                            frm.refresh_field(
                                "custom_items"
                            );

                            console.log(
                                "OCR API RESULT:",
                                apiResult
                            );

                        } catch (err) {

                            console.error(
                                "Document AI extraction error:",
                                err
                            );

                            frappe.msgprint(
                                __("Error extracting invoice: {0}", [
                                    err.message || err
                                ])
                            );

                        } finally {

                            frappe.dom.unfreeze();

                        }
                    }
                });
            }
        );
    }
});
```

---

# 25. Final Usage Rule

For V3 Client Script integration, remember these three lines:

```javascript
method: "frappe_docai.api.process"
```

```javascript
configuration: "7ujjqp2oki"
```

```javascript
const result = response.message.corrected || {};
```

Everything else is the ERPNext-specific mapping from that corrected JSON into the target DocType.

---

# End

V3 is designed so the Client Script does not need to know how Gemini, Google Cloud authentication, financial validation, or document extraction works.

The Client Script should simply:

```text
Upload file
    ↓
Call frappe_docai.api.process
    ↓
Check valid
    ↓
Read corrected
    ↓
Populate ERPNext
```
