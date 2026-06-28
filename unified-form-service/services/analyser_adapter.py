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
        
        # Try direct database insertion if running inside unified Flask context
        try:
            from flask import current_app
            if current_app and current_app.extensions and "responses_col" in current_app.extensions:
                from datetime import datetime, timezone
                db_payload = dict(payload)
                db_payload["inserted_at"] = datetime.now(timezone.utc)
                
                col = current_app.extensions["responses_col"]
                col.insert_one(db_payload)
                logger.info("Successfully synced response directly to database analyser collection")
                return {
                    "synced": True, 
                    "payload": payload, 
                    "response": {"status": "success", "message": "Direct DB Insert"}
                }
        except Exception as e:
            logger.warning(f"Could not perform direct DB insert sync, falling back to HTTP: {str(e)}")

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
