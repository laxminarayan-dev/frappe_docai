# Frappe Document AI

Reusable document-understanding and financial-validation backend for **Frappe Framework 16.x / ERPNext 16.x**.

`frappe_docai` was originally built around Google Document AI / OCR-based invoice extraction. Version 3 (V3) changes the runtime architecture to a **direct document-understanding pipeline**:

```text
Frappe / ERPNext
      |
      | PDF file URL
      v
frappe_docai.api.process
      |
      | load OCR Configuration
      v
Gemini 3.5 Flash-Lite
on Google Cloud Agent Platform / Vertex AI
      |
      | structured JSON
      v
Deterministic Financial Validator
      |
      | corrected JSON
      v
Final Validation
      |
      v
ERPNext Client Script / Business Logic
```

The application is designed to be **reusable and configuration-driven**. The same backend API can be used by Payment Entry today and by other ERPNext/Frappe documents such as Purchase Orders, Packing Lists, Purchase Receipts / GRNs, Delivery Notes, and other structured business documents in the future.

---

## Current V3 Status

| Component | Current V3 baseline |
|---|---|
| Frappe | 16.31.0 |
| ERPNext | 16.32.3 |
| App branch | `version-3` |
| Python | 3.14.x |
| Main API | `frappe_docai.api.process` |
| Semantic provider | `VertexAISemanticProvider` |
| Provider label | Google Agent Platform |
| Model | `gemini-3.5-flash-lite` |
| Location | `global` |
| Input | Original document bytes, currently PDF |
| Output | Structured JSON |
| Generation | `temperature = 0` |
| Response format | JSON with generated object properties marked required |
| HTTP timeout | 30 seconds |
| Financial layer | Deterministic validation / correction |
| Observability | `OCR API Log` |

> **Important:** Some older project material describes Google Document AI, Vision OCR, GCS output, and OCR table reconstruction. Those belong to earlier V1/V2 paths or compatibility code. They are **not required for the normal V3 PDF → Gemini runtime**.

---

# 1. Download and Install

## 1.1 Requirements

Before installing the app, you need:

- Frappe Framework 16.x
- ERPNext 16.x
- A working Frappe Bench
- A working Frappe site
- Git
- Internet access from the Frappe server
- A Google Cloud project with billing enabled
- Vertex AI / Agent Platform access
- A Google Cloud service account with permission to call the selected model

The V3 Python project declares these main Google packages:

```text
google-cloud-documentai
google-cloud-storage
google-cloud-vision
```

The legacy packages remain available because the repository retains compatibility with earlier Google OCR functionality. They are **not required as separate processors for the normal V3 semantic runtime**.

The live development project uses Python 3.14.x and declares Python `>=3.14`.

## 1.2 Download the V3 branch

From your Bench:

```bash
cd ~/frappe-bench

bench get-app --branch version-3 \
  https://github.com/laxminarayan-dev/frappe_docai.git
```

The repository is:

```text
https://github.com/laxminarayan-dev/frappe_docai
```

The V3 development branch is:

```text
version-3
```

## 1.3 Verify the app exists

```bash
cd ~/frappe-bench
bench list-apps
```

You can also verify the source directory:

```bash
ls -la ~/frappe-bench/apps/frappe_docai
```

## 1.4 Install the app on a site

Replace `YOUR_SITE_NAME` with your site name:

```bash
bench --site YOUR_SITE_NAME install-app frappe_docai
```

Example:

```bash
bench --site vendor2.site install-app frappe_docai
```

## 1.5 Migrate and clear cache

```bash
bench --site YOUR_SITE_NAME migrate

bench --site YOUR_SITE_NAME clear-cache
bench --site YOUR_SITE_NAME clear-website-cache
```

For a production-managed Bench:

```bash
bench restart
```

For development mode:

```bash
bench start
```

## 1.6 Verify installation

```bash
bench --site YOUR_SITE_NAME list-apps
```

You should see:

```text
frappe_docai
```

## 1.7 One-command installation block

When the Bench and site already exist, the normal installation sequence is:

```bash
cd ~/frappe-bench

bench get-app --branch version-3 \
  https://github.com/laxminarayan-dev/frappe_docai.git

bench --site YOUR_SITE_NAME install-app frappe_docai
bench --site YOUR_SITE_NAME migrate
bench --site YOUR_SITE_NAME clear-cache
bench --site YOUR_SITE_NAME clear-website-cache
bench --site YOUR_SITE_NAME list-apps
bench restart
```

The V3 project documentation also used explicit installation of Google authentication libraries where required:

```bash
bench pip install google-auth
```

The repository's Python metadata should remain the primary source for declared application dependencies.

---

# 2. What Is Frappe Document AI?

`frappe_docai` is a reusable server-side document extraction service for Frappe and ERPNext.

The core idea is simple:

```text
Business document
      ↓
Document understanding model
      ↓
Structured JSON
      ↓
Deterministic business / financial validation
      ↓
Corrected JSON
      ↓
ERPNext
```

Instead of creating separate document-extraction code for every DocType, the application exposes one reusable backend API and makes the extraction behavior configurable.

For example, the same API can be called with different OCR Configuration records:

```text
Invoice configuration
Purchase Order configuration
Packing List configuration
Purchase Receipt configuration
Delivery Note configuration
...
```

The consumer only needs to provide the correct configuration name.

---

# 3. Why We Built It

The original business requirement came from **vendor invoice extraction in Payment Entry**.

The intended workflow was:

```text
Payment Entry
      ↓
Upload vendor invoice
      ↓
Process document
      ↓
Extract invoice information
      ↓
Validate financial relationships
      ↓
Correct inconsistent model output
      ↓
Populate Payment Entry
```

The information required from the invoice includes fields such as:

```text
Vendor / Supplier
Invoice number
Invoice date
Invoice total
Total tax
Line items
Description / particular
Base amount
GST percentage
GST amount
Line total
```

The system needed to do more than OCR text. It needed to understand different document layouts and return structured business data without hardcoding one vendor's invoice format.

That led to two important requirements:

1. **Reusable extraction** — the same backend should serve multiple document types.
2. **Deterministic financial validation** — the model should not be treated as the final authority for arithmetic.

---

# 4. How the Project Evolved: V1 → V2 → V3

## 4.1 Earlier V1/V2 architecture

The earlier implementation was centered on Google Document AI / Vision OCR:

```text
Frappe File
      ↓
Google Document AI / OCR
      ↓
OCR text + entities + table information
      ↓
Normalization
      ↓
Bounding-box / row reconstruction
      ↓
Invoice JSON
      ↓
Payment Entry
```

This architecture introduced significant complexity around table extraction and spatial reconstruction.

For example, the normalized Vision words exposed bounding-box information and precomputed centers such as `x_center` and `y_center`, while one reconstruction implementation expected raw `boundingBox.vertices`. That compatibility problem was fixed and regression-tested.

## 4.2 Why V3 changed

The requirement expanded beyond simple OCR. The application needed better semantic understanding of the **original document**, including varying invoice layouts.

V3 therefore moved the normal runtime to:

```text
Original PDF
      ↓
Gemini directly reads the PDF
      ↓
Structured JSON
      ↓
Financial validation
      ↓
Final corrected JSON
```

The major architectural decision was:

> **Google Vision is no longer the normal V3 semantic extraction stage.**

Legacy Vision / Document AI code can remain in the repository for compatibility and older paths, but fresh V3 usage should use the direct PDF pipeline.

---

# 5. Current V3 Architecture in Detail

The complete V3 flow is:

```text
┌─────────────────────────────┐
│          ERPNext            │
│      Payment Entry          │
└─────────────┬───────────────┘
              │
              │ upload / select PDF
              ▼
┌─────────────────────────────┐
│       frappe_docai V3       │
│   frappe_docai.api.process  │
└─────────────┬───────────────┘
              │
              │ load configuration
              ▼
┌─────────────────────────────┐
│      OCR Configuration      │
│ provider / model / schema   │
│ instructions / connection   │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Gemini 3.5 Flash-Lite      │
│ Google Agent Platform /     │
│ Vertex AI                    │
│                             │
│ Original PDF as input       │
└─────────────┬───────────────┘
              │
              │ structured JSON
              ▼
┌─────────────────────────────┐
│  Financial Validator        │
│ deterministic arithmetic    │
│ + tax normalization rules   │
└─────────────┬───────────────┘
              │
              │ corrected JSON
              ▼
┌─────────────────────────────┐
│    Final Validation         │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ ERPNext Client Script /     │
│ business logic              │
└─────────────────────────────┘
```

## 5.1 Input

The normal V3 runtime receives the original document bytes.

For the current implementation, the primary supported document input is:

```text
PDF
```

The backend receives a Frappe file URL, loads the file, determines its MIME type, and passes the document bytes to the semantic provider.

Conceptually:

```text
Frappe File URL
      ↓
PDF bytes
      ↓
base64 / inlineData
      ↓
Gemini
```

## 5.2 Semantic provider

V3 introduced a replaceable semantic-provider contract.

The current implementation is:

```text
VertexAISemanticProvider
```

The provider accepts document-centric input such as:

```text
document_bytes
mime_type
file_name
instructions
schema
```

This is intentionally generic so the application does not become permanently coupled to one document type.

## 5.3 Structured model output

Gemini is requested to return JSON using:

```text
responseMimeType = application/json
responseSchema = configured schema
```

The provider also augments the generated schema with the tax evidence needed by the validator.

## 5.4 Deterministic financial stage

The model output is treated as **semantic data, not accounting truth**.

The validator independently checks relationships such as:

```text
line total ≈ base amount + line tax
invoice subtotal ≈ sum of line bases
invoice total ≈ subtotal + applicable tax
reported tax amount ≈ taxable base × applicable rate
```

Where a deterministic correction is justified, the application produces:

```text
corrected
```

The consumer should use that object for accounting-related field population.

## 5.5 Final validation

After financial correction, the result goes through final validation and the API returns the final status together with the extraction and validation information.

---

# 6. Google Cloud Setup

## 6.1 What V3 needs

For the normal direct PDF → Gemini runtime, you need:

```text
1. Google Cloud project
2. Billing enabled
3. Vertex AI / Agent Platform API enabled
4. Service account
5. Vertex AI User permission
6. Service-account JSON key
7. Gemini 3.5 Flash-Lite access in Global
```

The normal V3 path does **not** require you to create:

```text
Document AI processor
GCS input bucket
GCS output bucket
Vision OCR processor
```

Those belong to optional / legacy OCR workflows.

## 6.2 Project

Create or select a Google Cloud project and record the actual **Project ID**.

Example:

```text
my-frappe-docai-project
```

Do not confuse the project name with the project ID.

## 6.3 Set the project with gcloud

```bash
gcloud config set project YOUR_PROJECT_ID
```

Verify:

```bash
gcloud config get-value project
```

## 6.4 Enable Vertex AI

```bash
gcloud services enable aiplatform.googleapis.com \
  --project=YOUR_PROJECT_ID
```

Supporting services used during administration can also be enabled:

```bash
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  serviceusage.googleapis.com \
  --project=YOUR_PROJECT_ID
```

## 6.5 Create the service account

Example:

```bash
gcloud iam service-accounts create frappe-docai \
  --project=YOUR_PROJECT_ID \
  --display-name="Frappe Document AI"
```

The service-account email will be:

```text
frappe-docai@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

## 6.6 Grant Vertex AI User

Grant:

```text
roles/aiplatform.user
```

Example:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:frappe-docai@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

Verify the role:

```bash
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:frappe-docai@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

## 6.7 Create the JSON key

```bash
gcloud iam service-accounts keys create \
  ~/frappe-docai-service-account.json \
  --iam-account="frappe-docai@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

Protect the local key:

```bash
chmod 600 ~/frappe-docai-service-account.json
```

## 6.8 Security rule for the key

The service-account JSON is a credential.

Never:

- commit it to Git
- put it in this repository
- put it in JavaScript
- expose it to the browser
- put it in a public Frappe attachment
- put private-key contents directly into Client Scripts

The V3 design keeps credentials server-side in the Frappe Google Cloud Connection configuration.

---

# 7. Current Gemini Configuration

The V3 project uses:

```text
Provider: Google Agent Platform
Model: gemini-3.5-flash-lite
Location: global
Endpoint: blank
```

Do not blindly replace `global` with a regional location. Use the model/location configuration supported by the current project and provider.

The model request uses deterministic generation:

```text
temperature = 0
```

and structured JSON output.

---

# 8. Frappe Configuration

V3 uses two central configuration DocTypes and one logging DocType:

```text
Google Cloud Connection
OCR Configuration
OCR API Log
```

## 8.1 Google Cloud Connection

Create a **Google Cloud Connection** record.

Important fields are:

```text
Enabled: 1
Connection Name: Frappe Document AI
Google Cloud Project ID: YOUR_PROJECT_ID
Service Account Email: frappe-docai@YOUR_PROJECT_ID.iam.gserviceaccount.com
Service Account JSON: private uploaded JSON file
```

Legacy GCS fields may also exist in the DocType. They are not required for the normal direct-PDF V3 runtime.

Upload the service-account JSON as a **private Frappe attachment**.

## 8.2 OCR Configuration

Create an **OCR Configuration** record.

Example V3 configuration:

```text
Enabled: 1
Google Cloud Connection: <your Google Cloud Connection>
Semantic Provider: Google Agent Platform
Semantic Model: gemini-3.5-flash-lite
Semantic Location: global
Semantic Endpoint: blank
Extraction Instructions: <document-specific instructions>
Output Schema: <document-specific JSON schema>
```

The configuration is what makes the app reusable.

For example:

```text
OCR Configuration: invoice_extraction
```

could define an invoice schema, while:

```text
OCR Configuration: purchase_order_extraction
```

could define a Purchase Order schema.

The Client Script only changes the configuration name.

## 8.3 Current development example

The V3 development environment used records similar to:

```text
OCR Configuration
name = 7ujjqp2oki
api_name = invoice_extraction
```

and:

```text
Google Cloud Connection
name = fd0k5bsbpu
```

These are development examples, not values that should be hardcoded in another installation.

---

# 9. Output Schema Design

The V3 invoice configuration currently models fields such as:

```json
{
  "vendor_name": {
    "type": "STRING",
    "description": "Company or business name issuing the invoice"
  },
  "invoice_number": {
    "type": "STRING",
    "description": "Invoice number exactly as printed on the invoice"
  },
  "date": {
    "type": "STRING",
    "description": "Invoice issue date in YYYY-MM-DD format"
  },
  "total_amount": {
    "type": "NUMBER",
    "description": "Final invoice total including all applicable taxes"
  },
  "tax_amount": {
    "type": "NUMBER",
    "description": "Total tax amount charged on the invoice"
  },
  "gst_percentage": {
    "type": "NUMBER",
    "description": "Combined GST percentage when GST is applied on the consolidated taxable base; return 0 for line-level GST"
  },
  "gst_amount": {
    "type": "NUMBER",
    "description": "Combined GST amount when GST is applied on the consolidated taxable base; return 0 for line-level GST"
  },
  "line_items": {
    "type": "ARRAY",
    "items": {
      "type": "OBJECT",
      "properties": {
        "particular": {
          "type": "STRING",
          "description": "Description or name of the purchased item or service"
        },
        "base_amount": {
          "type": "NUMBER",
          "description": "Amount before GST"
        },
        "gst_percent": {
          "type": "NUMBER",
          "description": "GST percentage applicable to this line; return 0 when GST is consolidated"
        },
        "gst_amount": {
          "type": "NUMBER",
          "description": "GST amount applicable to this line; return 0 when GST is consolidated"
        },
        "total_amount": {
          "type": "NUMBER",
          "description": "Final line amount including GST"
        }
      }
    }
  }
}
```

The schema should be tailored to the business document being extracted.

## 9.1 Required fields behavior

V3 automatically marks generated object properties as required in the semantic response schema.

This was introduced after Gemini occasionally returned a sparse object even when the document clearly contained more information.

The combination of:

```text
required response properties
+
temperature = 0
+
JSON response mode
```

was tested against the primary invoice and stabilized repeated extraction.

---

# 10. Extraction Instructions

Extraction instructions are stored in the **OCR Configuration** record.

The instructions should define:

```text
What document is being processed
Which fields must be extracted
How dates should be interpreted
How line items should be interpreted
How taxes should be interpreted
What to do when evidence is missing
```

Keep instructions document-specific.

For example, an invoice configuration may instruct the model to:

- identify the supplier name exactly as printed
- normalize the invoice date to `YYYY-MM-DD`
- identify every line item and its taxable base
- distinguish line-level GST from consolidated GST
- return `0` for fields that are intentionally used only in the alternate tax representation
- avoid inventing data that is not supported by the document

Do **not** put credentials or tokens inside extraction instructions.

---

# 11. Main API

The V3 public backend API is:

```text
frappe_docai.api.process
```

Do not use the older V1/V2 invoice-specific API:

```text
frappe_docai.api.process_invoice
```

for new V3 integrations.

## 11.1 Parameters

The API accepts:

```text
file_url
configuration
options
```

Required:

```text
file_url
configuration
```

Optional:

```text
options
```

## 11.2 Minimal call

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "YOUR_OCR_CONFIGURATION"
    },
    callback: function (r) {
        console.log(r.message);
    }
});
```

## 11.3 Async / `await` pattern

The recommended pattern in a Client Script is:

```javascript
const response = await frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "YOUR_OCR_CONFIGURATION"
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

console.log("Corrected result:", result);
```

---

# 12. How to Use It from a Frappe Client Script

The normal integration pattern is:

```text
User selects / uploads PDF
        ↓
Get file_url
        ↓
frappe.call(process)
        ↓
Check valid
        ↓
Read corrected
        ↓
Populate ERPNext fields
        ↓
Refresh form / child table
```

## 12.1 Basic example

```javascript
frappe.ui.form.on("Your DocType", {
    async custom_extract_document(frm) {
        const file_url = frm.doc.custom_file_url;

        if (!file_url) {
            frappe.msgprint(__("Please select or upload a document first."));
            return;
        }

        frappe.dom.freeze(__("Extracting document..."));

        try {
            const response = await frappe.call({
                method: "frappe_docai.api.process",
                args: {
                    file_url,
                    configuration: "YOUR_OCR_CONFIGURATION"
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

            if (result.vendor_name) {
                await frm.set_value("supplier", result.vendor_name);
            }

            if (result.invoice_number) {
                await frm.set_value("custom_invoice_number", result.invoice_number);
            }

            if (result.date) {
                await frm.set_value("custom_invoice_date", result.date);
            }

            if (result.total_amount != null) {
                await frm.set_value("custom_invoice_total", result.total_amount);
            }

            frm.refresh_fields();
        } catch (err) {
            console.error("Document AI error:", err);
            frappe.msgprint(
                __("Document extraction failed: {0}", [err.message || err])
            );
        } finally {
            frappe.dom.unfreeze();
        }
    }
});
```

Replace field names with fields that actually exist on your DocType.

---

# 13. Uploading a File and Calling V3

A common pattern is to use Frappe's file uploader and call V3 immediately after a successful upload.

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
                configuration: "YOUR_OCR_CONFIGURATION"
            }
        });

        const apiResult = response.message || {};

        if (!apiResult.valid) {
            frappe.msgprint(
                apiResult.validation?.reason ||
                __("Document extraction failed validation.")
            );
            return;
        }

        const result = apiResult.corrected || {};

        console.log("Corrected extraction:", result);
        // Map result into your ERPNext form here.
    }
});
```

`file_doc.file_url` is the value passed to the V3 backend.

---

# 14. Use `corrected`, Not Raw `extracted`

A successful response can contain both:

```text
extracted
corrected
```

The meaning is:

```text
Gemini
  ↓
extracted
  ↓
financial validator
  ↓
corrected
```

`extracted` is the direct semantic-model output.

`corrected` is the result after deterministic financial validation.

For accounting-related field population, use:

```javascript
const result = response.message.corrected || {};
```

Do not directly populate ERPNext financial fields from `extracted` unless you intentionally need the raw model result for debugging.

---

# 15. Response Structure

A successful V3 response has the general shape:

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

The exact fields inside `extracted` and `corrected` depend on the selected OCR Configuration schema.

---

# 16. Populating Line Items

The current invoice line structure is:

```text
line_items[]
    particular
    base_amount
    gst_percent
    gst_amount
    total_amount
```

Example Client Script mapping:

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

The target field names are application-specific. Replace them with the actual custom fields on your DocType.

---

# 17. Supplier / Vendor Matching

The V3 backend returns extracted vendor information; matching that value to an ERPNext Supplier is integration-specific logic.

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
        await frm.set_value("party_type", "Supplier");
        await frm.set_value("party", supplierResponse.message.name);
    }
}
```

This is intentionally not hardcoded inside `frappe_docai` because every consuming ERPNext workflow may have different field mapping requirements.

---

# 18. Reusing the Same API for Different Documents

The API is designed so the document type is selected through configuration rather than through a different backend endpoint.

Examples:

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

```javascript
// Purchase Receipt / GRN
configuration: "purchase_receipt_config_name"
```

```javascript
// Delivery Note
configuration: "delivery_note_config_name"
```

The reusable API remains:

```text
frappe_docai.api.process
```

---

# 19. Optional `options`

The V3 API accepts an optional `options` argument:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url,
        configuration: "YOUR_OCR_CONFIGURATION",
        options: {
            example_option: true
        }
    }
});
```

Use only option names that are supported by the current backend implementation. Do not assume arbitrary options are accepted.

---

# 20. Payment Entry Integration

Payment Entry was the original concrete ERPNext use case.

The project-specific Payment Entry Client Script currently performs a workflow similar to:

```text
1. Open invoice file uploader
2. Upload vendor invoice
3. Save file URL
4. Call frappe_docai.api.process
5. Read corrected JSON
6. Set invoice number
7. Set invoice date
8. Determine NEFT / RTGS from the total
9. Attempt supplier matching
10. Populate custom item rows
11. Set GST / tax-related fields
12. Select an appropriate bank account when needed
13. Keep the uploaded invoice attached permanently after save
```

The generic V3 backend only performs extraction and validation. Payment Entry business logic remains in the Payment Entry Client Script.

---

# 21. GST and Tax Handling

Tax representation is one of the most important parts of V3 because tax data can appear in materially different forms on real invoices.

The current model supports two primary representations.

## 21.1 Consolidated GST

When GST is applied to the combined taxable base:

```text
Base 1 = 10044
Base 2 = 5357
Combined base = 15401

CGST 9% = 1386.09
SGST 9% = 1386.09
```

The normalized representation can be:

```text
top-level gst_percentage = 18
top-level gst_amount = 2772.18
```

and line-level GST remains zero:

```text
gst_percent = 0
gst_amount = 0
```

## 21.2 Line-level GST

When tax is independently applied to each line:

```text
top-level gst_percentage = 0
top-level gst_amount = 0
```

and each line keeps its own tax values:

```text
line.gst_percent
line.gst_amount
```

Example:

```text
Line 1: base 75000, GST 18%, GST amount 6750
Line 2: base 84.75, GST 18%, GST amount 15.25
```

## 21.3 Critical tax rule

Never add tax rates simply because multiple percentage values exist.

This is wrong:

```text
Line 1 = 18%
Line 2 = 18%
18% + 18% = 36%  <-- wrong
```

Those rates apply to different taxable bases.

The correct principle is:

> **Only combine tax rates when the tax components apply to the same taxable base / scope.**

For example, when both of these apply to the same consolidated base:

```text
CGST 9%
SGST 9%
```

then the components can be represented together as:

```text
18%
```

with the amounts summed as well.

## 21.4 Rate / amount inconsistency

The model may report a rate and an amount that do not mathematically agree.

For example:

```text
Base = 75000
Reported rate = 18%
Expected tax = 13500
Reported tax = 6750
```

The validator should detect that inconsistency rather than silently accepting both values as truth.

## 21.5 Layered taxation: current limitation

A more complicated invoice may contain:

```text
line-level GST
+
additional invoice-level tax / surcharge
```

The current V3 development identified this as an important next-stage tax-model refinement.

A future production-grade tax model may need to represent each tax component using information such as:

```text
label
rate
amount
scope
taxable_base
line reference (when applicable)
```

This allows deterministic normalization into:

```text
CONSOLIDATED
LINE LEVEL
```

or a layered combination.

The application should preserve the extracted tax evidence before normalization so that corrections remain auditable.

---

# 22. Financial Validation

V3 introduced a deterministic financial validation layer because a language model can understand a document correctly while still producing an arithmetic mistake.

The conceptual pipeline is:

```text
Gemini output
      ↓
extracted JSON
      ↓
financial_validator.py
      ↓
corrected JSON
      ↓
final validation
```

The validator can address cases such as:

- line GST amount inconsistent with an explicit line rate
- line total inconsistent with base + tax
- invoice total inconsistent with subtotal + applicable tax
- invoice-level tax accidentally copied into every line
- consolidated tax incorrectly represented as line tax

The key design rule is:

> **Never silently accept arithmetic contradictions just because the model returned them.**

---

# 23. API Logging and Observability

V3 includes an **OCR API Log** DocType for diagnostics and auditability.

Important fields include:

```text
api_method
file_url
configuration
provider
model
status
raw_response
extracted_json
validator_response
corrected_json
financial_validation
final_validation
token_usage
credits_used_inr
usage_metadata
gemini_request_time
total_processing_time
error
debug_information
request_options
```

When an extraction is wrong, inspect the pipeline in this order:

```text
raw_response
      ↓
extracted_json
      ↓
corrected_json
      ↓
financial_validation
      ↓
final_validation
```

This makes it possible to distinguish:

```text
Gemini extraction issue
```

from:

```text
financial-validator correction
```

from:

```text
final validation failure
```

---

# 24. Token Usage and Cost Tracking

The V3 provider records model usage metadata returned by Gemini.

Typical information includes:

```text
input tokens
output tokens
total tokens
usage metadata
estimated USD
estimated INR
timing
```

One representative successful test request used approximately:

```text
input tokens  = 2082
output tokens = 370
```

The application-side estimate for that request was approximately:

```text
₹0.15
```

This estimate is for application-side monitoring and auditing.

**It is not the same thing as the final Google Cloud billing statement.**

Treat the Google Cloud billing statement as the source of truth for actual charged usage.

Google model usage is billed according to usage rather than a single fixed price per API request.

---

# 25. Network and Authentication Behavior

The V3 provider uses an HTTP timeout of:

```text
30 seconds
```

This is intentionally shorter than the earlier 120-second timeout so a stalled request fails sooner.

Error handling exposes useful information for:

```text
HTTP errors
network errors
Google response body
underlying exception text
```

This is much more useful than returning only a generic extraction error.

## 25.1 401 UNAUTHENTICATED

A `401` from the Google endpoint generally indicates that the request did not contain a valid OAuth bearer token.

Check:

```text
Service-account JSON
Service-account email
Project ID
Token generation
Authorization header
```

Do not put the service-account private key in Client Script code as a workaround.

## 25.2 403 PERMISSION_DENIED

Check that the service account has:

```text
roles/aiplatform.user
```

and that the configured project is correct.

## 25.3 Request hangs

Check:

```text
Google connectivity
model endpoint
authentication
network path
Google response
```

A simple connectivity test is:

```bash
curl -I --connect-timeout 5 --max-time 10 \
  https://aiplatform.googleapis.com
```

This only confirms host reachability; it does not authenticate or execute the model request.

---

# 26. Testing and V3 Validation History

The V3 development process included several layers of testing.

## 26.1 OCR reconstruction regressions

Earlier normalized bounding-box / row-reconstruction cases were regression-tested after the compatibility fix.

## 26.2 V3 core test suite

The broader V3 core suite reached:

```text
44 passed
```

## 26.3 Direct Google connectivity

Authenticated minimal model generation:

```text
HTTP 200
~1.57 seconds
```

Direct one-page PDF request:

```text
HTTP 200
~2.16 seconds
```

These tests established that the service account, endpoint, and model access were functioning.

## 26.4 Repeated invoice extraction

The primary test invoice was processed five consecutive times after the response-schema fix.

All five returned the complete expected structure:

```text
invoice number: TI-104
date: 2026-09-09
line items: 2
total: 18173.18
tax: 2772.18
valid: True
```

The repeated test was important because the original issue was intermittent sparse model output rather than a deterministic Python exception.

---

# 27. Primary Development Test Invoice

The primary development PDF was:

```text
TEN BILL (1).pdf
```

Important printed values included:

```text
Vendor: TEN INDIA
Invoice number: TI-104
Invoice date: 09-09-2026
```

Line bases:

```text
10,044.00
5,357.00
```

Subtotal:

```text
15,401.00
```

Printed tax:

```text
CGST 1,386.09
SGST 1,386.09
```

Grand total:

```text
18,173.18
```

The noisy OCR date formatting in the earlier architecture was one reason direct document understanding was valuable in V3.

---

# 28. Debugging a Wrong Extraction

When the output is wrong, do not immediately change the Client Script or the prompt.

First inspect the corresponding **OCR API Log**.

Compare:

```text
raw_response
extracted_json
corrected_json
financial_validation
validation
```

### Case A — Gemini extracted the document incorrectly

You will normally see the incorrect information already present in the raw / extracted result.

Then investigate:

```text
OCR Configuration
Extraction Instructions
Output Schema
Document evidence
Model behavior
```

### Case B — Gemini extracted something reasonable but the final result is different

Compare:

```text
extracted_json
```

against:

```text
corrected_json
```

If the values changed there, the financial validator made the correction.

### Case C — Final validation fails

Inspect:

```text
financial_validation
validation
```

and the corresponding log record.

---

# 29. Common Mistakes

## Mistake 1 — Installing the old V1 branch

Do not use:

```bash
bench get-app ... --branch version-1
```

for a fresh V3 deployment.

Use:

```bash
bench get-app --branch version-3 \
  https://github.com/laxminarayan-dev/frappe_docai.git
```

## Mistake 2 — Using the old API

Old:

```text
frappe_docai.api.process_invoice
```

V3:

```text
frappe_docai.api.process
```

## Mistake 3 — Reading `extracted` instead of `corrected`

For ERPNext financial population, use:

```javascript
response.message.corrected
```

## Mistake 4 — Putting Google credentials in JavaScript

Never put the service-account JSON or access token in a Client Script.

## Mistake 5 — Assuming one tax percentage always represents one line

Tax needs to be interpreted by taxable base and scope.

## Mistake 6 — Treating application cost estimation as Google billing

`credits_used_inr` and related values are application-side estimates. They are not the authoritative billing statement.

---

# 30. Security Model

The V3 security model is:

```text
Browser / Client Script
        |
        | file_url + configuration + optional options
        v
Frappe server
        |
        | private credential lookup
        v
Google Cloud
```

The browser does **not** receive the service-account private key.

The Client Script should only send:

```text
file_url
configuration
options
```

The Google credentials remain server-side in the Frappe Google Cloud Connection configuration.

For production deployments:

- keep service-account JSON private
- avoid committing keys to source control
- use the minimum practical IAM permission set
- keep API logging enabled for auditability
- review cost metadata and Google Cloud billing separately

---

# 31. Optional Legacy Google Services

These services may still be useful for older code paths, tests, or future OCR workflows, but they are **not required by the normal V3 direct-PDF runtime**.

## Document AI API

```bash
gcloud services enable documentai.googleapis.com \
  --project=YOUR_PROJECT_ID
```

## Vision API

```bash
gcloud services enable vision.googleapis.com \
  --project=YOUR_PROJECT_ID
```

## Cloud Storage API

```bash
gcloud services enable storage.googleapis.com \
  --project=YOUR_PROJECT_ID
```

GCS was used during earlier asynchronous OCR testing with an input/output layout such as:

```text
input/
output/
```

The V3 direct-PDF runtime does not need that flow for the normal Gemini request.

---

# 32. Direct API Validation from Bench

After configuration, you can validate the backend directly from the Bench.

Open the console:

```bash
bench --site YOUR_SITE_NAME console
```

Check that the application module and configuration DocTypes exist:

```python
import frappe

print(
    "frappe_docai:",
    frappe.db.exists("Module Def", "Frappe Document AI")
)

print(
    "Google Cloud Connection:",
    frappe.db.exists("DocType", "Google Cloud Connection")
)

print(
    "OCR Configuration:",
    frappe.db.exists("DocType", "OCR Configuration")
)

print(
    "OCR API Log:",
    frappe.db.exists("DocType", "OCR API Log")
)
```

You can then execute the API against a test file:

```bash
bench --site YOUR_SITE_NAME execute frappe_docai.api.process \
  --kwargs '{"file_url":"/private/files/YOUR_TEST_PDF.pdf","configuration":"YOUR_OCR_CONFIGURATION"}'
```

A successful run should contain:

```text
valid = true
```

and a populated:

```text
corrected
```

object.

---

# 33. Recommended Deployment Order

For a clean deployment, follow this sequence:

```text
Frappe / ERPNext
        ↓
Bench
        ↓
Download frappe_docai version-3
        ↓
Install application
        ↓
Install / resolve Python dependencies
        ↓
Migrate
        ↓
Clear cache
        ↓
Google Cloud project
        ↓
Billing
        ↓
Vertex AI API
        ↓
Service account
        ↓
roles/aiplatform.user
        ↓
JSON key
        ↓
Google Cloud Connection
        ↓
OCR Configuration
        ↓
Upload test PDF
        ↓
frappe_docai.api.process
        ↓
Verify corrected JSON
        ↓
Connect Client Script
        ↓
Populate ERPNext
```

---

# 34. Production Readiness Rules

The V3 project established several design rules that should remain true as the application grows.

## Reusability

Do not hardcode one invoice layout into the backend.

Use:

```text
OCR Configuration
```

for schema and instructions.

## Untrusted model output

Gemini performs document understanding.

The financial validator performs deterministic accounting checks.

## Preserve evidence

Keep raw response / tax evidence available before normalization.

## Base-aware tax aggregation

Never add rates across unrelated taxable bases.

```text
18% on line 1
+
18% on line 2
≠ 36%
```

## Deterministic financial correction

Do not silently accept contradictions such as:

```text
base × rate != reported tax
```

unless the business rules explicitly justify another interpretation.

## Server-side credentials

Never move service-account secrets into browser code.

## Observability

Record:

```text
request
response
usage
cost estimate
timing
validation result
```

so model behavior can be investigated after the fact.

---

# 35. Known V3 Limitation / Next Engineering Area

The main remaining engineering area identified during V3 is the **tax-normalization model**.

A production-grade implementation should eventually distinguish all of these cases without ambiguity:

```text
1. No tax
2. Line-level GST
3. Consolidated GST
4. Multiple components on one consolidated taxable base
5. Multiple line-level tax components
6. Line-level tax + additional invoice-level tax / surcharge
7. Rate / amount inconsistencies
8. Different taxable bases
```

The recommended conceptual tax component model is:

```text
Tax component
    ├── label
    ├── rate
    ├── amount
    ├── scope
    ├── taxable_base
    └── line reference (when applicable)
```

The deterministic normalizer can then decide whether the business representation is:

```text
CONSOLIDATED
LINE LEVEL
LAYERED
```

This area should be finalized before claiming the tax validator is complete for every possible invoice structure.

---

# 36. Current Project Structure — Conceptual Responsibilities

The V3 source is organized around clear responsibilities rather than putting all logic in the API method.

The main responsibilities are:

```text
API layer
    → receives file_url / configuration / options

Configuration layer
    → loads OCR Configuration and Google Cloud Connection

Semantic provider
    → sends original document bytes + instructions + schema to Gemini

Schema conversion
    → converts configured schema into provider response schema
    → adds required object properties
    → includes tax evidence required by validation

Financial validation
    → validates and corrects arithmetic / tax representation

Logging
    → records raw response, extracted JSON, corrected JSON,
      validation, usage, cost estimate, timings, and errors
```

The public API intentionally hides these implementation details from the Client Script.

---

# 37. Quick Reference

## Repository

```text
https://github.com/laxminarayan-dev/frappe_docai
```

## V3 branch

```text
version-3
```

## Main API

```text
frappe_docai.api.process
```

## Do not use for new V3 integrations

```text
frappe_docai.api.process_invoice
```

## Provider

```text
VertexAISemanticProvider
```

## Model

```text
gemini-3.5-flash-lite
```

## Location

```text
global
```

## Configuration DocType

```text
OCR Configuration
```

## Google credential DocType

```text
Google Cloud Connection
```

## Logging DocType

```text
OCR API Log
```

## Primary development test PDF

```text
TEN BILL (1).pdf
```

## Primary test invoice

```text
TI-104
```

## Primary test total

```text
18173.18
```

## Primary test tax

```text
2772.18
```

## Test baseline

```text
44 passed
```

---

# 38. Full Example: Reusable Extraction Helper

When several Client Scripts use `frappe_docai`, the API call itself can be kept in a small helper.

```javascript
async function extractDocument(file_url, configuration) {
    const response = await frappe.call({
        method: "frappe_docai.api.process",
        args: {
            file_url,
            configuration
        }
    });

    const apiResult = response.message || {};

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
    "YOUR_OCR_CONFIGURATION"
);

console.log(result);
```

This pattern keeps the reusable backend API the same while allowing each DocType to handle its own ERPNext field mapping.

---

# 39. Full Example: Payment Entry Flow

A simplified Payment Entry integration looks like:

```javascript
async function extractInvoiceToPaymentEntry(frm, file_doc) {
    frappe.dom.freeze(__("Extracting vendor invoice..."));

    try {
        const response = await frappe.call({
            method: "frappe_docai.api.process",
            args: {
                file_url: file_doc.file_url,
                configuration: "YOUR_INVOICE_OCR_CONFIGURATION"
            }
        });

        const apiResult = response.message || {};

        if (!apiResult.valid) {
            throw new Error(
                apiResult.validation?.reason ||
                "Invoice extraction failed validation."
            );
        }

        const result = apiResult.corrected || {};

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

        if (result.total_amount != null) {
            await frm.set_value(
                "custom_total_amount",
                result.total_amount
            );
        }

        frm.clear_table("custom_items");

        for (const item of result.line_items || []) {
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
    } finally {
        frappe.dom.unfreeze();
    }
}
```

This is intentionally only the extraction-to-form portion. Supplier matching, bank-account selection, NEFT/RTGS logic, attachment persistence, and other Payment Entry business rules remain consumer-specific.

---

# 40. Final Architecture Summary

The V3 application can be summarized as:

```text
                ERPNext
                   │
                   │ upload/select PDF
                   ▼
          frappe_docai.api.process
                   │
                   │ configuration
                   ▼
            OCR Configuration
                   │
                   ▼
      Gemini / Vertex AI Agent Platform
                   │
                   │ structured JSON
                   ▼
        Deterministic Financial Validator
                   │
                   │ corrected JSON
                   ▼
             Final Validation
                   │
                   ▼
         ERPNext Client Script
                   │
                   ▼
          Business Documents
```

The most important architectural principles are:

```text
Reusable configuration
        +
Direct document understanding
        +
Structured output
        +
Deterministic financial validation
        +
Server-side credentials
        +
Per-call observability
        =
Reusable Frappe Document AI service
```

---

# 41. Official Documentation

## Frappe

- Bench commands: https://docs.frappe.io/framework/user/en/bench/bench-commands
- Frappe apps: https://docs.frappe.io/framework/user/en/basics/apps
- Create a site: https://docs.frappe.io/framework/user/en/tutorial/create-a-site
- Production setup: https://docs.frappe.io/framework/user/en/production-setup

## Google Cloud

- Gemini 3.5 Flash-Lite: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite
- Agent Platform locations: https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations
- Vertex AI access control: https://cloud.google.com/vertex-ai/docs/general/access-control
- Create service accounts: https://docs.cloud.google.com/iam/docs/service-accounts-create
- Service-account keys: https://docs.cloud.google.com/iam/docs/keys-create-delete
- Process PDF with Gemini: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-with-pdf
- Agent Platform pricing: https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing

---

# 42. Final Deployment Checklist

## Frappe / ERPNext

- [ ] Frappe 16.x installed
- [ ] ERPNext 16.x installed
- [ ] Bench working
- [ ] Git available
- [ ] `frappe_docai` downloaded from `version-3`
- [ ] App installed on target site
- [ ] Python dependencies resolved
- [ ] Site migrated
- [ ] Cache cleared
- [ ] Bench restarted

## Google Cloud

- [ ] Project selected
- [ ] Billing enabled
- [ ] `aiplatform.googleapis.com` enabled
- [ ] Service account created
- [ ] `roles/aiplatform.user` granted
- [ ] JSON key created
- [ ] JSON key kept private
- [ ] Gemini 3.5 Flash-Lite available
- [ ] Location configured as `global`

## Frappe configuration

- [ ] Google Cloud Connection created
- [ ] Project ID entered
- [ ] Service-account email entered
- [ ] JSON uploaded privately
- [ ] OCR Configuration created
- [ ] Semantic Provider = Google Agent Platform
- [ ] Semantic Model = `gemini-3.5-flash-lite`
- [ ] Semantic Location = `global`
- [ ] Semantic Endpoint left blank
- [ ] Extraction instructions configured
- [ ] Output schema configured

## Testing

- [ ] Google authentication test passes
- [ ] Direct PDF model test passes
- [ ] `frappe_docai.api.process` works
- [ ] `valid = true`
- [ ] `corrected` is populated
- [ ] `OCR API Log` is created
- [ ] Client Script calls the V3 API
- [ ] ERPNext fields populate correctly
- [ ] Line items populate correctly
- [ ] Financial corrections are understood before posting accounting data

---

# 43. Version / Compatibility Note

This README documents the **V3 runtime on the `version-3` branch**.

The old V1/V2 material may still exist elsewhere in the repository or project documentation and may refer to:

```text
Google Document AI
Vision OCR
Cloud Storage
OCR table reconstruction
process_invoice
```

Those should not be confused with the current V3 path:

```text
PDF
  ↓
Gemini 3.5 Flash-Lite
  ↓
financial validator
  ↓
corrected JSON
  ↓
ERPNext
```

For a fresh V3 installation or integration, use this README and the `version-3` branch as the starting point.

---

## License

MIT
