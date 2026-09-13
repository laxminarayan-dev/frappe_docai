# Frappe Document AI — Implementation Guide

This document contains the **implementation, architecture, configuration reference, development history, Payment Entry integration, Google Cloud details, schema, parser behavior, troubleshooting, and reusable deployment model** for `frappe_docai`.

For a quick installation, use the repository `README.md`.

---

# 1. Why We Built This

## 1.1 Problem

The requirement was to upload a vendor invoice from a Payment Entry and automatically extract useful invoice information instead of entering it manually.

Target data:

- Vendor/Supplier name
- Invoice number
- Invoice issue date
- Total invoice amount
- Total tax amount
- Line items
- Item/service description
- Base amount before GST
- GST percentage
- GST amount
- Final line-item amount including GST

Without the app, users have to open the invoice, read it, find the supplier, enter invoice details, and manually create every line item.

## 1.2 Why Google Cloud Document AI

Invoices are structured documents. Information can be spread across tables, columns, and different layouts.

Document AI provides document-processing results containing document text, entities, and tables. The application then uses custom parsing logic to convert those results into the JSON structure required by the Frappe/ERPNext integration.

## 1.3 Why a Separate Frappe App

The functionality is packaged as:

```text
frappe_docai
```

instead of modifying ERPNext core.

Benefits:

- Reusable across Frappe/ERPNext projects
- Separate from ERPNext core
- Easier maintenance and deployment
- Google configuration stored centrally
- Backend API can be reused
- Payment Entry integration can remain separate from the core app

---

# 2. Architecture

```text
Payment Entry
      |
      | Upload Invoice
      v
Frappe File
      |
      v
Payment Entry Client Script
      |
      | frappe.call()
      v
frappe_docai.api.process_invoice
      |
      v
Google Cloud Document AI
      |
      v
Entities + Tables + Document Text
      |
      v
Custom Parser
      |
      v
Structured Invoice JSON
      |
      v
Payment Entry fields + line items
```

---

# 3. Development Environment

The implementation was developed with:

```text
Frappe: 16.31.0
ERPNext: 16.32.3
frappe_docai: 0.0.1
Python: python3
google-cloud-documentai: 3.15.0
```

Bench:

```text
~/frappe-bench
```

Development site:

```text
vendor2.site
```

App path:

```text
/home/lucky/frappe-bench/apps/frappe_docai
```

Module:

```text
Frappe Document AI
```

---

# 4. App Creation

The original app was created from the bench with:

```bash
cd ~/frappe-bench
bench new-app frappe_docai
```

It was installed with:

```bash
bench --site vendor2.site install-app frappe_docai
```

Verify:

```bash
bench --site vendor2.site list-apps
```

---

# 5. Python Dependency

The app uses:

```text
google-cloud-documentai
```

Install:

```bash
cd ~/frappe-bench
bench pip install google-cloud-documentai
```

Verify:

```bash
bench pip show google-cloud-documentai
```

The development environment used version:

```text
3.15.0
```

The dependency is also declared in `pyproject.toml`:

```toml
dependencies = [
    "google-cloud-documentai"
]
```

---

# 6. Document AI Configuration Single DocType

The app contains the Single DocType:

```text
Document AI Configuration
```

Fields:

| Label | Fieldname | Type | Requirement |
|---|---|---|---|
| Enabled | `enabled` | Check | Default 1 |
| Google Cloud Project ID | `project_id` | Data | Mandatory |
| Google Cloud Location | `location` | Data | Mandatory |
| Processor ID | `processor_id` | Data | Mandatory |
| Google Credentials JSON | `credentials_json` | Attach | Mandatory |
| Connection Status | `connection_status` | Small Text | Read Only |
| Last Connection Test | `last_connection_test` | Datetime | Read Only |
| Schema JSON | `schema_json` | Code | Optional |
| Extraction Instructions | `extraction_instructions` | Text | Optional |
| Processor Version | `processor_version` | Data | Mandatory |

The backend reads it using:

```python
frappe.get_single("Document AI Configuration")
```

This keeps Google Cloud configuration outside the source code.

---

# 7. Google Configuration Used During Development

The development environment used:

```text
Project ID:
gen-lang-client-0690478224

Service Account:
msc-vendor-payment@gen-lang-client-0690478224.iam.gserviceaccount.com

Processor ID:
870994bf06747cb2

Location:
asia-south1

Processor Version:
pretrained-foundation-model-v1.5-2025-08-06
```

The credentials were stored in Frappe as a private attachment.

**These development credentials must not be copied to another environment or committed to GitHub.**

For another deployment, create/use that environment's own:

```text
Project
Service Account
Credentials JSON
Processor
Location
Processor Version
```

---

# 8. Google Cloud Project

For a deployment:

1. Select or create a Google Cloud project.
2. Copy the actual Project ID.
3. Keep it for Frappe configuration.

Project ID is different from the project display name.

---

# 9. Document AI API

In Google Cloud:

```text
APIs & Services
→ Library
→ Document AI API
→ Enable
```

The API must be enabled in the project that owns the processor/service-account setup.

---

# 10. Service Account

Create a service account under:

```text
IAM & Admin
→ Service Accounts
```

The service account is used by the Frappe server for Google authentication.

Keep its email address for troubleshooting.

---

# 11. IAM Permissions

The development setup used:

```text
Document AI API User (Beta)
Viewer (Beta)
```

Google Cloud permissions can change over time.

For a new environment, verify the currently available Document AI permissions and grant the service account enough access to process documents with the selected processor.

---

# 12. Service Account JSON

Create a key:

```text
Service Account
→ Keys
→ Add Key
→ Create new key
→ JSON
```

Download the JSON.

Security rules:

```text
DO NOT put it in JavaScript.
DO NOT commit it to Git.
DO NOT put it in a public GitHub repository.
DO NOT expose it to the browser.
DO NOT put it in a public Frappe attachment.
```

Use a private Frappe attachment.

---

# 13. Document AI Processor

The implementation uses a:

```text
Custom Extractor
```

The processor has:

```text
Processor ID
Location
Processor Version
```

These are separate values from the Google Cloud Project ID.

---

# 14. Processor Location

Development location:

```text
asia-south1
```

For another environment, use the actual location displayed for that processor.

Do not blindly reuse the development location.

---

# 15. Processor Version

Development version:

```text
pretrained-foundation-model-v1.5-2025-08-06
```

For another environment, use the version actually available for that processor.

Processor version is separate from:

- Project ID
- Processor ID
- Location

---

# 16. Google-to-Frappe Mapping

| Google Cloud information | Frappe field |
|---|---|
| Project ID | `project_id` |
| Processor Location | `location` |
| Processor ID | `processor_id` |
| Service Account JSON | `credentials_json` |
| Processor Version | `processor_version` |

Application behavior fields:

| Frappe field | Purpose |
|---|---|
| `enabled` | Enable/disable integration |
| `schema_json` | Desired extraction structure |
| `extraction_instructions` | Extraction instructions |
| `connection_status` | Connection/status information |
| `last_connection_test` | Last connection test time |

---

# 17. Schema JSON

The configured invoice schema was:

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
          "description": "GST percentage applicable to the line item"
        },
        "gst_amount": {
          "type": "NUMBER",
          "description": "GST amount for the line item"
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

This describes the desired output structure.

---

# 18. Extraction Instructions

```text
This document is a vendor invoice.

Extract the invoice information accurately and return the data according to the provided schema.

Identify the company or business issuing the invoice as vendor_name.

Extract the invoice number exactly as printed.

Extract the invoice issue date and convert it to YYYY-MM-DD format. Do not use the due date as the invoice date.

Extract the final invoice total as total_amount.

Extract the total tax amount as tax_amount.

For every line item, extract:
- particular: item or service description
- base_amount: amount before GST
- gst_percent: applicable GST percentage
- gst_amount: GST amount for that item
- total_amount: final line item amount including GST

Do not guess or invent values. If a value is not present or cannot be reliably determined, return null.

Preserve invoice numbers, names, and other identifiers exactly as printed.

For numerical values, return numbers without currency symbols or commas.
```

---

# 19. Backend Implementation

The main internal backend function is:

```python
def process_invoice_with_docai(file_url):
```

Its processing flow is:

```text
1. Read Document AI Configuration
2. Read schema/instructions
3. Read uploaded Frappe File
4. Determine MIME type
5. Load Google service-account credentials
6. Build Document AI processor endpoint
7. Send invoice bytes to Google Document AI
8. Receive processed document
9. Read root entities
10. Read document tables
11. Parse invoice fields
12. Parse line items
13. Return structured JSON
```

The backend combines Document AI extraction with custom table parsing because raw Document AI output did not always map directly to the ERPNext line-item structure.

---

# 20. Public API Wrapper

The internal function is:

```python
process_invoice_with_docai
```

The public whitelisted endpoint is:

```python
@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)
```

The Payment Entry Client Script calls:

```text
frappe_docai.api.process_invoice
```

If the wrapper is missing, the client call can fail with:

```text
AttributeError: module 'frappe_docai.api' has no attribute 'process_invoice'
```

After adding/changing it:

```bash
bench --site YOUR_SITE_NAME clear-cache
bench --site YOUR_SITE_NAME clear-website-cache
bench restart
```

---

# 21. Why REST Was Used

During development, the Python SDK's `DocumentSchema` did not expose the required `document_prompt` capability through the expected interface.

Therefore, the relevant processing request was implemented using the Document AI REST API with an authenticated Google session.

Do not assume every Document AI REST capability is exposed by the same Python SDK object.

---

# 22. Custom Table Parsing

Document AI can return table information such as:

```text
Description
Unit Price
Net Amount
Tax Rate
Tax Amount
Total Amount
```

A source table can look like:

```text
Apple iPhone 13 Pro (128GB) - Sierra Blue
75,000.0
18%
16,750.00
₹81,749.00
```

and:

```text
Shipping Charges
84.75
18%
15.25
100.00
```

The custom parser maps rows into:

```json
{
  "particular": "...",
  "base_amount": 0,
  "gst_percent": 0,
  "gst_amount": 0,
  "total_amount": 0
}
```

with actual extracted values.

The parser does not invent missing values.

---

# 23. Confirmed Test Result

A development test invoice produced:

```json
{
  "invoice_number": "DEL5-194299",
  "tax_amount": 6765.25,
  "vendor_name": "Rocket Kommerce LLP.",
  "total_amount": 81840,
  "line_items": [
    {
      "particular": "Apple iPhone 13 Pro (128GB) - Sierra Blue | B08L5W16HX (MBA_iPhone13PRO_128GB_GRN_2122)",
      "gst_percent": 18,
      "gst_amount": 16750,
      "total_amount": 81749,
      "base_amount": 75000
    },
    {
      "particular": "Shipping Charges",
      "gst_percent": 18,
      "gst_amount": 15.25,
      "total_amount": 100,
      "base_amount": 84.75
    }
  ],
  "date": null
}
```

The date was `null` because it could not be reliably extracted.

The source data also had a mismatch between the root total and displayed line-item totals. The parser did not invent a correction.

---

# 24. Payment Entry Integration

The current integration adds:

```text
Upload & Extract Invoice
```

The flow is:

```text
New Payment Entry
        ↓
Upload & Extract Invoice
        ↓
Frappe FileUploader
        ↓
Save file URL
        ↓
frappe_docai.api.process_invoice
        ↓
Document AI extraction
        ↓
Populate Payment Entry
```

---

# 25. Payment Entry Custom Fields

The current Client Script expects:

```text
custom_invoice_file
custom_invoice_number
custom_invoice_date
custom_items
```

The `custom_items` child table expects:

```text
perticular
base_amount
gst
gst_amount
amount_after_tax
```

If another project uses different fieldnames, either create these fields or change the Client Script mappings.

---

# 26. Payment Entry Field Mapping

| Extracted value | Payment Entry field |
|---|---|
| `invoice_number` | `custom_invoice_number` |
| `date` | `custom_invoice_date` |
| `vendor_name` | Supplier lookup |
| `total_amount` | NEFT/RTGS selection |
| `line_items[].particular` | `custom_items.perticular` |
| `line_items[].base_amount` | `custom_items.base_amount` |
| `line_items[].gst_percent` | `custom_items.gst` |
| `line_items[].gst_amount` | `custom_items.gst_amount` |
| `line_items[].total_amount` | `custom_items.amount_after_tax` |

---

# 27. Supplier Matching

The Client Script searches the Supplier DocType using the extracted vendor name.

Flow:

```text
Document AI vendor_name
        ↓
Supplier.supplier_name
        ↓
Matching Supplier
        ↓
Payment Type = Pay
Party Type = Supplier
Party = matched Supplier
```

If no Supplier is found, the user is informed and can create/select one manually.

---

# 28. NEFT / RTGS Rule

The current project-specific rule is:

```text
Total < 200000
        ↓
NEFT

Total >= 200000
        ↓
RTGS
```

This is business logic specific to the current project and should be changed if another organization uses a different rule.

---

# 29. Invoice Attachment

The uploaded invoice URL is stored in:

```text
custom_invoice_file
```

After Payment Entry save, the Client Script locates the Frappe File record and updates its attachment target so the invoice remains attached to the saved Payment Entry.

---

# 30. Current ERPNext Issue Found During Testing

A separate Payment Entry error appeared:

```text
TypeError: get_exchange_rate() missing 1 required positional argument: 'from_currency'
```

The request contained:

```json
{
  "transaction_date": "2026-09-12",
  "to_currency": "INR"
}
```

This is an ERPNext Payment Entry currency/exchange-rate issue, not a Google Document AI extraction error.

To inspect actual Payment Entry currency fields:

```bash
cd ~/frappe-bench
bench --site YOUR_SITE_NAME console
```

Then:

```python
import frappe

meta = frappe.get_meta("Payment Entry")

[
    (df.fieldname, df.label, df.fieldtype)
    for df in meta.fields
    if "currency" in (df.fieldname or "").lower()
    or "exchange" in (df.fieldname or "").lower()
]
```

Do not blindly add random currency fields or hard-code a currency fix before checking the actual Payment Entry metadata.

---

# 31. Realtime / Socket Warnings

Messages such as:

```text
ERR_CONNECTION_REFUSED :9000
```

are a separate realtime/socket development issue.

They are not the cause of:

```text
get_exchange_rate() missing from_currency
```

Browser preload warnings involving:

```text
icons.svg
```

are also unrelated to Document AI extraction.

---

# 32. Payment Entry Client Script

The Client Script must call:

```javascript
frappe.call({
    method: "frappe_docai.api.process_invoice",
    args: {
        file_url: file_doc.file_url
    }
});
```

The backend must contain:

```python
@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)
```

The API name must be:

```text
frappe_docai.api.process_invoice
```

---

# 33. New-Environment Setup Model

The reusable model is:

```text
New Frappe Project
        ↓
Google Cloud Project
        ↓
Document AI API
        ↓
Service Account
        ↓
Service Account JSON
        ↓
Document AI Processor
        ↓
Processor Location
        ↓
Processor Version
        ↓
Frappe Document AI Configuration
```

The app code stays the same. The Google configuration changes per environment.

---

# 34. Complete Google-to-Frappe Sequence

```text
1. Create/select Google Cloud project
2. Copy Project ID
3. Enable Document AI API
4. Create service account
5. Copy service-account email
6. Grant required IAM roles
7. Create JSON key
8. Download JSON
9. Open Document AI
10. Create/select processor
11. Copy Processor ID
12. Copy processor Location
13. Open processor versions
14. Copy Processor Version
15. Open Frappe Document AI Configuration
16. Upload JSON as private attachment
17. Enter Project ID
18. Enter Location
19. Enter Processor ID
20. Enter Processor Version
21. Enter Schema JSON
22. Enter Extraction Instructions
23. Enable configuration
24. Save
25. Test
```

---

# 35. Installation and Testing Order

Do not immediately test everything together.

## Test 1 — Python dependency

```bash
bench pip show google-cloud-documentai
```

## Test 2 — App installation

```bash
bench --site YOUR_SITE_NAME list-apps
```

## Test 3 — Frappe configuration

Open:

```text
Document AI Configuration
```

Check every field.

## Test 4 — Google credentials

Verify:

```text
Service Account JSON
IAM access
Private file accessibility
```

## Test 5 — Processor

Verify:

```text
Project
Processor
Location
Version
```

## Test 6 — Backend API

Test:

```text
frappe_docai.api.process_invoice
```

with an uploaded invoice.

## Test 7 — Payment Entry

Open a new Payment Entry and click:

```text
Upload & Extract Invoice
```

## Test 8 — Verify output

Check:

```text
Invoice Number
Invoice Date
Supplier
Total
Tax
Line Items
GST
Attachment
```

---

# 36. Production Checklist

## Frappe

```text
[ ] Correct Frappe version
[ ] Correct ERPNext version
[ ] frappe_docai downloaded
[ ] frappe_docai installed
[ ] google-cloud-documentai installed
[ ] Site migrated
[ ] Cache cleared
[ ] Bench restarted
```

## Google Cloud

```text
[ ] Project selected/created
[ ] Project ID copied
[ ] Document AI API enabled
[ ] Service account created
[ ] Required IAM access configured
[ ] JSON key created
[ ] JSON stored securely
[ ] Processor created/selected
[ ] Processor ID copied
[ ] Processor location copied
[ ] Processor version copied
```

## Frappe Configuration

```text
[ ] Document AI Configuration exists
[ ] Enabled = 1
[ ] Project ID entered
[ ] Location entered
[ ] Processor ID entered
[ ] Processor Version entered
[ ] Credentials JSON uploaded privately
[ ] Schema JSON entered
[ ] Extraction Instructions entered
```

## Payment Entry

```text
[ ] custom_invoice_file exists
[ ] custom_invoice_number exists
[ ] custom_invoice_date exists
[ ] custom_items exists
[ ] Child field perticular exists
[ ] Child field base_amount exists
[ ] Child field gst exists
[ ] Child field gst_amount exists
[ ] Child field amount_after_tax exists
[ ] Client Script installed
```

## Functional Test

```text
[ ] Invoice upload works
[ ] Backend API works
[ ] Document AI returns response
[ ] Invoice number extracted
[ ] Vendor extracted
[ ] Date extracted when available
[ ] Total extracted
[ ] Tax extracted
[ ] Line items extracted
[ ] Supplier matched
[ ] NEFT/RTGS rule works
[ ] Invoice remains attached
[ ] Payment Entry saves successfully
```

---

# 37. Troubleshooting

## `process_invoice` not found

Error:

```text
AttributeError: module 'frappe_docai.api' has no attribute 'process_invoice'
```

Ensure:

```python
@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)
```

Then:

```bash
bench --site YOUR_SITE_NAME clear-cache
bench --site YOUR_SITE_NAME clear-website-cache
bench restart
```

## Document AI 400 schema error

During development, unsupported schema structures caused:

```text
400 No valid schema provided for processing.
```

A REST schema override containing unsupported `description` fields also caused a 400 response.

Do not assume arbitrary nested schema definitions are accepted by every processor/API version.

Keep processor-supported schema behavior and custom parser behavior aligned.

## Google authentication failure

Check:

```text
Project ID
Service-account JSON
Private Frappe file accessibility
Document AI API
IAM permissions
Processor ID
Location
Processor Version
```

## `get_exchange_rate()` missing `from_currency`

This is a separate ERPNext Payment Entry currency/exchange-rate issue.

Inspect:

```bash
cd ~/frappe-bench
bench --site YOUR_SITE_NAME console
```

Then:

```python
import frappe

meta = frappe.get_meta("Payment Entry")

[
    (df.fieldname, df.label, df.fieldtype)
    for df in meta.fields
    if "currency" in (df.fieldname or "").lower()
    or "exchange" in (df.fieldname or "").lower()
]
```

Do not treat this as a Document AI credential/processor problem.

---

# 38. Security

The service-account JSON is the most sensitive part of the setup.

Always:

```text
[✓] Keep JSON private
[✓] Keep it server-side
[✓] Use Frappe private file storage
[✓] Do not expose it in JavaScript
[✓] Do not commit it to Git
[✓] Do not put it in public attachments
```

The browser should only call:

```text
frappe_docai.api.process_invoice
```

The server handles:

```text
Google authentication
Document AI request
Document parsing
Invoice extraction
```

---

# 39. Reusable Deployment Model

```text
                    SAME APP CODE
                         |
              +----------+----------+
              |                     |
              v                     v
       Frappe Project A      Frappe Project B
              |                     |
              v                     v
       Google Cloud A        Google Cloud B
              |                     |
              v                     v
       Service Account A    Service Account B
              |                     |
              v                     v
          Processor A          Processor B
```

The application code remains reusable.

Only the site-specific configuration changes.

---

# 40. Future Improvement: Package Payment Entry Customization

The current implementation expects the Payment Entry custom fields and Client Script to exist in the target project.

For a truly plug-and-play app, these project customizations should eventually be packaged into the Frappe app using fixtures/customizations.

Then installation can provide:

```text
App
+
Document AI Configuration
+
Payment Entry custom fields
+
Child table
+
Payment Entry Client Script
```

without requiring manual setup.

Until that is packaged, follow the Payment Entry setup documented above.

---

# 41. Core Design Principle

> **Keep the application reusable and keep Google Cloud configuration site-specific.**

Install the app once.

Configure the target Google Cloud project and processor.

Upload the target service-account JSON privately.

Configure the schema and extraction instructions.

Connect Payment Entry to the public backend API.

Never put environment-specific credentials into the public repository.
