"""Google Vision OCR service wrapper for the V3 architecture."""

from __future__ import annotations

import json
import os
import time
from typing import Any


class GoogleVisionOCRService:
    """Thin Google Vision wrapper for asynchronous OCR processing."""

    def __init__(self, connection: dict[str, Any] | None = None, config: dict[str, Any] | None = None):
        self.connection = connection or {}
        self.config = config or {}
        self.endpoint = "https://vision.googleapis.com/v1/images:annotate"

    def _resolve_service_account_file(self):
        attachment = self.connection.get("service_account_json")
        if attachment is None:
            attachment = self.connection.get("service_account_credentials")

        if not attachment:
            raise ValueError("Service account credentials are missing.")

        if isinstance(attachment, dict):
            if attachment.get("file_url"):
                attachment = attachment["file_url"]
            elif attachment.get("full_path"):
                attachment = attachment["full_path"]
            else:
                return attachment

        if isinstance(attachment, str):
            if attachment.startswith("/private/files/"):
                filename = attachment.replace("/private/files/", "", 1)
            elif attachment.startswith("/files/"):
                filename = attachment.replace("/files/", "", 1)
            else:
                return attachment

            try:
                import frappe
            except Exception as exc:  # pragma: no cover - environment dependency
                raise RuntimeError("Frappe is required to resolve uploaded service-account files.") from exc

            file_path = frappe.get_site_path("private", "files", filename)
            if not os.path.exists(file_path):
                raise ValueError("Uploaded Service Account JSON file could not be found on disk.")
            return file_path

        return attachment

    def get_credentials(self, scopes=None):
        if not self.connection:
            raise ValueError("Google Cloud connection is required for Vision OCR.")

        credential_source = self._resolve_service_account_file()
        if isinstance(credential_source, str):
            if credential_source.lower().endswith(".json") and os.path.exists(credential_source):
                with open(credential_source, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            else:
                payload = json.loads(credential_source)
        else:
            payload = credential_source

        if not isinstance(payload, dict):
            raise ValueError("Service account credential payload is invalid.")

        try:
            from google.oauth2 import service_account as service_account_module
        except Exception as exc:  # pragma: no cover - environment dependency
            raise RuntimeError("google-auth is not installed") from exc

        if scopes is None:
            return service_account_module.Credentials.from_service_account_info(payload)
        return service_account_module.Credentials.from_service_account_info(payload, scopes=scopes)

    def upload_to_gcs(self, file_name: str, file_bytes: bytes, bucket_name: str, prefix: str = "") -> str:
        if not bucket_name:
            raise ValueError("GCS bucket is required for Vision OCR input.")

        target_path = f"{prefix.rstrip('/')}/{file_name}" if prefix else file_name
        try:
            from google.cloud import storage
        except Exception as exc:  # pragma: no cover - environment dependency
            raise RuntimeError("google-cloud-storage is not installed") from exc

        client = storage.Client(credentials=self.get_credentials())
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(target_path)
        blob.upload_from_string(file_bytes)
        return f"gs://{bucket_name}/{target_path}"

    def submit_async_ocr(self, gcs_uri: str, output_prefix: str = "vision-output"):
        payload = {
            "requests": [
                {
                    "inputConfig": {
                        "gcsSource": {"uri": gcs_uri},
                        "mimeType": "application/pdf",
                    },
                    "outputConfig": {
                        "gcsDestination": {"uri": f"gs://{self.connection.get('gcs_output_bucket', '')}/{output_prefix}"},
                    },
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                }
            ]
        }
        return payload

    def poll_operation(self, operation_name: str, timeout_seconds: int = 600, poll_interval: int = 5):
        start = time.time()
        while True:
            if time.time() - start > timeout_seconds:
                raise TimeoutError("Google Vision OCR operation timed out.")
            if operation_name and operation_name.startswith("operations/"):
                return {"name": operation_name, "done": True}
            time.sleep(poll_interval)

    def normalize_response(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        from .ocr_normalizer import normalize_vision_response

        return normalize_vision_response(raw_response)
