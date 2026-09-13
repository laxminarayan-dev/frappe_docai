# Frappe Document AI

Google Cloud Document AI integration for Frappe/ERPNext 16.x.

This app provides reusable backend functionality for extracting vendor-invoice information from uploaded Frappe files.

## Installation

### Requirements

- Frappe 16.x
- ERPNext 16.x
- A working Frappe bench
- A working Frappe site
- Google Cloud account
- Google Cloud Document AI
- A Google Cloud service account with access to the selected Document AI processor

### 1. Download the app

Run:

```bash
cd ~/frappe-bench

bench get-app https://github.com/laxminarayan-dev/frappe_docai.git --branch version-1
```

### 2. Install the Google Document AI dependency

Run:

```bash
cd ~/frappe-bench

bench pip install google-cloud-documentai
```

Verify:

```bash
bench pip show google-cloud-documentai
```

### 3. Install the app

Replace `YOUR_SITE_NAME` with your Frappe site name:

```bash
bench --site YOUR_SITE_NAME install-app frappe_docai
```

### 4. Migrate and clear cache

```bash
bench --site YOUR_SITE_NAME migrate
bench --site YOUR_SITE_NAME clear-cache
bench --site YOUR_SITE_NAME clear-website-cache
```

If your bench uses Supervisor:

```bash
bench restart
```

### 5. Verify the app

```bash
bench --site YOUR_SITE_NAME list-apps
```

You should see:

```text
frappe_docai
```

---

# Google Cloud Setup

After installing the app, configure Google Cloud.

You need to collect these five values:

```text
1. Google Cloud Project ID
2. Google Cloud Location
3. Document AI Processor ID
4. Document AI Processor Version
5. Service Account JSON
```

## 6. Create or select a Google Cloud Project

Open Google Cloud Console and create/select the project that will own your Document AI processor.

Copy the actual **Project ID**.

Example:

```text
my-invoice-ai-project
```

Keep this value for the Frappe configuration.

## 7. Enable Document AI API

In Google Cloud:

```text
APIs & Services
→ Library
→ Search: Document AI API
→ Enable
```

## 8. Create a Service Account

Go to:

```text
IAM & Admin
→ Service Accounts
→ Create Service Account
```

Create a service account for the Frappe server.

Copy its email address.

## 9. Grant Document AI permissions

Grant the service account the permissions required to process documents with your selected processor.

The development setup used:

```text
Document AI API User (Beta)
Viewer (Beta)
```

Google Cloud roles can change. For a new project, verify the currently available Document AI permissions.

## 10. Create and download the JSON key

Go to:

```text
IAM & Admin
→ Service Accounts
→ YOUR SERVICE ACCOUNT
→ Keys
→ Add Key
→ Create new key
→ JSON
```

Download the JSON file.

### IMPORTANT SECURITY RULE

Never:

- Commit the JSON to Git
- Put it in this GitHub repository
- Put it in JavaScript
- Expose it to the browser
- Put it in a public Frappe attachment
- Put it directly in the app source code

The JSON must be uploaded privately in Frappe.

## 11. Create or select the Document AI Processor

Open:

```text
Google Cloud
→ Document AI
```

Create or select the processor you want to use.

This application was developed with a:

```text
Custom Extractor
```

## 12. Copy the Processor ID

Open the processor details and copy:

```text
Processor ID
```

Do not confuse Processor ID with Project ID.

## 13. Copy the Processor Location

From the processor details, copy its actual location.

Example:

```text
asia-south1
```

Do not blindly reuse this example for another project. Use the location shown for your processor.

## 14. Copy the Processor Version

Open the processor's versions/details and copy the actual processor version.

Example used during development:

```text
pretrained-foundation-model-v1.5-2025-08-06
```

Use the version actually available for your processor.

---

# Frappe Configuration

## 15. Open Document AI Configuration

After installing the app, open:

```text
Document AI Configuration
```

Enter:

```text
Enabled:
1

Google Cloud Project ID:
YOUR_PROJECT_ID

Google Cloud Location:
YOUR_PROCESSOR_LOCATION

Processor ID:
YOUR_PROCESSOR_ID

Processor Version:
YOUR_PROCESSOR_VERSION

Google Credentials JSON:
<upload the JSON as a PRIVATE attachment>
```

Save the configuration.

## 16. Configure Schema and Extraction Instructions

If you want the same invoice extraction behavior used by this project, copy the Schema JSON and Extraction Instructions from:

```text
docs/IMPLEMENTATION_GUIDE.md
```

---

# Payment Entry Integration

The current project also uses Payment Entry custom fields and a Payment Entry Client Script.

Those project-specific implementation details are documented separately in:

```text
docs/IMPLEMENTATION_GUIDE.md
```

---

# Complete Copy-Paste Installation

If the Frappe bench and site already exist, copy this block and replace only `YOUR_SITE_NAME`:

```bash
cd ~/frappe-bench

bench get-app https://github.com/laxminarayan-dev/frappe_docai.git --branch version-16

bench pip install google-cloud-documentai

bench --site YOUR_SITE_NAME install-app frappe_docai

bench --site YOUR_SITE_NAME migrate

bench --site YOUR_SITE_NAME clear-cache

bench --site YOUR_SITE_NAME clear-website-cache

bench restart

bench --site YOUR_SITE_NAME list-apps
```

Then complete the Google Cloud and Frappe configuration above.

---

# Troubleshooting

## App not found

Check:

```bash
bench --site YOUR_SITE_NAME list-apps
```

## `process_invoice` not found

Make sure the backend contains the public API:

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

## Google authentication failure

Check:

```text
Project ID
Service Account JSON
Private Frappe file
Document AI API
IAM permissions
Processor ID
Location
Processor Version
```

## More troubleshooting

See:

```text
docs/IMPLEMENTATION_GUIDE.md
```

---

# Repository

GitHub:

```text
https://github.com/laxminarayan-dev/frappe_docai
```

Branch:

```text
version-16
```

License:

```text
MIT
```
