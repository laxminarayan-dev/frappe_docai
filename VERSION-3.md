# frappe_docai — Version 3 Development Journey

## 1. Document purpose

This is the engineering history of **Version 3 (V3)** of the reusable `frappe_docai` application: the original goal, architecture changes, Google Cloud setup, extraction pipeline, debugging, schema changes, financial validation, API logging, Payment Entry integration, testing, billing investigation, and the tax-model questions that remain to be finalized.

The main objective was to build a reusable document-extraction service for ERPNext business documents rather than hardcoding one invoice layout. The intended future scope includes invoices, Purchase Orders, Packing Lists, Delivery Notes, GRNs / Purchase Receipts, and other structured documents.

---

## 2. Environment

| Component | Current value |
|---|---|
| Frappe | 16.31.0 |
| ERPNext | 16.32.3 |
| `frappe_docai` | 0.0.1 |
| Site | `vendor2.site` |
| Bench | `~/frappe-bench` |
| App path | `/home/lucky/frappe-bench/apps/frappe_docai` |
| Frappe module | `Frappe Document AI` |
| Python | 3.14.x in the live environment |

Installed apps in the development bench include:

```text
frappe
erpnext
frappe_docai
origen_desk_kit
```

---

# 3. Original problem

The original use case was invoice extraction in **Payment Entry**.

The desired workflow was:

```text
Payment Entry
    ↓
Upload vendor invoice
    ↓
Document processing
    ↓
Invoice information extraction
    ↓
Financial validation
    ↓
Populate Payment Entry
```

Target information included:

```text
Vendor / Supplier
Invoice number
Invoice issue date
Invoice total
Total tax
Line items
Description / particular
Base amount
GST percentage
GST amount
Line total
```

The system also had to be reusable, configurable, and independent from ERPNext core changes.

---

# 4. Earlier V1/V2 direction

The earlier implementation centered on Google Document AI / OCR processing.

Conceptually:

```text
Payment Entry
    ↓
Frappe File
    ↓
Google Document AI / OCR
    ↓
OCR text + entities + table information
    ↓
Custom normalization
    ↓
Table/row reconstruction
    ↓
Invoice JSON
    ↓
Payment Entry
```

This introduced substantial complexity around table rows, bounding boxes, and spatial association.

A key bug was discovered in row reconstruction: the normalized Vision words exposed `bbox` data and precomputed `x_center` / `y_center`, while one version of the reconstructor expected raw `boundingBox.vertices`. The reconstructor was changed to support the actual normalized structure without disturbing column grouping and association behavior.

Focused regression testing covered normalized bounding-box input plus one-row, two-row, three-row, and row-association cases. The focused reconstruction tests passed, and the broader V3 core suite later reached:

```text
44 passed
```

---

# 5. Why V3 changed the runtime architecture

The requirement expanded beyond OCR. The system needed semantic understanding of the original document, better handling of different invoice layouts, and reusable structured extraction.

The runtime architecture was therefore redesigned to:

```text
PDF
 ↓
Gemini directly reads original document
 ↓
Structured JSON
 ↓
Deterministic financial validation
 ↓
Final JSON
```

Important architectural decision:

> **Google Vision was removed from the normal V3 runtime extraction path.**

`google_vision.py` was retained for compatibility / existing functionality, but the new V3 `process()` runtime does not use Vision as the semantic extraction step.

---

# 6. Google Cloud environment

A Google Cloud project was prepared for the V3 runtime.

## Project

```text
gen-lang-client-0690478224
```

## Service account

```text
frappe-ocr@gen-lang-client-0690478224.iam.gserviceaccount.com
```

## Cloud components involved

- Vertex AI / Agent Platform
- Gemini
- Google Vision API
- Google Cloud Storage
- Google Document AI

The final V3 semantic runtime uses Vertex AI / Agent Platform with Gemini.

## Credential storage

The service-account JSON is stored privately in the Frappe `Google Cloud Connection` DocType rather than being exposed to the browser.

Current connection:

```text
Google Cloud Connection
name = fd0k5bsbpu
enabled = 1
project = gen-lang-client-0690478224
service account = frappe-ocr@gen-lang-client-0690478224.iam.gserviceaccount.com
service account file = /private/files/gen-lang-client-0690478224-4a0908634867.json
```

---

# 7. Google Cloud Storage work

A private GCS bucket was also prepared during the V3 work:

```text
Bucket: frappe-ocr
Region: asia-south2 (Delhi)
```

Prefixes:

```text
input/
output/
```

A test invoice was placed at:

```text
gs://frappe-ocr/input/TEN BILL (1).pdf
```

Earlier Vision asynchronous OCR testing successfully wrote output under:

```text
gs://frappe-ocr/output/output-1-to-1.json
```

This established that the Google-side document environment was working before the runtime architecture moved to direct Gemini PDF reading.

---

# 8. OCR Configuration DocType

V3 introduced a reusable configuration DocType so model/provider behavior was not hardcoded into the application.

Current configuration:

```text
OCR Configuration
name = 7ujjqp2oki
api_name = invoice_extraction
enabled = 1
```

Important fields:

```text
semantic_provider
semantic_model
semantic_location
semantic_endpoint
extraction_instructions
output_schema
google_cloud_connection
```

Current semantic configuration is:

```text
Provider: Google Agent Platform
Model: gemini-3.5-flash-lite
Location: global
Endpoint: blank
```

The configuration approach was designed so one `frappe_docai` installation can support different document types by using different schema/instruction records.

---

# 9. Semantic provider architecture

The V3 code introduced a replaceable semantic-provider contract.

The main implementation is:

```text
VertexAISemanticProvider
```

The provider factory recognizes Google provider aliases including:

```text
vertex_ai
vertex
google_vertex_ai
google_agent_platform
```

The provider was extended to accept the original document directly:

```text
document_bytes
mime_type
file_name
instructions
schema
```

This preserved compatibility with the earlier raw-text / reconstructed-row interface while enabling the new direct-PDF pipeline.

---

# 10. Direct PDF → Gemini

The major V3 implementation change was sending the original PDF itself to Gemini instead of depending on only reconstructed OCR text.

The request contains conceptually:

```text
inlineData
    mimeType = application/pdf
    data = base64(PDF)
```

and the instruction prompt.

So the semantic stage is:

```text
Frappe File
   ↓
PDF bytes
   ↓
Gemini inlineData
   ↓
Semantic JSON
```

This allows the model to inspect the original invoice layout.

---

# 11. Structured JSON response

Gemini was configured for structured JSON using:

```text
responseMimeType = application/json
responseSchema = configured schema
```

The provider also extends the configured schema internally with:

```text
tax_components
```

so printed tax evidence can be passed to deterministic financial validation.

The public output schema contains invoice fields and line items, including:

```text
vendor_name
invoice_number
date
total_amount
tax_amount
gst_percentage
gst_amount
line_items[]
```

Each line contains:

```text
particular
base_amount
gst_percent
gst_amount
total_amount
```

---

# 12. Intermittent sparse-response problem

After the direct Gemini pipeline was introduced, the same PDF sometimes produced a complete response and sometimes a very sparse response.

A sparse result looked like:

```json
{
  "vendor_name": "TEN INDIA",
  "invoice_number": null,
  "date": null,
  "total_amount": null,
  "tax_amount": null,
  "line_items": [],
  "tax_components": []
}
```

One such response used only about:

```text
15 output tokens
```

while a complete response used about:

```text
360–370 output tokens
```

This established that the problem was not a Python exception in the financial validator.

---

# 13. Raw Gemini response logging

To diagnose the intermittent behavior, an `OCR API Log` DocType was created.

It records:

```text
API method
file URL
configuration
provider
model
status
raw Gemini response
extracted JSON
validator response
corrected JSON
financial validation
final validation
token usage
estimated cost
usage metadata
Gemini request time
total processing time
errors
debug information
request options
```

The provider was changed to retain the full Gemini response payload so the application could store the actual raw response instead of only the normalized result.

This confirmed that different Google calls genuinely returned different candidate contents, rather than the difference being introduced by the Frappe post-processing code.

---

# 14. Network / authentication investigation

At one point the HTTP request appeared to hang for a long time. The traceback showed the process blocked inside:

```python
urllib.request.urlopen(...)
```

A direct endpoint test showed the Google service was reachable.

An unauthenticated direct model request returned:

```text
401 UNAUTHENTICATED
```

which was expected because no OAuth bearer token was supplied.

Then the actual Frappe-side credentials were used.

A minimal authenticated Gemini request returned:

```text
STATUS: 200
TIME: about 1.57 seconds
```

and a direct authenticated PDF request returned:

```text
STATUS: 200
TIME: about 2.16 seconds
```

Therefore the endpoint, service-account authentication, and model itself were all functioning.

---

# 15. HTTP timeout improvement

The provider originally used:

```text
timeout = 120 seconds
```

It was changed to:

```text
timeout = 30 seconds
```

This was a diagnostic/reliability improvement so a stalled request would fail much sooner.

Error handling was also improved so that:

- HTTP errors expose the status code and response body.
- Network errors expose the underlying exception text.

This is much more useful than a generic `semantic extraction request failed` message.

---

# 16. Deterministic generation

The Gemini generation configuration was changed to:

```json
{
  "temperature": 0,
  "responseMimeType": "application/json",
  "responseSchema": "..."
}
```

The intent was to reduce unnecessary generation variability.

---

# 17. The main sparse-response fix: required schema fields

The generated response schema initially contained properties but did not explicitly mark object properties as required.

That meant Gemini could legally return a partial object.

The schema conversion function was changed so every generated `OBJECT` automatically receives a `required` list containing all of its properties.

Conceptually:

```json
{
  "type": "OBJECT",
  "properties": {
    "vendor_name": {"type": "STRING"},
    "invoice_number": {"type": "STRING"},
    "date": {"type": "STRING"}
  },
  "required": [
    "vendor_name",
    "invoice_number",
    "date"
  ]
}
```

This was the key schema-level change that made repeated extraction stable.

---

# 18. Stability test after the schema fix

The same invoice was then processed repeatedly.

Results:

```text
RUN 1 → complete
RUN 2 → complete
RUN 3 → complete
RUN 4 → complete
RUN 5 → complete
```

All five runs returned:

```text
date: 2026-09-09
invoice: TI-104
items: 2
total: 18173.18
tax: 2772.18
valid: True
```

This brought the V3 extraction pipeline back to a stable baseline.

---

# 19. Primary test invoice

The main test file was:

```text
TEN BILL (1).pdf
```

Key printed information includes:

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

The OCR/source text also contained noisy date formatting, so direct document understanding by Gemini was important for correctly reading the date.

---

# 20. Financial validator

V3 introduced a deterministic financial-validation layer.

Architecture:

```text
Gemini
  ↓
extracted JSON
  ↓
financial_validator.py
  ↓
corrected JSON
  ↓
final validation
```

The validator treats Gemini output as untrusted semantic data and checks arithmetic relationships independently.

It can correct:

- line GST amounts inconsistent with explicit line rates
- line totals inconsistent with base + line GST
- invoice totals inconsistent with the deterministic subtotal/tax calculation
- invoice-level tax incorrectly copied into individual lines

---

# 21. Confirmed consolidated-tax behavior

For the `TEN INDIA` example, Gemini returned line GST values as well as invoice-level tax components:

```text
Line 1: 18% / 1807.92
Line 2: 18% / 964.26

CGST 9%  = 1386.09
SGST 9%  = 1386.09
```

The validator recognized the printed CGST/SGST as invoice-level evidence and removed the duplicated line allocation.

The corrected line data became:

```text
Line 1:
gst_percent = 0
gst_amount = 0
total_amount = 10044

Line 2:
gst_percent = 0
gst_amount = 0
total_amount = 5357
```

while the invoice-level tax remained:

```text
tax = 2772.18
```

and:

```text
subtotal = 15401
grand_total = 18173.18
```

The financial result was valid.

---

# 22. Important tax-model clarification

The ERP business requirement was then clarified further.

There are two primary desired GST representations.

## A. GST on consolidated taxable base

Example:

```text
Base 1 = 10044
Base 2 = 5357
Combined base = 15401

CGST 9% = 1386.09
SGST 9% = 1386.09
```

Desired normalized structure:

```text
top-level gst_percentage = 18
top-level gst_amount = 2772.18
```

and each line has:

```text
gst_percent = 0
gst_amount = 0
```

## B. GST on individual line items

Example:

```text
Line 1 → IGST 18% → 6750
Line 2 → IGST 18% → 15.25
```

Desired normalized structure:

```text
top-level gst_percentage = 0
top-level gst_amount = 0
```

while each line retains:

```text
gst_percent
gst_amount
```

---

# 23. Crucial percentage rule

Tax rates must be aggregated according to **tax scope / taxable base**, not merely because multiple percentages are present.

This is correct:

```text
CGST 9% + SGST 9%
```

when both apply to the **same consolidated taxable base**:

```text
9% + 9% = 18%
```

with amounts also summed.

This is not correct:

```text
Line 1 = 18%
Line 2 = 18%
18% + 18% = 36%  ← WRONG
```

Those two rates apply to different line bases, so each line remains 18%.

The normalization principle established during V3 is:

> **Only sum tax percentages when the tax components apply to the same taxable base / scope.**

---

# 24. Second tax example and inconsistency detection

A second example was:

```json
{
  "invoice_number": "DEL5-194299",
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
  ],
  "tax_components": [
    {
      "label": "IGST",
      "rate": 18,
      "amount": 6750,
      "level": "line-level"
    },
    {
      "label": "IGST",
      "rate": 18,
      "amount": 15.25,
      "level": "line-level"
    }
  ],
  "tax_amount": 6765.25
}
```

The important arithmetic observation was:

```text
75000 × 18% = 13500
```

not:

```text
6750
```

Therefore the first line's reported rate and reported amount are mathematically inconsistent.

This led to another important V3 rule:

> **If reported tax rate, taxable base, and tax amount disagree, the validator should identify the inconsistency rather than silently treating the model output as truth.**

---

# 25. Layered taxation question discovered later

A further business case was considered: an invoice may potentially contain both:

```text
line-level GST
+
additional invoice-level tax / surcharge
```

This exposed a limitation in the earlier validator design.

A rule such as:

```text
invoice-level tax exists
→ clear every line GST
```

is not sufficient for every possible real-world invoice.

A production-grade tax model may need to represent:

```text
line tax
invoice/consolidated tax
additional tax / surcharge
individual taxable bases
scope of each component
```

This is an identified next-stage refinement and should be finalized before the tax validator is considered production-complete for all possible invoice structures.

---

# 26. Current configured output schema

The configured schema was expanded with top-level consolidated GST fields:

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
    "description": "Combined GST percentage when GST is applied on the consolidated taxable base of all line items; return 0 when GST is applied at line level"
  },
  "gst_amount": {
    "type": "NUMBER",
    "description": "Combined GST amount when GST is applied on the consolidated taxable base of all line items; return 0 when GST is applied at line level"
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
          "description": "GST percentage applicable to this specific line item; return 0 when GST is applied only on the consolidated taxable base"
        },
        "gst_amount": {
          "type": "NUMBER",
          "description": "GST amount applicable to this specific line item; return 0 when GST is applied only on the consolidated taxable base"
        },
        "total_amount": {
          "type": "NUMBER",
          "description": "Final line item amount including GST"
        }
      }
    }
  }
}
```

---

# 27. API logging and token tracking

V3 tracks per-call model usage.

One representative successful OCR request had approximately:

```text
input tokens  = 2082
output tokens = 370
```

The application-side estimate for that request was approximately:

```text
₹0.15
```

The `OCR API Log` also stores raw usage metadata returned by Gemini so the application can calculate and audit its own estimated model cost.

This application-side estimate is distinct from the final Google Cloud billing statement.

---

# 28. Google Cloud billing investigation

A billing investigation was required because the Google Cloud console showed promotional-credit consumption.

A product/service breakdown showed approximately:

```text
Document AI                 ₹302.88
Agent Platform Model Garden ₹112.16
Cloud Storage                 ₹0.00
-------------------------------------
Total                       ≈ ₹415.04
```

An API metrics screen separately showed request counts for services such as:

```text
Cloud Document AI API
Cloud Vision API
Gemini API
Agent Platform API
```

A key lesson was established:

> **API request-count metrics are not the same thing as billable SKU usage.**

Document AI billing can depend on processed pages / processor type, while Gemini / Agent Platform billing is token-based.

The project was also confirmed to be using remaining promotional / welcome credits after moving to a full billing account.

---

# 29. Billing account investigation

The billing account attached to the project was identified as:

```text
billingAccounts/0162FA-A52DFE-B9E80F
```

Cloud Shell was used to inspect the project and billing environment.

BigQuery was considered for detailed billing analysis and the BigQuery service was enabled when needed for that investigation.

---

# 30. Payment Entry Client Script integration

The original Payment Entry Client Script called:

```text
frappe_docai.api.process_invoice
```

The V3 API is:

```text
frappe_docai.api.process
```

The V3 API requires:

```text
file_url
configuration
```

The intended Client Script call is therefore:

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

The existing Payment Entry mapping can then continue to use:

```text
result.invoice_number
result.date
result.total_amount
result.vendor_name
result.line_items
```

---

# 31. Existing Payment Entry behavior

The Payment Entry client workflow does the following:

1. Opens an invoice file uploader.
2. Saves the uploaded file URL.
3. Calls `frappe_docai.api.process` with the OCR Configuration.
4. Reads the corrected JSON.
5. Sets invoice number.
6. Sets invoice date.
7. Determines NEFT / RTGS based on total.
8. Attempts supplier matching.
9. Populates the `custom_items` child table.
10. Sets `perticular`, `base_amount`, `gst`, `gst_amount`, and `amount_after_tax`.
11. Selects an appropriate bank account when needed.
12. Attaches the uploaded file permanently after save.

---

# 32. Testing history

Important testing milestones:

## Reconstruction tests

The normalized-bounding-box reconstruction issue was fixed and focused reconstruction regressions passed.

## V3 core suite

The broader core test suite reached:

```text
44 passed
```

## Direct Google tests

Minimal authenticated generation:

```text
HTTP 200
~1.57 s
```

Direct one-page PDF request:

```text
HTTP 200
~2.16 s
```

## Repeated invoice test

The same PDF was processed five consecutive times after the required-schema fix.

All five produced the complete expected structure:

```text
TI-104
2026-09-09
2 line items
18173.18 total
2772.18 tax
valid = True
```

---

# 33. Current stable V3 baseline

At the end of this development journey, the stable baseline is:

```text
Frappe 16.31.0
ERPNext 16.32.3
frappe_docai 0.0.1

API:
frappe_docai.api.process

Provider:
VertexAISemanticProvider

Provider label:
Google Agent Platform

Model:
gemini-3.5-flash-lite

Location:
global

Input:
original PDF bytes

Output:
structured JSON

Generation:
temperature = 0
responseMimeType = application/json
required response fields

HTTP timeout:
30 seconds

Observability:
OCR API Log

Financial stage:
deterministic financial_validator.py
```

The repeated test of the primary invoice became stable after the response-schema change.

---

# 34. What was actually fixed in V3

## Architecture

Changed from the OCR-first runtime to:

```text
PDF → Gemini → financial validator → final JSON
```

## Row reconstruction

Fixed normalized `bbox` / center handling from the earlier OCR pipeline.

## Provider interface

Added support for direct document bytes and MIME type while preserving the provider contract.

## Gemini structured output

Enabled JSON response MIME type and structured response schema.

## Deterministic generation

Added:

```text
temperature = 0
```

## Sparse response stability

Made object fields required in the generated response schema.

## Network diagnostics

Reduced the provider timeout and exposed actual HTTP/network errors.

## Observability

Added raw-response, token, credit-estimate, usage-metadata, and timing logging.

## Financial validation

Added deterministic arithmetic checks and correction of model mistakes.

---

# 35. What is not yet fully finalized

The main remaining engineering problem is the **tax normalization model**.

The validator must eventually support all of the following without ambiguity:

```text
1. No tax
2. Line-level GST
3. Consolidated GST
4. Multiple components on one consolidated taxable base
5. Multiple line-level tax components
6. Possible line-level tax + additional invoice-level tax/surcharge
7. Rate/amount inconsistencies
8. Different taxable bases
```

The system should not simply use tax labels such as CGST / SGST / IGST as the business representation. Those labels are evidence from the invoice. The ERP representation needs a generic GST model with explicit scope.

---

# 36. Recommended long-term tax model

A better conceptual model for V3 is:

```text
Tax component
    ├── label
    ├── rate
    ├── amount
    ├── scope
    ├── taxable_base
    └── line reference (when applicable)
```

Then a deterministic normalizer decides whether the final ERP structure is:

```text
CONSOLIDATED
```

or:

```text
LINE LEVEL
```

or a layered combination of both.

The important rule remains:

```text
Same taxable base + multiple components
    → rates may be combined
    → amounts may be combined

Different taxable bases
    → do NOT add rates together
    → keep each rate attached to its own base
```

---

# 37. Production design principles established during V3

## Keep the application reusable

Do not hardcode one invoice layout.

Use:

```text
OCR Configuration
```

for schema and instructions.

## Keep the model untrusted

Gemini performs semantic understanding.

The financial validator determines accounting arithmetic.

## Preserve evidence before normalization

The raw printed tax evidence should remain available to the normalizer.

## Never add rates across unrelated bases

```text
18% + 18% on two different lines ≠ 36%
```

## Never silently accept arithmetic contradictions

If:

```text
base × rate != reported tax amount
```

record the inconsistency and apply deterministic rules only where justified.

## Keep credentials server-side

Service-account JSON must remain private and outside browser code/source control.

## Log model usage

Record:

```text
request
response
usage
cost estimate
timing
validation result
```

so model behavior can be audited.

---

# 38. Final V3 architecture

```text
                         ┌───────────────────────────┐
                         │         ERPNext            │
                         │       Payment Entry        │
                         └────────────┬──────────────┘
                                      │
                                Upload PDF
                                      │
                                      ▼
                         ┌───────────────────────────┐
                         │       frappe_docai         │
                         │        V3 process()        │
                         └────────────┬──────────────┘
                                      │
                              Load configuration
                                      │
                                      ▼
                         ┌───────────────────────────┐
                         │     Gemini / Vertex AI     │
                         │     Direct PDF reading     │
                         └────────────┬──────────────┘
                                      │
                           Structured JSON + evidence
                                      │
                                      ▼
                         ┌───────────────────────────┐
                         │   Financial Validator      │
                         │   Deterministic rules      │
                         └────────────┬──────────────┘
                                      │
                               Corrected JSON
                                      │
                                      ▼
                         ┌───────────────────────────┐
                         │      Final Validation      │
                         └────────────┬──────────────┘
                                      │
                                      ▼
                         ┌───────────────────────────┐
                         │       Payment Entry        │
                         │      Field Population      │
                         └───────────────────────────┘
```

---

# 39. Quick reference

## Main API

```text
frappe_docai.api.process
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

## Site

```text
vendor2.site
```

## Configuration

```text
OCR Configuration: 7ujjqp2oki
```

## Google connection

```text
Google Cloud Connection: fd0k5bsbpu
```

## Log DocType

```text
OCR API Log
```

## Primary test file

```text
TEN BILL (1).pdf
```

## Primary test invoice

```text
TI-104
```

## Primary total

```text
18173.18
```

## Primary tax

```text
2772.18
```

## Test status

```text
44 passed
```

---

# 40. Final status

V3 successfully evolved from an OCR / table-reconstruction implementation into a configuration-driven direct-document semantic extraction service.

The major intermittent Gemini-output problem was investigated using raw responses and was stabilized by tightening the generated response schema and using deterministic generation. The direct PDF endpoint, authentication, model access, and repeated invoice extraction were all verified.

The remaining important engineering task is to finalize the tax-normalization model, especially for invoices that contain:

```text
line-level taxes
consolidated taxes
multiple tax components
layered tax / surcharge
inconsistent rate/amount pairs
```

Once that model is finalized, the financial validator can be treated as the accounting normalization layer between Gemini's document understanding and ERPNext's business data.

---

## End of V3 journey document
