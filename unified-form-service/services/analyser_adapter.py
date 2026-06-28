from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


def to_analyser_payload(form_snapshot: dict, response: dict) -> dict:
    return {
        "form_id": form_snapshot["form_id"],
        "survey_id": form_snapshot["form_id"],  # Compatibility with form-analyser id_field
        "response_id": response["response_id"],
        "form_snapshot_version": form_snapshot.get("snapshot_version", 1),
        "status": response["status"],
        "submitted_at": response.get("submitted_at"),
        "answers": response["answers"],
        "data": response["answers"],            # Compatibility with form-analyser data subdocument
    }


class AnalyserSyncService:
    def __init__(self):
        self.last_payload: dict | None = None
        self.analyser_url = os.getenv("ANALYSER_URL", "http://localhost:5001")
        self.api_key = os.getenv("ANALYSER_API_KEY", "fa_default_key_for_sync")

    def sync(self, form_snapshot: dict, response: dict) -> dict:
        payload = to_analyser_payload(form_snapshot, response)
        self.last_payload = payload
        
        # Real HTTP call to form-analyser
        url = f"{self.analyser_url.rstrip('/')}/api/v1/responses"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }
        
        # Prepare request
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                logger.info(f"Successfully synced response to analyser: {resp_data}")
                return {"synced": True, "payload": payload, "response": resp_data}
        except urllib.error.URLError as e:
            logger.error(f"Failed to sync response to analyser: {str(e)}")
            return {"synced": False, "payload": payload, "error": str(e)}
