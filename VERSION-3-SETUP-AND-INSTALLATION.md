# frappe_docai V3 — GitHub Installation & Google Cloud Setup Guide

This is the deployment guide for installing the reusable `frappe_docai` application from GitHub and configuring it for the **current V3 runtime**.

The current V3 runtime is:

```text
Frappe Client Script
        ↓
frappe_docai.api.process
        ↓
Gemini 3.5 Flash-Lite on Google Cloud Agent Platform / Vertex AI
        ↓
Financial Validator
        ↓
Corrected JSON
        ↓
ERPNext
```

The current runtime sends the uploaded PDF directly to Gemini. Google Vision is **not required for the normal V3 runtime path**. Legacy Vision / Document AI components can remain installed for older code paths or tests, but they are optional for the current V3 direct-PDF pipeline.

---

# 1. What You Need Before Starting

## Frappe side

You need:

```text
Frappe 16.x
ERPNext 16.x
A working Bench
A working Frappe site
Git
Internet access from the Frappe server
```

The development environment for V3 used:

```text
Frappe        16.31.0
ERPNext       16.32.3
frappe_docai  0.0.1
Bench         ~/frappe-bench
Site          vendor2.site
App path      ~/frappe-bench/apps/frappe_docai
```

Matching the same major Frappe / ERPNext version is recommended.

---

# 2. What You Need on Google Cloud

For the **current V3 direct PDF → Gemini runtime**, the required Google pieces are:

```text
1. Google Cloud project
2. Billing enabled
3. Vertex AI / Agent Platform API enabled
4. Service account
5. Vertex AI User role
6. Service-account JSON key
7. Gemini 3.5 Flash-Lite available in Global
```

Google's current documentation lists `gemini-3.5-flash-lite` as GA and available in the Global location. The current model ID is:

```text
gemini-3.5-flash-lite
```

and its model endpoint location includes:

```text
global
```

Google also documents `roles/aiplatform.user` as the Vertex AI User role for service accounts interacting with Vertex AI.

Official references:

- Google Gemini 3.5 Flash-Lite:
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite
- Agent Platform locations:
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations
- Vertex AI access control:
  https://cloud.google.com/vertex-ai/docs/general/access-control
- Service-account creation:
  https://docs.cloud.google.com/iam/docs/service-accounts-create
- Service-account keys:
  https://docs.cloud.google.com/iam/docs/keys-create-delete

---

# 3. Important: Current V3 Does NOT Require These for Normal Runtime

The current V3 direct-document runtime does not need a Document AI processor or a Cloud Storage bucket just to perform the normal PDF extraction call.

You do **not** need to create:

```text
Document AI processor
GCS input bucket
GCS output bucket
Vision OCR processor
```

for the normal V3 path.

Those are relevant only if you intentionally use legacy OCR / Vision / Document AI functionality.

---

# 4. Google Cloud — Create or Select a Project

Open:

```text
Google Cloud Console
```

Select an existing project or create a new project.

Record the actual:

```text
Project ID
```

Do not confuse:

```text
Project name
```

with:

```text
Project ID
```

Example:

```text
Project ID:
my-frappe-docai-project
```

---

# 5. Google Cloud CLI — Set the Project

From Google Cloud Shell:

```bash
gcloud config set project <PROJECT_ID>
```

Example:

```bash
gcloud config set project my-frappe-docai-project
```

Verify:

```bash
gcloud config get-value project
```

---

# 6. Enable Billing

The project must have billing enabled for paid Google Cloud model usage.

Check:

```bash
gcloud billing projects describe <PROJECT_ID>
```

Example:

```bash
gcloud billing projects describe my-frappe-docai-project
```

You should see a billing account associated with the project.

If the project is not linked to billing, link it with:

```bash
gcloud billing projects link <PROJECT_ID> \
  --billing-account=<BILLING_ACCOUNT_ID>
```

Replace:

```text
<PROJECT_ID>
<BILLING_ACCOUNT_ID>
```

with the real values.

---

# 7. Enable the Vertex AI API

For the current V3 model call, enable:

```text
aiplatform.googleapis.com
```

Command:

```bash
gcloud services enable aiplatform.googleapis.com \
  --project=<PROJECT_ID>
```

Verify:

```bash
gcloud services list \
  --enabled \
  --project=<PROJECT_ID> \
  --filter="config.name=aiplatform.googleapis.com"
```

Expected service:

```text
aiplatform.googleapis.com
```

Google's current documentation explicitly uses `aiplatform.googleapis.com` for Vertex AI / Agent Platform access.

---

# 8. Enable Supporting APIs

IAM and Service Usage are often already available, but they can be enabled explicitly:

```bash
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  serviceusage.googleapis.com \
  --project=<PROJECT_ID>
```

These are useful for service-account administration and API management.

---

# 9. Create the Service Account

Create a dedicated service account for the app.

Recommended name:

```text
frappe-docai
```

Command:

```bash
gcloud iam service-accounts create frappe-docai \
  --project=<PROJECT_ID> \
  --display-name="Frappe Document AI"
```

Example:

```bash
gcloud iam service-accounts create frappe-docai \
  --project=my-frappe-docai-project \
  --display-name="Frappe Document AI"
```

The resulting email will be:

```text
frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com
```

Verify:

```bash
gcloud iam service-accounts list \
  --project=<PROJECT_ID>
```

---

# 10. Grant Vertex AI User

Grant the service account:

```text
Vertex AI User
```

IAM role:

```text
roles/aiplatform.user
```

Command:

```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

Example:

```bash
gcloud projects add-iam-policy-binding my-frappe-docai-project \
  --member="serviceAccount:frappe-docai@my-frappe-docai-project.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

Verify:

```bash
gcloud projects get-iam-policy <PROJECT_ID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

You should see:

```text
roles/aiplatform.user
```

Google documents `roles/aiplatform.user` as the role that lets a service account interact with Vertex AI.

---

# 11. Create the Service-Account JSON Key

The current app stores the service-account JSON as a private Frappe file attachment.

Create the key:

```bash
gcloud iam service-accounts keys create ~/frappe-docai-service-account.json \
  --iam-account=frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com
```

Example:

```bash
gcloud iam service-accounts keys create ~/frappe-docai-service-account.json \
  --iam-account=frappe-docai@my-frappe-docai-project.iam.gserviceaccount.com
```

Verify that it exists:

```bash
ls -l ~/frappe-docai-service-account.json
```

Restrict permissions:

```bash
chmod 600 ~/frappe-docai-service-account.json
```

## Security

This JSON is a credential.

Never:

```text
commit it to Git
put it in JavaScript
upload it to a public folder
send it to the browser
put it in a public GitHub repository
```

Google's current IAM documentation recommends securely protecting service-account keys and notes that keys cannot be downloaded again after creation.

---

# 12. Current Model Configuration

The V3 configuration should use:

```text
Provider:
Google Agent Platform

Model:
gemini-3.5-flash-lite

Location:
global

Endpoint:
blank
```

Do not invent a regional endpoint when using the current Global model configuration.

The current model is documented as available in the Global location.

---

# 13. Install the App From GitHub

The exact GitHub repository URL is deployment-specific and is intentionally left as a placeholder here because the current source documentation does not contain the public repository URL.

Replace:

```text
<YOUR_GITHUB_REPOSITORY>
```

with the real repository URL.

From the Bench:

```bash
cd ~/frappe-bench
```

## Option A — Bench get-app

Recommended:

```bash
bench get-app <YOUR_GITHUB_REPOSITORY>
```

If the repository contains a specific V3-compatible branch:

```bash
bench get-app --branch <BRANCH_NAME> <YOUR_GITHUB_REPOSITORY>
```

Example:

```bash
bench get-app --branch version-16 https://github.com/<ORG>/<REPO>.git
```

## Option B — Direct Git clone

```bash
cd ~/frappe-bench/apps

git clone <YOUR_GITHUB_REPOSITORY> frappe_docai
```

Then:

```bash
cd ~/frappe-bench
```

Frappe's official Bench documentation supports both fetching an app from a Git repository and installing an app that already exists in the bench.

Official reference:

https://docs.frappe.io/framework/user/en/bench/bench-commands

---

# 14. Verify the App Exists

Run:

```bash
cd ~/frappe-bench
bench list-apps
```

Or inspect the app directory:

```bash
ls -la ~/frappe-bench/apps/frappe_docai
```

You should have:

```text
~/frappe-bench/apps/frappe_docai
```

---

# 15. Install Python Dependencies

The development project used:

```text
google-cloud-documentai
```

and the V3 provider also requires Google authentication libraries.

Install the dependencies into the Bench environment:

```bash
cd ~/frappe-bench

bench pip install google-cloud-documentai
bench pip install google-auth
```

The development environment used:

```text
google-cloud-documentai 3.15.0
```

If your repository already declares these dependencies in its Python project metadata, allow the repository's dependency configuration to take precedence.

Verify:

```bash
bench pip show google-cloud-documentai
bench pip show google-auth
```

---

# 16. Install the App on the Site

Replace:

```text
<SITE_NAME>
```

with the target site.

Command:

```bash
bench --site <SITE_NAME> install-app frappe_docai
```

Example:

```bash
bench --site vendor2.site install-app frappe_docai
```

Frappe's official installation model is:

```text
get app onto bench
        ↓
bench --site SITE install-app APP
```

Official reference:

https://docs.frappe.io/framework/user/en/basics/apps

---

# 17. Verify App Installation

```bash
bench --site <SITE_NAME> list-apps
```

Expected:

```text
frappe
erpnext
frappe_docai
```

---

# 18. Migrate

Run:

```bash
bench --site <SITE_NAME> migrate
```

Example:

```bash
bench --site vendor2.site migrate
```

---

# 19. Clear Cache

Run:

```bash
bench --site <SITE_NAME> clear-cache
bench --site <SITE_NAME> clear-website-cache
```

Example:

```bash
bench --site vendor2.site clear-cache
bench --site vendor2.site clear-website-cache
```

---

# 20. Restart Bench

For a production-managed Bench:

```bash
bench restart
```

For development mode, use:

```bash
bench start
```

Frappe's official Bench documentation describes `bench restart` for restarting managed processes and `bench start` for development usage.

---

# 21. Confirm the Custom DocTypes

After installation, the app should provide the required configuration / logging DocTypes.

The V3 environment uses:

```text
Google Cloud Connection
OCR Configuration
OCR API Log
```

You can verify from Bench:

```bash
bench --site <SITE_NAME> console
```

Then:

```python
import frappe

for name in [
    "Google Cloud Connection",
    "OCR Configuration",
    "OCR API Log",
]:
    print(name, "=>", frappe.db.exists("DocType", name))
```

Expected:

```text
Google Cloud Connection => <name>
OCR Configuration => <name>
OCR API Log => <name>
```

---

# 22. Configure Google Cloud Connection in Frappe

Open:

```text
Google Cloud Connection
```

Create a record.

The current V3 DocType contains fields including:

```text
Enabled
Connection Name
Google Cloud Project ID
Service Account Email
GCS Input Bucket
GCS Output Bucket
Input Folder / Prefix
Output Folder / Prefix
Service Account JSON
```

For the current V3 direct Gemini runtime, configure the important fields as:

```text
Enabled:
1

Connection Name:
Frappe Document AI

Google Cloud Project ID:
<PROJECT_ID>

Service Account Email:
frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com

Service Account JSON:
<private uploaded JSON file>
```

The GCS fields can remain unused for the current direct-PDF runtime unless you intentionally enable a GCS-based legacy workflow.

---

# 23. Upload the Service Account JSON to Frappe

In the `Google Cloud Connection` record:

```text
Service Account JSON
```

Upload the JSON generated earlier.

The file should be stored as a private Frappe attachment.

Do not put the JSON in:

```text
public/files
```

Do not paste the private key contents into a Client Script.

---

# 24. Configure OCR Configuration

Open:

```text
OCR Configuration
```

Create or edit the configuration.

The important fields are:

```text
Enabled
Google Cloud Connection
Semantic Provider
Semantic Model
Semantic Location
Semantic Endpoint
Extraction Instructions
Output Schema
```

Recommended V3 values:

```text
Enabled:
1

Google Cloud Connection:
<Google Cloud Connection record>

Semantic Provider:
Google Agent Platform

Semantic Model:
gemini-3.5-flash-lite

Semantic Location:
global

Semantic Endpoint:
blank
```

---

# 25. OCR Output Schema

The schema is configuration-driven.

The V3 invoice configuration currently uses the following general structure:

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

The schema is not hardcoded to one business document. Create a different OCR Configuration for another document type when needed.

---

# 26. Configure Extraction Instructions

Extraction instructions are stored in:

```text
OCR Configuration → Extraction Instructions
```

The instructions should describe:

```text
What document is being processed
Which fields to extract
How to interpret dates
How to interpret line items
How to interpret taxes
What to do when evidence is missing
```

Keep the instructions specific to the configured document type.

Do not put Google service-account credentials in the instructions.

---

# 27. V3 Response Schema Behavior

The V3 provider automatically converts object properties into required response-schema properties.

This was added because the model previously returned intermittent sparse objects such as:

```json
{
  "vendor_name": "TEN INDIA",
  "invoice_number": null,
  "date": null,
  "line_items": []
}
```

After making object properties required, repeated tests became stable.

The response still remains subject to document evidence; a field can be null where the configured schema permits that behavior.

---

# 28. Current V3 API

The main API is:

```text
frappe_docai.api.process
```

Arguments:

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

Example:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "<OCR_CONFIGURATION_NAME>"
    },
    callback: function(r) {
        console.log(r.message);
    }
});
```

---

# 29. Client Script Integration

The recommended pattern is:

```javascript
const response = await frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_doc.file_url,
        configuration: "<OCR_CONFIGURATION_NAME>"
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

Use:

```text
result
```

for populating ERPNext fields.

---

# 30. Why `corrected` Should Be Used

The response contains:

```text
extracted
corrected
```

Use:

```javascript
response.message.corrected
```

for the final ERPNext data.

Conceptually:

```text
Gemini
  ↓
extracted
  ↓
financial validator
  ↓
corrected
```

The validator exists because model output can contain arithmetic or tax-structure mistakes.

---

# 31. Basic API Test

First upload a test PDF into Frappe.

Assume the file URL is:

```text
/private/files/invoice.pdf
```

Then execute:

```bash
bench --site <SITE_NAME> execute frappe_docai.api.process \
  --kwargs '{"file_url":"/private/files/invoice.pdf","configuration":"<OCR_CONFIGURATION_NAME>"}'
```

Example:

```bash
bench --site vendor2.site execute frappe_docai.api.process \
  --kwargs '{"file_url":"/private/files/TEN BILL (1).pdf","configuration":"7ujjqp2oki"}'
```

The response should contain:

```text
valid
configuration
file_name
mime_type
extracted
corrected
financial_validation
validation
usageMetadata
token_usage
credits_used_inr
timings
```

---

# 32. Direct Google Connectivity Test

Before debugging Frappe, test the Google endpoint independently.

The V3 endpoint has this form:

```text
https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/global/publishers/google/models/gemini-3.5-flash-lite:generateContent
```

The application obtains an OAuth access token from the service-account JSON.

A minimal authenticated test can be run from the Frappe environment using Python:

```python
from google.auth.transport.requests import Request
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(
    "/path/to/service-account.json",
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)

credentials.refresh(Request())

print("TOKEN AVAILABLE:", bool(credentials.token))
```

A `True` result confirms the credentials can obtain an OAuth token.

---

# 33. Direct Gemini Minimal Test

A minimal JSON generation test is useful before testing a PDF.

Expected shape:

```text
POST
aiplatform.googleapis.com
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
```

Example request body:

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "Return only JSON: {\"ok\": true}"
        }
      ]
    }
  ],
  "generationConfig": {
    "temperature": 0,
    "responseMimeType": "application/json",
    "responseSchema": {
      "type": "OBJECT",
      "properties": {
        "ok": {
          "type": "BOOLEAN"
        }
      },
      "required": [
        "ok"
      ]
    }
  }
}
```

Expected:

```text
HTTP 200
```

and JSON similar to:

```json
{"ok": true}
```

---

# 34. Direct PDF Test

The V3 provider sends the PDF as:

```text
inlineData
    mimeType = application/pdf
    data = base64(pdf)
```

along with the prompt.

A direct authenticated PDF test should return:

```text
HTTP 200
```

and model-generated JSON.

Google's current documentation also provides a PDF + Gemini example using `application/pdf` document input.

Official reference:

https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-with-pdf

---

# 35. Expected Test Sequence

Always test in this order:

```text
1. Bench works
2. App exists
3. App installed
4. Dependencies installed
5. Google Cloud API enabled
6. Service account exists
7. Vertex AI User role assigned
8. JSON key created
9. JSON uploaded privately
10. Google Cloud Connection saved
11. OCR Configuration saved
12. Minimal authenticated Google call
13. Direct PDF Gemini call
14. frappe_docai.api.process
15. Client Script
16. ERPNext field population
```

This prevents a Client Script problem from being confused with a Google authentication problem.

---

# 36. Troubleshooting — App Installation

## `ModuleNotFoundError`

Check:

```bash
bench pip show google-auth
bench pip show google-cloud-documentai
```

Install:

```bash
bench pip install google-auth
bench pip install google-cloud-documentai
```

Then:

```bash
bench --site <SITE_NAME> migrate
bench --site <SITE_NAME> clear-cache
bench restart
```

---

# 37. Troubleshooting — App Not Found

Check:

```bash
ls -la ~/frappe-bench/apps/frappe_docai
```

Then:

```bash
bench list-apps
```

If the repository was cloned directly but not installed:

```bash
bench --site <SITE_NAME> install-app frappe_docai
```

---

# 38. Troubleshooting — `401 UNAUTHENTICATED`

A 401 from:

```text
aiplatform.googleapis.com
```

usually means the request did not contain a valid OAuth bearer token.

Check:

```text
Service-account JSON
Service-account email
Project ID
Token generation
Authorization header
```

Do not solve a 401 by exposing the service-account private key in JavaScript.

---

# 39. Troubleshooting — `403 PERMISSION_DENIED`

Check that the service account has:

```text
roles/aiplatform.user
```

Command:

```bash
gcloud projects get-iam-policy <PROJECT_ID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com" \
  --format="table(bindings.role)"
```

You should see:

```text
roles/aiplatform.user
```

---

# 40. Troubleshooting — Request Hangs

The provider uses an HTTP timeout.

The current V3 implementation uses:

```text
30 seconds
```

If a request takes longer, inspect:

```text
Google connectivity
model endpoint
authentication
Google response
network path
```

The application reports network errors with their exception text.

A direct endpoint test is useful:

```bash
curl -I --connect-timeout 5 --max-time 10 \
  https://aiplatform.googleapis.com
```

A normal response from the host confirms the endpoint is reachable, although it does not authenticate or execute the model call.

---

# 41. Troubleshooting — Sparse Gemini Output

The V3 response schema should include required object properties.

The app automatically adds:

```text
required
```

for object properties in the Agent Platform response schema.

The provider also uses:

```text
temperature = 0
```

The combination was tested against the primary invoice and produced five consecutive complete results.

---

# 42. Troubleshooting — Wrong Financial Data

Do not immediately change the Gemini prompt.

First inspect:

```text
OCR API Log
```

Compare:

```text
raw_response
extracted_json
corrected_json
financial_validation
validation
```

This tells you whether the problem came from:

```text
Gemini extraction
```

or:

```text
financial validation
```

---

# 43. OCR API Log

The application records an `OCR API Log` for observability.

Useful fields:

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

This log should be used when diagnosing production behavior.

---

# 44. Cost Tracking

V3 records the model's usage metadata.

Typical fields include:

```text
input_tokens
output_tokens
total_tokens
usageMetadata
estimated USD
estimated INR
```

The application-side estimated cost is useful for internal auditing, but the final Google Cloud billing statement should always be treated as the source of truth for actual charged usage.

Google model billing is usage-based rather than a single fixed price per API call.

Official pricing:

https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing

---

# 45. Optional Legacy Google APIs

These are **not required for the current V3 direct PDF → Gemini runtime**, but they may be required if a future/legacy flow intentionally uses them.

## Enable Document AI API

```bash
gcloud services enable documentai.googleapis.com \
  --project=<PROJECT_ID>
```

## Enable Vision API

```bash
gcloud services enable vision.googleapis.com \
  --project=<PROJECT_ID>
```

## Enable Cloud Storage API

```bash
gcloud services enable storage.googleapis.com \
  --project=<PROJECT_ID>
```

Do not create a Document AI processor or GCS pipeline just because these APIs can be enabled. The current V3 runtime does not need them for normal direct PDF extraction.

---

# 46. Optional GCS Configuration

The `Google Cloud Connection` DocType contains:

```text
GCS Input Bucket
GCS Output Bucket
Input Folder / Prefix
Output Folder / Prefix
```

These fields exist for Google Cloud Storage-related functionality.

If a deployment intentionally uses a GCS workflow, create the bucket and configure these fields.

For the current direct PDF → Gemini runtime, they can remain unused.

---

# 47. Production Security Checklist

```text
[ ] Service-account JSON is private
[ ] Service-account JSON is not in GitHub
[ ] Service-account JSON is not in JavaScript
[ ] Service-account JSON is not in public/files
[ ] Client Script does not contain Google private credentials
[ ] Google OAuth token is generated server-side
[ ] Only the required IAM roles are granted
[ ] OCR API Log does not expose secrets
[ ] Billing account is monitored
```

---

# 48. Complete Frappe Installation Command Set

Replace:

```text
<YOUR_GITHUB_REPOSITORY>
<SITE_NAME>
<BRANCH_NAME>
```

with real values.

```bash
cd ~/frappe-bench

bench get-app <YOUR_GITHUB_REPOSITORY>

bench pip install google-auth
bench pip install google-cloud-documentai

bench --site <SITE_NAME> install-app frappe_docai

bench --site <SITE_NAME> migrate

bench --site <SITE_NAME> clear-cache
bench --site <SITE_NAME> clear-website-cache

bench --site <SITE_NAME> list-apps

bench restart
```

If a branch is required:

```bash
cd ~/frappe-bench

bench get-app --branch <BRANCH_NAME> <YOUR_GITHUB_REPOSITORY>
```

---

# 49. Complete Google Cloud CLI Setup

Replace all placeholders:

```bash
PROJECT_ID="<PROJECT_ID>"
SA_NAME="frappe-docai"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

Set project:

```bash
gcloud config set project "$PROJECT_ID"
```

Enable APIs:

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  serviceusage.googleapis.com \
  --project="$PROJECT_ID"
```

Create service account:

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="Frappe Document AI"
```

Grant Vertex AI User:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/aiplatform.user"
```

Create JSON key:

```bash
gcloud iam service-accounts keys create \
  ~/frappe-docai-service-account.json \
  --iam-account="$SA_EMAIL"
```

Protect the key:

```bash
chmod 600 ~/frappe-docai-service-account.json
```

---

# 50. Complete Frappe Configuration Checklist

## Google Cloud Connection

```text
Enabled:
1

Connection Name:
Frappe Document AI

Google Cloud Project ID:
<PROJECT_ID>

Service Account Email:
frappe-docai@<PROJECT_ID>.iam.gserviceaccount.com

Service Account JSON:
<private uploaded JSON>
```

## OCR Configuration

```text
Enabled:
1

Google Cloud Connection:
<Google Cloud Connection record>

Semantic Provider:
Google Agent Platform

Semantic Model:
gemini-3.5-flash-lite

Semantic Location:
global

Semantic Endpoint:
blank

Extraction Instructions:
<document-specific instructions>

Output Schema:
<document-specific JSON schema>
```

---

# 51. Client Script API Call

Minimal:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "<OCR_CONFIGURATION_NAME>"
    },
    callback: function(r) {

        const apiResult = r.message || {};

        if (!apiResult.valid) {
            frappe.msgprint(
                apiResult.validation?.reason ||
                __("Document extraction failed.")
            );
            return;
        }

        const result =
            apiResult.corrected || {};

        console.log(result);
    }
});
```

---

# 52. Full Deployment Validation

Once everything is configured:

```bash
bench --site <SITE_NAME> console
```

Check:

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

Then run the real API against a test PDF:

```bash
bench --site <SITE_NAME> execute frappe_docai.api.process \
  --kwargs '{"file_url":"/private/files/<TEST_PDF>.pdf","configuration":"<OCR_CONFIGURATION_NAME>"}'
```

Expected:

```text
valid = true
```

and a populated:

```text
corrected
```

object.

---

# 53. Deployment Order — One Page

For a fresh server:

```text
Frappe / ERPNext
       ↓
Bench
       ↓
Get frappe_docai from GitHub
       ↓
Install Python dependencies
       ↓
Install app on site
       ↓
Migrate
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
```

---

# 54. Common Mistakes to Avoid

## Mistake 1 — Calling the old API

Do not use:

```javascript
frappe_docai.api.process_invoice
```

for the V3 integration.

Use:

```javascript
frappe_docai.api.process
```

## Mistake 2 — Reading the wrong result object

Do not use:

```javascript
response.message.extracted
```

as the final ERPNext accounting data.

Use:

```javascript
response.message.corrected
```

## Mistake 3 — Putting credentials in JavaScript

Never put:

```text
service-account JSON
private key
OAuth token
```

into a Client Script.

## Mistake 4 — Assuming API request count equals billed cost

Request metrics and billed SKU usage are separate measurements.

Use `OCR API Log` for application-side token/cost tracking and Google Cloud Billing for actual Google charges.

## Mistake 5 — Treating line-level 18% + line-level 18% as 36%

Tax percentages from different taxable bases must not be blindly added.

This tax-normalization rule belongs in the deterministic financial validation layer.

---

# 55. Current V3 Architecture

```text
                         ┌──────────────────────────┐
                         │        ERPNext            │
                         │      Payment Entry        │
                         └────────────┬─────────────┘
                                      │
                                Upload PDF
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │      frappe_docai         │
                         │         V3 API            │
                         └────────────┬─────────────┘
                                      │
                              OCR Configuration
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │      Gemini / Vertex      │
                         │   Direct PDF processing   │
                         └────────────┬─────────────┘
                                      │
                                  JSON output
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │   Financial Validator     │
                         │    Deterministic rules    │
                         └────────────┬─────────────┘
                                      │
                               Corrected JSON
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       Client Script       │
                         │    ERPNext field mapping  │
                         └──────────────────────────┘
```

---

# 56. Official Documentation

## Frappe

Bench commands:

https://docs.frappe.io/framework/user/en/bench/bench-commands

Frappe apps:

https://docs.frappe.io/framework/user/en/basics/apps

Create a site:

https://docs.frappe.io/framework/user/en/tutorial/create-a-site

Production setup:

https://docs.frappe.io/framework/user/en/production-setup

## Google Cloud

Gemini 3.5 Flash-Lite:

https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite

Agent Platform locations:

https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations

Vertex AI IAM:

https://cloud.google.com/vertex-ai/docs/general/access-control

Create service accounts:

https://docs.cloud.google.com/iam/docs/service-accounts-create

Service-account keys:

https://docs.cloud.google.com/iam/docs/keys-create-delete

Process PDF with Gemini:

https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-with-pdf

Agent Platform pricing:

https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing

---

# 57. Final Checklist

Before declaring the deployment complete:

```text
Frappe
[ ] Frappe 16.x installed
[ ] ERPNext 16.x installed
[ ] Bench working
[ ] frappe_docai downloaded from GitHub
[ ] frappe_docai installed on site
[ ] Dependencies installed
[ ] Site migrated
[ ] Cache cleared
[ ] Bench restarted

Google Cloud
[ ] Project selected
[ ] Billing enabled
[ ] aiplatform.googleapis.com enabled
[ ] Service account created
[ ] roles/aiplatform.user granted
[ ] JSON key created
[ ] JSON kept private
[ ] gemini-3.5-flash-lite available
[ ] Global location configured

Frappe Configuration
[ ] Google Cloud Connection created
[ ] Project ID entered
[ ] Service-account email entered
[ ] JSON uploaded privately
[ ] OCR Configuration created
[ ] Provider = Google Agent Platform
[ ] Model = gemini-3.5-flash-lite
[ ] Location = global
[ ] Endpoint blank
[ ] Extraction instructions configured
[ ] Output schema configured

Testing
[ ] Minimal Google authentication test passes
[ ] Direct PDF Gemini test passes
[ ] frappe_docai.api.process passes
[ ] corrected JSON populated
[ ] OCR API Log created
[ ] Client Script calls process()
[ ] ERPNext fields populate correctly
```

---

# 58. Important Version Note

This guide describes the **current V3 runtime** developed in the project.

Some older documentation in the project describes a previous architecture based on:

```text
Google Document AI
Vision OCR
Custom table reconstruction
```

That older architecture should not be confused with the current V3 runtime:

```text
PDF
 ↓
Gemini 3.5 Flash-Lite
 ↓
financial validator
 ↓
corrected JSON
```

For a fresh V3 deployment, follow this document first.

---

# End

A successful installation has three independent parts:

```text
1. frappe_docai installed on the Frappe site
2. Google Cloud authentication + Vertex AI access working
3. OCR Configuration correctly mapped to the Google Cloud Connection
```

Once those three are correct, a Client Script can call:

```javascript
frappe.call({
    method: "frappe_docai.api.process",
    args: {
        file_url: file_url,
        configuration: "<OCR_CONFIGURATION_NAME>"
    }
});
```

and consume:

```javascript
response.message.corrected
```

as the final V3 document-extraction result.
