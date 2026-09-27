# Copyright (c) 2026, Laxmi Narayan and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe.model.document import Document


class GoogleCloudConnection(Document):
    """Reusable Google Cloud connection settings for OCR and GCS workflows."""

    def validate(self):
        file_url = self.service_account_json or ""
        if not file_url:
            frappe.throw("Service Account JSON is required.")

        filename = file_url.split("/")[-1]
        if not filename.lower().endswith(".json"):
            frappe.throw("Service Account JSON must be a .json file.")

        if file_url.startswith("/private/files/"):
            file_path = frappe.get_site_path("private", "files", filename)
        elif file_url.startswith("/files/"):
            file_path = frappe.get_site_path("private", "files", filename)
        else:
            file_path = file_url

        if not os.path.exists(file_path):
            frappe.throw("Uploaded Service Account JSON file could not be found on disk.")

        with open(file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, dict):
            frappe.throw("Uploaded Service Account JSON must contain a JSON object.")

        if payload.get("type") != "service_account":
            frappe.throw("Uploaded file is not a valid Google service-account JSON credential file.")
