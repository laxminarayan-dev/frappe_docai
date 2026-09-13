### Frappe Document AI

Google Document AI integration for Frappe

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app frappe_docai
```

### Contributing

This app uses `pre-commit` for code formatt# Frappe Document AI --- Complete Implementation & Reinstallation Guide

This guide documents the reusable `frappe_docai` app built for
Frappe/ERPNext Payment Entry invoice extraction with Google Cloud
Document AI.

## Contents

1.  [Why we built this](#part-1--why-we-need-this)
2.  [How we built this](#part-2--how-we-built-this)
3.  [How to install and configure it in another
    project](#part-3--setting-up-the-app-in-another-project)

------------------------------------------------------------------------

# PART 1 --- WHY WE NEED THIS

## 1.1 The problem

The requirement was to upload a vendor invoice from a **Payment Entry**
and automatically extract useful invoice information instead of entering
it manually.

The target data is:

-   Vendor/Supplier name
-   Invoice number
-   Invoice issue date
-   Total invoice amount
-   Total tax amount
-   Line items
-   Item/service description
-   Base amount before GST
-   GST percentage
-   GST amount
-   Final line-item amount including GST

Without this app, the user has to open the invoice, read it, find the
supplier, enter invoice details, and manually create every line item.

## 1.2 Why Google Cloud Document AI

Invoices are structured documents rather than simple text. Important
information can be spread across tables, columns and different layouts.

Google Cloud Document AI gives us document-processing results that
include document text, entities and tables. We then use our own parser
to convert the response into the exact JSON structure required by
ERPNext.

## 1.3 Why a separate Frappe app

The functionality was put into a reusable app:

``` text
frappe_docai
```

instead of modifying ERPNext core.

Benefits:

-   Reusable across Frappe/ERPNext projects
-   Separate from ERPNext core
-   Easier maintenance and deployment
-   Google configuration stored centrally
-   Backend API can be reused
-   Payment Entry integration remains separate from the core app

### Architecture

``` text
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

------------------------------------------------------------------------

# PART 2 --- HOW WE BUILT THIS

## 2.1 Development environment

The implementation was developed with:

``` text
Frappe        16.31.0
ERPNext       16.32.3
frappe_docai  0.0.1
Python        python3
google-cloud-documentai 3.15.0
```

Bench:

``` text
~/frappe-bench
```

Site:

``` text
vendor2.site
```

App path:

``` text
/home/lucky/frappe-bench/apps/frappe_docai
```

Module:

``` text
Frappe Document AI
```

## 2.2 Create the app

From the bench:

``` bash
cd ~/frappe-bench
bench new-app frappe_docai
```

Install it:

``` bash
bench --site vendor2.site install-app frappe_docai
```

Verify:

``` bash
bench --site vendor2.site list-apps
```

The app should appear as:

``` text
frappe_docai
```

## 2.3 Enable developer mode

Developer mode is required while developing custom DocTypes, scripts and
application files.

After configuration/code changes, clear cache:

``` bash
bench --site vendor2.site clear-cache
bench --site vendor2.site clear-website-cache
```

If Supervisor is being used:

``` bash
bench restart
```

## 2.4 Install the Google Document AI library

The app depends on:

``` text
google-cloud-documentai
```

Install it in the bench environment:

``` bash
cd ~/frappe-bench
bench pip install google-cloud-documentai
```

Verify:

``` bash
bench pip show google-cloud-documentai
```

The version used during development was:

``` text
3.15.0
```

The dependency was also declared in the app's Python project
configuration:

``` toml
dependencies = [
    "google-cloud-documentai"
]
```

## 2.5 Create the configuration Single DocType

Create:

``` text
Document AI Configuration
```

It is a **Single DocType** so one configuration can control the
integration for the site.

Fields:

  Label                     Field Type   Fieldname                   Requirement
  ------------------------- ------------ --------------------------- -------------
  Enabled                   Check        `enabled`                   Default 1
  Google Cloud Project ID   Data         `project_id`                Mandatory
  Google Cloud Location     Data         `location`                  Mandatory
  Processor ID              Data         `processor_id`              Mandatory
  Google Credentials JSON   Attach       `credentials_json`          Mandatory
  Connection Status         Small Text   `connection_status`         Read Only
  Last Connection Test      Datetime     `last_connection_test`      Read Only
  Schema JSON               Code         `schema_json`               
  Extraction Instructions   Text         `extraction_instructions`   
  Processor Version         Data         `processor_version`         Mandatory

The purpose is to keep Google Cloud configuration outside the source
code.

The backend reads it using:

``` python
frappe.get_single("Document AI Configuration")
```

Therefore the same app can be installed in multiple projects and each
site can use its own Google Cloud project, credentials and processor.

------------------------------------------------------------------------

# 2.6 Google Cloud configuration used during development

The values used for this implementation were:

``` text
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

The credentials JSON was stored in Frappe as a private attachment:

``` text
/private/files/gen-lang-client-0690478224-cc9324af9053.json
```

**Do not copy these credentials into a public repository.** For another
project, create/use the credentials belonging to that environment.

------------------------------------------------------------------------

# 2.7 Create/select the Google Cloud project

In Google Cloud Console:

1.  Select an existing project or create a new one.
2.  Copy the actual **Project ID**.
3.  Keep it for the Frappe configuration.

The Project ID is different from the display name.

For this implementation:

``` text
gen-lang-client-0690478224
```

------------------------------------------------------------------------

# 2.8 Enable Document AI API

In the selected Google Cloud project:

``` text
Google Cloud Console
    >
APIs & Services
    >
Library
```

Search for:

``` text
Document AI API
```

Open it and click:

``` text
Enable
```

The API must be enabled in the project that owns the
processor/service-account setup.

------------------------------------------------------------------------

# 2.9 Create the Google service account

Go to:

``` text
IAM & Admin
    >
Service Accounts
```

Create a service account.

The development service account was:

``` text
msc-vendor-payment@gen-lang-client-0690478224.iam.gserviceaccount.com
```

The service account is used by the Frappe server for Google
authentication.

------------------------------------------------------------------------

# 2.10 Give the service account permissions

The service account used in this implementation had:

``` text
Document AI API User (Beta)
Viewer (Beta)
```

Google Cloud roles can change over time, so on a new project verify the
currently available Document AI permissions and grant the service
account enough access to process documents with the selected processor.

------------------------------------------------------------------------

# 2.11 Create/download the service-account JSON

In:

``` text
IAM & Admin
    >
Service Accounts
    >
<your service account>
    >
Keys
```

Create:

``` text
Add Key
    >
Create new key
    >
JSON
```

Download the JSON file.

Example development filename:

``` text
gen-lang-client-0690478224-cc9324af9053.json
```

### Security rule

The JSON contains credentials.

Never:

-   Put it in JavaScript
-   Put it in a public Git repository
-   Commit it to Git
-   Expose it to the browser
-   Put it in a public file attachment

Store it privately on the server/Frappe side.

------------------------------------------------------------------------

# 2.12 Create/select the Document AI processor

Open Google Cloud Document AI.

Create or select the required processor.

This implementation used a:

``` text
Custom Extractor
```

Processor ID:

``` text
870994bf06747cb2
```

Important:

``` text
Project ID != Processor ID
```

Both values are required.

------------------------------------------------------------------------

# 2.13 Find processor location

Open the processor details and identify its location.

Development configuration:

``` text
asia-south1
```

The application uses this location while constructing the Document AI
endpoint.

For a new project, do not blindly reuse `asia-south1`; copy the actual
location shown for that processor.

------------------------------------------------------------------------

# 2.14 Find processor version

The processor version used during this implementation was:

``` text
pretrained-foundation-model-v1.5-2025-08-06
```

For another project, retrieve the actual version available for that
processor.

The processor version is a separate value from:

-   Project ID
-   Processor ID
-   Location

------------------------------------------------------------------------

# 2.15 Collect the five Google values

For every new deployment, collect:

``` text
1. Google Cloud Project ID
2. Google Cloud Location
3. Document AI Processor ID
4. Document AI Processor Version
5. Service Account JSON
```

Also keep the service-account email for troubleshooting.

A private setup sheet can look like:

``` text
PROJECT_ID=________________________

SERVICE_ACCOUNT_EMAIL=____________

PROCESSOR_ID=_____________________

LOCATION=_________________________

PROCESSOR_VERSION=________________

SERVICE_ACCOUNT_JSON=<private file>
```

------------------------------------------------------------------------

# 2.16 Configure Frappe

Open:

``` text
Document AI Configuration
```

Set:

``` text
Enabled:
1

Google Cloud Project ID:
gen-lang-client-0690478224

Google Cloud Location:
asia-south1

Processor ID:
870994bf06747cb2

Processor Version:
pretrained-foundation-model-v1.5-2025-08-06

Google Credentials JSON:
/private/files/gen-lang-client-0690478224-cc9324af9053.json
```

For a new project, replace every Google-specific value with the new
environment's values.

------------------------------------------------------------------------

# 2.17 Schema JSON

The configured schema was:

``` json
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

This describes the output structure we want.

------------------------------------------------------------------------

# 2.18 Extraction instructions

The configured instructions were:

``` text
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

------------------------------------------------------------------------

# 2.19 Backend implementation

The main internal backend function is:

``` python
def process_invoice_with_docai(file_url):
```

Its processing flow is:

``` text
1. Read Document AI Configuration
2. Read schema/instructions
3. Read the uploaded Frappe File
4. Determine MIME type
5. Load Google service-account credentials
6. Build the Document AI processor endpoint
7. Send invoice bytes to Google Document AI
8. Receive the processed document
9. Read root entities
10. Read document tables
11. Parse invoice fields
12. Parse line items
13. Return structured JSON
```

The backend combines Document AI extraction with custom table parsing
because the raw Document AI output did not always map directly to the
ERPNext line-item structure.

------------------------------------------------------------------------

# 2.20 Why REST was used for part of the Document AI integration

The Python SDK's `DocumentSchema` did not expose the required
`document_prompt` capability in the expected interface.

Therefore the relevant processing request was implemented using the
Document AI REST API with an authenticated Google session.

This is important when maintaining the app: do not assume that every
current Document AI REST capability is exposed by the same Python SDK
object.

------------------------------------------------------------------------

# 2.21 Why custom table parsing was required

The invoice response contained table information such as:

``` text
Description
Unit Price
Net Amount
Tax Rate
Tax Amount
Total Amount
```

A sample source table contained:

``` text
Apple iPhone 13 Pro (128GB) - Sierra Blue
75,000.0
18%
16,750.00
₹81,749.00
```

and:

``` text
Shipping Charges
84.75
18%
15.25
100.00
```

The parser therefore identifies table rows and maps them into:

``` json
{
  "particular": "...",
  "base_amount": 0,
  "gst_percent": 0,
  "gst_amount": 0,
  "total_amount": 0
}
```

with the actual extracted values.

------------------------------------------------------------------------

# 2.22 Confirmed example result

The final parser output for the test invoice was:

``` python
{
    "invoice_number": "DEL5-194299",
    "tax_amount": 6765.25,
    "vendor_name": "Rocket Kommerce LLP.",
    "total_amount": 81840,
    "line_items": [
        {
            "particular": "Apple iPhone 13 Pro (128GB) - Sierra Blue |\nB08L5W16HX (\nMBA_iPhone13PRO_128GB_GRN_2122)",
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
    "date": None
}
```

The date remained `None` because it could not be reliably extracted.

The root total and the sum of the displayed line-item totals also
differed in the source data. The parser did not invent a correction.

------------------------------------------------------------------------

# 2.23 Public API wrapper

The internal processing function is:

``` python
process_invoice_with_docai
```

The Payment Entry Client Script calls:

``` text
frappe_docai.api.process_invoice
```

Therefore the public wrapper is:

``` python
# ============================================================
# PUBLIC API ENDPOINT
# ============================================================

@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)
```

This wrapper is important.

If it is missing, the client call:

``` text
frappe_docai.api.process_invoice
```

will fail with an error similar to:

``` text
AttributeError: module 'frappe_docai.api' has no attribute 'process_invoice'
```

After adding/changing it:

``` bash
bench --site vendor2.site clear-cache
bench --site vendor2.site clear-website-cache
```

and restart when required.

------------------------------------------------------------------------

# 2.24 Payment Entry Client Script

The Client Script adds a button:

``` text
Upload & Extract Invoice
```

The important API call is:

``` javascript
const response = await frappe.call({
    method: 'frappe_docai.api.process_invoice',
    args: {
        file_url: file_doc.file_url
    }
});
```

The flow is:

``` text
New Payment Entry
        ↓
Upload & Extract Invoice
        ↓
Frappe FileUploader
        ↓
Save file URL in custom_invoice_file
        ↓
Call frappe_docai.api.process_invoice
        ↓
Document AI extraction
        ↓
Populate Payment Entry
```

------------------------------------------------------------------------

# 2.25 Payment Entry field mapping

The current integration expects:

  Extracted value               Payment Entry field
  ----------------------------- ---------------------------------
  `invoice_number`              `custom_invoice_number`
  `date`                        `custom_invoice_date`
  `vendor_name`                 Supplier lookup
  `total_amount`                NEFT/RTGS selection
  `line_items[].particular`     `custom_items.perticular`
  `line_items[].base_amount`    `custom_items.base_amount`
  `line_items[].gst_percent`    `custom_items.gst`
  `line_items[].gst_amount`     `custom_items.gst_amount`
  `line_items[].total_amount`   `custom_items.amount_after_tax`

------------------------------------------------------------------------

# 2.26 Supplier matching

The Client Script searches:

``` javascript
frappe.db.get_value(
    'Supplier',
    {
        supplier_name: result.vendor_name
    },
    'name'
);
```

If found, it sets:

``` text
payment_type = Pay
party_type   = Supplier
party        = matched Supplier
```

If no matching Supplier exists, the script displays a message so the
user can create/select the supplier manually.

------------------------------------------------------------------------

# 2.27 NEFT/RTGS business rule

The current script contains:

``` javascript
const paymentMode =
    Number(result.total_amount) < 200000
        ? 'NEFT'
        : 'RTGS';
```

Therefore:

``` text
Total < 200000  → NEFT
Total >= 200000 → RTGS
```

This is project-specific business logic and should be changed if another
organization uses a different rule.

------------------------------------------------------------------------

# 2.28 Line-item creation

Before adding extracted items:

``` javascript
frm.clear_table('custom_items');
```

Each result becomes a child row:

``` javascript
const row = frm.add_child('custom_items');

row.perticular = item.particular || '';

row.base_amount =
    Number(item.base_amount || 0);

row.gst =
    Number(item.gst_percent || 0);

row.gst_amount =
    Number(item.gst_amount || 0);

row.amount_after_tax =
    Number(item.total_amount || 0);
```

Then:

``` javascript
frm.refresh_field('custom_items');
```

------------------------------------------------------------------------

# 2.29 Invoice attachment

The uploaded invoice URL is stored in:

``` text
custom_invoice_file
```

After Payment Entry save, the script locates the Frappe File record and
updates its attachment target so the invoice is attached to the saved
Payment Entry.

------------------------------------------------------------------------

# 2.30 Current ERPNext issue discovered during testing

A separate Payment Entry error appeared:

``` text
TypeError: get_exchange_rate() missing 1 required positional argument: 'from_currency'
```

The request contained:

``` json
{
    "transaction_date": "2026-09-12",
    "to_currency": "INR"
}
```

This is an ERPNext Payment Entry currency/exchange-rate issue, not a
Google Document AI extraction error.

The custom API had already been reached successfully at that stage.

To inspect the actual Payment Entry currency fields:

``` bash
cd ~/frappe-bench
bench --site vendor2.site console
```

Then:

``` python
import frappe

meta = frappe.get_meta("Payment Entry")

[
    (df.fieldname, df.label, df.fieldtype)
    for df in meta.fields
    if "currency" in (df.fieldname or "").lower()
    or "exchange" in (df.fieldname or "").lower()
]
```

Do not blindly add random currency fields or hard-code a currency fix
before checking the actual Payment Entry metadata.

------------------------------------------------------------------------

# 2.31 Separate realtime/socket warnings

Messages such as:

``` text
ERR_CONNECTION_REFUSED :9000
```

are a separate realtime/socket development issue.

They are not the cause of:

``` text
get_exchange_rate() missing from_currency
```

Browser preload warnings involving:

``` text
icons.svg
```

are also unrelated to the Document AI extraction implementation.

------------------------------------------------------------------------

# PART 3 --- SETTING UP THE APP IN ANOTHER PROJECT

This section describes the complete reusable deployment process.

# 3.1 What the new environment needs

The target environment needs:

``` text
Frappe 16.x
ERPNext 16.x
Bench
Python
A working Frappe site
frappe_docai source
google-cloud-documentai
Google Cloud Document AI configuration
Payment Entry custom fields
Payment Entry Client Script
```

Matching the Frappe/ERPNext major version is preferred.

------------------------------------------------------------------------

# 3.2 Get/download the app

If the app is in Git:

``` bash
cd ~/frappe-bench/apps

git clone <YOUR_FRAPPE_DOCAI_REPOSITORY> frappe_docai
```

Then:

``` bash
cd ~/frappe-bench
bench --site <SITE_NAME> install-app frappe_docai
```

If the app is supplied as a ZIP, extract it into:

``` text
~/frappe-bench/apps/frappe_docai
```

Then install:

``` bash
bench --site <SITE_NAME> install-app frappe_docai
```

------------------------------------------------------------------------

# 3.3 Install dependencies

``` bash
cd ~/frappe-bench
bench pip install google-cloud-documentai
```

Verify:

``` bash
bench pip show google-cloud-documentai
```

------------------------------------------------------------------------

# 3.4 Verify app installation

``` bash
bench --site <SITE_NAME> list-apps
```

Expected:

``` text
frappe
erpnext
frappe_docai
```

------------------------------------------------------------------------

# 3.5 Migrate and restart

``` bash
bench --site <SITE_NAME> migrate
bench --site <SITE_NAME> clear-cache
bench --site <SITE_NAME> clear-website-cache
bench restart
```

------------------------------------------------------------------------

# 3.6 Create the Google Cloud environment for the new project

For a clean deployment:

``` text
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

------------------------------------------------------------------------

# 3.7 Step-by-step Google Cloud setup for a new project

## Step 1 --- Create/select project

Google Cloud Console → select/create project.

Copy:

``` text
Project ID
```

## Step 2 --- Enable API

APIs & Services → Library → search:

``` text
Document AI API
```

Click:

``` text
Enable
```

## Step 3 --- Create service account

IAM & Admin → Service Accounts → Create Service Account.

Copy:

``` text
Service Account Email
```

## Step 4 --- Grant permissions

Grant the required Document AI access.

The development setup used:

``` text
Document AI API User (Beta)
Viewer (Beta)
```

## Step 5 --- Create JSON key

Service Account → Keys → Add Key → Create new key → JSON.

Download the JSON.

## Step 6 --- Create/select Document AI processor

Open Document AI and create/select the required processor.

For this application the processor type used was:

``` text
Custom Extractor
```

## Step 7 --- Copy Processor ID

From processor details copy:

``` text
Processor ID
```

## Step 8 --- Copy processor location

From processor details copy:

``` text
Location
```

## Step 9 --- Copy processor version

From the processor's versions/details copy the actual version name.

## Step 10 --- Configure Frappe

Enter:

``` text
Project ID
Location
Processor ID
Processor Version
Service Account JSON
```

into:

``` text
Document AI Configuration
```

------------------------------------------------------------------------

# 3.8 How to know exactly which Google values go into which Frappe field

  Google Cloud information   Frappe field
  -------------------------- ---------------------
  Google Cloud Project ID    `project_id`
  Processor location         `location`
  Processor ID               `processor_id`
  Service-account JSON       `credentials_json`
  Processor version          `processor_version`

The remaining fields are application behavior:

  -----------------------------------------------------------------------
  Frappe field                        Purpose
  ----------------------------------- -----------------------------------
  `enabled`                           Enable/disable integration

  `schema_json`                       Desired extraction structure

  `extraction_instructions`           Instructions given to the
                                      extraction logic

  `connection_status`                 Test/status information

  `last_connection_test`              Last connection test time
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 3.9 Configure the Payment Entry custom fields

The current Client Script expects these Payment Entry fields:

``` text
custom_invoice_file
custom_invoice_number
custom_invoice_date
custom_items
```

The child table is expected to contain:

``` text
perticular
base_amount
gst
gst_amount
amount_after_tax
```

If another ERPNext project uses different fieldnames, either create
these fields or change the Client Script mappings.

------------------------------------------------------------------------

# 3.10 Install the Payment Entry Client Script

Create a Client Script for:

``` text
DocType: Payment Entry
```

Insert the application Client Script used by the current project.

The script must call:

``` javascript
frappe_docai.api.process_invoice
```

not a nonexistent method name.

The backend must contain:

``` python
@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)
```

------------------------------------------------------------------------

# 3.11 Configure Schema and instructions

If the new project should extract the same invoice data, copy:

``` text
Schema JSON
```

and:

``` text
Extraction Instructions
```

from Part 2.

If invoice formats/business requirements differ, these can be changed
without changing the basic app architecture.

------------------------------------------------------------------------

# 3.12 Test in the correct order

Do not immediately test everything together.

Use this order:

### Test 1 --- Python dependency

``` bash
bench pip show google-cloud-documentai
```

### Test 2 --- App installation

``` bash
bench --site <SITE_NAME> list-apps
```

### Test 3 --- Frappe configuration

Open:

``` text
Document AI Configuration
```

Check every field.

### Test 4 --- Google credentials

Verify the service-account JSON and IAM access.

### Test 5 --- Document AI processor

Verify:

``` text
Project
Processor
Location
Version
```

### Test 6 --- Backend API

Call the whitelisted:

``` text
frappe_docai.api.process_invoice
```

with an uploaded invoice.

### Test 7 --- Payment Entry

Open a new Payment Entry and click:

``` text
Upload & Extract Invoice
```

### Test 8 --- Verify output

Check:

``` text
Invoice Number
Invoice Date
Supplier
Total
Tax
Line Items
GST
Attachment
```

------------------------------------------------------------------------

# 3.13 Complete new-server command sequence

Replace `<SITE_NAME>` and `<YOUR_REPOSITORY>`.

``` bash
cd ~/frappe-bench

cd apps
git clone <YOUR_FRAPPE_DOCAI_REPOSITORY> frappe_docai

cd ..

bench pip install google-cloud-documentai

bench --site <SITE_NAME> install-app frappe_docai

bench --site <SITE_NAME> migrate

bench --site <SITE_NAME> clear-cache

bench --site <SITE_NAME> clear-website-cache

bench restart
```

Then configure Google Cloud and Frappe.

------------------------------------------------------------------------

# 3.14 Complete Google-to-Frappe setup sequence

``` text
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
21. Paste Schema JSON
22. Paste Extraction Instructions
23. Enable configuration
24. Save
25. Test
```

------------------------------------------------------------------------

# 3.15 Production checklist

## Frappe

``` text
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

``` text
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

## Frappe configuration

``` text
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

``` text
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

## Functional test

``` text
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

------------------------------------------------------------------------

# 3.16 Troubleshooting reference

## `process_invoice` not found

Error:

``` text
AttributeError: module 'frappe_docai.api' has no attribute 'process_invoice'
```

Ensure `api.py` contains:

``` python
@frappe.whitelist()
def process_invoice(file_url):
    return process_invoice_with_docai(file_url)
```

Then:

``` bash
bench --site <SITE_NAME> clear-cache
bench --site <SITE_NAME> clear-website-cache
```

Restart if necessary.

## Document AI 400 schema error

During development, unsupported schema structures caused errors such as:

``` text
400 No valid schema provided for processing.
```

A schema containing unsupported `description` fields in a particular
REST schema override also caused a 400 response.

Therefore the implementation should not assume that arbitrary nested
schema definitions are accepted by every processor/API version. Keep the
processor's supported schema behavior and the custom parser aligned.

## Google authentication failure

Check all of:

``` text
Project ID
Service-account JSON
File URL
Private file accessibility
Document AI API
IAM permissions
Processor ID
Location
Processor Version
```

## `get_exchange_rate()` missing `from_currency`

This is a separate ERPNext Payment Entry currency/exchange-rate issue.

Inspect:

``` bash
cd ~/frappe-bench
bench --site <SITE_NAME> console
```

Then:

``` python
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

------------------------------------------------------------------------

# 3.17 Security rules

The service-account JSON is the most sensitive part of the setup.

Always:

``` text
Keep JSON private
Keep it server-side
Use Frappe private file storage
Do not expose it in JavaScript
Do not commit it to Git
Do not put it in public attachments
```

The browser should only call:

``` text
frappe_docai.api.process_invoice
```

The server handles:

``` text
Google authentication
Document AI request
Document parsing
Invoice extraction
```

------------------------------------------------------------------------

# 3.18 Reusable deployment model

The intended model is:

``` text
                    SAME APP CODE
                         |
          +--------------+--------------+
          |                             |
          v                             v
   Frappe Project A              Frappe Project B
          |                             |
          v                             v
 Google Cloud A                  Google Cloud B
          |                             |
          v                             v
 Service Account A              Service Account B
          |                             |
          v                             v
 Processor A                    Processor B
```

The app code remains reusable.

Only the site-specific configuration changes.

------------------------------------------------------------------------

# 3.19 The most important information to collect before installing elsewhere

Before starting a new deployment, make sure you have:

``` text
FRAPPE:
    Site name
    Frappe version
    ERPNext version
    App source/repository

GOOGLE CLOUD:
    Project ID
    Service Account Email
    Service Account JSON
    Document AI Processor ID
    Processor Location
    Processor Version

FRAPPE CONFIGURATION:
    Schema JSON
    Extraction Instructions

PAYMENT ENTRY:
    Custom fieldnames
    Child-table fieldnames
    Client Script
```

If these are ready, the installation becomes straightforward.

------------------------------------------------------------------------

# FINAL QUICK REFERENCE

## Install app

``` bash
cd ~/frappe-bench
cd apps
git clone <YOUR_FRAPPE_DOCAI_REPOSITORY> frappe_docai
cd ..
bench pip install google-cloud-documentai
bench --site <SITE_NAME> install-app frappe_docai
bench --site <SITE_NAME> migrate
bench --site <SITE_NAME> clear-cache
bench --site <SITE_NAME> clear-website-cache
bench restart
```

## Google Cloud

``` text
Project
  ↓
Enable Document AI API
  ↓
Service Account
  ↓
IAM permissions
  ↓
JSON key
  ↓
Document AI Processor
  ↓
Processor ID
  ↓
Location
  ↓
Processor Version
```

## Frappe

``` text
Document AI Configuration
  ↓
Project ID
  ↓
Location
  ↓
Processor ID
  ↓
Processor Version
  ↓
Private Credentials JSON
  ↓
Schema
  ↓
Extraction Instructions
```

## Payment Entry

``` text
Upload Invoice
  ↓
frappe_docai.api.process_invoice
  ↓
Google Document AI
  ↓
Custom Parser
  ↓
Invoice JSON
  ↓
Payment Entry fields
  ↓
Line items
  ↓
Attachment
```

## Five Google values to remember

``` text
1. Project ID
2. Location
3. Processor ID
4. Processor Version
5. Service Account JSON
```

These are the core Google-specific values that must be collected for
every new deployment.

------------------------------------------------------------------------

# End

The core design principle is:

> **Keep the application reusable and keep Google Cloud configuration
> site-specific.**

Install the app once, configure the Google Cloud project/processor for
the target environment, upload the private service-account JSON,
configure the extraction schema/instructions, and connect the Payment
Entry Client Script to the whitelisted backend API.
ing and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/frappe_docai
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
